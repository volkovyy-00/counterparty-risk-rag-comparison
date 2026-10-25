"""Build the offline demo page: demo/index.html with every number and quote inlined as JSON.

    python src/build_demo.py                       # from results/demo_run/
    python src/build_demo.py --run DIR --fixture   # a test fixture (fake model) - shown with a banner

No network, no Neo4j: the graph comes from results/demo_run/graph.json.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

import config
import taxonomy

DEMO = config.ROOT / "demo"
TEMPLATE = DEMO / "template.html"
WORKSHOP_DQ = config.DATA_DIR / "corpus" / "workshop_sample" / "data_quality.jsonl"
WORKSHOP_CHECKS = ("document_identity", "ticker_mismatch", "duplicate_company", "item1a_omitted", "file_missing",
                   "mixed_years", "file_unreferenced")
APPROACH_ORDER = ["1_plain_rag", "2_graphrag", "3_taxonomy_first", "0_long_context"]

# Page furniture in the 10-K text, dropped from the DISPLAYED quote and context only (offsets and verification use
# the untouched text). Whole lines, matched after stripping. The page applies the same patterns (DATA.debris).
DEBRIS = [
    (r"^(page\s*)?\d{1,3}$", "i"),                                              # page numbers
    (r"^table of contents$", "i"),
    (r"^item\s*1a\.?.{0,60}\(continued\)$", "i"),                               # "Item 1A. Risk Factors (Continued)"
    (r"^(?=.*[A-Z]{2})[^a-z]{0,80}\b(COMPANY|INC|CORPORATION|CORP|N\.V|LTD|PLC|HOLDINGS|SUBSIDIARIES)\b[^a-z]*$",
     ""),                                                                          # "GENERAL MOTORS COMPANY AND SUBSIDIARIES"
]
_DEBRIS = [re.compile(p, re.I if "i" in f else 0) for p, f in DEBRIS]
# The same furniture inside a quote whose line breaks were flattened ("... and 13 Table of Contents GENERAL MOTORS
# COMPANY AND SUBSIDIARIES logistics ..."): a page number and/or "Table of Contents", then an optional running head.
_HEAD = r"(?:[A-Z][A-Z0-9&.,'-]*\s+){0,6}(?:COMPANY|INC|CORPORATION|CORP|N\.V\.|LTD|PLC|HOLDINGS)\.?(?:\s+AND\s+SUBSIDIARIES)?"
DEBRIS_INLINE = [
    (rf"(?:^|\s)(?:\d{{1,3}}\s+)?Table of Contents(?:\s+{_HEAD})?(?=\s|$)", ""),
    (r"(?:^|\s)Item\s*1A\.?[^()]{0,60}\(Continued\)(?=\s|$)", "i"),
]
_DEBRIS_INLINE = [re.compile(p, re.I if "i" in f else 0) for p, f in DEBRIS_INLINE]


def clean_quote(quote):
    """A quote for display on one line, without page furniture (line-based first, then flattened)."""
    out = re.sub(r"\s+", " ", clean_display(quote)).strip()
    for rx in _DEBRIS_INLINE:
        out = rx.sub(" ", out)
    return re.sub(r"\s+", " ", out).strip()


def clean_display(text):
    """`text` without page-furniture lines, for display only. Never feed the result back into offsets. Where a page
    break cut a sentence (no end punctuation before, lower case after), the two halves are joined with a space."""
    lines = ["\0" if any(rx.match(ln.strip()) for rx in _DEBRIS) else ln for ln in text.split("\n")]
    out = "\n".join(lines)
    out = re.sub(r"(?<=[^.!?:;\s])\s*\0(?:\s*\0)*\s*(?=[a-z])", " ", out)
    out = re.sub(r"\n*\0(?:\s*\0)*\n*", "\n\n", out)
    return re.sub(r"\n{3,}", "\n\n", out)


def _jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _git(*args):
    try:
        return subprocess.run(["git", *args], cwd=config.ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def scoring_rule_commit():
    out = _git("log", "-1", "--format=%H|%cI", "--", "SCORING_RULE.md")
    sha, when = out.split("|") if "|" in out else (None, None)
    rule = (config.ROOT / "SCORING_RULE.md").read_text()
    section = rule.split("## Rule", 1)[1].split("\n## ", 1)[0]
    bullets = [re.sub(r"\s+", " ", b).strip() for b in re.split(r"\n- ", "\n" + section.strip()) if b.strip()]
    titles = [re.match(r"\*\*(.+?)\*\*\s*(.*)", b) for b in bullets]
    return {"sha": sha, "committed_at": when,
            "bullets": [{"title": m.group(1).rstrip("."), "text": m.group(2)} if m else {"title": "", "text": b}
                        for m, b in zip(titles, bullets)]}


def _fmt(v, kind):
    if v is None:
        return "n/a"
    return {"pct": f"{v:.0%}", "f2": f"{v:.2f}", "usd": f"${v:.2f}"}.get(kind, str(v))


def decision(card, draft=False):
    """Screen 7 from decision.yaml. A placeholder that resolves to n/a stops the build unless draft=True (then it is
    shown as [placeholder] under a DRAFT banner)."""
    d = yaml.safe_load((DEMO / "decision.yaml").read_text())
    rows = card["rows"]
    values = {}
    for name in card["columns"]:
        get = lambda key: (rows.get(key) or {}).get(name)  # noqa: E731
        leaf, cat = get("leaf_prf"), get("category_prf")
        values.update({
            f"{name}.leaf_f1": _fmt(leaf and leaf["f1"], "f2"), f"{name}.category_f1": _fmt(cat and cat["f1"], "f2"),
            f"{name}.quote_coverage": _fmt(get("quote_coverage"), "pct"),
            f"{name}.rerun_jaccard": _fmt(get("rerun_jaccard_leaf"), "f2"),
            f"{name}.companies_covered": _fmt(get("companies_covered"), ""),
            f"{name}.build_cost": _fmt((get("build") or {}).get("cost_usd"), "usd"),
            f"{name}.ask_cost": _fmt((get("ask") or {}).get("cost_usd"), "usd")})
    missing = sorted({m for m in re.findall(r"\{([\w.]+)\}", d["recommendation"]) if values.get(m, "n/a") == "n/a"})
    if missing and not draft:
        raise SystemExit("Screen 7 has placeholders with no value (n/a): " + ", ".join(missing) +
                         ". Fill the key and rebuild, or build with --draft (make demo DRAFT=1).")
    fill = lambda s: re.sub(r"\{([\w.]+)\}", lambda m: values.get(m.group(1), "n/a") if m.group(1) not in missing  # noqa: E731
                            else f"[{m.group(1)}]", s)
    f1 = {n: ((rows.get("leaf_prf") or {}).get(n) or {}).get("f1") for n in card["columns"]
          if not n.startswith("0_")}
    best = max((n for n in f1 if f1[n] is not None), key=lambda n: f1[n], default=None)
    if best and best not in d["recommendation"].split("{")[0] and best.split("_", 1)[1].replace("_", "-") \
            not in d["recommendation"].lower():
        print(f"WARNING: decision.yaml recommends something other than the best leaf-F1 approach ({best}). "
              "Re-read screen 7 against the scorecard.", file=sys.stderr)
    return {"when_to_use": d["when_to_use"], "recommendation": fill(d["recommendation"]), "caveat": d["caveat"],
            "missing": missing}


def load_run(run_dir, fixture):
    run_dir = Path(run_dir)
    man = json.loads((run_dir / "manifest.json").read_text())
    served = man.get("served_models", [])
    fake = any(m.startswith(("fake", "unknown")) for m in served)
    if fake and not fixture:
        raise SystemExit(f"{run_dir} was produced by {served}: not real model output. Use --fixture to preview it.")
    approaches = {}
    for name in APPROACH_ORDER:
        path = run_dir / f"approach_{name}.json"
        if path.exists():
            r = json.loads(path.read_text())
            if "error" not in r:
                r["rejected"] = r.get("rejected", [])[:200]
                r.pop("raw_claims", None)
            approaches[name] = r
    card = json.loads((run_dir / "scorecard.json").read_text())
    reruns = {name: len(list((run_dir / "reruns" / name).glob("run_*.json"))) + 1
              for name in approaches if (run_dir / "reruns" / name).exists()}
    return man, approaches, card, reruns, fake


def build(run_dir, out, fixture=False, draft=False):
    man, approaches, card, reruns, fake = load_run(run_dir, fixture)
    run_dir = Path(run_dir)
    corpus_dir = config.DATA_DIR / "corpus" / man["corpus"]
    texts = {f["ticker"]: (corpus_dir / "item1a" / f"{f['ticker']}.txt").read_text() for f in man["filings"]
             if (corpus_dir / "item1a" / f"{f['ticker']}.txt").exists()}
    dq = _jsonl(run_dir / "corpus_data_quality.jsonl")
    workshop = [i for i in _jsonl(WORKSHOP_DQ) if i["check"] in WORKSHOP_CHECKS]
    graph_path = run_dir / "graph.json"
    qa_path = run_dir / "graph_qa.json"
    gov_path = run_dir / "governance.json"
    est_path = run_dir / "estimates.json"
    estimates = json.loads(est_path.read_text()) if est_path.exists() else {}
    from evaluate import load_ground_truth

    gt = load_ground_truth(man["corpus"])
    data = {
        "meta": {"question": man["question"], "group": man["group"], "corpus": man["corpus"], "model": man["model"],
                 "served_models": man.get("served_models", []), "created_at": man["created_at"],
                 "git": man.get("git", {}), "pricing_checked": man.get("pricing_checked"), "fixture": fake,
                 "key_status": gt["status"] if gt else "none", "labeller": gt["labeller"] if gt else "",
                 "effort": man.get("effort"), "embed_model": man.get("embed_model"), "knobs": man.get("knobs", {}),
                 "min_shared": man["knobs"]["min_shared"], "draft": draft,
                 "rebuild_usd": estimates.get("approach2_rebuild_usd")},
        "debris": DEBRIS, "debris_inline": DEBRIS_INLINE,
        "scoring_rule": scoring_rule_commit(),
        "filings": [dict(f, industry=config.INDUSTRY.get(f["ticker"], "other"),
                         short_name=config.DISPLAY_NAMES.get(f["ticker"], f["company"])) for f in man["filings"]],
        "texts": texts,
        "dq": {"edgar": dq, "workshop": workshop},
        "approaches": approaches,
        "scorecard": card,
        "reruns": reruns,
        "graph": json.loads(graph_path.read_text()) if graph_path.exists() else None,
        "graph_qa": json.loads(qa_path.read_text()) if qa_path.exists() else None,
        "governance": json.loads(gov_path.read_text()) if gov_path.exists() else None,
        "decision": decision(card, draft),
        "taxonomy": {"version": taxonomy.VERSION,
                     "categories": [{"id": c, "name": taxonomy.CATEGORY_NAMES[c]} for c in taxonomy.CATEGORY_IDS],
                     "leaves": [{"id": lid, "category": leaf["category"], "description": leaf["description"],
                                 "label": taxonomy.leaf_label(lid)} for lid, leaf in taxonomy.LEAVES.items()]},
    }
    html = TEMPLATE.read_text().replace("/*__DATA__*/null", json.dumps(data).replace("</", "<\\/"))
    out = Path(out)
    out.write_text(html)
    print(f"-> {config.rel(out)} ({len(html) / 1e6:.1f} MB){' - TEST FIXTURE' if fake else ''}")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", default=str(config.RESULTS_DIR / "demo_run"))
    parser.add_argument("--out", default=str(DEMO / "index.html"))
    parser.add_argument("--fixture", action="store_true", help="allow a fake-model run (shown with a banner)")
    parser.add_argument("--draft", action="store_true", help="allow screen-7 placeholders with no value (DRAFT banner)")
    args = parser.parse_args()
    if not (Path(args.run) / "manifest.json").exists():
        raise SystemExit(f"No recorded run in {args.run}. See README: the real run is frozen with real_run.py.")
    build(args.run, args.out, args.fixture, args.draft)


if __name__ == "__main__":
    main()
