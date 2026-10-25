# Approach 3 A/B: v2.0 fixed windows vs v3.0 heading windows

Filings NXPI, LEA. A = taxonomy-v2.0 / fixed, B = taxonomy-v3.0 / heading. Model claude-opus-5-5. Live spend: A $0.54, B $0.61.

**Read the bold rows first.** Duplicate-label rate = share of accepted claims that repeat a leaf already given to the same risk factor (the factor is the heading section that holds the quote, the same yardstick for both arms). Fewer claims at the same or a better quote pass rate is a win: v3 asks for one label per risk factor, so it should return fewer.

| Metric | NXPI A | NXPI B | LEA A | LEA B |
|---|---|---|---|---|
| Claims returned | 54 | 47 | 45 | 34 |
| Accepted | 54 | 46 | 45 | 30 |
| **Quote pass rate** | 100.0% | 100.0% | 100.0% | 96.8% |
| **Duplicate-label rate** | 3.7% | 0.0% | 11.1% | 0.0% |
| Labels per risk factor | 1.32 | 1.05 | 1.5 | 1.03 |
| Risk factors labelled | 41 | 44 | 30 | 29 |
| Rejected by label rules | 0 | 1 | 0 | 3 |
| OTHER rate | 11.1% | 13.0% | 2.2% | 3.3% |
| OTHER drivers | (none) | Dutch corporate law, Dutch incorporation, goodwill impairment, quarterly cash dividend, stock price volatility, stock repurchases | (none) | goodwill impairment |

## Five risk factors side by side

| Ticker | RF | Heading | A (v2.0) | B (v3.0, driver) |
|---|---|---|---|---|
| NXPI | 1 | The semiconductor industry is highly cyclical. | MACRO_DEMAND.cyclical_demand (1 claims) | MACRO_DEMAND.cyclical_demand (semiconductor industry cycles) (1 claims) |
| NXPI | 2 | Significantly increased volatility and instability and unfavorable economic cond | MACRO_DEMAND.cyclical_demand (1 claims) | MACRO_DEMAND.cyclical_demand (1 claims) |
| NXPI | 3 | The semiconductor industry is highly competitive. If we fail to introduce new te | AI_EMERGING_TECH.ai_development_use<br>COMPETITION_DISRUPTION.technology_change (2 claims) | COMPETITION_DISRUPTION.price_competition<br>COMPETITION_DISRUPTION.technology_change (2 claims) |
| LEA | 1 | Our industry is cyclical and a decline or significant fluctuation in the product | CUSTOMER_CONCENTRATION.auto_oem_customers<br>MACRO_DEMAND.vehicle_production_volumes (2 claims) | MACRO_DEMAND.vehicle_production_volumes (OEM production levels) (1 claims) |
| LEA | 2 | Increases in the costs and restrictions on the availability of raw materials, en | COMMODITY_INPUTS.raw_material_prices (1 claims) | COMMODITY_INPUTS.raw_material_prices (1 claims) |
