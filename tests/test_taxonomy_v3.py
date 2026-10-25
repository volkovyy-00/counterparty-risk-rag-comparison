"""Approach 3, taxonomy-v3: heading split, one label per risk factor, unscored driver. Offline (fake LLM)."""
import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import config  # noqa: E402
import llm  # noqa: E402
import taxonomy  # noqa: E402
from corpus import chunk_text, load_corpus, pack_sections, split_check, split_risk_factors  # noqa: E402
from tests import fake_llm  # noqa: E402
from verify import verify_claims  # noqa: E402

EDGAR = config.DATA_DIR / "corpus" / "edgar_latest"
# Frozen 25 Oct 2026 after tuning on the 8 filings with stand-alone headings (results/taxonomy_split_report.md).
# A change here changes every v3 window: re-run the split report and say why.
FROZEN_SPLIT = {"APTV": 48, "BWA": 42, "LEA": 31, "MCHP": 57, "NXPI": 45, "ON": 41, "TSLA": 41, "TXN": 19}
FROZEN_FIXED = {"F", "GM"}  # headings run into the paragraph
V2_PROMPT_SHA = {"taxonomy-v2.0": "8eaaa2a888e953d5ca05c287844c281723145d6ee852b2d6db6c4a7a94ad1968",
                 "taxonomy-v2.1": "dd92af1e6354b7d0b268b668d9e2a343718a8ac9101cf4218add6fe4975e51fe"}


@pytest.fixture
def fake(tmp_path, monkeypatch):
    fake_llm.install(monkeypatch)
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(config, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(config, "LLM_CACHE", "readwrite")
    llm.METER.stages.clear()


@pytest.fixture
def version(monkeypatch):
    """Load approach3_taxonomy under a given TAXO_PROMPT_VERSION / TAXO_SPLIT; the default is restored after."""
    import approach3_taxonomy

    def load(v, split=None):
        monkeypatch.setenv("TAXO_PROMPT_VERSION", v)
        monkeypatch.setattr(config, "TAXO_SPLIT", split)
        return importlib.reload(approach3_taxonomy)
    yield load
    monkeypatch.delenv("TAXO_PROMPT_VERSION", raising=False)
    monkeypatch.setattr(config, "TAXO_SPLIT", None)
    importlib.reload(approach3_taxonomy)


def _keyword_sentences(n, skip=()):
    """n (leaf, sentence) pairs whose sentence maps onto that leaf by keywords, one leaf each."""
    out = []
    for leaf, info in taxonomy.LEAVES.items():
        kw = next((k for k in info.get("keywords", []) if not k.endswith("*")), None)
        if not kw or leaf in skip:
            continue
        s = f"Our results could be harmed by {kw}, which may adversely affect our operations in future periods."
        if taxonomy.leaves_for(s)[:1] == [leaf]:
            out.append((leaf, s))
        if len(out) == n:
            return out
    raise AssertionError("not enough keyword leaves")


def _filing(sections, ticker="TEST"):
    """sections: [(heading, [paragraph, ...])] -> a filing dict with an Item 1A text."""
    parts = ["Risks Related to Our Business"]
    for heading, paras in sections:
        parts.append(heading + "\n" + "\n\n".join(paras))
    return {"ticker": ticker, "company": "Test Co", "accession": "0000000000-00-000000", "text": "\n\n".join(parts)}


def _filler(i, k):
    return f"Paragraph {i}.{k} describes the matter in more detail. " + "Further general context follows here. " * 18


def _edge_filing():
    """10 risk factors; factor 7 has six tariff paragraphs and sits across the old 12,000-char window edge."""
    others = _keyword_sentences(9, skip={"GEOPOLITICAL_TRADE.tariffs"})
    sections = []
    for i, (_, s) in enumerate(others[:6]):
        sections.append((f"Heading number {i} names a separate matter for the company.",
                         [s + " " + _filler(i, 0), _filler(i, 1)]))
    tariff = [f"New tariffs (measure {k}) on imported parts could raise the price of what we buy from abroad. "
              + _filler(7, k) for k in range(6)]
    sections.append(("Trade measures could raise the cost of the parts we import.", tariff))
    for i, (_, s) in enumerate(others[6:], start=8):
        sections.append((f"Heading number {i} names a separate matter for the company.", [s + " " + _filler(i, 0)]))
    return _filing(sections)


# --------------------------------------------------------------------------- split
def test_split_sections_keep_exact_offsets_and_carry_subcaptions():
    f = _edge_filing()
    secs = split_risk_factors(f["text"])
    assert all(f["text"][s["start"]:s["end"]] == s["text"] for s in secs)
    assert [s["idx"] for s in secs] == list(range(1, 11))  # no text before the first heading: no intro
    assert secs[0]["subcaption"] == "Risks Related to Our Business" and secs[0]["text"].startswith("Risks Related")
    assert secs[6]["heading"] == "Trade measures could raise the cost of the parts we import."
    assert split_check(secs, 12000) is None


def test_factor_across_old_window_edge_gets_one_claim_not_two(fake, version):
    from answer import finalise

    f = _edge_filing()
    tariff_start = f["text"].index("Trade measures could")
    assert any(s < tariff_start + 3000 < s + len(w) for s, w in chunk_text(f["text"], 12000, 0)) and any(
        s <= tariff_start < s + len(w) < tariff_start + 5000 for s, w in chunk_text(f["text"], 12000, 0))

    def tariff_claims(v):
        a3 = version(v)
        r = finalise(a3.run(config.QUESTION, [f]), [f])
        return [c for c in r["claims"] if c["leaf"] == "GEOPOLITICAL_TRADE.tariffs"], r
    v2, _ = tariff_claims("taxonomy-v2.0")
    v3, r3 = tariff_claims("taxonomy-v3.0")
    assert len(v2) == 2  # fixed windows: the factor is cut in two and labelled from each half
    assert len(v3) == 1 and v3[0]["source_ref"] == "TEST:rf7"
    assert r3["details"]["split_by_ticker"]["TEST"]["method"] == "heading"


def test_oversize_section_is_split_and_every_part_repeats_its_heading():
    heading = "A long risk factor heading that runs on for a while."
    f = _filing([(heading, [_filler(0, k) for k in range(12)])] +
                [(f"Short heading number {i} for this risk factor.", [_filler(i, 0)]) for i in range(1, 9)])
    secs = split_risk_factors(f["text"])
    assert len(secs[0]["text"]) > 2000
    windows = pack_sections(secs, 2000)
    parts = [w for w, idxs in windows if idxs == [1]]
    assert len(parts) >= 2
    assert all(w.startswith(f"[RF 1] {heading} (part {k + 1}/{len(parts)})") for k, w in enumerate(parts))
    assert all(len(idxs) == len(set(idxs)) for _, idxs in windows)


def test_filing_with_few_headings_falls_back_to_fixed_and_says_why(fake, version):
    from answer import finalise

    f = _filing([(f"Heading number {i} names a separate matter for the company.", [_filler(i, 0)])
                 for i in range(3)])
    a3 = version("taxonomy-v3.0")
    windows, info = a3.split_filing(f)
    assert info["method"] == "fixed" and "fewer than 8" in info["reason"]
    assert [w for _, w, _ in windows] == [w for _, w in chunk_text(f["text"], config.TAXO_WINDOW_CHARS, 0)]
    r = finalise(a3.run(config.QUESTION, [f]), [f])
    assert r["details"]["split_by_ticker"]["TEST"] == {"method": "fixed", "reason": info["reason"],
                                                       "sections": 0, "windows": len(windows)}


def test_manifest_records_split_and_fallback_reason_per_ticker(fake, tmp_path, monkeypatch):
    import run_all

    monkeypatch.setattr(config, "CORPUS", "edgar_latest")
    monkeypatch.setattr(config, "CORPUS_DIR", EDGAR)
    filings = load_corpus(EDGAR)
    monkeypatch.setattr(run_all, "load_corpus", lambda: [f for f in filings if f["ticker"] in ("GM", "TXN")])
    run_dir, _ = run_all.run(["3"], tmp_path / "run")
    man = json.loads((run_dir / "manifest.json").read_text())
    assert man["taxonomy_prompt_version"] == "taxonomy-v3.0" and man["taxonomy_split"] == "heading"
    assert man["taxonomy_sha256"] == taxonomy.SHA256
    assert man["taxonomy_split_by_ticker"]["TXN"] == {"method": "heading", "reason": None}
    assert man["taxonomy_split_by_ticker"]["GM"]["method"] == "fixed"
    assert "run into the paragraph" in man["taxonomy_split_by_ticker"]["GM"]["reason"]


@pytest.mark.skipif(not (EDGAR / "manifest.csv").exists(), reason="edgar_latest corpus not fetched")
def test_edgar_split_is_frozen():
    """>= 8 of 10 filings split by heading; the section counts do not drift between sessions."""
    got, fixed = {}, set()
    for f in load_corpus(EDGAR):
        secs = split_risk_factors(f["text"])
        if split_check(secs, config.TAXO_WINDOW_CHARS):
            fixed.add(f["ticker"])
        else:
            got[f["ticker"]] = len(secs)
    assert got == FROZEN_SPLIT and fixed == FROZEN_FIXED


# --------------------------------------------------------------------------- v2 reproducibility
@pytest.mark.parametrize("v", ["taxonomy-v2.0", "taxonomy-v2.1"])
def test_v2_prompts_and_windows_are_unchanged(version, v):
    import manifest

    a3 = version(v)
    assert a3.SPLIT == "fixed"
    assert manifest.sha256(a3.system() + json.dumps(a3.SCHEMA, sort_keys=True)) == V2_PROMPT_SHA[v]
    f = _edge_filing()
    assert a3.windows_for(f) == [(f"TEST:w{n + 1}", w) for n, (_, w) in
                                 enumerate(chunk_text(f["text"], config.TAXO_WINDOW_CHARS, 0))]


def test_v2_refuses_the_heading_split(version):
    with pytest.raises(SystemExit, match="always uses TAXO_SPLIT=fixed"):
        version("taxonomy-v2.0", "heading")


# --------------------------------------------------------------------------- driver and label rules
def _claim(f, leaf, quote, **kw):
    return dict({"company": f["ticker"], "category": taxonomy.category_of(leaf), "leaf": leaf, "quote": quote,
                 "source_ref": "TEST:w1", "risk": "x"}, **kw)


def test_driver_passes_through_and_scoring_ignores_it():
    import evaluate
    from answer import matrix, shared_risks

    f1, f2 = _edge_filing(), dict(_edge_filing(), ticker="TWO")
    q = "New tariffs (measure 0) on imported parts could raise the price of what we buy from abroad."
    raw = [_claim(f, "GEOPOLITICAL_TRADE.tariffs", q, driver="Mexico tariffs") for f in (f1, f2)]
    acc, rej, _ = verify_claims(raw, [f1, f2])
    assert not rej and [c["driver"] for c in acc] == ["Mexico tariffs"] * 2 and acc[0]["secondary"] is False
    bare = [dict(c, driver="") for c in acc]
    gt = {"status": "test", "yes": {"TEST": {"GEOPOLITICAL_TRADE.tariffs"}, "TWO": {"GEOPOLITICAL_TRADE.tariffs"}},
          "decided": {"TEST": {"GEOPOLITICAL_TRADE.tariffs"}, "TWO": {"GEOPOLITICAL_TRADE.tariffs"}}}
    tickers = ["TEST", "TWO"]
    assert evaluate.evaluate(acc, gt, tickers) == evaluate.evaluate(bare, gt, tickers)
    assert shared_risks(acc, 2) == shared_risks(bare, 2)
    assert matrix(acc, tickers, "leaf") == matrix(bare, tickers, "leaf")


def test_other_needs_a_driver(version):
    a3 = version("taxonomy-v3.0")
    f = _edge_filing()
    q = "Paragraph 0.1 describes the matter in more detail."
    claims = a3.validate_v3([_claim(f, "OTHER.stock_governance", q, driver=""),
                             _claim(f, "OTHER.stock_governance", q + " Further", driver="share buybacks")], {})
    acc, rej, stats = verify_claims(claims, [f])
    assert [r["reason"] for r in rej] == ["OTHER label without a driver"] and rej[0]["check"] == "label"
    assert [c["driver"] for c in acc] == ["share buybacks"] and stats["rejected_label"] == 1


def test_one_primary_per_factor_and_secondary_only_when_the_heading_names_both(version):
    a3 = version("taxonomy-v3.0")
    f = _edge_filing()
    q = "New tariffs (measure 0) on imported parts could raise the price of what we buy from abroad."
    two = {"heading": "Tariffs and export controls could limit our sales.", "subcaption": ""}
    one = {"heading": "Trade measures could raise the cost of the parts we import.", "subcaption": ""}
    sections = {"TEST:rf1": two, "TEST:rf2": one, "TEST:rf0": {"heading": "(introduction)", "subcaption": ""}}
    claims = a3.validate_v3([
        _claim(f, "GEOPOLITICAL_TRADE.tariffs", q, source_ref="TEST:rf1"),
        _claim(f, "GEOPOLITICAL_TRADE.export_controls", q, source_ref="TEST:rf1", secondary=True),  # heading: both
        _claim(f, "GEOPOLITICAL_TRADE.tariffs", q, source_ref="TEST:rf2"),
        _claim(f, "GEOPOLITICAL_TRADE.export_controls", q, source_ref="TEST:rf2", secondary=True),  # heading: neither
        _claim(f, "SUPPLY_CHAIN.logistics", q, source_ref="TEST:rf2"),  # a second primary
        _claim(f, "GEOPOLITICAL_TRADE.tariffs", q, source_ref="TEST:rf0"),  # the introduction
    ], sections)
    assert [c.get("label_error") for c in claims] == [
        None, None, None, "secondary label not supported by the heading",
        "second primary label for TEST:rf2 (one label per risk factor)",
        "label on (introduction), which is not a risk factor"]
