"""The screen-4 Cypher templates and the console's patterns (src/graph_patterns.py) evaluated in Python over the exported graph (results/demo_run/graph.json).

The stage laptop has no Neo4j. These functions return the same rows as graph_qa.TEMPLATES do in Neo4j (same
filters, same order, same limits), in the same row shape, so graph_qa.prompt / to_subgraph / answer work unchanged.
tests/test_console_api.py checks them against the rows recorded in results/demo_run/graph_qa.json.
BRIDGE_DRIVERS needs every mention's quote, which the export does not carry, so it is answered from the recording.
"""
import json
from pathlib import Path

import config

LOCAL_TEMPLATES = ("SHARED_AMONG", "SHARED_VS_SPECIFIC", "MOST_COMMON", "WHO_FACES", "COMPANY_RISKS", "COMPANY_PEERS", "UNIQUE_TO",
                   "CROSS_INDUSTRY", "INDUSTRY_ONLY")  # the last seven: src/graph_patterns.py


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


def _bp(n):
    return n.get("boilerplate_share") or 0


def _ranked(g, keep, key, role, limit=None):
    """Rows for every risk whose {ticker: edge} map passes keep(node, edges), sorted by key(node, edges)."""
    nodes, faces = {n["id"]: n for n in g["nodes"]}, _faces(g)
    got = sorted(((nodes[rid], es) for rid, es in faces.items() if keep(nodes[rid], es)), key=lambda x: key(*x))
    return [_row(n, es, role) for n, es in got[:limit]]


def most_common(g, industry=None, specific_only=False, limit=5):
    nodes, faces = {n["id"]: n for n in g["nodes"]}, _faces(g)
    got = []
    for rid, es in faces.items():
        es = {t: e for t, e in es.items() if industry is None or config.INDUSTRY.get(t) == industry}
        if es and not (specific_only and nodes[rid].get("generic")):
            got.append((nodes[rid], es))
    got.sort(key=lambda x: (-len(x[1]), -_bp(x[0]), x[0]["label"]))
    return [_row(n, es, "most common") for n, es in got[:limit]]


def who_faces(g, risks):
    want = set(risks)
    return _ranked(g, lambda n, es: n["label"] in want, lambda n, es: (-len(es), n["label"]), "asked about")


def company_risks(g, ticker, limit=8):
    """Specific risks first, then how many companies share each: the profile, with who else is linked."""
    return _ranked(g, lambda n, es: ticker in es, lambda n, es: (bool(n.get("generic")), -len(es), _bp(n), n["label"]),
                   "company profile", limit)


def company_peers(g, ticker, limit=6):
    return _ranked(g, lambda n, es: ticker in es and not n.get("generic") and len(es) >= 2,
                   lambda n, es: (-len(es), _bp(n), n["label"]), "shared with peers", limit)


def unique_to(g, ticker, limit=6):
    return _ranked(g, lambda n, es: set(es) == {ticker}, lambda n, es: (_bp(n), n["label"]), "only this company", limit)


def cross_industry(g, industries=("auto", "semis"), limit=6):
    inds = lambda es: {config.INDUSTRY.get(t, "other") for t in es}  # noqa: E731
    return _ranked(g, lambda n, es: not n.get("generic") and set(industries) <= inds(es),
                   lambda n, es: (-len(es), _bp(n), n["label"]), "both industries", limit)


def industry_only(g, industry, limit=6):
    return _ranked(g, lambda n, es: len(es) >= 2 and {config.INDUSTRY.get(t, "other") for t in es} == {industry},
                   lambda n, es: (-len(es), _bp(n), n["label"]), "one industry only", limit)


def rows_for(g, template, params):
    if template == "SHARED_AMONG":
        return shared_among(g, params["tickers"], params.get("min_shared", 2), params.get("limit", 8))
    if template == "SHARED_VS_SPECIFIC":
        return shared_vs_specific(g, params.get("min_shared", 2), params.get("industries", ("auto", "semis")))
    p = params
    if template == "MOST_COMMON":
        return most_common(g, p.get("industry"), p.get("specific_only", False), p.get("limit", 5))
    if template == "WHO_FACES":
        return who_faces(g, p["risks"])
    if template == "COMPANY_RISKS":
        return company_risks(g, p["ticker"], p.get("limit", 8))
    if template == "COMPANY_PEERS":
        return company_peers(g, p["ticker"], p.get("limit", 6))
    if template == "UNIQUE_TO":
        return unique_to(g, p["ticker"], p.get("limit", 6))
    if template == "CROSS_INDUSTRY":
        return cross_industry(g, p.get("industries", ("auto", "semis")), p.get("limit", 6))
    if template == "INDUSTRY_ONLY":
        return industry_only(g, p["industry"], p.get("limit", 6))
    raise ValueError(f"{template} is not evaluated locally")
