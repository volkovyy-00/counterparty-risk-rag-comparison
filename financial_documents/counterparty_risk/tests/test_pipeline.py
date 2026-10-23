"""Offline tests: python -m pytest tests -q   (Neo4j test runs only if NEO4J_PASSWORD is set)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
import llm  # noqa: E402
from corpus import chunk_text, find_quote, load_corpus  # noqa: E402
from item1a import extract_item1a, html_to_text  # noqa: E402
from tests import fake_llm  # noqa: E402

WORKSHOP_CORPUS = config.DATA_DIR / "corpus" / "workshop_sample"


@pytest.fixture
def offline(tmp_path, monkeypatch):
    fake_llm.install(monkeypatch)
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(config, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(config, "CORPUS", "workshop_sample")
    monkeypatch.setattr(config, "CORPUS_DIR", WORKSHOP_CORPUS)
    monkeypatch.setattr(config, "LLM_CACHE", "readwrite")
    if not (WORKSHOP_CORPUS / "manifest.csv").exists():
        pytest.skip("run prepare_workshop_sample.py first")
    return load_corpus(WORKSHOP_CORPUS)


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


def test_quote_check_is_verbatim_but_typography_tolerant():
    source = "Our “global” supply chain — including\nTaiwan — is concentrated."
    assert find_quote('Our "global" supply chain - including Taiwan - is concentrated.', source) >= 0
    assert find_quote("Our global supply chain is concentrated in Taiwan.", source) == -1


def test_chunker_covers_text():
    text = "\n\n".join(f"Paragraph {i}. " + "word " * 80 for i in range(30))
    chunks = chunk_text(text, 1500, 200)
    assert all(len(c) <= 2250 for _, c in chunks)
    assert "Paragraph 29." in chunks[-1][1] and "Paragraph 0." in chunks[0][1]


def test_replay_mode_fails_loudly_on_cache_miss(offline, monkeypatch):
    monkeypatch.setattr(config, "LLM_CACHE", "replay")
    with pytest.raises(llm.CacheMiss):
        llm.chat("system", "a prompt that was never recorded")


def test_taxonomy_rejects_fabricated_quotes(offline):
    import approach3_taxonomy

    result = approach3_taxonomy.run(config.QUESTION, offline)
    rejected = result["tables"]["rejections"]
    assert len(rejected) == result["details"]["windows_classified"]  # one planted fake per window
    assert set(rejected["reason"]) == {"quote not found verbatim in source"}
    assert all(len(r["tickers"]) >= config.MIN_SHARED for r in result["shared_risks"])
    assert "AAPL" not in set(result["tables"]["risk_factors"]["ticker"])  # Verde Bio file: no risk factors


def test_runner_end_to_end_with_cache_replay(offline, monkeypatch):
    import run_all

    monkeypatch.setattr(run_all, "LATEST", config.RESULTS_DIR / "latest")
    monkeypatch.setattr(sys, "argv", ["run_all.py", "--approaches", "1,3"])
    run_all.main()
    first = (config.RESULTS_DIR / "latest" / "comparison.md").read_text()
    assert "1 Plain RAG" in first and "3 Taxonomy-first" in first and "Eval P / R / F1" in first

    # Second run must work with no API at all.
    monkeypatch.setattr(config, "LLM_CACHE", "replay")
    monkeypatch.setattr(llm, "_call_chat", lambda *a: (_ for _ in ()).throw(AssertionError("API called")))
    llm.METER.stages.clear()
    run_all.main()
    assert "from cache" in (config.RESULTS_DIR / "latest" / "comparison.md").read_text()


@pytest.mark.skipif(not config.NEO4J_PASSWORD, reason="set NEO4J_PASSWORD to run against a local Neo4j")
def test_graphrag_build_and_ask(offline, monkeypatch):
    import approach2_graphrag

    approach2_graphrag.build(reset=True)
    result = approach2_graphrag.run(config.QUESTION, offline)
    graph = result["details"]["graph"]
    assert graph["companies"] == len([f for f in offline if f["text"]])
    assert graph["risk_factors_shared"] > 0
    assert result["citation_check"]["support_rate"] > 0.5  # fake model caps citations at 6
    assert not result["citation_check"]["unknown_tickers"]

    monkeypatch.setattr(config, "GRAPH_MODE", "vector_seeded")  # the workshop's top-k seeded pattern
    seeded = approach2_graphrag.run(config.QUESTION, offline)
    assert seeded["details"]["traversal_rows"] > 0
    assert not seeded["citation_check"]["unknown_tickers"]


def test_fetch_10k_logs_quality_issues(tmp_path, monkeypatch):
    """SEC is mocked: checks the data-quality rules, not the network."""
    import json

    import fetch_10k

    tickers = {"0": {"cik_str": 1652044, "ticker": "GOOGL", "title": "Alphabet Inc."},
               "1": {"cik_str": 1652044, "ticker": "GOOG", "title": "Alphabet Inc."},
               "2": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}

    def submissions(name, tick, fye, filings):
        keys = ["form", "accessionNumber", "filingDate", "reportDate", "primaryDocument"]
        return {"name": name, "tickers": tick, "fiscalYearEnd": fye,
                "filings": {"recent": {k: [f[i] for f in filings] for i, k in enumerate(keys)}}}

    body = "<p>Item 1A. Risk Factors</p><p>" + "Supply chain risk. " * 600 + "</p><p>Item 1B. Unresolved Staff Comments</p>"
    pages = {
        fetch_10k.TICKER_MAP_URL: json.dumps(tickers),
        fetch_10k.SUBMISSIONS_URL.format(cik=1652044): json.dumps(submissions(
            "Alphabet Inc.", ["GOOGL", "GOOG"], "1231",
            [("10-K/A", "0001652044-26-000002", "2026-04-01", "2025-12-31", "a.htm"),
             ("10-K", "0001652044-26-000001", "2026-02-01", "2025-12-31", "k.htm")])),
        fetch_10k.SUBMISSIONS_URL.format(cik=320193): json.dumps(submissions(
            "Apple Inc.", ["AAPL"], "0926", [("10-K", "0000320193-24-000001", "2024-11-01", "2024-09-28", "k.htm")])),
    }

    def fake_get(self, url):
        return pages.get(url, f"<html><body>{body}</body></html>").encode()

    monkeypatch.setattr(fetch_10k.SecClient, "get", fake_get)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(config, "SEC_USER_AGENT", "Test Runner test@example.com")
    monkeypatch.setattr(sys, "argv", ["fetch_10k.py", "--tickers", "GOOGL,GOOG,AAPL,ZZZZ"])
    fetch_10k.main()

    issues = [json.loads(l) for l in (tmp_path / "data/corpus/edgar_latest/data_quality.jsonl").read_text().splitlines()]
    checks = {(i["check"], i["subject"]) for i in issues}
    assert ("duplicate_company", "GOOG") in checks
    assert ("amended_after", "GOOGL") in checks
    assert ("ticker_not_found", "ZZZZ") in checks
    assert ("mixed_years", "all") in checks
    assert ("stale_filing", "AAPL") in checks
    manifest = load_corpus(tmp_path / "data/corpus/edgar_latest")
    assert [f["ticker"] for f in manifest] == ["GOOGL", "GOOG", "AAPL"]  # reported, not de-duplicated
    assert manifest[0]["text"].startswith("Supply chain risk.")
