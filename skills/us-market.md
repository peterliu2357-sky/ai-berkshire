# US listings: quotes, filings, and the Treasury hurdle

Use this skill for a domestic SEC 10-K issuer such as MU or AAPL. China ADR names such as PDD, TCEHY, and NTES stay on the ADR section of `skills/financial-data.md`. Korean and Taiwanese listings are not EDGAR 10-K filers.

## Data

Run the three commands in the domestic 10-K section of `skills/financial-data.md`. Do not paste extra flags. Set `SEC_USER_AGENT` to a name and an email such as `Your Name you@example.com` before `snapshot`. Do not commit that value. A noreply address is rejected, and a missing value stops `snapshot` before any request. `analyze` reads the snapshot file and does not open a socket.

Money is USD. GAAP net income already deducts stock-based compensation. Do not add that cost back, and do not subtract it a second time. A company non-GAAP figure that adds the cost back is not the hurdle earnings. This snapshot has no non-GAAP field unless a later parser stores one. Do not invent the bridge.

Buybacks and dilution come only from annual facts in the snapshot. Weighted-average shares are not the share count for market cap.

Market cap is the official close times EDGAR shares outstanding, as a raw share count. Then run `tools/financial_rigor.py verify-market-cap` with that raw count and `--currency USD`. If shares are missing, market cap is unavailable. Do not fill `--reported` from a Nasdaq market-cap string. Do not pass US shares to `three-scenario`.

The hurdle is the later 10-year Treasury yield in the snapshot. The same date keeps the Treasury.gov par yield. One parsed series is enough. The check is the through-cycle median GAAP net income divided by market cap, compared with that yield. Through-cycle needs five fiscal years. Fewer years is insufficient history. Peak earnings are not the run rate.

## Report rule

Every number in the report must appear in the snapshot JSON. Quote the session kind and the source timestamp with each price. A mixed-session pair has no return. Unscaled lexemes are not dollars. Scale-free percents may be cited, and a single-source percent must say so. If `annual` and `shares` are empty, the report uses prints, yields, percents, ranges, labels, and failures only.

SEC HTTP 403 is a failed fetch. Do not invent a 10-K, a 10-Q, an 8-K, a Form 4, or a CIK.
