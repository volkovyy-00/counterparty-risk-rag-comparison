"""Tiny eval: compare each approach's (company, risk category) claims with ground_truth.yaml.

Approach 3 answers in taxonomy ids already. Approaches 1 and 2 answer in free
text, so their risk names are mapped onto categories with the keyword lists in
taxonomy.yaml - deterministic, no LLM judge, and reported alongside the score
(an unmapped risk scores nothing).
"""
import yaml

import config
from answer import CATEGORY_IDS, categories_for


def load_ground_truth(corpus=None):
    gt = yaml.safe_load((config.ROOT / "ground_truth.yaml").read_text())
    section = gt["corpora"].get(corpus or config.CORPUS)
    if section is None:
        return None
    return {"status": section.get("status", "draft"), "labelled_against": section.get("labelled_against", ""),
            "exposures": {t: set(c or []) for t, c in section["exposures"].items()}}


def predicted_pairs(result):
    pairs, unmapped = set(), []
    for risk in result["shared_risks"]:
        cats = [risk["category"]] if risk.get("category") else categories_for(risk["risk"])
        if not cats:
            unmapped.append(risk["risk"])
        pairs |= {(t, c) for t in risk["tickers"] for c in cats}
    return pairs, unmapped


def evaluate(result, gt, tickers):
    tickers = set(tickers)
    exposures = {t: cats for t, cats in gt["exposures"].items() if t in tickers}
    # The question asks for shared risks, so only categories shared in the ground truth count.
    shared = {c for c in CATEGORY_IDS if sum(c in cats for cats in exposures.values()) >= config.MIN_SHARED}
    truth = {(t, c) for t, cats in exposures.items() for c in cats if c in shared}
    pred, unmapped = predicted_pairs(result)
    hit = pred & truth
    p = len(hit) / len(pred) if pred else 0.0
    r = len(hit) / len(truth) if truth else 0.0
    found = {c for c in shared if sum((t, c) in hit for t in exposures) >= config.MIN_SHARED}
    return {
        "precision": round(p, 3), "recall": round(r, 3),
        "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0,
        "pairs_predicted": len(pred), "pairs_true": len(truth), "pairs_correct": len(hit),
        "shared_categories_true": len(shared), "shared_categories_found": len(found),
        "missed_categories": sorted(shared - found),
        "unmapped_risks": unmapped,
        "ground_truth_status": gt["status"],
    }
