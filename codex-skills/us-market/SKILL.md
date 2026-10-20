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

Run the three commands in the domestic 10-K section of `skills/financial-data.md`. Do not paste extra flags onto those three lines. For a 20-F or 40-F filer, add `--adr-ratio` to `snapshot` only when the ordinary-shares-per-ADR figure is known. Without that ratio, market cap and the hurdle check are unavailable. Cover-page shares are ordinary shares. The quote is the ADR price. Do not multiply them. IFRS and non-USD companyfacts do not become GAAP rows. The snapshot records that those rows are unavailable.

Set `SEC_USER_AGENT` to a real name and email before `snapshot`. `Your Name you@example.com` shows the shape only. That literal value, and any example.com, example.org, or example.net address, is rejected. Do not commit the value. A noreply address is rejected, and a missing value stops `snapshot` before any request. `analyze` reads the snapshot file and does not open a socket.

Money is USD. GAAP net income already deducts stock-based compensation. Do not add that cost back, and do not subtract it a second time. A company non-GAAP figure that adds the cost back is not the hurdle earnings. This snapshot has no non-GAAP field unless a later parser stores one. Do not invent the bridge.

Buybacks and dilution come only from annual facts in the snapshot. Weighted-average shares are not the share count for market cap.

Market cap for a domestic 10-K is the official close times EDGAR shares outstanding, as a raw share count. If shares are missing, market cap is unavailable. For a 20-F or 40-F filer it is that close times ordinary shares divided by `--adr-ratio`. If the ratio is missing, market cap is unavailable. Do not pass that same product to `verify-market-cap --reported`. Do not fill `--reported` from a Nasdaq market-cap string. Do not pass US shares to `three-scenario`.

The hurdle is the later 10-year Treasury yield in the snapshot. The same date keeps the Treasury.gov par yield. One parsed series is enough. The check is the through-cycle median GAAP net income divided by market cap, compared with that yield. Through-cycle needs five fiscal years inside the latest ten calendar fiscal years. Say which years are in the window and which years are missing. Fewer than five inside the window is insufficient history. Peak earnings are not the run rate. A Yahoo daily bar's `as_of` is the bar stamp, not the closing auction. The price on that bar is the session close.

## Report rule

Every number in the report must appear in the snapshot JSON. Quote the session kind and the source timestamp with each price. A mixed-session pair has no return. Unscaled lexemes are not dollars. Scale-free percents may be cited, and a single-source percent must say so. If `annual` and `shares` are empty, the report uses prints, yields, percents, ranges, labels, and failures only.

SEC HTTP 403 is a failed fetch. Do not invent a 10-K, a 10-Q, an 8-K, a Form 4, or a CIK.
