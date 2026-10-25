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
