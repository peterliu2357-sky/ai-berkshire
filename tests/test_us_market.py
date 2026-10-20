#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_TOOLS = _ROOT / "tools"
_FIX = _ROOT / "tests" / "fixtures" / "us"
sys.path.insert(0, str(_TOOLS))

import us_market  # noqa: E402
from usmarket.fetch import (  # noqa: E402
    build_snapshot,
    http_get,
    parse_companyfacts,
    parse_form4,
    parse_fred_dgs10,
    parse_nasdaq_financials,
    parse_nasdaq_info,
    parse_nasdaq_summary_cap,
    parse_submissions,
    parse_treasury_par,
    parse_yahoo_chart,
)
from usmarket.types import (  # noqa: E402
    AnnualFact,
    IssuerSnapshot,
    MarketPrint,
    snapshot_from_json,
    PrintKind,
    ShareCount,
    TreasuryYield,
)
from usmarket.value import (  # noqa: E402
    capex_ratio,
    clears_hurdle,
    compare_prints,
    inventory_days,
    select_hurdle,
    through_cycle,
)

_COMMANDS = [
    "python3 tools/us_market.py quote MU",
    "python3 tools/us_market.py snapshot MU --out reports/Micron/evidence/us-snapshot-MU.json",
    "python3 tools/us_market.py analyze --snapshot reports/Micron/evidence/us-snapshot-MU.json",
]
_AGENT_PATH = _ROOT / "local" / "sec_user_agent.txt"
_AGENT_BYTES = _AGENT_PATH.read_bytes() if _AGENT_PATH.exists() else None
_AGENT_MTIME = _AGENT_PATH.stat().st_mtime_ns if _AGENT_PATH.exists() else None


def _read(name: str) -> bytes:
    return (_FIX / name).read_bytes()


def _empty_snap(**kwargs) -> IssuerSnapshot:
    base = dict(
        ticker="MU",
        prints=(),
        filings=(),
        annual=(),
        shares=None,
        yields=(),
        unscaled=(),
        percents=(),
        ranges=(),
        labels=(),
        insiders=(),
        failures=(),
    )
    base.update(kwargs)
    return IssuerSnapshot(**base)


class TestSessionPrints(unittest.TestCase):
    def test_yahoo_prior_close_drops_undated_fields(self):
        prints, ranges, detail = parse_yahoo_chart(_read("yahoo_chart_mu.json"), "MU")
        self.assertEqual(detail, "")
        meta_print = next(item for item in prints if item.source == "yahoo_chart")
        self.assertEqual(meta_print.price, Decimal("878.84"))
        self.assertEqual(meta_print.kind, PrintKind.OFFICIAL_CLOSE)
        self.assertEqual(meta_print.as_of, datetime(2026, 10, 16, 20, 0, tzinfo=timezone.utc))
        daily = [item for item in prints if item.source == "yahoo_daily_close"]
        self.assertEqual(daily[-1].price, Decimal("878.84"))
        self.assertEqual(daily[-1].as_of.date(), date(2026, 10, 16))
        self.assertTrue(all(item.kind == PrintKind.OFFICIAL_CLOSE for item in daily))
        self.assertEqual({item.label: item.value for item in ranges}["fifty_two_week_high"], Decimal("1255.0"))
        self.assertNotIn(Decimal("1029"), [item.price for item in prints])
        self.assertNotIn(Decimal("1029.0"), [item.price for item in prints])

    def test_nasdaq_date_only_stamp_is_not_a_print(self):
        body = json.dumps({
            "data": {
                "marketStatus": "Closed",
                "primaryData": {
                    "lastSalePrice": "$904.90",
                    "lastTradeTimestamp": "Oct 19, 2026",
                },
            }
        }).encode()
        prints, detail = parse_nasdaq_info(body, "MU")
        self.assertEqual(prints, [])
        self.assertEqual(detail, "undated last sale")

    def test_nasdaq_splits_premarket_from_official_close(self):
        prints, detail = parse_nasdaq_info(_read("nasdaq_info_mu.json"), "MU")
        self.assertEqual(detail, "")
        by_kind = {item.kind: item for item in prints}
        self.assertEqual(by_kind[PrintKind.EXTENDED_HOURS].price, Decimal("912.00"))
        self.assertEqual(by_kind[PrintKind.OFFICIAL_CLOSE].price, Decimal("878.84"))
        self.assertEqual(by_kind[PrintKind.OFFICIAL_CLOSE].as_of.date(), date(2026, 10, 16))

    def test_mixed_session_has_no_move(self):
        yahoo, _, _ = parse_yahoo_chart(_read("yahoo_chart_mu.json"), "MU")
        nasdaq, _ = parse_nasdaq_info(_read("nasdaq_info_mu.json"), "MU")
        extended = next(item for item in nasdaq if item.kind == PrintKind.EXTENDED_HOURS)
        compared = compare_prints(yahoo[0], extended)
        self.assertEqual(compared.relation, "mixed_session")
        self.assertIsNone(compared.move)
        official = next(item for item in nasdaq if item.kind == PrintKind.OFFICIAL_CLOSE)
        same = compare_prints(yahoo[0], official)
        self.assertEqual(same.relation, "same_kind")
        self.assertEqual(same.move, Decimal("0"))

    def test_non_usd_chart_has_no_print(self):
        body = b'{"chart":{"result":[{"meta":{"currency":"TWD","regularMarketPrice":1,"regularMarketTime":1,"currentTradingPeriod":{"regular":{"start":0,"end":2}}}}]}}'
        prints, _, detail = parse_yahoo_chart(body, "2330.TW")
        self.assertEqual(prints, [])
        self.assertIn("TWD", detail)


class TestUnscaledAndYields(unittest.TestCase):
    def test_nasdaq_revenue_cell_is_not_dollars(self):
        cap = parse_nasdaq_summary_cap(_read("nasdaq_summary_mu.json"))
        self.assertIsNotNone(cap)
        payload = cap.to_json()
        self.assertEqual(payload["lexeme"], "1,031,213,058,113")
        self.assertNotIn("ones", payload)
        self.assertNotIn("number", payload)
        cells, percents = parse_nasdaq_financials(_read("nasdaq_financials_mu.json"))
        revenue = next(
            item for item in cells
            if item.label == "Total Revenue" and item.period_end == "8/28/2025"
        )
        self.assertEqual(revenue.lexeme, "$37,378,000")
        self.assertNotIn("ones", revenue.to_json())
        margin = next(
            item for item in percents
            if item.label == "Gross Margin" and item.period_end == "8/28/2025"
        )
        self.assertEqual(margin.parts_per_hundred, Decimal("39.79079"))

    def test_hurdle_uses_later_date_and_skips_blanks(self):
        fred = parse_fred_dgs10(_read("fred_dgs10.csv") + b"\n2026-10-16,.\n")
        treasury = parse_treasury_par(_read("treasury_yield.csv"))
        self.assertEqual(fred.as_of, date(2026, 10, 15))
        self.assertEqual(fred.rate, Decimal("0.0510"))
        self.assertEqual(treasury.as_of, date(2026, 10, 16))
        self.assertEqual(treasury.rate, Decimal("0.0509"))
        chosen = select_hurdle([fred, treasury])
        self.assertEqual(chosen.source, "treasury_par")
        tied = select_hurdle([
            TreasuryYield(date(2026, 10, 16), Decimal("0.05"), "fred_dgs10"),
            TreasuryYield(date(2026, 10, 16), Decimal("0.0509"), "treasury_par"),
        ])
        self.assertEqual(tied.source, "treasury_par")


class TestCompanyfacts(unittest.TestCase):
    def test_later_filing_wins_and_weighted_shares_are_not_outstanding(self):
        annual, shares = parse_companyfacts(_read("companyfacts_sample.json"))
        income = [item for item in annual if item.concept == "net_income"]
        self.assertEqual(len(income), 1)
        self.assertEqual(income[0].ones, Decimal("999"))
        self.assertEqual(income[0].start, date(2024, 8, 30))
        inventory = [item for item in annual if item.concept == "inventory"]
        self.assertEqual(len(inventory), 1)
        self.assertEqual(inventory[0].ones, Decimal("10"))
        self.assertIsNone(inventory[0].start)
        self.assertEqual(shares.shares, Decimal("1122334455"))
        self.assertEqual(shares.tag, "EntityCommonStockSharesOutstanding")

    def test_annual_frame_year_beats_the_filing_fy(self):
        body = json.dumps({
            "facts": {"us-gaap": {"NetIncomeLoss": {"units": {"USD": [
                {
                    "start": "2024-08-30",
                    "end": "2025-08-28",
                    "val": 8539000000,
                    "fy": 2026,
                    "fp": "FY",
                    "form": "10-K",
                    "filed": "2026-10-09",
                    "frame": "CY2025",
                },
                {
                    "start": "2025-08-29",
                    "end": "2026-09-03",
                    "val": 84969000000,
                    "fy": 2026,
                    "fp": "FY",
                    "form": "10-K",
                    "filed": "2026-10-09",
                    "frame": "CY2026",
                },
            ]}}}}
        }).encode()
        annual, _shares = parse_companyfacts(body)
        income = sorted(
            (item for item in annual if item.concept == "net_income"),
            key=lambda item: item.end,
        )
        self.assertEqual([item.fiscal_year for item in income], [2025, 2026])
        self.assertEqual(income[0].ones, Decimal("8539000000"))
        self.assertEqual(income[1].ones, Decimal("84969000000"))

    def test_later_filing_keeps_the_value_and_the_first_fy(self):
        body = json.dumps({
            "facts": {"us-gaap": {"NetIncomeLoss": {"units": {"USD": [
                {
                    "start": "2010-09-03",
                    "end": "2011-09-01",
                    "val": 100,
                    "fy": 2011,
                    "form": "10-K",
                    "filed": "2011-10-25",
                },
                {
                    "start": "2010-09-03",
                    "end": "2011-09-01",
                    "val": 167000000,
                    "fy": 2013,
                    "form": "10-K",
                    "filed": "2013-10-28",
                },
            ]}}}}
        }).encode()
        annual, _shares = parse_companyfacts(body)
        income = [item for item in annual if item.concept == "net_income"]
        self.assertEqual(len(income), 1)
        self.assertEqual(income[0].fiscal_year, 2011)
        self.assertEqual(income[0].ones, Decimal("167000000"))

    def test_instant_fact_keeps_the_earliest_fy(self):
        body = json.dumps({
            "facts": {"us-gaap": {"InventoryNet": {"units": {"USD": [
                {
                    "end": "2025-08-28",
                    "val": 100,
                    "fy": 2025,
                    "form": "10-K",
                    "filed": "2025-10-03",
                },
                {
                    "end": "2025-08-28",
                    "val": 8355000000,
                    "fy": 2026,
                    "form": "10-K",
                    "filed": "2026-10-09",
                    "frame": "CY2025Q3I",
                },
            ]}}}}
        }).encode()
        annual, _shares = parse_companyfacts(body)
        inventory = [item for item in annual if item.concept == "inventory"]
        self.assertEqual(len(inventory), 1)
        self.assertEqual(inventory[0].fiscal_year, 2025)
        self.assertEqual(inventory[0].ones, Decimal("8355000000"))

    def test_latest_period_end_beats_a_longer_old_tag(self):
        def row(start, end, val, filed, frame):
            return {
                "start": start,
                "end": end,
                "val": val,
                "fy": int(end[:4]),
                "form": "10-K",
                "filed": filed,
                "frame": frame,
            }

        gaap = {
            "SalesRevenueNet": {"units": {"USD": [
                row("2021-09-03", "2022-09-01", 1, "2022-10-07", "CY2022"),
                row("2022-09-02", "2023-08-31", 2, "2023-10-06", "CY2023"),
                row("2023-09-01", "2024-08-29", 3, "2024-10-04", "CY2024"),
            ]}},
            "Revenues": {"units": {"USD": [
                row("2025-08-29", "2026-09-03", 9, "2026-10-09", "CY2026"),
            ]}},
        }
        body = json.dumps({"facts": {"us-gaap": gaap}}).encode()
        annual, _shares = parse_companyfacts(body)
        revenue = [item for item in annual if item.concept == "revenue"]
        self.assertEqual(len(revenue), 1)
        self.assertEqual(revenue[0].tag, "Revenues")
        self.assertEqual(revenue[0].ones, Decimal(9))

    def test_form4_url_strips_the_xsl_directory(self):
        body = json.dumps({
            "filings": {"recent": {
                "form": ["4"],
                "filingDate": ["2026-10-15"],
                "accessionNumber": ["0001242654-26-000016"],
                "primaryDocument": ["xslF345X06/primarydocument.xml"],
                "items": [""],
            }}
        }).encode()
        found = parse_submissions(body, "0000723125")
        self.assertEqual(len(found), 1)
        self.assertNotIn("xsl", found[0].url.lower())
        self.assertTrue(found[0].url.endswith("/primarydocument.xml"))

    def test_submissions_keep_item_202_and_cap_form4(self):
        forms = ["10-K", "8-K", "8-K", "4", "4", "4", "4", "4", "4", "10-Q"]
        items = ["", "2.02", "5.02", "", "", "", "", "", "", ""]
        body = json.dumps({
            "filings": {"recent": {
                "form": forms,
                "filingDate": ["2025-10-01"] * len(forms),
                "accessionNumber": [f"0001-25-{index:06d}" for index in range(len(forms))],
                "primaryDocument": [f"doc{index}.htm" for index in range(len(forms))],
                "items": items,
            }}
        }).encode()
        found = parse_submissions(body, "0000723125")
        kept = [item.form for item in found]
        self.assertEqual(kept.count("4"), 5)
        self.assertEqual(kept.count("8-K"), 1)
        self.assertIn("10-K", kept)
        self.assertIn("10-Q", kept)

    def test_form4_transaction(self):
        xml = b"""<?xml version="1.0"?>
        <ownershipDocument>
          <reportingOwner><rptOwnerName>Ada Example</rptOwnerName></reportingOwner>
          <nonDerivativeTransaction>
            <transactionDate><value>2026-10-01</value></transactionDate>
            <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
            <transactionAmounts>
              <transactionShares><value>100</value></transactionShares>
              <transactionPricePerShare><value>10.5</value></transactionPricePerShare>
              <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
            </transactionAmounts>
          </nonDerivativeTransaction>
        </ownershipDocument>
        """
        trades = parse_form4(xml, "https://www.sec.gov/example.xml", date(2026, 10, 2))
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].owner, "Ada Example")
        self.assertEqual(trades[0].shares, Decimal("100"))
        self.assertEqual(trades[0].code, "S")

    def test_form4_splits_transaction_date_from_filing_date(self):
        xml = b"""<?xml version="1.0"?>
        <ownershipDocument>
          <reportingOwner><rptOwnerName>RAY MICHAEL CHARLES</rptOwnerName></reportingOwner>
          <nonDerivativeTransaction>
            <transactionDate><value>2026-10-14</value></transactionDate>
            <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
            <transactionAmounts>
              <transactionShares><value>40</value></transactionShares>
              <transactionPricePerShare><value>947.29</value></transactionPricePerShare>
              <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
            </transactionAmounts>
          </nonDerivativeTransaction>
        </ownershipDocument>
        """
        trades = parse_form4(xml, "https://www.sec.gov/example.xml", date(2026, 10, 15))
        self.assertEqual(trades[0].transaction_date, date(2026, 10, 14))
        self.assertEqual(trades[0].filed, date(2026, 10, 15))

    def test_derivative_only_form4_is_not_an_empty_failure(self):
        xml = b"""<?xml version="1.0"?>
        <ownershipDocument>
          <reportingOwner><rptOwnerName>Ada Example</rptOwnerName></reportingOwner>
          <derivativeTransaction>
            <transactionDate><value>2026-10-14</value></transactionDate>
            <transactionCoding><transactionCode>M</transactionCode></transactionCoding>
            <transactionAmounts>
              <transactionShares><value>10</value></transactionShares>
              <transactionPricePerShare><value>0</value></transactionPricePerShare>
              <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
            </transactionAmounts>
          </derivativeTransaction>
        </ownershipDocument>
        """

        def get(url):
            if "company_tickers.json" in url:
                return 200, json.dumps({"0": {"cik_str": 723125, "ticker": "MU", "title": "Micron"}}).encode()
            if "submissions" in url:
                body = {"filings": {"recent": {
                    "form": ["4"],
                    "filingDate": ["2026-10-15"],
                    "accessionNumber": ["0001593199-26-000005"],
                    "primaryDocument": ["primarydocument.xml"],
                    "items": [""],
                }}}
                return 200, json.dumps(body).encode()
            if url.endswith("/primarydocument.xml"):
                return 200, xml
            return 404, b""

        snap = build_snapshot("MU", get)
        self.assertEqual(len(snap.insiders), 1)
        self.assertTrue(snap.insiders[0].derivative)
        self.assertFalse(any(item.detail == "no insider rows" for item in snap.failures))


class TestValuation(unittest.TestCase):
    def test_inventory_days_uses_period_length_once(self):
        self.assertEqual(inventory_days(Decimal("10"), Decimal("2"), 4), Decimal("20"))

    def test_capex_ratio_uses_absolute_values(self):
        self.assertEqual(capex_ratio(Decimal("-15"), Decimal("5")), Decimal("3"))

    def test_through_cycle_keeps_the_latest_ten_years(self):
        rows = [(2000 + year, Decimal(year)) for year in range(1, 13)]
        cycle = through_cycle(rows)
        self.assertIsNotNone(cycle)
        self.assertEqual(cycle.fiscal_years[0], 2003)
        self.assertEqual(cycle.fiscal_years[-1], 2012)
        self.assertEqual(cycle.trough, Decimal(3))
        self.assertEqual(cycle.peak, Decimal(12))
        self.assertEqual(cycle.gaps, ())

    def test_through_cycle_window_is_calendar_years(self):
        rows = [(year, Decimal(year)) for year in range(2001, 2013) if year != 2008]
        cycle = through_cycle(rows)
        self.assertIsNotNone(cycle)
        self.assertEqual(cycle.fiscal_years[0], 2003)
        self.assertNotIn(2002, cycle.fiscal_years)
        self.assertEqual(cycle.gaps, (2008,))

    def test_through_cycle_drops_a_window_with_fewer_than_five_years(self):
        rows = [(year, Decimal(1)) for year in range(2000, 2010)]
        rows.append((2020, Decimal(9)))
        self.assertIsNone(through_cycle(rows))

    def test_through_cycle_median_is_not_the_peak(self):
        self.assertIsNone(through_cycle([(2020, Decimal("1"))] * 4))
        cycle = through_cycle([
            (2020, Decimal("1")),
            (2021, Decimal("5")),
            (2022, Decimal("3")),
            (2023, Decimal("9")),
            (2024, Decimal("7")),
        ])
        self.assertEqual(cycle.median, Decimal("5"))
        self.assertEqual(cycle.peak, Decimal("9"))
        self.assertEqual(cycle.trough, Decimal("1"))

    def test_hurdle_is_strict(self):
        self.assertTrue(clears_hurdle(Decimal("6"), Decimal("100"), Decimal("0.05")))
        self.assertFalse(clears_hurdle(Decimal("5"), Decimal("100"), Decimal("0.05")))


class TestSnapshotAndCli(unittest.TestCase):
    def _fixture_get(self, url: str):
        mapping = {
            "query1.finance.yahoo.com": _read("yahoo_chart_mu.json"),
            "api.nasdaq.com/api/quote/MU/info": _read("nasdaq_info_mu.json"),
            "api.nasdaq.com/api/quote/MU/summary": _read("nasdaq_summary_mu.json"),
            "api.nasdaq.com/api/company/MU/financials": _read("nasdaq_financials_mu.json"),
            "fred.stlouisfed.org": _read("fred_dgs10.csv"),
            "home.treasury.gov": _read("treasury_yield.csv"),
        }
        for key, body in mapping.items():
            if key in url:
                return 200, body
        if "sec.gov" in url:
            return 403, b"<title>SEC.gov | Request Rate Threshold Exceeded</title>"
        return 404, b""

    def test_sec_403_keeps_prints_and_writes_no_filing(self):
        snap = build_snapshot("MU", self._fixture_get)
        self.assertEqual(snap.filings, ())
        self.assertIsNone(snap.shares)
        self.assertEqual(snap.annual, ())
        self.assertTrue(any(item.kind == PrintKind.OFFICIAL_CLOSE for item in snap.prints))
        self.assertTrue(any(item.source == "treasury_par" for item in snap.yields))
        self.assertTrue(any(item.source == "sec_company_tickers" and item.status == 403 for item in snap.failures))
        names = {item.label: item.value for item in snap.labels}
        self.assertEqual(names["company_name"], "Micron Technology, Inc. Common Stock")
        self.assertEqual(names["industry"], "Semiconductors")
        encoded = snap.to_json()
        self.assertTrue(all("ones" not in item and "number" not in item for item in encoded["unscaled"]))

    def test_empty_form4_and_missing_nasdaq_print_are_failures(self):
        def get(url):
            if "company_tickers.json" in url:
                return 200, json.dumps({"0": {"cik_str": 723125, "ticker": "MU", "title": "Micron"}}).encode()
            if "submissions" in url:
                body = {
                    "filings": {"recent": {
                        "form": ["4"],
                        "filingDate": ["2026-10-15"],
                        "accessionNumber": ["0001242654-26-000016"],
                        "primaryDocument": ["xslF345X06/primarydocument.xml"],
                        "items": [""],
                    }}
                }
                return 200, json.dumps(body).encode()
            if url.endswith("/primarydocument.xml"):
                return 200, b"<ownershipDocument></ownershipDocument>"
            if "/quote/MU/info" in url:
                return 200, json.dumps({"data": {"marketStatus": "Closed", "primaryData": {}}}).encode()
            return 404, b""

        snap = build_snapshot("MU", get)
        self.assertEqual(snap.insiders, ())
        self.assertTrue(all("xsl" not in item.url.lower() for item in snap.filings))
        self.assertTrue(any(item.source == "sec_form4" and item.detail == "no insider rows" for item in snap.failures))
        self.assertTrue(any(item.source == "nasdaq_info" and item.detail == "no print" for item in snap.failures))

    def test_stale_get_is_recorded(self):
        class Result(tuple):
            def __new__(cls):
                obj = tuple.__new__(cls, (404, b""))
                obj.stale_age = 100
                return obj

        snap = build_snapshot("MU", lambda url: Result())
        self.assertTrue(any(
            item.source == "stale_cache" and item.detail == "age_seconds=100"
            for item in snap.failures
        ))

    def test_html_error_page_without_cache_names_the_title(self):
        page = b"<html><title>Nasdaq | Access Denied</title><body>blocked</body></html>"

        def get(url):
            if "/quote/MU/info" in url:
                return 200, page
            return 404, b""

        snap = build_snapshot("MU", get)
        self.assertTrue(any(
            item.status == 200 and item.detail == "html error page: Nasdaq | Access Denied"
            for item in snap.failures
        ))
        self.assertFalse(any(item.detail == "no print" for item in snap.failures))

    def test_fresh_cache_hit_is_recorded_on_the_snapshot(self):
        class Result(tuple):
            def __new__(cls):
                obj = tuple.__new__(cls, (404, b""))
                obj.cached_at = 1700000000
                obj.cache_age = 12
                return obj

        snap = build_snapshot("MU", lambda url: Result())
        self.assertTrue(snap.cache)
        self.assertEqual(snap.cache[0].cached_at, "1700000000")
        self.assertEqual(snap.cache[0].age_seconds, "12")

    def test_foreign_20f_market_cap_needs_an_adr_ratio(self):
        chart = json.dumps({"chart": {"result": [{
            "meta": {
                "currency": "USD",
                "regularMarketPrice": 100,
                "regularMarketTime": 1700000000,
                "currentTradingPeriod": {"regular": {"start": 1700003600, "end": 1700020000}},
            },
        }]}}).encode()
        facts = json.dumps({"facts": {
            "ifrs-full": {"Revenue": {"units": {"TWD": [{
                "val": 9, "start": "2025-01-01", "end": "2025-12-31",
                "form": "20-F", "filed": "2026-04-01", "fy": 2025,
            }]}}},
            "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [{
                "val": 5000, "end": "2026-02-28", "form": "20-F", "filed": "2026-04-01",
            }]}}},
        }}).encode()
        submissions = json.dumps({"filings": {"recent": {
            "form": ["20-F"],
            "filingDate": ["2026-04-01"],
            "accessionNumber": ["0001046179-26-000001"],
            "primaryDocument": ["tsm-20f.htm"],
            "items": [""],
        }}}).encode()
        tickers = json.dumps({"0": {"cik_str": 1046179, "ticker": "TSM", "title": "TSMC"}}).encode()

        def get(url):
            if "query1.finance.yahoo.com" in url:
                return 200, chart
            if "company_tickers.json" in url:
                return 200, tickers
            if "submissions" in url:
                return 200, submissions
            if "companyfacts" in url:
                return 200, facts
            return 404, b""

        snap = build_snapshot("TSM", get)
        text = us_market.render_analysis(snap)
        self.assertIn("market_cap: unavailable", text)
        self.assertNotIn("market_cap: usd=500000", text)
        self.assertTrue(any("ordinary-shares-per-adr" in item.detail for item in snap.failures))
        self.assertTrue(any(item.detail == "gaap rows unavailable: ifrs or non-usd" for item in snap.failures))
        self.assertEqual(snap.annual, ())
        scaled = build_snapshot("TSM", get, adr_ratio=Decimal("5"))
        scaled_text = us_market.render_analysis(scaled)
        self.assertIn("market_cap: usd=100000", scaled_text)
        self.assertFalse(any("ordinary-shares-per-adr" in item.detail for item in scaled.failures))

    def _adr_chart(self):
        return json.dumps({"chart": {"result": [{
            "meta": {
                "currency": "USD",
                "regularMarketPrice": 100,
                "regularMarketTime": 1700000000,
                "currentTradingPeriod": {"regular": {"start": 1700003600, "end": 1700020000}},
            },
        }]}}).encode()

    def test_unknown_filing_type_does_not_price_ordinary_shares(self):
        shares = 227900788800
        facts = {
            "facts": {
                "us-gaap": {"NetIncomeLoss": {"units": {"USD": []}}},
                "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [{
                    "val": shares, "end": "2026-06-30", "form": "20-F", "filed": "2026-04-16",
                }]}}},
            }
        }
        for year, amount in ((2021, 1), (2022, 2), (2023, 3), (2024, 4), (2025, 5)):
            facts["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"].append({
                "val": amount,
                "start": f"{year - 1}-01-01",
                "end": f"{year - 1}-12-31",
                "form": "20-F",
                "filed": f"{year}-04-01",
                "fy": year - 1,
                "frame": f"CY{year - 1}",
            })
        fred = b"observation_date,DGS10\n2026-10-16,4.00\n"
        tickers = json.dumps({"0": {"cik_str": 1046179, "ticker": "TSM", "title": "TSMC"}}).encode()

        def get(url):
            if "query1.finance.yahoo.com" in url:
                return 200, self._adr_chart()
            if "company_tickers.json" in url:
                return 200, tickers
            if "submissions" in url:
                return 403, b"<title>SEC.gov | Request Rate Threshold Exceeded</title>"
            if "companyfacts" in url:
                return 200, json.dumps(facts).encode()
            if "fred.stlouisfed.org" in url:
                return 200, fred
            return 404, b""

        bare = us_market.render_analysis(build_snapshot("TSM", get))
        self.assertIn("market_cap: unavailable", bare)
        self.assertIn("hurdle_check: unavailable", bare)
        self.assertNotIn("22790078880000", bare)
        self.assertTrue(any("filing type unknown" in item.detail for item in build_snapshot("TSM", get).failures))
        scaled = us_market.render_analysis(build_snapshot("TSM", get, adr_ratio=Decimal("5")))
        self.assertIn("market_cap: usd=4558015776000", scaled)
        self.assertIn("adr_ratio=5", scaled)
        self.assertIn("hurdle_check:", scaled)
        self.assertNotIn("hurdle_check: unavailable", scaled)

    def test_ifrs_notice_is_a_foreign_filer_signal(self):
        facts = json.dumps({"facts": {
            "ifrs-full": {"Revenue": {"units": {"EUR": [{
                "val": 9, "start": "2025-01-01", "end": "2025-12-31",
                "form": "20-F", "filed": "2026-04-01", "fy": 2025,
            }]}}},
            "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [{
                "val": 5000, "end": "2026-02-28", "form": "20-F", "filed": "2026-04-01",
            }]}}},
        }}).encode()
        submissions = json.dumps({"filings": {"recent": {
            "form": ["10-K"],
            "filingDate": ["2026-04-01"],
            "accessionNumber": ["0001046179-26-000001"],
            "primaryDocument": ["annual.htm"],
            "items": [""],
        }}}).encode()
        tickers = json.dumps({"0": {"cik_str": 1046179, "ticker": "TSM", "title": "TSMC"}}).encode()

        def get(url):
            if "query1.finance.yahoo.com" in url:
                return 200, self._adr_chart()
            if "company_tickers.json" in url:
                return 200, tickers
            if "submissions" in url:
                return 200, submissions
            if "companyfacts" in url:
                return 200, facts
            return 404, b""

        snap = build_snapshot("TSM", get)
        text = us_market.render_analysis(snap)
        self.assertIn("market_cap: unavailable", text)
        self.assertNotIn("market_cap: usd=500000", text)
        self.assertTrue(any(item.detail == "gaap rows unavailable: ifrs or non-usd" for item in snap.failures))
        scaled = us_market.render_analysis(build_snapshot("TSM", get, adr_ratio=Decimal("5")))
        self.assertIn("market_cap: usd=100000", scaled)

    def test_adr_ratio_must_be_finite_and_positive(self):
        Path("/tmp/adr-ratio-rejected.json").unlink(missing_ok=True)
        os.environ["SEC_USER_AGENT"] = "Ada Lovelace ada@research.test"
        try:
            for raw in ("NaN", "sNaN", "Infinity", "-Infinity", "0", "-1"):
                err = io.StringIO()
                old = sys.stderr
                sys.stderr = err
                try:
                    code = us_market.main(
                        ["snapshot", "MU", "--out", "/tmp/adr-ratio-rejected.json", f"--adr-ratio={raw}"],
                        get=lambda url: (_ for _ in ()).throw(AssertionError(url)),
                    )
                except Exception as exc:
                    self.fail(f"{raw} raised {type(exc).__name__}: {exc}")
                finally:
                    sys.stderr = old
                self.assertEqual(code, 2, raw)
                self.assertIn("adr ratio rejected", err.getvalue(), raw)
                self.assertFalse(Path("/tmp/adr-ratio-rejected.json").exists(), raw)
        finally:
            os.environ.pop("SEC_USER_AGENT", None)

    def test_snapshot_exits_before_fetch_when_agent_missing(self):
        calls = []

        def boom(url):
            calls.append(url)
            raise AssertionError(url)

        os.environ.pop("SEC_USER_AGENT", None)
        os.environ["SEC_USER_AGENT_FILE"] = "/tmp/does-not-exist-sec-ua.txt"
        old_err = sys.stderr
        sys.stderr = io.StringIO()
        try:
            code = us_market.main(
                ["snapshot", "MU", "--out", "/tmp/does-not-write-us-snapshot.json"],
                get=boom,
            )
        finally:
            sys.stderr = old_err
            os.environ.pop("SEC_USER_AGENT_FILE", None)
        self.assertEqual(code, 2)
        self.assertEqual(calls, [])

    def test_snapshot_exit_zero_when_sec_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "snap.json")
            old = sys.stdout
            sys.stdout = io.StringIO()
            os.environ["SEC_USER_AGENT"] = "Ada Lovelace ada@research.test"
            try:
                code = us_market.main(["snapshot", "MU", "--out", path], get=self._fixture_get)
            finally:
                sys.stdout = old
                os.environ.pop("SEC_USER_AGENT", None)
            self.assertEqual(code, 0)
            saved = json.loads(Path(path).read_text())
            self.assertEqual(saved["filings"], [])
            self.assertTrue(saved["prints"])
            sibling = list(Path(directory).glob(".us-snapshot-*"))
            self.assertEqual(sibling, [])

    def test_quote_prints_kind_and_rejects_bad_tickers(self):
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            code = us_market.main(["quote", "MU"], get=self._fixture_get)
        finally:
            sys.stdout = old
        self.assertEqual(code, 0)
        text = buf.getvalue()
        self.assertIn("kind=official_close", text)
        self.assertIn("kind=extended_hours", text)
        self.assertIn("price=878.84", text)
        self.assertIn("relation=mixed_session", text)
        self.assertIn("move=none", text)
        self.assertNotIn("1029", text)
        calls = []

        def boom(url):
            calls.append(url)
            raise AssertionError(url)

        sys.stdout = io.StringIO()
        try:
            self.assertEqual(us_market.main(["quote", "MU;rm"], get=boom), 2)
            self.assertEqual(calls, [])
            seen = []

            def missing(url):
                seen.append(url)
                return 404, b""

            self.assertEqual(us_market.main(["quote", "005930.KS"], get=missing), 2)
            self.assertEqual(us_market.main(["quote", "BRK-B"], get=missing), 2)
            self.assertTrue(seen)
        finally:
            sys.stdout = old

    def test_analyze_unavailable_without_gaap(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "snap.json")
            old = sys.stdout
            sys.stdout = io.StringIO()
            os.environ["SEC_USER_AGENT"] = "Ada Lovelace ada@research.test"
            try:
                us_market.main(["snapshot", "MU", "--out", path], get=self._fixture_get)
            finally:
                sys.stdout = old
                os.environ.pop("SEC_USER_AGENT", None)
            proc = subprocess.run(
                [sys.executable, str(_TOOLS / "us_market.py"), "analyze", "--snapshot", path],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("gaap: unavailable", proc.stdout)
        self.assertIn("shares: unavailable", proc.stdout)
        self.assertIn("market_cap: unavailable", proc.stdout)
        self.assertIn("through_cycle: unavailable", proc.stdout)
        self.assertIn("inventory_days: unavailable", proc.stdout)
        self.assertIn("unscaled_note: not dollars", proc.stdout)
        self.assertIn("hurdle: rate=0.0509", proc.stdout)
        self.assertIn("parts_per_hundred=39.79079", proc.stdout)
        self.assertNotIn("non-GAAP", proc.stdout)
        self.assertNotIn("1,031,213,058,113 USD", proc.stdout)

    def test_analyze_uses_median_and_raw_shares(self):
        facts = []
        for year, amount in ((2020, "1"), (2021, "9"), (2022, "3"), (2023, "5"), (2024, "7")):
            facts.append(AnnualFact(year, date(year, 8, 31), "net_income", Decimal(amount), date(year, 10, 1), "NetIncomeLoss"))
        close = MarketPrint(
            "MU",
            Decimal("10"),
            PrintKind.OFFICIAL_CLOSE,
            datetime(2026, 10, 16, 20, 0, tzinfo=timezone.utc),
            "yahoo_chart",
        )
        snap = _empty_snap(
            prints=(close,),
            annual=tuple(facts),
            shares=ShareCount(Decimal("100"), date(2026, 8, 28), "EntityCommonStockSharesOutstanding"),
            yields=(TreasuryYield(date(2026, 10, 16), Decimal("0.04"), "treasury_par"),),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "snap.json")
            us_market.write_snapshot(path, snap)
            proc = subprocess.run(
                [sys.executable, str(_TOOLS / "us_market.py"), "analyze", "--snapshot", path],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("through_cycle: median=5 peak=9 trough=1", proc.stdout)
        self.assertIn("market_cap: usd=1000", proc.stdout)
        self.assertIn("hurdle_check: earnings_yield=0.005 rate=0.04 clears=no", proc.stdout)

    def test_analyze_rejects_a_non_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "nope.json")
            Path(path).write_text('{"type":"nope"}\n')
            proc = subprocess.run(
                [sys.executable, str(_TOOLS / "us_market.py"), "analyze", "--snapshot", path],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(proc.returncode, 1)

    def test_http_error_returns_status(self):
        class Broken(urllib.error.HTTPError):
            def __init__(self):
                super().__init__("https://www.sec.gov/x", 403, "no", {}, io.BytesIO(b"blocked"))

        original = urllib.request.urlopen
        urllib.request.urlopen = lambda *args, **kwargs: (_ for _ in ()).throw(Broken())
        try:
            status, body = http_get(
                "https://www.sec.gov/x",
                "tester",
                sleep=lambda _delay: None,
                attempts=3,
            )
        finally:
            urllib.request.urlopen = original
        self.assertEqual(status, 403)
        self.assertIn(b"blocked", body)


class TestSecClient(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("SEC_USER_AGENT", None)

    def test_missing_or_noreply_agent_is_rejected(self):
        from usmarket.fetch import SecConfigError, sec_user_agent

        os.environ.pop("SEC_USER_AGENT", None)
        with self.assertRaises(SecConfigError):
            sec_user_agent(path="/tmp/does-not-exist-sec-ua.txt")
        os.environ["SEC_USER_AGENT"] = "AI Berkshire someone@users.noreply.github.com"
        with self.assertRaises(SecConfigError):
            sec_user_agent(path="/tmp/does-not-exist-sec-ua.txt")
        os.environ["SEC_USER_AGENT"] = "not-an-email"
        with self.assertRaises(SecConfigError):
            sec_user_agent(path="/tmp/does-not-exist-sec-ua.txt")

    def test_placeholder_and_reserved_domains_are_rejected(self):
        from usmarket.fetch import valid_sec_user_agent

        self.assertFalse(valid_sec_user_agent("Your Name you@example.com"))
        self.assertFalse(valid_sec_user_agent("Ada Lovelace ada@example.com"))
        self.assertFalse(valid_sec_user_agent("Ada Lovelace ada@example.org"))
        self.assertFalse(valid_sec_user_agent("Ada Lovelace ada@example.net"))
        self.assertFalse(valid_sec_user_agent("Ada Lovelace ada@mail.example.com"))
        self.assertTrue(valid_sec_user_agent("Ada Lovelace ada@research.test"))

    def test_declared_headers_retry_gzip_and_cache(self):
        import gzip

        from usmarket.fetch import http_get

        calls = []
        delays = []

        class Response:
            def __init__(self, status, body, headers):
                self.status = status
                self._body = body
                self.headers = headers

            def read(self):
                return self._body

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        payload = b'{"ok":true}'
        packed = gzip.compress(payload)

        def opener(request, timeout):
            calls.append(request)
            if len(calls) < 3:
                raise urllib.error.HTTPError(
                    request.full_url, 403, "no", {}, io.BytesIO(b"no")
                )
            return Response(200, packed, {"Content-Encoding": "gzip"})

        with tempfile.TemporaryDirectory() as directory:
            status, body = http_get(
                "https://www.sec.gov/files/company_tickers.json",
                "Your Name you@example.com",
                opener=opener,
                sleep=delays.append,
                cache_dir=directory,
                attempts=3,
            )
            self.assertEqual(status, 200)
            self.assertEqual(body, payload)
            self.assertEqual(len(calls), 3)
            self.assertEqual(calls[0].get_header("User-agent"), "Your Name you@example.com")
            self.assertIn("gzip", calls[0].get_header("Accept-encoding"))
            self.assertTrue(delays)
            status, body = http_get(
                "https://www.sec.gov/files/company_tickers.json",
                "Your Name you@example.com",
                opener=opener,
                sleep=delays.append,
                cache_dir=directory,
                attempts=3,
            )
        self.assertEqual(status, 200)
        self.assertEqual(body, payload)
        self.assertEqual(len(calls), 3)

    def test_fresh_cache_exposes_cached_at_and_age(self):
        import base64

        from usmarket.fetch import _cache_path, http_get

        url = "https://www.sec.gov/files/company_tickers.json"
        with tempfile.TemporaryDirectory() as directory:
            path = _cache_path(directory, url)
            os.makedirs(directory, exist_ok=True)
            payload = {"status": 200, "saved": 1000, "body": base64.b64encode(b"{}").decode("ascii")}
            Path(path).write_text(json.dumps(payload), encoding="utf-8")
            result = http_get(url, "Ada Lovelace ada@research.test", opener=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("live fetch")), cache_dir=directory, now=lambda: 1030)
        self.assertEqual(result.cached_at, 1000)
        self.assertEqual(result.cache_age, 30)

    def test_live_get_sends_declared_agent_to_sec_and_fred(self):
        seen = []

        def capture(url, agent, timeout=40, opener=None, sleep=None, cache_dir=None, attempts=3, now=None):
            seen.append((url, agent, cache_dir))
            return 200, b"{}"

        os.environ["SEC_USER_AGENT"] = "Ada Lovelace ada@research.test"
        original = us_market.http_get
        us_market.http_get = capture
        try:
            us_market.live_get("https://www.sec.gov/files/company_tickers.json")
            us_market.live_get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10")
            us_market.live_get("https://api.nasdaq.com/api/quote/MU/info?assetclass=stocks")
            us_market.live_get("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/x")
        finally:
            us_market.http_get = original
        declared = "Ada Lovelace ada@research.test"
        self.assertEqual(seen[0][1], declared)
        self.assertEqual(seen[1][1], declared)
        self.assertIn("Chrome", seen[2][1])
        self.assertIn("Chrome", seen[3][1])
        self.assertTrue(seen[0][2])
        self.assertTrue(seen[1][2])
        self.assertIsNone(seen[2][2])
        self.assertTrue(seen[3][2])

    def test_stale_cache_is_logged_when_retries_fail(self):
        import base64

        from usmarket.fetch import _cache_path, http_get

        url = "https://www.sec.gov/files/company_tickers.json"
        with tempfile.TemporaryDirectory() as directory:
            path = _cache_path(directory, url)
            payload = {
                "status": 200,
                "saved": 0,
                "body": base64.b64encode(b"cached-body").decode("ascii"),
            }
            Path(path).write_text(json.dumps(payload), encoding="utf-8")

            def opener(request, timeout):
                raise urllib.error.HTTPError(
                    request.full_url, 503, "no", {}, io.BytesIO(b"down")
                )

            err = io.StringIO()
            old = sys.stderr
            sys.stderr = err
            try:
                status, body = http_get(
                    url,
                    "Your Name you@example.com",
                    opener=opener,
                    sleep=lambda _delay: None,
                    cache_dir=directory,
                    attempts=3,
                    now=lambda: 100000,
                )
            finally:
                sys.stderr = old
        self.assertEqual((status, body), (200, b"cached-body"))
        self.assertIn(f"using cached response after fetch failed: {url}", err.getvalue())

    def test_html_error_page_is_not_cached(self):
        from usmarket.fetch import http_get

        calls = []

        class Response:
            status = 200
            headers = {}

            def read(self):
                return b"<html><title>SEC.gov | Request Rate Threshold Exceeded</title></html>"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def opener(request, timeout):
            calls.append(request.full_url)
            return Response()

        with tempfile.TemporaryDirectory() as directory:
            http_get(
                "https://www.sec.gov/files/company_tickers.json",
                "Your Name you@example.com",
                opener=opener,
                sleep=lambda _delay: None,
                cache_dir=directory,
                attempts=1,
            )
            http_get(
                "https://www.sec.gov/files/company_tickers.json",
                "Your Name you@example.com",
                opener=opener,
                sleep=lambda _delay: None,
                cache_dir=directory,
                attempts=1,
            )
        self.assertEqual(len(calls), 2)

    def test_stale_cache_older_than_a_week_is_dropped(self):
        import base64

        from usmarket.fetch import _cache_path, http_get

        url = "https://www.sec.gov/files/company_tickers.json"
        with tempfile.TemporaryDirectory() as directory:
            path = _cache_path(directory, url)
            payload = {
                "status": 200,
                "saved": 0,
                "body": base64.b64encode(b"cached-body").decode("ascii"),
            }
            Path(path).write_text(json.dumps(payload), encoding="utf-8")

            def opener(request, timeout):
                raise urllib.error.HTTPError(
                    request.full_url, 503, "no", {}, io.BytesIO(b"down")
                )

            status, body = http_get(
                url,
                "Your Name you@example.com",
                opener=opener,
                sleep=lambda _delay: None,
                cache_dir=directory,
                attempts=1,
                now=lambda: 8 * 24 * 60 * 60,
            )
        self.assertEqual(status, 503)
        self.assertNotEqual(body, b"cached-body")

    def test_recent_stale_cache_is_flagged(self):
        import base64

        from usmarket.fetch import _cache_path, http_get

        url = "https://www.sec.gov/files/company_tickers.json"
        with tempfile.TemporaryDirectory() as directory:
            path = _cache_path(directory, url)
            payload = {
                "status": 200,
                "saved": 0,
                "body": base64.b64encode(b"cached-body").decode("ascii"),
            }
            Path(path).write_text(json.dumps(payload), encoding="utf-8")

            def opener(request, timeout):
                raise urllib.error.HTTPError(
                    request.full_url, 503, "no", {}, io.BytesIO(b"down")
                )

            result = http_get(
                url,
                "Your Name you@example.com",
                opener=opener,
                sleep=lambda _delay: None,
                cache_dir=directory,
                attempts=1,
                now=lambda: 2 * 24 * 60 * 60,
            )
        self.assertEqual(result[0], 200)
        self.assertEqual(result[1], b"cached-body")
        self.assertGreater(result.stale_age, 0)

    def test_incomplete_read_is_retried(self):
        import http.client

        from usmarket.fetch import http_get

        calls = []

        class Response:
            status = 200
            headers = {}

            def read(self):
                return b"{}"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def opener(request, timeout):
            calls.append(request.full_url)
            if len(calls) == 1:
                raise http.client.IncompleteRead(b"partial")
            return Response()

        status, body = http_get(
            "https://data.sec.gov/example.json",
            "Your Name you@example.com",
            opener=opener,
            sleep=lambda _delay: None,
            attempts=3,
        )
        self.assertEqual(status, 200)
        self.assertEqual(body, b"{}")
        self.assertEqual(len(calls), 2)


class TestMicronReport(unittest.TestCase):
    def test_every_number_is_in_the_snapshot(self):
        snapshot_path = _ROOT / "reports" / "Micron" / "evidence" / "us-snapshot-MU.json"
        self.assertTrue(snapshot_path.exists(), snapshot_path)
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        tokens = []

        def walk(node):
            if isinstance(node, dict):
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)
            elif isinstance(node, str):
                tokens.append(node)
            elif isinstance(node, (int, float)):
                tokens.append(str(node))

        walk(payload)
        snap = snapshot_from_json(payload)
        derived_lines = [
            line for line in us_market.render_analysis(snap).splitlines()
            if line.startswith((
                "market_cap:",
                "through_cycle:",
                "hurdle_check:",
                "sbc:",
                "inventory_days:",
                "capex_ratio:",
            ))
        ]
        for line in derived_lines:
            tokens.extend(re.findall(r"-?\d+(?:,\d{3})*(?:\.\d+)?", line))

        def whole_numbers(token: str) -> set[str]:
            cleaned = token.strip().replace("$", "").replace("%", "")
            if not re.fullmatch(r"-?\d+(?:,\d{3})*(?:\.\d+)?", cleaned):
                return set()
            value = cleaned.replace(",", "")
            found = {value}
            try:
                found.add(format(Decimal(value), "f"))
            except Exception:
                return found
            return found

        allowed = set()
        dates = set()
        for token in tokens:
            allowed.update(whole_numbers(token))
            dates.update(re.findall(
                r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\+\d{2}:\d{2}|Z))?",
                token,
            ))
            dates.update(re.findall(r"\d{1,2}/\d{1,2}/\d{4}", token))

        number_re = re.compile(r"(?<![\d.])-?\d+(?:,\d{3})*(?:\.\d+)?")
        self.assertNotIn("723125", allowed)
        for path in sorted((_ROOT / "reports" / "Micron").glob("*.md")):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("—", text, path)
            file_dates = set(dates)
            cutoff = re.search(r"(?m)^date:\s*(\d{4}-\d{2}-\d{2})\s*$", text)
            if cutoff:
                file_dates.add(cutoff.group(1))
            for line in text.splitlines():
                visible = re.sub(r"`[^`]+`", " ", line)
                visible = re.sub(r"[\w./-]+\.md", " ", visible)
                present = set()
                for stamp in file_dates:
                    if stamp in line:
                        for part in re.split(r"[-/T:+]", stamp):
                            if part.isdigit():
                                present.add(part)
                                present.add(str(int(part)))
                for match in number_re.finditer(visible):
                    raw = match.group(0)
                    cleaned = raw.replace(",", "")
                    if "." not in cleaned and cleaned in present:
                        continue
                    try:
                        as_dec = format(Decimal(cleaned), "f")
                    except Exception:
                        self.fail(f"{path}:{raw}")
                    if cleaned in allowed or as_dec in allowed:
                        continue
                    self.fail(f"{path.name} cites {raw} which is not in the snapshot: {line}")


class TestCommandDocs(unittest.TestCase):
    def test_domestic_commands_match_and_skills_do_not_paste_flags(self):
        files = [
            _ROOT / "README.md",
            _ROOT / "README_EN.md",
            _ROOT / "skills" / "financial-data.md",
        ]
        for path in files:
            found = [
                line.strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip().startswith("python3 tools/us_market.py")
            ]
            self.assertEqual(found, _COMMANDS, path)
        skill_dir = _ROOT / "skills"
        for path in skill_dir.glob("*.md"):
            if path.name == "financial-data.md":
                continue
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("python3 tools/us_market.py", text, path)

    def test_english_is_opt_in_and_20f_is_covered(self):
        team = (_ROOT / "skills" / "investment-team.md").read_text(encoding="utf-8")
        checklist = (_ROOT / "skills" / "investment-checklist.md").read_text(encoding="utf-8")
        data = (_ROOT / "skills" / "financial-data.md").read_text(encoding="utf-8")
        for text in (team, checklist):
            self.assertIn("lang=en", text)
            self.assertNotIn("改用 `skills/investment-team-en.md`", text)
        self.assertIn("20-F", data)
        self.assertIn("40-F", data)


class TestAgentFileUntouched(unittest.TestCase):
    def test_repo_agent_file_bytes_match_the_start_of_the_suite(self):
        after = _AGENT_PATH.read_bytes() if _AGENT_PATH.exists() else None
        mtime = _AGENT_PATH.stat().st_mtime_ns if _AGENT_PATH.exists() else None
        self.assertEqual(after, _AGENT_BYTES)
        self.assertEqual(mtime, _AGENT_MTIME)


def tearDownModule():
    if _AGENT_BYTES is None:
        if _AGENT_PATH.exists():
            _AGENT_PATH.unlink()
        return
    current = _AGENT_PATH.read_bytes() if _AGENT_PATH.exists() else None
    mtime = _AGENT_PATH.stat().st_mtime_ns if _AGENT_PATH.exists() else None
    if current == _AGENT_BYTES and mtime == _AGENT_MTIME:
        return
    _AGENT_PATH.parent.mkdir(exist_ok=True)
    _AGENT_PATH.write_bytes(_AGENT_BYTES)
    os.utime(_AGENT_PATH, ns=(_AGENT_MTIME, _AGENT_MTIME))


if __name__ == "__main__":
    unittest.main()
