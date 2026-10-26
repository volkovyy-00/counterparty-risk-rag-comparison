"""Console asks: the narrower plain-RAG questions shown after the main one, recorded so the stage never waits.

    python src/console_asks.py                    # retrieval for every ask (local embeddings, free) + the estimate, STOPS
    python src/console_asks.py --confirm-usd 1    # also records the answers -> results/console/rag_asks.json

Each ask runs the approach-1 pipeline unchanged (same chunks, top-k, prompt, schema and verifier) on a different
question. The main question is not here: its answer is the frozen one in results/demo_run/. Without --confirm-usd
nothing is spent and the file holds the real retrieval with no answer (the console says so).
"""
import argparse
import datetime
import json

import config
import llm

OUT = config.RESULTS_DIR / "console" / "rag_asks.json"
ASSUME_OUT = 1500  # output tokens per answer, assumed (stated, not measured)

# Narrow on purpose: each names one or two companies, so top-k lands on their filings and few others.
RAG_ASKS = [
    {"id": "tsla_cells", "label": "Tesla's battery cells",
     "question": "What does Tesla disclose about its dependence on battery cell suppliers?"},
    {"id": "gm_f_ev", "label": "GM and Ford: the EV shift",
     "question": "How are GM and Ford exposed to the transition to electric vehicles?"},
]


def chunk_spans(filings):
    """chunk_id -> (start, end) in the company's Item 1A, for every approach-1 chunk (no embedding needed)."""
    from corpus import chunks_for

    return {c["chunk_id"]: (c["start"], c["start"] + len(c["text"]))
            for c in chunks_for(filings, config.RAG_CHUNK_CHARS, config.RAG_CHUNK_OVERLAP)}


def retrieval(question, chunks, vectors):
    import approach1_rag

    got = approach1_rag.retrieve(question, chunks, vectors)
    return got, [{"chunk_id": c["chunk_id"], "ticker": c["ticker"], "score": c["score"], "start": c["start"],
                  "end": c["start"] + len(c["text"])} for c in got]


def estimate(prompts, measure):
    from estimate_cost import _row, _tokens
    import approach1_rag

    tok_in, measured = 0, True
    for user in prompts:
        n, m = _tokens(approach1_rag.SYSTEM, user, measure)
        tok_in, measured = tok_in + n, measured and m
    return dict(_row("console asks", len(prompts), tok_in, len(prompts) * ASSUME_OUT), measured=measured)


def main():
    import approach1_rag
    from answer import finalise
    from corpus import load_corpus

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--confirm-usd", type=float, default=0.0)
    args = parser.parse_args()
    filings = load_corpus()
    chunks, vectors = approach1_rag.build(filings)
    old = {a["id"]: a for a in json.loads(OUT.read_text())["asks"]} if OUT.exists() else {}
    asks, todo = [], []
    for a in RAG_ASKS:
        got, retrieved = retrieval(a["question"], chunks, vectors)
        keep = old.get(a["id"]) if old.get(a["id"], {}).get("question") == a["question"] else None
        rec = dict(a, retrieved=retrieved, chunks_indexed=len(chunks), top_k=len(retrieved),
                   result=(keep or {}).get("result"), recorded_at=(keep or {}).get("recorded_at"))
        asks.append(rec)
        print(f"  {a['id']}: retrieved {', '.join(sorted({c['ticker'] for c in got}))}"
              + (" (answer already recorded)" if rec["result"] else ""))
        if not rec["result"]:
            todo.append((rec, got))
    measure = bool(config.env("ANTHROPIC_API_KEY")) and config.LLM_PROVIDER == "anthropic"
    est = estimate([approach1_rag.user_prompt(r["question"], got) for r, got in todo], measure)
    how = "measured" if est["measured"] else "estimated as characters / 4"
    print(f"Console asks estimate ({config.LLM_MODEL}): {est['calls']} calls, {est['input_tokens']:,} input tokens ({how}), "
          f"{est['output_tokens']:,} output tokens (assumed) = ${est['cost_usd'] or 0:.2f}")
    if todo and (est["cost_usd"] or 0) <= args.confirm_usd:
        for rec, got in todo:
            reply, retrieved, record = approach1_rag.ask(rec["question"], chunks, vectors)
            result = finalise({"approach": "1_plain_rag", "summary": reply["summary"], "raw_claims": reply["claims"],
                               "sources": {c["chunk_id"]: c["text"] for c in retrieved}, "details": {}}, filings)
            result.pop("sources", None)
            rec.update(result=result, recorded_at=record.get("recorded_at"), model=record.get("served_model"))
            v = result["verification"]
            print(f"  {rec['id']}: {v['accepted']}/{v['claims']} claims verified")
    elif todo:
        print(f"Answers not recorded. Re-run with --confirm-usd N (N >= {est['cost_usd'] or 0:.2f}).")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"asks": asks, "embed_model": config.EMBED_MODEL, "top_k": config.RAG_TOP_K,
                               "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                               "usage": llm.METER.summary("rag.ask")}, indent=1))
    print(f"{len(asks)} asks -> {config.rel(OUT)}")


if __name__ == "__main__":
    main()
