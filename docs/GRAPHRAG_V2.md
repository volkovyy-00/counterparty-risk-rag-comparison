# GraphRAG v2 (approach 2)

Approach 2 started from the Neo4j workshop's `SimpleKGPipeline` pattern. That version is kept unchanged as
`GRAPH_PROMPT_VERSION=graph-v1-workshop` (same prompt hash as before, `33d67ddc…`) so it can be compared. The
default is now `graph-v2`, built for one question: *which industry risks connect these auto and semiconductor
counterparties?* Approaches 0, 1 and 3, the claims contract, the verifier and the scoring are unchanged.

## What changed and why

| | v1 (workshop) | v2 | Why |
|---|---|---|---|
| Chunks | 4,000 characters, 200 overlap, cut anywhere (~257 for 10 filings) | Whole paragraphs packed up to 6,000 characters, no overlap, the section sub-heading carried along (~162) | Risk factors and quotes stay intact; overlap duplicated mentions |
| Output | JSON parsed from free text, generic Person/KNOWS example | Provider-enforced JSON schema, system prompt cached, two worked examples from an airline and a retailer (outside the demo group) | [R3], [R4], [R10] |
| Unit | `RiskFactor {name}` only | `RiskMention {risk_name, detail, quote, specificity, drivers}` → resolved `RiskFactor`; named `ExposureDriver`s (places, counterparties, inputs, policies, end markets) | [R4], [R11]: shared concrete dependencies are what a graph can show and a fixed taxonomy cannot |
| Evidence | none on nodes; the ask got the first 4,000-character chunk per company | the model copies a quote; **code** finds its span (`verify.locate`) inside that chunk, otherwise the mention is dropped with a reason | [R5]: never ask the model for offsets |
| Resolution | exact name, then RapidFuzz `WRatio >= 0.8` | normalise + exact; candidates = embedding neighbours (cosine >= 0.80, top 8) ∪ `token_set_ratio >= 90`; components over 25 split; **one LLM call per component** decides "same driver and same mechanism"; a code rule refuses known opposite pairs | [R6]. WRatio misses synonyms ("Chip shortage" / "Semiconductor shortages" 0.70) and joins opposites ("Supply chain disruption" / "Supply chain" 0.90) |
| Generic | degree >= 80% of companies | `n_companies >= ceil(0.8·N)` **or** (boilerplate share >= 0.75 and n >= 3); idf = ln(N/n); kept but ranked last and hidden by **H** | [R9]: boilerplate is real but not worthless. The threshold is a design choice and is shown on screen |
| Ask | risks with >= 2 companies + first chunk text | specific risks first (autos ↔ semis, then n × idf), generic ones listed separately, the verified quote's paragraph as evidence, plus shared ExposureDrivers | [R1] corpus-level aggregation over shared nodes; [R11] two levels: themes and named entities |

Not adopted: community summaries ([R1]; ten filings fit in one long-context call, approach 0), reflection or
gleaning ([R7]; about twice the output tokens, and single-pass was most faithful), LightRAG or HippoRAG as
dependencies, temporal graphs, automatic schema discovery (more non-determinism to explain). GraphRAG is not
uniformly better than plain RAG ([R2]), and that is why the talk compares approaches under one scoring rule.

### Keep-apart rule (code, after the LLM)

A proposed group is split back into singletons, and logged as `rule: …`, if it mixes: supplier vs customer
concentration; an input shortage vs its price; physical climate vs climate regulation; export controls vs import
tariffs; recalls vs product liability; own plants vs suppliers. Patterns: `graph_resolve.KEEP_APART`.

## Files

| File | Contents |
|---|---|
| `src/graph_v2.py` | chunker, prompt, schema, extraction, validation |
| `src/graph_resolve.py` | resolution, keep-apart rule, generic score, driver aliases |
| `config/graph_aliases.yaml` | driver aliases (PRC → China, IRA → Inflation Reduction Act, …) |
| `src/approach2_graphrag.py` | build (v1 or v2), Neo4j load, ask |
| `src/graph_quality.py` | metrics from the build files, no Neo4j |
| `src/graph_check.py` | the hand-check CSV and its score |
| `src/graph_ab.py` | the A/B with its cost gate and report |

Outputs in `results/`:
- `graph_extract_<corpus>_graph-v2.jsonl`: raw replies.
- `graph_rejections_<corpus>.json`: dropped mentions, with reasons.
- `graph_resolution_<corpus>.json`: every component, merge, rejected merge and candidate pair.
- `graph_snapshot_<corpus>_graph-v2.json`: what was loaded into Neo4j; also the source of `graph.json`.
- `graph_quality_<corpus>_<version>.json` and `graph_check_<version>.csv`.

## How to run

```bash
python src/estimate_cost.py                   # v1 vs v2 graph cost and the A/B, no model call
make graph-ab                                 # prints the A/B estimate and stops
make graph-ab ARGS="--confirm-usd 5"          # A/B on GM, NXPI, TXN -> results/graph_ab_<date>.md
python src/approach2_graphrag.py build --reset   # full build (current GRAPH_PROMPT_VERSION)
make graph-quality && make graph-check        # metrics; then fill y/n in the CSV and run: python src/graph_check.py --score
GRAPH_PROMPT_VERSION=graph-v1-workshop python src/approach2_graphrag.py build --reset   # the baseline
```

The A/B passes when B has: quote verification >= 95%; paragraph coverage >= 85%; a lower singleton share than A;
at least 3 shared specific RiskFactors, at least 1 of them auto ↔ semis; and no keep-apart pair among its approved
merges. If B fails, the report says why and nothing is iterated without asking.

## Honest limits

- **Single model, single pass.** The same model extracts and adjudicates merges. The hand-check CSV
  (30 mentions, the 20 merge decisions nearest the threshold) is the only independent check, and its precision is
  reported only once a person has filled it.
- **Thresholds are choices.** Cosine 0.80, token_set 90 and generic share 0.8 come from the literature ([R6] uses
  cosine 0.8) and judgement, not tuning. They are shown, not hidden.
- **Recall is a proxy.** Paragraph coverage counts paragraphs with at least one verified quote. It does not
  check that every risk in a paragraph was found.
- **The keep-apart rule is a word list.** It catches the six known pairs and nothing else.
- **v1 has no quotes**, so its quote-based metrics are reported as not applicable rather than estimated.
- **Driver matching is literal.** A driver is kept only if its name appears in the quote's paragraph, so a
  correct but paraphrased driver is dropped. The count is logged.

## References

- [R1] Edge et al., *From Local to Global: A Graph RAG Approach to Query-Focused Summarization*, arXiv 2404.16130 (2024). https://arxiv.org/abs/2404.16130
- [R2] Han et al., *RAG vs. GraphRAG: A Systematic Evaluation*, arXiv 2502.11371 (2025). https://arxiv.org/abs/2502.11371 · *When to use Graphs in RAG*, arXiv 2506.05690 (2025). https://arxiv.org/abs/2506.05690 · *How Significant Are the Real Performance Gains?*, arXiv 2506.06331 (2025). https://arxiv.org/abs/2506.06331 · Vendor results (Microsoft Research, LazyGraphRAG blog post, Nov 2024; BenchmarkQED, 2025) are self-reported.
- [R3] Neo4j, neo4j-graphrag-python User Guide: Knowledge Graph Builder. https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_kg_builder.html · Anthropic, Structured outputs. https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- [R4] LlamaIndex `SchemaLLMPathExtractor` (strict schema) and LangChain `LLMGraphTransformer` (`allowed_relationships`, `strict_mode`), library documentation · FinReflectKG, arXiv 2508.17906 (2025). https://arxiv.org/abs/2508.17906
- [R5] google/langextract (2025). https://github.com/google/langextract
- [R6] Bratanic, Neo4j developer blog (Jul 2024): embedding kNN, connected components, edit-distance filter, LLM approve/reject. https://neo4j.com/blog/developer/global-graphrag-neo4j-langchain/ · KGGen, arXiv 2502.09956 (2025). https://arxiv.org/abs/2502.09956 · Zep/Graphiti, arXiv 2501.13956 (2025). https://arxiv.org/abs/2501.13956 · HippoRAG 2, arXiv 2502.14802 (2025). https://arxiv.org/abs/2502.14802
- [R7] Edge et al. 2024 (self-reflection / gleaning), as [R1] · FinReflectKG-EvalBench, arXiv 2510.05710 (2025). https://arxiv.org/abs/2510.05710
- [R8] FinReflectKG and FinReflectKG-EvalBench, as [R4] and [R7].
- [R9] Humanities and Social Sciences Communications (2024), article s41599-024-04169-w (summarises the Lang & Stice-Lawrence boilerplate measure). https://www.nature.com/articles/s41599-024-04169-w · Grundy & Petry, paper presented at the EFMA 2021 annual meeting (Item 1A informativeness).
- [R10] Microsoft GraphRAG, Auto prompt tuning. https://microsoft.github.io/graphrag/prompt_tuning/auto_prompt_tuning/
- [R11] LightRAG, arXiv 2410.05779 (2024). https://arxiv.org/abs/2410.05779
