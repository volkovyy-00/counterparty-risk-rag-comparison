# What industry risks connect these counterparties, and which counterparties share each one?

Group `auto_semis` - 10 filings - model `claude-opus-5-5` - run 2026-10-25T19:48:20Z - key: **verified**

| Metric | 0_long_context | 1_plain_rag | 2_graphrag | 3_taxonomy_first |
|---|---|---|---|---|
| P / R / F1 category | 1.00 / 0.20 / 0.33 | 1.00 / 0.06 / 0.12 | 1.00 / 0.10 / 0.18 | 0.98 / 0.91 / 0.94 |
| P / R / F1 leaf | 1.00 / 0.08 / 0.15 | 1.00 / 0.01 / 0.03 | 0.93 / 0.03 / 0.06 | 0.92 / 0.62 / 0.74 |
| Quote coverage | 100% | 100% | 100% | 95% |
| Quotes rejected | 0 | 0 | 0 | 1 |
| Labels rejected (off-taxonomy) | 0 | 0 | 0 | 20 |
| Rerun consistency (Jaccard, leaf) | - | 1.00 | - | 0.96 |
| Companies covered | 10 of 10 | 5 of 10 | 9 of 10 | 10 of 10 |
| Build: tokens / cost / time | no model calls | 0 tok / $0.00 / replayed | 1,024,482 tok / $4.88 / replayed | 933,311 tok / $3.04 / replayed |
| Ask: tokens / cost / time | 239,737 tok / $1.05 / replayed | 13,693 tok / $0.09 / replayed | 95,418 tok / $0.43 / replayed | no model calls |

Scoring rule: SCORING_RULE.md. Costs: pricing.yaml, checked 2026-10-06.
