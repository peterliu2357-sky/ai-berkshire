---
name: us-market
description: "AI Berkshire skill: US listings: quotes, filings, and the Treasury hurdle. Source: skills/us-market.md."
---

## Codex adapter note

This skill is generated from `skills/us-market.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# US listings: quotes, filings, and the Treasury hurdle

Use this skill for a domestic SEC 10-K issuer such as MU or AAPL, and for a US-listed 20-F or 40-F issuer such as TSM, ASML, or NVO. China ADR names such as PDD, TCEHY, and NTES stay on the ADR section of `skills/financial-data.md`. Korean and Taiwanese local listings are not EDGAR 10-K filers. The report stays in Chinese unless the user asks for English or passes `lang=en`.

## Data

Run the three commands in the domestic 10-K section of `skills/financial-data.md`. Do not paste extra flags onto those three lines. For a 20-F or 40-F filer, add `--adr-ratio` to `snapshot` only when the ordinary-shares-per-ADR figure is known. Without that ratio, market cap and the hurdle check are unavailable. The same block applies when submissions are missing, so the filing type is unknown, and when companyfacts are IFRS or non-USD. A passed ratio scales the cap to the ADR price times ordinary shares divided by that ratio. Cover-page shares are ordinary shares. The quote is the ADR price. Do not multiply them. IFRS and non-USD companyfacts do not become GAAP rows. The snapshot records that those rows are unavailable. `--adr-ratio` must be a finite positive number. NaN and Infinity are rejected.

Set `SEC_USER_AGENT` to a real name and email before `snapshot`. `Your Name you@example.com` shows the shape only. That literal value, and any example.com, example.org, or example.net address, is rejected. Do not commit the value. A noreply address is rejected, and a missing value stops `snapshot` before any request. `analyze` reads the snapshot file and does not open a socket.

Money is USD. GAAP net income already deducts stock-based compensation. Do not add that cost back, and do not subtract it a second time. A company non-GAAP figure that adds the cost back is not the hurdle earnings. This snapshot has no non-GAAP field unless a later parser stores one. Do not invent the bridge.

Buybacks and dilution come only from annual facts in the snapshot. Weighted-average shares are not the share count for market cap.

Market cap for a domestic 10-K is the official close times EDGAR shares outstanding, as a raw share count. If shares are missing, or the filing type is unknown, market cap is unavailable. For a 20-F or 40-F filer, and for an IFRS or non-USD filer, it is that close times ordinary shares divided by `--adr-ratio`. If the ratio is missing, market cap is unavailable. Do not pass that same product to `verify-market-cap --reported`. Do not fill `--reported` from a Nasdaq market-cap string. Do not pass US shares to `three-scenario`.

The hurdle is the later 10-year Treasury yield in the snapshot. The same date keeps the Treasury.gov par yield. One parsed series is enough. The check is the through-cycle median GAAP net income divided by market cap, compared with that yield. Through-cycle needs five fiscal years inside the latest ten calendar fiscal years. Say which years are in the window and which years are missing. Fewer than five inside the window is insufficient history. Peak earnings are not the run rate. A Yahoo daily bar's `as_of` is the bar stamp, not the closing auction. The price on that bar is the session close.

## Citations

Market cap, the share count, and GAAP amounts stay in the snapshot. `audit` still rejects a GAAP amount that is not in the snapshot, including on a line that also has a citation. Every other number needs a bracket from `python3 tools/source_ledger.py`. Paste that stdout line. The line includes `measure=` and the tier. A qualifier cannot rename shares, market cap, or enterprise value. A measure that contains profit, income, revenue, sales, or EPS is that snapshot concept unless every year on it is later than the latest fiscal year. `fy26`, `ttm`, `latest`, `last_year`, `reported`, and `actual` are the current period. Calling any such figure GAAP net income, total revenue, or 净利润 fails the audit. A line that names net income has to use the net income figure, and a line that names revenue has to use the revenue figure. A qualified figure for a period the snapshot already has must show that snapshot number in the note. `hbm_share`, `market_share`, `dram_bit_share`, `dram_cash_cost`, and `eps_growth` can be cited when the snapshot has no such concept. The collision error names the concept. Product labels such as HBM3E, 12-Hi, 1-gamma, 232-layer, Q4, FY26, Top 3, 2x, and DDR5 are not quantities. Do not pass `--tier` or `--publisher`. `PRIMARY_HOSTS` and `SECONDARY_HOSTS` in `tools/usmarket/claims.py` assign the tier and the publisher. Leave the host names in those tuples. A registry edit changes the tier, and the old bracket fails until you print it again.

Company IR is primary when the cited host is the issuer site. A submissions `website` or `investorWebsite` is stored as a `website` label. `MU` also maps to `micron.com` when that label is absent. `ir`, `investors`, `investor`, `news`, and `newsroom` prefixes of that host count. Any other subdomain stays low. The publisher is `company IR`. Biographies and filing prose use `admit excerpt`.

`admit cited` rejects `sec.gov` and its subdomains. Quote a filing with `admit excerpt` only when that accession is already a `FilingRef` on this snapshot. The command takes `--contains` and `--out`. It does not take `--url`. `--out` is `reports/<company>/evidence/excerpts/<id>.txt`, the file beside the ledger that `audit` reads. If the sentence is not in the cover document, the command reads `EX-99` exhibits from the filing index and cites that exhibit URL. An index row counts when its type or filename is `EX-99`, `EXHIBIT-99`, or `exhibit99-1.htm`.

`admit peer` records a pointer to a concept and fiscal year on another snapshot. The stored path is relative to the repo root. A peer snapshot whose ticker or CIK is this issuer is rejected. Do not copy the peer number into this file. `python3 tools/source_ledger.py remove --ledger PATH --id ID` deletes one row.

`admit dispute` groups two or more cited or peer rows that share one measure and differ in value. A section that shows one member and hides another fails `audit`.

`derive three-scenario` reads `--growth` and `--pe` as comma-separated claim ids. `derive irr` reads `--profit` and `--pe`. Profit uses the unit `usd_ones`. `--years` defaults to 3 for three-scenario and 10 for irr. Neither derive command has `--shares` or `--reported`. Do not pass a US share count to `three-scenario --shares`. Do not pass an analyze market cap to `verify-market-cap --reported`. When analyze prints `market_cap: unavailable`, irr writes no row and exits non-zero.

`admit score` takes `--stars` and at least one `--anchor`. A low claim, a derived row, or a dispute cannot anchor a star. Put those ids in `--context`. `--withhold` prints a withheld bracket and no star count. Star glyphs in the note must match the score bracket.

The ledger path is `reports/<company>/evidence/source-ledger.json`. The file stores the URL, the value, and the dates. It does not store the tier or the publisher.

One cited example, from the repo root.

```bash
python3 tools/source_ledger.py admit cited \
  --ledger reports/Micron/evidence/source-ledger.json \
  --id dram-ddr5-tf \
  --measure dram_spot_ddr5 \
  --value 5.15 \
  --unit usd_per_gb \
  --url https://www.trendforce.com/example/ddr5 \
  --published 2026-03-18
```

Check the note with `python3 tools/source_ledger.py audit --report PATH --snapshot PATH --ledger PATH`. Exit 0 on a pass. A note with no US signal prints `audit: skipped`. A snapshot note with no ledger and only snapshot numbers passes. A star glyph, an outlined star, a rating mark such as 评级四星, or a text score such as four stars with no ledger fails. `anchor=snap:market_cap` alone does not anchor a score. At least one anchor must be a cited row, an excerpt, or a peer row.

## Report rule

Quote the session kind and the source timestamp with each price. A mixed-session pair has no return. Unscaled lexemes are not dollars. Scale-free percents may be cited, and a single-source percent must say so. If `annual` and `shares` are empty, the report uses prints, yields, percents, ranges, labels, and failures only, plus any pasted citation brackets.

SEC HTTP 403 is a failed fetch. Do not invent a 10-K, a 10-Q, an 8-K, a Form 4, or a CIK.
