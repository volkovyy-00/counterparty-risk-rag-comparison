"""All settings come from environment variables (or a local .env file).

Nothing here is secret by default; keys are read from the environment only.
"""
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
load_dotenv(ROOT / ".env")


def env(name, default=None):
    value = os.getenv(name)
    return default if value in (None, "") else value


# --- The question and the counterparty group -------------------------------
QUESTION = env(
    "QUESTION",
    "What industry risks connect these counterparties, and which counterparties share each one?",
)
# Groups live in groups.yaml (GROUP=auto_semis by default); TICKERS=... overrides the list.
_GROUPS = yaml.safe_load((CONFIG_DIR / "groups.yaml").read_text())
GROUP = env("GROUP", _GROUPS["default"])
if GROUP not in _GROUPS["groups"]:
    raise SystemExit(f"GROUP={GROUP!r} is not in groups.yaml ({', '.join(_GROUPS['groups'])})")
_group = _GROUPS["groups"][GROUP]
for _key in ("companies", "notes"):
    if any(not isinstance(k, str) for k in (_group.get(_key) or {})):  # e.g. unquoted ON parses as True
        raise SystemExit(f"groups.yaml {GROUP}.{_key}: quote every ticker that YAML reads as a non-string")
TICKERS = [
    t.strip().upper()
    for t in env("TICKERS", ",".join(_group["companies"])).split(",")
    if t.strip()
]
INDUSTRY = {t: _group["companies"].get(t, "other") for t in TICKERS}  # ticker -> industry label
GROUP_NOTES = _group.get("notes") or {}
MIN_SHARED = int(env("MIN_SHARED", "2"))  # "shared" = faced by at least this many companies

# --- Corpus -----------------------------------------------------------------
# edgar_latest    : latest 10-K per ticker, downloaded by fetch_10k.py
# workshop_sample : the PDFs shipped with the workshop, labelled exactly as its CSV says
CORPUS = env("CORPUS", "edgar_latest")
DATA_DIR = ROOT / "data"
CORPUS_DIR = DATA_DIR / "corpus" / CORPUS
RESULTS_DIR = ROOT / "results"
CACHE_DIR = ROOT / "cache"

# --- SEC EDGAR fair-access rules -------------------------------------------
# SEC asks automated clients to declare who they are ("Name email@domain")
# and to stay at or below 10 requests per second.
SEC_USER_AGENT = env("SEC_USER_AGENT")
SEC_MAX_RPS = min(float(env("SEC_MAX_RPS", "5")), 10.0)

# --- LLM provider -----------------------------------------------------------
# anthropic : Anthropic Messages API (ANTHROPIC_API_KEY)
# openai    : OpenAI, or any OpenAI-compatible server via OPENAI_BASE_URL (Ollama, vLLM, ...)
# azure     : Azure OpenAI (AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, OPENAI_API_VERSION)
LLM_PROVIDER = env("LLM_PROVIDER", "anthropic")
# Some environments store the key under a generic name; the SDK reads ANTHROPIC_API_KEY.
if LLM_PROVIDER == "anthropic" and not env("ANTHROPIC_API_KEY") and env("API_KEY", "").startswith("sk-ant-"):
    os.environ["ANTHROPIC_API_KEY"] = os.environ["API_KEY"]
LLM_MODEL = env("LLM_MODEL", "claude-opus-5-5" if LLM_PROVIDER == "anthropic" else "gpt-4.1-mini")
# Sampling temperature is sent to OpenAI-style providers only ("none" = don't send).
# Current Anthropic models accept only their default sampling, so it is never sent there.
LLM_TEMPERATURE = env("LLM_TEMPERATURE", "0")
LLM_EFFORT = env("LLM_EFFORT", "low")  # Anthropic output_config.effort: low | medium | high | xhigh | max
# strict : the provider enforces the JSON schema (OpenAI strict mode, Anthropic output_config.format)
# json   : schema is only described in the prompt (local models); the code validator still applies
LLM_STRUCTURED = env("LLM_STRUCTURED", "strict")
LLM_CONCURRENCY = int(env("LLM_CONCURRENCY", "4"))
LLM_TIMEOUT_S = float(env("LLM_TIMEOUT_S", "600"))
# local  : fastembed (ONNX, runs on CPU, no key; the model is downloaded once from Hugging Face)
# openai / azure : embeddings API
EMBED_PROVIDER = env("EMBED_PROVIDER", "local" if LLM_PROVIDER == "anthropic" else LLM_PROVIDER)
EMBED_MODEL = env("EMBED_MODEL", "BAAI/bge-small-en-v1.5" if EMBED_PROVIDER == "local" else "text-embedding-3-small")
EMBED_DIMENSIONS = int(env("EMBED_DIMENSIONS", "384" if EMBED_PROVIDER == "local" else "1536"))

# readwrite : use cached responses when present, call the API otherwise (default)
# replay    : never call the API; fail on a cache miss (offline demo)
# off       : always call the API
LLM_CACHE = env("LLM_CACHE", "readwrite")

# --- Neo4j ------------------------------------------------------------------
NEO4J_URI = env("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = env("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = env("NEO4J_PASSWORD")
NEO4J_DATABASE = env("NEO4J_DATABASE", "neo4j")

# --- Approach knobs ---------------------------------------------------------
RAG_CHUNK_CHARS = int(env("RAG_CHUNK_CHARS", "1500"))
RAG_CHUNK_OVERLAP = int(env("RAG_CHUNK_OVERLAP", "200"))
RAG_TOP_K = int(env("RAG_TOP_K", "12"))
GRAPH_CHUNK_CHARS = int(env("GRAPH_CHUNK_CHARS", "4000"))
GRAPH_CHUNK_OVERLAP = int(env("GRAPH_CHUNK_OVERLAP", "200"))
GRAPH_RESOLVER = env("GRAPH_RESOLVER", "fuzzy")  # exact | fuzzy
GRAPH_MODE = env("GRAPH_MODE", "global")  # global traversal | vector_seeded (workshop pattern)
TAXO_WINDOW_CHARS = int(env("TAXO_WINDOW_CHARS", "12000"))


def rel(path):
    """Path relative to the project folder when possible (for short log lines)."""
    try:
        return path.relative_to(ROOT)
    except ValueError:
        return path
