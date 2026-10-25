"""Run manifests: everything needed to say exactly what produced a result.

model, prompt SHA-256 per approach, taxonomy version + hash, corpus manifest hash,
git SHA, timestamp, cache mode - and a diff between two manifests (governance screen).
"""
import hashlib
import json
import subprocess
from datetime import datetime, timezone

import config
import llm
import taxonomy


def sha256(text):
    return hashlib.sha256(text.encode() if isinstance(text, str) else text).hexdigest()


def corpus_hash(corpus_dir=None):
    """Hash of manifest.csv plus every Item 1A file it lists (order-independent of the file system)."""
    corpus_dir = corpus_dir or config.CORPUS_DIR
    manifest = corpus_dir / "manifest.csv"
    if not manifest.exists():
        return None
    h = hashlib.sha256(manifest.read_bytes())
    for path in sorted((corpus_dir / "item1a").glob("*.txt")):
        h.update(path.name.encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def git_state():
    def git(*args):
        try:
            return subprocess.run(["git", *args], cwd=config.ROOT, capture_output=True, text=True,
                                  timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""
    return {"sha": git("rev-parse", "HEAD") or None,
            "dirty": bool(git("status", "--porcelain", "--", "."))}


def _graph_v2_hash(ask_system, claims):
    import graph_resolve
    import graph_v2

    return sha256(ask_system + graph_v2.SYSTEM_V2 + json.dumps(graph_v2.MENTIONS_SCHEMA, sort_keys=True)
                  + graph_resolve.RESOLVE_SYSTEM + graph_resolve.DRIVER_SYSTEM + claims)


def prompt_hashes():
    import approach0_long_context
    import approach1_rag
    import approach2_graphrag
    import approach3_taxonomy
    import graph_qa
    from answer import CLAIMS_SCHEMA

    claims = json.dumps(CLAIMS_SCHEMA, sort_keys=True)
    return {
        "0_long_context": sha256(approach0_long_context.SYSTEM + claims),
        "1_plain_rag": sha256(approach1_rag.SYSTEM + claims),
        "2_graphrag": sha256(approach2_graphrag.SYSTEM + approach2_graphrag.EXTRACTION_INSTRUCTION + claims)
        if config.GRAPH_PROMPT_VERSION == "graph-v1-workshop" else _graph_v2_hash(approach2_graphrag.SYSTEM, claims),
        "3_taxonomy_first": sha256(approach3_taxonomy.system() + json.dumps(approach3_taxonomy.SCHEMA, sort_keys=True)),
    } | ({"2_graph_qa": graph_qa.prompt_sha256()} if config.GRAPH_PROMPT_VERSION == "graph-v2" else {})


def build(filings, approaches, label=""):
    import approach3_taxonomy

    return {
        "label": label,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "question": config.QUESTION,
        "group": config.GROUP,
        "corpus": config.CORPUS,
        "filings": [{k: f.get(k, "") for k in ("ticker", "company", "accession", "filing_date", "report_date",
                                                "fiscal_year_end", "url")} for f in filings],
        "corpus_manifest_sha256": corpus_hash(),
        "provider": config.LLM_PROVIDER,
        "model": config.LLM_MODEL,
        "effort": config.LLM_EFFORT if config.LLM_PROVIDER == "anthropic" else None,
        "structured_output": config.LLM_STRUCTURED,
        "embed_provider": config.EMBED_PROVIDER,
        "embed_model": config.EMBED_MODEL,
        "taxonomy_version": taxonomy.VERSION,
        "taxonomy_sha256": taxonomy.SHA256,
        "taxonomy_prompt_version": approach3_taxonomy.PROMPT_VERSION,
        "prompt_sha256": prompt_hashes(),
        "cache_mode": config.LLM_CACHE,
        "approaches": approaches,
        "knobs": {"rag_top_k": config.RAG_TOP_K, "rag_chunk_chars": config.RAG_CHUNK_CHARS,
                  "graph_chunk_chars": config.GRAPH_CHUNK_CHARS, "graph_resolver": config.GRAPH_RESOLVER,
                  "graph_mode": config.GRAPH_MODE, "graph_prompt_version": config.GRAPH_PROMPT_VERSION,
                  "graph_v2_chunk_chars": config.GRAPH_V2_CHUNK_CHARS, "graph_sim_min": config.GRAPH_SIM_MIN,
                  "generic_share": config.GENERIC_SHARE, "taxo_window_chars": config.TAXO_WINDOW_CHARS,
                  "min_shared": config.MIN_SHARED},
        "pricing_checked": llm.PRICES_CHECKED,
        "git": git_state(),
    }


def diff(a, b, prefix=""):
    """Flat list of (key, value_a, value_b) where two manifests differ."""
    out = []
    for key in sorted(set(a) | set(b)):
        va, vb = a.get(key), b.get(key)
        name = f"{prefix}{key}"
        if isinstance(va, dict) and isinstance(vb, dict):
            out += diff(va, vb, name + ".")
        elif va != vb:
            out.append((name, va, vb))
    return out
