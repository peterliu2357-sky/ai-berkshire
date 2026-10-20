---
title: Micron snapshot note, 2026-10-20
date: 2026-10-20
type: 研究
---

# Micron snapshot note, 2026-10-20

Data cutoff is 2026-10-20. The evidence file is `evidence/us-snapshot-MU.json`, written by `tools/us_market.py snapshot` after `quote`. `analyze` reads that file and does not open a socket. This note is research, not investment advice.

The issuer is information grade A on the skill scale: annual GAAP facts in this file run through fiscal year 2026, and a `10-K` was filed 2026-10-09. The trap for a grade A name is to treat a widely discussed peak year as the business. Sell-side notes are not in the file, so this report cannot measure how close it sits to street consensus. A long GAAP history can feel complete. It does not show what a customer buys.

Bias checks kept while writing:

- The hurdle result comes from the median GAAP net income and the Treasury yield in the file, not from how many rows the file has.
- Dropping the peak year from the story would change the tone. The tool keeps the peak in the set and does not use it as the run rate.
- No street narrative was loaded, so agreement with the market story is not an input.
- A good business with a thin public record is not the case this file describes. The record is long. The product mix is still missing.

`analyze` prints a share count, a market cap, and GAAP rows. `through_cycle` uses fiscal years 2017 through 2026. Gaps are none. The failures list is empty. Nasdaq info is a timed intraday last, not an official close. Nasdaq statement cells remain unscaled lexemes.

Every figure in the four English notes and in `final-report.md` is a whole field in the snapshot or a figure on an `analyze` summary line. A date part is cited only on a line that also contains a snapshot timestamp, or the timestamp sits in code ticks when the clock offset is negative.

Reproduce the file from the repo root with the three commands in the domestic `10-K` section of `skills/financial-data.md`. `snapshot` requires `SEC_USER_AGENT` in the environment. Do not commit that value.

Detail sits in `01-business-model.md`, `02-valuation.md`, `03-competition.md`, `04-risk-and-management.md`, and `final-report.md`.
