"""TEST-ONLY stand-in for the LLM and embedding APIs.

Deterministic keyword rules that exercise the plumbing (schemas, caching,
quote checks, Neo4j writes) without network access. Its answers are not
analysis and must never be presented as results.
"""
import hashlib
import json
import re
from types import SimpleNamespace

import numpy as np

import llm
from answer import CATEGORY_NAMES, categories_for

FABRICATED = "This sentence was invented by the fake model and appears in no filing whatsoever."


def _sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text)) if 60 < len(s) < 400]


def fake_call_chat(system, user, schema, schema_name):
    if schema_name == "risk_factors":
        excerpt = user.split("\n\n", 1)[1]
        out, seen = [], set()
        for s in _sentences(excerpt):
            cats = categories_for(s)
            if cats and cats[0] not in seen:
                seen.add(cats[0])
                out.append({"heading": s[:60], "category": cats[0], "quote": s[:200]})
        out.append({"heading": "fabricated", "category": "OTHER", "quote": FABRICATED})
        content = {"risk_factors": out}
    elif schema_name == "shared_risks":
        groups = {}
        for cid, ticker, text in re.findall(r"\[([\w-]+)\] ([A-Z]+)[^\n]*\n?([^\[]*)", user):
            for cat in categories_for(text)[:2]:
                g = groups.setdefault(CATEGORY_NAMES[cat], {"tickers": set(), "citations": []})
                g["tickers"].add(ticker)
                g["citations"].append(cid)
        content = {"summary": "fake summary",
                   "shared_risks": [{"risk": k, "tickers": sorted(v["tickers"]), "citations": v["citations"][:6]}
                                    for k, v in groups.items()]}
    else:  # neo4j-graphrag entity extraction prompt (V1, JSON in text)
        text = user.rsplit("Input text:", 1)[-1]
        cats = sorted({c for s in _sentences(text) for c in categories_for(s)})
        content = json.dumps({"nodes": [{"id": str(i), "label": "RiskFactor",
                                         "properties": {"name": CATEGORY_NAMES[c]}} for i, c in enumerate(cats)],
                              "relationships": []})
    return content, len(system + user) // 4, len(json.dumps(content)) // 4


def _vector(text, dims):
    v = np.zeros(dims, dtype=np.float32)
    for word in re.findall(r"[a-z]{4,}", text.lower()):
        v[int(hashlib.md5(word.encode()).hexdigest(), 16) % dims] += 1
    return (v / (np.linalg.norm(v) or 1)).tolist()


class FakeEmbeddings:
    def create(self, model, input, dimensions):
        return SimpleNamespace(data=[SimpleNamespace(embedding=_vector(t, dimensions)) for t in input],
                               usage=SimpleNamespace(prompt_tokens=sum(len(t) // 4 for t in input)))


def install(monkeypatch):
    monkeypatch.setattr(llm, "_call_chat", fake_call_chat)
    monkeypatch.setattr(llm, "_client", lambda provider: SimpleNamespace(embeddings=FakeEmbeddings()))
