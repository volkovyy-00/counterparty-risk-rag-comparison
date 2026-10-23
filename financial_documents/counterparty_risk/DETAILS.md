# Details

Reference material for the [demo script](README.md).

## Outputs (`results/latest/`)

| File | Contents |
|---|---|
| `comparison.md` | side-by-side: answer, citations, eval, tokens, cost, time |
| `<approach>.json` | full answer, citations, evidence text, usage |
| `3_taxonomy_first_matrix.csv` | company x category counts |
| `3_taxonomy_first_rejections.csv` | every quote rejected as not verbatim |
| `../data_quality_<corpus>.md` | data-quality findings (reported, not fixed) |
| `../graph_build_<corpus>.json` | graph build cost and node counts |

**Columns.** *Claims backed* = (risk, company) pairs where a cited excerpt comes from that company's own filing.
*Eval* = precision / recall over (company, category) pairs against `ground_truth.yaml`; free-text risks from
approaches 1-2 are mapped to categories by the keyword lists in `taxonomy.yaml` (deterministic, no LLM judge).
*Build* is paid once; *Ask* is paid per question.

## Configuration (environment variables)

| Variable | Default | |
|---|---|---|
| `TICKERS` | `AAPL,MSFT,NVDA,AMZN,GOOGL,INTC,PYPL,PCG,MCD,AIG` | the counterparty group |
| `QUESTION` | the question above | |
| `CORPUS` | `edgar_latest` | or `workshop_sample` (see below) |
| `LLM_PROVIDER` / `LLM_MODEL` | `openai` / `gpt-4.1-mini` | `azure`, `anthropic`, or any OpenAI-compatible server via `OPENAI_BASE_URL` |
| `EMBED_PROVIDER` / `EMBED_MODEL` | `openai` / `text-embedding-3-small` | |
| `LLM_CACHE` | `readwrite` | `replay` (offline) or `off` |
| `NEO4J_URI` / `NEO4J_USERNAME` / `NEO4J_PASSWORD` | `bolt://localhost:7687` / `neo4j` / - | |
| `RAG_TOP_K` | `12` | approach 1 (and `vector_seeded` mode) |
| `GRAPH_MODE` | `global` | `vector_seeded` = the workshop's top-k-seeded Cypher pattern |
| `GRAPH_RESOLVER` | `fuzzy` | `exact` = name match only, as in the workshop |
| `MIN_SHARED` | `2` | companies needed for a risk to count as shared |
| `SEC_MAX_RPS` | `5` | capped at SEC's 10 requests/second |

Prices for the cost column live in `pricing.yaml`. Check your provider's current prices before quoting a number.

## The workshop sample, audited

`python prepare_workshop_sample.py` checks `../data/Company_Filings.csv` against its PDFs and against
`../data/Asset_Manager_Holdings.csv`, then builds `CORPUS=workshop_sample` **with the CSV labels unchanged**.
Full log: `results/data_quality_workshop_sample.md`. Highlights:

- **Duplicate company**: two `APPLE INC` rows (CIK 1490054 and 320193).
- **Wrong document**: the row `APPLE INC / AAPL` points to a 10-K from *Verde Bio Holdings*, a smaller reporting company with no risk factors.
- **Mismatched tickers**: Apple's real 10-K is labelled `INTC`; Intel is labelled `INTL` (the holdings file says `INTC`).
- **Different years**: one PDF is Alphabet's 2016 10-K (accession `...-16-...`) next to 2023 filings, and it has no CSV row.
- **Missing files**: Intel, AIG and McDonald's PDFs are referenced but not in the folder; their accession numbers have 9 digits, not 10.
- **Truncated section**: Microsoft's Item 1A is about 3,600 characters in a 2,062-page PDF.
- **Identifiers**: CUSIPs that lost leading zeros, fail the check digit, or hold the CIK instead (PayPal).

## Design decisions and known limits

- **Company identity comes from provenance, not the LLM** (approach 2): in Item 1A the filer is the company at risk.
- **The graph only connects what the extractor names the same way.** The prompt asks for generic 2-5 word names and a fuzzy resolver merges near-duplicates. Shared-risk counts depend on both; compare `GRAPH_RESOLVER=exact`.
- **Plain RAG sees only `RAG_TOP_K` chunks**, so an "across all companies" question is capped by retrieval, not by the model.
- **Quote check**: case-sensitive substring match after normalising whitespace, curly quotes and dashes; quotes under 20 characters are rejected. Checked only against the same company's Item 1A.
- **Item 1A extraction** takes the longest heading-to-heading span (skips the table of contents). Short or missing sections are logged, not patched.
- **Ground truth is a draft** until a person checks it against the filings in `manifest.csv`. The keyword mapping used to score approaches 1-2 is coarse and can over- or under-credit them; `unmapped_risks` in each JSON shows what scored nothing.
- **Cached latency is not live latency.** Replayed runs report tokens and cost from the original call and say how many calls came from cache.

## Files

`fetch_10k.py` (step 1) · `prepare_workshop_sample.py` · `approach1_rag.py` · `approach2_graphrag.py` ·
`approach3_taxonomy.py` · `run_all.py` · `evaluate.py` · `label_helper.py` · `llm.py` (one metered, cached client) ·
`taxonomy.yaml` · `ground_truth.yaml` · `pricing.yaml` · `tests/` (offline; `tests/fake_llm.py` is a test stand-in, never a result)

## References

1. U.S. SEC, "Accessing EDGAR Data" (fair access: declared User-Agent, max 10 requests/second). https://www.sec.gov/os/accessing-edgar-data
2. U.S. SEC, "EDGAR Application Programming Interfaces" (submissions API, `company_tickers.json`). https://www.sec.gov/edgar/sec-api-documentation
3. Neo4j, genai-workshop, `financial_documents` (Apache-2.0). https://github.com/neo4j-product-examples/genai-workshop
4. Neo4j, neo4j-graphrag-python, "User Guide: Knowledge Graph Builder". https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_kg_builder.html
5. OpenAI Cookbook, "Introduction to Structured Outputs". https://cookbook.openai.com/examples/structured_outputs_intro
6. CUSIP check digit ("modulus 10 double-add-double", ANSI X9.6), as implemented in Apache Commons Validator. https://commons.apache.org/validator/apidocs/org/apache/commons/validator/routines/checkdigit/CUSIPCheckDigit.html

## License

Derived from the Apache-2.0 Neo4j genai-workshop; see `../LICENSE`. This folder adds new files only.
