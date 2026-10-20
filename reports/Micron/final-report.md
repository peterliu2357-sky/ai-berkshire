---
title: Micron team note, 2026-10-20
date: 2026-10-20
type: 研究
---

# Micron team note, 2026-10-20

Data cutoff is 2026-10-20. Evidence is `evidence/us-snapshot-MU.json`. Not investment advice. Star scores are withheld. DRAM prices, NAND prices, segment mix, and peer filings are not in the file. The failures list is empty, so the withheld scores are not a failed SEC fetch.

Information grade is A, as stated in `README.md`. AI confidence in the figures below is high where the figure is an `analyze` line or a snapshot field. Investment certainty is low. A long filing record is not the same thing as a known franchise.

## Facts used for the decision

Key dollar rows, each one a GAAP `ones` value or an `analyze` line. Nasdaq lexemes are not in this table.

| Figure | Amount |
| --- | --- |
| Median net income | 6087000000 |
| Peak net income | 84969000000 |
| Trough net income | -5833000000 |
| Fiscal 2026 revenue | 133188000000 |
| Fiscal 2023 revenue | 15540000000 |
| Fiscal 2026 operating cash | 89675000000 |
| Fiscal 2026 capex | 30712000000 |
| Official close | 904.90 |
| Share count | 1131423212 |
| Market cap | 1023824864538.80 |

Nasdaq calls the issuer Micron Technology, Inc. Common Stock, exchange NASDAQ-GS, industry Semiconductors.

The official close used for market cap is 904.90 USD, kind official_close, source `yahoo_daily_close`, as of 2026-10-19T13:30:00+00:00. That clock is the bar stamp, not the closing auction. Shares are 1131423212 as of 2026-10-02, tag `EntityCommonStockSharesOutstanding`. Market cap is 1023824864538.80 USD. The Nasdaq Market Cap lexeme `1,036,180,006,014` is unscaled and was not used as the cap.

GAAP net income uses fiscal years 2017 through 2026. Gaps are none. The median is 6087000000, the peak is 84969000000, and the trough is -5833000000. The peak is fiscal year 2026, end 2026-09-03, filed 2026-10-09. Revenue for that year is 133188000000. Fiscal year 2023 revenue is 15540000000 and fiscal year 2023 net income is -5833000000.

Treasury par yield is 0.0515 on 2026-10-19. FRED DGS10 is 0.0509 on 2026-10-16. The hurdle check uses 0.0515 and the median, and prints earnings yield 0.005945352775488605368121573015, `clears=no`.

Fiscal year 2026 stock-based compensation is 1333000000. GAAP net income already deducts it. Inventory days print as 149.4175362093131910917302601 over 370 days. The capex ratio prints as 3.231821530043144270230453541. Buybacks are 650000000. Fiscal year 2025 buybacks are 0.

Intraday lasts on 2026-10-20 are 915.766 USD at 2026-10-20T14:52:03+00:00, source `yahoo_chart`, and 915.7657 USD, source `nasdaq_info`, as of `2026-10-20T10:52:00-04:00`. They are not official closes. Mixed-session pairs have no return. The fifty-two-week high is 1255.0 and the low is 192.4.

## Six dimensions

The valuation cell is not the whole decision. A failed Treasury hurdle tightens what a buyer should do. It does not, alone, rewrite a business conclusion the file does not contain.

| Dimension | Result | Confidence |
| --- | --- | --- |
| Business, Duan view | The accounts swing from trough net income -5833000000 to peak 84969000000. Why the customer pays is not in the file. | Low. Mix is missing. |
| Moat, Buffett view | The five moat tests are unverified. Capex ratio 3.231821530043144270230453541 is reinvestment, not a proven cost gap. | Low. |
| Managers | `Form 4` rows exist, including RAY MICHAEL CHARLES and MEHROTRA SANJAY. The proxy filed 2025-11-25 was not read. No holding percent. | Low. |
| Main risk, Munger view | Using peak GAAP net income 84969000000 as the run rate, while the median check prints `clears=no`. | The two dollar figures are in the file. The probability is not. |
| Civilizational place, Li Lu view | Unavailable. No industry structure and no bit price. | Not scored. |
| Valuation | Three-year price band: unavailable, because US shares were not passed to `three-scenario`. Ten-year pressure test that this path does run: earnings yield 0.005945352775488605368121573015 versus Treasury 0.0515, `clears=no`. The IRR flip tool was not run. | High on the printed check. No price band. |

## Valuation reconciliation

There is no priced three-year band to set against the hurdle. `three-scenario` was not run. The ten-year IRR model was not run, so it is not used as a veto and it is not used as a pass. The conflict a reader may feel is between the peak year and the median. The tool keeps both. The check uses the median and prints `clears=no`. A yield on the peak was not calculated and is not a number in this note.

If the peak were treated as the bull case, that would be a different earnings base from the one `through_cycle` uses. This note does not do that. The final line below does not rest on an unrun IRR.

## Decision

Judgment, not a fact: the file does not support a buy at the official close of 904.90 USD. The reasons that are facts are the hurdle result, the identification of fiscal year 2026 as the peak, and the absence of a product split. The reason that is a judgment is that those facts together are enough to refuse a new purchase when a valuation price band cannot be produced without breaking the US share rule.

| Stance | What this file supports |
| --- | --- |
| Empty account | Do not buy at 904.90 USD, the official close used for the cap. No buy band is in the file. |
| Existing holder | No sell price is in the file. Do not treat peak net income 84969000000 as the run rate. The median check prints `clears=no`. |
| What would count as a sell signal | A price is not in the file. Anchoring on 1255.0 or 192.4 is a chart fact, not a signal this note adopts. |
| What would count as an add | A later snapshot in which `analyze` prints `clears=yes` on the through-cycle median. This file prints `clears=no`. |

The price range the research skill asks for is unavailable. Inventing one would put numbers into the note that are not in the snapshot. The prices that are in the file are the official closes, the two intraday lasts, and the high 1255.0 and low 192.4.

## What was not done, and why

- A web sweep for TAM, bit prices, share of shipments, and manager biographies was not used as a fact source. `skills/us-market.md` and `skills/memory-cycle.md` allow a number in this note only when the snapshot or an `analyze` line has it. DRAM and NAND prices are not fields.
- `three-scenario` was not run. The US path says not to pass this share count into that command.
- `verify-market-cap --reported` was not run. The path says not to pass the official-close product back in, and not to fill the reported cap from the Nasdaq lexeme.
- `verify-valuation` was not run. Per-share earnings, book value, and dividend are not fields.
- `terminal_value.py` audit, exit PE, IRR, and flip were not run. The inputs are judgments, and the outputs are not snapshot fields. They are not a hidden veto.
- Peer quotes for NVDA, AMD, TSMC, and a Korean listing were not written into this file. A separate snapshot would be required, and those numbers must not be pasted into the Micron snapshot.
- `8-K` and proxy bodies were not read. The snapshot stores the filing URL, not the item text. Hyperscaler and export-control sentences would need that text.

`cross-validate` was run on Treasury par 0.0515 and FRED 0.0509. The tool reported the pair inside its default tolerance. The deviation percent it printed is not a snapshot field and is omitted.

## Confidence versus certainty

Figures taken straight from the snapshot or from `analyze` are the high-confidence layer: the official close, the share count, the market cap, the GAAP rows cited above, the hurdle line, inventory days, the capex ratio, stock-based compensation, and the two Form 4 rows. Conclusions that are judgments are marked as judgments: refusing a new buy, reading the swing as a cycle the file cannot separate from a mix shift, and withholding moat and manager scores.

The grade A label is about how much public history exists, not about how certain the business is. The business certainty is limited by the missing mix, the missing bit price, and the missing peers.

Detail sits in `01-business-model.md`, `02-valuation.md`, `03-competition.md`, and `04-risk-and-management.md`.
