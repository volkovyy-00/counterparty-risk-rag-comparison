# One question, three approaches

> **What industry risks connect these counterparties, and which counterparties share each one?**

Ten US-listed companies: six in autos and four in semiconductors (`GROUP=auto_semis` in `config/groups.yaml`). Each
company's latest 10-K, **Item 1A Risk Factors**, from SEC EDGAR. The question is answered three ways under **one
output contract**, then checked by **one verifier** and scored by **one rule** ([SCORING_RULE.md](SCORING_RULE.md)):

| # | Approach | Retrieval and reasoning | Returns |
|---|---|---|---|
| 1 | Plain RAG | top-k vector retrieval, one call | claims `{company, category, leaf, quote, source_ref}` |
| 2 | GraphRAG (Neo4j as the graph store, workshop `SimpleKGPipeline`) | graph traversal of risks shared by 2+ companies | same |
| 3 | Taxonomy-first | the model labels each risk factor with a fixed id (`config/taxonomy.yaml` v2) and a quote; code counts | same |
| L | Control: long context | all ten Item 1A sections in one call, if they fit | same |

The data is public: SEC EDGAR filings, plus the Apache-2.0 sample data of the Neo4j
[genai-workshop](https://github.com/neo4j-product-examples/genai-workshop) for the data-quality audit (see
[NOTICE](NOTICE)). There is no proprietary data, and the views are the author's own.

---

## On stage (offline, ~10 s to start)

```bash
pip install -r requirements.txt
make demo            # builds demo/index.html from results/demo_run/ and opens it
make demo-live       # same, plus the one live step (plain-RAG ask; 20 s deadline, then the recorded answer)
```

Keys: **1–7** switch screens, **G** governance, **T** timer, **D** dark theme, **Esc** closes a panel. Inside screens:
**R** runs the live RAG ask (screen 3), **H** hides generic nodes (4), **L** switches to the leaf level (5), and
**F/O/A** run the governance checks (G). The beat-by-beat script is in [docs/REHEARSAL.md](docs/REHEARSAL.md).

Fallbacks: no Wi-Fi → `make demo`. No Neo4j → nothing changes, because the graph comes from
`results/demo_run/graph.json` and the graph answers from `results/demo_run/graph_qa.json`. No browser → open the PNGs in `demo/fallback/` (`make screenshots`).

## Producing the frozen run (once, online – this is the only step that spends money)

```bash
cp .env.sample .env       # SEC_USER_AGENT, ANTHROPIC_API_KEY (or another provider); never commit .env
docker compose up -d      # local Neo4j with APOC
make real-run ARGS="--stage core"                       # prints the core estimate (cap $20) and stops
LLM_MAX_USD=20 make real-run ARGS="--stage core --confirm-usd 20"
LLM_MAX_USD=10 make real-run ARGS="--stage extras --confirm-usd 10"   # optional, after core
make label                # a person labels the key in the browser -> config/ground_truth.yaml, status: verified
make build-demo           # rebuild after labelling: P/R/F1 lose the DRAFT banner (DRAFT=1 builds before that)
make check-secrets && git add results/demo_run results/spend cache && git commit
```

The corpus in `data/corpus/edgar_latest/` is frozen; the real run never fetches from EDGAR. `src/real_run.py` runs
in two stages, each with its own estimate, cap and "go". `LLM_MAX_USD` must be set to the stage cap, and a spend
log (`results/spend/real_run_<stage>.jsonl`) carries it across every step of the stage.

- **core** (cap $20): builds the graph (calls already in `cache/chat/` replay for free), runs approaches 1, 2, 3
  and L and freezes them into `results/demo_run/`, exports the graph, answers the fixed screen-4 graph questions
  (`src/graph_qa.py`; read-only Cypher, verified claims, `results/demo_run/graph_qa.json`), then builds the
  governance fixtures, the page and the screenshots.
- **extras** (cap $10): (a) 2 reruns of approach 1 and (b) 1 rerun of approach 3, both with the cache off, for
  the rerun-consistency figure; (c) audit run B, approach 3 after a model swap. Over the cap, (b) is dropped first,
  then (c). Approach 2 is not rerun: a graph rebuild is estimated at about $9.4, and screen 6 shows that figure.

Every model call is cached, so `LLM_CACHE=replay python src/run_all.py` reproduces run A with zero API calls.

## Tests

```bash
make test             # offline; uses a test-only fake model that can never be frozen into results/demo_run/
NEO4J_PASSWORD=... make test   # also builds and exports a small graph
```

CI: `.github/workflows/tests.yml` runs these tests offline. It needs no secrets.

Settings, outputs, design decisions, limits and references: [docs/DETAILS.md](docs/DETAILS.md).

## Repository layout

```
src/        the pipeline: fetch, the four approaches, verifier, scoring, demo server (flat scripts, run from the root)
config/     groups.yaml, taxonomy.yaml, pricing.yaml, ground_truth.yaml (the hand-labelled key)
demo/       the page template, label tool and screenshot script
data/       corpora (data/raw/ is downloaded, git-ignored)
results/    frozen runs; results/demo_run/ is what the stage shows
tests/      offline tests with a test-only fake model
docs/       DETAILS.md (settings, design decisions, references), REHEARSAL.md (the 9-minute script),
            GRAPHRAG_V2.md (what changed in approach 2 and why)
SCORING_RULE.md   committed before any real run
```
