"""Check that every console graph pattern returns the same rows in Neo4j (Cypher) and in Python (graph_local).

    docker compose up -d && python src/graph_parity.py           # compare against the graph already in Neo4j
    python src/graph_parity.py --load                            # empty database only: load graph.json first

No model call, no spend. It never deletes anything: --load refuses unless the database is empty.
Exit status 1 on any mismatch.
"""
import argparse
import json
import sys

from neo4j import GraphDatabase, RoutingControl

import config
import graph_local
from graph_patterns import CYPHER

# One parameter set per pattern case; tickers and industries cover both industries.
CASES = [
    ("SHARED_AMONG", {"tickers": ["GM", "NXPI"], "min_shared": 2, "limit": 8}),
    ("SHARED_AMONG", {"tickers": ["F", "BWA", "LEA", "MCHP", "ON"], "min_shared": 3, "limit": 8}),
    ("SHARED_VS_SPECIFIC", {"min_shared": 2, "industries": ["auto", "semis"]}),
    ("MOST_COMMON", {"industry": None, "specific_only": False, "limit": 5}),
    ("MOST_COMMON", {"industry": "semis", "specific_only": True, "limit": 5}),
    ("COMPANY_RISKS", {"ticker": "TSLA", "limit": 8}),
    ("COMPANY_RISKS", {"ticker": "NXPI", "limit": 8}),
    ("COMPANY_PEERS", {"ticker": "TSLA", "limit": 6}),
    ("COMPANY_PEERS", {"ticker": "TXN", "limit": 6}),
    ("UNIQUE_TO", {"ticker": "F", "limit": 6}),
    ("CROSS_INDUSTRY", {"industries": ["auto", "semis"], "limit": 6}),
    ("INDUSTRY_ONLY", {"industry": "auto", "limit": 6}),
    ("INDUSTRY_ONLY", {"industry": "semis", "limit": 6}),
]


def norm(rows):
    """Neo4j and the export number risk nodes differently; everything else must match, in order."""
    return [(r["risk"], r["role"], bool(r["generic"]), r["n_companies"],
             sorted((e["ticker"], tuple(e["quotes"]), tuple(e["spans"])) for e in r["evidence"])) for r in rows]


def load(drv, g):
    n = drv.execute_query("MATCH (x) RETURN count(x) AS n", database_=config.NEO4J_DATABASE).records[0]["n"]
    if n:
        raise SystemExit(f"--load needs an empty database; this one has {n} nodes. Nothing was changed.")
    companies = [{"ticker": x["label"], "name": x["name"], "industry": x["industry"]}
                 for x in g["nodes"] if x["type"] == "Company"]
    risks = [{"id": x["id"][2:], "name": x["label"], "definition": x.get("definition"), "generic": x.get("generic"),
              "n_companies": x["degree"], "boilerplate_share": x.get("boilerplate_share")}
             for x in g["nodes"] if x["type"] == "RiskFactor"]
    edges = [{"ticker": e["source"][2:], "rid": e["target"][2:], "quotes": [q["text"] for q in e["quotes"]],
              "spans": [f"{q['start']}:{q['end']}" for q in e["quotes"]], "chunk_ids": [q["chunk_id"] for q in e["quotes"]]}
             for e in g["edges"]]
    q = drv.execute_query
    q("UNWIND $rows AS x CREATE (:Company {ticker: x.ticker, name: x.name, industry: x.industry})", rows=companies)
    q("UNWIND $rows AS x CREATE (r:RiskFactor) SET r = x", rows=risks)
    q("""UNWIND $rows AS x MATCH (c:Company {ticker: x.ticker}), (r:RiskFactor {id: x.rid})
         CREATE (c)-[:FACES_RISK {quotes: x.quotes, spans: x.spans, chunk_ids: x.chunk_ids}]->(r)""", rows=edges)
    print(f"loaded {len(companies)} companies, {len(risks)} risks, {len(edges)} links from graph.json")


def run(drv, g):
    bad = 0
    for name, params in CASES:
        neo = [dict(r) for r in drv.execute_query(CYPHER[name], params, routing_=RoutingControl.READ,
                                                     database_=config.NEO4J_DATABASE).records]
        py = graph_local.rows_for(g, name, params)
        ok = norm(neo) == norm(py)
        bad += not ok
        print(f"{'ok ' if ok else 'BAD'} {name:<19} {json.dumps(params)[:60]:<60} {len(neo)} rows")
    # WHO_FACES takes risk names: use the top rows of MOST_COMMON so the names exist in both.
    names = [r["risk"] for r in graph_local.rows_for(g, "MOST_COMMON", {"limit": 3})]
    neo = [dict(r) for r in drv.execute_query(CYPHER["WHO_FACES"], {"risks": names}, routing_=RoutingControl.READ,
                                                 database_=config.NEO4J_DATABASE).records]
    ok = norm(neo) == norm(graph_local.who_faces(g, names))
    bad += not ok
    print(f"{'ok ' if ok else 'BAD'} WHO_FACES           {names[:2]} {len(neo)} rows")
    return bad


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--load", action="store_true")
    args = parser.parse_args()
    g = graph_local.load()
    with GraphDatabase.driver(config.NEO4J_URI, auth=(config.NEO4J_USERNAME, config.NEO4J_PASSWORD)) as drv:
        if args.load:
            load(drv, g)
        bad = run(drv, g)
    print("all patterns match" if not bad else f"{bad} mismatches")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
