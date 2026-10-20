---
title: Micron snapshot note, 2026-10-20
date: 2026-10-20
type: 研究
---

# Micron snapshot note, 2026-10-20

Data cutoff is 2026-10-20. The evidence file is `evidence/us-snapshot-MU.json`, written by `tools/us_market.py snapshot`. This note is research, not investment advice.

`analyze` on that file prints a share count, a market cap, and GAAP rows. The through-cycle median uses the latest ten fiscal years, 2017 through 2026. `Form 4` rows were parsed from the raw XML. Nasdaq info returned a last sale with no clock, recorded as `undated last sale`. Nasdaq statement cells remain unscaled lexemes.

Every figure in the four English notes and in `final-report.md` is a whole field in the snapshot, a figure on an `analyze` summary line, or a part of a full date that appears on the same line.

Reproduce the file from the repo root with the three commands in the domestic `10-K` section of `skills/financial-data.md`. `snapshot` requires `SEC_USER_AGENT` in the environment, in the form `Your Name you@example.com`. Do not commit that value.
