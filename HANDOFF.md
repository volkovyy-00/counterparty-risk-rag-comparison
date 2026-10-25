# Session handoff — counterparty-risk-rag-comparison

Read this first in a new session, then `README.md` and `docs/GRAPHRAG_V2.md`. Written 25 Oct 2026.

## The project
A 45-minute talk, *How AI Rewired the Business Analyst Role* (AI for Business 2026, Prague), with a 9-minute live
demo on 4 Nov 2026. The demo answers one question three ways on public SEC 10-K Item 1A text: plain RAG,
GraphRAG (Neo4j) and taxonomy-first, plus a long-context control row, all checked by one verifier and scored by
one rule (`SCORING_RULE.md`). It also has a static offline web app (`make demo`). The group is `auto_semis`: GM F
TSLA APTV BWA LEA (autos) and NXPI MCHP ON TXN (semis).

## Hard constraints (from the user, keep them)
- Public or synthetic data only. Nothing from the user's employer: no names, tools, data or numbers, anywhere,
  including commits.
- No vendor pitch. Don't frame banks as having "broken processes" or "stalled pilots". The views are the
  author's own.
- Every source goes in a references list. No video citations in the body text.
- **No paid run without an explicit "go".** Print the estimate first. Agreed caps: graph A/B ≤ $5; core run
  (taxonomy + graph + three answers) ≤ $20; then audit or reruns ≤ $10. Never start a run whose estimate
  exceeds its cap.
- If something can't be measured, say so; don't estimate in its place. The fake LLM is for tests only and can
  never be frozen into `results/demo_run/`.
- SEC fair access: a declared User-Agent, ≤ 5 requests per second by default, never above 10. The corpus is
  already fetched and frozen.
- The human labels the ground truth, never Claude. Keep the Apache-2.0 LICENSE and NOTICE.

## Repository state
- Remote https://github.com/volkovyy-00/counterparty-risk-rag-comparison: `main` is at `1c3bdc5` and holds
  GraphRAG v2 and taxonomy v3 (both merged). `standalone`, `demo-ready`, `graphrag-v2` and `taxonomy-v3` are older
  branches; the user may delete them (this session's proxy cannot delete branches).
- **Branch `demo`** (from `1c3bdc5`): the real-data demo work as a clean PR into main. It replaces `demo-real`,
  whose history carried 38 MiB of caches and retaken screenshots: the user approved deleting `demo-real` on origin
  once `demo` is merged.
- **Tracked vs Release:** git tracks code, config (with the verified key), `data/corpus/`, `results/demo_run/`
  and `results/spend/`. The fallback PNGs, the LLM replay cache (`cache/chat`, `cache/count`) and every other
  `results/` file are in the Release `demo-artifacts-2026-10-25`; `make fetch-artifacts [WHAT=...]` restores them.
  `make demo` needs none of them. New cache entries or screenshots mean a new Release (tag + the pinned SHA256 in
  `scripts/fetch_artifacts.sh`).
- Layout: `src/` code, `config/` YAML (groups, taxonomy, pricing, ground_truth, graph_aliases), `demo/` page,
  `tests/`, `docs/` (DETAILS, REHEARSAL, GRAPHRAG_V2), `data/corpus/edgar_latest/` (frozen 10-K Item 1A text).
- Tests: 45 passed and 2 skipped without Neo4j; 46 passed and 1 skipped with Neo4j. The remaining skip is the
  "frozen demo run" check, because `results/demo_run/` doesn't exist yet.

## Environment (cloud container)
- Environment variables set by the user: the Anthropic key as `API_KEY` (`config.py` maps it to
  `ANTHROPIC_API_KEY`), `SEC_USER_AGENT`, and `OPEN_ROUTER_API` (an OpenRouter key; the code doesn't read it
  yet).
- Allowed domains include www.sec.gov, data.sec.gov, huggingface.co, *.hf.co and openrouter.ai.
- `.env` is git-ignored, so recreate it in a new container:
  `SEC_USER_AGENT="<from env>"` and `NEO4J_PASSWORD=demo-password`.
- Neo4j: start Docker with `nohup dockerd &`, then `docker start neo4j-demo`. If the container is missing, run
  `docker compose up -d`.
- Local embeddings: `BAAI/bge-small-en-v1.5` through fastembed, cached under `cache/models/` (git-ignored); it
  downloads on first use. OpenRouter lists embedding models (e.g. `openai/text-embedding-3-small`,
  `qwen/qwen3-embedding-*`, `voyageai/voyage-4*`), but switching would change approach 1. The user leans
  towards cloud embeddings; it isn't decided and isn't done.

## What GraphRAG v2 is (done)
See `docs/GRAPHRAG_V2.md`.
- `GRAPH_PROMPT_VERSION=graph-v2` (default) or `graph-v1-workshop` (unchanged baseline, prompt hash
  `33d67ddc…`).
- Chunks: whole paragraphs, 6,000 characters, no overlap, about 162 chunks.
- Extraction: structured output with a cached system prompt (2,182 tokens).
- Quotes: located in their chunk by code; failures are rejected with a reason.
- Resolution: embedding + lexical candidates, one LLM call per candidate group, and a keep-apart code rule.
- Generic score, ExposureDrivers, quote-level ask evidence.
- `make graph-quality`, `make graph-check` (hand-check CSV), `make graph-ab` (cost-gated).
- Screen 4 now uses a ranked column layout; clicking a node shows its quote in about 420 characters of context
  plus a full-filing view. **The user confirmed this drawer is right as it is.** Screen 6 has a graph-quality
  row.

## Done on 25 Oct 2026 (second session)
- **Graph A/B ran and passes** (`results/graph_ab_2026-10-25.md`, history in `docs/GRAPHRAG_V2.md`). B went
  from coverage 83.8% / singletons 92.2% / 7 shared specific to 89.0% / 74.8% / 18 (10 auto ↔ semis), no
  keep-apart breach. Fixes: comparable risk names, a mention per later paragraph with another driver, page-break
  fragments joined, candidates from names (cosine 0.75), components of 12, same-words merge, keep-apart splits only
  the smaller side (+ natural disaster vs yield), alias keys ("U.S."). The singleton bar was changed with the user's
  approval to "below graph-v2's first run (92.2%)", because A's 70.5% comes from over-merging.
- **Spend:** $3.41 in total for the A/B series (first $5 cap: $2.05; second $5 cap: $1.36). All calls are in
  `cache/chat/` (Release asset `replay-cache.tar.gz`), so the 3 A/B filings replay for free in the full build.
- **Screen 4 = ask the graph** (`src/graph_qa.py`, `make graph-qa`): 5 fixed questions on 3 read-only Cypher
  templates; the page draws exactly the returned rows, shows Cypher + template + params, opens the quote drawer
  from any node; empty rows → no model call, "No bridge found – the graph won't invent a link". Stage chips:
  GM + NXPI, most shared vs most specific (landing), what links autos to chips; M shows 2 more; O whole graph.
  No free-text input; Text2Cypher left out. Rehearsal beat 4 is timed per chip. The answers are written by
  `GRAPH_QA_MODEL` (Haiku 5.5, effort low, ~$0.01 for all five); the rest of the pipeline stays on `LLM_MODEL`.
- **Test page (private):** https://claude.ai/artifact/BgdoQHpoYVn2NAD9ZnJ96W. It has real Haiku answers ($0.0074)
  on the **3-filing A/B graph only (GM, NXPI, TXN)**, so the two Q&A questions are empty, and the other screens are
  fixture data. The 10-company answers come from the real run: its `build --reset` builds the full graph (~$9.60
  on Opus), then the graph-QA step answers. The user deferred a separate full build ("not now"); if one is wanted
  before the real run, the cap they gave is $12.
- `python src/approach2_graphrag.py load --reset --snapshot <file>` reloads a saved v2 graph with no model call.
- **Screen 5 overflow fixed** (fixed 520px side column, cross-leaf counts; cells unchanged) and **screen 2
  overflow fixed** (132px; 6 findings + "N more"). All 23 screenshot states fit at 1920×1080 and 1280×720.
- Two commit messages (535c5ea, a80e81a) have the attribution lines on the subject paragraph; rewriting pushed
  history was not allowed. Harmless.

## Taxonomy v3 (approach 3, merged into main)
- `TAXO_PROMPT_VERSION=taxonomy-v3.0` is the default: Item 1A is split by risk-factor heading
  (`corpus.split_risk_factors`) and packed into whole-section windows. The prompt asks for **one label per risk
  factor** plus an unscored `driver` note. `taxonomy-v2.x` keeps the fixed paragraph windows and its prompt.
  `taxonomy-v3.1` (adds "prefer the most specific leaf") stays runnable but is no longer the default run B.
- Split report (`results/taxonomy_split_report.md`, no model call): 8 of 10 filings split by heading. GM and F
  set their headings in bold inside the first paragraph, so they use the paragraph split (`corpus.split_paragraphs`:
  each paragraph whose first sentence reads like a heading is a section). Until the core run they fell back to
  fixed windows with no `[RF n]` markers, and the v3 prompt returned almost nothing for them (GM 5 claims, F 0).
- Coverage check (`results/taxonomy_coverage.md`): no new leaf justified.
- A/B on NXPI and LEA (`results/taxonomy_ab/report.md`, $1.15): v3.0 duplicate-label rate 0% (v2.0: 3.7% / 11.1%),
  quote pass 100% / 96.8%, fewer labels per risk factor (1.05 / 1.03). OTHER drivers listed on screen 5, not scored.

## Cost estimates (Opus 5.5, input tokens measured, output tokens assumed)
- Full graph build: v1 $7.97, v2 about $9.6 (v2 extraction now returns somewhat more mentions per chunk).
- The old one-shot freeze (2 reruns of 1, 2, 3 + audit run B) was estimated at $50.79 ($21.01 with no reruns);
  too much. **Decided (demo-real):** the real run is staged, each stage gated by the user's "go":
  - `--stage core` (cap $20, `LLM_MAX_USD=20`): graph build, run A of 1, 2, 3, L frozen, graph export, graph QA,
    governance, page, screenshots. No reruns, no run B.
  - `--stage extras` (cap $10, `LLM_MAX_USD=10`): (a) 2 reruns of approach 1; (b) 1 rerun of approach 3
    (taxonomy-v3.0, cache off); (c) audit run B as a **model swap**: approach 3 on Sonnet 5.5, prompt v3.0. Over the
    cap, (b) is dropped first, then (c). Approach 2 is not rerun (a rebuild costs about $9.6); screen 6 says so.

## demo-real: status (25 Oct 2026, third session)
- Brief: the real-data demo, staged spend with gates. **Gate 1 (core) and Gate 2 (extras) are done; next is the
  Final stage** (offline `make demo`, fallbacks, REHEARSAL beats, timings). Nothing is pushed: don't push until
  the user says "push".
- Key: verified by the user (YV, 650 cells), cherry-picked from `ground-truth-key` (`f0a0027`); run A re-scored in
  replay ($0). Leaf F1: RAG 0.03, GraphRAG 0.06, taxonomy 0.74, long context 0.15. The page now builds without
  `--draft` (the extras gave screen 7 its rerun Jaccard); screenshots are from the non-draft page.
- Stage 0: `real_run.py --stage core|extras`, spend ledger (`LLM_SPEND_LEDGER`, so `LLM_MAX_USD` holds across
  steps), bridge ranking in code (`graph_qa.rank_bridge`), `driver_dups.py` (alias *proposals* only), page fixes.
- Core run, measured (`results/demo_run/spend.json`, ledger `results/spend/real_run_core.jsonl`): **$8.76 of the
  $20 cap** (estimate $13.94). Graph build $3.94, run A $3.62, graph QA $0.02, then three fixes: GM/F
  re-classified $0.75, approach-2 ask again $0.43, graph QA again $0.01.
- Fixed during the core run:
  - GM and F fell back to fixed windows without `[RF n]` markers; the v3 prompt returned almost nothing (GM 5
    claims, F 0). They now use the paragraph split (`corpus.split_paragraphs`).
  - `test_graphrag_build_ask_and_export` resets the local Neo4j, so a test run with Neo4j up wiped the demo graph.
    It now needs `NEO4J_TEST=1`. The graph was rebuilt from the cache (`LLM_CACHE=replay ... build --reset`, $0),
    identical: 704 mentions, 360 risk factors.
  - The approach-2 ask and graph-QA prompts depended on Neo4j's storage order, so a rebuild changed their cache
    keys. Evidence is now sorted on every field; graph QA replays identically.
- Run A: L 36/36 claims, 10/10 companies; RAG 13/13, retrieved 8/10 (F and TXN never retrieved), 5/10 in the
  answer; GraphRAG 19/19, 9/10; taxonomy 410/431 (1 quote, 20 labels rejected), 10/10, 60 shared leaves.
- `driver_dups.py` on the full graph proposes some wrong aliases (North/South America, Northern Africa/Northern
  California, Department of War/Commerce, Robotaxi/robotics). Review by hand; don't paste the YAML as is.
- Extras (Gate 2): estimate $8.44 re-measured (nothing dropped); **measured $4.57 of the $10 cap** (ledger
  `results/spend/real_run_extras.jsonl`): (a) RAG reruns $0.20, (b) taxonomy rerun $2.92, (c) run B on Sonnet
  $1.45. `claude-sonnet-5-5` confirmed in the API's models list first.
  - Rerun Jaccard (leaf): RAG 1.00 over 3 runs (it is consistently narrow: same 1% recall each time), taxonomy
    0.96 over 2 runs. GraphRAG not rerun (a rebuild ~$9.35); screen 6 says so.
  - Run B (`results/demo_run/audit/run_b/`, served Sonnet only): 406/413 verified vs run A 410/431; 57 shared
    leaves vs 60; OTHER 7.9% vs 7.8%; 10/10 companies both; leaf F1 0.75 vs 0.74.
- Never install `fake_llm` outside the tests' `offline` fixture or `make_fixture`: it writes fake replies into the
  real `cache/chat/`.

## Next tasks, in order
1. Done this session: A/B, screen 4 ask-the-graph, screen 5 (and 2) overflow. Items 2–3 below are kept for
   reference.
2. **Screen 4 as "ask the graph"** (the user wants it; the plan was drafted but not yet approved in detail):
   - Predefined question chips.
   - Each question runs a fixed, parameterised, read-only Cypher template; the LLM writes the answer from the
     returned rows; claims go through the shared verifier.
   - **The graph shown is exactly the subgraph the query returned** (the user wants to keep a graph, as the
     answer).
   - Clicking a node opens the existing drawer (quote in context + full filing). No extra chunk view is needed.
   - Show the Cypher used. Optionally, one recorded Text2Cypher contrast (LLM-written Cypher displayed, never run
     on stage), as in the workshop (notebook 03 uses VectorCypherRetriever and Text2CypherRetriever; notebook 04
     an agent with a Cypher tool).
   - Keep the full overview behind a key.
   - Draft questions:
     - GM + NXPI;
     - TSLA, ON and TXN;
     - F, BWA, LEA, MCHP and ON;
     - the biggest shared risk across all ten vs the biggest *specific* bottleneck;
     - which named place, input or policy links autos to chips.
   - Precompute answers in the real run (`results/demo_run/graph_qa.json`) and replay offline. About 5–6 extra
     calls, under $1.
3. Pre-existing bug: **screen 5 overflows by 178 px with 10 companies** at every size. Fix it (approach 3's
   screen; outside the GraphRAG change).
4. The real run (now includes graph QA), after the user decides on model and budget: `make estimate`, then `make real-run ARGS="--confirm-usd N"`.
5. The user labels the key (`make label`); then the timed dry run (`docs/REHEARSAL.md`) and the recording.

## Working notes
- The stop hook asks to push every commit. The user's GraphRAG spec said no push, so explain this instead of
  pushing.
- Make small commits. End commit messages with the Co-Authored-By and Claude-Session lines. No model ids in
  commits or docs.
- Fixture for page work at $0:
  `python -m tests.make_fixture <dir> edgar_latest` (with `NEO4J_PASSWORD` set, it also runs approach 2), then
  `python src/build_demo.py --run <dir> --fixture`, then `python demo/screenshots.py --out <dir>/shots`.
