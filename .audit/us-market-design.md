# US market design, locked after review

Both interrogations were Grok-family. Opus, Gemini, GPT, and Muse did not start. The lock below is the lead judgment on the two reviews, then the code that tests passed against.

## Commands

Three commands. The lines are identical in `README.md`, `README_EN.md`, and the new domestic 10-K section of `skills/financial-data.md`. English skills point at that section and do not paste the lines. China ADR names stay on the old macrotrends section.

```bash
python3 tools/us_market.py quote MU
python3 tools/us_market.py snapshot MU --out reports/Micron/evidence/us-snapshot-MU.json
python3 tools/us_market.py analyze --snapshot reports/Micron/evidence/us-snapshot-MU.json
```

`quote` prints kind and timestamp. Exit 0 when a print exists. Exit 2 otherwise. It writes nothing.

`snapshot` always writes the JSON when the command runs to completion. Exit 0 when at least one print or yield was saved. Exit 2 when neither was. SEC 403 is a `FetchFailure` inside the file, not a missing file. A timeout returns status 0 and does not raise.

`analyze` does not open a socket. Exit 0 for a snapshot, including empty GAAP. Exit 1 when the file is not a snapshot.

Write uses `tempfile.mkstemp` and `os.replace`. A second run replaces the same path. The JSON has no local clock field.

Ticker pattern allows `MU`, `BRK-B`, and `005930.KS`. Korean listings are not 10-K filers.

## Types

Package `tools/usmarket/` with `types.py`, `value.py`, `fetch.py`. CLI is `tools/us_market.py`.

`MarketPrint` carries `PrintKind`: `official_close`, `intraday_last`, `extended_hours`. Undated prices are dropped. Yahoo `chartPreviousClose` is not a print. Completed daily bars before the current regular session are `official_close` with source `yahoo_daily_close`. The bar timestamp is the one Yahoo sends.

`UnscaledAmount` JSON has `type`, `lexeme`, `label`, `period_end`, `source`. It has no `ones` and no `number`. Nasdaq statement cells and the Nasdaq market-cap string stay here. `analyze` does not treat them as dollars.

`Percent` holds scale-free ratios such as gross margin.

`AnnualFact.ones` is already dollars from XBRL `val`. There is no second scale factor. Flow facts need a 300 to 380 day span and a form that starts with 10-K, 20-F, or 40-F. The later `filed` value wins. Segments are skipped. Instant inventory uses `InventoryNet` with no `start`. Share count is an instant `EntityCommonStockSharesOutstanding` or `CommonStockSharesOutstanding`. A row with `start` is not a share count. Weighted-average shares are not a share count.

`TreasuryYield.rate` is a fraction quantized to 0.0001. Blank and `.` cells are skipped. `select_hurdle` takes the later date. The same date keeps `treasury_par`.

## Valuation

Decimal context matches `financial_rigor.py`. `inventory_days` is inventory divided by cost of goods, then times the period length. `capex_ratio` uses absolute values. `through_cycle` returns none below five fiscal years. The median is not the peak. GAAP net income is not grossed up for stock-based compensation. Market cap is official close times EDGAR shares. Missing shares skip `verify-market-cap`. US shares do not go to `three-scenario`.

## Report

English files under `reports/Micron/`. `CLAUDE.md` keeps Chinese as the default and names the English filenames for a domestic 10-K. A test fails if a number in those notes is not in `evidence/us-snapshot-MU.json`.

## Rejected

One module for HTTP and medians. Replacing the ADR section. Exit 2 on SEC 403 when quotes exist, because that blocks `analyze`. Converting unscaled lexemes to dollars. Publishing a GAAP figure when EDGAR is 403. Omitting the four-master files. The user asked for those files. The content rule is fail-closed.
