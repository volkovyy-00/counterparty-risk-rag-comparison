"""Approach 3 - taxonomy-first extraction.

The LLM does one narrow job: map each risk factor in a window of Item 1A onto a
fixed taxonomy id, with a verbatim quote. Everything after that - quote
checking, the company x category matrix, the ranking and the answer text - is
plain Python, so it is repeatable and auditable.
"""
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

import config
import llm
from answer import CATEGORY_IDS, CATEGORY_NAMES, TAXONOMY
from corpus import chunk_text, find_quote

SYSTEM = (
    "You are a credit risk analyst classifying the Risk Factors section (Item 1A) of a 10-K filing.\n"
    "For EVERY distinct risk factor in the excerpt (usually introduced by a heading sentence), return:\n"
    "- heading: the risk factor's heading or a 5-12 word paraphrase of it\n"
    "- category: the single best taxonomy id\n"
    "- quote: 15-50 words copied EXACTLY, character for character, from the excerpt, that justify the category\n"
    "Do not merge different risk factors. Do not invent text. If the excerpt contains no risk factor, return an empty list.\n\n"
    "Taxonomy:\n"
    + "\n".join(f"- {c['id']}: {c['name']} - {c['description']}" for c in TAXONOMY)
)

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["risk_factors"],
    "properties": {
        "risk_factors": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["heading", "category", "quote"],
                "properties": {
                    "heading": {"type": "string"},
                    "category": {"type": "string", "enum": CATEGORY_IDS},
                    "quote": {"type": "string"},
                },
            },
        }
    },
}


def _classify_window(filing, n, window):
    user = (f"Company: {filing['company']} ({filing['ticker']}), 10-K accession {filing['accession']}.\n"
            f"Excerpt {n + 1}:\n\n{window}")
    with llm.METER.as_stage("taxonomy.build"):
        reply = llm.chat(SYSTEM, user, schema=SCHEMA, schema_name="risk_factors")
    accepted, rejected = [], []
    for rf in reply["risk_factors"]:
        row = {"ticker": filing["ticker"], "company": filing["company"], "accession": filing["accession"],
               "url": filing["url"], "window": n, "heading": rf["heading"], "category": rf["category"],
               "quote": rf["quote"]}
        if rf["category"] not in CATEGORY_IDS:
            rejected.append(dict(row, reason="category not in taxonomy"))
            continue
        # Checked against this window, then this filing's Item 1A - never another company's text.
        if find_quote(rf["quote"], window) < 0 and find_quote(rf["quote"], filing["text"]) < 0:
            rejected.append(dict(row, reason="quote not found verbatim in source"))
            continue
        accepted.append(dict(row, filing_ref=f"{filing['accession']} Item 1A, excerpt {n + 1}"))
    return accepted, rejected


def build(filings):
    jobs = [(f, n, w) for f in filings
            for n, (_, w) in enumerate(chunk_text(f["text"], config.TAXO_WINDOW_CHARS, 0))]
    accepted, rejected = [], []
    with llm.METER.track("taxonomy.build"), ThreadPoolExecutor(config.LLM_CONCURRENCY) as pool:
        for ok, bad in pool.map(lambda job: _classify_window(*job), jobs):
            accepted += ok
            rejected += bad
    return pd.DataFrame(accepted), pd.DataFrame(rejected), len(jobs)


def aggregate(df, tickers):
    """Company x category matrix (number of risk factors) and the ranked shared categories."""
    matrix = pd.crosstab(df["ticker"], df["category"]).reindex(index=sorted(tickers), columns=CATEGORY_IDS,
                                                                fill_value=0)
    exposed = matrix > 0
    ranking = pd.DataFrame({
        "category": CATEGORY_IDS,
        "name": [CATEGORY_NAMES[c] for c in CATEGORY_IDS],
        "companies": [exposed[c].sum() for c in CATEGORY_IDS],
        "risk_factors": [matrix[c].sum() for c in CATEGORY_IDS],
        "tickers": [sorted(exposed.index[exposed[c]]) for c in CATEGORY_IDS],
    }).sort_values(["companies", "risk_factors"], ascending=False)
    return matrix, ranking[ranking["companies"] >= config.MIN_SHARED]


def run(question, filings):
    tickers = [f["ticker"] for f in filings]
    df, rejected, windows = build(filings)
    with llm.METER.track("taxonomy.ask"):  # no LLM calls here: pure pandas
        if df.empty:
            raise SystemExit("Taxonomy extraction accepted no risk factors - check the LLM settings.")
        matrix, ranking = aggregate(df, tickers)
        first_quote = df.drop_duplicates(["category", "ticker"]).set_index(["category", "ticker"])
        shared, evidence = [], {}
        for row in ranking.itertuples():
            citations = []
            for t in row.tickers:
                q = first_quote.loc[(row.category, t)]
                ref = f"{t}:x{q['window'] + 1}"  # short id for the table; full reference in evidence
                evidence[ref] = {"quote": q["quote"], "filing_ref": q["filing_ref"], "url": q["url"]}
                citations.append(ref)
            shared.append({"risk": row.name, "category": row.category, "tickers": row.tickers,
                           "citations": citations, "risk_factor_count": int(row.risk_factors)})
        top = ", ".join(f"{r['risk']} ({len(r['tickers'])} of {len(tickers)})" for r in shared[:5])
        summary = (f"{len(shared)} taxonomy categories are shared by at least {config.MIN_SHARED} of the "
                   f"{len(tickers)} counterparties. Most widely shared: {top}.")
    total = len(df) + len(rejected)
    return {
        "approach": "3_taxonomy_first",
        "summary": summary,
        "shared_risks": shared,
        "citation_check": {"claims": sum(len(r["tickers"]) for r in shared),
                           "supported_claims": sum(len(r["tickers"]) for r in shared),
                           "support_rate": 1.0 if shared else None,
                           "quotes_checked": total, "quotes_rejected": len(rejected),
                           "rejection_rate": round(len(rejected) / total, 3) if total else None},
        "stages": {"build": "taxonomy.build", "ask": "taxonomy.ask"},
        "details": {"windows_classified": windows, "risk_factors_accepted": len(df)},
        "evidence": evidence,
        "tables": {"matrix": matrix, "risk_factors": df, "rejections": rejected},
    }
