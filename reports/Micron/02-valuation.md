---
title: Micron valuation, Buffett view, 2026-10-20
date: 2026-10-20
type: 研究
---

# Micron valuation, Buffett view, 2026-10-20

Data cutoff is 2026-10-20. Source file `evidence/us-snapshot-MU.json`. Not investment advice.

## Price

The price used for market cap is the Yahoo chart official close, 904.9 USD at 2026-10-19T20:00:00+00:00.

Yahoo daily bars are also official closes. The price is that bar's session close. The timestamp is Yahoo's bar stamp, the New York regular-session start, not the closing auction. `analyze` marks those lines `clock=bar_stamp`.

- 2026-10-13T13:30:00+00:00 is 953.19 USD
- 2026-10-14T13:30:00+00:00 is 914.13 USD
- 2026-10-15T13:30:00+00:00 is 931.24 USD
- 2026-10-16T13:30:00+00:00 is 878.84 USD
- 2026-10-19T13:30:00+00:00 is 904.90 USD

Nasdaq info returned HTTP 200 and the failure detail `undated last sale`. The stamp had a date and no clock, so it is not a timed print. The chart meta high is 1255.0 and the low is 192.4. Nasdaq stores `$1255/$192.4`.

## Shares and market cap

The share fact is `EntityCommonStockSharesOutstanding`, count 1131423212, as of 2026-10-02. The snapshot does not name which form carried that instant fact. The latest `10-K` was filed 2026-10-09. Fiscal year 2026 ends 2026-09-03.

`analyze` prints `market_cap: usd=1023824864538.8` from price 904.9 times those shares, source `yahoo_chart`. That product was not passed back to `verify-market-cap --reported`. Doing so would check the product against itself. US shares were not passed to `three-scenario`.

The Nasdaq Market Cap lexeme is `1,023,824,864,539`. That is the same product rounded to a dollar. The cell still has no scale field, so it is not used as an independent dollar cap.

## GAAP and the hurdle

`through_cycle` keeps the latest ten fiscal years, 2017 through 2026. It prints median 6087000000, peak 84969000000, trough -5833000000. The peak row is fiscal year 2026, end 2026-09-03, ones 84969000000, filed 2026-10-09. The trough inside that window is fiscal year 2023, end 2023-08-31, ones -5833000000.

The hurdle is the later yield. Treasury par is 0.0515 on 2026-10-19. FRED DGS10 is 0.0509 on 2026-10-16. `analyze` uses 0.0515. The earnings yield on the ten-year median is 0.005945352775488605368121573015. The check prints `clears=no`.

Stock-based compensation for fiscal year 2026 is 1333000000. The ratio to absolute GAAP net income is 0.01568807447422000965057844626. GAAP net income already deducts that cost. It is not added back.

Buybacks for fiscal year 2026, tag `PaymentsForRepurchaseOfCommonStock`, are 650000000.

Judgment: this note has no intrinsic-value estimate beyond the ten-year check, and that check does not clear the Treasury hurdle. The counterpoint is the peak. A reader who puts 84969000000 over the same market cap is using the latest year, not the median the tool uses. Both numbers are in the file. Neither is a target price.

No star score.

> "Price is what you pay, value is what you get." Warren Buffett. The price and the GAAP rows are in the snapshot. A target price is not.
