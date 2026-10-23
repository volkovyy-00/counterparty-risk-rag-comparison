"""One metered, cached client for every LLM and embedding call in the prototype.

Why one client: all three approaches pay through the same meter, so the
token, cost and latency numbers in results/ are comparable. The cache makes
the demo replayable offline (LLM_CACHE=replay).
"""
import hashlib
import json
import threading
import time
from collections import defaultdict
from contextlib import contextmanager

import yaml

import config

_PRICES = yaml.safe_load((config.ROOT / "pricing.yaml").read_text()) or {}
PRICES_CHECKED = str(_PRICES.pop("checked", "unknown"))


class CacheMiss(RuntimeError):
    pass


# --------------------------------------------------------------------------- meter
class Meter:
    """Adds up calls, tokens and cost per named stage (e.g. 'rag.ask')."""

    def __init__(self):
        self._lock = threading.Lock()
        self._local = threading.local()
        self.stages = defaultdict(lambda: defaultdict(float))
        self.served_models = set()  # model ids the provider reported (cached records included)

    @property
    def stage(self):
        return getattr(self._local, "stage", "unstaged")

    @contextmanager
    def track(self, stage):
        previous, self._local.stage = self.stage, stage
        start = time.perf_counter()
        try:
            yield
        finally:
            with self._lock:
                self.stages[stage]["wall_clock_s"] += time.perf_counter() - start
            self._local.stage = previous

    @contextmanager
    def as_stage(self, stage):
        """Attribute calls to `stage` without adding wall-clock time (for worker threads)."""
        previous, self._local.stage = self.stage, stage
        try:
            yield
        finally:
            self._local.stage = previous

    def add(self, stage, model, input_tokens, output_tokens, cached, kind, latency_s=0.0,
            cache_write_tokens=0, cache_read_tokens=0):
        """input_tokens excludes prompt-cache writes/reads, which are counted and priced separately."""
        with self._lock:
            s = self.stages[stage]
            s[f"{kind}_calls"] += 1
            s["cached_calls"] += 1 if cached else 0
            s["input_tokens"] += input_tokens + cache_write_tokens + cache_read_tokens
            s["prompt_cache_read_tokens"] += cache_read_tokens
            s["output_tokens"] += output_tokens
            s["recorded_latency_s"] += latency_s  # as measured when the call was made live
            cost = price_usd(model, input_tokens, output_tokens, cache_write_tokens, cache_read_tokens)
            if cost is None:
                s["unpriced_calls"] += 1
            else:
                s["cost_usd"] += cost

    def summary(self, *stages):
        out = defaultdict(float)
        for name in stages:
            for key, value in self.stages.get(name, {}).items():
                out[key] += value
        return {k: round(v, 6) if isinstance(v, float) else v for k, v in out.items()}


METER = Meter()


def price_usd(model, input_tokens, output_tokens, cache_write_tokens=0, cache_read_tokens=0):
    """Cost from pricing.yaml, or None if the model is not priced there."""
    price = _PRICES.get(model)
    if price is None:
        return None
    return (input_tokens * price["input"] + output_tokens * price["output"]
            + cache_write_tokens * price.get("cache_write", price["input"])
            + cache_read_tokens * price.get("cache_read", price["input"])) / 1e6


# --------------------------------------------------------------------------- cache
def _cache_path(kind, payload):
    key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return config.CACHE_DIR / kind / key[:2] / f"{key}.json"


def _cache_get(path, mode=None):
    mode = mode or config.LLM_CACHE
    if mode != "off" and path.exists():
        return json.loads(path.read_text())
    if mode == "replay":
        raise CacheMiss(
            f"LLM_CACHE=replay but no cached response at {config.rel(path)}. "
            "Run once online with LLM_CACHE=readwrite to record it."
        )
    return None


def _cache_put(path, record, mode=None):
    if (mode or config.LLM_CACHE) == "off":
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=1))


# --------------------------------------------------------------------------- clients
_clients = {}


def _client(provider):
    if provider not in _clients:
        if provider == "openai":
            from openai import OpenAI

            _clients[provider] = OpenAI(base_url=config.env("OPENAI_BASE_URL"), max_retries=4,
                                        timeout=config.LLM_TIMEOUT_S)
        elif provider == "azure":
            from openai import AzureOpenAI

            _clients[provider] = AzureOpenAI(max_retries=4)  # reads AZURE_OPENAI_* env vars
        elif provider == "anthropic":
            import anthropic

            _clients[provider] = anthropic.Anthropic(max_retries=4, timeout=config.LLM_TIMEOUT_S)
        elif provider == "local":
            from fastembed import TextEmbedding

            # Model files are kept under cache/models (git-ignored) so the live step works offline later.
            _clients[provider] = TextEmbedding(model_name=config.EMBED_MODEL,
                                               cache_dir=str(config.CACHE_DIR / "models"))
        else:
            raise ValueError(f"Unknown provider {provider!r} (use anthropic, openai, azure; local for embeddings)")
    return _clients[provider]


def _temperature():
    t = config.LLM_TEMPERATURE
    return None if str(t).lower() == "none" else float(t)


def _json_instruction(schema):
    return ("\n\nReply with a single JSON object and nothing else. It must match this JSON schema:\n"
            + json.dumps(schema))


def _parse_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(text)


def _call_chat(system, user, schema, schema_name, timeout=None):
    """One provider call. Returns (content, usage dict, served model id)."""
    provider, model = config.LLM_PROVIDER, config.LLM_MODEL
    strict = schema is not None and config.LLM_STRUCTURED == "strict"
    if schema is not None and not strict:
        system += _json_instruction(schema)
    client = _client(provider)
    if timeout:
        client = client.with_options(timeout=timeout, max_retries=0)

    if provider == "anthropic":
        # Current Claude models: no sampling parameters, no forced tool_choice. Structured output
        # goes through output_config.format; the system prompt is marked for prompt caching
        # because the taxonomy prompt repeats on every call.
        output_config = {"effort": config.LLM_EFFORT}
        if strict:
            output_config["format"] = {"type": "json_schema", "schema": schema}
        with client.messages.stream(
                model=model, max_tokens=32000, output_config=output_config,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}]) as stream:
            resp = stream.get_final_message()
        if resp.stop_reason in ("refusal", "max_tokens"):
            raise RuntimeError(f"{model} stopped with stop_reason={resp.stop_reason}; nothing was cached")
        text = "".join(b.text for b in resp.content if b.type == "text")
        u = resp.usage
        usage = {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
                 "cache_write_tokens": u.cache_creation_input_tokens or 0,
                 "cache_read_tokens": u.cache_read_input_tokens or 0}
        return (_parse_json(text) if schema else text), usage, resp.model

    kwargs = dict(model=model, messages=[{"role": "system", "content": system},
                                         {"role": "user", "content": user}])
    if _temperature() is not None:
        kwargs["temperature"] = _temperature()
    if strict:
        kwargs["response_format"] = {"type": "json_schema",
                                     "json_schema": {"name": schema_name, "strict": True, "schema": schema}}
    resp = client.chat.completions.create(**kwargs)
    text = resp.choices[0].message.content or ""
    usage = {"input_tokens": resp.usage.prompt_tokens, "output_tokens": resp.usage.completion_tokens}
    return (_parse_json(text) if schema else text), usage, resp.model


# --------------------------------------------------------------------------- public API
def request_key(system, user, schema=None):
    return {"provider": config.LLM_PROVIDER, "model": config.LLM_MODEL,
            "temperature": None if config.LLM_PROVIDER == "anthropic" else config.LLM_TEMPERATURE,
            "effort": config.LLM_EFFORT if config.LLM_PROVIDER == "anthropic" else None,
            "structured": config.LLM_STRUCTURED, "system": system, "user": user, "schema": schema}


def chat(system, user, schema=None, schema_name="answer", cache=None, timeout=None, return_record=False):
    """Return the model's reply: a dict when `schema` is given, else a string.

    cache   : override LLM_CACHE for this call (the live demo step uses "off")
    timeout : seconds, no retries (the live demo step); default = LLM_TIMEOUT_S with retries
    """
    path = _cache_path("chat", request_key(system, user, schema))
    record = _cache_get(path, cache)
    cached = record is not None
    if not cached:
        start = time.perf_counter()
        content, usage, served = _call_chat(system, user, schema, schema_name, timeout)
        record = {"model": config.LLM_MODEL, "served_model": served, "content": content, **usage,
                  "latency_s": round(time.perf_counter() - start, 3),
                  "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        _cache_put(path, record, cache)
    METER.served_models.add(record.get("served_model") or f"unknown:{record['model']}")
    METER.add(METER.stage, record["model"], record["input_tokens"], record["output_tokens"], cached, "llm",
              record.get("latency_s", 0.0), record.get("cache_write_tokens", 0), record.get("cache_read_tokens", 0))
    return (record["content"], dict(record, cached=cached)) if return_record else record["content"]


def embed(texts, batch_size=96, cache=None):
    """Embed a list of strings; each text is cached individually."""
    vectors, todo = [None] * len(texts), []
    for i, text in enumerate(texts):
        path = _cache_path("embed", {"provider": config.EMBED_PROVIDER, "model": config.EMBED_MODEL,
                                     "dimensions": config.EMBED_DIMENSIONS, "text": text})
        record = _cache_get(path, cache)
        if record is None:
            todo.append((i, path))
        else:
            vectors[i] = record["vector"]
            METER.add(METER.stage, config.EMBED_MODEL, record["tokens"], 0, True, "embed", record.get("latency_s", 0.0))

    for start in range(0, len(todo), batch_size):
        batch = todo[start:start + batch_size]
        t0 = time.perf_counter()
        if config.EMBED_PROVIDER == "local":  # fastembed: no API, no token bill
            embedded = [v.tolist() for v in _client("local").embed([texts[i] for i, _ in batch])]
            tokens_each = 0
        else:
            resp = _client(config.EMBED_PROVIDER).embeddings.create(
                model=config.EMBED_MODEL, input=[texts[i] for i, _ in batch],
                dimensions=config.EMBED_DIMENSIONS)
            embedded = [item.embedding for item in resp.data]
            tokens_each = resp.usage.prompt_tokens / max(len(batch), 1)  # API reports the batch total
        latency_each = (time.perf_counter() - t0) / max(len(batch), 1)
        for (i, path), vector in zip(batch, embedded):
            vectors[i] = vector
            _cache_put(path, {"model": config.EMBED_MODEL, "tokens": tokens_each, "vector": vector,
                              "latency_s": latency_each}, cache)
            METER.add(METER.stage, config.EMBED_MODEL, tokens_each, 0, False, "embed", latency_each)
    return vectors


# --------------------------------------------------------------------------- neo4j-graphrag adapters
def graphrag_adapters():
    """LLM and Embedder objects for neo4j-graphrag that route through this module."""
    import logging

    from neo4j_graphrag.embeddings.base import Embedder
    from neo4j_graphrag.llm import LLMInterface
    from neo4j_graphrag.llm.types import LLMResponse

    logging.getLogger("neo4j_graphrag.llm.base").setLevel(logging.ERROR)  # V1 interface deprecation notice
    stage = METER.stage  # pipeline worker threads don't inherit the caller's stage

    class MeteredLLM(LLMInterface):
        def invoke(self, input, message_history=None, system_instruction=None):
            with METER.as_stage(stage):
                text = chat(system_instruction or "You are a precise information extraction assistant.", input)
            return LLMResponse(content=text)

        async def ainvoke(self, input, message_history=None, system_instruction=None):
            import asyncio

            return await asyncio.to_thread(self.invoke, input, message_history, system_instruction)

    class MeteredEmbedder(Embedder):
        def embed_query(self, text):
            with METER.as_stage(stage):
                return embed([text])[0]

    return MeteredLLM(model_name=config.LLM_MODEL), MeteredEmbedder()


def count_tokens(system, user):
    """Input tokens the provider would bill for this prompt (Anthropic count_tokens; cached).

    Returns None for providers without a counting endpoint - callers must say "not measured"
    rather than estimate.
    """
    if config.LLM_PROVIDER != "anthropic":
        return None
    path = _cache_path("count", {"model": config.LLM_MODEL, "system": system, "user": user})
    record = _cache_get(path)
    if record is None:
        resp = _client("anthropic").messages.count_tokens(
            model=config.LLM_MODEL, system=system, messages=[{"role": "user", "content": user}])
        record = {"model": config.LLM_MODEL, "input_tokens": resp.input_tokens,
                  "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        _cache_put(path, record)
    return record["input_tokens"]


def context_window():
    """The model's input limit from the provider's Models API (cached), or LLM_CONTEXT_TOKENS."""
    if config.env("LLM_CONTEXT_TOKENS"):
        return int(config.env("LLM_CONTEXT_TOKENS"))
    if config.LLM_PROVIDER != "anthropic":
        return None
    path = _cache_path("model_info", {"model": config.LLM_MODEL})
    record = _cache_get(path)
    if record is None:
        info = _client("anthropic").models.retrieve(config.LLM_MODEL)
        record = {"model": config.LLM_MODEL, "max_input_tokens": getattr(info, "max_input_tokens", None)}
        _cache_put(path, record)
    return record["max_input_tokens"]
