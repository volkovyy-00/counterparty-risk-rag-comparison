"""Serve the demo on localhost (stdlib only). Never needs Neo4j; needs the network only with --live.

    python src/serve.py              # offline: page + governance checks (no model call)
    python src/serve.py --live       # also enables the one live step: plain-RAG ask (1 embedding + 1 chat call)

The live step has a hard LIVE_TIMEOUT_S (20 s) deadline. On timeout or any error
it returns the recorded answer from results/demo_run/ with mode "cached", and the
page shows "CACHED (recorded <timestamp>)". Nothing else calls an API.
"""
import argparse
import json
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import config

LIVE_TIMEOUT_S = float(config.env("LIVE_TIMEOUT_S", "20"))
DEMO_DIR = config.ROOT / "demo"
RUN_DIR = config.RESULTS_DIR / "demo_run"


class Live:
    """Plain-RAG index loaded from the recorded run's cache, ready for one live ask."""

    def __init__(self, run_dir=RUN_DIR):
        self.run_dir = Path(run_dir)
        self.cached = json.loads((self.run_dir / "approach_1_plain_rag.json").read_text())
        self.index = None
        self.pool = ThreadPoolExecutor(2)

    def prepare(self):
        """Load chunks and their recorded embeddings (replay: no network)."""
        import approach1_rag
        from corpus import load_corpus

        saved = config.LLM_CACHE
        config.LLM_CACHE = "replay"
        try:
            self.filings = load_corpus()
            self.index = approach1_rag.build(self.filings)
        finally:
            config.LLM_CACHE = saved
        return self

    def cached_answer(self, note):
        return {"mode": "cached", "recorded_at": self.cached["details"].get("answer_recorded_at")
                or json.loads((self.run_dir / "manifest.json").read_text())["created_at"],
                "note": note, "result": None}

    def _ask(self):
        import approach1_rag
        from answer import finalise

        chunks, vectors = self.index
        start = time.perf_counter()
        reply, retrieved, record = approach1_rag.ask(config.QUESTION, chunks, vectors, cache="off",
                                                     timeout=LIVE_TIMEOUT_S)
        result = finalise({"approach": "1_plain_rag", "summary": reply["summary"], "raw_claims": reply["claims"],
                           "sources": {c["chunk_id"]: c["text"] for c in retrieved},
                           "details": {"top_k": len(retrieved),
                                       "tickers_in_retrieved_context": sorted({c["ticker"] for c in retrieved}),
                                       "answer_recorded_at": record["recorded_at"]}}, self.filings)
        result.pop("sources", None)
        return {"mode": "live", "seconds": round(time.perf_counter() - start, 1),
                "recorded_at": record["recorded_at"], "model": record.get("served_model"), "result": result}

    def ask(self, timeout=LIVE_TIMEOUT_S):
        if self.index is None:
            return self.cached_answer("live index not loaded - showing the recorded answer")
        future = self.pool.submit(self._ask)
        try:
            return future.result(timeout=timeout)
        except FutureTimeout:
            return self.cached_answer(f"no answer within {timeout:.0f} s - showing the recorded answer")
        except Exception as exc:  # network down, key missing, provider error: fall back, never crash on stage
            return self.cached_answer(f"live call failed ({type(exc).__name__}) - showing the recorded answer")


def governance_check(kind):
    import governance
    from corpus import load_corpus

    filings = load_corpus()
    if kind == "fabricated":
        return governance.fabricated(filings, RUN_DIR)
    if kind == "offtaxonomy":
        return governance.off_taxonomy(filings, RUN_DIR)
    if kind == "audit":
        return governance.audit(RUN_DIR, RUN_DIR / "audit" / "run_b")
    return {"error": f"unknown check {kind}"}


def make_handler(live):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(DEMO_DIR), **kwargs)

        def log_message(self, *args):  # presenter mode: no request log on the terminal
            pass

        def _json(self, obj):
            data = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path.startswith("/api/status"):
                return self._json({"live": live is not None, "timeout_s": LIVE_TIMEOUT_S})
            return super().do_GET()

        def do_POST(self):
            if self.path.startswith("/api/live_rag"):
                return self._json(live.ask() if live else {"mode": "cached", "note": "live step not enabled",
                                                           "result": None})
            if self.path.startswith("/api/governance/"):
                try:
                    return self._json(governance_check(self.path.rsplit("/", 1)[-1]))
                except (Exception, SystemExit) as exc:  # e.g. no corpus: the page shows its precomputed copy
                    return self._json({"error": str(exc)})
            self.send_error(404)
    return Handler


def serve(port=8000, live=False, open_browser=True):
    live_obj = None
    if live:
        print("Live step: loading the plain-RAG index from the recorded run ...")
        live_obj = Live().prepare()
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(live_obj))
    url = f"http://localhost:{port}/index.html"
    print(f"Demo at {url}  ({'LIVE step enabled' if live else 'offline'}; Ctrl+C to stop)")
    if open_browser:
        webbrowser.open(url)
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    server = serve(args.port, args.live, not args.no_browser)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
