"""Produce results/demo_run/ from a real run - the only step that spends money. Staged; each stage needs a "go".

    python src/real_run.py --stage core                    # preflight + measured estimate, then STOPS
    LLM_MAX_USD=20 python src/real_run.py --stage core --confirm-usd 20
    LLM_MAX_USD=10 python src/real_run.py --stage extras --confirm-usd 10   # after core is frozen

core   : graph build (--reset; calls already in cache/chat/, e.g. the A/B filings, replay for free) -> run A of
         approaches 1, 2, 3 and L, frozen -> export graph -> graph QA -> governance fixtures -> page -> screenshots.
         No reruns, no run B.
extras : (a) approach 1 reruns (--n 2); (b) one approach 3 rerun (--n 1, taxonomy-v3.0, cache off); (c) audit
         run B as a model swap: approach 3, taxonomy-v3.0, on RUN_B_MODEL -> governance -> page. Approach 2 is not
         rerun (a rebuild is priced and shown instead). Over the cap, (b) is dropped first, then (c).
         taxonomy-v3.1 stays runnable by hand: TAXO_PROMPT_VERSION=taxonomy-v3.1 python src/run_all.py ...

Gates: the stage estimate must be <= its cap and <= --confirm-usd, and LLM_MAX_USD must be set and <= the cap.
Every live call is logged to results/spend/real_run_<stage>.jsonl; LLM_MAX_USD applies to the whole stage (the
log carries the spend across steps). Every model call is cached, so LLM_CACHE=replay reproduces run A offline.
"""
import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict

import config

DEMO_RUN = config.RESULTS_DIR / "demo_run"
SPEND_DIR = config.RESULTS_DIR / "spend"


def ledger(stage):
    return SPEND_DIR / f"real_run_{stage}.jsonl"


def step(stage, title, *cmd, env=None):
    print(f"\n=== {title}\n$ {' '.join(cmd)}", flush=True)
    extra = {"LLM_SPEND_LEDGER": str(ledger(stage)), "LLM_SPEND_STEP": title, **(env or {})}
    subprocess.run([sys.executable, *cmd], cwd=config.ROOT, check=True, env={**os.environ, **extra})


def spent(stage):
    """Measured live spend per step, from the stage's ledger."""
    path, out = ledger(stage), defaultdict(float)
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                out[rec["step"]] += rec["usd"]
    return dict(out)


def preflight(stage):
    problems = []
    if config.LLM_PROVIDER == "anthropic" and not config.env("ANTHROPIC_API_KEY"):
        problems.append("no ANTHROPIC_API_KEY (or API_KEY) in the environment or .env")
    if not (config.DATA_DIR / "corpus" / "edgar_latest" / "manifest.csv").exists():
        problems.append("data/corpus/edgar_latest/ is missing: the corpus is frozen and never fetched live")
    if stage == "core" and not config.NEO4J_PASSWORD:
        problems.append("NEO4J_PASSWORD not set (docker compose up -d; see .env.sample)")
    if config.CORPUS != "edgar_latest":
        problems.append(f"CORPUS={config.CORPUS}: the demo run uses edgar_latest")
    if stage == "extras" and not (DEMO_RUN / "manifest.json").exists():
        problems.append("no frozen run A in results/demo_run/: run --stage core first")
    if problems:
        raise SystemExit("Cannot start the real run:\n- " + "\n- ".join(problems))


def gate(stage, total, confirm):
    import estimate_cost

    cap = estimate_cost.STAGE_CAPS[stage]
    if total > cap:
        raise SystemExit(f"\nEstimated ${total:.2f} is over the {stage} cap of ${cap:.2f}. Nothing was spent.")
    if total > confirm:
        raise SystemExit(f"\nNothing was spent. To run: LLM_MAX_USD={cap:.0f} python src/real_run.py --stage {stage} "
                         f"--confirm-usd {cap:.0f}")
    if config.LLM_MAX_USD is None or config.LLM_MAX_USD > cap:
        raise SystemExit(f"\nSet LLM_MAX_USD to the stage cap (<= {cap:.0f}) for a paid stage. Nothing was spent.")
    prior = sum(spent(stage).values())
    if prior:
        print(f"Note: {config.rel(ledger(stage))} already logs ${prior:.2f}; it counts towards LLM_MAX_USD.")


def save_estimate(est):
    path = DEMO_RUN / "estimates.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    rows = est["rows"] if est["stage"] == "core" else list(est["subs"].values())
    data[est["stage"]] = {"total_usd": round(est["total_usd"], 4), "input_measured": est["input_measured"],
                          "rows": [{k: r[k] for k in ("stage", "calls", "input_tokens", "output_tokens", "cost_usd")}
                                   for r in rows]}
    data["approach2_rebuild_usd"] = est["rebuild_usd"]
    DEMO_RUN.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1))


def save_spend(stage):
    path = DEMO_RUN / "spend.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    per_step = spent(stage)
    data[stage] = {"total_usd": round(sum(per_step.values()), 4),
                   "per_step": {k: round(v, 4) for k, v in per_step.items()}}
    path.write_text(json.dumps(data, indent=1))
    print(f"\nMeasured live spend, {stage}: ${data[stage]['total_usd']:.2f}")
    for k, v in data[stage]["per_step"].items():
        print(f"  {k}: ${v:.2f}")


def core(args):
    cap = f"{config.LLM_MAX_USD:.2f}"
    step("core", "Build the knowledge graph (approach 2)", "src/approach2_graphrag.py", "build", "--reset")
    step("core", "Run A: approaches 1, 2, 3 and the long-context control; freeze", "src/run_all.py",
         "--approaches", "1,2,3,L", "--freeze", "--label", "run A (prompt taxonomy-v3.0)",
         env={"TAXO_PROMPT_VERSION": "taxonomy-v3.0"})
    step("core", "Export the graph for offline use", "src/export_graph.py")
    step("core", "Ask the graph: the fixed screen-4 questions", "src/graph_qa.py", "--confirm-usd", cap)


def extras(args, subs):
    if "a" in subs:
        step("extras", "(a) Approach 1 reruns, cache off", "src/rerun.py", "--approaches", "1", "--n", "2")
    if "b" in subs:
        step("extras", "(b) Approach 3 rerun, taxonomy-v3.0, cache off", "src/rerun.py", "--approaches", "3",
             "--n", "1", env={"TAXO_PROMPT_VERSION": "taxonomy-v3.0"})
    if "c" in subs:
        import estimate_cost

        step("extras", "(c) Audit run B: approach 3 after a model swap", "src/run_all.py", "--approaches", "3",
             "--out", str(DEMO_RUN / "audit" / "run_b"), "--label", "run B (model swap)",
             env={"LLM_MODEL": estimate_cost.RUN_B_MODEL, "TAXO_PROMPT_VERSION": "taxonomy-v3.0"})


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stage", choices=("core", "extras"), required=True)
    parser.add_argument("--confirm-usd", type=float, default=0.0, help="spend up to this much (estimate must fit)")
    parser.add_argument("--only", help="extras: run only these sub-steps, e.g. a,c")
    parser.add_argument("--skip-screenshots", action="store_true")
    args = parser.parse_args()
    preflight(args.stage)

    import estimate_cost
    from corpus import load_corpus

    filings = load_corpus()
    if args.stage == "core":
        est = estimate_cost.estimate_core(filings, measure=True)
        print("\n" + estimate_cost.report_stage(est))
        total, subs = est["total_usd"], None
    else:
        est = estimate_cost.estimate_extras(filings, measure=True)
        print("\n" + estimate_cost.report_stage(est))
        only = [x.strip() for x in args.only.split(",")] if args.only else None
        subs, dropped = estimate_cost.fit_extras(est, estimate_cost.STAGE_CAPS["extras"], only)
        total = sum(est["subs"][k]["cost_usd"] or 0 for k in subs)
        if dropped:
            print(f"\nOver the cap: dropped {', '.join(f'({k})' for k in dropped)}. Running {', '.join(subs)}: "
                  f"${total:.2f}")
    gate(args.stage, total, args.confirm_usd)

    save_estimate(est)
    if args.stage == "core":
        core(args)
    else:
        extras(args, subs)
    save_estimate(est)  # freeze keeps estimates.json; rewrite in case the run dir was recreated
    save_spend(args.stage)
    step(args.stage, "Governance fixtures (no model call)", "src/governance.py")
    step(args.stage, "Build the demo page (DRAFT until the key is verified)", "src/build_demo.py", "--draft")
    if not args.skip_screenshots:
        step(args.stage, "Screenshots (visual fallback)", "demo/screenshots.py")
    print("\nDone. Check results/demo_run/comparison.md, then commit results/demo_run/, results/spend/ and cache/.")


if __name__ == "__main__":
    main()
