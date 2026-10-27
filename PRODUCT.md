# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack
Vite front end in `ui/`, separate from the Python pipeline. It talks to `src/serve.py` (stdlib HTTP, thin API). Offline it reads `results/demo_run/` JSON; live it calls `/api/live_rag` and a graph ask on frozen templates. The built UI is committed so the stage laptop needs no Node. (Confirmed by the author, 25 Oct 2026.)

## Users
- **Presenter (primary operator):** the author, on stage at AI for Business 2026, Prague, 4 Nov 2026, driving a 9-minute live demo inside a 45-minute talk, *How AI Rewired the Business Analyst Role*. Clicks and types under time pressure, on a projector, with the audience watching every state change.
- **Audience (primary reader):** business analysts, risk and data people. They read the screen from a distance and must follow which approach answered, what evidence backs it, and whether it was live or replayed. *(Inferred from the talk title.)*

## Product Purpose
One question, answered three ways on public SEC 10-K Item 1A text: *What industry risks connect these counterparties, and which counterparties share each one?* Plain RAG, GraphRAG and taxonomy-first (plus a long-context control) share one output contract, one verifier and one scoring rule. The console lets the presenter ask live and show that every claim traces back to a verbatim quote in the filing. Success: the audience sees the trade-offs on real interaction, and the demo never shows a blank screen.

## Positioning
Not a vendor product. A fair, governed comparison: the scoring rule was committed before any model ran, every claim is verified against the filing text, and the graph is asked only through fixed read-only Cypher templates, so it can't invent a link.

## Operating Context
- Projector, 1920×1080 primary, 1280×720 fallback. Keyboard shortcuts plus clicks.
- Live calls may fail or be slow. On a timeout or error, the frozen `results/demo_run/` answer is shown with a REPLAY badge. LIVE / REPLAY are the only mode badges.
- Neo4j is not needed on stage: the graph comes from `results/demo_run/graph.json`.
- The beat-by-beat script lives in `docs/REHEARSAL.md`.

## Capabilities and Constraints
- Approaches 1 and 2: a real streamed answer to a chip or typed question, with the existing evidence (coverage strip; Cypher + subgraph; click → verbatim quote in Item 1A + EDGAR link).
- Approach 3: keep the heatmap + quote drawer; modernize chrome only. No new taxonomy UI (no leaf-icon dashboards).
- The pipeline is not rewritten into the front end.
- The graph view is our own layout, modernized; NVL only if it is a small, reliable drop-in. No faked Bloom-style graph.
- Live spend cap `LIVE_MAX_USD` = $3 across rehearsals and stage; routing on Haiku 5.5, answers on Opus 5.5.
- Screens: question, data quality, plain RAG, GraphRAG, taxonomy, scorecard, decision (reruns), governance (fabrication / out-of-taxonomy / run A vs B checks).

## Brand Commitments
- Dark product console, not a slide deck. The yellow fixture tape and the keyboard-slide metaphor are retired as the main experience. (Author, 25 Oct 2026.)
- Views are the author's own. No vendor pitch. Nothing from the author's employer: no names, tools, data or numbers.

## Evidence on Hand
- `results/demo_run/`: frozen real run (claims, scorecard, graph.json, graph_qa.json, governance.json, audit run B, reruns, spend).
- `data/corpus/edgar_latest/`: frozen Item 1A text for GM F TSLA APTV BWA LEA NXPI MCHP ON TXN.
- `config/taxonomy.yaml`, `SCORING_RULE.md`, the hand-labelled key in `config/ground_truth`.
- Do not fabricate numbers: every figure on screen is read from the run files.

## Product Principles
1. Every claim is traceable: one click from answer to the sentence in the filing.
2. Honest about mode: LIVE or REPLAY is always visible; a fallback is never hidden.
3. Same contract for every approach, so the comparison reads at a glance.
4. Never a blank screen.
5. The machinery is visible (Cypher, retrieval coverage, verifier rejections), because it is the governance argument.

## Accessibility & Inclusion
Projector legibility: large type for read-from-the-room values, high contrast, and no meaning carried by colour alone (approach and state also labelled in text).
