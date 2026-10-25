"""Hand-check set for the GraphRAG graph: a person fills in yes/no, nothing is pre-filled.

    python src/graph_check.py            # -> results/graph_check_<version>.csv (30 mentions + 20 merge decisions)
    python src/graph_check.py --score    # precision per question once the CSV is filled in (y/n)

Mentions: 30 random verified RiskMentions (fixed seed). Merges: the 10 approved and 10 rejected candidate pairs
closest to the cosine threshold GRAPH_SIM_MIN - the decisions most likely to be wrong.
"""
import argparse
import csv
import json
import random

import config

QUESTIONS = ["real_risk_factor_in_this_text", "quote_supports_the_name", "name_not_vaguer_than_text",
             "merge_correct"]
FIELDS = ["kind", "id", "ticker", "risk_name_or_pair", "quote_or_scores", *QUESTIONS, "notes"]


def path(version=None):
    return config.RESULTS_DIR / f"graph_check_{version or config.GRAPH_PROMPT_VERSION}.csv"


def make(snap, audit, n_mentions=30, n_merges=10, seed=7):
    rows = []
    for m in random.Random(seed).sample(snap["mentions"], min(n_mentions, len(snap["mentions"]))):
        rows.append({"kind": "mention", "id": m["id"], "ticker": m["ticker"], "risk_name_or_pair": m["risk_name"],
                     "quote_or_scores": m["quote"]})
    pairs = audit.get("candidate_pairs", [])
    dist = lambda p: abs(p["cos"] - config.GRAPH_SIM_MIN)  # noqa: E731
    for decision in ("merged", "kept apart"):
        for p in sorted((p for p in pairs if p["decision"] == decision), key=dist)[:n_merges]:
            rows.append({"kind": f"merge ({decision})", "id": "", "ticker": "",
                         "risk_name_or_pair": f"{p['a']}  <->  {p['b']}",
                         "quote_or_scores": f"cosine {p['cos']:.3f}, lexical {p['lex']:.0f}"})
    for r in rows:
        for q in QUESTIONS:
            r.setdefault(q, "")
        r.setdefault("notes", "")
    return rows


def write(rows, out):
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def score(csv_path):
    """Share of 'y' among the filled answers, per question. Unfilled cells are not counted."""
    with csv_path.open() as f:
        rows = list(csv.DictReader(f))
    out = {}
    for q in QUESTIONS:
        answers = [r[q].strip().lower()[:1] for r in rows if r[q].strip()]
        answers = [a for a in answers if a in ("y", "n")]
        out[q] = {"filled": len(answers), "precision": round(answers.count("y") / len(answers), 3) if answers else None}
    return out


if __name__ == "__main__":
    from approach2_graphrag import snapshot_path

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--score", action="store_true")
    args = parser.parse_args()
    if args.score:
        print(json.dumps(score(path()), indent=1))
    else:
        if config.GRAPH_PROMPT_VERSION != "graph-v2":
            raise SystemExit("The hand-check set needs graph-v2 (v1 stores no quotes or merge decisions).")
        snap = json.loads(snapshot_path().read_text())
        audit = json.loads((config.RESULTS_DIR / f"graph_resolution_{config.CORPUS}.json").read_text())
        rows = make(snap, audit)
        write(rows, path())
        print(f"{len(rows)} rows -> {config.rel(path())} - fill y/n in the question columns, then --score")
