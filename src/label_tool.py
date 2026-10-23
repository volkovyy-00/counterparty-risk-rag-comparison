"""Hand-label the ground-truth key in a browser - a person decides every cell.

    python src/label_tool.py            # opens http://localhost:8765 (stdlib only, offline)

For each company and each taxonomy leaf: read the candidate sentences (keyword
hits from label_helper.py, a pointer only), search the full Item 1A if needed,
then press Y (the Item 1A gives this risk at least one dedicated risk factor) or
N. Progress is saved to ground_truth.yaml as status: draft. "Mark verified"
needs every cell decided and your initials; it records the accession numbers
you labelled against. Nothing here proposes or pre-fills a label.
"""
import argparse
import json
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import yaml

import config
import taxonomy
from corpus import load_corpus
from evaluate import GT_PATH
from label_helper import candidates


def load_section():
    doc = yaml.safe_load(GT_PATH.read_text()) or {}
    doc.setdefault("corpora", {})
    return doc, doc["corpora"].setdefault(config.CORPUS, {})


def save(labels, initials, verify, filings):
    doc, section = load_section()
    tickers = [f["ticker"] for f in filings]
    clean = {}
    for t in tickers:
        cell = labels.get(t, {})
        yes = sorted(leaf for leaf, v in cell.items() if v == "yes" and leaf in taxonomy.LEAVES)
        no = sorted(leaf for leaf, v in cell.items() if v == "no" and leaf in taxonomy.LEAVES)
        if yes or no:
            clean[t] = {"yes": yes, "no": no}
    decided = sum(len(v["yes"]) + len(v["no"]) for v in clean.values())
    total = len(tickers) * len(taxonomy.LEAF_IDS)
    if verify and (decided < total or not initials.strip()):
        return {"ok": False, "error": f"{decided} of {total} cells decided; initials required to verify"}
    section.update({
        "group": config.GROUP, "taxonomy_version": taxonomy.VERSION,
        "status": "verified" if verify else ("draft" if decided else "unlabelled"),
        "labeller": initials.strip(), "labelled_at": date.today().isoformat(),
        "accessions": {f["ticker"]: f["accession"] for f in filings},
        "labels": clean,
    })
    header = GT_PATH.read_text().split("corpora:", 1)[0]
    GT_PATH.write_text(header + yaml.safe_dump({"corpora": doc["corpora"]}, sort_keys=False, width=120))
    return {"ok": True, "status": section["status"], "decided": decided, "total": total}


def state(filings, cands):
    _, section = load_section()
    labels = {t: {**{leaf: "yes" for leaf in v.get("yes", [])}, **{leaf: "no" for leaf in v.get("no", [])}}
              for t, v in (section.get("labels") or {}).items()}
    return {"corpus": config.CORPUS, "group": config.GROUP, "status": section.get("status", "unlabelled"),
            "labeller": section.get("labeller", ""),
            "filings": [{k: f[k] for k in ("ticker", "company", "accession", "report_date", "url")} for f in filings],
            "texts": {f["ticker"]: f["text"] for f in filings},
            "leaves": [{"id": lid, "category": leaf["category"], "category_name": taxonomy.CATEGORY_NAMES[leaf["category"]],
                        "description": leaf["description"]} for lid, leaf in taxonomy.LEAVES.items()],
            "candidates": cands, "labels": labels}


PAGE = (config.ROOT / "demo" / "label_tool.html")


def make_handler(filings, cands):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, body, ctype="application/json"):
            data = body.encode() if isinstance(body, str) else body
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path.startswith("/api/state"):
                self._send(json.dumps(state(filings, cands)))
            else:
                self._send(PAGE.read_text(), "text/html; charset=utf-8")

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
            self._send(json.dumps(save(body.get("labels", {}), body.get("initials", ""), bool(body.get("verify")),
                                       filings)))
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    filings = load_corpus()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(filings, candidates(filings)))
    url = f"http://localhost:{args.port}"
    print(f"Labelling {config.CORPUS} ({len(filings)} companies x {len(taxonomy.LEAF_IDS)} leaves) at {url}  "
          "(Ctrl+C to stop; progress is saved on every change)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
