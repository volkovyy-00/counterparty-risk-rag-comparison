"""Approach 2 - GraphRAG with Neo4j. Two prompt versions (GRAPH_PROMPT_VERSION):

    python src/approach2_graphrag.py build --reset   # once, before the demo (LLM-heavy)
    python src/approach2_graphrag.py ask             # what the runner calls

graph-v1-workshop - the workshop's SimpleKGPipeline pattern, kept unchanged as the A/B baseline:
    (Company)-[:FACES_RISK]->(RiskFactor)-[:FROM_CHUNK]->(Chunk)-[:FROM_DOCUMENT]->(Document)
graph-v2 (default) - own extractor (graph_v2.py) and resolver (graph_resolve.py):
    (Company)-[:FILED]->(Document)<-[:FROM_DOCUMENT]-(Chunk)
    (Company)-[:DISCLOSES]->(RiskMention)-[:FROM_CHUNK]->(Chunk)
    (RiskMention)-[:INSTANCE_OF]->(RiskFactor)    (RiskMention)-[:INVOLVES]->(ExposureDriver)
    (Company)-[:FACES_RISK {quotes, spans, chunk_ids, mentions}]->(RiskFactor)   derived, keeps old queries working
Chunks are cited as TICKER-g<index>, e.g. NVDA-g7.

Design choice (both versions): which company faces a risk is taken from provenance (the 10-K it was
extracted from), not from the LLM - in Item 1A the filer is always the company at risk.
"""
import argparse
import asyncio
import hashlib
import json
import logging

from neo4j import GraphDatabase

import config
import llm
from answer import CLAIMS_SCHEMA, system_prompt
from corpus import load_corpus
from verify import locate

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

# ---- graph-v2 load and ask (plain parameterised Cypher)
V2_LOAD = [
    """UNWIND $docs AS d
       MERGE (doc:Document {ticker: d.ticker}) SET doc += d
       MERGE (c:Company {ticker: d.ticker}) SET c.name = d.company, c.cik = d.cik, c.industry = d.industry
       MERGE (c)-[:FILED]->(doc)""",
    """UNWIND $chunks AS ch
       MATCH (doc:Document {ticker: ch.ticker})
       MERGE (c:Chunk {id: ch.id})
       SET c.index = ch.index, c.text = ch.text, c.start = ch.start, c.end = ch.end, c.heading = ch.heading,
           c.ticker = ch.ticker, c.embedding = ch.embedding
       MERGE (c)-[:FROM_DOCUMENT]->(doc)""",
    """UNWIND $risk_factors AS r
       MERGE (n:RiskFactor {id: r.id})
       SET n.name = r.name, n.definition = r.definition, n.aliases = r.aliases, n.n_companies = r.n_companies,
           n.industries = r.industries, n.generic = r.generic, n.idf = r.idf, n.boilerplate_share = r.boilerplate_share""",
    """UNWIND $drivers AS d
       MERGE (n:ExposureDriver {id: d.id}) SET n.name = d.name, n.type = d.type, n.aliases = d.aliases""",
    """UNWIND $mentions AS m
       MATCH (c:Company {ticker: m.ticker}) MATCH (ch:Chunk {id: m.chunk_id}) MATCH (r:RiskFactor {id: m.rf_id})
       CREATE (x:RiskMention {id: m.id, ticker: m.ticker, heading: m.heading, risk_name: m.risk_name,
               detail: m.detail, quote: m.quote, start: m.start, end: m.end, specificity: m.specificity,
               chunk_id: m.chunk_id, prompt_version: m.prompt_version})
       CREATE (c)-[:DISCLOSES]->(x) CREATE (x)-[:FROM_CHUNK]->(ch) CREATE (x)-[:INSTANCE_OF]->(r)
       MERGE (r)-[:FROM_CHUNK]->(ch)
       WITH x, m UNWIND m.driver_ids AS did
       MATCH (d:ExposureDriver {id: did}) CREATE (x)-[:INVOLVES]->(d)""",
    """MATCH (c:Company)-[:DISCLOSES]->(x:RiskMention)-[:INSTANCE_OF]->(r:RiskFactor)
       WITH c, r, x ORDER BY x.start
       WITH c, r, collect(x) AS xs
       MERGE (c)-[f:FACES_RISK]->(r)
       SET f.quotes = [x IN xs | x.quote], f.spans = [x IN xs | toString(x.start) + ':' + toString(x.end)],
           f.chunk_ids = [x IN xs | x.chunk_id], f.mentions = size(xs)""",
]

SHARED_RISKS_V2_CYPHER = """
MATCH (c:Company)-[f:FACES_RISK]->(r:RiskFactor)
WITH r, collect({ticker: c.ticker, quote: f.quotes[0], span: f.spans[0], chunk_id: f.chunk_ids[0]}) AS evidence
WHERE size(evidence) >= $min_shared
RETURN r.name AS risk, coalesce(r.generic, false) AS generic, coalesce(r.idf, 0.0) AS idf, evidence
"""

SHARED_DRIVERS_CYPHER = """
MATCH (c:Company)-[:DISCLOSES]->(x:RiskMention)-[:INVOLVES]->(d:ExposureDriver)
MATCH (x)-[:INSTANCE_OF]->(r:RiskFactor)
WITH d, collect(DISTINCT c.ticker) AS tickers, collect(DISTINCT {ticker: c.ticker, risk: r.name}) AS uses
WHERE size(tickers) >= $min_shared
RETURN d.name AS driver, d.type AS type, tickers, uses
ORDER BY size(tickers) DESC, driver
LIMIT 25
"""

# The workshop's vector-seeded pattern on the v2 schema: chunk hits -> mentions -> risk factors -> companies.
VECTOR_SEEDED_V2_CYPHER = """
WITH node
MATCH (node)<-[:FROM_CHUNK]-(:RiskMention)-[:INSTANCE_OF]->(r:RiskFactor)
MATCH (c:Company)-[f:FACES_RISK]->(r)
WITH r, collect({ticker: c.ticker, quote: f.quotes[0], span: f.spans[0], chunk_id: f.chunk_ids[0]}) AS evidence
RETURN r.name AS risk, coalesce(r.generic, false) AS generic, coalesce(r.idf, 0.0) AS idf, evidence
"""

MAX_SPECIFIC, MAX_GENERIC = 30, 10

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


def prompt_sha256(version=None):
    """SHA-256 of what steers graph extraction for a prompt version (recorded in the build file)."""
    if (version or config.GRAPH_PROMPT_VERSION) == "graph-v1-workshop":
        from neo4j_graphrag.generation.prompts import ERExtractionTemplate

        text = EXTRACTION_INSTRUCTION + ERExtractionTemplate.DEFAULT_TEMPLATE + json.dumps(SCHEMA, sort_keys=True)
    else:
        import graph_resolve
        import graph_v2

        text = (graph_v2.SYSTEM_V2 + json.dumps(graph_v2.MENTIONS_SCHEMA, sort_keys=True) + graph_resolve.RESOLVE_SYSTEM
                + graph_resolve.DRIVER_SYSTEM)
    return hashlib.sha256(text.encode()).hexdigest()


def _reset(drv, reset):
    existing = _count(drv)
    if existing and not reset:
        raise SystemExit(f"Database already has {existing} nodes. Re-run with --reset to DELETE ALL nodes "
                         f"in {config.NEO4J_URI} ({config.NEO4J_DATABASE}) and rebuild.")
    if existing:
        print(f"--reset: deleting all {existing} nodes")
        with drv.session(database=config.NEO4J_DATABASE) as session:  # IN TRANSACTIONS needs auto-commit
            session.run("MATCH (n) CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 5000 ROWS").consume()
    drv.execute_query("DROP INDEX chunkEmbeddings IF EXISTS", database_=config.NEO4J_DATABASE)  # dims may change


def snapshot_path(version=None):
    return config.RESULTS_DIR / f"graph_snapshot_{config.CORPUS}_{version or config.GRAPH_PROMPT_VERSION}.json"


def build(reset=False, record=True, filings=None):
    """Build the graph. record=False (reruns, restores) keeps results/graph_build_<corpus>.json as it is."""
    filings = filings if filings is not None else load_corpus()
    drv = driver()
    _reset(drv, reset)
    if config.GRAPH_PROMPT_VERSION == "graph-v1-workshop":
        extra = _build_v1(drv, filings)
    else:
        extra = _build_v2(drv, filings)
    from neo4j_graphrag.indexes import create_vector_index

    create_vector_index(drv, name="chunkEmbeddings", label="Chunk", embedding_property="embedding",
                        dimensions=config.EMBED_DIMENSIONS, similarity_fn="cosine",
                        neo4j_database=config.NEO4J_DATABASE)
    stats = graph_stats(drv)
    drv.close()
    if not record:
        return stats
    record = {"corpus": config.CORPUS, "model": config.LLM_MODEL, "prompt_version": config.GRAPH_PROMPT_VERSION,
              "prompt_sha256": prompt_sha256(), "resolver": config.GRAPH_RESOLVER,
              "chunk_chars": config.GRAPH_CHUNK_CHARS if config.GRAPH_PROMPT_VERSION == "graph-v1-workshop"
              else config.GRAPH_V2_CHUNK_CHARS,
              "tickers": [f["ticker"] for f in filings],
              "usage": llm.METER.summary("graph.build", "graph.resolve"),
              "usage_by_stage": {s: llm.METER.summary(s) for s in ("graph.build", "graph.resolve")},
              "graph": stats, **extra}
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (config.RESULTS_DIR / f"graph_build_{config.CORPUS}.json").write_text(json.dumps(record, indent=2))
    print(json.dumps({k: v for k, v in record.items() if not k.startswith("risk_factor_names")}, indent=2))
    return stats


def _build_v1(drv, filings):
    """graph-v1-workshop: SimpleKGPipeline with the workshop-style prompt, exact then fuzzy resolution."""
    from neo4j_graphrag.components.resolver import FuzzyMatchResolver
    from neo4j_graphrag.components.text_splitters.fixed_size_splitter import FixedSizeSplitter
    from neo4j_graphrag.experimental.pipeline.kg_builder import SimpleKGPipeline
    from neo4j_graphrag.generation.prompts import ERExtractionTemplate

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
        exact_names = [dict(r) for r in drv.execute_query(
            "MATCH (d:Document)<-[:FROM_DOCUMENT]-(:Chunk)<-[:FROM_CHUNK]-(r:RiskFactor) "
            "RETURN r.name AS name, collect(DISTINCT d.ticker) AS tickers ORDER BY name",
            database_=config.NEO4J_DATABASE).records]
        resolved = exact
        if config.GRAPH_RESOLVER == "fuzzy":
            asyncio.run(FuzzyMatchResolver(drv, neo4j_database=config.NEO4J_DATABASE).run())
            resolved = _count(drv, "MATCH (r:RiskFactor) RETURN count(r) AS n")
            print(f"  fuzzy resolution: {exact} -> {resolved} RiskFactor nodes")
        drv.execute_query(LINK_COMPANIES_CYPHER, database_=config.NEO4J_DATABASE)

    names = [dict(r) for r in drv.execute_query(
        "MATCH (c:Company)-[:FACES_RISK]->(r:RiskFactor) RETURN r.name AS name, collect(DISTINCT c.ticker) AS tickers "
        "ORDER BY name", database_=config.NEO4J_DATABASE).records]
    return {"risk_factors_exact": exact, "risk_factors_resolved": resolved, "risk_factor_names": names,
            "risk_factor_names_exact": exact_names}


def _build_v2(drv, filings):
    """graph-v2: paragraph chunks -> verified mentions -> resolution -> plain Cypher load."""
    import graph_resolve
    import graph_v2

    with llm.METER.track("graph.build"):
        chunks, accepted, rejected = graph_v2.run(filings)
        vectors = llm.embed([c["text"] for c in chunks])
    with llm.METER.track("graph.resolve"):
        snap = graph_resolve.resolve(accepted, filings)
    snap.update({"prompt_version": graph_v2.PROMPT_VERSION, "resolver": config.GRAPH_RESOLVER,
                 "tickers": [f["ticker"] for f in filings],
                 "chunks": [{k: c[k] for k in ("id", "ticker", "index", "start", "end", "heading")} for c in chunks],
                 "rejected": len(rejected)})
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_path().write_text(json.dumps(snap, indent=1))

    by_ticker = {f["ticker"]: f for f in filings}
    params = {
        "docs": [{"ticker": f["ticker"], "company": f["company"], "cik": f.get("cik", ""), "accession": f["accession"],
                  "url": f.get("url", ""), "filed": f.get("filing_date", ""), "period": f.get("report_date", ""),
                  "industry": config.INDUSTRY.get(f["ticker"], "other")} for f in filings],
        "chunks": [dict(c, embedding=v) for c, v in zip(chunks, vectors)],
        "risk_factors": snap["risk_factors"], "drivers": snap["drivers"],
        "mentions": [{k: m.get(k) for k in ("id", "ticker", "heading", "risk_name", "detail", "quote", "start", "end",
                                            "specificity", "chunk_id", "prompt_version", "rf_id", "driver_ids")}
                     for m in snap["mentions"] if m["ticker"] in by_ticker],
    }
    for query in V2_LOAD:
        drv.execute_query(query, params, database_=config.NEO4J_DATABASE)
    a = snap["audit"]
    print(f"  resolution ({config.GRAPH_RESOLVER}): {a['mentions']} mentions -> {a['names_exact']} names -> "
          f"{a['risk_factors']} RiskFactors; {len(a['merges_approved'])} merges approved, "
          f"{len(a['merges_rejected'])} rejected")
    total = len(accepted) + len(rejected)
    return {"risk_factors_exact": a["names_exact"], "risk_factors_resolved": a["risk_factors"],
            "mentions": a["mentions"], "mentions_rejected": len(rejected),
            "verification_rate": round(len(accepted) / total, 4) if total else None,
            "merges_approved": len(a["merges_approved"]), "merges_rejected": len(a["merges_rejected"]),
            "drivers": len(snap["drivers"])}


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


def _rank_v2(rows):
    """Specific shared risks first: both industries present, then n_companies x idf, then name."""
    for r in rows:
        r["tickers"] = sorted({e["ticker"] for e in r["evidence"]})
        r["industries"] = sorted({config.INDUSTRY.get(t, "other") for t in r["tickers"]})
        r["cross_industry"] = {"auto", "semis"} <= set(r["industries"])
    key = lambda r: (not r["cross_industry"], -len(r["tickers"]) * r["idf"], r["risk"])  # noqa: E731
    specific = sorted((r for r in rows if not r["generic"]), key=key)[:MAX_SPECIFIC]
    generic = sorted((r for r in rows if r["generic"]), key=lambda r: (-len(r["tickers"]), r["risk"]))[:MAX_GENERIC]
    return specific, generic


def _paragraph(spans, text, start):
    """The paragraph (as cut by graph_v2.paragraphs, so never longer than a v2 chunk) containing `start`."""
    for s, e in spans:
        if s <= start < e:
            return text[s:e].strip()
    return text[max(0, start - 400):start + 400].strip()


def _run_v2(drv, question, filings):
    import graph_v2

    texts = {f["ticker"]: f["text"] for f in filings}
    spans = {t: graph_v2.paragraphs(text) for t, text in texts.items()}
    if config.GRAPH_MODE == "vector_seeded":
        from neo4j_graphrag.retrievers import VectorCypherRetriever

        _, embedder = llm.graphrag_adapters()
        retriever = VectorCypherRetriever(drv, index_name="chunkEmbeddings", embedder=embedder,
                                          retrieval_query=VECTOR_SEEDED_V2_CYPHER,
                                          neo4j_database=config.NEO4J_DATABASE)
        merged = {}
        for rec in retriever.get_search_results(query_text=question, top_k=config.RAG_TOP_K).records:
            merged.setdefault(rec["risk"], dict(rec))
        rows = [r for r in merged.values() if len({e["ticker"] for e in r["evidence"]}) >= config.MIN_SHARED]
    else:
        rows = [dict(r) for r in drv.execute_query(SHARED_RISKS_V2_CYPHER, min_shared=config.MIN_SHARED,
                                                   database_=config.NEO4J_DATABASE).records]
    specific, generic = _rank_v2(rows)
    drivers = [dict(r) for r in drv.execute_query(SHARED_DRIVERS_CYPHER, min_shared=config.MIN_SHARED,
                                                  database_=config.NEO4J_DATABASE).records]
    sources, blocks, lines = {}, [], []
    seen = set()

    def cite(e, whole_paragraph):
        start = int(e["span"].split(":")[0])
        body = _paragraph(spans[e["ticker"]], texts[e["ticker"]], start) if whole_paragraph else e["quote"]
        cited = sources.get(e["chunk_id"], "")
        if not whole_paragraph and cited and locate(body, cited):  # already in a cited paragraph
            return e["chunk_id"]
        if (e["chunk_id"], body) not in seen:
            seen.add((e["chunk_id"], body))
            sources[e["chunk_id"]] = (sources[e["chunk_id"]] + "\n\n" + body) if e["chunk_id"] in sources else body
            blocks.append(f"[{e['chunk_id']}] {e['ticker']}\n{body}\n")
        return e["chunk_id"]

    for r in specific:
        ids = [cite(e, True) for e in sorted(r["evidence"], key=lambda e: e["ticker"])]
        tag = " (autos and semis)" if r["cross_industry"] else ""
        lines.append(f"RISK '{r['risk']}' shared by {', '.join(r['tickers'])}{tag}; evidence {', '.join(ids)}")
    if generic:
        lines.append("\nALSO SHARED, GENERIC (faced by most companies or mostly boilerplate):")
        for r in generic:
            ids = [cite(e, False) for e in sorted(r["evidence"], key=lambda e: e["ticker"])]
            lines.append(f"RISK '{r['risk']}' shared by {', '.join(r['tickers'])} (generic); evidence {', '.join(ids)}")
    if drivers:
        lines.append("\nSHARED EXPOSURE DRIVERS (named in the filings):")
        for d in drivers:
            uses = "; ".join(f"{u['risk']} ({u['ticker']})" for u in sorted(d["uses"], key=lambda u: u["ticker"]))
            lines.append(f"DRIVER '{d['driver']}' ({d['type']}) shared by {', '.join(d['tickers'])}: {uses}")
    context = "\n".join(blocks) + "\n" + "\n".join(lines) if rows else "(the traversal found no shared risk factors)"
    reply = llm.chat(SYSTEM, f"Question: {question}\n\nGraph results:\n{context}",
                     schema=CLAIMS_SCHEMA, schema_name="claims")
    traversal = [{"risk": r["risk"], "tickers": r["tickers"], "generic": r["generic"],
                  "cross_industry": r["cross_industry"]} for r in specific + generic]
    return reply, sources, traversal, [{"driver": d["driver"], "type": d["type"], "tickers": d["tickers"]}
                                       for d in drivers]


def run(question, filings):
    drv = driver()
    if _count(drv, "MATCH (r:RiskFactor) RETURN count(r) AS n") == 0:
        raise SystemExit("Graph is empty: run `python src/approach2_graphrag.py build --reset` first.")
    if config.GRAPH_PROMPT_VERSION == "graph-v2":
        with llm.METER.track("graph.ask"):
            reply, sources, traversal, drivers = _run_v2(drv, question, filings)
        stats = graph_stats(drv)
        drv.close()
        return {"approach": "2_graphrag", "summary": reply["summary"], "raw_claims": reply["claims"],
                "sources": sources, "stages": {"build": "graph.build", "ask": "graph.ask"},
                "details": {"mode": config.GRAPH_MODE, "prompt_version": config.GRAPH_PROMPT_VERSION,
                            "traversal_rows": len(traversal), "graph": stats, "evidence_chunks": len(sources),
                            "traversal": traversal, "shared_drivers": drivers}}
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
    parser.add_argument("--tickers", help="build from this subset only, e.g. GM,NXPI,TXN (the graph A/B)")
    args = parser.parse_args()
    if args.command == "build":
        wanted = set(args.tickers.upper().split(",")) if args.tickers else None
        build(args.reset, filings=[f for f in load_corpus() if not wanted or f["ticker"] in wanted])
    elif args.command == "stats":
        print(json.dumps(graph_stats(driver()), indent=2))
    else:
        result = run(config.QUESTION, load_corpus())
        print(json.dumps({k: result[k] for k in ("summary", "raw_claims")}, indent=2))
