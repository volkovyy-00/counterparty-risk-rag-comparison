# Rehearsal script – 9:00 live demo

Start with `make demo`, or `make demo-live` if the Wi-Fi is good. Press **T** at 0:00 to start the timer overlay, and
**Shift+T** to restart it. Each line below gives the start time, the key, what to say, where to point, and the fallback
if anything stalls. Numbers in [brackets] are read off the screen. Fill them in after the frozen run and say them as
shown.

| Beat | Start | Key | Say (≈ one breath per line) | Point at | If it stalls |
|---|---|---|---|---|---|
| 1 | 0:00 | `1`, then `T` | "One question, ten counterparties: six in autos, four in chips. Their latest 10-K, Item 1A only." "Before any model ran, I committed the scoring rule – here is its time and hash, before the results." | The question, the tiles, the commit time vs the run time | Screenshot `01_question.png` |
| 2 | 0:45 | `2` | "First gate: the data. [N] warnings on the EDGAR set – different fiscal years, one March year-end, corporate actions to check." "Same gate on the public workshop sample: Apple's 10-K filed under INTC, and a different company's 10-K under AAPL. Caught before any answer." | Right panel: `ticker_mismatch`, `document_identity` | `02_data_quality.png` |
| 3 | 1:30 | `3` (`R` if live) | "Approach 1, plain RAG: embed the question and take the top 12 chunks." "Retrieved from [k] of 10 companies – this strip – and [m] of 10 are in the answer. A company that is never retrieved cannot be linked to anyone." "Every claim carries a quote. Click one – it is located in that company's own 10-K." | Coverage strip, then one claim row → panel | Live badge falls back to CACHED at 20 s by itself. Otherwise `03_plain_rag.png` |
| 4 | 3:00 | `4` (lands on *Most shared vs most specific*), `→`, click a node, `←` `←` if ahead | **0:00–0:35** "Approach 2, GraphRAG: the risks are a graph in Neo4j, and I ask it fixed questions. Each one is a read-only Cypher query – here it is." "Most shared across all ten: [label], [x] of 10. True, and it says nothing. Most shared *specific* risk across autos and chips: [label]." **0:35–1:10** `→` "What links autos to chips? A named place, input or policy that both sides cite: [driver] – [autos] ↔ [semis]." (If the screen says *No bridge found*: "The graph returned nothing, and it will not invent a link." If it says *Only generic links*: "Everything both sides name is the home country or near-universal – the graph says so instead of calling it a finding.") **1:10–1:25** click a node: "Every edge carries the sentence from the filing." **1:25–1:30** only if ahead: `←` `←` *GM + NXPI*, one line. | The two labelled nodes; the Cypher box; the diamond(s) | `04_graph_qa.png`, `04q3_bridge.png`, `04q5_quotes.png` |
| 5 | 4:30 | `5`, `L`, click a cell | "Approach 3, taxonomy-first: the model does one narrow job – label each risk factor with a fixed id and copy a quote. Counting is code." "At category level almost everything is hot (grey rows are generic)." "Leaf level (L): this is where autos and chips connect – [leaf]: [autos] ↔ [semis]." "Click a cell: every quote, highlighted in the filing, with a link to EDGAR at that sentence." | Generic rows; the "Where autos and semis connect" box; the quote panel | `05_taxonomy_category.png`, `05b_taxonomy_leaf.png`, `05c_taxonomy_quote_panel.png` |
| 6 | 6:30 | `6` | "Same rule, same verifier, same hand-labelled key." "Leaf F1: [a1] / [a2] / [a3]. Quote coverage: [q1] / [q2] / [q3]. Reruns agree at [j1] / [j2] / [j3]." "Cost sits in different places: RAG pays per question, the other two pay once to build." | F1 row, coverage row, the build vs ask rows | `06_scorecard.png` |
| 7 | 8:15 | `7` | "When I would use each – one line each." "For a risk committee I would take [choice], because [the two numbers]." "What did not go to plan: [one line]." | The recommendation box | `07_decision.png` |
| end | 9:00 | – | Hand over to the governance section (`G`). | | |

Screen 4 in Q&A: **M** shows the two parked questions (*TSLA + ON + TXN*, *F, BWA, LEA, MCHP, ON*); **O** opens the
whole graph (then **H** hides generic nodes, **X** shows named drivers). There is no free-text box by design: a fixed
question with its Cypher on screen is the governance point.

Governance section (after the demo, up to 3:00): **G**, then **F** (a planted paraphrase is rejected and the closest
real sentence is shown), **O** (`SUPPLY_GEOPOLITICS` is rejected by the code validator), **A** (manifest diff between
run A and run B – approach 3 after a model swap – plus the heatmap cells that changed). These are offline and deterministic. If the server is not
running, the page shows the precomputed result and says so. Screenshots: `G1_…`, `G2_…`, `G3_…`.

## Timing check

- Do a full dry run with the timer overlay (**T**). The overlay shows the current beat, its window and
  "on plan / behind / ahead". The target is 9:00 ± 0:15.
- If beat 3 runs long, skip the live call and stay on CACHED. The badge is part of the story either way.
- The total speaking budget is about 130–140 words a minute. Each row above is sized for its window, so trim words
  rather than skipping a screen.

## Fallbacks, in order

1. **No Wi-Fi.** Use `make demo`. Everything is served from `results/demo_run/`, and nothing calls an API.
2. **No Neo4j.** Nothing changes. The graph comes from `results/demo_run/graph.json`, and the screen-4 answers from
   `results/demo_run/graph_qa.json`; nothing is typed on stage, so nothing needs a live query.
3. **Browser trouble.** Open `demo/index.html` directly as a file. Everything works except the live step, and
   governance uses its precomputed copy.
4. **Laptop trouble.** Use the PNGs in `demo/fallback/` (`make screenshots`), or the recording below.

## Recording

Record one full rehearsal as the last-resort fallback. Keep the MP4 out of git (it is in `.gitignore`); its expected
path is `demo/fallback/demo_run.mp4`.

- **macOS:** QuickTime → File → New Screen Recording, or ⌘⇧5. Choose the browser window in full screen.
- **Windows:** Xbox Game Bar (Win+Alt+R), or OBS Studio.
- **Linux:** OBS Studio, or
  `ffmpeg -f x11grab -video_size 1920x1080 -i :0.0 -r 30 demo/fallback/demo_run.mp4`.

Run the browser in full screen at 1920×1080 with the timer overlay off, and press the keys from the table above.
