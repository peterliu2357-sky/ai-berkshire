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


class TestValuation(unittest.TestCase):
    def test_inventory_days_uses_period_length_once(self):
        self.assertEqual(inventory_days(Decimal("10"), Decimal("2"), 4), Decimal("20"))

    def test_capex_ratio_uses_absolute_values(self):
        self.assertEqual(capex_ratio(Decimal("-15"), Decimal("5")), Decimal("3"))

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

    def test_snapshot_exit_zero_when_sec_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "snap.json")
            old = sys.stdout
            sys.stdout = io.StringIO()
            try:
                code = us_market.main(["snapshot", "MU", "--out", path], get=self._fixture_get)
            finally:
                sys.stdout = old
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
            try:
                us_market.main(["snapshot", "MU", "--out", path], get=self._fixture_get)
            finally:
                sys.stdout = old
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
            status, body = http_get("https://www.sec.gov/x", "tester")
        finally:
            urllib.request.urlopen = original
        self.assertEqual(status, 403)
        self.assertIn(b"blocked", body)


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
        lexemes = [item["lexeme"] for item in payload["unscaled"]]
        date_parts = set()
        for token in tokens:
            for part in token.replace("T", "-").replace(":", "-").replace("+", "-").replace("/", "-").split("-"):
                if part.isdigit():
                    date_parts.add(part)
                    date_parts.add(str(int(part)))
        allowed = set()
        for token in tokens:
            cleaned = token.replace(",", "").replace("%", "").replace("$", "")
            allowed.add(cleaned)
            try:
                allowed.add(format(Decimal(cleaned), "f"))
            except Exception:
                continue

        number_re = re.compile(r"(?<![\d.])-?\d+(?:,\d{3})*(?:\.\d+)?")
        for path in sorted((_ROOT / "reports" / "Micron").glob("*.md")):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("—", text, path)
            for line in text.splitlines():
                visible = re.sub(r"`[^`]+`", " ", line)
                visible = re.sub(r"[\w./-]+\.md", " ", visible)
                for match in number_re.finditer(visible):
                    raw = match.group(0)
                    cleaned = raw.replace(",", "")
                    if cleaned in date_parts or str(int(cleaned.split(".")[0])) in date_parts and "." not in cleaned:
                        continue
                    try:
                        as_dec = format(Decimal(cleaned), "f")
                    except Exception:
                        self.fail(f"{path}:{raw}")
                    if cleaned in allowed or as_dec in allowed:
                        continue
                    if any(raw in lex or cleaned in lex.replace(",", "") for lex in lexemes if lex in line or lex.replace(",", "") in line.replace(",", "")):
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


if __name__ == "__main__":
    unittest.main()
