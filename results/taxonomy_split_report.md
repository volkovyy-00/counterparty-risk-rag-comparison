# Approach 3: risk-factor split per filing

Corpus `edgar_latest`, window 12,000 characters. Rules: `corpus.split_risk_factors` (plain line rules, no model call). A heading is a line of 6-60 words ending in a period and followed by a longer line; a sub-caption is a short line naming risks ("Risks Related to ..."). A filing falls back to the fixed windows if it has fewer than 8 headings or a section over 3x the window.

**8 of 10 filings split by heading.** Windows sent to the model: 85 with this split vs 83 with the old fixed windows.

| Ticker | Item 1A chars | Headings | Windows | Fixed windows | Largest section | Method | Fallback reason | First 3 headings |
|---|---|---|---|---|---|---|---|---|
| GM | 67,316 | 1 | 6 | 6 | 21,054 | **fixed** | 1 heading line(s) found, fewer than 8: headings likely run into the paragraph | - |
| F | 93,665 | 3 | 9 | 9 | 41,317 | **fixed** | 3 heading line(s) found, fewer than 8: headings likely run into the paragraph | - |
| TSLA | 83,766 | 40 | 9 | 8 | 4,678 | **heading** |  | We may experience issues or delays in developing, launching and ramping the production of <br>Our suppliers may fail to deliver components according to schedules, prices, quality and v<br>We may be unable to meet our projected construction timelines, costs and production ramps  |
| APTV | 93,048 | 47 | 11 | 12 | 5,171 | **heading** |  | Disruptions in the supply of raw materials and other supplies that we and our customers us<br>We and our customers use a broad range of materials and supplies, including copper and oth<br>When we fail to make timely deliveries in accordance with our contractual obligations, we  |
| BWA | 58,256 | 41 | 6 | 6 | 4,507 | **heading** |  | Our portfolio strategy may prove unsuccessful.<br>We may not prove successful in our strategy due to many factors, including any of the risk<br>Goodwill and indefinite-lived intangible assets, which are subject to periodic impairment  |
| LEA | 54,380 | 30 | 6 | 6 | 8,337 | **heading** |  | Our industry is cyclical and a decline or significant fluctuation in the production levels<br>Increases in the costs and restrictions on the availability of raw materials, energy, comm<br>Our failure to execute our strategic objectives could adversely affect our financial perfo |
| NXPI | 78,414 | 45 | 8 | 7 | 4,124 | **heading** |  | The semiconductor industry is highly cyclical.<br>Significantly increased volatility and instability and unfavorable economic conditions may<br>The semiconductor industry is highly competitive. If we fail to introduce new technologies |
| MCHP | 159,643 | 52 | 18 | 15 | 9,548 | **heading** |  | Our operating results are impacted by global economic conditions and may fluctuate in the <br>Our operating results may be adversely impacted by the inability of our key suppliers to p<br>We may lose sales if critical materials from concentrated sources become restricted or sub |
| ON | 86,958 | 40 | 9 | 11 | 5,534 | **heading** |  | The manufacturing and other operations required to produce our products are highly depende<br>We may be unable to implement certain business strategies and restructuring initiatives an<br>If we are unable to identify and make the substantial research and development investments |
| TXN | 27,418 | 18 | 3 | 3 | 3,570 | **heading** |  | Our global operations subject us to risks associated with domestic or international politi<br>We face substantial competition that requires us to respond rapidly to product development<br>Changes in expected demand for our products could have a material adverse effect on our re |

Why GM, F fall back: these 10-Ks set each heading in bold at the start of its first paragraph. The text extraction keeps the words but not the bold, so heading and body share one line and no rule can tell where the heading ends without guessing. They keep the fixed windows, which is what v2 used for every filing.
