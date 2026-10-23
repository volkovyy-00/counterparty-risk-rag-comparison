"""Export the GraphRAG graph to JSON so the demo never needs Neo4j at runtime.

    python export_graph.py                       # -> results/demo_run/graph.json

Nodes: Company and RiskFactor (with degree = number of companies facing it).
Edges: FACES_RISK, each with the evidence chunk ids it came from.
Also records the entity-resolution numbers (RiskFactor count after exact-name
merging vs after fuzzy merging) from results/graph_build_<corpus>.json.
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


def export(path=None):
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", help="default results/demo_run/graph.json")
    export(parser.parse_args().out)
