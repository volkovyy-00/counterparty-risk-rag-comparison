"""The screen-4 Cypher templates evaluated in Python over the exported graph (results/demo_run/graph.json).

The stage laptop has no Neo4j. These functions return the same rows as graph_qa.TEMPLATES do in Neo4j (same
filters, same order, same limits), in the same row shape, so graph_qa.prompt / to_subgraph / answer work unchanged.
tests/test_console_api.py checks them against the rows recorded in results/demo_run/graph_qa.json.
BRIDGE_DRIVERS needs every mention's quote, which the export does not carry, so it is answered from the recording.
"""
import json
from pathlib import Path

import config

LOCAL_TEMPLATES = ("SHARED_AMONG", "SHARED_VS_SPECIFIC")


def load(path=None):
    return json.loads(Path(path or config.RESULTS_DIR / "demo_run" / "graph.json").read_text())


def _faces(g):
    """{risk node id: {ticker: edge}} over FACES_RISK edges."""
    out = {}
    for e in g["edges"]:
        out.setdefault(e["target"], {})[e["source"][2:]] = e
    return out


def _row(node, edges, role, tickers=None):
    """One query row; quotes[0..2] in Cypher is the first two (the end is exclusive)."""
    ev = [{"ticker": t, "quotes": [q["text"] for q in e["quotes"][:2]],
           "spans": [f"{q['start']}:{q['end']}" for q in e["quotes"][:2]],
           "chunk_ids": [q["chunk_id"] for q in e["quotes"][:2]]}
          for t, e in sorted(edges.items()) if tickers is None or t in tickers]
    return {"id": node["id"][2:], "risk": node["label"], "definition": node.get("definition") or "",
            "generic": bool(node.get("generic")), "n_companies": node.get("degree"), "role": role, "evidence": ev}


def shared_among(g, tickers, min_shared=2, limit=8):
    nodes, faces, want = {n["id"]: n for n in g["nodes"]}, _faces(g), set(tickers)
    rows = [_row(nodes[rid], es, "shared", want) for rid, es in faces.items() if len(want & set(es)) >= min_shared]
    rows.sort(key=lambda r: (-len(r["evidence"]), r["generic"], r["n_companies"], r["risk"]))
    return rows[:limit]


def shared_vs_specific(g, min_shared=2, industries=("auto", "semis")):
    nodes, faces = {n["id"]: n for n in g["nodes"]}, _faces(g)
    risks = [(nodes[rid], es) for rid, es in faces.items()]
    bp = lambda n: n.get("boilerplate_share") or 0  # noqa: E731
    shared = sorted(risks, key=lambda x: (-len(x[1]), -bp(x[0]), x[0]["label"]))[:1]
    spans = [x for x in risks if not x[0].get("generic") and len(x[1]) >= min_shared
             and all(i in {config.INDUSTRY.get(t, "other") for t in x[1]} for i in industries)]
    specific = sorted(spans, key=lambda x: (-len(x[1]), bp(x[0]), x[0]["label"]))[:1]
    rows = [_row(n, es, "most shared") for n, es in shared] + [_row(n, es, "most specific") for n, es in specific]
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: r["role"]):  # UNION: one row per risk
        if r["id"] not in seen:
            seen.add(r["id"]), out.append(r)
    return out


def rows_for(g, template, params):
    if template == "SHARED_AMONG":
        return shared_among(g, params["tickers"], params.get("min_shared", 2), params.get("limit", 8))
    if template == "SHARED_VS_SPECIFIC":
        return shared_vs_specific(g, params.get("min_shared", 2), params.get("industries", ("auto", "semis")))
    raise ValueError(f"{template} is not evaluated locally")
