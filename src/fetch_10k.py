"""Step 1: download the latest 10-K for each ticker from SEC EDGAR and cut out Item 1A.

    SEC_USER_AGENT="Your Name your.email@example.com" python src/fetch_10k.py

Follows SEC fair-access rules: a declared User-Agent, at most SEC_MAX_RPS
requests per second (default 5, never above 10), back-off on 429/503, and every
response cached on disk so a re-run does not hit SEC again.
Data-quality problems are logged to data_quality.md - never silently fixed.
"""
import argparse
import hashlib
import json
import re
import threading
import time
from datetime import date, datetime

import requests

import config
from corpus import QualityLog, write_manifest
from item1a import SMALLER_REPORTING, extract_item1a, html_to_text

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{doc}"
RAW_DIR = config.DATA_DIR / "raw" / "sec"
CORPORATE_ACTION = re.compile(r"(?i)[^.]{0,200}\b(spin-?off|spun off|separation of|split-?off)\b[^.]{0,200}\.")


class SecClient:
    def __init__(self, user_agent, max_rps):
        if not user_agent or "@" not in user_agent:
            raise SystemExit('Set SEC_USER_AGENT="Your Name your.email@example.com" (SEC requires it).')
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"})
        self.min_interval, self._last, self._lock = 1.0 / max_rps, 0.0, threading.Lock()

    def get(self, url):
        cached = RAW_DIR / hashlib.sha256(url.encode()).hexdigest()[:24]
        if cached.exists():
            return cached.read_bytes()
        for attempt in range(5):
            with self._lock:
                wait = self._last + self.min_interval - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                self._last = time.monotonic()
            resp = self.session.get(url, timeout=60)
            if resp.status_code in (429, 503):
                delay = float(resp.headers.get("Retry-After", 2 ** (attempt + 1)))
                print(f"  SEC returned {resp.status_code}; waiting {delay:.0f}s")
                time.sleep(delay)
                continue
            resp.raise_for_status()
            RAW_DIR.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(resp.content)
            return resp.content
        raise RuntimeError(f"SEC kept refusing {url}")


def latest_10k(submissions):
    """Most recent original 10-K in the 'recent' block, plus any later 10-K/A."""
    recent = submissions["filings"]["recent"]
    rows = [dict(zip(recent, values)) for values in zip(*recent.values())]
    rows.sort(key=lambda r: r["filingDate"], reverse=True)
    original = next((r for r in rows if r["form"] == "10-K"), None)
    amendments = [r for r in rows if r["form"] == "10-K/A" and original and r["filingDate"] > original["filingDate"]]
    other_annual = sorted({r["form"] for r in rows if r["form"] in ("20-F", "40-F", "10-KT")})
    return original, amendments, other_annual


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tickers", default=",".join(config.TICKERS))
    args = parser.parse_args()
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]

    corpus_dir = config.DATA_DIR / "corpus" / "edgar_latest"
    (corpus_dir / "item1a").mkdir(parents=True, exist_ok=True)
    log = QualityLog("Data quality - SEC EDGAR latest 10-K")
    sec = SecClient(config.SEC_USER_AGENT, config.SEC_MAX_RPS)

    print(f"Ticker map: {TICKER_MAP_URL}")
    ticker_map = {v["ticker"].upper(): v for v in json.loads(sec.get(TICKER_MAP_URL)).values()}

    rows, seen_cik = [], {}
    for ticker in tickers:
        print(f"{ticker}:")
        lookup = ticker.replace(".", "-")
        if lookup != ticker:
            log.add("INFO", "ticker_format", ticker, f"SEC lists class shares with '-': looked up {lookup}")
        entry = ticker_map.get(lookup)
        if not entry:
            log.add("ERROR", "ticker_not_found", ticker, "not in SEC company_tickers.json - skipped")
            continue
        cik = int(entry["cik_str"])
        if cik in seen_cik:
            log.add("WARN", "duplicate_company", ticker,
                    f"same CIK {cik} as {seen_cik[cik]} ({entry['title']}) - the same filing will be counted twice")
        seen_cik.setdefault(cik, ticker)

        sub = json.loads(sec.get(SUBMISSIONS_URL.format(cik=cik)))
        if lookup not in [t.upper() for t in sub.get("tickers", [])]:
            log.add("WARN", "ticker_mismatch", ticker, f"CIK {cik} submissions list tickers {sub.get('tickers')}")
        filing, amendments, other = latest_10k(sub)
        if not filing:
            log.add("ERROR", "no_10k", ticker, f"no 10-K in recent filings (annual forms seen: {other or 'none'})")
            continue
        for a in amendments:
            log.add("WARN", "amended_after", ticker,
                    f"10-K/A {a['accessionNumber']} filed {a['filingDate']} after the 10-K used")

        acc = filing["accessionNumber"]
        url = ARCHIVE_URL.format(cik=cik, acc_nodash=acc.replace("-", ""), doc=filing["primaryDocument"])
        text = html_to_text(sec.get(url).decode("utf-8", errors="replace"))
        body, method = extract_item1a(text)
        if method == "not_found":
            log.add("ERROR", "item1a_not_found", ticker, f"no Item 1A heading found in {url}")
        elif method == "loose":
            log.add("WARN", "item1a_heading", ticker, "Item 1A found only by loose match - check boundaries")
        if SMALLER_REPORTING.search(body[:3000]):
            log.add("WARN", "item1a_omitted", ticker, "filer says it is a smaller reporting company; no risk factors")
        elif body and len(body) < 8000:
            log.add("WARN", "item1a_short", ticker, f"only {len(body):,} characters - incomplete or cross-referenced?")

        fye = sub.get("fiscalYearEnd", "")
        if fye and fye != "1231":
            log.add("INFO", "non_calendar_fiscal_year", ticker,
                    f"fiscal year ends {fye[:2]}/{fye[2:]} (MM/DD); period {filing['reportDate']}")
        action = CORPORATE_ACTION.search(body)
        if action:
            log.add("INFO", "corporate_action_mentioned", ticker,
                    f"Item 1A mentions: \"{' '.join(action.group(0).split())[:240]}\"")

        item_file = f"item1a/{ticker}.txt"
        (corpus_dir / item_file).write_text(body)
        rows.append({"ticker": ticker, "company": sub.get("name", entry["title"]), "cik": cik, "form": filing["form"],
                     "accession": acc, "filing_date": filing["filingDate"], "report_date": filing["reportDate"],
                     "fiscal_year_end": sub.get("fiscalYearEnd", ""), "url": url, "item1a_chars": len(body),
                     "item1a_file": item_file if body else "", "source": "sec_edgar"})
        print(f"  {sub.get('name')} {filing['form']} {acc} period {filing['reportDate']} - Item 1A {len(body):,} chars")

    # ---- reminders from groups.yaml (facts to double-check; nothing is changed)
    for t, note in config.GROUP_NOTES.items():
        if t in tickers:
            log.add("INFO", "group_note", t, note)

    # ---- checks across the whole set
    if rows:
        periods = {r["ticker"]: r["report_date"] for r in rows if r["report_date"]}
        years = {}
        for t, p in periods.items():
            years.setdefault(p[:4], []).append(t)
        if len(years) > 1:
            log.add("WARN", "mixed_years", "all",
                    "fiscal periods end in different calendar years: "
                    + "; ".join(f"{y}: {', '.join(ts)}" for y, ts in sorted(years.items())))
        fye = {}
        for r in rows:
            fye.setdefault(r["fiscal_year_end"], []).append(r["ticker"])
        if len(fye) > 1:
            log.add("INFO", "fiscal_year_ends", "all", "different fiscal year ends (MMDD): "
                    + "; ".join(f"{k or '?'}: {', '.join(v)}" for k, v in sorted(fye.items())))
        for t, p in periods.items():
            age = (date.today() - datetime.strptime(p, "%Y-%m-%d").date()).days
            if age > 15 * 30:
                log.add("WARN", "stale_filing", t, f"period ended {p} ({age} days ago)")

    write_manifest(rows, corpus_dir)
    intro = (f"Fetched {datetime.now():%Y-%m-%d %H:%M} for tickers: {', '.join(tickers)}. "
             f"{len(rows)} filings kept.")
    log.write(corpus_dir / "data_quality.md", corpus_dir / "data_quality.jsonl", intro)
    config.RESULTS_DIR.mkdir(exist_ok=True)
    (config.RESULTS_DIR / "data_quality_edgar_latest.md").write_text((corpus_dir / "data_quality.md").read_text())
    print(f"\n{len(rows)} filings -> {corpus_dir}/manifest.csv; data-quality log -> results/data_quality_edgar_latest.md")


if __name__ == "__main__":
    main()
