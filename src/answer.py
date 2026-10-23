"""The one output contract shared by every approach: a list of claims.

    {company, category, leaf, quote, source_ref, risk}

company    : ticker of the company exposed (must be in the group)
category   : taxonomy category id
leaf       : taxonomy leaf id, CATEGORY.leaf
quote      : copied verbatim from the cited source - checked by verify.py
source_ref : the excerpt the quote comes from (chunk id, graph chunk id or window id)
risk       : short human-readable label (free text, shown only)

Approaches differ in how they retrieve and reason, not in what they return.
"""
import config
import taxonomy

CLAIM_PROPERTIES = {
    "risk": {"type": "string", "description": "Short label for the risk, 2-6 words."},
    "company": {"type": "string", "description": "Ticker of the exposed company, exactly as given."},
    "category": {"type": "string", "enum": taxonomy.CATEGORY_IDS},
    "leaf": {"type": "string", "enum": taxonomy.LEAF_IDS},
    "quote": {"type": "string", "description": "15-50 words copied exactly from the cited excerpt."},
    "source_ref": {"type": "string", "description": "Id of the excerpt the quote is copied from."},
}

CLAIMS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "claims"],
    "properties": {
        "summary": {"type": "string", "description": "Two or three sentences answering the question."},
        "claims": {
            "type": "array",
            "items": {"type": "object", "additionalProperties": False,
                      "required": list(CLAIM_PROPERTIES), "properties": CLAIM_PROPERTIES},
        },
    },
}

CLAIM_RULES = (
    "Return claims: one claim per (company, risk) the excerpts support. For each claim give the company's ticker, "
    "the taxonomy category and leaf ids from the list below, a quote of 15-50 words copied EXACTLY, character for "
    "character, from ONE excerpt of THAT company, and the id of that excerpt as source_ref. "
    "A company may appear in a claim only if one of its own excerpts supports it. Do not invent text. "
    "Prefer risks that two or more companies share.\n\nTaxonomy (use only these ids):\n"
)


def system_prompt(intro):
    return f"{intro}\n\n{CLAIM_RULES}{taxonomy.prompt_listing()}"


def shared_leaves(claims, level="leaf", min_shared=None):
    """{label: sorted tickers} for labels claimed for at least `min_shared` companies."""
    min_shared = min_shared or config.MIN_SHARED
    out = {}
    for c in claims:
        out.setdefault(c[level], set()).add(c["company"])
    return {k: sorted(v) for k, v in out.items() if len(v) >= min_shared}


def shared_risks(claims, n_companies):
    """Leaf-level answer table: shared leaves ranked specific-first (generic = >=80% of companies)."""
    rows = []
    for leaf, tickers in shared_leaves(claims).items():
        own = [c for c in claims if c["leaf"] == leaf]
        rows.append({"leaf": leaf, "category": taxonomy.category_of(leaf), "risk": taxonomy.leaf_name(leaf),
                     "tickers": tickers, "claims": len(own),
                     "generic": len(tickers) >= 0.8 * n_companies,
                     "cross_industry": len({config.INDUSTRY.get(t, "other") for t in tickers}) > 1})
    return sorted(rows, key=lambda r: (r["generic"], -len(r["tickers"]), -r["claims"], r["leaf"]))


def matrix(claims, tickers, level="category"):
    """{label: {ticker: number of accepted claims}} - the heatmap values."""
    labels = taxonomy.CATEGORY_IDS if level == "category" else taxonomy.LEAF_IDS
    m = {label: {t: 0 for t in tickers} for label in labels}
    for c in claims:
        if c["company"] in tickers:
            m[c[level]][c["company"]] += 1
    return m


def finalise(result, filings):
    """Apply the shared verifier and build the answer every approach is scored on."""
    from verify import dedupe, verify_claims

    tickers = [f["ticker"] for f in filings]
    accepted, rejected, stats = verify_claims(result["raw_claims"], filings, result.get("sources"))
    accepted = dedupe(accepted)
    shared = shared_risks(accepted, len(tickers))
    if result.get("summary") is None:  # computed answer (taxonomy-first)
        specific = [r for r in shared if not r["generic"]]
        top = ", ".join(f"{r['risk']} ({len(r['tickers'])} of {len(tickers)})" for r in specific[:4])
        result["summary"] = (f"{len(shared)} taxonomy leaves are shared by at least {config.MIN_SHARED} of the "
                             f"{len(tickers)} counterparties; {len(specific)} of them are specific "
                             f"(fewer than 80% of companies). Most widely shared specific risks: {top or 'none'}.")
    result.update(
        claims=accepted, rejected=rejected, verification=stats, shared_risks=shared,
        companies_covered=sorted({t for r in shared for t in r["tickers"]}),
        matrix={"category": matrix(accepted, tickers, "category"), "leaf": matrix(accepted, tickers, "leaf")},
    )
    return result
