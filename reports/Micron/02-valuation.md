---
title: Micron valuation, Buffett view, 2026-10-20
date: 2026-10-20
type: 研究
---

# Micron valuation, Buffett view, 2026-10-20

Data cutoff is 2026-10-20. Source file `evidence/us-snapshot-MU.json`. Not investment advice.

## Price

Market cap uses an official close only. The close `analyze` selects is the later official close: 904.90 USD, kind official_close, source `yahoo_daily_close`, as of 2026-10-19T13:30:00+00:00. That timestamp is the bar stamp, not the closing auction. `analyze` marks daily-bar lines `clock=bar_stamp`.

Other official closes in the file, same kind and source, each a session close:

- 2026-10-14T13:30:00+00:00 is 914.13 USD
- 2026-10-15T13:30:00+00:00 is 931.24 USD
- 2026-10-16T13:30:00+00:00 is 878.84 USD
- 2026-10-19T13:30:00+00:00 is 904.90 USD

The session on 2026-10-20 is not closed in this file. Two intraday lasts are present. They are not the market-cap price. A mixed-session pair has no return.

- Yahoo chart intraday last is 915.766 USD, kind intraday_last, source `yahoo_chart`, as of 2026-10-20T14:52:03+00:00.
- Nasdaq intraday last is 915.7657 USD, kind intraday_last, source `nasdaq_info`, as of `2026-10-20T10:52:00-04:00`.

The chart meta high is 1255.0 and the low is 192.4, source `yahoo_chart`. A wide high-low span is a price fact. It is not a cycle call and it is not a valuation band.

## Shares and market cap

The share fact is `EntityCommonStockSharesOutstanding`, count 1131423212, as of 2026-10-02. Weighted-average shares are not the share count for market cap. The latest `10-K` was filed 2026-10-09. Fiscal year 2026 ends 2026-09-03. Listing in the file is domestic, so no ADR ratio is applied.

`analyze` prints `market_cap: usd=1023824864538.80` from price 904.90 times those shares, source `yahoo_daily_close`. That product was not passed back to `verify-market-cap --reported`. Doing so would check the product against itself. US shares were not passed to `three-scenario`. The `calc` command in `tools/financial_rigor.py` uses binary floating point. Its printed tail is not the decimal on the `analyze` line, so it is not the cap in this note.

The Nasdaq Market Cap lexeme is `1,036,180,006,014`. The cell has no scale field. It is not an independent dollar cap, and it is not the official-close product above. The official-close cap remains 1023824864538.80 USD.

## The hurdle

`through_cycle` keeps fiscal years 2017 through 2026 and prints gaps none. Median GAAP net income is 6087000000. Peak is 84969000000. Trough is -5833000000. The window has five or more years inside it. History is sufficient for the tool. The peak is not the hurdle earnings.

The hurdle is the later yield. Treasury par is 0.0515 on 2026-10-19, source `treasury_par`. FRED DGS10 is 0.0509 on 2026-10-16, source `fred_dgs10`. `analyze` uses 0.0515. `cross-validate` was run on those two rates and reported them inside its default tolerance. The deviation it printed is not a snapshot field and is not repeated here.

The earnings yield on the ten-year median is 0.005945352775488605368121573015. The check prints `clears=no`.

Stock-based compensation for fiscal year 2026 is 1333000000. The ratio to absolute GAAP net income is 0.01568807447422000965057844626. GAAP net income already deducts that cost. It is not added back, and a non-GAAP bridge is not in the snapshot.

## What was not priced

`three-scenario` was not run. Its share argument is not a raw share count, and the US path forbids passing this share count in. A target price from that tool is unavailable. No valuation price band is in the file.

The ten-year exit-PE and IRR tools were not run. They need a capital cost, a steady ROIC, and a perpetual growth rate. Those inputs are judgments, and the numbers they produce are not snapshot fields. The US rule used here is that every number in the note must already be in the snapshot or on an `analyze` line. Publishing those outputs would break that rule. The hurdle check above is the valuation test this path does run. It is a position pressure test against the Treasury yield. It is not, by itself, the whole buy or avoid decision. That joint decision is in `final-report.md`.

Per-share earnings, book value, and dividend are not fields. `verify-valuation` was not run, because those per-share inputs are not in the file.

Judgment: this note has no intrinsic-value price range. The counterpoint is the peak. A reader who puts 84969000000 over the same market cap is using the latest year, not the median the tool uses. Both dollar amounts are in the file. The second yield was not computed, and it is not printed.

No star score.

Buffett question: if the required return is wrong, does the conclusion flip? The flip tool was not run, for the reason above. What the file does show is a median earnings yield of 0.005945352775488605368121573015 against a Treasury par rate of 0.0515, and the check prints `clears=no`.

The question about holding through a five-year market close is a judgment: the file does not show a reason the customer must keep paying, and the median does not clear the Treasury yield. That is not a willingness to hold.

> "Price is what you pay; value is what you get." Warren Buffett, quoting Ben Graham, in the Berkshire shareholder letter PDF at `https://www.berkshirehathaway.com/letters/2008ltr.pdf`. The sentence beside it says he likes quality merchandise when it is marked down. The extension used here stays with that sentence: the file has a price, 904.90 USD, and the through-cycle check does not show that price as a markdown against median GAAP earnings. The letter is not a comment on this issuer.
