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


class CacheMiss(RuntimeError):
    pass


# --------------------------------------------------------------------------- meter
class Meter:
    """Adds up calls, tokens and cost per named stage (e.g. 'rag.ask')."""

    def __init__(self):
        self._lock = threading.Lock()
        self._local = threading.local()
        self.stages = defaultdict(lambda: defaultdict(float))

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

    def add(self, stage, model, input_tokens, output_tokens, cached, kind):
        price = _PRICES.get(model)
        with self._lock:
            s = self.stages[stage]
            s[f"{kind}_calls"] += 1
            s["cached_calls"] += 1 if cached else 0
            s["input_tokens"] += input_tokens
            s["output_tokens"] += output_tokens
            if price is None:
                s["unpriced_calls"] += 1
            else:
                s["cost_usd"] += (input_tokens * price["input"] + output_tokens * price["output"]) / 1e6

    def summary(self, *stages):
        out = defaultdict(float)
        for name in stages:
            for key, value in self.stages.get(name, {}).items():
                out[key] += value
        return {k: round(v, 6) if isinstance(v, float) else v for k, v in out.items()}


METER = Meter()


# --------------------------------------------------------------------------- cache
def _cache_path(kind, payload):
    key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return config.CACHE_DIR / kind / key[:2] / f"{key}.json"


def _cache_get(path):
    if config.LLM_CACHE != "off" and path.exists():
        return json.loads(path.read_text())
    if config.LLM_CACHE == "replay":
        raise CacheMiss(
            f"LLM_CACHE=replay but no cached response at {config.rel(path)}. "
            "Run once online with LLM_CACHE=readwrite to record it."
        )
    return None


def _cache_put(path, record):
    if config.LLM_CACHE == "off":
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=1))


# --------------------------------------------------------------------------- clients
_clients = {}


def _client(provider):
    if provider not in _clients:
        if provider == "openai":
            from openai import OpenAI

            _clients[provider] = OpenAI(base_url=config.env("OPENAI_BASE_URL"), max_retries=4)
        elif provider == "azure":
            from openai import AzureOpenAI

            _clients[provider] = AzureOpenAI(max_retries=4)  # reads AZURE_OPENAI_* env vars
        elif provider == "anthropic":
            import anthropic

            _clients[provider] = anthropic.Anthropic(max_retries=4)
        else:
            raise ValueError(f"Unknown provider {provider!r} (use openai, azure or anthropic)")
    return _clients[provider]


def _temperature():
    t = config.LLM_TEMPERATURE
    return None if str(t).lower() == "none" else float(t)


def _call_chat(system, user, schema, schema_name):
    provider, model = config.LLM_PROVIDER, config.LLM_MODEL
    temperature = _temperature()
    if provider == "anthropic":
        kwargs = dict(model=model, max_tokens=8000, system=system,
                      messages=[{"role": "user", "content": user}])
        if temperature is not None:
            kwargs["temperature"] = temperature
        if schema:
            kwargs["tools"] = [{"name": schema_name, "description": "Return the answer.", "input_schema": schema}]
            kwargs["tool_choice"] = {"type": "tool", "name": schema_name}
        resp = _client(provider).messages.create(**kwargs)
        if schema:
            content = next(b.input for b in resp.content if b.type == "tool_use")
        else:
            content = "".join(b.text for b in resp.content if b.type == "text")
        return content, resp.usage.input_tokens, resp.usage.output_tokens

    kwargs = dict(model=model, messages=[{"role": "system", "content": system},
                                         {"role": "user", "content": user}])
    if temperature is not None:
        kwargs["temperature"] = temperature
    if schema:
        kwargs["response_format"] = {"type": "json_schema",
                                     "json_schema": {"name": schema_name, "strict": True, "schema": schema}}
    resp = _client(provider).chat.completions.create(**kwargs)
    text = resp.choices[0].message.content or ""
    content = json.loads(text) if schema else text
    return content, resp.usage.prompt_tokens, resp.usage.completion_tokens


# --------------------------------------------------------------------------- public API
def chat(system, user, schema=None, schema_name="answer"):
    """Return the model's reply: a dict when `schema` is given, else a string."""
    request = {"provider": config.LLM_PROVIDER, "model": config.LLM_MODEL,
               "temperature": config.LLM_TEMPERATURE, "system": system, "user": user,
               "schema": schema}
    path = _cache_path("chat", request)
    record = _cache_get(path)
    cached = record is not None
    if not cached:
        start = time.perf_counter()
        content, tokens_in, tokens_out = _call_chat(system, user, schema, schema_name)
        record = {"model": config.LLM_MODEL, "content": content, "input_tokens": tokens_in,
                  "output_tokens": tokens_out, "latency_s": round(time.perf_counter() - start, 3),
                  "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        _cache_put(path, record)
    METER.add(METER.stage, record["model"], record["input_tokens"], record["output_tokens"], cached, "llm")
    return record["content"]


def embed(texts, batch_size=96):
    """Embed a list of strings; each text is cached individually."""
    vectors, todo = [None] * len(texts), []
    for i, text in enumerate(texts):
        path = _cache_path("embed", {"provider": config.EMBED_PROVIDER, "model": config.EMBED_MODEL,
                                     "dimensions": config.EMBED_DIMENSIONS, "text": text})
        record = _cache_get(path)
        if record is None:
            todo.append((i, path))
        else:
            vectors[i] = record["vector"]
            METER.add(METER.stage, config.EMBED_MODEL, record["tokens"], 0, True, "embed")

    for start in range(0, len(todo), batch_size):
        batch = todo[start:start + batch_size]
        resp = _client(config.EMBED_PROVIDER).embeddings.create(
            model=config.EMBED_MODEL, input=[texts[i] for i, _ in batch],
            dimensions=config.EMBED_DIMENSIONS)
        tokens_each = resp.usage.prompt_tokens / max(len(batch), 1)  # API reports the batch total
        for (i, path), item in zip(batch, resp.data):
            vectors[i] = item.embedding
            _cache_put(path, {"model": config.EMBED_MODEL, "tokens": tokens_each, "vector": item.embedding})
            METER.add(METER.stage, config.EMBED_MODEL, tokens_each, 0, False, "embed")
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
