"""Audit the workshop's sample data and turn its PDFs into an offline corpus.

    python prepare_workshop_sample.py

Checks ../data/Company_Filings.csv against the PDFs in ../data/form10k-sample
and against ../data/Asset_Manager_Holdings.csv (a second source in the same
repo). Every problem is reported; the corpus keeps the CSV's labels exactly as
they are, so you can show what a pipeline does with them.
"""
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

from pypdf import PdfReader

import config
from corpus import QualityLog, write_manifest
from item1a import SMALLER_REPORTING

WORKSHOP = config.ROOT.parent
FILINGS_CSV = WORKSHOP / "data" / "Company_Filings.csv"
HOLDINGS_CSV = WORKSHOP / "data" / "Asset_Manager_Holdings.csv"
PDF_DIR = WORKSHOP / "data" / "form10k-sample"
ACCESSION = re.compile(r"^\d{10}-\d{2}-\d{6}$")
NAME_STOPWORDS = {"INC", "CORP", "CORPORATION", "HLDGS", "GROUP", "CO", "THE"}


def cusip_check_digit(first8):
    """Standard CUSIP check digit ('modulus 10 double-add-double')."""
    total = 0
    for i, ch in enumerate(first8):
        v = int(ch) if ch.isdigit() else ord(ch) - 55 if ch.isalpha() else {"*": 36, "@": 37, "#": 38}[ch]
        if i % 2:
            v *= 2
        total += v // 10 + v % 10
    return str((10 - total % 10) % 10)


def check_cusip(log, subject, cusip6, cusip):
    if len(cusip) < 9:
        log.add("WARN", "cusip_format", subject, f"cusip '{cusip}' has {len(cusip)} characters, not 9 "
                "(leading zeros lost when the CSV was saved?)")
    elif len(cusip) > 9:
        log.add("WARN", "cusip_format", subject, f"cusip '{cusip}' has {len(cusip)} characters, not 9")
    padded = cusip.zfill(9)
    if len(padded) == 9 and cusip_check_digit(padded[:8].upper()) != padded[8]:
        log.add("WARN", "cusip_check_digit", subject, f"'{padded}' fails the CUSIP check digit")
    if cusip6.zfill(6) != padded[:6]:
        log.add("WARN", "cusip6_mismatch", subject, f"cusip6 '{cusip6}' is not the first 6 characters of '{padded}'")


def pdf_text(path):
    return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)


def item1a_from_marker(text):
    """The workshop PDFs carry 'Section: Item1a' ... 'Section: Item7' markers."""
    start = text.find("Section: Item1a")
    if start < 0:
        return ""
    end = text.find("Section: Item7", start)
    body = text[start:end if end > 0 else None]
    return re.sub(r"^Section: Item1a\s*>[^\n]*\n", "", body).strip()


def first_name_token(name):
    tokens = [t for t in re.findall(r"[A-Z&]+", name.upper()) if t not in NAME_STOPWORDS]
    return tokens[0] if tokens else name


def main():
    log = QualityLog("Data quality - workshop sample (Company_Filings.csv + form10k-sample PDFs)")
    with FILINGS_CSV.open(newline="") as f:
        filings = list(csv.DictReader(f))
    with HOLDINGS_CSV.open(newline="") as f:
        holdings = list(csv.DictReader(f))

    # ---- identifiers inside Company_Filings.csv
    for name, n in Counter(r["name"] for r in filings).items():
        if n > 1:
            ciks = [r["cik"] for r in filings if r["name"] == name]
            tickers = [r["ticker"] for r in filings if r["name"] == name]
            log.add("ERROR", "duplicate_company", name, f"{n} rows, CIKs {ciks}, tickers {tickers}")
    for key in ("ticker", "cik"):
        for value, n in Counter(r[key] for r in filings).items():
            if n > 1:
                log.add("ERROR", f"duplicate_{key}", value, f"{n} rows share {key} {value}")

    # ---- cross-check against the holdings file in the same repo
    by_name = defaultdict(set)
    cusips_by_name = defaultdict(set)
    for h in holdings:
        by_name[h["companyName"].upper()].add(h["ticker"])
        cusips_by_name[h["companyName"].upper()].add(h["cusip"].zfill(9))
    for r in filings:
        subject = f"{r['name']} (row ticker {r['ticker']})"
        expected = by_name.get(r["name"].upper())
        if expected and r["ticker"] not in expected:
            log.add("ERROR", "ticker_mismatch", subject,
                    f"Asset_Manager_Holdings.csv lists {r['name']} as {sorted(expected)}")
        held = cusips_by_name.get(r["name"].upper())
        if held and r["cusip"].zfill(9) not in held:
            log.add("WARN", "cusip_conflict", subject, f"cusip {r['cusip']} vs holdings file {sorted(held)}")
        if r["cusip"] == r["cik"]:
            log.add("WARN", "cusip_equals_cik", subject, f"cusip field holds the CIK value {r['cik']}")
        check_cusip(log, subject, r["cusip6"], r["cusip"])
    for name, tickers in by_name.items():
        if len({h["cusip"] for h in holdings if h["companyName"].upper() == name}) > 1 and len(tickers) == 1:
            log.add("INFO", "share_classes", name, f"two CUSIPs (share classes) both labelled {sorted(tickers)}")
    filed_names = {r["name"].upper() for r in filings}
    for name in sorted(set(by_name) - filed_names):
        similar = [n for n in filed_names if first_name_token(n) == first_name_token(name)]
        if similar:
            log.add("WARN", "name_inconsistent", name, f"holdings file name differs from Company_Filings.csv {similar}")
        else:
            log.add("WARN", "missing_from_filings_csv", name, f"held in holdings file as "
                    f"{sorted(by_name[name])} but has no row in Company_Filings.csv")

    # ---- the PDFs themselves
    pdfs = {p.name: p for p in PDF_DIR.glob("*.pdf")}
    referenced = set()
    rows, years = [], {}
    item_dir = config.DATA_DIR / "corpus" / "workshop_sample" / "item1a"
    item_dir.mkdir(parents=True, exist_ok=True)
    for r in filings:
        subject = f"{r['name']} (row ticker {r['ticker']})"
        file_name = Path(r["path_Mac_ix"]).name
        referenced.add(file_name)
        stem = Path(file_name).stem
        if not ACCESSION.match(stem):
            log.add("WARN", "accession_format", subject, f"file name '{stem}' is not a valid accession number "
                    "(expected 10-2-6 digits)")
        elif int(stem[:10]) != int(r["cik"]):
            log.add("INFO", "accession_prefix", subject, f"accession prefix {int(stem[:10])} differs from CIK "
                    f"{r['cik']} (fine for a filing agent - worth a look otherwise)")
        if file_name not in pdfs:
            log.add("ERROR", "file_missing", subject, f"{file_name} is referenced but not in form10k-sample/")
            continue
        print(f"Reading {file_name} ...")
        text = pdf_text(pdfs[file_name])
        token = first_name_token(r["name"])
        if not re.search(rf"(?i)\b{re.escape(token)}", text[:30000]):
            opening = re.sub(r"\s+", " ", text[17:400]).strip()
            log.add("ERROR", "document_identity", subject,
                    f"'{token.title()}' never appears in the first pages; document opens: \"{opening[:160]}...\"")
        years[file_name] = stem[11:13]
        body = item1a_from_marker(text)
        if SMALLER_REPORTING.search(body[:3000]):
            log.add("ERROR", "item1a_omitted", subject, "document says smaller reporting company - no risk factors")
        elif len(body) < 8000:
            log.add("WARN", "item1a_short", subject, f"Item 1A is only {len(body):,} characters "
                    f"in a {len(PdfReader(pdfs[file_name]).pages):,}-page PDF - truncated?")
        item_file = f"item1a/{r['ticker']}.txt"
        (item_dir.parent / item_file).write_text(body)
        rows.append({"ticker": r["ticker"], "company": r["name"], "cik": r["cik"], "form": "10-K",
                     "accession": stem, "url": f"workshop:data/form10k-sample/{file_name}",
                     "item1a_chars": len(body), "item1a_file": item_file if body else "",
                     "source": "workshop_csv_as_labelled"})

    for name in sorted(set(pdfs) - referenced):
        stem = Path(name).stem
        log.add("WARN", "file_unreferenced", name, f"PDF has no row in Company_Filings.csv (CIK prefix "
                f"{int(stem[:10])}, filed 20{stem[11:13]}) - excluded from the corpus")
        years[name] = stem[11:13]
    year_counts = Counter(years.values())
    if len(year_counts) > 1:
        log.add("WARN", "mixed_years", "form10k-sample/", "filings from different years: "
                + "; ".join(f"20{y}: {', '.join(sorted(k for k, v in years.items() if v == y))}"
                            for y in sorted(year_counts)))

    corpus_dir = config.DATA_DIR / "corpus" / "workshop_sample"
    write_manifest(rows, corpus_dir)
    intro = ("Source: the Apache-2.0 Neo4j genai-workshop `financial_documents/data`. The corpus built from it "
             "keeps the CSV labels unchanged, so a ticker can point at another company's filing.")
    log.write(corpus_dir / "data_quality.md", corpus_dir / "data_quality.jsonl", intro)
    config.RESULTS_DIR.mkdir(exist_ok=True)
    (config.RESULTS_DIR / "data_quality_workshop_sample.md").write_text((corpus_dir / "data_quality.md").read_text())
    print(f"\n{len(rows)} filings -> {corpus_dir}; log -> results/data_quality_workshop_sample.md")


if __name__ == "__main__":
    main()
