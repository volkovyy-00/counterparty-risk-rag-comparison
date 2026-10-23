"""Rerun consistency: independent repeat runs with the LLM cache OFF.

    python rerun.py --approaches 1,2,3 --n 2     # adds runs 2 and 3 next to the frozen run 1

The frozen run in results/demo_run/ is run 1. Each extra run calls the model
again (cache off, nothing written to the cache) and stores only its verified
claims in results/demo_run/reruns/<approach>/run_<k>.json. The scorecard then
reports the mean pairwise Jaccard of the scored (company, leaf) pairs.

Approach 2 reruns rebuild the graph (that is where its variability comes
from). Afterwards the graph of run 1 is restored by replaying the recorded
build from the cache - no model calls.
"""
import argparse
import json

import config
import llm
from answer import finalise
from corpus import load_corpus
from run_all import APPROACHES, DEMO_RUN, _module, jsonable, scorecard, write_comparison, refuse_test_models
from evaluate import load_ground_truth


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--approaches", default="1,2,3")
    parser.add_argument("--n", type=int, default=2, help="extra runs per approach (run 1 is the frozen run)")
    args = parser.parse_args()
    if not (DEMO_RUN / "manifest.json").exists():
        raise SystemExit("No frozen run in results/demo_run/ - run `python run_all.py --freeze` first.")
    filings = load_corpus()
    keys = [k.strip().upper() for k in args.approaches.split(",")]
    for key in keys:
        name = APPROACHES[key][0]
        out_dir = DEMO_RUN / "reruns" / name
        out_dir.mkdir(parents=True, exist_ok=True)
        for k in range(2, 2 + args.n):
            print(f"== {name} run {k} (cache off)")
            config.LLM_CACHE = "off"
            llm.METER.stages.clear()
            if key == "2":
                import approach2_graphrag

                approach2_graphrag.build(reset=True, record=False)
            result = finalise(_module(key).run(config.QUESTION, filings), filings)
            refuse_test_models(llm.METER.served_models)
            (out_dir / f"run_{k}.json").write_text(json.dumps(jsonable({
                "approach": name, "run": k, "model": config.LLM_MODEL,
                "served_models": sorted(llm.METER.served_models),
                "verification": result["verification"], "claims": result["claims"],
                "usage": {s: llm.METER.summary(s) for s in result["stages"].values()}}), indent=1))
        if key == "2":
            import approach2_graphrag

            print("== restoring the frozen graph (replaying the recorded build, no model calls)")
            config.LLM_CACHE = "replay"
            approach2_graphrag.build(reset=True, record=False)

    card = scorecard(DEMO_RUN)
    (DEMO_RUN / "scorecard.json").write_text(json.dumps(jsonable(card), indent=1))
    man = json.loads((DEMO_RUN / "manifest.json").read_text())
    print(write_comparison(DEMO_RUN, card, man, load_ground_truth()))


if __name__ == "__main__":
    main()
