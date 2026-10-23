# One question, three approaches

> **What industry risks connect these counterparties, and which counterparties share each one?**

Ten public companies, their latest 10-K **Item 1A Risk Factors** from SEC EDGAR, and three ways to answer:

| # | Approach | The LLM does... | Code does... |
|---|---|---|---|
| 1 | **Plain RAG** | answer from the top-k retrieved chunks | chunk, embed, retrieve |
| 2 | **GraphRAG** (Neo4j, workshop `SimpleKGPipeline`) | extract `RiskFactor` nodes; summarise the traversal | link companies by provenance; find risks shared by 2+ companies |
| 3 | **Taxonomy-first** | map each risk factor to a fixed id in `taxonomy.yaml` + verbatim quote | reject quotes not in the source; build company x category matrix; rank |

Public data only: SEC EDGAR filings and the Apache-2.0 workshop sample in `../data`. No proprietary data.

---

## 0. Set up (once, ~5 min)

```bash
cd financial_documents/counterparty_risk
pip install -r requirements.txt
cp .env.sample .env            # set SEC_USER_AGENT, OPENAI_API_KEY (or another provider)
docker compose up -d           # local Neo4j with APOC  (or point NEO4J_URI at Aura)
python -m pytest tests -q      # offline self-test, no API key needed
```

## 1. The day before (online)

```bash
python fetch_10k.py                          # 10-Ks + Item 1A + data-quality log     ~1 min
python approach2_graphrag.py build --reset   # knowledge graph (deletes ALL nodes)   ~10-20 min
python run_all.py                            # all three, records the LLM cache      ~3-5 min
python label_helper.py                       # then check ground_truth.yaml, set status: verified
LLM_CACHE=replay python run_all.py           # rehearse with Wi-Fi OFF
```

Times are estimates for 10 filings with `gpt-4.1-mini`; your first run writes the real ones to `results/`.

## 2. On stage

```bash
python run_all.py                  # ~seconds: every call is a cache hit
cat results/data_quality_edgar_latest.md
```

## 3. If the conference Wi-Fi fails

| Level | Command | Needs |
|---|---|---|
| A | `LLM_CACHE=replay python run_all.py` | cache from step 1, local Neo4j (graph is kept in the Docker volume) |
| B | `LLM_CACHE=replay python run_all.py --approaches 1,3` | cache only - no Neo4j |
| C | `python run_all.py --show` | nothing - prints the last saved comparison |

Copy `cache/`, `data/corpus/` and `results/` to the demo laptop (or commit them).
`replay` never calls an API and stops on a cache miss; it never makes up an answer.

---

**Results** land in `results/latest/comparison.md` (plus one JSON per approach, the taxonomy matrix and
rejected quotes). Settings are environment variables, listed in [DETAILS.md](DETAILS.md) with the data-quality
findings, design decisions, known limits and references.
