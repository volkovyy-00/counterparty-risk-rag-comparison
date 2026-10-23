"""TEST-ONLY: build a complete demo run from the fake model, for developing and testing the page.

    python -m tests.make_fixture /tmp/fixture_run     # never inside results/demo_run

The output is marked as fake (served model "fake-test-model"); build_demo.py
shows it only with --fixture and a "TEST FIXTURE" banner.
"""
import json
import shutil
import sys
from pathlib import Path

from _pytest.monkeypatch import MonkeyPatch

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / "src"), str(Path(__file__).resolve().parents[1])]

import config  # noqa: E402
import llm  # noqa: E402
from tests import fake_llm  # noqa: E402


def make(out, with_graph=None):
    out = Path(out).resolve()
    if out == (config.RESULTS_DIR / "demo_run").resolve() or config.RESULTS_DIR.resolve() in out.parents:
        raise SystemExit("fixtures never go under results/")
    mp = MonkeyPatch()
    fake_llm.install(mp)
    tmp = out.parent / (out.name + "_work")
    mp.setattr(config, "CACHE_DIR", tmp / "cache")
    mp.setattr(config, "RESULTS_DIR", tmp / "results")
    mp.setattr(config, "CORPUS", "workshop_sample")
    mp.setattr(config, "CORPUS_DIR", config.DATA_DIR / "corpus" / "workshop_sample")
    import governance
    import run_all
    from answer import finalise
    from corpus import load_corpus

    with_graph = bool(config.NEO4J_PASSWORD) if with_graph is None else with_graph
    if out.exists():
        shutil.rmtree(out)
    keys = ["1", "3", "L"]
    if with_graph:
        import approach2_graphrag
        import export_graph

        approach2_graphrag.build(reset=True)
        keys.insert(1, "2")
    run_all.run(keys, out, label="fixture run A (prompt taxonomy-v2.0)")
    if with_graph:
        export_graph.export(out / "graph.json")
    filings = load_corpus()
    for name, key in (("1_plain_rag", "1"), ("3_taxonomy_first", "3")):  # fake reruns: drop a few claims
        for k in (2, 3):
            r = finalise(run_all._module(key).run(config.QUESTION, filings), filings)
            claims = r["claims"][: max(1, len(r["claims"]) - 3 * k)]
            (out / "reruns" / name).mkdir(parents=True, exist_ok=True)
            (out / "reruns" / name / f"run_{k}.json").write_text(json.dumps({"claims": claims}))
    mp.setenv("TAXO_PROMPT_VERSION", "taxonomy-v2.1")
    import importlib

    import approach3_taxonomy
    importlib.reload(approach3_taxonomy)
    llm.METER.stages.clear()
    run_b = out / "audit" / "run_b"
    run_all.run(["3"], run_b, label="fixture run B (prompt taxonomy-v2.1)")
    b = json.loads((run_b / "approach_3_taxonomy_first.json").read_text())  # make run B differ visibly
    b["matrix"]["category"]["GEOPOLITICAL_TRADE"]["NVDA"] = 0
    (run_b / "approach_3_taxonomy_first.json").write_text(json.dumps(b))
    card = run_all.scorecard(out)
    (out / "scorecard.json").write_text(json.dumps(run_all.jsonable(card)))
    (out / "governance.json").write_text(json.dumps(governance.run_all(out)))
    mp.undo()
    importlib.reload(approach3_taxonomy)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"fixture -> {out}")
    return out


if __name__ == "__main__":
    make(sys.argv[1] if len(sys.argv) > 1 else "/tmp/fixture_run")
