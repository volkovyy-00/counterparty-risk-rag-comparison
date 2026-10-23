"""Help a person hand-label ground_truth.yaml: candidate sentences per (company, leaf).

    python label_helper.py      # results/labelling_worksheet_<corpus>.md + labelling_candidates_<corpus>.json

For every company and every taxonomy leaf it lists up to three Item 1A sentences
that contain the leaf's keywords, best first, with their character offsets. This
only points at evidence: a keyword hit is not a label, and a cell with no hit
can still be a "yes". Labels are a human decision, made in label_tool.py.
"""
import json
import re

import config
import taxonomy
from corpus import load_corpus

MAX_CANDIDATES = 3


def sentences_with_offsets(text):
    for m in re.finditer(r"[^.!?]+[.!?]", text):
        s = " ".join(m.group().split())
        if 40 <= len(s) <= 600:
            yield m.start(), m.end(), s


def candidates(filings):
    """{ticker: {leaf: [{start, end, text, hits}]}} - keyword hits, most hits first."""
    out = {}
    for f in filings:
        sents = list(sentences_with_offsets(f["text"]))
        out[f["ticker"]] = {}
        for leaf, patterns in taxonomy.LEAF_KEYWORDS.items():
            scored = []
            for start, end, s in sents:
                hits = sum(bool(p.search(s)) for p in patterns)
                if hits:
                    scored.append({"start": start, "end": end, "text": s, "hits": hits})
            scored.sort(key=lambda c: (-c["hits"], c["start"]))
            out[f["ticker"]][leaf] = {"count": len(scored), "top": scored[:MAX_CANDIDATES]}
    return out


def main():
    filings = load_corpus()
    cands = candidates(filings)
    tickers = [f["ticker"] for f in filings]
    config.RESULTS_DIR.mkdir(exist_ok=True)
    payload = {"corpus": config.CORPUS, "group": config.GROUP, "taxonomy_version": taxonomy.VERSION,
               "filings": [{k: f[k] for k in ("ticker", "company", "accession", "report_date", "url")} for f in filings],
               "leaves": {lid: {"category": leaf["category"], "description": leaf["description"]}
                          for lid, leaf in taxonomy.LEAVES.items()},
               "candidates": cands}
    (config.RESULTS_DIR / f"labelling_candidates_{config.CORPUS}.json").write_text(json.dumps(payload))

    lines = [f"# Labelling worksheet - {config.CORPUS} ({config.GROUP})", "",
             "Keyword hits per Item 1A sentence (a pointer, not a label). Decide each cell in label_tool.py.", "",
             "| Leaf | " + " | ".join(tickers) + " |", "|---" * (len(tickers) + 1) + "|"]
    for leaf in taxonomy.LEAF_IDS:
        lines.append(f"| {leaf} | " + " | ".join(str(cands[t][leaf]["count"] or ".") for t in tickers) + " |")
    lines += ["", "## Candidate sentences", ""]
    for t in tickers:
        lines += [f"### {t}", ""]
        for leaf in taxonomy.LEAF_IDS:
            for c in cands[t][leaf]["top"][:1]:
                lines.append(f"- **{leaf}** (chars {c['start']}-{c['end']}): {c['text'][:300]}")
        lines.append("")
    out = config.RESULTS_DIR / f"labelling_worksheet_{config.CORPUS}.md"
    out.write_text("\n".join(lines) + "\n")
    cells = len(tickers) * len(taxonomy.LEAF_IDS)
    print(f"{len(tickers)} companies x {len(taxonomy.LEAF_IDS)} leaves = {cells} cells to decide\n-> {out}")


if __name__ == "__main__":
    main()
