# Data quality - SEC EDGAR latest 10-K

Fetched 2026-10-25 10:22 for tickers: GM, F, TSLA, APTV, BWA, LEA, NXPI, MCHP, ON, TXN. 10 filings kept.

**0 errors, 2 warnings, 8 notes.** Nothing below was corrected automatically.

| Severity | Check | Subject | Detail |
|---|---|---|---|
| WARN | amended_after | TSLA | 10-K/A 0001104659-26-053166 filed 2026-04-30 after the 10-K used |
| WARN | mixed_years | all | fiscal periods end in different calendar years: 2025: GM, F, TSLA, APTV, BWA, LEA, NXPI, ON, TXN; 2026: MCHP |
| INFO | corporate_action_mentioned | APTV | Item 1A mentions: "29 Table of Contents Planned Spin-off of Electrical Distribution Systems Business We are pursuing a plan to separate our Electrical Distributions Systems business into an independent, publicly traded company." |
| INFO | corporate_action_mentioned | BWA | Item 1A mentions: "Risks related to the spin-off of PHINIA Inc." |
| INFO | fiscal_year_ends | all | different fiscal year ends (MMDD): 0331: MCHP; 1231: GM, F, TSLA, APTV, BWA, LEA, NXPI, ON, TXN |
| INFO | group_note | APTV | Aptiv has announced a separation of its Electrical Distribution Systems business; check whether the 10-K used describes the company before or after it. |
| INFO | group_note | BWA | BorgWarner spun off PHINIA Inc. in 2023; check that comparisons with older filings use the post-spin company. |
| INFO | group_note | MCHP | Microchip's fiscal year ends in March; its latest 10-K covers a different period from the calendar-year filers. |
| INFO | group_note | NXPI | NXP Semiconductors N.V. is a Dutch company that files a 10-K with the SEC; check the fiscal period against the others. |
| INFO | non_calendar_fiscal_year | MCHP | fiscal year ends 03/31 (MM/DD); period 2026-03-31 |
