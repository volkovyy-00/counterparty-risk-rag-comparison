"""Approach 3 - taxonomy-first extraction.

The LLM does one narrow job: label each risk factor in a window of Item 1A with a
fixed taxonomy category and leaf, plus a verbatim quote. Everything after that -
label validation, quote checking, the company x category matrix, the ranking and
the answer text - is plain Python (verify.py, answer.py), so it is repeatable
and auditable.
"""
from concurrent.futures import ThreadPoolExecutor

import config
import llm
import taxonomy
from corpus import chunk_text

# Prompt versions are kept side by side so two recorded runs can be diffed (governance screen).
PROMPT_VERSION = config.env("TAXO_PROMPT_VERSION", "taxonomy-v2.0")
_EXTRA = {
    "taxonomy-v2.0": "",
    "taxonomy-v2.1": ("\nPrefer the most specific leaf that the quote supports. Use OTHER only when no other "
                      "category fits, and do not label a risk factor with a category it mentions only in passing."),
}
if PROMPT_VERSION not in _EXTRA:
    raise SystemExit(f"TAXO_PROMPT_VERSION={PROMPT_VERSION!r}: use one of {', '.join(_EXTRA)}")

_BASE = (
    "You are a credit risk analyst classifying the Risk Factors section (Item 1A) of a 10-K filing.\n"
    "For EVERY distinct risk factor in the excerpt (usually introduced by a heading sentence), return:\n"
    "- heading: the risk factor's heading or a 5-12 word paraphrase of it\n"
    "- category: the single best taxonomy category id\n"
    "- leaf: the single best leaf id within that category\n"
    "- quote: 15-50 words copied EXACTLY, character for character, from the excerpt, that justify the leaf\n"
    "A risk factor that clearly covers two leaves may be returned twice, once per leaf, each with its own quote.\n"
    "Do not merge different risk factors. Do not invent text. If the excerpt contains no risk factor, "
    "return an empty list."
)


def system():
    return _BASE + _EXTRA[PROMPT_VERSION] + "\n\nTaxonomy (use only these ids):\n" + taxonomy.prompt_listing()


SYSTEM = system()

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
                "required": ["heading", "category", "leaf", "quote"],
                "properties": {
                    "heading": {"type": "string"},
                    "category": {"type": "string", "enum": taxonomy.CATEGORY_IDS},
                    "leaf": {"type": "string", "enum": taxonomy.LEAF_IDS},
                    "quote": {"type": "string"},
                },
            },
        }
    },
}


def windows_for(filing):
    return [(f"{filing['ticker']}:w{n + 1}", w) for n, (_, w) in
            enumerate(chunk_text(filing["text"], config.TAXO_WINDOW_CHARS, 0))]


def _classify_window(filing, ref, window):
    user = (f"Company: {filing['company']} ({filing['ticker']}), 10-K accession {filing['accession']}.\n"
            f"Excerpt {ref}:\n\n{window}")
    with llm.METER.as_stage("taxonomy.build"):
        reply = llm.chat(SYSTEM, user, schema=SCHEMA, schema_name="risk_factors")
    return [{"company": filing["ticker"], "category": rf.get("category", ""), "leaf": rf.get("leaf", ""),
             "quote": rf.get("quote", ""), "source_ref": ref, "risk": rf.get("heading", "")}
            for rf in reply.get("risk_factors", [])]


def run(question, filings):
    jobs = [(f, ref, w) for f in filings for ref, w in windows_for(f)]
    claims = []
    with llm.METER.track("taxonomy.build"), ThreadPoolExecutor(config.LLM_CONCURRENCY) as pool:
        for out in pool.map(lambda job: _classify_window(*job), jobs):
            claims += out
    with llm.METER.track("taxonomy.ask"):  # no LLM call: the answer is computed from the verified claims
        pass
    return {
        "approach": "3_taxonomy_first",
        "summary": None,  # written by code from the verified claims (answer.finalise)
        "raw_claims": claims,
        "sources": {ref: w for _, ref, w in jobs},
        "stages": {"build": "taxonomy.build", "ask": "taxonomy.ask"},
        "details": {"windows_classified": len(jobs), "prompt_version": PROMPT_VERSION},
    }
