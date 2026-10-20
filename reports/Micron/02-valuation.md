---
title: Micron valuation, Buffett view, 2026-10-20
date: 2026-10-20
type: 研究
market: us
---

# Micron valuation, Buffett view, 2026-10-20

Data cutoff is 2026-10-20. Not investment advice. Judgment is marked as judgment.

## Official close and cap

The official close used for market cap is 904.90 USD, kind official_close, source yahoo_daily_close, timestamp 2026-10-19T13:30:00+00:00. That timestamp is the bar stamp, not the closing auction.

Earlier official closes in the file, same kind and source, are 914.13 at 2026-10-14T13:30:00+00:00, 931.24 at 2026-10-15T13:30:00+00:00, and 878.84 at 2026-10-16T13:30:00+00:00.

Yahoo chart intraday last is 901.914 at 2026-10-20T19:41:02+00:00. The file also holds a nasdaq_info intraday last of 902.0609. Those prints are not the official close. This note states no return across session kinds.

Shares are 1131423212 as of 2026-10-02, tag EntityCommonStockSharesOutstanding. Market cap is 1023824864538.80 USD. The product was not passed back to verify-market-cap. An unscaled Nasdaq Market Cap lexeme is in the file and is not treated as dollars.

Yahoo high is 1255.0 and low is 192.4.

## Through-cycle hurdle

Fiscal years 2017 through 2026 are the window. The file shows no gap inside that window. The median is 6087000000, the peak is 84969000000, and the trough is -5833000000. The peak is the latest year. It is not the run rate.

| Fiscal year | Revenue | Net income |
| --- | --- | --- |
| 2017 | 20322000000 | 5089000000 |
| 2018 | 30391000000 | 14135000000 |
| 2019 | 23406000000 | 6313000000 |
| 2020 | 21435000000 | 2687000000 |
| 2021 | 27705000000 | 5861000000 |
| 2022 | 30758000000 | 8687000000 |
| 2023 | 15540000000 | -5833000000 |
| 2024 | 25111000000 | 778000000 |
| 2025 | 37378000000 | 8539000000 |
| 2026 | 133188000000 | 84969000000 |

Treasury par yield is 0.0515 on 2026-10-19. FRED DGS10 is 0.0509 on 2026-10-16. The hurdle uses the later Treasury.gov par yield.

The hurdle check prints earnings yield 0.005945352775488605368121573015 against rate 0.0515 and clears=no.

Fiscal 2026 stock-based compensation is 1333000000. The analyze ratio is 0.01568807447422000965057844626. GAAP net income already deducts that cost. A non-GAAP figure that adds it back is not the hurdle earnings.

Inventory days are 149.4175362093131910917302601 and the period length is 370 days, end 2026-09-03. The fiscal 2026 capex ratio is 3.231821530043144270230453541. Fiscal 2026 buybacks are 650000000. Fiscal 2025 buybacks are 0. Cash as a balance-sheet total is not an annual concept in the rows used here, so it is not stated.

## One quarter of company outlook, not a three-year path

Company IR prints a first-quarter outlook for the year after the latest filed fiscal year. The page's own label for the figure is revenue. The stored amount is the midpoint in ones.

{61500000000}[c:fq1-2027-guide https://investors.micron.com/news/press-release/2026/Micron-Technology-Inc--Reports-Record-Fiscal-Fourth-Quarter-and-Full-Year-2026-Results/ company IR published=2026-09-30 measure=fq1_2027_outlook_usd_ones primary]

The same page prints a GAAP diluted EPS outlook for that quarter.

{37.84}[c:fq1-2027-eps https://investors.micron.com/news/press-release/2026/Micron-Technology-Inc--Reports-Record-Fiscal-Fourth-Quarter-and-Full-Year-2026-Results/ company IR published=2026-09-30 measure=fq1_2027_gaap_diluted_eps primary]

The exhibit repeats the outlook band.

[c:mu-8k-guide https://www.sec.gov/Archives/edgar/data/723125/000072312526000018/a2026q4ex991-pressrelease.htm SEC published=2026-09-30 primary]
[q:mu-8k-guide]
FQ1-27     GAAP  (1)   Outlook        Non-GAAP  (2)   Outlook                  Revenue     $61.5 billion ± $1.5 billion
[/q]

Judgment: a one-quarter outlook is not a three-year earnings growth rate. It was not fed to derive.

## Why derive did not run

`derive three-scenario` needs three cited growth rates and three cited exit multiples. This ledger has percent changes in DRAM and NAND contract prices, and it has the one-quarter outlook above. It does not have three published multi-year EPS growth rates, and it does not have three published exit multiples. A Reuters page that a search result described was not fetched, so no multiple from that page was admitted. `derive irr` needs a cited terminal-year profit in usd ones. No such profit was found, so no IRR row was written. `terminal_value.py` was not run. The ten-year position-size test is unavailable. That absence is not a buy signal and it is not, by itself, a veto.

The price fact this file does have is the hurdle. The counterpoint is that fiscal 2026 net income was 84969000000, so a trailing multiple on the peak looks nothing like the multiple on the median. The peak is still the peak.

A memory star also needs a price, a peer, and a proxy excerpt.

{60.70}[c:ddr5-16gb-spot https://www.trendforce.com/price/dram/dram_spot TrendForce published=2026-10-20 measure=ddr5_16gb_4800_session_average secondary]

{23601000000}[c:amd-rev-2022 https://www.sec.gov/Archives/edgar/data/2488/000000248825000012/amd-20241228.htm SEC published=2025-02-05 primary]

[c:mu-proxy-ceo https://www.sec.gov/Archives/edgar/data/723125/000072312525000038/mu-20251125.htm SEC published=2025-11-25 primary]
[q:mu-proxy-ceo]
currently led by Sanjay Mehrotra, as our Chairman, President and Chief Executive Officer
[/q]

The industry margin beside Micron's is the SK hynix operating-margin print.

{76}[c:skh-margin https://news.skhynix.com/en/q2-2026-business-results/ SK hynix published=2026-07-29 measure=skhynix_q2_2026_operating_margin_percent secondary]

The filing sentence used as the valuation anchor is the HBM reversal risk.

[c:mu-10k-hbm https://www.sec.gov/Archives/edgar/data/723125/000072312526000023/mu-20260903.htm SEC published=2026-10-09 primary]
[q:mu-10k-hbm]
If demand for HBM weakens and suppliers shift capacity from HBM to conventional DRAM, this could result in a significant increase in conventional DRAM supply.
[/q]

## Score

Judgment: at the official close, the through-cycle median does not clear the Treasury hurdle. That is a statement about a new purchase at this cap. It is not a sourced sale price for a holder.

★★

[s:score-buffett stars=2 anchor=mu-10k-hbm,skh-margin context=dram-qoq-dispute,ddr4-spot-vs-contract]

No simulated quotation. This run did not read a Buffett original about Micron.

Buffett's price question, applied as a question: if the quote went away for five years, the thing left on the page would be the median of those ten fiscal years against the Treasury yield, not the latest year.
