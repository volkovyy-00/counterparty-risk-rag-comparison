"""Run all three approaches on the same question and write a side-by-side comparison.

    python run_all.py                 # all three
    python run_all.py --approaches 1,3
    python run_all.py --show          # just print the last saved comparison (no network, no Neo4j)

Writes results/latest/ (and a timestamped copy in results/runs/).
"""
import argparse
import json
import shutil
import traceback
from datetime import datetime

import config
import llm
from corpus import load_corpus
from evaluate import evaluate, load_ground_truth

APPROACHES = {"1": ("1_plain_rag", "1 Plain RAG"), "2": ("2_graphrag", "2 GraphRAG"),
              "3": ("3_taxonomy_first", "3 Taxonomy-first")}
LATEST = config.RESULTS_DIR / "latest"


def _module(key):
    import approach1_rag, approach2_graphrag, approach3_taxonomy  # noqa: E401 (lazy: Neo4j is optional)

    return {"1": approach1_rag, "2": approach2_graphrag, "3": approach3_taxonomy}[key]


def usage_for(result):
    build = llm.METER.summary(result["stages"]["build"])
    if result["approach"] == "2_graphrag" and not build:
        saved = config.RESULTS_DIR / f"graph_build_{config.CORPUS}.json"
        if saved.exists():
            build = json.loads(saved.read_text())["usage"]
            build["from_saved_build"] = True
    return {"build": build, "ask": llm.METER.summary(result["stages"]["ask"])}


def fmt_usage(u):
    if not u:
        return "-"
    tokens = int(u.get("input_tokens", 0) + u.get("output_tokens", 0))
    calls, texts = int(u.get("llm_calls", 0)), int(u.get("embed_calls", 0))
    cost = "n/a" if u.get("unpriced_calls") else f"${u.get('cost_usd', 0):.4f}"
    cached = int(u.get("cached_calls", 0))
    parts = [f"{calls} LLM calls"] + ([f"{texts} texts embedded"] if texts else [])
    if cached:
        parts.append(f"{cached}/{calls + texts} from cache")
    if u.get("from_saved_build"):
        parts.append("from saved build")
    return f"{tokens:,} tok / {cost} / {u.get('wall_clock_s', 0):.1f}s ({', '.join(parts)})"


def write_comparison(results, filings, dq_summary, gt):
    order = [r for r in results if "error" not in r]
    cols = [APPROACHES[r["key"]][1] for r in results]
    periods = sorted(f["report_date"] for f in filings if f.get("report_date"))
    lines = [f"# {config.QUESTION}", "",
             f"**Corpus** `{config.CORPUS}`: {len(filings)} filings"
             + (f", fiscal periods {periods[0]} to {periods[-1]}" if periods else "")
             + f" | **Model** {config.LLM_PROVIDER}/{config.LLM_MODEL} | **Cache** {config.LLM_CACHE}"
             + f" | {datetime.now():%Y-%m-%d %H:%M}", "",
             f"**Data quality:** {dq_summary}", "",
             "| | " + " | ".join(cols) + " |", "|---" * (len(cols) + 1) + "|"]

    def row(label, fn):
        cells = []
        for r in results:
            try:
                cells.append("error" if "error" in r else fn(r))
            except Exception:
                cells.append("-")
        lines.append(f"| {label} | " + " | ".join(cells) + " |")

    row("Shared risks returned", lambda r: str(len(r["shared_risks"])))
    row("Companies covered", lambda r: f"{len({t for s in r['shared_risks'] for t in s['tickers']})} of {len(filings)}")
    row("Claims backed by that company's text",
        lambda r: f"{r['citation_check']['supported_claims']}/{r['citation_check']['claims']}")
    row("Quotes rejected (not verbatim)", lambda r: (f"{r['citation_check']['quotes_rejected']}/"
                                                     f"{r['citation_check']['quotes_checked']}"
                                                     if "quotes_checked" in r["citation_check"] else "not checked"))
    if gt:
        row(f"Eval P / R / F1 (truth: {gt['status']})",
            lambda r: f"{r['eval']['precision']:.2f} / {r['eval']['recall']:.2f} / {r['eval']['f1']:.2f}")
        row("Shared categories found", lambda r: f"{r['eval']['shared_categories_found']} of "
                                                 f"{r['eval']['shared_categories_true']}")
    row("Build: tokens / cost / time", lambda r: fmt_usage(r["usage"]["build"]))
    row("Ask: tokens / cost / time", lambda r: fmt_usage(r["usage"]["ask"]))

    for r in results:
        lines += ["", f"## {APPROACHES[r['key']][1]}", ""]
        if "error" in r:
            lines.append(f"Did not run: `{r['error']}`")
            continue
        lines += [r["summary"], "", "| Risk | Companies | Citations |", "|---|---|---|"]
        for s in r["shared_risks"][:8]:
            cites = ", ".join(s["citations"][:4]) + (" ..." if len(s["citations"]) > 4 else "")
            lines.append(f"| {s['risk']} | {', '.join(s['tickers'])} | {cites} |")
        if len(r["shared_risks"]) > 8:
            lines.append(f"| ... {len(r['shared_risks']) - 8} more in {r['approach']}.json | | |")
        if "matrix" in r.get("tables", {}):
            m = r["tables"]["matrix"]
            cats = [s["category"] for s in r["shared_risks"]]
            lines += ["", "Risk factors per category (rows) and company (columns):", "",
                      "| | " + " | ".join(m.index) + " |", "|---" * (len(m.index) + 1) + "|"]
            for c in cats:
                lines.append(f"| {c} | " + " | ".join(str(v) if v else "." for v in m[c]) + " |")
        if r.get("eval", {}).get("missed_categories"):
            lines.append(f"\nMissed vs ground truth: {', '.join(r['eval']['missed_categories'])}")

    lines += ["", "---", "Claims backed = (risk, company) pairs where a cited excerpt comes from that company's "
              "own Item 1A. Eval maps free-text risk names (approaches 1-2) onto the taxonomy by keyword; "
              "see evaluate.py. Cost uses pricing.yaml - check current provider prices before quoting."]
    if any(r.get("usage", {}).get("ask", {}).get("cached_calls") for r in order):
        lines.append("Some calls were replayed from cache: their time is not live latency; tokens and cost are "
                     "those recorded on the original call.")
    return "\n".join(lines) + "\n"


def jsonable(result):
    out = {k: v for k, v in result.items() if k != "tables"}
    return json.loads(json.dumps(out, default=lambda o: o.item() if hasattr(o, "item") else str(o)))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--approaches", default="1,2,3")
    parser.add_argument("--show", action="store_true", help="print results/latest/comparison.md and exit")
    args = parser.parse_args()
    if args.show:
        print((LATEST / "comparison.md").read_text())
        return

    filings = load_corpus()
    tickers = [f["ticker"] for f in filings]
    dq_file = config.CORPUS_DIR / "data_quality.jsonl"
    dq = [json.loads(line) for line in dq_file.read_text().splitlines()] if dq_file.exists() else []
    dq_summary = (f"{sum(i['severity'] == 'ERROR' for i in dq)} errors, {sum(i['severity'] == 'WARN' for i in dq)} "
                  f"warnings - see results/data_quality_{config.CORPUS}.md" if dq_file.exists() else "not checked")
    gt = load_ground_truth()
    print(f"Question: {config.QUESTION}\nCorpus: {config.CORPUS} ({', '.join(tickers)})\nData quality: {dq_summary}\n")

    results = []
    for key in [k.strip() for k in args.approaches.split(",")]:
        name, label = APPROACHES[key]
        print(f"== {label}")
        try:
            result = _module(key).run(config.QUESTION, filings)
        except (Exception, SystemExit) as exc:  # keep the demo going if one approach can't run
            traceback.print_exc() if isinstance(exc, Exception) else None
            print(f"   skipped: {exc}")
            results.append({"key": key, "approach": name, "error": str(exc)})
            continue
        result["key"] = key
        result["usage"] = usage_for(result)
        if gt:
            result["eval"] = evaluate(result, gt, tickers)
        results.append(result)
        print(f"   {len(result['shared_risks'])} shared risks; ask {fmt_usage(result['usage']['ask'])}")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = config.RESULTS_DIR / "runs" / f"{stamp}_{config.CORPUS}"
    run_dir.mkdir(parents=True, exist_ok=True)
    for r in results:
        (run_dir / f"{r['approach']}.json").write_text(json.dumps(jsonable(r), indent=2))
        for table_name, df in r.get("tables", {}).items():
            df.to_csv(run_dir / f"{r['approach']}_{table_name}.csv", index=table_name == "matrix")
    comparison = write_comparison(results, filings, dq_summary, gt)
    (run_dir / "comparison.md").write_text(comparison)
    (run_dir / "run_config.json").write_text(json.dumps({
        "question": config.QUESTION, "corpus": config.CORPUS, "tickers": tickers, "provider": config.LLM_PROVIDER,
        "model": config.LLM_MODEL, "embed_model": config.EMBED_MODEL, "cache": config.LLM_CACHE,
        "rag_top_k": config.RAG_TOP_K, "graph_mode": config.GRAPH_MODE, "graph_resolver": config.GRAPH_RESOLVER,
        "min_shared": config.MIN_SHARED}, indent=2))
    if LATEST.exists():
        shutil.rmtree(LATEST)
    shutil.copytree(run_dir, LATEST)
    print("\n" + comparison)
    print(f"-> {config.rel(LATEST)}/ (copy in {config.rel(run_dir)}/)")


if __name__ == "__main__":
    main()
