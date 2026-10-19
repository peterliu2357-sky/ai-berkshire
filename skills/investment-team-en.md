# Investment team, English path for a domestic 10-K issuer

Run this for a US domestic 10-K issuer. The default Chinese team skill stays in force for China, Hong Kong, Taiwan, and China ADR names.

## Files

Write English markdown under `reports/{Company}/`.

- `README.md` states the data cutoff, the snapshot path, and what is unavailable.
- `01-business-model.md` is the Duan Yongping view.
- `02-valuation.md` is the Buffett view.
- `03-competition.md` is the Munger view.
- `04-risk-and-management.md` is the Li Lu view.
- `final-report.md` is the team lead synthesis.
- `evidence/us-snapshot-{TICKER}.json` is the tool output. It is evidence, not a finished report.

## Method

1. Run the three commands in the domestic 10-K section of `skills/financial-data.md`.
2. For a memory maker, also follow `skills/memory-cycle.md`.
3. Use `skills/us-market.md` for GAAP, stock-based compensation, buybacks, the Treasury hurdle, and market cap.
4. Do not call `three-scenario` with a US share count.
5. If WebSearch or EDGAR fails, say so at the top. Do not fill GAAP from memory.
6. State a fact only when the snapshot or a saved filing supports it. Mark a judgment as a judgment. Give the counterpoint in the same section.
7. Withhold a star score when the filing source failed. An unavailable score is the result.

## Valuation block

Official close only, with kind and timestamp. Market cap only when shares exist, checked with `tools/financial_rigor.py verify-market-cap` and `--currency USD`. Through-cycle median versus the selected Treasury yield. If either input is missing, write `unavailable`.
