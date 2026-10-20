---
title: Micron team note, 2026-10-20
date: 2026-10-20
type: 研究
---

# Micron team note, 2026-10-20

Data cutoff is 2026-10-20. Evidence is `evidence/us-snapshot-MU.json`. Not investment advice. Star scores are withheld because DRAM prices, NAND prices, and peer filings are not in the file.

## What was fetched

Nasdaq calls the issuer Micron Technology, Inc. Common Stock, exchange NASDAQ-GS, industry Semiconductors. Nasdaq info did not become a timed print. The failure detail is `undated last sale`.

The official close used for market cap is 904.9 USD, source `yahoo_chart`, timestamp 2026-10-19T20:00:00+00:00. The same day's Yahoo daily bar is 904.90 USD at 2026-10-19T13:30:00+00:00. That timestamp is the bar stamp, not the closing auction. Earlier daily closes in the file are 953.19, 914.13, 931.24, and 878.84 USD. Yahoo high is 1255.0 and low is 192.4. Nasdaq stores `$1255/$192.4`.

Shares are 1131423212 as of 2026-10-02, tag `EntityCommonStockSharesOutstanding`. Market cap from that close times those shares is 1023824864538.8 USD. The Nasdaq Market Cap lexeme `1,023,824,864,539` is that product rounded to a dollar. It was not used as a separate reported cap.

GAAP net income, tag `NetIncomeLoss`, uses the latest ten fiscal years by calendar, 2017 through 2026. That window has no missing year. The median is 6087000000, the peak is 84969000000, and the trough is -5833000000. The peak is fiscal year 2026, end 2026-09-03, filed 2026-10-09. Revenue for that year is 133188000000. Fiscal year 2023 revenue is 15540000000 and fiscal year 2023 net income is -5833000000.

Treasury par yield is 0.0515 on 2026-10-19. FRED DGS10 is 0.0509 on 2026-10-16. The hurdle check uses 0.0515 and the ten-year median, and prints earnings yield 0.005945352775488605368121573015, `clears=no`.

Fiscal year 2026 stock-based compensation is 1333000000. GAAP net income already deducts it. Inventory days print as 149.4175362093131910917302601 over 370 days. The capex ratio prints as 3.231821530043144270230453541. Buybacks are 650000000.

`Form 4` documents were fetched without the `xsl` path segment. The insider list is not empty. One row is RAY MICHAEL CHARLES, transaction date 2026-10-14, filing date 2026-10-15, code S, shares 40.00, price 947.29.

Nasdaq gross margin, one source, runs from -9.11197 on 8/31/2023 to 80.71598 on 9/3/2026.

## What was not fetched

No DRAM price and no NAND price. No peer snapshot for Samsung, SK hynix, NVDA, AMD, or TSMC. The proxy was listed and not read.

## Synthesis

The tape in this file is an official close of 904.9 USD and a share count of 1131423212, so the cap is 1023824864538.8 USD. Against that cap, the median GAAP net income of the latest ten calendar fiscal years, 2017 through 2026, does not clear a Treasury yield of 0.0515. The same file's latest GAAP net income is 84969000000, which is the peak, not the median.

Judgment: the file does not support a buy or a sell. The ten-year check fails the hurdle, and the latest year is the peak of a window whose trough is -5833000000. The counterpoint is that fiscal year 2026 revenue of 133188000000 and a Nasdaq gross margin of 80.71598 describe a strong reported year. A strong reported year is a reason to keep the median on the page, not a reason to drop it. The chart span from 192.4 to 1255.0 says the same thing about the tape.

Detail sits in `01-business-model.md`, `02-valuation.md`, `03-competition.md`, and `04-risk-and-management.md`.
