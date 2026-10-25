"""Graph A/B on a few filings before any full rebuild: A = graph-v1-workshop + fuzzy, B = graph-v2 + llm resolver.

    python src/graph_ab.py                      # prints the estimate and STOPS (no model call)
    python src/graph_ab.py --confirm-usd 5      # runs both builds if the estimate fits, then writes the report
    python src/graph_ab.py --report             # rewrite the report from finished runs (no model call)

Same model, same LLM_EFFORT, cache on (the B calls are reused by a later full v2 build of these filings).
Each arm writes to results/graph_ab/<version>/ and builds into the local Neo4j (each build resets it).
-> results/graph_ab_<date>.md
"""
import argparse
import datetime
import json
import os
import subprocess
import sys

import config

VERSIONS = {"graph-v1-workshop": "fuzzy", "graph-v2": "llm"}
AB_DIR = config.RESULTS_DIR / "graph_ab"


def arm_dir(version):
    return AB_DIR / version


def run_arm(version):
    env = {**os.environ, "GRAPH_PROMPT_VERSION": version, "GRAPH_RESOLVER": VERSIONS[version],
           "RESULTS_DIR": str(arm_dir(version))}
    tickers = ",".join(config.GRAPH_AB_TICKERS)
    for cmd in (["src/approach2_graphrag.py", "build", "--reset", "--tickers", tickers],
                ["src/graph_quality.py", "--version", version]):
        print(f"\n=== {version}: {' '.join(cmd)}", flush=True)
        subprocess.run([sys.executable, *cmd], cwd=config.ROOT, env=env, check=True)


def _load(version, name):
    path = arm_dir(version) / name
    return json.loads(path.read_text()) if path.exists() else None


def _fmt(x):
    if isinstance(x, float):
        return f"{x:.1%}" if x <= 1 else f"{x:.2f}"
    return "-" if x is None else str(x)


def merge_examples(a_build, b_audit):
    """3 merges B made that A's string rule would have missed, and the 3 most doubtful merges A's rule made."""
    from rapidfuzz import fuzz

    import graph_resolve
    import llm

    b_missed_by_a = []
    for m in b_audit.get("merges_approved", []):
        names = m["members"]
        if any(fuzz.WRatio(x, y, processor=str.lower) / 100 < 0.8 for i, x in enumerate(names) for y in names[i + 1:]):
            b_missed_by_a.append(f"{m['canonical_name'] or names[0]}: " + " + ".join(f"'{n}'" for n in names))
    exact = sorted({r["name"] for r in (a_build or {}).get("risk_factor_names_exact", [])})
    a_pairs = [(x, y) for i, x in enumerate(exact) for y in exact[i + 1:]
               if fuzz.WRatio(x, y, processor=str.lower) / 100 >= 0.8]
    flagged = [(x, y, graph_resolve.keep_apart_violation([x, y])) for x, y in a_pairs]
    doubtful = [f"'{x}' + '{y}' (keep-apart rule: {rule})" for x, y, rule in flagged if rule]
    if len(doubtful) < 3 and a_pairs:  # then the least similar in meaning (local embeddings, no cost)
        rest = [(x, y) for x, y, rule in flagged if not rule]
        vecs = llm.embed(sorted({n for p in rest for n in p}))
        idx = {n: i for i, n in enumerate(sorted({n for p in rest for n in p}))}
        import numpy as np

        v = np.asarray(vecs, dtype=np.float32)
        v /= np.linalg.norm(v, axis=1, keepdims=True).clip(1e-9)
        scored = sorted(rest, key=lambda p: float(v[idx[p[0]]] @ v[idx[p[1]]]))
        doubtful += [f"'{x}' + '{y}' (cosine {float(v[idx[x]] @ v[idx[y]]):.2f}; check by hand)" for x, y in scored]
    return b_missed_by_a[:3], doubtful[:3], len(a_pairs)


def report():
    qa, qb = _load("graph-v1-workshop", f"graph_quality_{config.CORPUS}_graph-v1-workshop.json"), \
        _load("graph-v2", f"graph_quality_{config.CORPUS}_graph-v2.json")
    if not (qa and qb):
        raise SystemExit("Both arms must have run first (python src/graph_ab.py --confirm-usd N).")
    a_build = _load("graph-v1-workshop", f"graph_build_{config.CORPUS}.json")
    b_audit = _load("graph-v2", f"graph_resolution_{config.CORPUS}.json") or {}
    keys = ["quote_verification_rate", "paragraph_coverage", "mentions", "canonical_risk_factors", "singleton_share",
            "shared_specific", "shared_specific_cross_industry", "generic_risk_factors", "shared_drivers"]
    lines = [f"# Graph A/B - {datetime.date.today().isoformat()}", "",
             f"Filings: {', '.join(config.GRAPH_AB_TICKERS)} · model {config.LLM_MODEL} · effort {config.LLM_EFFORT}",
             "A = graph-v1-workshop + fuzzy resolver (WRatio >= 0.8) · B = graph-v2 + LLM-checked resolver", "",
             "| Metric | A (v1 workshop) | B (v2) |", "|---|---|---|"]
    lines += [f"| {k} | {_fmt(qa.get(k))} | {_fmt(qb.get(k))} |" for k in keys]
    lines.append(f"| most generic | {_fmt(qa.get('most_generic'))} | {_fmt(qb.get('most_generic'))} |")
    for arm, q in (("A", qa), ("B", qb)):
        tc = q.get("tokens_and_cost")
        if isinstance(tc, dict):
            lines.append(f"| cost {arm} (USD) | " + ", ".join(f"{s}: {u['cost_usd']:.2f}" for s, u in tc.items()) + " | |")
    lines += ["", "## Example shared, specific RiskFactors", "", "A: " + "; ".join(qa.get("examples_shared_specific") or ["none"]),
              "", "B: " + "; ".join(qb.get("examples_shared_specific") or ["none"]), "",
              "B shared drivers: " + "; ".join(qb.get("examples_shared_drivers") or ["none"])]
    b_only, a_doubtful, n_a = merge_examples(a_build, b_audit)
    lines += ["", "## Merges B made that A's string rule would have missed", ""] + \
             [f"- {x}" for x in b_only or ["none"]]
    lines += ["", f"## Most doubtful of A's {n_a} fuzzy merges (judge by hand)", ""] + \
             [f"- {x}" for x in a_doubtful or ["none"]]
    approved = b_audit.get("merges_approved", [])
    import graph_resolve

    bad = [m for m in approved if graph_resolve.keep_apart_violation(m["members"])]
    checks = {
        "verification >= 95%": isinstance(qb["quote_verification_rate"], float) and qb["quote_verification_rate"] >= .95,
        "coverage >= 85%": isinstance(qb["paragraph_coverage"], float) and qb["paragraph_coverage"] >= .85,
        "singleton share lower than A": qb["singleton_share"] < qa["singleton_share"],
        ">= 3 shared specific RiskFactors": qb["shared_specific"] >= 3,
        ">= 1 shared specific auto<->semis": qb["shared_specific_cross_industry"] >= 1,
        "no keep-apart pair merged": not bad,
    }
    lines += ["", "## Pass criteria for B", ""] + [f"- [{'x' if ok else ' '}] {k}" for k, ok in checks.items()]
    lines += ["", "PASS" if all(checks.values()) else "FAIL - report why and stop; no prompt iteration without asking."]
    out = config.RESULTS_DIR / f"graph_ab_{datetime.date.today().isoformat()}.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return checks


def main():
    import estimate_cost
    from corpus import load_corpus

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--confirm-usd", type=float, default=0.0)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    if args.report:
        report()
        return
    measure = bool(config.env("ANTHROPIC_API_KEY")) and config.LLM_PROVIDER == "anthropic"
    ab = estimate_cost.graph_ab(load_corpus(), measure)
    print(f"Graph A/B estimate ({config.LLM_MODEL}, {', '.join(ab['tickers'])}): A ${ab['graph-v1-workshop']:.2f} + "
          f"B ${ab['graph-v2']:.2f} = ${ab['total_usd']:.2f} (output tokens assumed; see estimate_cost.py)")
    if ab["total_usd"] > args.confirm_usd:
        raise SystemExit(f"Nothing was spent. Re-run with --confirm-usd N (N >= {ab['total_usd']:.2f}) to go ahead.")
    for version in VERSIONS:
        run_arm(version)
    report()


if __name__ == "__main__":
    main()
