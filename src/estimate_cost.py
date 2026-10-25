"""Estimate what a real run will cost BEFORE any model call, and gate runs over a budget.

    python src/estimate_cost.py                 # print the estimate for the full freeze (see real_run.py)

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
ASSUME_OUT = {"taxonomy_window": 2500, "graph_chunk": 900, "graph_v2_chunk": 1800, "claims_answer": 6000}
GRAPH_PROMPT_OVERHEAD = 1500  # SimpleKGPipeline extraction template + schema, tokens
# graph-v2 resolution and ask: stated assumptions until an A/B run measures them.
ASSUME_V2 = {"mentions_per_chunk": 6, "components_per_mention": 0.15, "resolve_in": 1500, "resolve_out": 600,
             "ask_evidence_tokens": 30 * 3 * 300 + 10 * 3 * 60,
             "qa_evidence_tokens": 8000}  # graph QA: about 7,000 measured on the 3-filing A/B graph


def _tokens(system, user, measure, model=None):
    if measure:
        n = llm.count_tokens(system, user, model)
        if n is not None:
            return n, True
    return (len(system) + len(user)) // 4, False


def estimate(filings, reruns=2, audit_run=True, measure=True):
    import approach0_long_context as a0
    import approach1_rag as a1
    import approach3_taxonomy as a3

    measured = []
    rows = []

    def add(stage, calls, tok_in, tok_out, cached_system=0):
        cost = llm.price_usd(config.LLM_MODEL, tok_in - cached_system, tok_out, 0, cached_system)
        rows.append({"stage": stage, "calls": calls, "input_tokens": tok_in, "output_tokens": tok_out,
                     "cost_usd": cost})

    # Approach 3 - one call per window; the system prompt is prompt-cached after the first call.
    t3 = taxonomy_rows(filings, a3.PROMPT_VERSION, a3.SPLIT, measure)
    measured.append(t3["measured"])
    rows.append(t3["row"])

    # Approach 2 - the prompt version that will run (both versions are compared in graph_compare below).
    graph = graph_rows(filings, config.GRAPH_PROMPT_VERSION, measure)
    measured.append(graph["measured"])
    rows += graph["rows"]

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

    # Approach 2, screen 4 - one answer per fixed graph question (no Neo4j here: evidence size assumed).
    if config.GRAPH_PROMPT_VERSION == "graph-v2":
        import graph_qa

        qa_sys, m = _tokens(graph_qa.SYSTEM, "", measure, config.GRAPH_QA_MODEL)
        measured.append(m)
        n_qa = len(graph_qa.QUESTIONS)
        rows.append(_row("2 graph QA", n_qa, n_qa * (qa_sys + ASSUME_V2["qa_evidence_tokens"]),
                         n_qa * graph_qa.ASSUME_OUT, model=config.GRAPH_QA_MODEL))

    rows.sort(key=lambda r: {"3": 0, "2": 1, "1": 2, "L": 3}[r["stage"][0]])
    one_run = sum(r["cost_usd"] or 0 for r in rows)
    rerun_cost = reruns * sum(r["cost_usd"] or 0 for r in rows
                              if not r["stage"].startswith("L") and r["stage"] != "2 graph QA")
    audit_cost = rows[0]["cost_usd"] if audit_run else 0  # rows[0] is the taxonomy build
    taxo_compare = {(v, s): taxonomy_rows(filings, v, s, measure) for v, s in TAXO_COMPARE}
    return {"rows": rows, "one_run_usd": one_run, "reruns_usd": rerun_cost, "audit_run_usd": audit_cost,
            "taxonomy_compare": taxo_compare,
            "total_usd": one_run + rerun_cost + audit_cost, "item1a_tokens": nL,
            "input_measured": all(measured), "model": config.LLM_MODEL,
            "graph_compare": {v: graph_rows(filings, v, measure) for v in ("graph-v1-workshop", "graph-v2")},
            "graph_ab": graph_ab(filings, measure)}


def _row(stage, calls, tok_in, tok_out, cache_write=0, cache_read=0, model=None):
    cost = llm.price_usd(model or config.LLM_MODEL, tok_in, tok_out, cache_write, cache_read)
    return {"stage": stage, "calls": calls, "input_tokens": tok_in + cache_write + cache_read,
            "output_tokens": tok_out, "cost_usd": cost}


def graph_rows(filings, version, measure=True):
    """Approach 2 rows (build, resolve, ask) for one prompt version."""
    import approach2_graphrag as a2

    if version == "graph-v1-workshop":
        gchunks = sum(len(chunk_text(f["text"], config.GRAPH_CHUNK_CHARS, config.GRAPH_CHUNK_OVERLAP)) for f in filings)
        evidence = min(gchunks, 40 * 4)  # SHARED_RISKS_CYPHER: <= 40 risks, evidence chunks deduplicated
        rows = [_row("2 graph build", gchunks, gchunks * (config.GRAPH_CHUNK_CHARS // 4 + GRAPH_PROMPT_OVERHEAD),
                     gchunks * ASSUME_OUT["graph_chunk"]),
                _row("2 graph ask", 1, evidence * config.GRAPH_CHUNK_CHARS // 4 + len(a2.SYSTEM) // 4,
                     ASSUME_OUT["claims_answer"])]
        return {"version": version, "rows": rows, "measured": False,
                "usd": sum(r["cost_usd"] or 0 for r in rows)}
    import graph_v2

    sys_tok, m = _tokens(graph_v2.SYSTEM_V2, "", measure)
    pairs = [(f, c) for f in filings for c in graph_v2.graph_chunks(f)]
    n = len(pairs)
    user_tok = sum(len(graph_v2.user_prompt(f, c)) // 4 for f, c in pairs)
    writes = min(n, config.LLM_CONCURRENCY)  # parallel first calls may each write the prompt cache
    mentions = n * ASSUME_V2["mentions_per_chunk"]
    comps = round(mentions * ASSUME_V2["components_per_mention"])
    rows = [_row("2 graph build", n, user_tok, n * ASSUME_OUT["graph_v2_chunk"], sys_tok * writes,
                 sys_tok * (n - writes)),
            _row("2 graph resolve", comps, comps * ASSUME_V2["resolve_in"], comps * ASSUME_V2["resolve_out"]),
            _row("2 graph ask", 1, ASSUME_V2["ask_evidence_tokens"] + len(a2.SYSTEM) // 4,
                 ASSUME_OUT["claims_answer"])]
    return {"version": version, "rows": rows, "measured": m, "chunks": n, "system_tokens": sys_tok,
            "usd": sum(r["cost_usd"] or 0 for r in rows)}


TAXO_COMPARE = [("taxonomy-v2.0", "fixed"), ("taxonomy-v3.0", "heading")]


def taxonomy_rows(filings, version, split, measure=True):
    """Approach-3 build for one prompt version and split: one call per window, system prompt cached."""
    import approach3_taxonomy as a3

    sys_tok, m = _tokens(a3.system(version), "", measure)
    windows = [w for f in filings for _, w, _ in a3.split_filing(f, split)[0]]
    win_tok = sum(len(w) // 4 for w in windows)
    n = len(windows)
    cost = llm.price_usd(config.LLM_MODEL, win_tok + sys_tok, ASSUME_OUT["taxonomy_window"] * n, 0,
                         sys_tok * (n - 1))
    return {"row": {"stage": "3 taxonomy build", "calls": n, "input_tokens": win_tok + sys_tok * n,
                    "output_tokens": ASSUME_OUT["taxonomy_window"] * n, "cost_usd": cost},
            "windows": n, "system_tokens": sys_tok, "measured": m, "usd": cost}


def taxonomy_ab(filings, tickers, measure=True):
    """The approach-3 A/B: v2.0 on fixed windows vs v3.0 on heading windows, for `tickers` only."""
    ab = [f for f in filings if f["ticker"] in tickers]
    out = {f"{v} {s}": round(taxonomy_rows(ab, v, s, measure)["usd"] or 0, 4) for v, s in TAXO_COMPARE}
    return dict(out, total_usd=round(sum(out.values()), 4), tickers=[f["ticker"] for f in ab])


def graph_ab(filings, measure=True):
    """The A/B on GRAPH_AB_TICKERS: build + resolve for both versions (no ask - the A/B compares graphs)."""
    ab = [f for f in filings if f["ticker"] in config.GRAPH_AB_TICKERS]
    out = {}
    for v in ("graph-v1-workshop", "graph-v2"):
        g = graph_rows(ab, v, measure)
        out[v] = round(sum(r["cost_usd"] or 0 for r in g["rows"] if r["stage"] != "2 graph ask"), 4)
    out["total_usd"] = round(sum(out.values()), 4)
    out["tickers"] = [f["ticker"] for f in ab]
    out["chars"] = sum(len(f["text"]) for f in ab)
    return out


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
              f"Audit run B (approach 3, prompt v3.1): ${est['audit_run_usd']:.2f}",
              f"TOTAL for the frozen demo:            ${est['total_usd']:.2f}",
              f"Long-context prompt: {est['item1a_tokens']:,} tokens (all Item 1A + instructions)"]
    (va, a), (vb, b) = est["taxonomy_compare"].items()
    lines += ["", f"Approach 3 split: {va[0]} {va[1]} {a['windows']} windows ${a['usd']:.2f} -> "
              f"{vb[0]} {vb[1]} {b['windows']} windows ${b['usd']:.2f} "
              f"(system prompt {a['system_tokens']:,} -> {b['system_tokens']:,} tokens, cached)"]
    gc = est["graph_compare"]
    lines += ["", f"Approach 2, both prompt versions (full corpus; v2 assumptions: {ASSUME_V2}):",
              f"{'stage':<22}{'v1 workshop USD':>17}{'v2 USD':>10}"]
    stages = ["2 graph build", "2 graph resolve", "2 graph ask"]
    for s in stages:
        v = {k: next((r["cost_usd"] for r in g["rows"] if r["stage"] == s), None) for k, g in gc.items()}
        fmt = lambda x: "-" if x is None else f"{x:.2f}"  # noqa: E731
        lines.append(f"{s:<22}{fmt(v['graph-v1-workshop']):>17}{fmt(v['graph-v2']):>10}")
    lines.append(f"{'total':<22}{gc['graph-v1-workshop']['usd']:>17.2f}{gc['graph-v2']['usd']:>10.2f}")
    ab = est["graph_ab"]
    lines += ["", f"Graph A/B on {', '.join(ab['tickers'])} ({ab['chars']:,} chars, build + resolve only): "
              f"A (v1) ${ab['graph-v1-workshop']:.2f} + B (v2) ${ab['graph-v2']:.2f} = ${ab['total_usd']:.2f}"]
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
