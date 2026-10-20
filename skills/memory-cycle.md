# Memory cycle: what to measure, and what to leave blank

Use this with `skills/us-market.md` for a memory maker such as Micron. Samsung and SK hynix are not EDGAR 10-K filers. A quote for `005930.KS` is a price cross-check only. It is not a 10-K.

## Facts the snapshot can hold

When the snapshot has the fact, compute it with `analyze` and cite the line.

- Inventory days are inventory divided by cost of goods, then multiplied by the period length in days. Do not divide by cost of goods times days.
- Capex ratio is absolute capex divided by absolute depreciation.
- Gross margin and operating margin percents are usable only as percents. A Nasdaq dollar cell with no scale is an unscaled lexeme.
- Through-cycle earnings are the median of annual GAAP net income. The tool needs at least five fiscal years and, when more exist, keeps only the latest ten. State that window in the report. Peak and trough stay in the set. They are not the hurdle earnings.
- Hyperscaler and export-control claims need a filing, an 8-K item 2.02 URL, or another document whose URL is in the snapshot. Do not scrape copyrighted transcripts. If submissions did not return HTTP 200, there is no 8-K URL.

## When the fact is missing

`analyze` prints `unavailable`. The report repeats unavailable. Do not publish a DRAM price, a NAND price, a contract price, an HBM bit shipment, or a capex dollar amount that is not a field in the snapshot. A wide 52-week range is a price fact. It is not a cycle call.

Peers NVDA, AMD, and TSMC can be quoted with the same tool when the ticker passes validation. Their filings are separate snapshots. Do not borrow their numbers into the Micron snapshot.
