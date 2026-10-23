"""Scoring, exactly as SCORING_RULE.md defines it. No LLM judge anywhere.

Unit: a (company, leaf) pair and a (company, category) pair claimed as an exposure.
Only shared exposures count, because the question asks for shared risks:
  truth     = key pairs whose label is true for >= MIN_SHARED companies of the group
  predicted = an approach's VERIFIED claims whose label it claims for >= MIN_SHARED companies
"""
from itertools import combinations

import yaml

import config
import taxonomy

GT_PATH = config.ROOT / "ground_truth.yaml"


def load_ground_truth(corpus=None):
    """The labelled key for this corpus, or None if there is none yet."""
    doc = yaml.safe_load(GT_PATH.read_text()) or {}
    section = (doc.get("corpora") or {}).get(corpus or config.CORPUS)
    if not section or not section.get("labels"):
        return None
    # A hand-edited file may have unquoted yes:/no: keys, which YAML reads as booleans.
    get = lambda v, key: set(v.get(key) or v.get(key == "yes") or [])  # noqa: E731
    yes = {str(t): get(v, "yes") for t, v in section["labels"].items()}
    decided = {str(t): get(v, "yes") | get(v, "no") for t, v in section["labels"].items()}
    return {"status": section.get("status", "draft"), "labeller": section.get("labeller", ""),
            "labelled_at": section.get("labelled_at", ""), "accessions": section.get("accessions", {}),
            "taxonomy_version": section.get("taxonomy_version"), "yes": yes, "decided": decided}


def truth_pairs(gt, tickers, level):
    pairs = set()
    for t in tickers:
        for leaf in gt["yes"].get(t, ()):
            pairs.add((t, leaf if level == "leaf" else taxonomy.category_of(leaf)))
    return _shared(pairs)


def predicted_pairs(claims, level):
    return _shared({(c["company"], c[level]) for c in claims})


def _shared(pairs):
    count = {}
    for _, label in pairs:
        count[label] = count.get(label, 0) + 1
    return {p for p in pairs if count[p[1]] >= config.MIN_SHARED}


def prf(pred, truth):
    hit = pred & truth
    p = len(hit) / len(pred) if pred else 0.0
    r = len(hit) / len(truth) if truth else 0.0
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0,
            "predicted": len(pred), "true": len(truth), "correct": len(hit)}


def evaluate(claims, gt, tickers):
    out = {"ground_truth_status": gt["status"]}
    for level in ("category", "leaf"):
        truth = truth_pairs(gt, tickers, level)
        pred = predicted_pairs(claims, level)
        out[level] = prf(pred, truth)
        out[level]["missed"] = sorted(f"{t}:{label}" for t, label in truth - pred)
        out[level]["extra"] = sorted(f"{t}:{label}" for t, label in pred - truth)
    out["unlabelled_tickers"] = sorted(t for t in tickers if not gt["decided"].get(t))
    return out


def jaccard(a, b):
    return 1.0 if not a and not b else len(a & b) / len(a | b)


def rerun_consistency(claim_sets, level="leaf"):
    """Mean pairwise Jaccard of the scored pairs across independent runs (None if fewer than 2 runs)."""
    pair_sets = [predicted_pairs(claims, level) for claims in claim_sets]
    scores = [jaccard(a, b) for a, b in combinations(pair_sets, 2)]
    return round(sum(scores) / len(scores), 3) if scores else None
