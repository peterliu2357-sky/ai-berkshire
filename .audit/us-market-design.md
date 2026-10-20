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

`snapshot` calls `sec_user_agent()` before any request. A missing or malformed `SEC_USER_AGENT` exits 2 and writes nothing. The value is the environment variable, or one line in `local/sec_user_agent.txt`. It must be a name plus an email. A noreply address is rejected. The placeholder in docs is `Your Name you@example.com`. The value is not committed.

When the agent is valid, `snapshot` writes the JSON if the command finishes. Exit 0 when at least one print or yield was saved. Exit 2 when neither was. A later SEC 403 is a `FetchFailure` inside the file, not a missing file. A timeout returns status 0 and does not raise.

`http_get` sends `User-Agent`, `Accept`, `Accept-Encoding: gzip, deflate`, and `Host`. It decompresses gzip and deflate. It retries 403, 429, 500, 502, 503, 504, and status 0, with pauses of 0.5, 1, and so on. `sec.gov` waits at least 0.12 seconds between requests. A 200 body is cached under `local/http-cache` for 12 hours. After the retries fail, a stale cache is used and the URL is printed on stderr. `sec.gov` and `stlouisfed.org` use the declared agent. Yahoo, Nasdaq, and Treasury keep a browser agent. Treasury is cached. A declared agent on Nasdaq hangs, so it stays on the browser agent.

`analyze` does not open a socket. Exit 0 for a snapshot, including empty GAAP. Exit 1 when the file is not a snapshot.

Write uses `tempfile.mkstemp` and `os.replace`. A second run replaces the same path. The JSON has no local clock field.

Ticker pattern allows `MU`, `BRK-B`, and `005930.KS`. Korean listings are not 10-K filers.

## Types

Package `tools/usmarket/` with `types.py`, `value.py`, `fetch.py`. CLI is `tools/us_market.py`.

`MarketPrint` carries `PrintKind`: `official_close`, `intraday_last`, `extended_hours`. Undated prices are dropped. Yahoo `chartPreviousClose` is not a print. Completed daily bars before the current regular session are `official_close` with source `yahoo_daily_close`. The bar timestamp is the one Yahoo sends.

`UnscaledAmount` JSON has `type`, `lexeme`, `label`, `period_end`, `source`. It has no `ones` and no `number`. Nasdaq statement cells and the Nasdaq market-cap string stay here. `analyze` does not treat them as dollars.

`Percent` holds scale-free ratios such as gross margin.

`AnnualFact.ones` is already dollars from XBRL `val`. There is no second scale factor. Flow facts need a 300 to 380 day span and a form that starts with 10-K, 20-F, or 40-F. The later `filed` value wins for the dollar amount. Segments are skipped. The fiscal year is an annual `CY` frame when any fact for that period end has one. Otherwise it is the `fy` on the earliest filing of that end. A later 10-K often stamps its own `fy` on comparative columns, and that stamp is not the period year. Instant inventory uses `InventoryNet` with no `start`. Share count is an instant `EntityCommonStockSharesOutstanding` or `CommonStockSharesOutstanding`. A row with `start` is not a share count. Weighted-average shares are not a share count.

`TreasuryYield.rate` is a fraction quantized to 0.0001. Blank and `.` cells are skipped. `select_hurdle` takes the later date. The same date keeps `treasury_par`.

## Valuation

Decimal context matches `financial_rigor.py`. `inventory_days` is inventory divided by cost of goods, then times the period length. `capex_ratio` uses absolute values. `through_cycle` returns none below five fiscal years. The median is not the peak. GAAP net income is not grossed up for stock-based compensation. Market cap is official close times EDGAR shares. Missing shares skip `verify-market-cap`. US shares do not go to `three-scenario`.

## Report

English files under `reports/Micron/`. `CLAUDE.md` keeps Chinese as the default and names the English filenames for a domestic 10-K. A test fails if a number in those notes is not in `evidence/us-snapshot-MU.json` and not in the `analyze` text for that same file.

## Rejected

One module for HTTP and medians. Replacing the ADR section. Exit 2 on SEC 403 when quotes exist, because that blocks `analyze`. Converting unscaled lexemes to dollars. Publishing a GAAP figure when EDGAR is 403. Omitting the four-master files. The user asked for those files. The content rule is fail-closed.
