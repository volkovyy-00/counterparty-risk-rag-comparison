"""Serve the demo on localhost (stdlib only). Never needs Neo4j; needs the network only with --live.

    python src/serve.py              # offline: page + governance checks (no model call)
    python src/serve.py --live       # also enables the live asks on the console (plain RAG and the graph)

Live asks stream NDJSON (one JSON object per line, see ui/src/lib/live.js) and have a hard LIVE_TIMEOUT_S
deadline. On timeout, any error or the spend cap they end in {"type": "replay"}, and the page shows the recorded
answer with a REPLAY badge. Retrieval (local embeddings) is free; each answer is one model call, and the graph ask
adds one small routing call. Live spend is logged to results/spend/console_live.jsonl and capped at LIVE_MAX_USD
across rehearsals and the stage. The old page (demo/index.html) keeps its one-shot /api/live_rag answer.
"""
import argparse
import json
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import config

LIVE_TIMEOUT_S = float(config.env("LIVE_TIMEOUT_S", "20"))
LIVE_MAX_USD = float(config.env("LIVE_MAX_USD", "3"))
DEMO_DIR = config.ROOT / "demo"
RUN_DIR = config.RESULTS_DIR / "demo_run"
SPEND_LOG = config.RESULTS_DIR / "spend" / "console_live.jsonl"
# Assumed cost of one live ask, checked against the cap before the call (the real cost is logged after it).
ASK_USD = {"rag": 0.08, "graph": 0.08}
ROUTE_MODEL = config.env("CONSOLE_ROUTE_MODEL", config.GRAPH_QA_MODEL)
GRAPH_ANSWER_MODEL = config.env("CONSOLE_GRAPH_MODEL", config.LLM_MODEL)

ROUTE_SYSTEM = (
    "You route a question about the 10-K risk factors of a fixed group of companies to ONE fixed, read-only graph "
    "query. You never write a query. Templates:\n"
    "SHARED_AMONG: which risks do the named companies share (needs at least two tickers).\n"
    "SHARED_VS_SPECIFIC: the risk shared most widely, and the most widely shared specific risk linking autos and "
    "chips.\n"
    "BRIDGE_DRIVERS: which named place, input or policy links the automakers' risks to the chipmakers' risks.\n"
    "SHARED_RISKS: the overall question, what risks connect all the companies and who shares each.\n"
    "NONE: the question is not about shared risks of these companies.\n"
    "Companies (ticker: name): {companies}. Return the template, the tickers it needs (empty if none) and a "
    "one-line reason."
)


def route_schema():
    return {"type": "object", "additionalProperties": False, "required": ["template", "tickers", "reason"],
            "properties": {"template": {"type": "string", "enum": ["SHARED_AMONG", "SHARED_VS_SPECIFIC", "BRIDGE_DRIVERS",
                                                                     "SHARED_RISKS", "NONE"]},
                           "tickers": {"type": "array", "items": {"type": "string", "enum": config.TICKERS}},
                           "reason": {"type": "string"}}}


class Spend:
    """Live console spend across processes: one JSON line per paid call, capped at LIVE_MAX_USD."""

    def __init__(self, path=SPEND_LOG, cap=LIVE_MAX_USD):
        self.path, self.cap, self.lock = Path(path), cap, threading.Lock()

    def spent(self):
        if not self.path.exists():
            return 0.0
        return sum(json.loads(line)["usd"] for line in self.path.read_text().splitlines() if line.strip())

    def allows(self, usd):
        return self.spent() + usd <= self.cap

    def add(self, what, record):
        import llm

        if not record or record.get("cached"):
            return
        usd = llm.price_usd(record["model"], record["input_tokens"], record["output_tokens"],
                            record.get("cache_write_tokens", 0), record.get("cache_read_tokens", 0)) or 0.0
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a") as fh:
                fh.write(json.dumps({"step": "console live", "stage": what, "model": record["model"],
                                     "usd": round(usd, 6), "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}) + "\n")


class Live:
    """Plain-RAG index and the exported graph, loaded once, ready for live asks."""

    def __init__(self, run_dir=RUN_DIR, spend=None):
        self.run_dir = Path(run_dir)
        self.cached = json.loads((self.run_dir / "approach_1_plain_rag.json").read_text())
        self.index = None
        self.graph = None
        self.spend = spend or Spend()
        self.pool = ThreadPoolExecutor(4)

    def prepare(self):
        """Load chunks and their embeddings (from the cache; a local embedding model fills any gap for free)."""
        import approach1_rag
        import graph_local
        from corpus import load_corpus

        saved = config.LLM_CACHE
        config.LLM_CACHE = "readwrite" if config.EMBED_PROVIDER == "local" else "replay"
        try:
            self.filings = load_corpus()
            self.index = approach1_rag.build(self.filings)
        finally:
            config.LLM_CACHE = saved
        if (self.run_dir / "graph.json").exists():
            self.graph = graph_local.load(self.run_dir / "graph.json")
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
        self.spend.add("rag", record)
        result = finalise({"approach": "1_plain_rag", "summary": reply["summary"], "raw_claims": reply["claims"],
                           "sources": {c["chunk_id"]: c["text"] for c in retrieved},
                           "details": {"top_k": len(retrieved),
                                       "tickers_in_retrieved_context": sorted({c["ticker"] for c in retrieved}),
                                       "answer_recorded_at": record["recorded_at"]}}, self.filings)
        result.pop("sources", None)
        return {"mode": "live", "seconds": round(time.perf_counter() - start, 1),
                "recorded_at": record["recorded_at"], "model": record.get("served_model"), "result": result}

    def ask(self, timeout=LIVE_TIMEOUT_S):
        """The old page's one-shot ask on the main question (plain JSON)."""
        if self.index is None:
            return self.cached_answer("live index not loaded - showing the recorded answer")
        if not self.spend.allows(ASK_USD["rag"]):
            return self.cached_answer(f"live spend cap ${self.spend.cap:.2f} reached - showing the recorded answer")
        future = self.pool.submit(self._ask)
        try:
            return future.result(timeout=timeout)
        except FutureTimeout:
            return self.cached_answer(f"no answer within {timeout:.0f} s - showing the recorded answer")
        except Exception as exc:  # network down, key missing, provider error: fall back, never crash on stage
            return self.cached_answer(f"live call failed ({type(exc).__name__}) - showing the recorded answer")

    # ------------------------------------------------------------------ console: streamed asks
    def _deadline(self, fn, *args, timeout=LIVE_TIMEOUT_S):
        return self.pool.submit(fn, *args).result(timeout=timeout)

    def rag_stream(self, question):
        """Plain RAG on any question: retrieval (free, local), then one answer call. Yields NDJSON events."""
        import approach1_rag
        from answer import finalise

        if self.index is None:
            yield {"type": "replay", "note": "live index not loaded"}
            return
        chunks, vectors = self.index
        start = time.perf_counter()
        yield {"type": "stage", "step": 0, "text": "embedding the question"}
        try:
            got = self._deadline(approach1_rag.retrieve, question, chunks, vectors)
        except Exception as exc:
            yield {"type": "replay", "note": f"retrieval failed ({type(exc).__name__})"}
            return
        retrieved = [{"chunk_id": c["chunk_id"], "ticker": c["ticker"], "score": c["score"], "start": c["start"],
                      "end": c["start"] + len(c["text"])} for c in got]
        yield {"type": "retrieved", "retrieved": retrieved, "chunks_indexed": len(chunks), "top_k": len(got)}
        if not self.spend.allows(ASK_USD["rag"]):
            yield {"type": "replay", "note": f"live spend cap ${self.spend.cap:.2f} reached"}
            return
        yield {"type": "stage", "step": 2, "text": "the model is writing the answer"}

        def answer():
            import llm

            reply, record = llm.chat(approach1_rag.SYSTEM, approach1_rag.user_prompt(question, got),
                                     schema=approach1_rag.CLAIMS_SCHEMA, schema_name="claims", cache="off",
                                     timeout=LIVE_TIMEOUT_S, return_record=True)
            self.spend.add("rag", record)
            return reply

        try:
            reply = self._deadline(answer, timeout=LIVE_TIMEOUT_S + 2)
        except FutureTimeout:
            yield {"type": "replay", "note": f"no answer within {LIVE_TIMEOUT_S:.0f} s"}
            return
        except Exception as exc:  # network down, key missing, provider error
            yield {"type": "replay", "note": f"live call failed ({type(exc).__name__})"}
            return
        yield {"type": "stage", "step": 3, "text": "checking every quote"}
        result = finalise({"approach": "1_plain_rag", "summary": reply["summary"], "raw_claims": reply["claims"],
                           "sources": {c["chunk_id"]: c["text"] for c in got}, "details": {}}, self.filings)
        result.pop("sources", None)
        yield {"type": "result", "result": result, "retrieved": retrieved, "chunks_indexed": len(chunks),
               "seconds": round(time.perf_counter() - start, 1)}

    def route(self, question):
        """(template, params, reason): the model picks a fixed template and its tickers; code checks them."""
        import graph_qa
        import llm

        names = ", ".join(f"{f['ticker']}: {f['company']}" for f in self.filings)
        reply, record = llm.chat(ROUTE_SYSTEM.format(companies=names), question, schema=route_schema(),
                                 schema_name="route", model=ROUTE_MODEL, effort="low", cache="off",
                                 timeout=LIVE_TIMEOUT_S, return_record=True)
        self.spend.add("graph.route", record)
        t, tickers = reply["template"], [x for x in dict.fromkeys(reply.get("tickers") or []) if x in config.TICKERS]
        if t == "SHARED_AMONG":
            if len(tickers) < 2:
                return "NONE", {}, "names fewer than two companies"
            return t, {"tickers": tickers, "min_shared": 2 if len(tickers) <= 3 else 3, "limit": 8}, reply["reason"]
        if t == "SHARED_VS_SPECIFIC":
            return t, {"min_shared": 2, "industries": graph_qa.INDUSTRIES}, reply["reason"]
        return t, {}, reply["reason"]

    def graph_stream(self, question, qid=None):
        """Graph ask: route to a template, run it over the exported graph, answer from the rows, verify."""
        import graph_local
        import graph_qa

        if self.graph is None:
            yield {"type": "replay", "note": "no exported graph"}
            return
        start = time.perf_counter()
        fixed = {q["id"]: q for q in graph_qa.QUESTIONS}
        if not self.spend.allows(ASK_USD["graph"]):
            yield {"type": "replay", "note": f"live spend cap ${self.spend.cap:.2f} reached", "closest": qid}
            return
        yield {"type": "stage", "step": 0, "text": "choosing a fixed query"}
        if qid in fixed:
            q = fixed[qid]
            template, params, reason = q["template"], q["params"], "fixed question"
        elif qid == "main":
            template, params, reason = "SHARED_RISKS", {}, "the main question"
        else:
            try:
                template, params, reason = self._deadline(self.route, question)
            except Exception as exc:
                yield {"type": "replay", "note": f"routing failed ({type(exc).__name__})"}
                return
        routed = {"template": template, "reason": reason}
        if template == "SHARED_RISKS":  # approach 2's own answer; the graph build is not re-run on stage
            yield {"type": "replay", "note": "the main question replays approach 2's frozen answer", "closest": "main"}
            return
        if template == "BRIDGE_DRIVERS":
            yield {"type": "replay", "note": "the bridge query needs every mention's quote; showing its recording",
                   "closest": "bridge"}
            return
        if template not in graph_local.LOCAL_TEMPLATES:
            yield {"type": "replay", "note": f"no fixed query answers this ({reason})"}
            return
        yield {"type": "stage", "step": 1, "text": "running the read-only query"}
        rows = graph_local.rows_for(self.graph, template, params)
        sub = graph_qa.to_subgraph(rows, self.filings)
        q = {"id": qid or "typed", "question": question, "template": template, "params": params}
        yield {"type": "plan", "id": q["id"], "template": template, "params": params,
               "cypher": graph_qa.TEMPLATES[template].strip(), "rows": len(rows), "subgraph": sub}
        try:
            res = self._deadline(self._graph_answer, q, rows, timeout=LIVE_TIMEOUT_S + 2)
        except FutureTimeout:
            yield {"type": "replay", "note": f"no answer within {LIVE_TIMEOUT_S:.0f} s", "closest": qid}
            return
        except Exception as exc:
            yield {"type": "replay", "note": f"live call failed ({type(exc).__name__})", "closest": qid}
            return
        yield {"type": "stage", "step": 4, "text": "checking every quote"}
        yield {"type": "result", "result": dict(q, rows=len(rows), cypher=graph_qa.TEMPLATES[template].strip(),
                                                subgraph=sub, **res),
               "routed": routed, "seconds": round(time.perf_counter() - start, 1)}

    def _graph_answer(self, q, rows):
        import graph_qa
        import llm

        before = llm.METER.live_usd
        res = graph_qa.answer(q, rows, self.filings, cache="off", timeout=LIVE_TIMEOUT_S, model=GRAPH_ANSWER_MODEL)
        usd = llm.METER.live_usd - before
        if usd:
            with self.spend.lock:
                self.spend.path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.spend.path, "a") as fh:
                    fh.write(json.dumps({"step": "console live", "stage": "graph.answer", "model": GRAPH_ANSWER_MODEL,
                                         "usd": round(usd, 6), "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}) + "\n")
        return res


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

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            try:
                return json.loads(self.rfile.read(n) or b"{}") if n else {}
            except ValueError:
                return {}

        def _stream(self, events):
            """NDJSON, one event per line, flushed as it happens; the connection closes at the end."""
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                for e in events:
                    self.wfile.write((json.dumps(e) + "\n").encode())
                    self.wfile.flush()
            except Exception as exc:  # the page shows the recording; never a traceback on stage
                try:
                    self.wfile.write((json.dumps({"type": "replay", "note": f"server error ({type(exc).__name__})"})
                                      + "\n").encode())
                except OSError:
                    pass

        def do_GET(self):
            if self.path.startswith("/api/status"):
                return self._json({"live": live is not None, "retrieval": bool(live and live.index is not None),
                                   "timeout_s": LIVE_TIMEOUT_S, "cap_usd": LIVE_MAX_USD,
                                   "spent_usd": round(live.spend.spent(), 4) if live else None})
            return super().do_GET()

        def do_POST(self):
            if self.path.startswith("/api/live_rag"):
                body = self._body()
                if "question" in body:  # the console: streamed, any question
                    if not live:
                        return self._stream([{"type": "replay", "note": "live asks are off on this server"}])
                    return self._stream(live.rag_stream(str(body["question"])[:500]))
                return self._json(live.ask() if live else {"mode": "cached", "note": "live step not enabled",
                                                           "result": None})
            if self.path.startswith("/api/graph_ask"):
                body = self._body()
                if not live:
                    return self._stream([{"type": "replay", "note": "live asks are off on this server",
                                          "closest": body.get("qid")}])
                return self._stream(live.graph_stream(str(body.get("question", ""))[:500], body.get("qid")))
            if self.path.startswith("/api/governance/"):
                try:
                    return self._json(governance_check(self.path.rsplit("/", 1)[-1]))
                except (Exception, SystemExit) as exc:  # e.g. no corpus: the page shows its precomputed copy
                    return self._json({"error": str(exc)})
            self.send_error(404)
    return Handler


def serve(port=8000, live=False, open_browser=True, page="index.html"):
    live_obj = None
    if live:
        print(f"Live asks: loading the plain-RAG index and the exported graph (cap ${LIVE_MAX_USD:.2f}) ...")
        live_obj = Live().prepare()
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(live_obj))
    url = f"http://localhost:{port}/{page}"
    print(f"Demo at {url}  ({'LIVE step enabled' if live else 'offline'}; Ctrl+C to stop)")
    if open_browser:
        webbrowser.open(url)
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--page", default="index.html", help="page under demo/ to open, e.g. console/index.html")
    args = parser.parse_args()
    server = serve(args.port, args.live, not args.no_browser, args.page)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
