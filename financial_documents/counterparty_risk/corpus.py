"""Reading the prepared corpus, chunking, and the data-quality log format."""
import csv
import json
import re
from dataclasses import asdict, dataclass

import config

MANIFEST_FIELDS = ["ticker", "company", "cik", "form", "accession", "filing_date", "report_date",
                   "fiscal_year_end", "url", "item1a_chars", "item1a_file", "source"]


# --------------------------------------------------------------------------- data-quality log
@dataclass
class Issue:
    severity: str  # ERROR | WARN | INFO
    check: str
    subject: str  # ticker, row or file the issue is about
    detail: str


class QualityLog:
    """Collects data-quality findings. Findings are reported, never auto-fixed."""

    def __init__(self, title):
        self.title, self.issues = title, []

    def add(self, severity, check, subject, detail):
        self.issues.append(Issue(severity, check, subject, detail))
        print(f"  [{severity}] {check} - {subject}: {detail}")

    def write(self, path_md, path_jsonl, intro=""):
        path_md.parent.mkdir(parents=True, exist_ok=True)
        with path_jsonl.open("w") as f:
            for issue in self.issues:
                f.write(json.dumps(asdict(issue)) + "\n")
        counts = {s: sum(i.severity == s for i in self.issues) for s in ("ERROR", "WARN", "INFO")}
        lines = [f"# {self.title}", "", intro, "",
                 f"**{counts['ERROR']} errors, {counts['WARN']} warnings, {counts['INFO']} notes.** "
                 "Nothing below was corrected automatically.", "",
                 "| Severity | Check | Subject | Detail |", "|---|---|---|---|"]
        order = {"ERROR": 0, "WARN": 1, "INFO": 2}
        for i in sorted(self.issues, key=lambda i: (order[i.severity], i.check, i.subject)):
            lines.append(f"| {i.severity} | {i.check} | {i.subject} | {i.detail.replace('|', '/')} |")
        path_md.write_text("\n".join(lines) + "\n")


# --------------------------------------------------------------------------- corpus
def write_manifest(rows, corpus_dir):
    corpus_dir.mkdir(parents=True, exist_ok=True)
    with (corpus_dir / "manifest.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in MANIFEST_FIELDS})


def load_corpus(corpus_dir=None):
    """Return a list of filing dicts (manifest row + 'text' = Item 1A)."""
    corpus_dir = corpus_dir or config.CORPUS_DIR
    manifest = corpus_dir / "manifest.csv"
    if not manifest.exists():
        raise SystemExit(f"No corpus at {manifest}. Run fetch_10k.py (or prepare_workshop_sample.py) first.")
    filings = []
    with manifest.open() as f:
        for row in csv.DictReader(f):
            if row["item1a_file"]:
                row["text"] = (corpus_dir / row["item1a_file"]).read_text()
                filings.append(row)
    return filings


def chunk_text(text, size, overlap):
    """Split on paragraph boundaries into ~size-character chunks; returns (start, chunk) pairs."""
    paragraphs = [(m.start(), m.group()) for m in re.finditer(r"[^\n]+(?:\n(?!\n)[^\n]+)*", text)]
    chunks, current, current_start = [], "", 0
    for start, para in paragraphs:
        if current and len(current) + len(para) > size:
            chunks.append((current_start, current))
            tail = current[-overlap:] if overlap else ""
            current, current_start = tail, current_start + len(current) - len(tail)
        if not current:
            current_start = start
        current = f"{current}\n\n{para}" if current else para
        while len(current) > size * 1.5:  # one very long paragraph
            chunks.append((current_start, current[:size]))
            current, current_start = current[size - overlap:], current_start + size - overlap
    if current.strip():
        chunks.append((current_start, current))
    return chunks


def chunks_for(filings, size, overlap):
    out = []
    for filing in filings:
        for n, (start, text) in enumerate(chunk_text(filing["text"], size, overlap)):
            out.append({"chunk_id": f"{filing['ticker']}-{n:03d}", "ticker": filing["ticker"],
                        "company": filing["company"], "accession": filing["accession"],
                        "start": start, "text": text})
    return out


# --------------------------------------------------------------------------- verbatim checks
def find_quote(quote, source):
    """Start offset of `quote` in `source` (typography/whitespace tolerant), or -1. See verify.locate."""
    from verify import locate

    span = locate(quote, source)
    return span[0] if span else -1
