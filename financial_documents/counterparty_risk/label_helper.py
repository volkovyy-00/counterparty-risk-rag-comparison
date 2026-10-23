"""Help a human hand-label ground_truth.yaml: for every company x category, show
how often the category's keywords occur in Item 1A and the first matching sentence.

    python label_helper.py            # writes results/labelling_worksheet_<corpus>.md

This only points you at evidence. The labels in ground_truth.yaml are a human
judgement; nothing here writes to that file.
"""
import re

import config
from answer import TAXONOMY, _KEYWORDS
from corpus import load_corpus


def main():
    filings = load_corpus()
    lines = [f"# Labelling worksheet - {config.CORPUS}", "",
             "Keyword hits per Item 1A (a hint, not a label). Read the sentence, then decide.", ""]
    header = "| Category | " + " | ".join(f["ticker"] for f in filings) + " |"
    lines += [header, "|---" * (len(filings) + 1) + "|"]
    sentences = {f["ticker"]: re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", f["text"])) for f in filings}
    examples = []
    for c in TAXONOMY:
        cells = []
        for f in filings:
            hits = [s for s in sentences[f["ticker"]] if any(p.search(s) for p in _KEYWORDS[c["id"]])]
            cells.append(str(len(hits)) if hits else ".")
            if hits:
                examples.append(f"- **{c['id']} / {f['ticker']}**: {hits[0][:220]}")
        lines.append(f"| {c['id']} | " + " | ".join(cells) + " |")
    lines += ["", "## First matching sentence", ""] + examples
    out = config.RESULTS_DIR / f"labelling_worksheet_{config.CORPUS}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines[: len(TAXONOMY) + 6]))
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
