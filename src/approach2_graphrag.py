"""Approach 2 - GraphRAG with Neo4j, built on the workshop's SimpleKGPipeline.

    python src/approach2_graphrag.py build --reset   # once, before the demo (LLM-heavy)
    python src/approach2_graphrag.py ask             # what the runner calls

Graph:  (Company)-[:FACES_RISK]->(RiskFactor)-[:FROM_CHUNK]->(Chunk)-[:FROM_DOCUMENT]->(Document)
        Chunks are cited as TICKER-g<index>, e.g. NVDA-g7.

Design choice: the LLM extracts RiskFactor nodes only. Which company faces a
risk is taken from provenance (the 10-K it was extracted from), not from the
LLM - in Item 1A the filer is always the company at risk.
"""
import argparse
import asyncio
import json
import logging

from neo4j import GraphDatabase

import config
import llm
from answer import CLAIMS_SCHEMA, system_prompt
from corpus import load_corpus

SCHEMA = {"node_types": [{"label": "RiskFactor", "properties": [{"name": "name", "type": "STRING"}],
                          "description": "A risk the filing company says could harm its business."}],
          "relationship_types": [], "patterns": []}

EXTRACTION_INSTRUCTION = (
    "Extract only RiskFactor nodes. Name each RiskFactor with a short, generic noun phrase of 2-5 words "
    "that another company could also use (for example 'Cybersecurity breaches', 'Supplier concentration', "
    "'Export controls'), not company-specific wording. Return no relationships.\n\n"
)

SHARED_RISKS_CYPHER = """
MATCH (c:Company)-[:FACES_RISK]->(r:RiskFactor)
WITH r, collect(DISTINCT c.ticker) AS tickers
WHERE size(tickers) >= $min_shared
MATCH (r)-[:FROM_CHUNK]->(ch:Chunk)-[:FROM_DOCUMENT]->(d:Document)
WITH r, tickers, d.ticker AS ticker, collect(ch)[0] AS first
WITH r, tickers, collect({chunk_id: ticker + '-g' + toString(first.index), ticker: ticker,
                          text: first.text}) AS evidence
RETURN r.name AS risk, tickers, evidence
ORDER BY size(tickers) DESC, risk
LIMIT $limit
"""

# The workshop's "what risks connect companies" pattern: seeded by top-k vector hits.
VECTOR_SEEDED_CYPHER = """
WITH node
MATCH (node)-[:FROM_DOCUMENT]->(d:Document)<-[:FILED]-(c1:Company)
MATCH (c1)-[:FACES_RISK]->(r:RiskFactor)<-[:FACES_RISK]-(c2:Company)
WHERE c1 <> c2
MATCH (r)-[:FROM_CHUNK]->(rc:Chunk)-[:FROM_DOCUMENT]->(rd:Document)
RETURN r.name AS risk, collect(DISTINCT c1.ticker) + collect(DISTINCT c2.ticker) AS tickers,
       collect(DISTINCT {chunk_id: rd.ticker + '-g' + toString(rc.index), ticker: rd.ticker,
                         text: rc.text})[0..3] AS evidence
"""

LINK_COMPANIES_CYPHER = """
MATCH (d:Document) WHERE d.ticker IS NOT NULL
MERGE (c:Company {ticker: d.ticker}) SET c.name = d.company, c.cik = d.cik
MERGE (c)-[:FILED]->(d)
WITH c, d
MATCH (d)<-[:FROM_DOCUMENT]-(:Chunk)<-[:FROM_CHUNK]-(r:RiskFactor)
MERGE (c)-[:FACES_RISK]->(r)
"""

SYSTEM = system_prompt(
    "You are a credit risk analyst. A knowledge graph lists risk factors that several companies share, each "
    "with source excerpts labelled [id] TICKER. Turn them into claims: quote each company's own excerpt."
)


def driver():
    if not config.NEO4J_PASSWORD:
        raise SystemExit("Set NEO4J_URI, NEO4J_USERNAME and NEO4J_PASSWORD (see .env.sample).")
    return GraphDatabase.driver(config.NEO4J_URI, auth=(config.NEO4J_USERNAME, config.NEO4J_PASSWORD))


def _count(drv, query="MATCH (n) RETURN count(n) AS n"):
    return drv.execute_query(query, database_=config.NEO4J_DATABASE).records[0]["n"]


def build(reset=False, record=True):
    """Build the graph. record=False (reruns, restores) keeps results/graph_build_<corpus>.json as it is."""
    from neo4j_graphrag.components.resolver import FuzzyMatchResolver
    from neo4j_graphrag.components.text_splitters.fixed_size_splitter import FixedSizeSplitter
    from neo4j_graphrag.experimental.pipeline.kg_builder import SimpleKGPipeline
    from neo4j_graphrag.generation.prompts import ERExtractionTemplate
    from neo4j_graphrag.indexes import create_vector_index

    filings = load_corpus()
    drv = driver()
    existing = _count(drv)
    if existing and not reset:
        raise SystemExit(f"Database already has {existing} nodes. Re-run with --reset to DELETE ALL nodes "
                         f"in {config.NEO4J_URI} ({config.NEO4J_DATABASE}) and rebuild.")
    if existing:
        print(f"--reset: deleting all {existing} nodes")
        with drv.session(database=config.NEO4J_DATABASE) as session:  # IN TRANSACTIONS needs auto-commit
            session.run("MATCH (n) CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 5000 ROWS").consume()
    drv.execute_query("DROP INDEX chunkEmbeddings IF EXISTS", database_=config.NEO4J_DATABASE)  # dims may change

    with llm.METER.track("graph.build"):
        graph_llm, embedder = llm.graphrag_adapters()
        pipeline = SimpleKGPipeline(
            llm=graph_llm, driver=drv, embedder=embedder, schema=SCHEMA, from_file=False,
            neo4j_database=config.NEO4J_DATABASE, on_error="IGNORE",
            text_splitter=FixedSizeSplitter(chunk_size=config.GRAPH_CHUNK_CHARS,
                                            chunk_overlap=config.GRAPH_CHUNK_OVERLAP),
            prompt_template=ERExtractionTemplate(
                template=EXTRACTION_INSTRUCTION + ERExtractionTemplate.DEFAULT_TEMPLATE),
            perform_entity_resolution=True,  # exact-name merge, as in the workshop
        )
        for f in filings:
            print(f"  {f['ticker']}: {len(f['text']):,} chars")
            meta = {k: f[k] for k in ("ticker", "company", "cik", "accession", "url")}
            asyncio.run(pipeline.run_async(text=f["text"], document_metadata=meta))

        exact = _count(drv, "MATCH (r:RiskFactor) RETURN count(r) AS n")  # after exact-name resolution
        resolved = exact
        if config.GRAPH_RESOLVER == "fuzzy":
            asyncio.run(FuzzyMatchResolver(drv, neo4j_database=config.NEO4J_DATABASE).run())
            resolved = _count(drv, "MATCH (r:RiskFactor) RETURN count(r) AS n")
            print(f"  fuzzy resolution: {exact} -> {resolved} RiskFactor nodes")
        drv.execute_query(LINK_COMPANIES_CYPHER, database_=config.NEO4J_DATABASE)
        create_vector_index(drv, name="chunkEmbeddings", label="Chunk", embedding_property="embedding",
                            dimensions=config.EMBED_DIMENSIONS, similarity_fn="cosine",
                            neo4j_database=config.NEO4J_DATABASE)

    stats = graph_stats(drv)
    if not record:
        drv.close()
        return stats
    record = {"corpus": config.CORPUS, "model": config.LLM_MODEL, "resolver": config.GRAPH_RESOLVER,
              "chunk_chars": config.GRAPH_CHUNK_CHARS, "usage": llm.METER.summary("graph.build"), "graph": stats,
              "risk_factors_exact": exact, "risk_factors_resolved": resolved}
    config.RESULTS_DIR.mkdir(exist_ok=True)
    (config.RESULTS_DIR / f"graph_build_{config.CORPUS}.json").write_text(json.dumps(record, indent=2))
    print(json.dumps(record, indent=2))
    drv.close()


def graph_stats(drv):
    q = {"companies": "MATCH (n:Company) RETURN count(n) AS n",
         "chunks": "MATCH (n:Chunk) RETURN count(n) AS n",
         "risk_factors": "MATCH (n:RiskFactor) RETURN count(n) AS n",
         "faces_risk": "MATCH ()-[r:FACES_RISK]->() RETURN count(r) AS n",
         "risk_factors_shared": "MATCH (c:Company)-[:FACES_RISK]->(r:RiskFactor) WITH r, count(DISTINCT c) AS k "
                                "WHERE k >= 2 RETURN count(r) AS n"}
    return {k: _count(drv, v) for k, v in q.items()}


def _traverse(drv, question):
    if config.GRAPH_MODE == "vector_seeded":
        from neo4j_graphrag.retrievers import VectorCypherRetriever

        _, embedder = llm.graphrag_adapters()
        retriever = VectorCypherRetriever(drv, index_name="chunkEmbeddings", embedder=embedder,
                                          retrieval_query=VECTOR_SEEDED_CYPHER,
                                          neo4j_database=config.NEO4J_DATABASE)
        records = retriever.get_search_results(query_text=question, top_k=config.RAG_TOP_K).records
        merged = {}
        for rec in records:
            row = merged.setdefault(rec["risk"], {"risk": rec["risk"], "tickers": set(), "evidence": []})
            row["tickers"] |= set(rec["tickers"])
            row["evidence"] += rec["evidence"]
        return [dict(r, tickers=sorted(r["tickers"])) for r in merged.values()]
    return [dict(rec) for rec in drv.execute_query(SHARED_RISKS_CYPHER, min_shared=config.MIN_SHARED, limit=40,
                                                   database_=config.NEO4J_DATABASE).records]


def run(question, filings):
    drv = driver()
    if _count(drv, "MATCH (r:RiskFactor) RETURN count(r) AS n") == 0:
        raise SystemExit("Graph is empty: run `python src/approach2_graphrag.py build --reset` first.")
    with llm.METER.track("graph.ask"):
        rows = _traverse(drv, question)
        # Each evidence chunk once, under its graph chunk id (e.g. NVDA-g7); risks refer to the ids.
        sources, lines = {}, []
        for row in rows:
            ids = []
            for e in row["evidence"]:
                if e["chunk_id"] not in sources:
                    sources[e["chunk_id"]] = e["text"]
                    lines.append(f"[{e['chunk_id']}] {e['ticker']}\n{e['text']}\n")
                ids.append(e["chunk_id"])
            lines.append(f"RISK '{row['risk']}' shared by {', '.join(row['tickers'])}; evidence {', '.join(ids)}\n")
        context = "\n".join(lines) if rows else "(the traversal found no shared risk factors)"
        reply = llm.chat(SYSTEM, f"Question: {question}\n\nGraph results:\n{context}",
                         schema=CLAIMS_SCHEMA, schema_name="claims")
    stats = graph_stats(drv)
    drv.close()
    return {
        "approach": "2_graphrag",
        "summary": reply["summary"],
        "raw_claims": reply["claims"],
        "sources": sources,
        "stages": {"build": "graph.build", "ask": "graph.ask"},
        "details": {"mode": config.GRAPH_MODE, "traversal_rows": len(rows), "graph": stats,
                    "evidence_chunks": len(sources),
                    "traversal": [{"risk": r["risk"], "tickers": r["tickers"]} for r in rows]},
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["build", "ask", "stats"])
    parser.add_argument("--reset", action="store_true", help="delete ALL nodes in the target database first")
    args = parser.parse_args()
    if args.command == "build":
        build(args.reset)
    elif args.command == "stats":
        print(json.dumps(graph_stats(driver()), indent=2))
    else:
        result = run(config.QUESTION, load_corpus())
        print(json.dumps({k: result[k] for k in ("summary", "raw_claims")}, indent=2))
