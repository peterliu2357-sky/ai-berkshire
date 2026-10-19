---
title: Micron valuation, Buffett view, 2026-10-19
date: 2026-10-19
type: 研究
---

# Micron valuation, Buffett view, 2026-10-19

Data cutoff is 2026-10-19. Source file `evidence/us-snapshot-MU.json`. Not investment advice.

## Price, with the session attached

Yahoo daily close field, source `yahoo_daily_close`. The timestamp on each bar is 13:30 UTC. That is the stamp Yahoo puts on the daily bar. It is not a separate closing-auction clock.

- 2026-10-13T13:30:00+00:00 is 953.19 USD
- 2026-10-14T13:30:00+00:00 is 914.13 USD
- 2026-10-15T13:30:00+00:00 is 931.24 USD
- 2026-10-16T13:30:00+00:00 is 878.84 USD

878.84 USD is the latest `official_close` in the file. It is one source. This run did not store a Nasdaq `Closed at` print.

Two later prints are `intraday_last` on 2026-10-19, not closes.

- Nasdaq info, 2026-10-19T09:37:00-04:00, is 914.085 USD
- Yahoo chart, 2026-10-19T13:37:50+00:00, is 913.76 USD

`compare_prints` marks an official close against either intraday print as `mixed_session`, so there is no return between 878.84 and 914.085. The two intraday prints are the same kind and the same calendar day. Both are quoted. Neither is the close used for a market cap.

The Yahoo chart meta high is 1255.0 and the low is 192.4. Nasdaq summary stores the same endpoints as the text `$1255/$192.4`. The chart meta does not date each endpoint on its own.

## What cannot be priced

Shares are unavailable. Market cap is unavailable. `verify-market-cap` was not run, because there is no EDGAR share count to multiply. The Nasdaq summary cell labeled Market Cap has lexeme `1,033,849,274,197`. That string has no scale. It is not a dollar market cap and it was not passed to `--reported`.

GAAP net income is unavailable, so there is no through-cycle median and no earnings yield. Stock-based compensation is unavailable. Buybacks are unavailable.

The Treasury.gov par yield in the file is rate 0.0509 on 2026-10-16, source `treasury_par`. FRED DGS10 failed with status 0, so the hurdle is a single series. The hurdle check is unavailable because income and market cap are missing.

A Nasdaq income-statement cell labeled Total Revenue, period end 8/28/2025, has lexeme `$37,378,000`. The cell has no scale. It is not a dollar revenue figure. The same is true of the other dollar-signed cells in the file.

Judgment: there is no intrinsic-value estimate in this note. The counterpoint is that a last daily close of 878.84 and a same-day intraday pair near 914.085 and 913.76 already disagree about which price a buyer would be paying, before any earnings input exists.

No star score.

> "Price is what you pay, value is what you get." Warren Buffett. The price prints are in the snapshot. The value is not.
