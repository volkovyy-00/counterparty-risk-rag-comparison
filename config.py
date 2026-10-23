"""All settings come from environment variables (or a local .env file).

Nothing here is secret by default; keys are read from the environment only.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def env(name, default=None):
    value = os.getenv(name)
    return default if value in (None, "") else value


# --- The question and the counterparty group -------------------------------
QUESTION = env(
    "QUESTION",
    "What industry risks connect these counterparties, and which counterparties share each one?",
)
# Same ten names the workshop sample intends to cover, with correct tickers.
TICKERS = [
    t.strip().upper()
    for t in env("TICKERS", "AAPL,MSFT,NVDA,AMZN,GOOGL,INTC,PYPL,PCG,MCD,AIG").split(",")
    if t.strip()
]
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
# openai    : OpenAI, or any OpenAI-compatible server via OPENAI_BASE_URL (Ollama, vLLM, ...)
# azure     : Azure OpenAI (AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, OPENAI_API_VERSION)
# anthropic : Anthropic Messages API (ANTHROPIC_API_KEY); embeddings still use EMBED_PROVIDER
LLM_PROVIDER = env("LLM_PROVIDER", "openai")
LLM_MODEL = env("LLM_MODEL", "gpt-4.1-mini")
LLM_TEMPERATURE = env("LLM_TEMPERATURE", "0")  # "none" = don't send (some models only allow default)
LLM_CONCURRENCY = int(env("LLM_CONCURRENCY", "4"))
EMBED_PROVIDER = env("EMBED_PROVIDER", "openai" if LLM_PROVIDER == "anthropic" else LLM_PROVIDER)
EMBED_MODEL = env("EMBED_MODEL", "text-embedding-3-small")
EMBED_DIMENSIONS = int(env("EMBED_DIMENSIONS", "1536"))

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
