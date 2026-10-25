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


# --------------------------------------------------------------------------- risk-factor sections (approach 3)
# Item 1A puts each risk factor under a one-sentence heading on its own line, grouped under short
# sub-captions ("Risks Related to ..."). Plain line rules, no model. Tuned on the edgar_latest filings
# (25 Oct 2026) and then frozen: tests pin the section count per filing.
_LINE = re.compile(r"[^\n]+")
_BULLETS = "•·▪ \t"
_DEBRIS = [re.compile(p) for p in (r"^\d{1,3}$", r"(?i)^item\s*1a\b.*\(continued\)$", r"(?i)^table of contents$",
                                   r"(?i)^page \d+", r"^[^a-z]*[A-Z][^a-z]*$")]  # page numbers, running heads
_SUBCAPTION = re.compile(r"(?i)\brisks?\b|\brelat(?:ed|ing) to\b|\buncertainties\b")
_SUBCAPTION_DOT = re.compile(r"(?i)^risks? (?:related|relating) to\b")  # "Risks related to X." with a period
_NOT_HEADING = re.compile(r"(?i)^(?:in addition|additionally|furthermore|moreover|for example|also|these|this|such|"
                          r"as a result|accordingly|however|further|similarly|finally|likewise|in particular|"
                          r"consequently|based on|any of these|historically)\b")
MIN_SECTIONS = 8  # fewer headings than this: the filing falls back to fixed windows
MAX_SECTION_FACTOR = 3  # a section over this many windows long also falls back


def _clean(line):
    return " ".join(line.strip().lstrip(_BULLETS).split())


def _is_debris(line):
    return any(p.search(line) for p in _DEBRIS)


def _line_kind(line, next_line):
    """'debris' | 'subcaption' | 'heading' | 'body' for one cleaned line."""
    if _is_debris(line):
        return "debris"
    words = len(line.split())
    if line[:1].isupper() and ((words <= 16 and _SUBCAPTION_DOT.search(line)) or (
            words <= 12 and not line.endswith((".", ":", ";", ",")) and _SUBCAPTION.search(line))):
        return "subcaption"
    if (6 <= words <= 60 and line.endswith(".") and (line[:1].isupper() or line[:1] in "\"“")
            and not _NOT_HEADING.search(line) and len(next_line) > len(line)):
        return "heading"
    return "body"


def split_risk_factors(text):
    """Ordered risk-factor sections of an Item 1A text.

    Each section is {idx, start, end, subcaption, heading, text}; text == source[start:end], so offsets
    stay exact (page-break debris stays inside the text). idx 0 is anything before the first heading.
    """
    lines = [(m.start(), _clean(m.group())) for m in _LINE.finditer(text)]
    lines = [(s, ln) for s, ln in lines if ln]
    bounds, subcaption, pending, pending_body = [], "", None, False  # bounds: (start, heading, subcaption)
    for i, (start, line) in enumerate(lines):
        next_line = next((ln for _, ln in lines[i + 1:] if not _is_debris(ln)), "")
        kind = _line_kind(line, next_line)
        if kind == "subcaption":
            if pending is not None and pending_body:  # text under a sub-caption with no heading: a summary list
                bounds.append((pending, f"({subcaption})", ""))
                pending = None
            subcaption, pending_body = line.rstrip("."), False
            pending = start if pending is None else pending
        elif kind == "heading":
            bounds.append((start if pending is None else pending, line, subcaption))
            pending = None
        elif kind == "body" and pending is not None:
            pending_body = True
    if not bounds or text[:bounds[0][0]].strip():
        bounds.insert(0, (0, "(introduction)", ""))
    sections = []
    for n, (start, heading, sub) in enumerate(bounds):
        end = bounds[n + 1][0] if n + 1 < len(bounds) else len(text)
        end = start + len(text[start:end].rstrip())
        sections.append({"idx": len(sections) if bounds[0][1] == "(introduction)" else len(sections) + 1,
                         "start": start, "end": end, "subcaption": sub, "heading": heading, "text": text[start:end]})
    return sections


_FIRST_SENTENCE = re.compile(r"^(.{20,600}?[.!?])(?=\s+[A-Z“\"(]|\s*$)")
_LIST_INTRO = re.compile(r"(?i)^(?:we have listed|the following|set forth below|below (?:is|are))\b")


def split_paragraphs(text):
    """Sections for a filing whose headings run into the paragraph (bold lost in extraction).

    A paragraph starts a section when its first sentence reads like a heading (6-60 words, not a
    continuation such as "In addition") and more text follows on the same line; that sentence is the
    heading. Continuation paragraphs that also look like this become their own sections, so these
    filings split a little finer than the heading split. Same section dicts as split_risk_factors.
    """
    bounds = []
    for m in _LINE.finditer(text):
        line = _clean(m.group())
        first = _FIRST_SENTENCE.match(line)
        if not first or _is_debris(line) or _LIST_INTRO.search(line):
            continue
        heading = first.group(1)
        if (6 <= len(heading.split()) <= 60 and (line[:1].isupper() or line[:1] in "\"“")
                and not _NOT_HEADING.search(line) and len(line) > len(heading) + 80):
            bounds.append((m.start(), heading))
    if not bounds or text[:bounds[0][0]].strip():
        bounds.insert(0, (0, "(introduction)"))
    sections = []
    for n, (start, heading) in enumerate(bounds):
        end = bounds[n + 1][0] if n + 1 < len(bounds) else len(text)
        end = start + len(text[start:end].rstrip())
        sections.append({"idx": len(sections) if bounds[0][1] == "(introduction)" else len(sections) + 1,
                         "start": start, "end": end, "subcaption": "", "heading": heading, "text": text[start:end]})
    return sections


def split_check(sections, size):
    """None if the heading split is usable, else the reason to fall back to fixed windows."""
    headed = [s for s in sections if not s["heading"].startswith("(")]
    if len(headed) < MIN_SECTIONS:
        return (f"{len(headed)} heading line(s) found, fewer than {MIN_SECTIONS}: headings likely run into the "
                "paragraph")
    big = max(sections, key=lambda s: len(s["text"]))
    if len(big["text"]) > MAX_SECTION_FACTOR * size:
        return f"section {big['idx']} is {len(big['text']):,} chars (> {MAX_SECTION_FACTOR}x the {size:,} window)"
    return None


def section_marker(section, part=None):
    sub = f"\nSub-caption: {section['subcaption']}" if section["subcaption"] else ""
    tail = f" (part {part[0]}/{part[1]})" if part else ""
    return f"[RF {section['idx']}] {section['heading']}{tail}{sub}"


def pack_sections(sections, size):
    """Windows of whole sections, each up to ~size characters: list of (text, [section idx, ...]).

    A section never straddles two windows. One that is longer than `size` is cut on paragraphs, and every
    part carries the section's marker again.
    """
    units = []
    for s in sections:
        if len(s["text"]) <= size:
            units.append((s["idx"], f"{section_marker(s)}\n\n{s['text']}"))
            continue
        parts = chunk_text(s["text"], size, 0)
        units += [(s["idx"], f"{section_marker(s, (k + 1, len(parts)))}\n\n{p}") for k, (_, p) in enumerate(parts)]
    windows, text, idxs = [], "", []
    for idx, unit in units:
        if text and len(text) + len(unit) + 2 > size:
            windows.append((text, idxs))
            text, idxs = "", []
        text = f"{text}\n\n{unit}" if text else unit
        idxs = idxs if idx in idxs else idxs + [idx]
    if text:
        windows.append((text, idxs))
    return windows


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
