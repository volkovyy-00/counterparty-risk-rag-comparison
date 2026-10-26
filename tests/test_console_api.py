"""The console's live API (src/serve.py): streamed asks, graph templates without Neo4j, and every fallback.

Uses the frozen run in results/demo_run/ and the fake model (tests only). No network, no Neo4j, no spend.
"""
import json
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import config  # noqa: E402
import llm  # noqa: E402
from tests import fake_llm  # noqa: E402

RUN = ROOT / "results" / "demo_run"
pytestmark = pytest.mark.skipif(not (RUN / "graph_qa.json").exists(), reason="needs the frozen run")


def _strip_ids(sub):
    """Neo4j and the export number risk nodes differently; everything else must match."""
    ids = {n["id"]: n["label"] for n in sub["nodes"]}
    return json.dumps({"nodes": sorted((n["label"], n["type"], n.get("n_companies")) for n in sub["nodes"]),
                       "edges": sorted((e["source"], ids[e["target"]], json.dumps(e["quotes"])) for e in sub["edges"])})


def test_graph_templates_in_python_return_the_recorded_neo4j_rows():
    import graph_local
    import graph_qa
    from corpus import load_corpus

    g, filings = graph_local.load(RUN / "graph.json"), load_corpus()
    checked = 0
    for q in json.loads((RUN / "graph_qa.json").read_text())["questions"]:
        if q["template"] not in graph_local.LOCAL_TEMPLATES:
            continue
        rows = graph_local.rows_for(g, q["template"], q["params"])
        assert len(rows) == q["rows"], q["id"]
        assert _strip_ids(graph_qa.to_subgraph(rows, filings)) == _strip_ids(q["subgraph"]), q["id"]
        checked += 1
    assert checked >= 3


@pytest.fixture
def live(tmp_path, monkeypatch):
    import approach1_rag
    import graph_local
    import serve
    from corpus import load_corpus

    fake_llm.install(monkeypatch)
    monkeypatch.setattr(config, "LLM_CACHE", "off")
    lv = serve.Live(RUN, spend=serve.Spend(tmp_path / "spend.jsonl", cap=3))
    lv.filings = load_corpus()
    lv.index = approach1_rag.build(lv.filings)
    lv.graph = graph_local.load(RUN / "graph.json")
    return lv


def test_rag_stream_retrieves_then_answers_with_verified_claims(live):
    events = list(live.rag_stream("What does Tesla disclose about its battery cell suppliers?"))
    kinds = [e["type"] for e in events]
    assert kinds[0] == "stage" and "retrieved" in kinds and kinds[-1] == "result"
    got = next(e for e in events if e["type"] == "retrieved")
    assert got["top_k"] == len(got["retrieved"]) == config.RAG_TOP_K
    assert all(c["end"] > c["start"] for c in got["retrieved"])
    res = events[-1]["result"]
    assert res["verification"]["claims"] >= res["verification"]["accepted"]
    assert all(c["start"] is not None for c in res["claims"])  # every shown claim located in its filing


def test_rag_stream_falls_back_on_timeout_error_and_cap(live, monkeypatch, tmp_path):
    import serve

    monkeypatch.setattr(serve, "LIVE_TIMEOUT_S", 0.5)
    monkeypatch.setattr(llm, "_call_chat", lambda *a, **k: time.sleep(5))
    start = time.perf_counter()
    last = list(live.rag_stream("any question"))[-1]
    assert time.perf_counter() - start < 3 and last["type"] == "replay" and "no answer within" in last["note"]

    def boom(*a, **k):
        raise ConnectionError("no network")
    monkeypatch.setattr(llm, "_call_chat", boom)
    last = list(live.rag_stream("any question"))[-1]
    assert last["type"] == "replay" and "live call failed" in last["note"]

    live.spend = serve.Spend(tmp_path / "capped.jsonl", cap=0.01)
    events = list(live.rag_stream("any question"))
    assert events[-1]["type"] == "replay" and "cap" in events[-1]["note"]
    assert any(e["type"] == "retrieved" for e in events)  # retrieval is free and still shown


def test_graph_stream_routes_runs_and_verifies(live, monkeypatch):
    monkeypatch.setattr(live, "route", lambda q: ("SHARED_AMONG", {"tickers": ["GM", "NXPI"], "min_shared": 2,
                                                                   "limit": 8}, "two companies named"))
    events = list(live.graph_stream("Which risks do GM and NXP both disclose?"))
    plan = next(e for e in events if e["type"] == "plan")
    assert plan["template"] == "SHARED_AMONG" and plan["rows"] == 8 and "MATCH" in plan["cypher"]
    res = events[-1]
    assert res["type"] == "result" and res["routed"]["template"] == "SHARED_AMONG"
    assert {n["label"] for n in res["result"]["subgraph"]["nodes"] if n["type"] == "Company"} == {"GM", "NXPI"}


def test_graph_stream_replays_what_it_cannot_run_live(live, monkeypatch):
    assert list(live.graph_stream("x", "bridge"))[-1] == {
        "type": "replay", "note": "the bridge query needs every mention's quote; showing its recording", "closest": "bridge"}
    assert list(live.graph_stream("x", "main"))[-1]["closest"] == "main"
    monkeypatch.setattr(live, "route", lambda q: ("NONE", {}, "not about shared risks"))
    last = list(live.graph_stream("What is the weather in Prague?"))[-1]
    assert last["type"] == "replay" and "no fixed query" in last["note"]


def test_server_streams_replay_when_live_is_off():
    import serve

    server = serve.ThreadingHTTPServer(("127.0.0.1", 0), serve.make_handler(None))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        st = json.loads(urllib.request.urlopen(base + "/api/status").read())
        assert st["live"] is False and st["cap_usd"] == serve.LIVE_MAX_USD
        for path, body in (("/api/live_rag", {"question": "q"}), ("/api/graph_ask", {"question": "q", "qid": "gm_nxpi"})):
            req = urllib.request.Request(base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
            lines = urllib.request.urlopen(req).read().decode().splitlines()
            assert json.loads(lines[-1])["type"] == "replay"
    finally:
        server.shutdown()
