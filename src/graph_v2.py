"""GraphRAG v2 extraction: paragraph chunks -> RiskMentions with verified quotes.

    python src/graph_v2.py --tickers GM,NXPI      # extract + validate only (writes the JSONL), no Neo4j

Replaces the workshop prompt (kept as graph-v1-workshop) for approach 2:
- chunks are whole paragraphs packed up to GRAPH_V2_CHUNK_CHARS, never cut mid-paragraph, no overlap;
- one structured-output call per chunk (schema enforced by the provider, system prompt cached);
- the model returns a verbatim quote, code finds its span (verify.locate) - the model never gives offsets;
- a mention survives only if its quote is in that chunk; drivers only if named in the quote's paragraph.
Company identity still comes from provenance: the filer of the 10-K is the company at risk.
"""
import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor

import config
import llm
from verify import locate

PROMPT_VERSION = "graph-v2"
DRIVER_TYPES = ["GEOGRAPHY", "NAMED_COUNTERPARTY", "INPUT_COMMODITY", "REGULATION_POLICY", "TECHNOLOGY_END_MARKET"]
_PARA = re.compile(r"[^\n]+(?:\n(?!\n)[^\n]+)*")


# --------------------------------------------------------------------------- chunks
def _split_long(text, start, end, size):
    """Cut a block longer than `size` at line breaks (else sentence ends), greedily, never mid-sentence."""
    if end - start <= size:
        return [(start, end)]
    block = text[start:end]
    cuts = [m.end() for m in re.finditer(r"\n", block)] or [m.end() for m in re.finditer(r"(?<=[.!?])\s+", block)]
    pieces, a, last = [], 0, 0
    for c in cuts + [len(block)]:
        if c - a > size and last > a:
            pieces.append((a, last))
            a = last
        last = c
    pieces.append((a, len(block)))
    out = []
    for s, e in pieces:
        s2, e2 = s + len(block[s:e]) - len(block[s:e].lstrip()), s + len(block[s:e].rstrip())
        if e2 > s2:
            out.append((start + s2, start + e2))
    return out


def paragraphs(text, size=None):
    """(start, end) of every paragraph (blocks separated by a blank line); blocks over `size` are cut."""
    size = size or config.GRAPH_V2_CHUNK_CHARS
    out = []
    for m in _PARA.finditer(text):
        if m.group().strip():
            out += _split_long(text, m.start(), m.end(), size)
    return out


def _is_subheading(par):
    s = par.strip()
    return len(s) <= 110 and "\n" not in s and not re.search(r"[.;:,]$", s) and len(s.split()) <= 14


def graph_chunks(filing, size=None):
    """Whole paragraphs packed up to `size` chars. Each chunk carries the latest section sub-heading."""
    size = size or config.GRAPH_V2_CHUNK_CHARS
    text, ticker = filing["text"], filing["ticker"]
    chunks, cur, heading, cur_heading = [], [], "", ""

    def flush():
        if cur:
            chunks.append({"id": f"{ticker}-g{len(chunks)}", "ticker": ticker, "index": len(chunks),
                           "start": cur[0][0], "end": cur[-1][1], "heading": cur_heading,
                           "text": text[cur[0][0]:cur[-1][1]]})

    for start, end in paragraphs(text):
        par = text[start:end]
        if _is_subheading(par) and "risk" in par.lower() and not par.lower().startswith("item 1a"):
            heading = par.strip()
        if cur and end - cur[0][0] > size:
            flush()
            cur = []
        if not cur:
            cur_heading = heading
        cur.append((start, end))
    flush()
    return chunks


# --------------------------------------------------------------------------- prompt
MENTIONS_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["mentions"],
    "properties": {"mentions": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["heading", "risk_name", "detail", "quote", "specificity", "drivers"],
        "properties": {
            "heading": {"type": "string"},
            "risk_name": {"type": "string"},
            "detail": {"type": "string"},
            "quote": {"type": "string"},
            "specificity": {"type": "string", "enum": ["specific", "boilerplate"]},
            "drivers": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["name", "type"],
                "properties": {"name": {"type": "string"}, "type": {"type": "string", "enum": DRIVER_TYPES}}}},
        }}}},
}

# Two worked examples from outside the demo group (an airline and a retailer), written in the style of
# 10-K risk-factor language for this prompt. A test checks every quote occurs verbatim in its input.
FEW_SHOT = [
    {
        "input": (
            "Our business is highly dependent on the price and availability of aircraft fuel.\n\n"
            "Aircraft fuel is our second-largest operating expense. Prices rose sharply after supply disruptions "
            "in the Middle East, and we do not hedge more than 20% of our expected consumption. A sustained "
            "increase of $10 per barrel would raise our annual fuel expense by approximately $400 million.\n\n"
            "We rely on a single manufacturer for our narrow-body fleet.\n\n"
            "All of our narrow-body aircraft are built by Airbus, and delivery delays of the A321neo have already "
            "forced us to reduce planned capacity. Any further delay could limit our growth."
        ),
        "output": {"mentions": [
            {"heading": "Dependence on the price and availability of aircraft fuel",
             "risk_name": "Jet fuel price volatility",
             "detail": "Fuel is second-largest expense; hedges at most 20%; +$10/bbl adds about $400 million a year",
             "quote": "A sustained increase of $10 per barrel would raise our annual fuel expense by approximately "
                      "$400 million.",
             "specificity": "specific",
             "drivers": [{"name": "Middle East", "type": "GEOGRAPHY"},
                         {"name": "aircraft fuel", "type": "INPUT_COMMODITY"}]},
            {"heading": "Reliance on a single aircraft manufacturer",
             "risk_name": "Single-source aircraft supplier dependence",
             "detail": "All narrow-body aircraft from Airbus; A321neo delivery delays already cut capacity",
             "quote": "All of our narrow-body aircraft are built by Airbus, and delivery delays of the A321neo have "
                      "already forced us to reduce planned capacity.",
             "specificity": "specific",
             "drivers": [{"name": "Airbus", "type": "NAMED_COUNTERPARTY"}]},
        ]},
    },
    {
        "input": (
            "Risks Related to Information Security\n\n"
            "We are subject to cyber attacks and other security incidents.\n\n"
            "Like other companies, we face threats to our information systems, and a breach could disrupt our "
            "operations and harm our reputation.\n\n"
            "New tariffs on imported goods could increase our costs.\n\n"
            "About 60% of the merchandise we sell is sourced from China and Vietnam. Tariffs imposed under "
            "Section 301 have increased the landed cost of these goods, and we may not be able to pass the "
            "increase on to customers."
        ),
        "output": {"mentions": [
            {"heading": "Cyber attacks and other security incidents",
             "risk_name": "Cybersecurity breach of information systems",
             "detail": "Generic statement; no specific systems, incidents or magnitudes named",
             "quote": "Like other companies, we face threats to our information systems, and a breach could "
                      "disrupt our operations and harm our reputation.",
             "specificity": "boilerplate",
             "drivers": []},
            {"heading": "Tariffs on imported goods",
             "risk_name": "Import tariff cost increase",
             "detail": "About 60% of merchandise sourced from China and Vietnam; Section 301 tariffs raise landed cost",
             "quote": "Tariffs imposed under Section 301 have increased the landed cost of these goods, and we may "
                      "not be able to pass the increase on to customers.",
             "specificity": "specific",
             "drivers": [{"name": "China", "type": "GEOGRAPHY"}, {"name": "Vietnam", "type": "GEOGRAPHY"},
                         {"name": "Section 301", "type": "REGULATION_POLICY"}]},
        ]},
    },
]

_RULES = """You are a credit analyst reading Item 1A (Risk Factors) of a company's annual 10-K filing. You list the \
risks that could hurt the filer's ability to operate and repay its debt. The filer is always the company at risk: \
never output a company name or ticker as a risk.

UNIT. Return one mention per distinct risk factor in the excerpt. A risk factor is usually a heading sentence followed \
by one or more paragraphs. If one risk factor clearly covers two different drivers (for example a named input \
shortage and a separate regulation), return two mentions, each with its own quote. For a bullet list, return one \
mention per substantive bullet; if the bullets are only a few words each, return one mention for the whole list.

FIELDS
- heading: the risk factor's heading sentence, or a 5-12 word paraphrase if it has none.
- risk_name: 3-7 words that name the driver and its mechanism of harm, worded so another company could use the same \
name, but never vaguer than the text. Write "Semiconductor supply shortage", not "Supply chain issues"; "Customer \
concentration in auto OEMs", not "Concentration". Noun phrase in sentence case. Do not start with "Risk of" or \
"Risks related to". No company names, no tickers.
- detail: at most 25 words on what is specific to this company: named places, inputs, programmes, customers, \
magnitudes. Say "Generic statement" if there is nothing specific.
- quote: 1-3 consecutive sentences copied EXACTLY, character for character, from the excerpt (15-60 words) that \
support risk_name. Prefer the sentence with the most specific evidence over the heading.
- specificity: "boilerplate" if any public company could have written the quote word for word (generic cyber \
attacks, generic litigation, "general economic conditions", forward-looking-statement language); otherwise "specific".
- drivers: only entities NAMED in the quote or its paragraph, written as in the text: places (Taiwan, China), named \
suppliers or customers, inputs (gallium, lithium, rare earth magnets), laws and policies (Inflation Reduction Act, \
Section 232 tariffs, CAFE standards), end markets or technologies (EV demand, AI data centers). Do not infer a \
driver that is not named. Empty list if none.

DO NOT invent risks or text. Do not merge two different risk factors into one mention. Do not split one risk factor \
into several mentions with synonymous names. Do not extract from the introductory disclaimer or from section \
sub-headings alone. Do not give opinions or severity. If the excerpt has no risk factor, return {"mentions": []}.
"""


def system_prompt():
    examples = "\n\n".join(
        f"EXAMPLE {i + 1} - excerpt:\n{ex['input']}\n\nEXAMPLE {i + 1} - output:\n{json.dumps(ex['output'], indent=1)}"
        for i, ex in enumerate(FEW_SHOT))
    return _RULES + "\nTwo worked examples from companies outside this analysis:\n\n" + examples


SYSTEM_V2 = system_prompt()


def user_prompt(filing, chunk):
    section = f"Section: {chunk['heading']}\n" if chunk["heading"] else ""
    return (f"Company: {filing['company']} ({filing['ticker']}), 10-K accession {filing['accession']}.\n"
            f"{section}Excerpt {chunk['id']}:\n\n{chunk['text']}")


# --------------------------------------------------------------------------- extract + validate
def extract(filings):
    """One structured call per chunk. Returns (chunks, records); records keep the raw replies."""
    chunks = [(f, c) for f in filings for c in graph_chunks(f)]

    def one(fc):
        f, c = fc
        with llm.METER.as_stage("graph.build"):
            reply = llm.chat(SYSTEM_V2, user_prompt(f, c), schema=MENTIONS_SCHEMA, schema_name="risk_mentions")
        return {"chunk_id": c["id"], "ticker": f["ticker"], "prompt_version": PROMPT_VERSION,
                "mentions": reply.get("mentions", [])}

    with ThreadPoolExecutor(max_workers=config.LLM_CONCURRENCY) as pool:
        records = list(pool.map(one, chunks))
    return [c for _, c in chunks], records


_SUFFIX = re.compile(r"\b(inc|corp|corporation|co|company|plc|n\.?v|ltd|holdings|the)\b\.?", re.I)
_COMMON_FIRST = {"general", "texas", "on", "the", "american", "united"}


def company_terms(filing):
    """Words that would make a risk name company-specific: the ticker and the company's core name."""
    core = re.sub(r"\s+", " ", _SUFFIX.sub(" ", filing["company"].replace(",", " "))).strip().lower()
    terms = {filing["ticker"].lower(), core}
    first = core.split(" ")[0] if core else ""
    if len(first) >= 3 and first not in _COMMON_FIRST:
        terms.add(first)
    return {t for t in terms if t}


def _paragraph_at(text, pos, spans):
    for s, e in spans:
        if s <= pos < e:
            return s, e
    return max(0, pos - 400), min(len(text), pos + 400)


def validate(filings, chunks, records):
    """Keep a mention only if its quote is found inside its own chunk. Returns (accepted, rejected)."""
    by_ticker = {f["ticker"]: f for f in filings}
    by_chunk = {c["id"]: c for c in chunks}
    para_spans = {t: paragraphs(f["text"]) for t, f in by_ticker.items()}
    accepted, rejected = [], []
    for rec in records:
        f, c = by_ticker[rec["ticker"]], by_chunk[rec["chunk_id"]]
        terms = company_terms(f)
        for k, m in enumerate(rec["mentions"]):
            mid = f"{c['id']}-m{k}"
            name = (m.get("risk_name") or "").strip()
            base = {"id": mid, "ticker": f["ticker"], "chunk_id": c["id"], **m}
            words = set(re.findall(r"[a-z0-9]+", name.lower()))
            if not name:
                rejected.append({**base, "reason": "empty_name"})
                continue
            if any((t in words) if " " not in t else (t in name.lower()) for t in terms):
                rejected.append({**base, "reason": "company_in_name"})
                continue
            local = locate(m.get("quote", ""), f["text"][c["start"]:c["end"]])
            if local is None:
                elsewhere = locate(m.get("quote", ""), f["text"])
                rejected.append({**base, "reason": "outside_chunk" if elsewhere else "quote_not_found"})
                continue
            span = (c["start"] + local[0], c["start"] + local[1])
            ps, pe = _paragraph_at(f["text"], span[0], para_spans[f["ticker"]])
            paragraph = f["text"][ps:pe].lower()
            drivers = [d for d in m.get("drivers", []) if d.get("name", "").strip()
                       and d["name"].strip().lower() in paragraph]
            dropped = len(m.get("drivers", [])) - len(drivers)
            accepted.append({**base, "risk_name": name, "drivers": drivers, "drivers_dropped": dropped,
                             "start": span[0], "end": span[1], "paragraph": [ps, pe],
                             "prompt_version": rec["prompt_version"]})
    return accepted, rejected


def extract_path(version=PROMPT_VERSION):
    return config.RESULTS_DIR / f"graph_extract_{config.CORPUS}_{version}.jsonl"


def run(filings):
    """Extract and validate; write the raw JSONL and the rejections file. Returns (chunks, accepted, rejected)."""
    chunks, records = extract(filings)
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with extract_path().open("w") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")
    accepted, rejected = validate(filings, chunks, records)
    total = len(accepted) + len(rejected)
    reasons = {}
    for r in rejected:
        reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
    (config.RESULTS_DIR / f"graph_rejections_{config.CORPUS}.json").write_text(json.dumps(
        {"prompt_version": PROMPT_VERSION, "mentions": total, "accepted": len(accepted),
         "verification_rate": round(len(accepted) / total, 4) if total else None,
         "reasons": reasons, "rejected": rejected}, indent=1))
    print(f"  {len(chunks)} chunks, {total} mentions, {len(accepted)} verified"
          + (f" ({len(accepted) / total:.0%})" if total else "") + f"; rejected: {reasons or 'none'}")
    return chunks, accepted, rejected


if __name__ == "__main__":
    from corpus import load_corpus

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tickers", help="comma-separated subset (default: all filings in the corpus)")
    args = parser.parse_args()
    wanted = set(args.tickers.upper().split(",")) if args.tickers else None
    run([f for f in load_corpus() if not wanted or f["ticker"] in wanted])
