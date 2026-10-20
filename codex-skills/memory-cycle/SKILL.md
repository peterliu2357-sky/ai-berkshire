---
name: memory-cycle
description: "AI Berkshire skill: Memory cycle: what to measure, and what to leave blank. Source: skills/memory-cycle.md."
---

## Codex adapter note

This skill is generated from `skills/memory-cycle.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# Memory cycle: what to measure, and what to leave blank

Use this with `skills/us-market.md` for a memory maker such as Micron. Samsung and SK hynix are not EDGAR 10-K filers. A quote for `005930.KS` is a price cross-check only. It is not a 10-K.

## Facts the snapshot can hold

When the snapshot has the fact, compute it with `analyze` and cite the line.

- Inventory days are inventory divided by cost of goods, then multiplied by the period length in days. Do not divide by cost of goods times days.
- Capex ratio is absolute capex divided by absolute depreciation.
- Gross margin and operating margin percents are usable only as percents. A Nasdaq dollar cell with no scale is an unscaled lexeme.
- Through-cycle earnings are the median of annual GAAP net income. The window is the latest ten fiscal years by calendar, counting back from the newest year. State that window and any missing year inside it. Fewer than five years inside the window is insufficient history. Peak and trough stay in the set. They are not the hurdle earnings.
- Hyperscaler and export-control claims need a filing, an 8-K item 2.02 URL, or another document whose URL is in the snapshot. Quote filing prose with the excerpt command in `skills/us-market.md` when the accession is already on the snapshot. Do not scrape copyrighted transcripts. If submissions did not return HTTP 200, there is no 8-K URL.

## When the fact is missing

`analyze` prints `unavailable` when a snapshot field did not come back. Repeat unavailable for that field. A DRAM price, a NAND price, a contract price, an HBM bit shipment, or a capex dollar amount can appear only as a citation bracket from `skills/us-market.md`. Do not type the number when the snapshot and the pasted bracket both lack it. A wide 52-week range is a price fact. It is not a cycle call.

Peers NVDA, AMD, and TSMC stay in their own snapshots. Point at one field with the peer command in `skills/us-market.md`. Do not copy that number into the Micron snapshot.

A memory note needs a price, a peer, and a proxy excerpt before a star. The ledger will accept a secondary price as the only anchor. This checklist does not. Withhold the star when the note lacks a price, a peer, or a proxy.
