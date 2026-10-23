# One question, three approaches

> **What industry risks connect these counterparties, and which counterparties share each one?**

Ten US-listed companies: six in autos and four in semiconductors (`GROUP=auto_semis` in `groups.yaml`). Each
company's latest 10-K, **Item 1A Risk Factors**, from SEC EDGAR. The question is answered three ways under **one
output contract**, then checked by **one verifier** and scored by **one rule** ([SCORING_RULE.md](SCORING_RULE.md)):

| # | Approach | Retrieval and reasoning | Returns |
|---|---|---|---|
| 1 | Plain RAG | top-k vector retrieval, one call | claims `{company, category, leaf, quote, source_ref}` |
| 2 | GraphRAG (Neo4j as the graph store, workshop `SimpleKGPipeline`) | graph traversal of risks shared by 2+ companies | same |
| 3 | Taxonomy-first | the model labels each risk factor with a fixed id (`taxonomy.yaml` v2) and a quote; code counts | same |
| L | Control: long context | all ten Item 1A sections in one call, if they fit | same |

The data is public: SEC EDGAR filings and the Apache-2.0 workshop sample in `../data`. There is no proprietary
data, and the views are the author's own.

---

## On stage (offline, ~10 s to start)

```bash
cd financial_documents/counterparty_risk
pip install -r requirements.txt
make demo            # or ./demo.sh - builds demo/index.html from results/demo_run/ and opens it
make demo-live       # same, plus the one live step (plain-RAG ask; 20 s deadline, then the recorded answer)
```

Keys: **1–7** switch screens, **G** governance, **T** timer, **D** dark theme, **Esc** closes a panel. Inside screens:
**R** runs the live RAG ask (screen 3), **H** hides generic nodes (4), **L** switches to the leaf level (5), and
**F/O/A** run the governance checks (G). The beat-by-beat script is in [REHEARSAL.md](REHEARSAL.md).

Fallbacks: no Wi-Fi → `make demo`. No Neo4j → nothing changes, because the graph comes from
`results/demo_run/graph.json`. No browser → open the PNGs in `demo/fallback/` (`make screenshots`).

## Producing the frozen run (once, online – this is the only step that spends money)

```bash
cp .env.sample .env       # SEC_USER_AGENT, ANTHROPIC_API_KEY (or another provider); never commit .env
docker compose up -d      # local Neo4j with APOC
make estimate             # prints the cost estimate; nothing is called
make real-run             # stops if the estimate is over $5
make real-run ARGS="--confirm-usd 25"
make label                # a person labels the key in the browser -> ground_truth.yaml, status: verified
make build-demo           # rebuild after labelling: P/R/F1 lose the DRAFT banner
make check-secrets && git add results/demo_run cache data/corpus && git commit
```

`real_run.py` does the following in order:

1. Fetches the 10-Ks, respecting SEC fair-access rules and logging data-quality issues without fixing them.
2. Builds the graph.
3. Runs approaches 1, 2, 3 and L, then freezes the result into `results/demo_run/`.
4. Exports the graph.
5. Records run B for the audit trail.
6. Adds 2 more runs with the cache off for the rerun-consistency figure.
7. Builds the governance fixtures, the page and the screenshots.

Every model call is cached, so `LLM_CACHE=replay python run_all.py` reproduces run A with zero API calls.

## Tests

```bash
make test             # offline; uses a test-only fake model that can never be frozen into results/demo_run/
NEO4J_PASSWORD=... make test   # also builds and exports a small graph
```

CI: `.github/workflows/counterparty-risk-tests.yml` runs these tests offline. It needs no secrets.

Settings, outputs, design decisions, limits and references: [DETAILS.md](DETAILS.md).
