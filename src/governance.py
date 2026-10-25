"""The three governance moments - offline, deterministic, no model call.

    python src/governance.py        # -> results/demo_run/governance.json (the fallback the page shows
                                #    if it is opened without serve.py)

(a) fabricated : a planted, clearly labelled paraphrase of a real Item 1A sentence
                 goes through the real verifier and is rejected; the closest real
                 sentence is shown.
(b) off_taxonomy : a planted claim labelled SUPPLY_GEOPOLITICS goes through the code
                 validator (not the provider's enum) and is rejected.
(c) audit      : two recorded runs whose manifests differ in prompt or model version;
                 the manifest diff and the heatmap cells that changed.
"""
import difflib
import json
import re
from pathlib import Path

import config
import manifest
import taxonomy
from corpus import load_corpus
from verify import closest_sentence, locate, verify_claims

DEMO_RUN = config.RESULTS_DIR / "demo_run"
AUDIT_B = DEMO_RUN / "audit" / "run_b"
PLANTED = "PLANTED FOR THIS DEMO - written by code, not by a model and not by the filer"
OFF_TAXONOMY_LABEL = ("SUPPLY_GEOPOLITICS", "SUPPLY_GEOPOLITICS.taiwan_chips")

# Mechanical paraphrase rules: the kind of drift a model makes when it "quotes" from memory.
_PARAPHRASE = [(r"\bcould\b", "might"), (r"\bmay\b", "might"), (r"\badversely affect(ed)?\b", "hurt"),
               (r"\bmaterially\b", "significantly"), (r"\bour\b", "the company's"), (r"\bwe\b", "the company"),
               (r"\bWe\b", "The company"), (r"\bOur\b", "The company's"), (r"\bresults of operations\b", "results"),
               (r"\bfinancial condition\b", "finances")]


def paraphrase(sentence):
    out = sentence
    for pattern, repl in _PARAPHRASE:
        out = re.sub(pattern, repl, out)
    return out


def _approach(run_dir, name):
    path = Path(run_dir) / f"approach_{name}.json"
    return json.loads(path.read_text()) if path.exists() else None


def _source_claim(filings, run_dir=DEMO_RUN):
    """A deterministic real claim to start from: approach 3's first verified claim on a preferred leaf."""
    result = _approach(run_dir, "3_taxonomy_first")
    claims = sorted((result or {}).get("claims", []), key=lambda c: (c["company"], c.get("start", 0)))
    for leaf in ("SUPPLY_CHAIN.semiconductor_supply", "GEOPOLITICAL_TRADE.tariffs", "SUPPLY_CHAIN.single_source"):
        for c in claims:
            if c["leaf"] == leaf and paraphrase(c["quote"]) != c["quote"]:
                return c
    for c in claims:
        if paraphrase(c["quote"]) != c["quote"]:
            return c
    f = filings[0]  # no run yet: first long sentence of the first filing
    s = next(s for s in re.split(r"(?<=[.!?])\s+", " ".join(f["text"].split())) if len(s) > 80
             and paraphrase(s) != s)
    return {"company": f["ticker"], "category": "OTHER", "leaf": "OTHER.stock_governance", "quote": s}


def fabricated(filings, run_dir=DEMO_RUN):
    src = _source_claim(filings, run_dir)
    planted = dict(src, quote=paraphrase(src["quote"]), source_ref="planted")
    accepted, rejected, _ = verify_claims([planted], filings)
    text = next(f["text"] for f in filings if f["ticker"] == src["company"])
    closest, score = closest_sentence(planted["quote"], text)
    span = locate(closest, text) if closest else None
    return {"label": PLANTED, "company": src["company"], "leaf": src["leaf"], "planted_quote": planted["quote"],
            "verdict": "accepted" if accepted else "rejected",
            "reason": rejected[0]["reason"] if rejected else None,
            "closest_real_sentence": closest, "similarity": score, "closest_span": span}


def off_taxonomy(filings, run_dir=DEMO_RUN):
    src = _source_claim(filings, run_dir)
    category, leaf = OFF_TAXONOMY_LABEL
    planted = dict(src, category=category, leaf=leaf, source_ref="planted")
    accepted, rejected, _ = verify_claims([planted], filings)
    return {"label": PLANTED, "company": src["company"], "quote": src["quote"], "category": category, "leaf": leaf,
            "verdict": "accepted" if accepted else "rejected",
            "reason": rejected[0]["reason"] if rejected else None,
            "check": rejected[0]["check"] if rejected else None,
            "taxonomy_version": taxonomy.VERSION, "categories": len(taxonomy.CATEGORY_IDS),
            "leaves": len(taxonomy.LEAF_IDS),
            "nearest_valid": difflib.get_close_matches(category, taxonomy.CATEGORY_IDS, n=2, cutoff=0.3),
            "note": "The validator rejects; it never re-maps a label the model invented."}


def audit(run_a=DEMO_RUN, run_b=AUDIT_B):
    """Manifest diff and changed heatmap cells between two recorded runs (approach 3)."""
    run_a, run_b = Path(run_a), Path(run_b)
    if not (run_a / "manifest.json").exists() or not (run_b / "manifest.json").exists():
        return {"available": False, "reason": f"needs {config.rel(run_a)}/ and {config.rel(run_b)}/ - see real_run.py"}
    ma, mb = (json.loads((d / "manifest.json").read_text()) for d in (run_a, run_b))
    shown = ("label", "model", "served_models", "taxonomy_prompt_version", "taxonomy_split",
             "prompt_sha256.3_taxonomy_first",
             "taxonomy_version", "taxonomy_sha256", "corpus_manifest_sha256", "git.sha", "created_at", "cache_mode")
    rows = []
    flat_diff = {k: (a, b) for k, a, b in manifest.diff(ma, mb)}
    for key in shown:
        a, b = _get(ma, key), _get(mb, key)
        rows.append({"field": key, "a": a, "b": b, "changed": key in flat_diff or a != b})
    ra, rb = _approach(run_a, "3_taxonomy_first"), _approach(run_b, "3_taxonomy_first")
    changed = {}
    for level in ("category", "leaf"):
        cells = []
        for label, row in ra["matrix"][level].items():
            for t, va in row.items():
                vb = rb["matrix"][level].get(label, {}).get(t, 0)
                if va != vb:
                    cells.append({"label": label, "ticker": t, "a": va, "b": vb, "flip": (va > 0) != (vb > 0)})
        changed[level] = cells
    return {"available": True, "manifest_rows": rows, "changed_cells": changed,
            "a": {"label": ma.get("label"), "created_at": ma["created_at"]},
            "b": {"label": mb.get("label"), "created_at": mb["created_at"]}}


def _get(d, dotted):
    for part in dotted.split("."):
        d = d.get(part) if isinstance(d, dict) else None
    return d


def run_all(run_dir=DEMO_RUN):
    filings = load_corpus()
    return {"fabricated": fabricated(filings, run_dir), "off_taxonomy": off_taxonomy(filings, run_dir),
            "audit": audit(run_dir, Path(run_dir) / "audit" / "run_b")}


if __name__ == "__main__":
    out = run_all()
    DEMO_RUN.mkdir(parents=True, exist_ok=True)
    (DEMO_RUN / "governance.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk in ("verdict", "reason", "available")}
                      for k, v in out.items()}, indent=1))
