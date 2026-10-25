"""Produce results/demo_run/ from a real run - the only step that spends money. Run it once, then freeze.

    python src/real_run.py                    # checks + cost estimate, then STOPS if the estimate is over $5
    python src/real_run.py --confirm-usd 25   # runs if the estimate is at or below $25

Steps: fetch 10-Ks (if not fetched yet) -> estimate cost -> build graph -> run 1,2,3,L
and freeze -> export graph -> audit run B (approach 3, prompt v2.1) -> reruns 2 and 3
(cache off) -> governance fixtures -> build demo/index.html -> screenshots.
Every model call is cached, so `LLM_CACHE=replay python src/run_all.py` reproduces run A offline.
"""
import argparse
import os
import subprocess
import sys

import config

GATE_USD = 5.0


def step(title, *cmd, env=None):
    print(f"\n=== {title}\n$ {' '.join(cmd)}", flush=True)
    subprocess.run([sys.executable, *cmd], cwd=config.ROOT, check=True, env={**os.environ, **(env or {})})


def preflight():
    problems = []
    if config.LLM_PROVIDER == "anthropic" and not config.env("ANTHROPIC_API_KEY"):
        problems.append("no ANTHROPIC_API_KEY (or API_KEY) in the environment or .env")
    corpus = config.DATA_DIR / "corpus" / "edgar_latest" / "manifest.csv"
    if not corpus.exists() and not config.SEC_USER_AGENT:
        problems.append('SEC_USER_AGENT="Name email" is needed to fetch the 10-Ks')
    if not config.NEO4J_PASSWORD:
        problems.append("NEO4J_PASSWORD not set (docker compose up -d; see .env.sample)")
    if config.CORPUS != "edgar_latest":
        problems.append(f"CORPUS={config.CORPUS}: the demo run uses edgar_latest")
    if problems:
        raise SystemExit("Cannot start the real run:\n- " + "\n- ".join(problems))
    return corpus.exists()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--confirm-usd", type=float, default=0.0, help="spend up to this much (estimate must fit)")
    parser.add_argument("--reruns", type=int, default=2)
    parser.add_argument("--skip-screenshots", action="store_true")
    args = parser.parse_args()
    have_corpus = preflight()
    if not have_corpus:
        step("Fetch latest 10-K per ticker from SEC EDGAR (cached on disk)", "src/fetch_10k.py")

    import estimate_cost
    from corpus import load_corpus

    est = estimate_cost.estimate(load_corpus(), args.reruns, measure=True)
    print("\n" + estimate_cost.report(est, args.reruns))
    budget = max(args.confirm_usd, GATE_USD)
    if est["total_usd"] > budget:
        raise SystemExit(f"\nEstimated ${est['total_usd']:.2f} is over ${budget:.2f}. Nothing was spent. "
                         f"Re-run with --confirm-usd {est['total_usd'] * 1.3:.0f} to go ahead (30% headroom).")

    step("Build the knowledge graph (approach 2)", "src/approach2_graphrag.py", "build", "--reset")
    step("Run A: approaches 1, 2, 3 and the long-context control; freeze", "src/run_all.py", "--approaches", "1,2,3,L",
         "--freeze", "--label", "run A (prompt taxonomy-v2.0)")
    step("Export the graph for offline use", "src/export_graph.py")
    step("Ask the graph: the fixed screen-4 questions", "src/graph_qa.py", "--confirm-usd", f"{budget:.2f}")
    step("Run B for the audit trail: approach 3 with prompt v2.1", "src/run_all.py", "--approaches", "3",
         "--out", str(config.RESULTS_DIR / "demo_run" / "audit" / "run_b"), "--label", "run B (prompt taxonomy-v2.1)",
         env={"TAXO_PROMPT_VERSION": "taxonomy-v2.1"})
    if args.reruns:
        step(f"Rerun consistency: {args.reruns} more runs per approach, cache off", "src/rerun.py",
             "--approaches", "1,2,3", "--n", str(args.reruns))
    step("Governance fixtures (no model call)", "src/governance.py")
    step("Build the demo page", "src/build_demo.py")
    if not args.skip_screenshots:
        step("Screenshots (visual fallback)", "demo/screenshots.py")
    print("\nDone. Check results/demo_run/comparison.md, then commit results/demo_run/, cache/ and data/corpus/.")


if __name__ == "__main__":
    main()
