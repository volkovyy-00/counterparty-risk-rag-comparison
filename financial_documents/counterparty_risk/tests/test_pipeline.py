"""Offline tests: python -m pytest tests -q   (Neo4j tests run only if NEO4J_PASSWORD is set)."""
import json
import socket
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
import llm  # noqa: E402
import taxonomy  # noqa: E402
from corpus import chunk_text, load_corpus  # noqa: E402
from item1a import extract_item1a, html_to_text  # noqa: E402
from tests import fake_llm  # noqa: E402
from verify import locate, normalise, verify_claims  # noqa: E402

WORKSHOP_CORPUS = config.DATA_DIR / "corpus" / "workshop_sample"


@pytest.fixture
def offline(tmp_path, monkeypatch):
    fake_llm.install(monkeypatch)
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(config, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(config, "CORPUS", "workshop_sample")
    monkeypatch.setattr(config, "CORPUS_DIR", WORKSHOP_CORPUS)
    monkeypatch.setattr(config, "LLM_CACHE", "readwrite")
    llm.METER.stages.clear()
    llm.METER.served_models.clear()
    if not (WORKSHOP_CORPUS / "manifest.csv").exists():
        pytest.skip("run prepare_workshop_sample.py first")
    return load_corpus(WORKSHOP_CORPUS)


def _run(module, filings):
    from answer import finalise

    return finalise(module.run(config.QUESTION, filings), filings)


# --------------------------------------------------------------------------- extraction and text
def test_item1a_skips_table_of_contents():
    html = """<html><body>
    <table><tr><td>Item 1A.</td><td>Risk Factors</td><td>12</td></tr>
           <tr><td>Item 1B.</td><td>Unresolved Staff Comments</td></tr></table>
    <p>Item 1. Business</p><p>See <a href='#x'>Item 1A. Risk Factors</a> for more.</p>
    <p style='font-weight:bold'>Item 1A. Risk Factors</p>
    <p>Our suppliers are concentrated in one region. """ + "More text. " * 300 + """</p>
    <p>Item 1B. Unresolved Staff Comments</p><p>None.</p>
    <div style='display:none'>Item 1A. Risk Factors hidden xbrl</div>
    </body></html>"""
    body, method = extract_item1a(html_to_text(html))
    assert method == "heading"
    assert body.startswith("Our suppliers are concentrated")
    assert "Unresolved" not in body and "See Item 1A" not in body


def test_quote_check_is_verbatim_but_typography_tolerant_and_returns_raw_offsets():
    source = "Intro.\n\nOur “global” supply chain —  including\nTaiwan — is concentrated. End."
    start, end = locate('Our "global" supply chain - including Taiwan - is concentrated.', source)
    assert source[start:end] == "Our “global” supply chain —  including\nTaiwan — is concentrated."
    assert locate("Our global supply chain is concentrated in Taiwan.", source) is None
    assert locate("too short", source) is None


def test_chunker_covers_text():
    text = "\n\n".join(f"Paragraph {i}. " + "word " * 80 for i in range(30))
    chunks = chunk_text(text, 1500, 200)
    assert all(len(c) <= 2250 for _, c in chunks)
    assert "Paragraph 29." in chunks[-1][1] and "Paragraph 0." in chunks[0][1]


def test_taxonomy_v2_is_closed_and_two_level():
    assert taxonomy.VERSION == 2
    assert {"PRODUCT_SAFETY_RECALL", "EMISSIONS_EV_TRANSITION", "COMMODITY_INPUTS"} <= set(taxonomy.CATEGORY_IDS)
    for cat, leaves in taxonomy.LEAVES_BY_CATEGORY.items():
        assert 2 <= len(leaves) <= 5, cat
    for leaf in ["SUPPLY_CHAIN.semiconductor_supply", "SUPPLY_CHAIN.single_source", "GEOPOLITICAL_TRADE.tariffs",
                 "GEOPOLITICAL_TRADE.china_exposure", "GEOPOLITICAL_TRADE.export_controls",
                 "CUSTOMER_CONCENTRATION.auto_oem_customers"]:
        assert leaf in taxonomy.LEAVES


def test_groups_default_is_auto_semis():
    import yaml

    groups = yaml.safe_load((config.ROOT / "groups.yaml").read_text())
    assert groups["default"] == "auto_semis"
    assert list(groups["groups"]["auto_semis"]["companies"]) == \
        ["GM", "F", "TSLA", "APTV", "BWA", "LEA", "NXPI", "MCHP", "ON", "TXN"]


# --------------------------------------------------------------------------- the shared verifier
def test_verifier_rules(offline):
    nvda = next(f for f in offline if f["ticker"] == "NVDA")
    amzn = next(f for f in offline if f["ticker"] == "AMZN")
    real = next(s for s in fake_llm._sentences(nvda["text"]) if len(s) > 80)
    other = next(s for s in fake_llm._sentences(amzn["text"]) if len(s) > 80)
    claims = [
        {"company": "NVDA", "category": "SUPPLY_CHAIN", "leaf": "SUPPLY_CHAIN.single_source", "quote": real},
        {"company": "NVDA", "category": "SUPPLY_CHAIN", "leaf": "SUPPLY_CHAIN.single_source", "quote": other},
        {"company": "NVDA", "category": "SUPPLY_CHAIN", "leaf": "SUPPLY_CHAIN.single_source",
         "quote": fake_llm.FABRICATED},
        {"company": "NVDA", "category": fake_llm.OFF_TAXONOMY, "leaf": "SUPPLY_CHAIN.single_source", "quote": real},
        {"company": "NVDA", "category": "TAX", "leaf": "SUPPLY_CHAIN.single_source", "quote": real},
        {"company": "XYZ", "category": "TAX", "leaf": "TAX.tax_audits_disputes", "quote": real},
        {"company": "NVDA", "category": "", "leaf": "", "risk": "tariffs on imports", "quote": real},
    ]
    accepted, rejected, stats = verify_claims(claims, offline)
    reasons = [r["reason"] for r in rejected]
    assert "quote is from AMZN's filing, not NVDA's" in reasons
    assert "quote not found verbatim in the company's Item 1A" in reasons
    assert f"category '{fake_llm.OFF_TAXONOMY}' is not in taxonomy v2" in reasons
    assert "leaf 'SUPPLY_CHAIN.single_source' does not belong to category 'TAX'" in reasons
    assert "company 'XYZ' is not in the group" in reasons
    assert stats["keyword_fallback"] == 1 and accepted[-1]["fallback"]
    for c in accepted:
        assert normalise(nvda["text"][c["start"]:c["end"]]) == normalise(c["quote"])


@pytest.mark.parametrize("key", ["1", "3", "L"])
def test_shared_verifier_on_every_approach(offline, key):
    import run_all

    result = _run(run_all._module(key), offline)
    by_ticker = {f["ticker"]: f["text"] for f in offline}
    assert result["claims"], "no verified claims"
    for c in result["claims"]:  # every accepted quote is located in that company's own Item 1A
        assert normalise(by_ticker[c["company"]][c["start"]:c["end"]]) == normalise(c["quote"])
    assert result["verification"]["quote_coverage"] is not None
    if key == "3":  # the fake plants one fabricated quote per window: all must be rejected
        assert result["verification"]["rejected_quote"] == result["details"]["windows_classified"]
        assert "AAPL" not in {c["company"] for c in result["claims"]}  # Verde Bio file: no risk factors


def test_validator_rejects_off_taxonomy_label_when_provider_does_not_enforce_enums(offline, monkeypatch):
    """An OpenAI-compatible local server in JSON mode: no schema enforcement, so the code must catch it."""
    import approach3_taxonomy

    sent = []

    class Completions:
        def create(self, **kwargs):
            sent.append(kwargs)
            text = next(f for f in offline if f["ticker"] == "NVDA")["text"]
            quote = next(s for s in fake_llm._sentences(text) if len(s) > 80)
            body = {"risk_factors": [{"heading": "x", "category": fake_llm.OFF_TAXONOMY,
                                      "leaf": "SUPPLY_GEOPOLITICS.taiwan", "quote": quote}]}
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(body)))],
                                   usage=SimpleNamespace(prompt_tokens=10, completion_tokens=10), model="local-model")

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()), with_options=lambda **k: client)
    monkeypatch.setattr(llm, "_call_chat", fake_llm.REAL_CALL_CHAT)  # the real code path, fake transport
    monkeypatch.setattr(llm, "_client", lambda provider: client)
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(config, "LLM_STRUCTURED", "json")
    nvda = [f for f in offline if f["ticker"] == "NVDA"]
    result = _run(approach3_taxonomy, nvda)
    assert "response_format" not in sent[0]  # nothing enforced by the provider
    assert result["claims"] == []
    assert {r["check"] for r in result["rejected"]} == {"label"}
    assert result["rejected"][0]["reason"] == f"category '{fake_llm.OFF_TAXONOMY}' is not in taxonomy v2"


# --------------------------------------------------------------------------- caching, replay, freezing
def test_replay_mode_fails_loudly_on_cache_miss(offline, monkeypatch):
    monkeypatch.setattr(config, "LLM_CACHE", "replay")
    with pytest.raises(llm.CacheMiss):
        llm.chat("system", "a prompt that was never recorded")


def test_replay_runs_with_no_network(offline, monkeypatch, tmp_path):
    import run_all

    run_all.run(["1", "3", "L"], tmp_path / "first")
    monkeypatch.setattr(config, "LLM_CACHE", "replay")
    monkeypatch.setattr(llm, "_call_chat", lambda *a, **k: (_ for _ in ()).throw(AssertionError("API called")))

    def no_network(*args, **kwargs):
        raise AssertionError("network used in replay")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    llm.METER.stages.clear()
    run_dir, text = run_all.run(["1", "3", "L"], tmp_path / "replay")
    card = json.loads((run_dir / "scorecard.json").read_text())
    assert set(card["columns"]) == {"0_long_context", "1_plain_rag", "3_taxonomy_first"}
    assert "replayed" in text  # latency is never reported for replayed calls
    assert "DRAFT KEY" in text


def test_freeze_refuses_fake_model_output(offline, monkeypatch, tmp_path):
    import run_all

    monkeypatch.setattr(run_all, "DEMO_RUN", tmp_path / "demo_run")
    run_dir, _ = run_all.run(["3"], tmp_path / "run")
    with pytest.raises(SystemExit, match="Refusing to freeze"):
        run_all.freeze(run_dir, llm.METER.served_models)
    assert not (tmp_path / "demo_run").exists()


def test_committed_demo_run_contains_no_fake_output():
    demo = config.ROOT / "results" / "demo_run"
    if not demo.exists():
        pytest.skip("no results/demo_run yet")
    for path in demo.rglob("*"):
        if path.is_file() and path.suffix in (".json", ".md", ".csv", ".jsonl"):
            assert fake_llm.FAKE_MODEL not in path.read_text(errors="ignore"), path
    man = json.loads((demo / "manifest.json").read_text())
    assert man["served_models"] and not any(m.startswith(("fake", "unknown")) for m in man["served_models"])


# --------------------------------------------------------------------------- manifests and consistency
def test_manifest_hashes_and_diff(offline, tmp_path, monkeypatch):
    import shutil

    import manifest

    corpus = tmp_path / "corpus"
    shutil.copytree(WORKSHOP_CORPUS, corpus)
    h1 = manifest.corpus_hash(corpus)
    assert h1 == manifest.corpus_hash(corpus) and len(h1) == 64
    (corpus / "item1a" / "NVDA.txt").write_text("changed")
    assert manifest.corpus_hash(corpus) != h1
    a = manifest.build(offline, ["3_taxonomy_first"])
    monkeypatch.setattr(config, "LLM_MODEL", "another-model")
    b = manifest.build(offline, ["3_taxonomy_first"])
    changed = {k for k, _, _ in manifest.diff(a, b)}
    assert "model" in changed and "taxonomy_sha256" not in changed
    assert set(a["prompt_sha256"]) == {"0_long_context", "1_plain_rag", "2_graphrag", "3_taxonomy_first"}


def test_rerun_consistency_jaccard():
    from evaluate import jaccard, rerun_consistency

    def claims(*pairs):
        return [{"company": t, "leaf": leaf, "category": taxonomy.category_of(leaf)} for t, leaf in pairs]

    tariff, chips = "GEOPOLITICAL_TRADE.tariffs", "SUPPLY_CHAIN.semiconductor_supply"
    run_a = claims(("GM", tariff), ("F", tariff), ("GM", chips), ("F", chips))
    run_b = claims(("GM", tariff), ("F", tariff))
    assert jaccard({1, 2}, {2, 3}) == pytest.approx(1 / 3)
    assert rerun_consistency([run_a, run_a, run_a]) == 1.0
    assert rerun_consistency([run_a, run_b, run_b]) == pytest.approx((0.5 + 0.5 + 1.0) / 3, abs=1e-3)
    assert rerun_consistency([run_a]) is None


def test_scoring_counts_only_shared_pairs():
    from evaluate import evaluate

    gt = {"status": "verified", "yes": {"GM": {"GEOPOLITICAL_TRADE.tariffs", "TAX.tax_audits_disputes"},
                                        "F": {"GEOPOLITICAL_TRADE.tariffs"}}, "decided": {"GM": {1}, "F": {1}}}
    claims = [{"company": "GM", "leaf": "GEOPOLITICAL_TRADE.tariffs", "category": "GEOPOLITICAL_TRADE"},
              {"company": "F", "leaf": "GEOPOLITICAL_TRADE.tariffs", "category": "GEOPOLITICAL_TRADE"},
              {"company": "GM", "leaf": "TAX.tax_law_changes", "category": "TAX"}]  # not shared: not scored
    e = evaluate(claims, gt, ["GM", "F"])
    assert e["leaf"]["precision"] == 1.0 and e["leaf"]["recall"] == 1.0
    assert e["category"]["true"] == 2  # TAX is only GM's: not a shared exposure


# --------------------------------------------------------------------------- Neo4j (optional)
@pytest.mark.skipif(not config.NEO4J_PASSWORD, reason="set NEO4J_PASSWORD to run against a local Neo4j")
def test_graphrag_build_ask_and_export(offline, monkeypatch, tmp_path):
    import approach2_graphrag
    import export_graph

    approach2_graphrag.build(reset=True)
    result = _run(approach2_graphrag, offline)
    assert result["details"]["graph"]["risk_factors_shared"] > 0
    assert result["claims"] and all(c["in_cited_source"] is not None for c in result["claims"])
    graph = export_graph.export(tmp_path / "graph.json")
    assert {n["type"] for n in graph["nodes"]} == {"Company", "RiskFactor"}
    assert graph["resolution"]["risk_factors_exact"] >= graph["resolution"]["risk_factors_resolved"]

    monkeypatch.setattr(config, "GRAPH_MODE", "vector_seeded")  # the workshop's top-k seeded pattern
    seeded = approach2_graphrag.run(config.QUESTION, offline)
    assert seeded["details"]["traversal_rows"] > 0


# --------------------------------------------------------------------------- data quality (SEC mocked)
def test_fetch_10k_logs_quality_issues(tmp_path, monkeypatch):
    """SEC is mocked: checks the data-quality rules, not the network."""
    import fetch_10k

    tickers = {"0": {"cik_str": 1652044, "ticker": "GOOGL", "title": "Alphabet Inc."},
               "1": {"cik_str": 1652044, "ticker": "GOOG", "title": "Alphabet Inc."},
               "2": {"cik_str": 827054, "ticker": "MCHP", "title": "Microchip Technology Inc."}}

    def submissions(name, tick, fye, filings):
        keys = ["form", "accessionNumber", "filingDate", "reportDate", "primaryDocument"]
        return {"name": name, "tickers": tick, "fiscalYearEnd": fye,
                "filings": {"recent": {k: [f[i] for f in filings] for i, k in enumerate(keys)}}}

    body = ("<p>Item 1A. Risk Factors</p><p>" + "Supply chain risk. " * 600
            + "We completed the spin-off of our fuel systems business in 2023.</p>"
            + "<p>Item 1B. Unresolved Staff Comments</p>")
    pages = {
        fetch_10k.TICKER_MAP_URL: json.dumps(tickers),
        fetch_10k.SUBMISSIONS_URL.format(cik=1652044): json.dumps(submissions(
            "Alphabet Inc.", ["GOOGL", "GOOG"], "1231",
            [("10-K/A", "0001652044-26-000002", "2026-04-01", "2025-12-31", "a.htm"),
             ("10-K", "0001652044-26-000001", "2026-02-01", "2025-12-31", "k.htm")])),
        fetch_10k.SUBMISSIONS_URL.format(cik=827054): json.dumps(submissions(
            "Microchip Technology Inc.", ["MCHP"], "0331",
            [("10-K", "0000827054-24-000001", "2024-05-20", "2024-03-31", "k.htm")])),
    }

    def fake_get(self, url):
        return pages.get(url, f"<html><body>{body}</body></html>").encode()

    monkeypatch.setattr(fetch_10k.SecClient, "get", fake_get)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(config, "SEC_USER_AGENT", "Test Runner test@example.com")
    monkeypatch.setattr(config, "GROUP_NOTES", {"MCHP": "March fiscal year end"})
    monkeypatch.setattr(sys, "argv", ["fetch_10k.py", "--tickers", "GOOGL,GOOG,MCHP,ZZZZ"])
    fetch_10k.main()

    issues = [json.loads(line) for line in
              (tmp_path / "data/corpus/edgar_latest/data_quality.jsonl").read_text().splitlines()]
    checks = {(i["check"], i["subject"]) for i in issues}
    for expected in [("duplicate_company", "GOOG"), ("amended_after", "GOOGL"), ("ticker_not_found", "ZZZZ"),
                     ("mixed_years", "all"), ("stale_filing", "MCHP"), ("non_calendar_fiscal_year", "MCHP"),
                     ("group_note", "MCHP"), ("corporate_action_mentioned", "GOOGL")]:
        assert expected in checks, expected
    manifest = load_corpus(tmp_path / "data/corpus/edgar_latest")
    assert [f["ticker"] for f in manifest] == ["GOOGL", "GOOG", "MCHP"]  # reported, not de-duplicated
    assert manifest[0]["text"].startswith("Supply chain risk.")
