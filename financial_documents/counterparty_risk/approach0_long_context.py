"""Control row - long context: all Item 1A sections in ONE call, same claims contract.

No retrieval, no graph, no taxonomy pass: the model reads everything at once.
It runs only if the measured prompt fits the model's context window; otherwise
the scorecard shows "n/a - N tokens". Nothing is truncated to make it fit.
"""
import llm
from answer import CLAIMS_SCHEMA, system_prompt

SYSTEM = system_prompt(
    "You are a credit risk analyst. You are given the complete Risk Factors section (Item 1A) of each "
    "company's latest 10-K, each labelled [TICKER]. Use the ticker as source_ref."
)


class DoesNotFit(RuntimeError):
    pass


def user_prompt(question, filings):
    docs = "\n\n".join(f"[{f['ticker']}] {f['ticker']} ({f['company']}) 10-K {f['accession']} Item 1A\n{f['text']}" for f in filings)
    return f"Question: {question}\n\n{docs}"


def run(question, filings):
    user = user_prompt(question, filings)
    tokens, limit = llm.count_tokens(SYSTEM, user), llm.context_window()
    if tokens is None or limit is None:
        raise DoesNotFit("n/a - token count not measurable for this provider")
    if tokens + 32000 > limit:  # leave room for the answer
        raise DoesNotFit(f"n/a - {tokens:,} tokens (limit {limit:,})")
    with llm.METER.track("long.ask"):
        reply = llm.chat(SYSTEM, user, schema=CLAIMS_SCHEMA, schema_name="claims")
    return {
        "approach": "0_long_context",
        "summary": reply["summary"],
        "raw_claims": reply["claims"],
        "sources": {f["ticker"]: f["text"] for f in filings},
        "stages": {"build": "long.build", "ask": "long.ask"},
        "details": {"prompt_tokens": tokens, "context_window": limit},
    }
