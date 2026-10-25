# Taxonomy coverage of the group's drivers

Taxonomy v2 (sha256 `b2b58f5a5f99`), corpus `edgar_latest`. Each Item 1A sentence that names a driver term is mapped onto a leaf by the taxonomy's keyword rules (`taxonomy.leaves_for`, the verifier's fallback). This is a proxy for where a model would put it, not a measurement. No model call.

**New leaf justified: NO.** Rule: a driver landing in an ill-fitting leaf for 3 or more companies. The existing leaves take every driver; the v3 `driver` note carries the detail.

Near miss: **Taiwan / geographic concentration** lands badly for NXPI, MCHP only (2 < 3). Under taxonomy-v3 these sections keep their closest leaf and the `driver` note names the exposure (e.g. "Taiwan foundry concentration"); review the drivers after the A/B before adding a leaf.

## Taiwan / geographic concentration

Fitting leaves: `SUPPLY_CHAIN.outsourced_manufacturing`, `SUPPLY_CHAIN.single_source`. Companies mentioning it: 2 of 10. Ill-fitting landings: 2 (NXPI, MCHP).

| Ticker | Sentences | Top leaf (share) | Reaches a fitting leaf | Fits | Also | Shortest example |
|---|---|---|---|---|---|---|
| NXPI | 4 | `RATES_FX_FUNDING.fx_exposure` (25%) | 0% | **no** | CLIMATE_NATCAT.natural_disasters_weather 1, GEOPOLITICAL_TRADE.china_exposure 1 | For example, we currently participate in a joint venture with Taiwan Semiconductor Manufacturing Company Limited (“TSMC”) called Systems on Silicon Manufacturing Company Pte. |
| MCHP | 5 | `GEOPOLITICAL_TRADE.china_exposure` (60%) | 40% | **no** | SUPPLY_CHAIN.outsourced_manufacturing 1, REGULATION_LEGAL.government_incentives 1 | During fiscal 2026, approximately 75% of our net sales were made to foreign customers, including 18% in China and 15% in Taiwan. |

## Export controls

Fitting leaves: `GEOPOLITICAL_TRADE.export_controls`. Companies mentioning it: 10 of 10. Ill-fitting landings: 0 (none).

| Ticker | Sentences | Top leaf (share) | Reaches a fitting leaf | Fits | Also | Shortest example |
|---|---|---|---|---|---|---|
| GM | 1 | `GEOPOLITICAL_TRADE.export_controls` (100%) | 100% | yes |  | and foreign countries’ export controls, economic sanctions, import controls, foreign investment, and other similar measures; (12) impacts on our operations or liabilities resulting from U.S. |
| F | 2 | `GEOPOLITICAL_TRADE.tariffs` (50%) | 100% | yes | GEOPOLITICAL_TRADE.export_controls 1 | To the extent governments in various regions implement or intensify restrictions or barriers to trade, such as tariff or non-tariff barriers, export controls, currency manipulation, or policies that otherwise favor domes |
| TSLA | 2 | `GEOPOLITICAL_TRADE.tariffs` (100%) | 100% | yes |  | We cannot predict whether, and to what extent, there may be changes to international trade agreements, such as those with China, or whether, or to what extent, quotas, duties, additional tariffs, export controls or other |
| APTV | 1 | `CUSTOMER_CONCENTRATION.customer_credit` (100%) | 100% | yes |  | and other countries; •tariffs, quotas, customs and other import or export restrictions and other trade barriers; •expropriation and nationalization; •difficulty of enforcing agreements, collecting receivables and protect |
| BWA | 1 | `REGULATION_LEGAL.litigation_investigations` (100%) | 100% | yes |  | 26 Table of Contents Changes that could impact the legal environment include new legislation, new regulations, new policies, investigations and legal proceedings, and new interpretations of existing legal rules and regul |
| LEA | 5 | `GEOPOLITICAL_TRADE.tariffs` (60%) | 100% | yes | GEOPOLITICAL_TRADE.export_controls 1, GEOPOLITICAL_TRADE.conflict_sanctions 1 | •International trade policies, such as tariffs, sanctions, export controls and other trade restrictions, could adversely affect our financial performance. |
| NXPI | 5 | `GEOPOLITICAL_TRADE.export_controls` (40%) | 100% | yes | GEOPOLITICAL_TRADE.conflict_sanctions 1, CLIMATE_NATCAT.pandemic_health 1 | government, we ceased shipments of our products to Huawei pending approval of export licenses. |
| MCHP | 23 | `GEOPOLITICAL_TRADE.export_controls` (57%) | 96% | yes | REGULATION_LEGAL.litigation_investigations 2, OTHER.reporting_controls 1 | export controls may encourage our non-U.S. |
| ON | 5 | `GEOPOLITICAL_TRADE.export_controls` (60%) | 100% | yes | GEOPOLITICAL_TRADE.tariffs 2 | Additional tariffs, export controls or other trade restrictions between the two countries could materially adversely affect our results of operations. |
| TXN | 3 | `GEOPOLITICAL_TRADE.tariffs` (33%) | 100% | yes | CUSTOMER_CONCENTRATION.distributor_channel 1, GEOPOLITICAL_TRADE.export_controls 1 | Governments have adopted or proposed measures, including export controls on certain minerals, materials and equipment, that could adversely affect equipment and material availability, cost or movement. |

## Critical minerals

Fitting leaves: `COMMODITY_INPUTS.critical_minerals`, `EMISSIONS_EV_TRANSITION.battery_supply_cost`. Companies mentioning it: 6 of 10. Ill-fitting landings: 0 (none).

| Ticker | Sentences | Top leaf (share) | Reaches a fitting leaf | Fits | Also | Shortest example |
|---|---|---|---|---|---|---|
| GM | 2 | `COMMODITY_INPUTS.raw_material_prices` (50%) | 100% | yes | COMMODITY_INPUTS.critical_minerals 1 | In addition, elevated cost, or reduced availability, of critical materials for our EV propulsion systems, including lithium, nickel, cobalt, and certain rare earth metals, may lead to higher production costs for our EVs  |
| F | 5 | `COMMODITY_INPUTS.critical_minerals` (40%) | 100% | yes | GEOPOLITICAL_TRADE.china_exposure 1, CUSTOMER_CONCENTRATION.auto_oem_customers 1 | Our ability to manufacture electrified products is dependent upon the availability of raw materials and other components necessary for the production of batteries, e.g., lithium, cobalt, nickel. |
| TSLA | 9 | `EMISSIONS_EV_TRANSITION.battery_supply_cost` (56%) | 100% | yes | COMMODITY_INPUTS.critical_minerals 2, EMISSIONS_EV_TRANSITION.ev_adoption_pace 1 | In addition, the battery packs that we produce make use of lithium-ion cells. |
| BWA | 1 | `COMMODITY_INPUTS.raw_material_prices` (100%) | 100% | yes |  | We use a variety of commodities (including aluminum, copper, nickel, plastic resins, steel, other raw materials and energy) and materials purchased in various forms such as castings, powder metal, forgings, stampings and |
| NXPI | 1 | `COMMODITY_INPUTS.raw_material_prices` (100%) | 100% | yes |  | Similar investigations on other industries or products, including automotive, copper, steel, aluminum, critical minerals and aircraft, may also adversely impact the semiconductor industry and our business. |
| MCHP | 8 | `GEOPOLITICAL_TRADE.conflict_sanctions` (25%) | 100% | yes | GEOPOLITICAL_TRADE.export_controls 2, COMMODITY_INPUTS.critical_minerals 1 | China is a predominant producer of many rare earth materials essential to the global electronics industry. |

## EV and chip incentives

Fitting leaves: `REGULATION_LEGAL.government_incentives`. Companies mentioning it: 6 of 10. Ill-fitting landings: 0 (none).

| Ticker | Sentences | Top leaf (share) | Reaches a fitting leaf | Fits | Also | Shortest example |
|---|---|---|---|---|---|---|
| GM | 2 | `SUPPLY_CHAIN.logistics` (50%) | 100% | yes | REGULATION_LEGAL.government_incentives 1 | and other countries in which we do business (for example, the Act and the 21 Table of Contents GENERAL MOTORS COMPANY AND SUBSIDIARIES Inflation Reduction Act (IRA)), the possibility of tax controversy related to adverse |
| F | 4 | `REGULATION_LEGAL.government_incentives` (50%) | 100% | yes | EMISSIONS_EV_TRANSITION.battery_supply_cost 2 | In 2022, Congress established these incentives and many retail and commercial vehicle purchasers were eligible for a tax credit of up to $7,500 per vehicle, increasing market demand for plug-in vehicles. |
| TSLA | 5 | `REGULATION_LEGAL.government_incentives` (80%) | 100% | yes | EMISSIONS_EV_TRANSITION.charging_infrastructure 1 | and abroad, including certain tax exemptions, tax credits and rebates, may be reduced, eliminated, amended or exhausted from time to time. |
| BWA | 1 | `TAX.tax_law_changes` (100%) | 100% | yes |  | Changes in tax laws or tax rates, the resolution of tax assessments or audits by various tax authorities, and the inability to fully utilize our tax loss carryforwards and tax credits could adversely affect our operating |
| NXPI | 2 | `REGULATION_LEGAL.government_incentives` (100%) | 100% | yes |  | Transfer pricing uncertainties can also result from disputes with local tax authorities about transfer pricing of internal deliveries of goods and services or related to financing, acquisitions and divestments, the use o |
| TXN | 1 | `REGULATION_LEGAL.government_incentives` (100%) | 100% | yes |  | A number of factors could cause our tax rate to increase, including changes in the jurisdictions in which our profits are earned and taxed; changes in the mix of profits from those jurisdictions; changes in available tax |
