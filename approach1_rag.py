"""Approach 1 - plain vector RAG: chunk, embed, retrieve top-k, answer with claims + verbatim quotes."""
import numpy as np

import config
import llm
from answer import CLAIMS_SCHEMA, system_prompt
from corpus import chunks_for

SYSTEM = system_prompt(
    "You are a credit risk analyst. Answer only from the filing excerpts you are given. "
    "Each excerpt is labelled [chunk_id] TICKER (company). If the excerpts do not cover a company, "
    "leave it out rather than guess."
)


def build(filings):
    chunks = chunks_for(filings, config.RAG_CHUNK_CHARS, config.RAG_CHUNK_OVERLAP)
    with llm.METER.track("rag.build"):
        vectors = np.array(llm.embed([c["text"] for c in chunks]), dtype=np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    return chunks, vectors


def retrieve(question, chunks, vectors, top_k=None, cache=None):
    q = np.array(llm.embed([question], cache=cache)[0], dtype=np.float32)
    scores = vectors @ (q / np.linalg.norm(q))
    top = np.argsort(-scores)[:top_k or config.RAG_TOP_K]
    return [dict(chunks[i], score=round(float(scores[i]), 4)) for i in top]


def user_prompt(question, retrieved):
    context = "\n\n".join(f"[{c['chunk_id']}] {c['ticker']} ({c['company']})\n{c['text']}" for c in retrieved)
    return f"Question: {question}\n\nExcerpts:\n\n{context}"


def ask(question, chunks, vectors, cache=None, timeout=None):
    with llm.METER.track("rag.ask"):
        retrieved = retrieve(question, chunks, vectors, cache=cache)
        reply, record = llm.chat(SYSTEM, user_prompt(question, retrieved), schema=CLAIMS_SCHEMA,
                                 schema_name="claims", cache=cache, timeout=timeout, return_record=True)
    return reply, retrieved, record


def run(question, filings):
    chunks, vectors = build(filings)
    reply, retrieved, record = ask(question, chunks, vectors)
    return {
        "approach": "1_plain_rag",
        "summary": reply["summary"],
        "raw_claims": reply["claims"],
        "sources": {c["chunk_id"]: c["text"] for c in retrieved},
        "stages": {"build": "rag.build", "ask": "rag.ask"},
        "details": {
            "chunks_indexed": len(chunks),
            "top_k": len(retrieved),
            "tickers_in_retrieved_context": sorted({c["ticker"] for c in retrieved}),
            "retrieved": [{k: c[k] for k in ("chunk_id", "ticker", "score", "start")} for c in retrieved],
            "answer_recorded_at": record.get("recorded_at"),
        },
    }
