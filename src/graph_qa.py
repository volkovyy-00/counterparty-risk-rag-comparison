"""Approach 2, screen 4: "ask the graph". Fixed questions, each a fixed read-only Cypher template.

    python src/graph_qa.py                      # builds every prompt from the graph in Neo4j, prints the estimate, STOPS
    python src/graph_qa.py --confirm-usd 1      # answers the questions -> results/demo_run/graph_qa.json

The graph shown on the page for a question is exactly the rows its query returned. The model writes the answer
from those rows only, and every claim goes through the shared verifier. A query that returns no rows is recorded as
empty and gets no model call: the graph does not invent a link. There is no free-text question anywhere.
Needs a filled graph-v2 database (the real run calls this right after export_graph.py).
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path

from neo4j import RoutingControl

import config
import llm
from answer import CLAIMS_SCHEMA, system_prompt
from corpus import load_corpus
from verify import verify_claims

_EVIDENCE = "{ticker: c.ticker, quotes: f.quotes[0..2], spans: f.spans[0..2], chunk_ids: f.chunk_ids[0..2]}"

TEMPLATES = {
    "SHARED_AMONG": f"""
MATCH (c:Company)-[f:FACES_RISK]->(r:RiskFactor)
WHERE c.ticker IN $tickers
WITH r, collect({_EVIDENCE}) AS evidence
WHERE size(evidence) >= $min_shared
RETURN r.id AS id, r.name AS risk, r.definition AS definition, coalesce(r.generic, false) AS generic,
       r.n_companies AS n_companies, 'shared' AS role, evidence
ORDER BY size(evidence) DESC, generic, r.n_companies, risk
LIMIT $limit""",
    "SHARED_VS_SPECIFIC": f"""
CALL () {{
  MATCH (c:Company)-[:FACES_RISK]->(r:RiskFactor)
  WITH r, count(DISTINCT c) AS n
  ORDER BY n DESC, coalesce(r.boilerplate_share, 0) DESC, r.name LIMIT 1
  RETURN r, 'most shared' AS role
  UNION
  MATCH (c:Company)-[:FACES_RISK]->(r:RiskFactor)
  WHERE NOT coalesce(r.generic, false)
  WITH r, count(DISTINCT c) AS n, collect(DISTINCT c.industry) AS inds
  WHERE n >= $min_shared AND all(i IN $industries WHERE i IN inds)
  WITH r, n ORDER BY n DESC, coalesce(r.boilerplate_share, 0), r.name LIMIT 1
  RETURN r, 'most specific' AS role
}}
MATCH (c:Company)-[f:FACES_RISK]->(r)
WITH r, role, collect({_EVIDENCE}) AS evidence
RETURN r.id AS id, r.name AS risk, r.definition AS definition, coalesce(r.generic, false) AS generic,
       r.n_companies AS n_companies, role, evidence
ORDER BY role""",
    "BRIDGE_DRIVERS": """
MATCH (c:Company)-[:DISCLOSES]->(x:RiskMention)-[:INVOLVES]->(d:ExposureDriver)
WHERE d.type IN $driver_types
MATCH (x)-[:INSTANCE_OF]->(r:RiskFactor)
WITH d, collect(DISTINCT c.industry) AS inds, collect(DISTINCT c.ticker) AS tickers,
     collect({ticker: c.ticker, risk: r.name, quote: x.quote, span: toString(x.start) + ':' + toString(x.end),
              chunk_id: x.chunk_id}) AS uses
WHERE size(tickers) >= $min_shared AND all(i IN $industries WHERE i IN inds)
RETURN d.id AS id, d.name AS driver, d.type AS type, tickers, uses
ORDER BY CASE d.type WHEN 'INPUT_COMMODITY' THEN 0 WHEN 'NAMED_COUNTERPARTY' THEN 1
         WHEN 'REGULATION_POLICY' THEN 2 ELSE 3 END, size(tickers) DESC, driver
LIMIT $limit""",
}

INDUSTRIES = ["auto", "semis"]
# "Which named place, input or policy": end markets ("Automotive") would link autos to chips by definition.
BRIDGE_TYPES = ["INPUT_COMMODITY", "NAMED_COUNTERPARTY", "REGULATION_POLICY", "GEOGRAPHY"]

# stage=True: the three chips used live in the talk, in this order; the others are for Q&A.
QUESTIONS = [
    {"id": "gm_nxpi", "label": "GM + NXPI", "stage": True, "template": "SHARED_AMONG",
     "question": "Which risks do GM and NXP Semiconductors both disclose?",
     "params": {"tickers": ["GM", "NXPI"], "min_shared": 2, "limit": 8}},
    {"id": "shared_vs_specific", "label": "Most shared vs most specific", "stage": True,
     "template": "SHARED_VS_SPECIFIC",
     "question": "What is the risk most widely shared across all ten companies, and what is the most widely shared "
                 "specific risk linking autos and semis?",
     "params": {"min_shared": 2, "industries": INDUSTRIES}},
    {"id": "bridge", "label": "What links autos to chips?", "stage": True, "template": "BRIDGE_DRIVERS",
     "question": "Which named place, input or policy links the automakers' risks to the chipmakers' risks?",
     "params": {"driver_types": BRIDGE_TYPES, "industries": INDUSTRIES, "min_shared": 2, "limit": 5}},
    {"id": "tsla_on_txn", "label": "TSLA + ON + TXN", "stage": False, "template": "SHARED_AMONG",
     "question": "Which risks do Tesla, onsemi and Texas Instruments share?",
     "params": {"tickers": ["TSLA", "ON", "TXN"], "min_shared": 2, "limit": 8}},
    {"id": "five", "label": "F, BWA, LEA, MCHP, ON", "stage": False, "template": "SHARED_AMONG",
     "question": "Which risks do Ford, BorgWarner, Lear, Microchip and onsemi share?",
     "params": {"tickers": ["F", "BWA", "LEA", "MCHP", "ON"], "min_shared": 3, "limit": 8}},
]

SYSTEM = system_prompt(
    "You are a credit risk analyst. A fixed, read-only Cypher query on a knowledge graph of 10-K risk factors "
    "returned the rows below, each with source excerpts labelled [id] TICKER. Answer the question from these rows "
    "only; if they do not answer it, say so. Quote each company's own excerpt."
)
ASSUME_OUT = 2500  # output tokens per answer, assumed (stated, not measured)


def prompt_sha256():
    text = SYSTEM + json.dumps(TEMPLATES, sort_keys=True) + json.dumps(QUESTIONS, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()


def query(drv, q):
    """Run a question's template in a READ transaction (Neo4j refuses writes in read mode)."""
    return [dict(r) for r in drv.execute_query(TEMPLATES[q["template"]], q["params"], routing_=RoutingControl.READ,
                                               database_=config.NEO4J_DATABASE).records]


def _evidence(row):
    """Driver rows carry `uses` (one per mention); risk rows carry `evidence` (parallel lists per company)."""
    if "uses" in row:
        return [dict(u) for u in row["uses"]]
    return [{"ticker": e["ticker"], "risk": row["risk"], "quote": qt, "span": sp, "chunk_id": ch}
            for e in row["evidence"] for qt, sp, ch in zip(e["quotes"], e["spans"], e["chunk_ids"])]


def to_subgraph(rows, filings):
    """{nodes, edges, drivers, driver_edges} in export_graph.export_v2's shape, holding only what `rows` returned."""
    names = {f["ticker"]: f["company"] for f in filings}
    nodes, edges, drivers, driver_edges, seen = [], [], [], [], set()
    for row in rows:
        ev = _evidence(row)
        by_t = {}
        for e in ev:
            s, t = (int(x) for x in e["span"].split(":"))
            by_t.setdefault(e["ticker"], []).append({"text": e["quote"], "start": s, "end": t,
                                                     "chunk_id": e["chunk_id"], "risk_name": e["risk"]})
        industries = sorted({config.INDUSTRY.get(t, "other") for t in by_t})
        driver = "driver" in row
        nid = ("d:" if driver else "r:") + row["id"]
        node = {"id": nid, "label": row["driver"] if driver else row["risk"], "degree": len(by_t),
                "industries": industries}
        if driver:
            drivers.append(dict(node, type="ExposureDriver", driver_type=row["type"]))
        else:
            nodes.append(dict(node, type="RiskFactor", generic=row["generic"], definition=row.get("definition") or "",
                              n_companies=row["n_companies"], role=row["role"]))
        out = driver_edges if driver else edges
        for t, qs in sorted(by_t.items()):
            out.append({"source": f"c:{t}", "target": nid, "quotes": sorted(qs, key=lambda q: q["start"])[:3]})
            seen.add(t)
    companies = [{"id": f"c:{t}", "type": "Company", "label": t, "name": names.get(t, t),
                  "industry": config.INDUSTRY.get(t, "other")} for t in sorted(seen)]
    return {"nodes": companies + nodes, "edges": edges, "drivers": drivers, "driver_edges": driver_edges}


def prompt(q, rows, filings):
    """(user prompt, sources) for one question, cited the same way as the approach-2 ask."""
    from approach2_graphrag import Citer

    citer, lines = Citer(filings), []
    for row in rows:
        ev = _evidence(row)
        first = {}
        for e in ev:  # one paragraph per company per row; further quotes as bare quotes
            first.setdefault(e["ticker"], e)
        ids = [citer.cite(e, whole_paragraph=first[e["ticker"]] is e) for e in ev]
        ids = list(dict.fromkeys(ids))
        if "driver" in row:
            uses = "; ".join(sorted({f"{e['risk']} ({e['ticker']})" for e in ev}))
            lines.append(f"DRIVER '{row['driver']}' ({row['type']}) named by {', '.join(sorted(row['tickers']))}: "
                         f"{uses}; evidence {', '.join(ids)}")
        else:
            tickers = sorted({e["ticker"] for e in ev})
            tag = f" [{row['role']}]" if row["role"] != "shared" else ""
            gen = " (generic)" if row["generic"] else ""
            lines.append(f"RISK '{row['risk']}'{tag}{gen} disclosed by {', '.join(tickers)} "
                         f"({row['n_companies']} companies in the group); evidence {', '.join(ids)}")
    context = "\n".join(citer.blocks) + "\n" + "\n".join(lines)
    return f"Question: {q['question']}\n\nQuery rows:\n{context}", citer.sources


def answer(q, rows, filings):
    """The model's answer to one question from its rows, verified. No rows -> no call."""
    if not rows:
        return {"empty": True, "summary": "No link found: the query returned no rows, and the graph does not "
                                          "invent one.", "claims": [], "rejected": [], "verification": None}
    user, sources = prompt(q, rows, filings)
    with llm.METER.track("graph.qa"):
        reply = llm.chat(SYSTEM, user, schema=CLAIMS_SCHEMA, schema_name="claims", model=config.GRAPH_QA_MODEL,
                         effort=config.GRAPH_QA_EFFORT)
    accepted, rejected, stats = verify_claims(reply["claims"], filings, sources)
    return {"empty": False, "summary": reply["summary"], "claims": accepted, "rejected": rejected,
            "verification": stats}


def estimate(drv, filings, measure=True):
    """Builds every prompt from the graph (no model call). Input tokens measured when a key is set."""
    from estimate_cost import _row, _tokens

    tok_in, calls, measured = 0, 0, True
    for q in QUESTIONS:
        rows = query(drv, q)
        if rows:
            n, m = _tokens(SYSTEM, prompt(q, rows, filings)[0], measure, config.GRAPH_QA_MODEL)
            tok_in, calls, measured = tok_in + n, calls + 1, measured and m
    row = _row("2 graph QA", calls, tok_in, calls * ASSUME_OUT, model=config.GRAPH_QA_MODEL)
    return dict(row, measured=measured)


def run(out=None, filings=None):
    from approach2_graphrag import driver

    filings = filings or load_corpus()
    out = Path(out or config.RESULTS_DIR / "demo_run" / "graph_qa.json")
    drv = driver()
    items = []
    for q in QUESTIONS:
        rows = query(drv, q)
        before = llm.METER.summary("graph.qa")
        result = answer(q, rows, filings)
        after = llm.METER.summary("graph.qa")
        usage = {k: round(after.get(k, 0) - before.get(k, 0), 6) for k in after}
        items.append({**{k: q[k] for k in ("id", "label", "question", "stage", "template", "params")},
                      "cypher": TEMPLATES[q["template"]].strip(), "rows": len(rows),
                      "subgraph": to_subgraph(rows, filings), **result, "usage": usage})
        v = result["verification"]
        print(f"  {q['id']}: {len(rows)} rows" + (f", {v['accepted']}/{v['claims']} claims verified" if v
                                                     else " - empty, no model call"))
    drv.close()
    data = {"questions": items,
            "build": {"model": config.GRAPH_QA_MODEL, "effort": config.GRAPH_QA_EFFORT,
                      "prompt_sha256": prompt_sha256(),
                      "graph_prompt_version": config.GRAPH_PROMPT_VERSION,
                      "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                      "usage": llm.METER.summary("graph.qa")}}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1))
    print(f"{len(items)} questions -> {config.rel(out)}")
    return data


def main():
    from approach2_graphrag import driver

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--confirm-usd", type=float, default=0.0)
    parser.add_argument("--out", help="default results/demo_run/graph_qa.json")
    args = parser.parse_args()
    filings = load_corpus()
    measure = bool(config.env("ANTHROPIC_API_KEY")) and config.LLM_PROVIDER == "anthropic"
    drv = driver()
    est = estimate(drv, filings, measure)
    drv.close()
    how = "measured" if est["measured"] else "estimated as characters / 4"
    print(f"Graph QA estimate ({config.GRAPH_QA_MODEL}, effort {config.GRAPH_QA_EFFORT}): {est['calls']} calls, "
          f"{est['input_tokens']:,} input tokens "
          f"({how}), {est['output_tokens']:,} output tokens (assumed) = ${est['cost_usd'] or 0:.2f}")
    if (est["cost_usd"] or 0) > args.confirm_usd:
        raise SystemExit(f"Nothing was spent. Re-run with --confirm-usd N (N >= {est['cost_usd'] or 0:.2f}).")
    run(args.out, filings)


if __name__ == "__main__":
    main()
