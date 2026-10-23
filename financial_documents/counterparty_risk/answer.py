"""The answer format shared by all three approaches, plus shared checks."""
import re

import yaml

import config

TAXONOMY = yaml.safe_load((config.ROOT / "taxonomy.yaml").read_text())["categories"]
CATEGORY_IDS = [c["id"] for c in TAXONOMY]
CATEGORY_NAMES = {c["id"]: c["name"] for c in TAXONOMY}

# Strict JSON schema for the free-text approaches (1 and 2).
SHARED_RISKS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "shared_risks"],
    "properties": {
        "summary": {"type": "string", "description": "Two or three sentences answering the question."},
        "shared_risks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["risk", "tickers", "citations"],
                "properties": {
                    "risk": {"type": "string", "description": "Short name of the shared risk."},
                    "tickers": {"type": "array", "items": {"type": "string"}},
                    "citations": {"type": "array", "items": {"type": "string"},
                                  "description": "Chunk ids, exactly as given in the context."},
                },
            },
        },
    },
}


def check_citations(shared_risks, chunks_by_id, tickers):
    """Each (risk, ticker) claim counts as supported if a cited chunk comes from that ticker's filing."""
    claims = supported = 0
    unknown_tickers, unknown_chunks = set(), set()
    for risk in shared_risks:
        cited = [chunks_by_id[c] for c in risk["citations"] if c in chunks_by_id]
        unknown_chunks |= {c for c in risk["citations"] if c not in chunks_by_id}
        cited_tickers = {c["ticker"] for c in cited}
        for t in risk["tickers"]:
            if t not in tickers:
                unknown_tickers.add(t)
            claims += 1
            supported += t in cited_tickers
    return {"claims": claims, "supported_claims": supported,
            "support_rate": round(supported / claims, 3) if claims else None,
            "unknown_tickers": sorted(unknown_tickers), "unknown_citations": sorted(unknown_chunks)}


def shared_only(shared_risks):
    return [r for r in shared_risks if len(set(r["tickers"])) >= config.MIN_SHARED]


def _keyword_pattern(keyword):
    stem = keyword.rstrip("*")
    tail = "" if keyword.endswith("*") else r"\b"
    return re.compile(rf"\b{re.escape(stem)}{tail}", re.I)


_KEYWORDS = {c["id"]: [_keyword_pattern(k) for k in c.get("keywords", [])] for c in TAXONOMY}


def categories_for(text):
    """Deterministic keyword mapping of a free-text risk name onto taxonomy ids (eval only)."""
    return [cid for cid, patterns in _KEYWORDS.items() if any(p.search(text) for p in patterns)]
