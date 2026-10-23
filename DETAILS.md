# Details

Reference material for the [demo script](README.md).

## Outputs (`results/demo_run/` - what the demo shows)

| File | Contents |
|---|---|
| `manifest.json` | model and served model ids, prompt SHA-256 per approach, taxonomy version and hash, corpus manifest hash, filings (accession, dates), git SHA, cache mode, knobs, pricing date |
| `approach_<name>.json` | summary, verified claims (with Item 1A character offsets), rejected claims with reasons, verification stats, shared leaves, company x category/leaf matrices, usage (build/ask), eval |
| `scorecard.json`, `comparison.md` | every metric of SCORING_RULE.md, one column per approach |
| `reruns/<approach>/run_<k>.json` | verified claims of the cache-off reruns (rerun consistency) |
| `audit/run_b/` | run B (approach 3, prompt v2.1) for the audit-trail diff |
| `graph.json` | the exported graph (Company, RiskFactor, FACES_RISK) and exact vs fuzzy RiskFactor counts |
| `governance.json` | precomputed governance moments (the page re-runs them live through serve.py) |
| `corpus_manifest.csv`, `corpus_data_quality.jsonl` | the filings used and the data-quality log |

`results/data_quality_<corpus>.md` lists the data-quality findings (reported, never fixed);
`results/graph_build_<corpus>.json` the graph build usage.

## Configuration (environment variables or `.env`)

| Variable | Default | |
|---|---|---|
| `GROUP` | `auto_semis` | `semis_tech`, `legacy_mixed` (groups.yaml) |
| `TICKERS` | from the group | overrides the group's list |
| `QUESTION` | the question above | |
| `CORPUS` | `edgar_latest` | or `workshop_sample` (see below) |
| `LLM_PROVIDER` / `LLM_MODEL` | `anthropic` / `claude-opus-5-5` | `openai`, `azure`, or any OpenAI-compatible server via `OPENAI_BASE_URL` |
| `LLM_EFFORT` | `low` | Anthropic effort level |
| `LLM_STRUCTURED` | `strict` | `json` = schema only described in the prompt (local models); the code validator applies either way |
| `EMBED_PROVIDER` / `EMBED_MODEL` | `local` / `BAAI/bge-small-en-v1.5` | fastembed on CPU; or `openai` / `text-embedding-3-small` |
| `LLM_CACHE` | `readwrite` | `replay` (offline, fails on a miss) or `off` |
| `NEO4J_URI` / `NEO4J_USERNAME` / `NEO4J_PASSWORD` | `bolt://localhost:7687` / `neo4j` / - | build time only; the demo never needs Neo4j |
| `RAG_TOP_K` | `12` | approach 1 |
| `GRAPH_MODE` | `global` | `vector_seeded` = the workshop's top-k-seeded pattern (kept, not on stage) |
| `GRAPH_RESOLVER` | `fuzzy` | `exact` = name match only, as in the workshop |
| `TAXO_PROMPT_VERSION` | `taxonomy-v2.0` | `taxonomy-v2.1` is run B of the audit trail |
| `MIN_SHARED` | `2` | companies needed for a risk to count as shared |
| `SEC_USER_AGENT` / `SEC_MAX_RPS` | - / `5` | "Name email"; capped at SEC's 10 requests/second |
| `LIVE_TIMEOUT_S` | `20` | deadline of the live step |

Prices for the cost figures live in `pricing.yaml` with the date they were checked. Check them before quoting a number.

## The workshop sample, audited

`python prepare_workshop_sample.py` downloads the Neo4j genai-workshop sample data (pinned commit, into the git-ignored
`data/raw/workshop/`), checks `Company_Filings.csv` against its PDFs and against `Asset_Manager_Holdings.csv`, then builds `CORPUS=workshop_sample` **with the CSV labels unchanged**.
Full log: `results/data_quality_workshop_sample.md`. Highlights:

- **Duplicate company**: two `APPLE INC` rows (CIK 1490054 and 320193).
- **Wrong document**: the row `APPLE INC / AAPL` points to a 10-K from *Verde Bio Holdings*, a smaller reporting company with no risk factors.
- **Mismatched tickers**: Apple's real 10-K is labelled `INTC`; Intel is labelled `INTL` (the holdings file says `INTC`).
- **Different years**: one PDF is Alphabet's 2016 10-K (accession `...-16-...`) next to 2023 filings, and it has no CSV row.
- **Missing files**: Intel, AIG and McDonald's PDFs are referenced but not in the folder; their accession numbers have 9 digits, not 10.
- **Truncated section**: Microsoft's Item 1A is about 3,600 characters in a 2,062-page PDF.
- **Identifiers**: CUSIPs that lost leading zeros, fail the check digit, or hold the CIK instead (PayPal).

## Design decisions and known limits

- **One contract, one verifier.** All approaches return the same claims. `verify.py` validates labels in code against the closed taxonomy (a provider's enum enforcement is not relied on) and locates each quote in that company's own Item 1A. A quote found only in another company's filing is rejected and named as such.
- **Keyword mapping is a fallback only**, for claims that arrive with no label; the count is reported. An invented label is rejected, never re-mapped.
- **Company identity comes from provenance, not the LLM** (approach 2): in Item 1A the filer is the company at risk.
- **The graph only connects what the extractor names the same way.** Shared-risk counts depend on the extraction prompt and the resolver; the demo shows exact vs fuzzy counts.
- **Plain RAG sees only `RAG_TOP_K` chunks**, so an "across all companies" question is capped by retrieval, not by the model.
- **The flat category level saturates**: most companies have most categories. The leaf level is where the industries separate and connect, so the heatmap ranks specific shared risks above generic ones (>= 80% of companies).
- **Ground truth is labelled by a person** (`label_tool.py`). Until it is `verified`, every P/R/F1 carries a DRAFT banner.
- **Latency is only reported when recorded live**; replayed runs show tokens and cost from the original call and "replayed" for time.
- **The test-only fake model can never be frozen**: `run_all.py --freeze` refuses any run whose served model is fake, and a test checks `results/demo_run/`.

## Files

`fetch_10k.py` · `prepare_workshop_sample.py` · `approach0_long_context.py` · `approach1_rag.py` · `approach2_graphrag.py` ·
`approach3_taxonomy.py` · `answer.py` (contract) · `verify.py` (verifier + validator) · `evaluate.py` (scoring) ·
`manifest.py` · `run_all.py` · `rerun.py` · `export_graph.py` · `governance.py` · `estimate_cost.py` · `real_run.py` ·
`label_helper.py` · `label_tool.py` · `build_demo.py` · `serve.py` · `demo/` (page template, screenshots) ·
`check_secrets.py` · `llm.py` (one metered, cached client) · `groups.yaml` · `taxonomy.yaml` · `ground_truth.yaml` ·
`pricing.yaml` · `tests/` (offline; `tests/fake_llm.py` is a test stand-in, never a result)

## References

1. U.S. SEC, "Accessing EDGAR Data" (fair access: declared User-Agent, max 10 requests/second). https://www.sec.gov/os/accessing-edgar-data
2. U.S. SEC, "EDGAR Application Programming Interfaces" (submissions API, `company_tickers.json`). https://www.sec.gov/edgar/sec-api-documentation
3. Neo4j, genai-workshop, `financial_documents` (Apache-2.0). https://github.com/neo4j-product-examples/genai-workshop
4. Neo4j, neo4j-graphrag-python, "User Guide: Knowledge Graph Builder". https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_kg_builder.html
5. OpenAI Cookbook, "Introduction to Structured Outputs". https://cookbook.openai.com/examples/structured_outputs_intro
6. CUSIP check digit ("modulus 10 double-add-double", ANSI X9.6), as implemented in Apache Commons Validator. https://commons.apache.org/validator/apidocs/org/apache/commons/validator/routines/checkdigit/CUSIPCheckDigit.html
7. Anthropic, "Structured outputs" (`output_config.format`). https://platform.claude.com/docs/en/build-with-claude/structured-outputs
8. Anthropic, "Token counting". https://platform.claude.com/docs/en/build-with-claude/token-counting
9. Anthropic, "Pricing". https://platform.claude.com/docs/en/about-claude/pricing
10. BAAI, bge-small-en-v1.5 embedding model. https://huggingface.co/BAAI/bge-small-en-v1.5 - run locally with Qdrant fastembed, https://github.com/qdrant/fastembed
11. WICG, "URL Fragment Text Directives" (`#:~:text=` links to a quote). https://wicg.github.io/scroll-to-text-fragment/
12. Matplotlib, viridis colormap (perceptually uniform, colour-blind friendly), used for the heatmap. https://matplotlib.org/stable/users/explain/colors/colormaps.html

## License

Apache-2.0; see `LICENSE` and `NOTICE` (the workshop sample data used for the audit is Apache-2.0, from the Neo4j genai-workshop).
