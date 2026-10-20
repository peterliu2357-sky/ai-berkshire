---
title: Micron business model, Duan view, 2026-10-20
date: 2026-10-20
type: 研究
---

# Micron business model, Duan view, 2026-10-20

Data cutoff is 2026-10-20. Source file `evidence/us-snapshot-MU.json`. Not investment advice.

## What the file can call the business

Nasdaq labels the issuer `Micron Technology, Inc. Common Stock` on `NASDAQ-GS`, sector Technology, industry Semiconductors. Those strings are labels. They do not name a product, a contract, or a price.

One sentence from the accounts: GAAP revenue and GAAP profit swing from a loss year to a peak year inside the latest window, and the file does not say what the customer is paying for. Judgment: that pattern is what a commodity cycle looks like in the accounts, and it is also what a mix shift can look like. The snapshot cannot separate those stories.

The GAAP revenue tag is `RevenueFromContractWithCustomerExcludingAssessedTax`. Dollars, `ones`, by fiscal year and period end:

| Fiscal year | Period end | Revenue ones |
| --- | --- | --- |
| 2017 | 2017-08-31 | 20322000000 |
| 2018 | 2018-08-30 | 30391000000 |
| 2019 | 2019-08-29 | 23406000000 |
| 2020 | 2020-09-03 | 21435000000 |
| 2021 | 2021-09-02 | 27705000000 |
| 2022 | 2022-09-01 | 30758000000 |
| 2023 | 2023-08-31 | 15540000000 |
| 2024 | 2024-08-29 | 25111000000 |
| 2025 | 2025-08-28 | 37378000000 |
| 2026 | 2026-09-03 | 133188000000 |

Fiscal year 2026 revenue is the high end of these rows. Fiscal year 2023 revenue is the low end. The latest `10-K` was filed 2026-10-09. The file does not split the latest year into DRAM, NAND, or HBM. No bit price is in the snapshot.

GAAP net income, tag `NetIncomeLoss`, at the turns already in the revenue table:

| Fiscal year | Period end | Net income ones |
| --- | --- | --- |
| 2017 | 2017-08-31 | 5089000000 |
| 2018 | 2018-08-30 | 14135000000 |
| 2019 | 2019-08-29 | 6313000000 |
| 2020 | 2020-09-03 | 2687000000 |
| 2021 | 2021-09-02 | 5861000000 |
| 2022 | 2022-09-01 | 8687000000 |
| 2023 | 2023-08-31 | -5833000000 |
| 2024 | 2024-08-29 | 778000000 |
| 2025 | 2025-08-28 | 8539000000 |
| 2026 | 2026-09-03 | 84969000000 |

`through_cycle` keeps 2017 through 2026, gaps none, and prints median 6087000000, peak 84969000000, trough -5833000000. The peak is fiscal year 2026. The trough is fiscal year 2023. Peak earnings are not the run rate.

## Margins, cash, and reinvestment

Nasdaq gross margin is one source, parts per hundred, by the vendor period text: 8/31/2023 is -9.11197, 8/31/2024 is 22.35275, 8/28/2025 is 39.79079, and 9/3/2026 is 80.71598. Operating margin on those period ends is -36.96911, then 5.19294, then 26.13837, then 74.5863. These are not EDGAR ratios. A single-source percent is labeled as one source.

GAAP gross profit for the year ended 2026-09-03 is 107504000000. GAAP revenue for that same end is 133188000000. GAAP operating income for that end is 99340000000. This note does not divide those rows. The earlier operating-income rows are 9702000000 for the year ended 2022-09-01, -5745000000 for the year ended 2023-08-31, 1304000000 for the year ended 2024-08-29, and 9770000000 for the year ended 2025-08-28. The path is a swing, not a smooth operating-leverage series.

Cash from operations for fiscal year 2026, tag `NetCashProvidedByUsedInOperatingActivities`, is 89675000000. Capex, tag `PaymentsToAcquirePropertyPlantAndEquipment`, is 30712000000. Depreciation is 9503000000. `analyze` prints capex ratio 3.231821530043144270230453541 for fiscal year 2026. Free cash flow is not a field. The difference of the two cash rows was not computed, because that difference is not a snapshot field.

Nasdaq prints a cash lexeme `$38,364,000` and a long-term debt lexeme `$4,688,000` on period text 9/3/2026, and a research-and-development lexeme `$5,650,000` on the same period text. `analyze` prints `unscaled_note: not dollars`. Those cells are not used as cash, debt, or research dollars. Net cash is unavailable.

Inventory at 2026-09-03 is 10372000000. Cost of goods for the year ended that day is 25684000000, start 2025-08-29. `analyze` prints inventory days 149.4175362093131910917302601 over 370 days.

Buybacks, tag `PaymentsForRepurchaseOfCommonStock`, are 0 for fiscal year 2025 and 650000000 for fiscal year 2026. A dividend fact is not in the annual rows.

## What is not a business description

No customer name, no contract length, and no repurchase reason beyond the GAAP totals. The revenue tag says the dollars come from contracts with customers, excluding assessed tax. It does not say the contract repeats.

Judgment: a durable reason the customer pays is not in this file. The counterpoint is the fiscal year 2026 revenue of 133188000000 and the Nasdaq gross margin of 80.71598. A strong reported year is a fact in the file. It is not, by itself, a franchise.

No star score. Memory prices, segment mix, and peer filings are not in the file. The filing fetch itself is not in the failures list.

Duan question: if the business can be said in one sentence, what is it? The sentence this file supports is the swing from trough net income -5833000000 to peak net income 84969000000, with no product split beside it.

> "买股票就是买公司，所以不懂不碰。" Duan Yongping, reply dated in the archive file `reports/茅台/段永平雪球发言-茅台相关.md`, source URL in that file. The extension used here is the second clause: the snapshot does not show what is being bought, so it does not support a purchase. The line is not a finding that the GAAP totals are false.
