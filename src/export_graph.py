"""Export the GraphRAG graph to JSON so the demo never needs Neo4j at runtime.

    python src/export_graph.py                       # -> results/demo_run/graph.json

Nodes: Company and RiskFactor (with degree = number of companies facing it).
Edges: FACES_RISK, each with the evidence chunk ids it came from.
graph-v2 (default) is exported from the build snapshot (results/graph_snapshot_<corpus>_graph-v2.json), the same
data that was loaded into Neo4j, and adds: per RiskFactor definition, aliases, idf, boilerplate_share; per edge the
verified quotes with EDGAR links; ExposureDriver nodes; the resolution counts and the graph-quality metrics.
graph-v1-workshop is exported from Neo4j as before. Old keys are always filled, so older pages still render.
"""
import argparse
import json
from pathlib import Path

import config

NODES = """
MATCH (c:Company) OPTIONAL MATCH (c)-[:FACES_RISK]->(r:RiskFactor)
RETURN c.ticker AS ticker, c.name AS name, count(DISTINCT r) AS degree ORDER BY ticker
"""
RISKS = """
MATCH (c:Company)-[:FACES_RISK]->(r:RiskFactor)
WITH r, collect(DISTINCT c.ticker) AS tickers
OPTIONAL MATCH (r)-[:FROM_CHUNK]->(ch:Chunk)-[:FROM_DOCUMENT]->(d:Document)
RETURN elementId(r) AS id, r.name AS name, tickers,
       collect(DISTINCT d.ticker + '-g' + toString(ch.index)) AS chunks
ORDER BY size(tickers) DESC, name
"""


def export(path=None, filings=None):
    if config.GRAPH_PROMPT_VERSION == "graph-v2":
        return export_v2(path, filings)
    from approach2_graphrag import driver

    path = Path(path or config.RESULTS_DIR / "demo_run" / "graph.json")
    drv = driver()
    db = config.NEO4J_DATABASE
    companies = [dict(r) for r in drv.execute_query(NODES, database_=db).records]
    risks = [dict(r) for r in drv.execute_query(RISKS, database_=db).records]
    drv.close()
    n = max(len(companies), 1)
    nodes = [{"id": f"c:{c['ticker']}", "type": "Company", "label": c["ticker"], "name": c["name"],
              "industry": config.INDUSTRY.get(c["ticker"], "other"), "degree": c["degree"]} for c in companies]
    edges = []
    for i, r in enumerate(risks):
        rid = f"r:{i}"
        nodes.append({"id": rid, "type": "RiskFactor", "label": r["name"], "degree": len(r["tickers"]),
                      "share": round(len(r["tickers"]) / n, 3), "generic": len(r["tickers"]) >= 0.8 * n,
                      "industries": sorted({config.INDUSTRY.get(t, "other") for t in r["tickers"]})})
        for t in r["tickers"]:
            edges.append({"source": f"c:{t}", "target": rid,
                          "chunks": [ch for ch in r["chunks"] if ch.startswith(f"{t}-g")]})
    build_file = config.RESULTS_DIR / f"graph_build_{config.CORPUS}.json"
    build = json.loads(build_file.read_text()) if build_file.exists() else {}
    top = max((nd for nd in nodes if nd["type"] == "RiskFactor"), key=lambda nd: nd["degree"], default=None)
    graph = {
        "corpus": config.CORPUS,
        "nodes": nodes, "edges": edges,
        "resolution": {"resolver": build.get("resolver"),
                       "risk_factors_exact": build.get("risk_factors_exact"),
                       "risk_factors_resolved": build.get("risk_factors_resolved")},
        "most_generic": top and {"label": top["label"], "companies": top["degree"], "share": top["share"]},
        "build": {k: build.get(k) for k in ("model", "chunk_chars", "usage")},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(graph, indent=1))
    print(f"{len(companies)} companies, {len(risks)} risk factors, {len(edges)} edges -> {config.rel(path)}")
    return graph


def export_v2(path=None, filings=None, snapshot=None):
    import graph_quality
    from approach2_graphrag import snapshot_path
    from corpus import load_corpus
    from verify import edgar_fragment_url

    path = Path(path or config.RESULTS_DIR / "demo_run" / "graph.json")
    snap = snapshot or json.loads(snapshot_path().read_text())
    filings = [f for f in (filings or load_corpus()) if f["ticker"] in snap["tickers"]]
    url = {f["ticker"]: f.get("url", "") for f in filings}
    n = max(len(filings), 1)
    mentions = {m["id"]: m for m in snap["mentions"]}
    rfs = sorted(snap["risk_factors"], key=lambda r: (-r["n_companies"], r["name"]))
    nodes = [{"id": f"c:{f['ticker']}", "type": "Company", "label": f["ticker"], "name": f["company"],
              "industry": config.INDUSTRY.get(f["ticker"], "other"),
              "degree": sum(f["ticker"] in r["tickers"] for r in rfs)} for f in filings]
    edges = []
    for i, r in enumerate(rfs):
        rid = f"r:{i}"
        nodes.append({"id": rid, "type": "RiskFactor", "label": r["name"], "degree": r["n_companies"],
                      "share": round(r["n_companies"] / n, 3), "generic": r["generic"], "industries": r["industries"],
                      "definition": r["definition"], "aliases": r["aliases"], "idf": r["idf"],
                      "boilerplate_share": r["boilerplate_share"]})
        for t in r["tickers"]:
            ms = sorted((mentions[x] for x in r["mention_ids"] if mentions[x]["ticker"] == t), key=lambda m: m["start"])
            edges.append({"source": f"c:{t}", "target": rid, "chunks": sorted({m["chunk_id"] for m in ms}),
                          "quotes": [{"text": m["quote"], "start": m["start"], "end": m["end"],
                                      "chunk_id": m["chunk_id"], "risk_name": m["risk_name"],
                                      "edgar_url": edgar_fragment_url(url[t], m["quote"])
                                      if str(url.get(t, "")).startswith("http") else ""}
                                     for m in ms[:5]]})
    drivers, driver_edges = [], []
    for k, d in enumerate(sorted(snap["drivers"], key=lambda d: (-len(d["tickers"]), d["name"]))):
        did = f"d:{k}"
        drivers.append({"id": did, "type": "ExposureDriver", "label": d["name"], "driver_type": d["type"],
                        "degree": len(d["tickers"]), "aliases": d["aliases"],
                        "industries": sorted({config.INDUSTRY.get(t, "other") for t in d["tickers"]})})
        driver_edges += [{"source": f"c:{t}", "target": did} for t in d["tickers"]]
    a = snap["audit"]
    top = max((nd for nd in nodes if nd["type"] == "RiskFactor"), key=lambda nd: nd["degree"], default=None)
    quality = graph_quality.compute_v2(snap, filings)
    graph = {
        "corpus": config.CORPUS, "prompt_version": snap["prompt_version"],
        "nodes": nodes, "edges": edges, "drivers": drivers, "driver_edges": driver_edges,
        "resolution": {"resolver": snap["resolver"], "prompt_version": snap["prompt_version"],
                       "mentions": a["mentions"], "risk_factors": a["risk_factors"],
                       "merges_approved": len(a["merges_approved"]),
                       "merges_rejected": len(a["merges_rejected"]),
                       "merges_rejected_by_rule": sum(str(r.get("reason", "")).startswith("rule")
                                                      for r in a["merges_rejected"]),
                       "generic_rule": a.get("generic_rule"),
                       "risk_factors_exact": a["names_exact"], "risk_factors_resolved": a["risk_factors"]},
        "most_generic": top and {"label": top["label"], "companies": top["degree"], "share": top["share"]},
        "quality": quality,
        "build": {"model": config.LLM_MODEL, "chunk_chars": config.GRAPH_V2_CHUNK_CHARS},
    }
    build_file = config.RESULTS_DIR / f"graph_build_{config.CORPUS}.json"
    if build_file.exists():
        build = json.loads(build_file.read_text())
        graph["build"] = {k: build.get(k) for k in ("model", "chunk_chars", "usage", "prompt_version", "prompt_sha256")}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(graph, indent=1))
    print(f"{len(filings)} companies, {len(rfs)} risk factors ({quality['shared_specific_cross_industry']} specific "
          f"cross-industry), {len(drivers)} drivers, {len(edges)} edges -> {config.rel(path)}")
    return graph


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", help="default results/demo_run/graph.json")
    export(parser.parse_args().out)
