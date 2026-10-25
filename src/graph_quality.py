"""Graph-quality metrics for approach 2, computed from the build files (no Neo4j, no model call).

    python src/graph_quality.py                       # current GRAPH_PROMPT_VERSION
    python src/graph_quality.py --version graph-v1-workshop

graph-v2 reads results/graph_snapshot_<corpus>_graph-v2.json (built from the extraction JSONL);
graph-v1-workshop reads the RiskFactor names saved in results/graph_build_<corpus>.json. v1 stores no quotes,
so its quote-based metrics are reported as not applicable rather than estimated.
-> results/graph_quality_<corpus>_<version>.json
"""
import argparse
import json
import math

import config


def _tokens_and_cost(results_dir):
    path = results_dir / f"graph_build_{config.CORPUS}.json"
    if not path.exists():
        return None
    build = json.loads(path.read_text())
    stages = build.get("usage_by_stage") or {"graph.build": build.get("usage", {})}
    return {s: {"input_tokens": int(u.get("input_tokens", 0)), "output_tokens": int(u.get("output_tokens", 0)),
                "llm_calls": int(u.get("llm_calls", 0)), "cost_usd": round(u.get("cost_usd", 0.0), 4)}
            for s, u in stages.items()}


def _shared(risk_factors, n_total):
    """Common counts from [{name, tickers, generic?}] - the same for both versions."""
    generic_min = math.ceil(config.GENERIC_SHARE * n_total)
    rows = []
    for r in risk_factors:
        tickers = sorted(set(r["tickers"]))
        inds = {config.INDUSTRY.get(t, "other") for t in tickers}
        generic = r.get("generic", len(tickers) >= generic_min)
        rows.append({"name": r["name"], "n": len(tickers), "generic": generic, "cross": {"auto", "semis"} <= inds})
    total = len(rows) or 1
    shared_specific = [r for r in rows if r["n"] >= config.MIN_SHARED and not r["generic"]]
    top = max(rows, key=lambda r: (r["n"], r["name"]), default=None)
    return {
        "canonical_risk_factors": len(rows),
        "singleton_share": round(sum(r["n"] == 1 for r in rows) / total, 4),
        "shared_specific": len(shared_specific),
        "shared_specific_cross_industry": sum(r["cross"] for r in shared_specific),
        "generic_risk_factors": sum(r["generic"] for r in rows),
        "most_generic": top and {"name": top["name"], "companies": top["n"]},
        "examples_shared_specific": [r["name"] for r in sorted(shared_specific, key=lambda r: (-r["cross"], -r["n"],
                                                                                               r["name"]))[:5]],
    }


def compute_v2(snap, filings):
    import graph_v2

    filings = [f for f in filings if f["ticker"] in snap["tickers"]]
    mentions = snap["mentions"]
    total = len(mentions) + snap.get("rejected", 0)
    # paragraph coverage: share of Item 1A paragraphs (>= 200 chars) that contain at least one verified quote
    covered = paras = 0
    spans = {}
    for m in mentions:
        spans.setdefault(m["ticker"], []).append((m["start"], m["end"]))
    for f in filings:
        for s, e in graph_v2.paragraphs(f["text"]):
            if e - s < 200:
                continue
            paras += 1
            covered += any(a < e and b > s for a, b in spans.get(f["ticker"], []))
    a = snap["audit"]
    per_filing = {f["ticker"]: sum(m["ticker"] == f["ticker"] for m in mentions) for f in filings}
    shared_drivers = [d for d in snap["drivers"] if len(d["tickers"]) >= config.MIN_SHARED]
    return {
        "prompt_version": snap["prompt_version"], "resolver": snap["resolver"], "filings": len(filings),
        "quote_verification_rate": round(len(mentions) / total, 4) if total else None,
        "paragraph_coverage": round(covered / paras, 4) if paras else None,
        "mentions": len(mentions), "mentions_rejected": snap.get("rejected", 0), "mentions_per_filing": per_filing,
        **_shared(snap["risk_factors"], len(filings)),
        "shared_drivers": len(shared_drivers),
        "examples_shared_drivers": [f"{d['name']} ({', '.join(d['tickers'])})" for d in
                                    sorted(shared_drivers, key=lambda d: (-len(d["tickers"]), d["name"]))[:5]],
        "resolution": {"names_exact": a["names_exact"], "components": len(a["components"]),
                       "merges_approved": len(a["merges_approved"]),
                       "merges_rejected_llm": sum(r.get("reason") == "llm" for r in a["merges_rejected"]),
                       "merges_rejected_rule": sum(str(r.get("reason", "")).startswith("rule")
                                                   for r in a["merges_rejected"])},
    }


def compute_v1(build):
    names = build.get("risk_factor_names") or []
    n_total = len(build.get("tickers") or {t for r in names for t in r["tickers"]})
    return {
        "prompt_version": "graph-v1-workshop", "resolver": build.get("resolver"), "filings": n_total,
        "quote_verification_rate": "n/a (v1 stores no quotes)", "paragraph_coverage": "n/a (v1 stores no quotes)",
        "mentions": "n/a", "mentions_per_filing": "n/a",
        **_shared(names, n_total),
        "shared_drivers": "n/a (v1 has no ExposureDriver nodes)",
        "resolution": {"names_exact": build.get("risk_factors_exact"),
                       "after_fuzzy": build.get("risk_factors_resolved")},
    }


def compute(version=None, results_dir=None, filings=None):
    from corpus import load_corpus

    version = version or config.GRAPH_PROMPT_VERSION
    results_dir = results_dir or config.RESULTS_DIR
    if version == "graph-v2":
        snap = json.loads((results_dir / f"graph_snapshot_{config.CORPUS}_graph-v2.json").read_text())
        out = compute_v2(snap, filings or load_corpus())
    else:
        out = compute_v1(json.loads((results_dir / f"graph_build_{config.CORPUS}.json").read_text()))
    out["tokens_and_cost"] = _tokens_and_cost(results_dir) or "not recorded"
    path = results_dir / f"graph_quality_{config.CORPUS}_{version}.json"
    path.write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", choices=["graph-v1-workshop", "graph-v2"])
    print(json.dumps(compute(parser.parse_args().version), indent=1))
