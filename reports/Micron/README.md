---
title: Micron snapshot note, 2026-10-20
date: 2026-10-20
type: 研究
---

# Micron snapshot note, 2026-10-20

Data cutoff is 2026-10-20. The evidence file is `evidence/us-snapshot-MU.json`, written by `tools/us_market.py snapshot`. This note is research, not investment advice.

`analyze` on that file prints a share count, a market cap, and GAAP rows. The failures list is empty. FRED DGS10 and the Treasury par yield are both present. Nasdaq statement cells remain unscaled lexemes. They are not treated as dollars.

What the file contains is listed in the four English notes and in `final-report.md`. Every figure in those notes is a field in the snapshot or a figure `analyze` prints from that file.

Reproduce the file from the repo root with the three commands in the domestic 10-K section of `skills/financial-data.md`. `snapshot` requires `SEC_USER_AGENT` in the environment, in the form `Your Name you@example.com`. Do not commit that value.
