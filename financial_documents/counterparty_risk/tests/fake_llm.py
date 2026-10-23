"""TEST-ONLY stand-in for the LLM and embedding APIs.

Deterministic keyword rules that exercise the plumbing (schemas, caching,
quote checks, Neo4j writes) without network access. Its answers are not
analysis and must never be presented as results: it reports itself as
FAKE_MODEL, and run_all.freeze refuses any run that contains it.
"""
import hashlib
import json
import re
from types import SimpleNamespace

import numpy as np

import llm
import taxonomy

FAKE_MODEL = "fake-test-model"
REAL_CALL_CHAT = llm._call_chat  # kept so a test can run the real provider code against a fake transport
FABRICATED = "This sentence was invented by the fake model and appears in no filing whatsoever."
OFF_TAXONOMY = "SUPPLY_GEOPOLITICS"


def _sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text)) if 60 < len(s) < 400]


def _claims_from_excerpts(user, per_excerpt=2):
    """Claims for prompts made of '[ref] TICKER ...' excerpts (approaches 1, 2 and L)."""
    claims = []
    for ref, ticker, body in re.findall(r"^\[([\w:.-]+)\] ([A-Z]+)[^\n]*\n(.*?)(?=^\[|^RISK |\Z)", user, re.S | re.M):
        n = 0
        for s in _sentences(body):
            leaves = taxonomy.leaves_for(s)
            if leaves and n < per_excerpt:
                n += 1
                claims.append({"risk": taxonomy.leaf_name(leaves[0]), "company": ticker,
                               "category": taxonomy.category_of(leaves[0]), "leaf": leaves[0],
                               "quote": s[:200], "source_ref": ref})
    return claims


def fake_call_chat(system, user, schema, schema_name, timeout=None):
    if schema_name == "risk_factors":
        excerpt = user.split("\n\n", 1)[1]
        out, seen = [], set()
        for s in _sentences(excerpt):
            leaves = taxonomy.leaves_for(s)
            if leaves and leaves[0] not in seen:
                seen.add(leaves[0])
                out.append({"heading": s[:60], "category": taxonomy.category_of(leaves[0]), "leaf": leaves[0],
                            "quote": s[:200]})
        out.append({"heading": "fabricated", "category": "OTHER", "leaf": "OTHER.stock_governance",
                    "quote": FABRICATED})
        content = {"risk_factors": out}
    elif schema_name == "claims":
        content = {"summary": "fake summary", "claims": _claims_from_excerpts(user)}
    else:  # neo4j-graphrag entity extraction prompt (V1, JSON in text)
        text = user.rsplit("Input text:", 1)[-1]
        cats = sorted({c for s in _sentences(text) for c in taxonomy.categories_for(s)})
        content = json.dumps({"nodes": [{"id": str(i), "label": "RiskFactor",
                                         "properties": {"name": taxonomy.CATEGORY_NAMES[c]}}
                                        for i, c in enumerate(cats)],
                              "relationships": []})
    usage = {"input_tokens": len(system + user) // 4, "output_tokens": len(json.dumps(content)) // 4}
    return content, usage, FAKE_MODEL


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
    import config

    monkeypatch.setattr(llm, "_call_chat", fake_call_chat)
    monkeypatch.setattr(config, "EMBED_PROVIDER", "fake")
    monkeypatch.setattr(llm, "_client", lambda provider: SimpleNamespace(embeddings=FakeEmbeddings()))
    monkeypatch.setattr(llm, "count_tokens", lambda system, user: len(system + user) // 4)
    monkeypatch.setattr(llm, "context_window", lambda: 1_000_000)
