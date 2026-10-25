"""Approach-3 A/B on two filings before any full run: A = taxonomy-v2.0 on fixed windows, B = taxonomy-v3.0 on
heading windows. Same model, same LLM_EFFORT, cache on.

    python src/taxonomy_ab.py                    # prints the estimate and STOPS (no model call)
    python src/taxonomy_ab.py --confirm-usd 2    # runs both arms if the estimate fits; hard cap = that amount
    python src/taxonomy_ab.py --report           # rewrite the report from finished arms (no model call)

The cap is enforced twice: the estimate must fit, and LLM_MAX_USD stops live calls once the arms together
have spent it (the second arm gets what the first left). Writes results/taxonomy_ab/<arm>/ and
results/taxonomy_ab/report.md - never results/demo_run/.

Headline metrics: duplicate-label rate and quote pass rate. Fewer claims at the same or better quote pass
rate is a win, not a loss: one label per risk factor is the point of v3.
"""
import argparse
import json
import os
import subprocess
import sys
from collections import Counter

import config

TICKERS = [t.strip().upper() for t in config.env("TAXO_AB_TICKERS", "NXPI,LEA").split(",") if t.strip()]
ARMS = {"A": ("taxonomy-v2.0", "fixed"), "B": ("taxonomy-v3.0", "heading")}
AB_DIR = config.RESULTS_DIR / "taxonomy_ab"
OUT = "approach_3_taxonomy_first.json"


def arm_dir(arm):
    version, split = ARMS[arm]
    return AB_DIR / f"{arm}_{version}_{split}"


def run_arm(arm, cap_usd):
    """Run one arm in a fresh process (the prompt version is read at import)."""
    version, split = ARMS[arm]
    env = {**os.environ, "TAXO_PROMPT_VERSION": version, "TAXO_SPLIT": split, "LLM_MAX_USD": f"{cap_usd:.4f}"}
    print(f"\n=== arm {arm}: {version} on {split} windows, {', '.join(TICKERS)}, cap ${cap_usd:.2f}", flush=True)
    subprocess.run([sys.executable, __file__, "--arm", arm], cwd=config.ROOT, env=env, check=True)
    return json.loads((arm_dir(arm) / OUT).read_text())["live_usd"]


def _arm_main(arm):
    import approach3_taxonomy
    import llm
    from answer import finalise
    from corpus import load_corpus

    filings = [f for f in load_corpus() if f["ticker"] in TICKERS]
    try:
        result = finalise(approach3_taxonomy.run(config.QUESTION, filings), filings)
    except llm.SpendCapReached as exc:
        raise SystemExit(f"Stopped by the spend cap: {exc}. The finished calls are cached.")
    result.pop("sources", None)
    result.update(live_usd=round(llm.METER.live_usd, 4), served_models=sorted(llm.METER.served_models),
                  usage=llm.METER.summary("taxonomy.build"), tickers=TICKERS)
    arm_dir(arm).mkdir(parents=True, exist_ok=True)
    (arm_dir(arm) / OUT).write_text(json.dumps(result, indent=1, default=str))
    print(f"   {result['verification']['accepted']}/{result['verification']['claims']} claims verified; "
          f"live spend ${result['live_usd']:.2f}")


# --------------------------------------------------------------------------- metrics (no model call)
def _section_of(filings):
    """claim -> heading-split section of its quote (same yardstick for both arms)."""
    from corpus import split_risk_factors

    secs = {f["ticker"]: split_risk_factors(f["text"]) for f in filings}

    def find(c):
        return next((s for s in secs[c["company"]] if s["start"] <= c.get("start", -1) < s["end"]), None)
    return find


def metrics(result, filings):
    find = _section_of(filings)
    out = {}
    for t in TICKERS:
        acc = [c for c in result["claims"] if c["company"] == t]
        rej = [c for c in result["rejected"] if c["company"] == t]
        quoted = len(acc) + sum(r["check"] == "quote" for r in rej)  # claims whose quote was checked
        keys = Counter((find(c) or {}).get("idx", -1) for c in acc)
        leaf_keys = Counter(((find(c) or {}).get("idx", -1), c["leaf"]) for c in acc)
        other = [c for c in acc if c["leaf"].startswith("OTHER.")]
        out[t] = {"claims": len(acc) + len(rej), "accepted": len(acc),
                  "quote_pass": round(len(acc) / quoted, 3) if quoted else None,
                  "label_rejected": sum(r["check"] == "label" for r in rej),
                  "duplicate_label_rate": round(sum(n - 1 for n in leaf_keys.values()) / len(acc), 3) if acc else None,
                  "labels_per_factor": round(len(acc) / len(keys), 2) if keys else None,
                  "factors_labelled": len(keys),
                  "other_rate": round(len(other) / len(acc), 3) if acc else None,
                  "other_drivers": sorted({c.get("driver") or "(none)" for c in other})}
    return out


def samples(ra, rb, filings, n=5):
    """n risk factors labelled by both arms, spread over the tickers: leaves side by side."""
    find = _section_of(filings)

    def by_section(r):
        out = {}
        for c in r["claims"]:
            s = find(c)
            if s and s["idx"] > 0:
                out.setdefault((c["company"], s["idx"]), (s, []))[1].append(c)
        return out
    a, b = by_section(ra), by_section(rb)
    both = sorted(set(a) & set(b))
    picks = [k for t in TICKERS for k in [x for x in both if x[0] == t][: (n + 1) // len(TICKERS)]][:n]
    return [{"ticker": k[0], "rf": k[1], "heading": a[k][0]["heading"],
             "a": sorted({c["leaf"] for c in a[k][1]}), "a_n": len(a[k][1]),
             "b": sorted({c["leaf"] + (f" ({c['driver']})" if c.get("driver") else "") for c in b[k][1]}),
             "b_n": len(b[k][1])} for k in picks]


def report():
    from corpus import load_corpus

    paths = {arm: arm_dir(arm) / OUT for arm in ARMS}
    if not all(p.exists() for p in paths.values()):
        raise SystemExit("Both arms must have run first (python src/taxonomy_ab.py --confirm-usd N).")
    filings = [f for f in load_corpus() if f["ticker"] in TICKERS]
    res = {arm: json.loads(p.read_text()) for arm, p in paths.items()}
    m = {arm: metrics(r, filings) for arm, r in res.items()}
    rows = [("Claims returned", "claims", str), ("Accepted", "accepted", str),
            ("**Quote pass rate**", "quote_pass", lambda x: "-" if x is None else f"{x:.1%}"),
            ("**Duplicate-label rate**", "duplicate_label_rate", lambda x: "-" if x is None else f"{x:.1%}"),
            ("Labels per risk factor", "labels_per_factor", str), ("Risk factors labelled", "factors_labelled", str),
            ("Rejected by label rules", "label_rejected", str),
            ("OTHER rate", "other_rate", lambda x: "-" if x is None else f"{x:.1%}"),
            ("OTHER drivers", "other_drivers", lambda x: ", ".join(x) or "-")]
    head = " | ".join(f"{t} {arm}" for t in TICKERS for arm in ARMS)
    lines = ["# Approach 3 A/B: v2.0 fixed windows vs v3.0 heading windows", "",
             f"Filings {', '.join(TICKERS)}. A = {' / '.join(ARMS['A'])}, B = {' / '.join(ARMS['B'])}. Model "
             f"{', '.join(res['B'].get('served_models', []))}. Live spend: A ${res['A']['live_usd']:.2f}, "
             f"B ${res['B']['live_usd']:.2f}.", "",
             "**Read the bold rows first.** Duplicate-label rate = share of accepted claims that repeat a leaf "
             "already given to the same risk factor (the factor is the heading section that holds the quote, the "
             "same yardstick for both arms). Fewer claims at the same or a better quote pass rate is a win: v3 asks "
             "for one label per risk factor, so it should return fewer.", "",
             f"| Metric | {head} |", "|---" * (1 + len(TICKERS) * len(ARMS)) + "|"]
    for label, key, fmt in rows:
        lines.append(f"| {label} | " + " | ".join(fmt(m[arm][t][key]) for t in TICKERS for arm in ARMS) + " |")
    lines += ["", "## Five risk factors side by side", "", "| Ticker | RF | Heading | A (v2.0) | B (v3.0, driver) |",
              "|---|---|---|---|---|"]
    for s in samples(res["A"], res["B"], filings):
        lines.append(f"| {s['ticker']} | {s['rf']} | {s['heading'][:80].replace('|', '/')} | "
                     f"{'<br>'.join(s['a'])} ({s['a_n']} claims) | {'<br>'.join(s['b'])} ({s['b_n']} claims) |")
    path = AB_DIR / "report.md"
    path.write_text("\n".join(lines) + "\n")
    print(f"-> {config.rel(path)}")


def main():
    import estimate_cost
    from corpus import load_corpus

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--confirm-usd", type=float, default=0.0)
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--arm", choices=list(ARMS), help=argparse.SUPPRESS)  # internal: one arm, this process
    args = parser.parse_args()
    if args.arm:
        _arm_main(args.arm)
        return
    if args.report:
        report()
        return
    measure = bool(config.env("ANTHROPIC_API_KEY")) and config.LLM_PROVIDER == "anthropic"
    ab = estimate_cost.taxonomy_ab(load_corpus(), TICKERS, measure)
    print(f"Taxonomy A/B estimate ({config.LLM_MODEL}, {', '.join(ab['tickers'])}): "
          + " + ".join(f"{k} ${v:.2f}" for k, v in ab.items() if k not in ("total_usd", "tickers"))
          + f" = ${ab['total_usd']:.2f} (output tokens assumed; cached calls replay free)")
    if ab["total_usd"] > args.confirm_usd:
        raise SystemExit(f"Nothing was spent. Re-run with --confirm-usd N (N >= {ab['total_usd']:.2f}) to go ahead.")
    left = args.confirm_usd
    for arm in ARMS:
        left -= run_arm(arm, left)
    report()


if __name__ == "__main__":
    main()
