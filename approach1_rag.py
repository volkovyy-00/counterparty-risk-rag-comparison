"""Approach 1 - plain vector RAG: chunk, embed, retrieve top-k, answer with citations."""
import numpy as np

import config
import llm
from answer import SHARED_RISKS_SCHEMA, check_citations, shared_only
from corpus import chunks_for

SYSTEM = (
    "You are a credit risk analyst. Answer only from the numbered filing excerpts you are given. "
    "Each excerpt is labelled [chunk_id] TICKER (company). Cite chunk ids for every claim. "
    "A ticker may be listed for a risk only if a cited excerpt from that ticker's filing supports it. "
    "If the excerpts do not cover a company, leave it out rather than guess."
)


def build(filings):
    chunks = chunks_for(filings, config.RAG_CHUNK_CHARS, config.RAG_CHUNK_OVERLAP)
    with llm.METER.track("rag.build"):
        vectors = np.array(llm.embed([c["text"] for c in chunks]), dtype=np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    return chunks, vectors


def ask(question, chunks, vectors, top_k=None):
    top_k = top_k or config.RAG_TOP_K
    with llm.METER.track("rag.ask"):
        q = np.array(llm.embed([question])[0], dtype=np.float32)
        scores = vectors @ (q / np.linalg.norm(q))
        top = np.argsort(-scores)[:top_k]
        retrieved = [dict(chunks[i], score=round(float(scores[i]), 4)) for i in top]
        context = "\n\n".join(f"[{c['chunk_id']}] {c['ticker']} ({c['company']})\n{c['text']}" for c in retrieved)
        reply = llm.chat(SYSTEM, f"Question: {question}\n\nExcerpts:\n\n{context}",
                         schema=SHARED_RISKS_SCHEMA, schema_name="shared_risks")
    return reply, retrieved


def run(question, filings):
    chunks, vectors = build(filings)
    reply, retrieved = ask(question, chunks, vectors)
    by_id = {c["chunk_id"]: c for c in chunks}
    tickers = {f["ticker"] for f in filings}
    return {
        "approach": "1_plain_rag",
        "summary": reply["summary"],
        "shared_risks": shared_only(reply["shared_risks"]),
        "citation_check": check_citations(reply["shared_risks"], by_id, tickers),
        "stages": {"build": "rag.build", "ask": "rag.ask"},
        "details": {
            "chunks_indexed": len(chunks),
            "top_k": len(retrieved),
            "tickers_in_retrieved_context": sorted({c["ticker"] for c in retrieved}),
            "retrieved": [{k: c[k] for k in ("chunk_id", "ticker", "score")} for c in retrieved],
        },
        "evidence": {c["chunk_id"]: c["text"][:300] for c in retrieved},
    }
