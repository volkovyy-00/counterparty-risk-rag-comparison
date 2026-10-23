"""Estimate what a real run will cost BEFORE any model call, and gate runs over a budget.

    python estimate_cost.py                 # print the estimate for the full freeze (see real_run.py)

Input tokens: measured with the provider's token-counting endpoint when a key is
set (Anthropic count_tokens, no model call), otherwise characters / 4 - the
printout says which. Output tokens cannot be measured in advance: the
assumptions per call are printed next to the result. Prices: pricing.yaml.
"""
import argparse

import config
import llm
from corpus import chunk_text, chunks_for, load_corpus

# Assumed output tokens per call (answer + adaptive thinking at LLM_EFFORT=low). Stated, not measured.
ASSUME_OUT = {"taxonomy_window": 2500, "graph_chunk": 900, "claims_answer": 6000}
GRAPH_PROMPT_OVERHEAD = 1500  # SimpleKGPipeline extraction template + schema, tokens


def _tokens(system, user, measure):
    if measure:
        n = llm.count_tokens(system, user)
        if n is not None:
            return n, True
    return (len(system) + len(user)) // 4, False


def estimate(filings, reruns=2, audit_run=True, measure=True):
    import approach0_long_context as a0
    import approach1_rag as a1
    import approach2_graphrag as a2
    import approach3_taxonomy as a3

    measured = []
    rows = []

    def add(stage, calls, tok_in, tok_out, cached_system=0):
        cost = llm.price_usd(config.LLM_MODEL, tok_in - cached_system, tok_out, 0, cached_system)
        rows.append({"stage": stage, "calls": calls, "input_tokens": tok_in, "output_tokens": tok_out,
                     "cost_usd": cost})

    # Approach 3 - one call per window; the system prompt is prompt-cached after the first call.
    sys_tok, m = _tokens(a3.SYSTEM, "", measure)
    measured.append(m)
    windows = [(f, ref, w) for f in filings for ref, w in a3.windows_for(f)]
    win_tok = sum(len(w) // 4 for _, _, w in windows)
    t3_in = win_tok + sys_tok * len(windows)
    add("3 taxonomy build", len(windows), t3_in, ASSUME_OUT["taxonomy_window"] * len(windows),
        cached_system=sys_tok * (len(windows) - 1))

    # Approach 2 - one extraction call per graph chunk, plus one answer call.
    gchunks = sum(len(chunk_text(f["text"], config.GRAPH_CHUNK_CHARS, config.GRAPH_CHUNK_OVERLAP)) for f in filings)
    add("2 graph build", gchunks, gchunks * (config.GRAPH_CHUNK_CHARS // 4 + GRAPH_PROMPT_OVERHEAD),
        gchunks * ASSUME_OUT["graph_chunk"])
    evidence = min(gchunks, 40 * 4)  # SHARED_RISKS_CYPHER: <= 40 risks, evidence chunks deduplicated
    add("2 graph ask", 1, evidence * config.GRAPH_CHUNK_CHARS // 4 + len(a2.SYSTEM) // 4, ASSUME_OUT["claims_answer"])

    # Approach 1 - top-k chunks in one call (embeddings: local model, no cost).
    chunks = chunks_for(filings, config.RAG_CHUNK_CHARS, config.RAG_CHUNK_OVERLAP)
    top = chunks[: config.RAG_TOP_K]
    n1, m = _tokens(a1.SYSTEM, a1.user_prompt(config.QUESTION, top), measure)
    measured.append(m)
    add("1 RAG ask", 1, n1, ASSUME_OUT["claims_answer"])

    # Control - everything in one call.
    nL, m = _tokens(a0.SYSTEM, a0.user_prompt(config.QUESTION, filings), measure)
    measured.append(m)
    add("L long-context ask", 1, nL, ASSUME_OUT["claims_answer"])

    one_run = sum(r["cost_usd"] or 0 for r in rows)
    rerun_cost = reruns * sum(r["cost_usd"] or 0 for r in rows if not r["stage"].startswith("L"))
    audit_cost = rows[0]["cost_usd"] if audit_run else 0
    return {"rows": rows, "one_run_usd": one_run, "reruns_usd": rerun_cost, "audit_run_usd": audit_cost,
            "total_usd": one_run + rerun_cost + audit_cost, "item1a_tokens": nL,
            "input_measured": all(measured), "model": config.LLM_MODEL}


def report(est, reruns):
    how = "measured with count_tokens" if est["input_measured"] else "ESTIMATED as characters / 4 (no key)"
    lines = [f"Cost estimate - model {est['model']}, prices from pricing.yaml (checked {llm.PRICES_CHECKED})",
             f"Input tokens: {how}. Output tokens: ASSUMED per call {ASSUME_OUT}.", "",
             f"{'stage':<22}{'calls':>7}{'input tok':>12}{'output tok':>12}{'USD':>9}"]
    for r in est["rows"]:
        cost = "n/a" if r["cost_usd"] is None else f"{r['cost_usd']:.2f}"
        lines.append(f"{r['stage']:<22}{r['calls']:>7}{r['input_tokens']:>12,}{r['output_tokens']:>12,}{cost:>9}")
    lines += ["", f"One full run (1, 2, 3, L):           ${est['one_run_usd']:.2f}",
              f"{reruns} reruns of 1, 2, 3 (cache off):     ${est['reruns_usd']:.2f}",
              f"Audit run B (approach 3, prompt v2.1): ${est['audit_run_usd']:.2f}",
              f"TOTAL for the frozen demo:            ${est['total_usd']:.2f}",
              f"Long-context prompt: {est['item1a_tokens']:,} tokens (all Item 1A + instructions)"]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reruns", type=int, default=2)
    parser.add_argument("--no-measure", action="store_true", help="skip count_tokens even if a key is set")
    args = parser.parse_args()
    measure = not args.no_measure and bool(config.env("ANTHROPIC_API_KEY")) and config.LLM_PROVIDER == "anthropic"
    print(report(estimate(load_corpus(), args.reruns, measure=measure), args.reruns))


if __name__ == "__main__":
    main()
