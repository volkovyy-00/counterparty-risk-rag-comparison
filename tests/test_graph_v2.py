"""Offline tests for GraphRAG v2 (approach 2): chunking, validation, resolution, metrics, export, estimate."""
import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import config  # noqa: E402
import graph_resolve  # noqa: E402
import graph_v2  # noqa: E402
import llm  # noqa: E402
from corpus import load_corpus  # noqa: E402
from tests import fake_llm  # noqa: E402
from tests.test_pipeline import offline  # noqa: E402,F401  (shared fixture)
from verify import locate  # noqa: E402

EDGAR = config.DATA_DIR / "corpus" / "edgar_latest"


def _filing(text, ticker="AAA", company="Alpha Widgets Inc."):
    return {"ticker": ticker, "company": company, "accession": "0000000000-26-000001", "text": text, "url": ""}


# --------------------------------------------------------------------------- chunks
def test_graph_chunks_keep_paragraphs_whole_with_raw_offsets():
    filings = load_corpus(EDGAR) if (EDGAR / "manifest.csv").exists() else load_corpus()
    for f in filings:
        chunks = graph_v2.graph_chunks(f)
        assert [c["id"] for c in chunks] == [f"{f['ticker']}-g{i}" for i in range(len(chunks))]
        for c in chunks:
            assert c["text"] == f["text"][c["start"]:c["end"]]
        assert all(a["end"] <= b["start"] for a, b in zip(chunks, chunks[1:]))  # no overlap
        for s, e in graph_v2.paragraphs(f["text"]):  # every paragraph sits inside exactly one chunk
            assert sum(c["start"] <= s and e <= c["end"] for c in chunks) == 1


def test_page_break_fragments_join_the_previous_paragraph():
    text = "Our pension plans may need more cash than planned.\n\nFunding depends on returns and the level\n\nof interest rates.\n\nTariffs may raise costs."
    pars = [text[s:e].strip() for s, e in graph_v2.paragraphs(text)]
    assert pars == ["Our pension plans may need more cash than planned.",
                    "Funding depends on returns and the level\n\nof interest rates.", "Tariffs may raise costs."]


def test_keep_apart_split_drops_only_the_smaller_side():
    names = ["Natural disaster disruption of fabs", "Severe weather disruption", "Fab yield problems"]
    rule, out = graph_resolve.keep_apart_split(names)
    assert rule.startswith("natural disaster") and out == [2]
    assert graph_resolve.keep_apart_split(names[:2]) is None


def test_long_block_is_cut_at_line_or_sentence_ends():
    text = "Risks related to our business\n\n" + " ".join(f"Sentence number {i} is here." for i in range(600))
    chunks = graph_v2.graph_chunks(_filing(text), size=2000)
    assert len(chunks) > 3 and all(len(c["text"]) <= 2000 + 200 for c in chunks)  # + a carried heading
    assert all(c["text"].endswith(".") for c in chunks)
    assert chunks[1]["heading"] == "Risks related to our business"


# --------------------------------------------------------------------------- prompt
def test_few_shot_examples_are_verbatim_and_outside_the_demo_group():
    group = {t.lower() for t in config.TICKERS}
    for ex in graph_v2.FEW_SHOT:
        for m in ex["output"]["mentions"]:
            assert locate(m["quote"], ex["input"]) is not None, m["quote"]
            assert all(d["name"] in ex["input"] for d in m["drivers"])
            assert set(m) == set(graph_v2.MENTIONS_SCHEMA["properties"]["mentions"]["items"]["required"])
    prompt = graph_v2.SYSTEM_V2.lower()
    assert not any(f" {t} " in prompt for t in group if len(t) > 2)
    for word in ("general motors", "ford", "tesla", "nxp", "microchip", "texas instruments", "semiconductor shortage"):
        assert word not in "\n".join(ex["input"].lower() for ex in graph_v2.FEW_SHOT)


def test_schema_has_no_bounds_the_provider_would_reject():
    text = json.dumps(graph_v2.MENTIONS_SCHEMA) + json.dumps(graph_resolve.RESOLVE_SCHEMA)
    for word in ("minLength", "maxLength", "minimum", "maximum", "minItems", "maxItems"):
        assert word not in text


# --------------------------------------------------------------------------- validation
def test_validation_keeps_only_quotes_inside_their_chunk():
    p1 = "Supply of semiconductors from Taiwan is limited, and a shortage could halt our assembly lines for weeks."
    p2 = "Our largest customer accounts for 40% of revenue, so losing it would sharply reduce our cash flow."
    f = _filing(p1 + "\n\n" + p2)
    chunks = graph_v2.graph_chunks(f, size=len(p1) + 1)  # one paragraph per chunk
    assert len(chunks) == 2
    m = lambda name, quote, drivers=(): {"heading": "h", "risk_name": name, "detail": "d", "quote": quote,  # noqa: E731
                                         "specificity": "specific", "drivers": list(drivers)}
    records = [{"chunk_id": "AAA-g0", "ticker": "AAA", "prompt_version": "graph-v2", "mentions": [
        m("Semiconductor supply shortage", p1[:60], [{"name": "Taiwan", "type": "GEOGRAPHY"},
                                                     {"name": "Japan", "type": "GEOGRAPHY"}]),
        m("Customer concentration", p2[:60]),                     # true quote, but from the other chunk
        m("Invented risk", fake_llm.FABRICATED),
        m("Alpha supply risk", p1[:60]),                          # company name in the risk name
        m("", p1[:60])]}]
    accepted, rejected = graph_v2.validate([f], chunks, records)
    assert [a["risk_name"] for a in accepted] == ["Semiconductor supply shortage"]
    assert accepted[0]["start"] == 0 and [d["name"] for d in accepted[0]["drivers"]] == ["Taiwan"]
    assert accepted[0]["drivers_dropped"] == 1
    assert sorted(r["reason"] for r in rejected) == ["company_in_name", "empty_name", "outside_chunk",
                                                    "quote_not_found"]


# --------------------------------------------------------------------------- resolution
def _mention(i, ticker, name, detail="", spec="specific"):
    return {"id": f"{ticker}-g0-m{i}", "ticker": ticker, "chunk_id": f"{ticker}-g0", "risk_name": name,
            "detail": detail, "quote": f"quote {i}", "specificity": spec, "drivers": [], "start": i, "end": i + 1}


def test_name_normalisation_merges_trivial_variants():
    assert graph_resolve.normalise_name("Risks related to export controls") == "export control"
    assert graph_resolve.normalise_name("Export Control") == "export control"
    assert graph_resolve.normalise_name("Supply shortages") == "supply shortage"
    assert graph_resolve.normalise_name("Supply chain") != graph_resolve.normalise_name("Supply chain disruption")
    assert graph_resolve.display_name("risks related to tariffs") == "Tariffs"


def test_llm_resolution_refuses_keep_apart_pairs_and_writes_the_audit(offline, monkeypatch):
    detail = "single source dependence on a few large partners for most volume"
    ms = [_mention(0, "AAA", "Supplier concentration", detail), _mention(1, "BBB", "Customer concentration", detail),
          _mention(2, "CCC", "Lithium price volatility", "battery cells"),
          _mention(3, "AAA", "Product recalls", "vehicle recall campaigns cost"),
          _mention(4, "BBB", "Product liability claims", "vehicle recall campaigns cost")]
    filings = [{"ticker": t} for t in ("AAA", "BBB", "CCC")]
    monkeypatch.setattr(config, "GRAPH_SIM_MIN", 0.5)
    snap = graph_resolve.resolve(ms, filings, resolver="llm")
    names = {r["name"] for r in snap["risk_factors"]}
    assert {"Supplier concentration", "Customer concentration", "Product recalls", "Product liability claims"} <= names
    audit = json.loads((config.RESULTS_DIR / f"graph_resolution_{config.CORPUS}.json").read_text())
    rules = [r for r in audit["merges_rejected"] if str(r.get("reason", "")).startswith("rule")]
    assert any("supplier vs customer" in r["reason"] for r in rules)
    for m in audit["merges_approved"]:
        assert graph_resolve.keep_apart_violation(m["members"]) is None
    assert all(r["n_companies"] == 1 for r in snap["risk_factors"])  # nothing merged: all singletons
    assert {m["rf_id"] for m in snap["mentions"]} == {r["id"] for r in snap["risk_factors"]}


def test_large_components_are_split_before_adjudication(offline, monkeypatch):
    monkeypatch.setattr(config, "GRAPH_COMPONENT_MAX", 3)
    monkeypatch.setattr(config, "GRAPH_SIM_MIN", 0.3)
    words = "semiconductor supply shortage chips wafers foundry capacity allocation".split()
    ms = [_mention(i, f"T{i}", " ".join(words[: 2 + i % 6]) + f" variant{i}", " ".join(words)) for i in range(9)]
    snap = graph_resolve.resolve(ms, [{"ticker": f"T{i}"} for i in range(9)], resolver="llm")
    assert snap["audit"]["components"], "candidates should form at least one component"
    assert all(len(c["members"]) <= 3 for c in snap["audit"]["components"])


def test_exact_and_fuzzy_resolvers_stay_selectable(offline):
    ms = [_mention(0, "AAA", "Export controls"), _mention(1, "BBB", "Risks related to export controls"),
          _mention(2, "CCC", "Export control rules")]
    filings = [{"ticker": t} for t in ("AAA", "BBB", "CCC")]
    exact = graph_resolve.resolve(ms, filings, resolver="exact")
    fuzzy = graph_resolve.resolve(ms, filings, resolver="fuzzy")
    assert len(exact["risk_factors"]) == 2 and len(fuzzy["risk_factors"]) == 1
    assert llm.METER.summary("graph.resolve").get("llm_calls", 0) == 0  # no model call for exact or fuzzy


def test_generic_flag_rule(monkeypatch):
    monkeypatch.setattr(config, "GENERIC_SHARE", 0.8)
    t = ["A", "B", "C", "D", "E"]
    ms = [_mention(i, x, "Broad risk") for i, x in enumerate(t[:4])]  # 4 of 5 companies -> generic
    ms += [_mention(10 + i, x, "Cyber boilerplate", spec="boilerplate") for i, x in enumerate(t[:3])]  # 3, all boiler
    ms += [_mention(20 + i, x, "Specific three") for i, x in enumerate(t[:3])]
    ms += [_mention(30 + i, x, "Boiler two", spec="boilerplate") for i, x in enumerate(t[:2])]
    rfs, _, audit = graph_resolve.resolve_risks(ms, [{"ticker": x} for x in t], resolver="exact")
    generic = {r["name"]: r["generic"] for r in rfs}
    assert generic == {"Broad risk": True, "Cyber boilerplate": True, "Specific three": False, "Boiler two": False}
    assert audit["generic_rule"]["min_companies"] == 4
    idf = {r["name"]: r["idf"] for r in rfs}
    assert idf["Broad risk"] < idf["Specific three"] < idf["Boiler two"]


def test_driver_aliases_merge_before_any_model_call(offline):
    ms = [dict(_mention(0, "AAA", "X"), drivers=[{"name": "PRC", "type": "GEOGRAPHY"}]),
          dict(_mention(1, "BBB", "Y"), drivers=[{"name": "China", "type": "GEOGRAPHY"},
                                                 {"name": "IRA", "type": "REGULATION_POLICY"}]),
          dict(_mention(2, "CCC", "Z"), drivers=[{"name": "Taiwan", "type": "GEOGRAPHY"},
                                                 {"name": "U.S.", "type": "GEOGRAPHY"}]),
          dict(_mention(3, "DDD", "W"), drivers=[{"name": "United States", "type": "GEOGRAPHY"}])]
    drivers, _, _ = graph_resolve.resolve_drivers(ms, resolver="exact")
    by = {d["name"]: d for d in drivers}
    assert set(by) == {"China", "Inflation Reduction Act", "Taiwan", "United States"}
    assert len(by["China"]["mention_ids"]) == 2
    assert len(by["United States"]["mention_ids"]) == 2  # "U.S." keys as "u.s" (trailing dot stripped)


# --------------------------------------------------------------------------- metrics, hand check, export
@pytest.fixture
def v2_snapshot(offline):
    chunks, accepted, rejected = graph_v2.run(offline)
    snap = graph_resolve.resolve(accepted, offline)
    snap.update({"prompt_version": "graph-v2", "resolver": "llm", "tickers": [f["ticker"] for f in offline],
                 "rejected": len(rejected), "chunks": [{k: c[k] for k in ("id", "ticker", "start", "end")} for c in chunks]})
    import approach2_graphrag

    approach2_graphrag.snapshot_path().write_text(json.dumps(snap))
    return snap


def test_extraction_jsonl_and_rejections_are_written(v2_snapshot):
    lines = graph_v2.extract_path().read_text().splitlines()
    assert lines and all(json.loads(x)["prompt_version"] == "graph-v2" for x in lines)
    rej = json.loads((config.RESULTS_DIR / f"graph_rejections_{config.CORPUS}.json").read_text())
    assert rej["reasons"].get("quote_not_found", 0) >= 1  # the fake model's planted quote
    assert 0 < rej["verification_rate"] < 1


def test_graph_quality_from_files_without_neo4j(v2_snapshot, offline, monkeypatch):
    import graph_quality

    monkeypatch.setattr(config, "NEO4J_URI", "bolt://127.0.0.1:1")
    q = graph_quality.compute("graph-v2", filings=offline)
    for key in ("quote_verification_rate", "paragraph_coverage", "mentions_per_filing", "canonical_risk_factors",
                "singleton_share", "shared_specific", "shared_specific_cross_industry", "generic_risk_factors",
                "most_generic", "shared_drivers", "resolution", "tokens_and_cost"):
        assert key in q
    assert 0 < q["quote_verification_rate"] < 1 and 0 < q["paragraph_coverage"] <= 1
    assert (config.RESULTS_DIR / f"graph_quality_{config.CORPUS}_graph-v2.json").exists()


def test_hand_check_csv_is_empty_until_a_person_fills_it(v2_snapshot, tmp_path):
    import graph_check

    rows = graph_check.make(v2_snapshot, v2_snapshot["audit"])
    assert sum(r["kind"] == "mention" for r in rows) == min(30, len(v2_snapshot["mentions"]))
    assert all(r[q] == "" for r in rows for q in graph_check.QUESTIONS)
    out = tmp_path / "check.csv"
    graph_check.write(rows, out)
    assert graph_check.score(out)["quote_supports_the_name"]["precision"] is None
    with out.open() as f:
        filled = list(csv.DictReader(f))
    for i, r in enumerate(filled):
        r["quote_supports_the_name"] = "y" if i % 4 else "n"
    graph_check.write(filled, out)
    s = graph_check.score(out)["quote_supports_the_name"]
    assert s["filled"] == len(filled) and 0.7 < s["precision"] < 0.8


def test_export_v2_adds_fields_and_keeps_old_keys(v2_snapshot, offline, tmp_path, monkeypatch):
    import export_graph

    monkeypatch.setattr(config, "NEO4J_URI", "bolt://127.0.0.1:1")  # export v2 needs no Neo4j
    g = export_graph.export_v2(tmp_path / "graph.json", offline, snapshot=v2_snapshot)
    rf = next(n for n in g["nodes"] if n["type"] == "RiskFactor")
    assert {"definition", "aliases", "idf", "boilerplate_share", "generic", "industries", "degree"} <= set(rf)
    edge = next(e for e in g["edges"] if e["quotes"])
    q = edge["quotes"][0]
    text = next(f["text"] for f in offline if f"c:{f['ticker']}" == edge["source"])
    assert locate(q["text"], text) == (q["start"], q["end"])
    assert {"risk_factors_exact", "risk_factors_resolved", "mentions", "merges_approved"} <= set(g["resolution"])
    assert g["quality"]["quote_verification_rate"] and "drivers" in g


def test_v1_prompt_hash_is_unchanged(monkeypatch):
    import manifest

    monkeypatch.setattr(config, "GRAPH_PROMPT_VERSION", "graph-v1-workshop")
    assert manifest.prompt_hashes()["2_graphrag"] == "33d67ddc738b7b9fc2baaf1ca777845b15e2cc834171dca6802aa8a03274b678"
    monkeypatch.setattr(config, "GRAPH_PROMPT_VERSION", "graph-v2")
    assert manifest.prompt_hashes()["2_graphrag"] != "33d67ddc738b7b9fc2baaf1ca777845b15e2cc834171dca6802aa8a03274b678"


def test_estimate_has_graph_rows_for_both_versions(offline):
    import estimate_cost

    v1 = estimate_cost.graph_rows(offline, "graph-v1-workshop", measure=False)
    v2 = estimate_cost.graph_rows(offline, "graph-v2", measure=False)
    assert [r["stage"] for r in v1["rows"]] == ["2 graph build", "2 graph ask"]
    assert [r["stage"] for r in v2["rows"]] == ["2 graph build", "2 graph resolve", "2 graph ask"]
    assert all(r["cost_usd"] > 0 for r in v1["rows"] + v2["rows"])
    assert v2["chunks"] == sum(len(graph_v2.graph_chunks(f)) for f in offline)
    ab = estimate_cost.graph_ab(offline, measure=False)
    assert ab["total_usd"] == pytest.approx(ab["graph-v1-workshop"] + ab["graph-v2"])


# --------------------------------------------------------------------------- demo page
def _page_errors(html_path, query, check):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    errors, found = [], None
    with sync_playwright() as p:
        exe = "/opt/pw-browsers/chromium"
        try:
            browser = p.chromium.launch(**({"executable_path": exe} if Path(exe).exists() else {}))
        except Exception:
            return None
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(html_path.as_uri() + query)
        page.wait_for_selector("body[data-ready='1']")
        found = check in page.inner_text("body")
        browser.close()
    return errors, found


def test_demo_page_renders_new_old_and_missing_graph(tmp_path, monkeypatch):
    import build_demo
    from tests import make_fixture

    run = make_fixture.make(tmp_path / "run", with_graph=False)  # writes a graph-v2 graph.json from the fake model
    monkeypatch.setattr(config, "NEO4J_PASSWORD", None)
    cases = {"new": ("?screen=4&risk=1&drivers=1", "verified mentions")}
    for name, (query, text) in cases.items():
        build_demo.build(run, tmp_path / f"{name}.html", fixture=True)
        res = _page_errors(tmp_path / f"{name}.html", query, text)
        if res is None:
            pytest.skip("no browser")
        assert res == ([], True), name
    old = {"nodes": [{"id": "c:AAPL", "type": "Company", "label": "AAPL", "industry": "other", "degree": 1}],
           "edges": [], "resolution": {"resolver": "fuzzy", "risk_factors_exact": 3, "risk_factors_resolved": 1}}
    (run / "graph.json").write_text(json.dumps(old))
    build_demo.build(run, tmp_path / "old.html", fixture=True)
    assert _page_errors(tmp_path / "old.html", "?screen=4", "exact-name") == ([], True)
    (run / "graph.json").unlink()
    build_demo.build(run, tmp_path / "none.html", fixture=True)
    assert _page_errors(tmp_path / "none.html", "?screen=4", "No exported graph") == ([], True)
