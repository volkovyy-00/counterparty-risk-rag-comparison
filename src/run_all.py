"""Run the approaches on the same question, verify every claim with the same code, score them.

    python src/run_all.py                          # approaches 1,2,3 + long-context control (L)
    python src/run_all.py --approaches 1,3         # without Neo4j
    python src/run_all.py --freeze                 # also copy the run to results/demo_run/ (what the demo shows)
    python src/run_all.py --show                   # print the last comparison (no network, no Neo4j)

Writes results/runs/<stamp>_<corpus>/ and results/latest/.
"""
import argparse
import json
import shutil
import traceback
from datetime import datetime

import config
import llm
import manifest
from answer import finalise
from corpus import load_corpus
from evaluate import evaluate, load_ground_truth, rerun_consistency

APPROACHES = {"L": ("0_long_context", "Control: long context"), "1": ("1_plain_rag", "Approach 1 - plain RAG"),
              "2": ("2_graphrag", "Approach 2 - GraphRAG"), "3": ("3_taxonomy_first", "Approach 3 - taxonomy-first")}
LATEST = config.RESULTS_DIR / "latest"
DEMO_RUN = config.RESULTS_DIR / "demo_run"
KEEP_ON_FREEZE = ("reruns", "audit", "graph.json", "governance.json")  # produced by other steps


def _module(key):
    import approach0_long_context, approach1_rag, approach2_graphrag, approach3_taxonomy  # noqa: E401 (lazy)

    return {"L": approach0_long_context, "1": approach1_rag, "2": approach2_graphrag, "3": approach3_taxonomy}[key]


def usage_for(result):
    """Build and ask usage. Latency is the live wall clock, or None if any call came from cache."""
    out = {}
    for part in ("build", "ask"):
        u = llm.METER.summary(result["stages"][part])
        if result["approach"] == "2_graphrag" and part == "build" and not u.get("llm_calls"):
            saved = config.RESULTS_DIR / f"graph_build_{config.CORPUS}.json"
            if saved.exists():
                u = dict(json.loads(saved.read_text())["usage"], from_saved_build=True)
        live = not u.get("cached_calls")
        out[part] = {"input_tokens": int(u.get("input_tokens", 0)), "output_tokens": int(u.get("output_tokens", 0)),
                     "cost_usd": None if u.get("unpriced_calls") else round(u.get("cost_usd", 0.0), 4),
                     "llm_calls": int(u.get("llm_calls", 0)), "embed_calls": int(u.get("embed_calls", 0)),
                     "cached_calls": int(u.get("cached_calls", 0)),
                     "latency_s": round(u.get("wall_clock_s", 0.0), 2) if live else None,
                     "recorded_latency_s": round(u.get("recorded_latency_s", 0.0), 2),
                     "from_saved_build": bool(u.get("from_saved_build"))}
    return out


def fmt_usage(u):
    if not u or not (u["llm_calls"] or u["embed_calls"]):
        return "no model calls"
    cost = "n/a" if u["cost_usd"] is None else f"${u['cost_usd']:.2f}"
    time_ = f"{u['latency_s']:.0f}s" if u["latency_s"] is not None else "replayed"
    return f"{u['input_tokens'] + u['output_tokens']:,} tok / {cost} / {time_}"


def scorecard(run_dir):
    """Rows of the scoring rule, one column per approach, from the files in run_dir."""
    rows, cols = {}, []
    for path in sorted(run_dir.glob("approach_*.json")):
        r = json.loads(path.read_text())
        name = r["approach"]
        cols.append(name)
        if "error" in r:
            rows.setdefault("status", {})[name] = r["error"]
            continue
        v, e = r["verification"], r.get("eval")
        reruns = sorted((run_dir / "reruns" / name).glob("run_*.json")) if (run_dir / "reruns").exists() else []
        claim_sets = [r["claims"]] + [json.loads(p.read_text())["claims"] for p in reruns]
        cells = {
            "category_prf": e and e["category"], "leaf_prf": e and e["leaf"],
            "quote_coverage": v["quote_coverage"], "quotes_rejected": v["rejected_quote"],
            "labels_rejected": v["rejected_label"], "keyword_fallback": v["keyword_fallback"],
            "claims": v["claims"],
            "rerun_jaccard_leaf": rerun_consistency(claim_sets) if len(claim_sets) >= 3 else None,
            "reruns": len(claim_sets),
            "companies_covered": len(r["companies_covered"]),
            "build": r["usage"]["build"], "ask": r["usage"]["ask"],
        }
        for k, val in cells.items():
            rows.setdefault(k, {})[name] = val
    return {"columns": cols, "rows": rows}


def write_comparison(run_dir, card, man, gt):
    lines = [f"# {config.QUESTION}", "",
             f"Group `{man['group']}` - {len(man['filings'])} filings - model `{man['model']}` - "
             f"run {man['created_at']} - key: **{gt['status'] if gt else 'none'}**", ""]
    if not gt or gt["status"] != "verified":
        lines += ["> **DRAFT KEY - not for slides.** P/R/F1 below are not against a verified key.", ""]
    cols = card["columns"]
    lines += ["| Metric | " + " | ".join(cols) + " |", "|---" * (len(cols) + 1) + "|"]

    def cell(key, fn):
        vals = card["rows"].get(key, {})
        return [fn(vals[c]) if vals.get(c) is not None else "-" for c in cols]

    prf = lambda x: f"{x['precision']:.2f} / {x['recall']:.2f} / {x['f1']:.2f}"  # noqa: E731
    for label, key, fn in [("P / R / F1 category", "category_prf", prf), ("P / R / F1 leaf", "leaf_prf", prf),
                           ("Quote coverage", "quote_coverage", lambda x: f"{x:.0%}"),
                           ("Quotes rejected", "quotes_rejected", str),
                           ("Labels rejected (off-taxonomy)", "labels_rejected", str),
                           ("Rerun consistency (Jaccard, leaf)", "rerun_jaccard_leaf", lambda x: f"{x:.2f}"),
                           ("Companies covered", "companies_covered", lambda x: f"{x} of {len(man['filings'])}"),
                           ("Build: tokens / cost / time", "build", fmt_usage),
                           ("Ask: tokens / cost / time", "ask", fmt_usage)]:
        lines.append(f"| {label} | " + " | ".join(cell(key, fn)) + " |")
    status = card["rows"].get("status")
    if status:
        lines += [""] + [f"- {c}: did not run - {msg}" for c, msg in status.items()]
    lines += ["", "Scoring rule: SCORING_RULE.md. Costs: pricing.yaml, checked " + man["pricing_checked"] + "."]
    text = "\n".join(lines) + "\n"
    (run_dir / "comparison.md").write_text(text)
    return text


def refuse_test_models(served):
    bad = sorted(m for m in served if m.startswith("fake") or m.startswith("unknown:"))
    if bad:
        raise SystemExit(f"Refusing to freeze: answers came from {bad}. results/demo_run/ takes real model output only.")


def freeze(run_dir, served):
    refuse_test_models(served)
    DEMO_RUN.mkdir(parents=True, exist_ok=True)
    for item in DEMO_RUN.iterdir():
        if item.name not in KEEP_ON_FREEZE:
            shutil.rmtree(item) if item.is_dir() else item.unlink()
    for item in run_dir.iterdir():
        dest = DEMO_RUN / item.name
        shutil.copytree(item, dest) if item.is_dir() else shutil.copy2(item, dest)
    print(f"-> frozen into {config.rel(DEMO_RUN)}/")


def jsonable(obj):
    return json.loads(json.dumps(obj, default=lambda o: o.item() if hasattr(o, "item") else str(o)))


def run(approach_keys, out_dir=None, label=""):
    filings = load_corpus()
    tickers = [f["ticker"] for f in filings]
    gt = load_ground_truth()
    print(f"Question: {config.QUESTION}\nGroup: {config.GROUP} | corpus: {config.CORPUS} ({', '.join(tickers)})\n"
          f"Model: {config.LLM_PROVIDER}/{config.LLM_MODEL} | cache: {config.LLM_CACHE} | "
          f"key: {gt['status'] if gt else 'none'}\n")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = out_dir or config.RESULTS_DIR / "runs" / f"{stamp}_{config.CORPUS}"
    run_dir.mkdir(parents=True, exist_ok=True)
    for key in approach_keys:
        name, label_ = APPROACHES[key]
        print(f"== {label_}")
        try:
            result = finalise(_module(key).run(config.QUESTION, filings), filings)
        except (Exception, SystemExit) as exc:  # keep going if one approach can't run
            traceback.print_exc() if isinstance(exc, Exception) and not type(exc).__name__ == "DoesNotFit" else None
            print(f"   skipped: {exc}")
            (run_dir / f"approach_{name}.json").write_text(json.dumps({"approach": name, "error": str(exc)}))
            continue
        result["usage"] = usage_for(result)
        result["eval"] = evaluate(result["claims"], gt, tickers) if gt else None
        result.pop("sources", None)  # excerpts are re-derivable from the corpus; keep the run small
        (run_dir / f"approach_{name}.json").write_text(json.dumps(jsonable(result), indent=1))
        v = result["verification"]
        print(f"   {v['accepted']}/{v['claims']} claims verified; {len(result['shared_risks'])} shared leaves; "
              f"ask {fmt_usage(result['usage']['ask'])}")
    man = manifest.build(filings, [APPROACHES[k][0] for k in approach_keys], label)
    man["served_models"] = sorted(llm.METER.served_models)
    man["ground_truth_status"] = gt["status"] if gt else "none"
    (run_dir / "manifest.json").write_text(json.dumps(man, indent=1))
    for name in ("manifest.csv", "data_quality.jsonl"):
        if (config.CORPUS_DIR / name).exists():
            shutil.copy2(config.CORPUS_DIR / name, run_dir / f"corpus_{name}")
    card = scorecard(run_dir)
    (run_dir / "scorecard.json").write_text(json.dumps(jsonable(card), indent=1))
    text = write_comparison(run_dir, card, man, gt)
    return run_dir, text


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--approaches", default="1,2,3,L")
    parser.add_argument("--freeze", action="store_true", help="copy the run into results/demo_run/")
    parser.add_argument("--out", help="write the run here instead of results/runs/<stamp>")
    parser.add_argument("--label", default="", help="a name for this run, stored in its manifest")
    parser.add_argument("--show", action="store_true", help="print results/latest/comparison.md and exit")
    args = parser.parse_args()
    if args.show:
        print((LATEST / "comparison.md").read_text())
        return
    from pathlib import Path

    run_dir, text = run([k.strip().upper() for k in args.approaches.split(",")],
                        Path(args.out) if args.out else None, args.label)
    if LATEST.exists():
        shutil.rmtree(LATEST)
    shutil.copytree(run_dir, LATEST)
    print("\n" + text)
    print(f"-> {config.rel(run_dir)}/ (copy in {config.rel(LATEST)}/)")
    if args.freeze:
        freeze(run_dir, llm.METER.served_models)


if __name__ == "__main__":
    main()
