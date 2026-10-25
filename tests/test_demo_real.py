"""Offline tests for the real-data demo: staged spend, bridge ranking, quote debris, screen labels."""
import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import config  # noqa: E402
import llm  # noqa: E402
from tests import fake_llm  # noqa: E402


# --------------------------------------------------------------------------- staged spend
def test_spend_ledger_carries_the_cap_across_processes(tmp_path, monkeypatch):
    ledger = tmp_path / "spend.jsonl"
    ledger.write_text(json.dumps({"step": "earlier step", "usd": 4.5}) + "\n")
    monkeypatch.setenv("LLM_SPEND_LEDGER", str(ledger))
    monkeypatch.setenv("LLM_SPEND_STEP", "this step")
    assert llm._ledger_prior() == 4.5
    monkeypatch.setattr(llm, "_LEDGER_PRIOR", llm._ledger_prior())
    monkeypatch.setattr(config, "LLM_MAX_USD", 5.0)
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    fake_llm.install(monkeypatch)
    monkeypatch.setattr(llm, "price_usd", lambda *a, **k: 1.0)  # every fake call costs $1
    monkeypatch.setattr(llm.METER, "live_usd", 0.0)
    llm.chat("sys", "first")  # 4.5 < 5: allowed, logged
    lines = [json.loads(x) for x in ledger.read_text().splitlines()]
    assert lines[-1]["step"] == "this step" and lines[-1]["usd"] == 1.0
    with pytest.raises(llm.SpendCapReached):  # 4.5 + 1.0 >= 5
        llm.chat("sys", "second")


def test_extras_drop_taxonomy_rerun_before_the_model_swap():
    import estimate_cost

    est = {"subs": {"a": {"cost_usd": 0.3}, "b": {"cost_usd": 5.2}, "c": {"cost_usd": 2.7}}}
    assert estimate_cost.fit_extras(est, 10) == (["a", "b", "c"], [])
    assert estimate_cost.fit_extras(est, 6) == (["a", "c"], ["b"])
    assert estimate_cost.fit_extras(est, 1) == (["a"], ["b", "c"])
    assert estimate_cost.fit_extras(est, 1, only=["c"]) == (["c"], [])


def test_real_run_refuses_without_the_stage_cap(monkeypatch):
    import real_run

    monkeypatch.setattr(config, "LLM_MAX_USD", None)
    with pytest.raises(SystemExit, match="LLM_MAX_USD"):
        real_run.gate("core", 12.0, 20.0)
    monkeypatch.setattr(config, "LLM_MAX_USD", 25.0)
    with pytest.raises(SystemExit, match="LLM_MAX_USD"):
        real_run.gate("core", 12.0, 20.0)
    with pytest.raises(SystemExit, match="over the core cap"):
        real_run.gate("core", 21.0, 30.0)
    with pytest.raises(SystemExit, match="Nothing was spent"):
        real_run.gate("extras", 8.0, 0.0)


# --------------------------------------------------------------------------- bridge ranking (screen 4)
def _drv(name, typ, tickers):
    return {"id": name, "driver": name, "type": typ, "tickers": tickers, "uses": []}


def test_bridge_ranking_prefers_specific_drivers():
    import graph_qa

    rows = [_drv("United States", "GEOGRAPHY", ["GM", "NXPI"]),            # home country: never ranked
            _drv("North America", "GEOGRAPHY", ["F", "ON"]),
            _drv("China", "GEOGRAPHY", ["GM", "F", "TSLA", "APTV", "BWA", "LEA", "NXPI", "ON"]),  # 8 of 10 = 80%
            _drv("import tariffs", "REGULATION_POLICY", ["GM", "NXPI", "TXN"]),
            _drv("export controls", "REGULATION_POLICY", ["GM", "NXPI"]),
            _drv("TSMC", "NAMED_COUNTERPARTY", ["GM", "NXPI"]),
            _drv("rare earth elements", "INPUT_COMMODITY", ["TSLA", "ON"]),
            _drv("Taiwan", "GEOGRAPHY", ["F", "MCHP"])]
    shown, generic_only = graph_qa.rank_bridge(rows, 10)
    assert not generic_only
    # fewest companies first (all have 2), then input, named counterparty, place, policy; at most 3
    assert [r["driver"] for r in shown] == ["rare earth elements", "TSMC", "Taiwan"]
    assert not any(r["generic"] for r in shown)
    assert graph_qa.bridge_generic(rows[2], 10) == "cited by 8 of 10"
    assert graph_qa.bridge_generic(rows[2], 11) is None  # 8 of 11 < 80%
    shown, _ = graph_qa.rank_bridge(rows[3:5], 10)
    assert [r["driver"] for r in shown] == ["export controls", "import tariffs"]  # specificity before type


def test_bridge_with_only_generic_drivers_says_so_and_makes_no_call(monkeypatch):
    import graph_qa

    rows = [_drv("China", "GEOGRAPHY", ["GM", "NXPI", "TXN"]), _drv("United States", "GEOGRAPHY", ["GM", "NXPI"]),
            _drv("import tariffs", "REGULATION_POLICY", ["GM", "NXPI", "TXN"])]
    shown, generic_only = graph_qa.rank_bridge(rows, 3)  # the 3-filing A/B graph: 3 of 3 is everyone
    assert generic_only and all(r["generic"] for r in shown) and len(shown) == 3
    assert {r["why_generic"] for r in shown} == {"home country", "cited by 3 of 3"}
    monkeypatch.setattr(llm, "chat", lambda *a, **k: pytest.fail("no model call for generic-only rows"))
    out = graph_qa.answer(graph_qa.QUESTIONS[2], shown, [], generic_only=True)
    assert out["generic_only"] and out["summary"].startswith("Only generic links – no specific bridge")
    assert graph_qa.rank_bridge([], 10) == ([], False)
    sub = graph_qa.to_subgraph([dict(shown[0], uses=[])], [])
    assert sub["drivers"][0]["generic"] is True


def test_driver_near_duplicates_are_reported_not_added():
    import driver_dups

    drivers = [{"name": "critical minerals", "type": "INPUT_COMMODITY", "tickers": ["GM", "F"]},
               {"name": "critical materials", "type": "INPUT_COMMODITY", "tickers": ["NXPI"]},
               {"name": "minerals", "type": "INPUT_COMMODITY", "tickers": ["TXN"]},
               {"name": "minerals", "type": "GEOGRAPHY", "tickers": ["ON"]},
               {"name": "lithium", "type": "INPUT_COMMODITY", "tickers": ["GM"]}]
    spelling, subset = driver_dups.groups(drivers)
    assert spelling == [{"type": "INPUT_COMMODITY", "canonical": "critical minerals",
                         "names": ["critical minerals", "critical materials"], "tickers": ["F", "GM", "NXPI"]}]
    assert [s["names"] for s in subset] == [["minerals", "critical minerals"]]
    before = (config.CONFIG_DIR / "graph_aliases.yaml").read_text()
    assert "critical minerals: [critical materials]" in driver_dups.report((spelling, subset), "x")
    assert (config.CONFIG_DIR / "graph_aliases.yaml").read_text() == before
