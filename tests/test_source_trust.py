#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "tools"))

import source_ledger  # noqa: E402
from financial_rigor import scenario_target_price  # noqa: E402
from us_market import render_analysis  # noqa: E402
from usmarket.claims import (  # noqa: E402
    AuditResult,
    Cited,
    CitedUnit,
    ClaimId,
    DeriveTool,
    Dispute,
    IrrRequest,
    Measure,
    PeerSnapshot,
    Scored,
    SourceLedger,
    ThreeScenario,
    Tier,
    admit,
    audit_report,
    build_parser,
    citation_lines,
    derive,
    load_ledger,
    snapshot_allow_list,
    tier_of_host,
    unexcused_numbers,
    visible_text,
    write_ledger,
)
from usmarket.types import (  # noqa: E402
    AnnualFact,
    FetchFailure,
    FilingRef,
    InsiderTrade,
    IssuerSnapshot,
    MarketPrint,
    PrintKind,
    ShareCount,
    SourceLabel,
    snapshot_from_json,
)


def _mu(**overrides) -> IssuerSnapshot:
    base = dict(
        ticker="MU",
        prints=(
            MarketPrint(
                "MU",
                Decimal("100"),
                PrintKind.OFFICIAL_CLOSE,
                datetime(2026, 10, 17, 20, 0, tzinfo=timezone.utc),
                "nasdaq_quote",
            ),
        ),
        filings=(
            FilingRef(
                "10-K",
                date(2026, 10, 1),
                "0000723125-26-000099",
                "https://www.sec.gov/Archives/edgar/data/723125/mu.htm",
            ),
        ),
        annual=(
            AnnualFact(
                2026,
                date(2026, 8, 28),
                "net_income",
                Decimal("1000"),
                date(2026, 10, 1),
                "NetIncomeLoss",
            ),
        ),
        shares=ShareCount(Decimal("100"), date(2026, 8, 28), "EntityCommonStockSharesOutstanding"),
        yields=(),
        unscaled=(),
        percents=(),
        ranges=(),
        labels=(),
        insiders=(),
        failures=(),
    )
    base.update(overrides)
    return IssuerSnapshot(**base)


def _cited(claim_id: str, measure: str, value: str, unit: CitedUnit, url: str) -> Cited:
    return Cited(
        ClaimId(claim_id),
        Measure(measure),
        Decimal(value),
        unit,
        url,
        date(2026, 3, 18),
        None,
        (),
        "",
    )


def _option_strings(parser: argparse.ArgumentParser) -> set[str]:
    found: set[str] = set()
    for action in parser._actions:
        found.update(action.option_strings)
        if isinstance(action, argparse._SubParsersAction):
            for child in action.choices.values():
                found.update(_option_strings(child))
    return found


class TestHostTiers(unittest.TestCase):
    def test_trendforce_host_is_secondary(self):
        self.assertEqual(
            tier_of_host("https://www.trendforce.com/example/ddr5"),
            (Tier.SECONDARY, "TrendForce"),
        )
        self.assertEqual(tier_of_host("https://spot.trendforce.com/ddr5")[0], Tier.LOW)
        claim = _cited(
            "dram-ddr5-tf",
            "dram_spot_ddr5",
            "5.15",
            CitedUnit.USD_PER_GB,
            "https://www.trendforce.com/example/ddr5",
        )
        line = citation_lines(_mu(), SourceLedger("MU", (claim,)), {}, {})[claim.id][0]
        self.assertEqual(
            line,
            "{5.15}[c:dram-ddr5-tf https://www.trendforce.com/example/ddr5 "
            "TrendForce published=2026-03-18 measure=dram_spot_ddr5 secondary]",
        )

    def test_gartner_and_idc_are_secondary(self):
        self.assertEqual(tier_of_host("https://www.gartner.com/doc/1"), (Tier.SECONDARY, "Gartner"))
        self.assertEqual(tier_of_host("https://www.idc.com/getdoc.jsp"), (Tier.SECONDARY, "IDC"))

    def test_unknown_https_host_is_low(self):
        self.assertEqual(
            tier_of_host("https://www.goldmansachs.com/research/note"),
            (Tier.LOW, "goldmansachs.com"),
        )

    def test_company_site_in_labels_is_primary(self):
        labeled = _mu(labels=(SourceLabel("website", "https://www.micron.com", "nasdaq_info"),))
        claim = _cited("ir-page", "press_release", "1.25", CitedUnit.COUNT, "https://micron.com/ir")
        line = citation_lines(labeled, SourceLedger("MU", (claim,)), {}, {})[claim.id][0]
        self.assertIn("company IR", line)
        self.assertTrue(line.endswith("primary]"))
        bare = citation_lines(_mu(), SourceLedger("MU", (claim,)), {}, {})[claim.id][0]
        self.assertIn("company IR", bare)
        self.assertTrue(bare.endswith("primary]"))
        blurb = _mu(labels=(SourceLabel("blurb", "see https://memory-prices.invalid/spot", "hand"),))
        buried = _cited("spot", "dram_spot_ddr5", "5.15", CitedUnit.USD_PER_GB, "https://memory-prices.invalid/spot")
        buried_line = citation_lines(blurb, SourceLedger("MU", (buried,)), {}, {})[buried.id][0]
        self.assertTrue(buried_line.endswith("low]"))

    def test_query_at_sign_does_not_pick_the_host(self):
        tier, publisher = tier_of_host("https://evil.example?x=@federalregister.gov/path")
        self.assertEqual((tier, publisher), (Tier.LOW, "evil.example"))

    def test_untrusted_subdomain_does_not_inherit_a_tier(self):
        self.assertEqual(tier_of_host("https://community.samsung.com/forum")[0], Tier.LOW)
        self.assertEqual(tier_of_host("https://spot.trendforce.com/ddr5")[0], Tier.LOW)
        self.assertEqual(
            tier_of_host("https://newsroom.samsung.com/story"),
            (Tier.SECONDARY, "Samsung"),
        )
        self.assertEqual(
            tier_of_host("https://www.trendforce.com/example/ddr5"),
            (Tier.SECONDARY, "TrendForce"),
        )

    def test_micron_ir_hosts_are_primary_without_a_website_label(self):
        snap = _mu()
        for url in ("https://investors.micron.com/news", "https://ir.micron.com/releases"):
            claim = _cited("ir-page", "press_release", "1.25", CitedUnit.COUNT, url)
            line = citation_lines(snap, SourceLedger("MU", (claim,)), {}, {})[claim.id][0]
            self.assertIn("company IR", line)
            self.assertTrue(line.endswith("primary]"), line)
        forum = _cited("forum", "press_release", "1.25", CitedUnit.COUNT, "https://community.micron.com/thread")
        forum_line = citation_lines(snap, SourceLedger("MU", (forum,)), {}, {})[forum.id][0]
        self.assertTrue(forum_line.endswith("low]"), forum_line)


class TestAdmitAndAudit(unittest.TestCase):
    def test_gaap_alias_is_blocked_even_when_the_fact_is_absent(self):
        snap = _mu(annual=())
        ledger = SourceLedger("MU", ())
        for measure in ("revenue", "NetIncomeLoss", "share_count", "equity_value", "Net_Income"):
            claim = _cited("alias", measure, "424242", CitedUnit.USD_ONES, "https://www.trendforce.com/alias")
            with self.assertRaises(ValueError):
                admit(ledger, claim, snap)

    def test_low_input_keeps_an_estimate_from_anchoring_a_star(self):
        snap = _mu()
        low = _cited("spot", "dram_spot_ddr5", "4", CitedUnit.USD_PER_GB, "https://memory-prices.invalid/spot")
        estimate = Cited(
            ClaimId("est"),
            Measure("dram_spot_ddr5"),
            Decimal("5.15"),
            CitedUnit.USD_PER_GB,
            "https://www.trendforce.com/example/ddr5",
            date(2026, 3, 18),
            None,
            (ClaimId("spot"),),
            "",
        )
        ledger = admit(admit(SourceLedger("MU", ()), low, snap), estimate, snap)
        ledger = admit(ledger, Scored(ClaimId("score-mu"), 4, ("est",), ("spot",)), snap)
        lines = citation_lines(snap, ledger, {}, {})
        self.assertIn("estimate", lines[estimate.id][0])
        self.assertTrue(lines[estimate.id][0].endswith("low]"))
        report = "\n".join([lines[estimate.id][0], lines[low.id][0], lines[ClaimId("score-mu")][0], "★★★★"])
        result = audit_report(report, snap, ledger, {})
        self.assertEqual(result.status, "fail")
        self.assertTrue(any("est" in item and "low" in item for item in result.failures))

    def test_backticks_do_not_hide_a_number(self):
        result = audit_report("`424242`\n", _mu(), None, {})
        self.assertEqual(result.status, "fail")
        self.assertTrue(any("424242" in item for item in result.failures))

    def test_backtick_prose_does_not_hide_a_quantity(self):
        snap = _mu()
        samples = (
            ("`7.77 USD per GB`\n", "7.77"),
            ("`$412`\n", "412"),
            ("`EPS 75 x 15 = 1125`\n", "1125"),
        )
        for line, needle in samples:
            result = audit_report(line, snap, None, {})
            self.assertEqual(result.status, "fail", line)
            self.assertTrue(any(needle in item for item in result.failures), result.failures)

    def test_core_synonym_cannot_stand_in_for_a_snapshot_figure(self):
        snap = _mu()
        empty = SourceLedger("MU", ())
        for measure in (
            "mkt_cap",
            "market_capitalization",
            "enterprise_value",
            "net_profit",
            "total_revenue",
            "fy2026_revenue",
            "eps",
            "diluted_eps",
            "shares_out",
            "share_count_diluted",
            "peer_nvda_revenue",
        ):
            claim = _cited("alias", measure, "99999999999", CitedUnit.USD_ONES, "https://www.reuters.com/markets/example")
            with self.assertRaises(ValueError, msg=measure):
                admit(empty, claim, snap)
        planted = _cited(
            "net-profit",
            "net_profit",
            "99999999999",
            CitedUnit.USD_ONES,
            "https://www.reuters.com/markets/example",
        )
        ledger = SourceLedger("MU", (planted,))
        line = citation_lines(snap, ledger, {}, {})[planted.id][0]
        result = audit_report(line + "\n", snap, ledger, {})
        self.assertEqual(result.status, "fail")
        self.assertTrue(any("99999999999" in item for item in result.failures))

    def test_star_glyphs_fail_without_a_ledger(self):
        result = audit_report("Verdict ★★★★★\nShares 100 as of 2026-08-28.\n", _mu(), None, {})
        self.assertEqual(result.status, "fail")
        self.assertTrue(any("star" in item for item in result.failures))

    def test_insider_shares_do_not_excuse_an_unrelated_price(self):
        snap = _mu(
            insiders=(
                InsiderTrade(
                    date(2026, 10, 14),
                    date(2026, 10, 15),
                    "RAY",
                    "S",
                    "D",
                    Decimal("40.00"),
                    Decimal("947.29"),
                    "https://www.sec.gov/Archives/example.xml",
                ),
            ),
            failures=(FetchFailure("nasdaq_info", 200, "https://www.example.invalid/info", "undated"),),
        )
        spot = audit_report("DRAM spot price 40.00\n", snap, None, {})
        self.assertEqual(spot.status, "fail")
        self.assertTrue(any("40.00" in item for item in spot.failures))
        stray = audit_report("The year 2026 was the trough.\n", snap, None, {})
        self.assertEqual(stray.status, "fail")
        self.assertTrue(any("2026" in item for item in stray.failures))
        status = audit_report("DRAM spot 200\n", snap, None, {})
        self.assertEqual(status.status, "fail")
        self.assertTrue(any("200" in item for item in status.failures))

    def test_chinese_numerals_in_a_us_note_are_scanned(self):
        result = audit_report("净利润二千四百亿元\n", _mu(), None, {})
        self.assertEqual(result.status, "fail")
        self.assertTrue(any("240000000000" in item or "二千四百" in item for item in result.failures))

    def test_qualified_measure_and_a_labeled_forecast_stay_citeable(self):
        snap = _mu()
        for measure in ("segment_dram_revenue", "hbm_capex", "profit_2036", "nongaap_eps"):
            claim = _cited("alias", measure, "5.15", CitedUnit.USD_ONES, "https://www.trendforce.com/example/ddr5")
            admit(SourceLedger("MU", ()), claim, snap)

    def test_a_snapshot_figure_passes_when_the_line_names_it(self):
        snap = _mu(
            insiders=(
                InsiderTrade(
                    date(2026, 10, 14),
                    date(2026, 10, 15),
                    "RAY",
                    "S",
                    "D",
                    Decimal("40.00"),
                    Decimal("947.29"),
                    "https://www.sec.gov/Archives/example.xml",
                ),
            ),
            failures=(FetchFailure("nasdaq_info", 200, "https://www.example.invalid/info", "undated"),),
        )
        self.assertEqual(
            audit_report("owner transaction shares 40.00 and price 947.29\n", snap, None, {}).status,
            "pass",
        )
        self.assertEqual(audit_report("Fiscal year 2026 ends 2026-08-28.\n", _mu(), None, {}).status, "pass")
        self.assertEqual(audit_report("Nasdaq info, status 200\n", snap, None, {}).status, "pass")
        self.assertEqual(audit_report("`10-K` and `005930.KS`\n", _mu(), None, {}).status, "pass")

    def test_thesis_anchor_plus_a_snapshot_ref_can_score(self):
        snap = _mu()
        cited = _cited("spot", "dram_spot_ddr5", "5.15", CitedUnit.USD_PER_GB, "https://www.trendforce.com/example/ddr5")
        ledger = admit(SourceLedger("MU", ()), cited, snap)
        ledger = admit(ledger, Scored(ClaimId("score-mu"), 4, ("spot", "snap:market_cap")), snap)
        lines = citation_lines(snap, ledger, {}, {})
        report = "\n".join([lines[cited.id][0], lines[ClaimId("score-mu")][0], "★★★★"])
        self.assertEqual(audit_report(report, snap, ledger, {}).status, "pass")

    def test_snapshot_anchor_alone_cannot_support_a_star(self):
        snap = _mu()
        ledger = admit(SourceLedger("MU", ()), Scored(ClaimId("score-mu"), 4, ("snap:market_cap",)), snap)
        line = citation_lines(snap, ledger, {}, {})[ClaimId("score-mu")][0]
        result = audit_report(line + "\n★★★★\n", snap, ledger, {})
        self.assertEqual(result.status, "fail")
        self.assertTrue(any("anchor" in item for item in result.failures))

    def test_ledger_ticker_must_match_the_snapshot(self):
        result = audit_report("Shares 100 as of 2026-08-28.\n", _mu(), SourceLedger("AAPL", ()), {})
        self.assertEqual(result.status, "fail")
        self.assertIn("ledger ticker does not match the snapshot", result.failures)

    def test_sec_gov_cited_raises(self):
        snap = _mu()
        ledger = SourceLedger("MU", ())
        for url in ("https://www.sec.gov/Archives/x.htm", "https://data.sec.gov/api/x"):
            claim = _cited("sec-fact", "export_count", "1", CitedUnit.COUNT, url)
            with self.assertRaises(ValueError):
                admit(ledger, claim, snap)

    def test_low_only_score_fails_and_secondary_score_passes(self):
        snap = _mu()
        low = _cited("spot", "dram_spot_ddr5", "5.15", CitedUnit.USD_PER_GB, "https://memory-prices.invalid/spot")
        low_ledger = admit(admit(SourceLedger("MU", ()), low, snap), Scored(ClaimId("score-mu"), 4, ("spot",)), snap)
        low_lines = citation_lines(snap, low_ledger, {}, {})
        low_report = "\n".join([low_lines[low.id][0], low_lines[ClaimId("score-mu")][0], "★★★★"])
        low_result = audit_report(low_report, snap, low_ledger, {})
        self.assertEqual(low_result.status, "fail")
        self.assertTrue(any("spot" in item and "low" in item for item in low_result.failures))
        self.assertFalse(any("not in the snapshot" in item for item in low_result.failures))

        cited = _cited(
            "spot",
            "dram_spot_ddr5",
            "5.15",
            CitedUnit.USD_PER_GB,
            "https://www.trendforce.com/example/ddr5",
        )
        ledger = admit(admit(SourceLedger("MU", ()), cited, snap), Scored(ClaimId("score-mu"), 4, ("spot",)), snap)
        lines = citation_lines(snap, ledger, {}, {})
        report = "\n".join([lines[cited.id][0], lines[ClaimId("score-mu")][0], "★★★★"])
        result = audit_report(report, snap, ledger, {})
        self.assertEqual(result.status, "pass")
        self.assertIsInstance(result, AuditResult)

    def test_hidden_dispute_member_fails(self):
        snap = _mu()
        first = _cited(
            "dram-ddr5-tf",
            "dram_spot_ddr5",
            "5.15",
            CitedUnit.USD_PER_GB,
            "https://www.trendforce.com/example/ddr5",
        )
        second = _cited(
            "dram-ddr5-r",
            "dram_spot_ddr5",
            "5.40",
            CitedUnit.USD_PER_GB,
            "https://www.reuters.com/markets/example",
        )
        ledger = SourceLedger("MU", ())
        ledger = admit(ledger, first, snap)
        ledger = admit(ledger, second, snap)
        dispute = Dispute(ClaimId("dram-ddr5"), Measure("dram_spot_ddr5"), (first.id, second.id))
        ledger = admit(ledger, dispute, snap)
        lines = citation_lines(snap, ledger, {}, {})
        heading = "# " + lines[first.id][0] + "\nbody without the other\n"
        self.assertEqual(audit_report(heading, snap, ledger, {}).status, "fail")
        hidden = "# Spot\n" + lines[first.id][0] + "\n"
        hidden_result = audit_report(hidden, snap, ledger, {})
        self.assertEqual(hidden_result.status, "fail")
        self.assertTrue(any("dram-ddr5" in item for item in hidden_result.failures))
        shown = "# Spot\n" + "\n".join(
            [lines[first.id][0], lines[second.id][0], lines[dispute.id][0]]
        )
        self.assertEqual(audit_report(shown, snap, ledger, {}).status, "pass")

    def test_braced_citation_excuses_its_digits_and_the_bracket(self):
        snap = _mu()
        claim = _cited(
            "dram-ddr5-tf",
            "dram_spot_ddr5",
            "5.15",
            CitedUnit.USD_PER_GB,
            "https://www.trendforce.com/example/ddr5",
        )
        analyze = render_analysis(snap)
        self.assertNotIn("5.15", snapshot_allow_list(snap, analyze))
        line = citation_lines(snap, SourceLedger("MU", (claim,)), {}, {})[claim.id][0]
        self.assertNotEqual(unexcused_numbers(line, snap, analyze, None), [])
        self.assertEqual(unexcused_numbers(line, snap, analyze, {claim.id: (line,)}), [])

    def test_gaap_number_on_a_cited_line_still_fails(self):
        snap = _mu()
        claim = _cited(
            "dram-ddr5-tf",
            "dram_spot_ddr5",
            "5.15",
            CitedUnit.USD_PER_GB,
            "https://www.trendforce.com/example/ddr5",
        )
        ledger = SourceLedger("MU", (claim,))
        line = citation_lines(snap, ledger, {}, {})[claim.id][0]
        report = f"net income 424242 {line}\n"
        analyze = render_analysis(snap)
        self.assertIn("424242", unexcused_numbers(report, snap, analyze, {claim.id: (line,)}))
        result = audit_report(report, snap, ledger, {})
        self.assertEqual(result.status, "fail")
        self.assertTrue(
            any("424242" in item and "not in the snapshot" in item for item in result.failures)
        )

    def test_snapshot_class_citation_does_not_excuse_its_number(self):
        snap = _mu()
        claim = Cited(
            ClaimId("ni-extra"),
            Measure("net_income"),
            Decimal("424242"),
            CitedUnit.USD_ONES,
            "https://www.trendforce.com/example/income",
            date(2026, 3, 18),
            None,
            (),
            "",
        )
        ledger = SourceLedger("MU", (claim,))
        line = citation_lines(snap, ledger, {}, {})[claim.id][0]
        result = audit_report(line + "\n", snap, ledger, {})
        self.assertEqual(result.status, "fail")
        self.assertTrue(any("424242" in item for item in result.failures))

    def test_ledger_text_containing_at_is_rejected(self):
        with self.assertRaises(ValueError):
            load_ledger('{"claims": [], "ticker": "a@b"}\n')
        with self.assertRaises(ValueError):
            load_ledger('{"claims": [], "ticker": "mu--shares"}\n')
        loaded = load_ledger('{"claims": [], "ticker": "MU"}\n')
        self.assertEqual(loaded.ticker, "MU")
        self.assertEqual(loaded.claims, ())

    def test_note_without_a_us_signal_skips(self):
        result = audit_report("收入约为100亿元。\n", None, None, {})
        self.assertEqual(result.status, "skip")

    def test_allow_listed_snapshot_note_passes_without_a_ledger(self):
        snap = _mu()
        result = audit_report("Shares 100 as of 2026-08-28.\n", snap, None, {})
        self.assertEqual(result.failures, ())
        self.assertEqual(result.status, "pass")

    def test_existing_micron_notes_pass_without_a_ledger(self):
        folder = _ROOT / "reports" / "Micron"
        snap = snapshot_from_json(json.loads((folder / "evidence" / "us-snapshot-MU.json").read_text(encoding="utf-8")))
        for path in sorted(folder.glob("*.md")):
            result = audit_report(path.read_text(encoding="utf-8"), snap, None, {})
            self.assertEqual(result.status, "pass", (path.name, result.failures))


class TestDerive(unittest.TestCase):
    def _rates(self, snap: IssuerSnapshot) -> SourceLedger:
        claims = [
            _cited("g-bull", "growth_bull", "0.20", CitedUnit.RATIO, "https://www.trendforce.com/g/bull"),
            _cited("g-base", "growth_base", "0.10", CitedUnit.RATIO, "https://www.reuters.com/g/base"),
            _cited("g-bear", "growth_bear", "0", CitedUnit.RATIO, "https://www.ft.com/g/bear"),
            _cited("pe-bull", "pe_bull", "15", CitedUnit.MULTIPLE, "https://www.bloomberg.com/pe/bull"),
            _cited("pe-base", "pe_base", "12", CitedUnit.MULTIPLE, "https://www.wsj.com/pe/base"),
            _cited("pe-bear", "pe_bear", "8", CitedUnit.MULTIPLE, "https://www.ft.com/pe/bear"),
            _cited("profit-2036", "profit_2036", "2000", CitedUnit.USD_ONES, "https://www.trendforce.com/profit"),
        ]
        ledger = SourceLedger(snap.ticker, ())
        for claim in claims:
            ledger = admit(ledger, claim, snap)
        return ledger

    def test_three_scenario_price_uses_snapshot_refs(self):
        snap = _mu()
        ledger = self._rates(snap)
        request = ThreeScenario(
            ClaimId("scenario-mu"),
            (ClaimId("g-bull"), ClaimId("g-base"), ClaimId("g-bear")),
            (ClaimId("pe-bull"), ClaimId("pe-base"), ClaimId("pe-bear")),
        )
        derived = derive(ledger, snap, request)
        again = derive(derived, snap, request)
        self.assertEqual(len(again.claims), len(derived.claims))
        row = again.by_id()[request.id]
        self.assertEqual(row.tool, DeriveTool.THREE_SCENARIO)
        self.assertEqual(
            row.inputs[-3:],
            ("snap:gaap:net_income:2026", "snap:shares:2026-08-28", "snap:close:2026-10-17"),
        )
        self.assertNotIn("--shares", " ".join(row.inputs))
        self.assertNotIn("--reported", " ".join(row.inputs))
        eps = Decimal("1000") / Decimal("100")
        expected = []
        for growth, pe in (("0.20", "15"), ("0.10", "12"), ("0", "8")):
            future = eps
            for _ in range(3):
                future = future * (Decimal("1") + Decimal(growth))
            cents = (future * Decimal(pe)).quantize(Decimal("0.01"))
            expected.append(format(cents, "f"))
        text = "\n".join(citation_lines(snap, again, {}, {})[request.id])
        for canon in expected:
            self.assertIn("{" + canon + "}", text)
        self.assertIn("tier=secondary", text)
        self.assertIn("tool=three_scenario", text)
        self.assertEqual(scenario_target_price(Decimal("10"), Decimal("0.1"), Decimal("12"), 3), Decimal("159.72"))
        self.assertIn("case=bull", text)
        self.assertIn("case=base", text)
        self.assertIn("case=bear", text)
        partial = audit_report(citation_lines(snap, again, {}, {})[request.id][0] + "\n", snap, again, {})
        self.assertEqual(partial.status, "fail")
        self.assertTrue(any("hides a scenario" in item for item in partial.failures))

    def test_derive_replaces_a_snap_ref_that_no_longer_resolves(self):
        snap = _mu()
        ledger = self._rates(snap)
        request = ThreeScenario(
            ClaimId("scenario-mu"),
            (ClaimId("g-bull"), ClaimId("g-base"), ClaimId("g-bear")),
            (ClaimId("pe-bull"), ClaimId("pe-base"), ClaimId("pe-bear")),
        )
        derived = derive(ledger, snap, request)
        later = _mu(shares=ShareCount(Decimal("100"), date(2026, 9, 1), "EntityCommonStockSharesOutstanding"))
        refreshed = derive(derived, later, request)
        self.assertIn("snap:shares:2026-09-01", refreshed.by_id()[request.id].inputs)
        kept = _mu(
            annual=_mu().annual
            + (
                AnnualFact(
                    2027,
                    date(2027, 8, 28),
                    "net_income",
                    Decimal("5000"),
                    date(2027, 10, 1),
                    "NetIncomeLoss",
                ),
            )
        )
        again = derive(derived, kept, request)
        self.assertIn("snap:gaap:net_income:2026", again.by_id()[request.id].inputs)

    def test_irr_recomputes_market_cap_from_the_snapshot(self):
        snap = _mu()
        ledger = self._rates(snap)
        request = IrrRequest(ClaimId("irr-mu"), ClaimId("profit-2036"), ClaimId("pe-base"))
        derived = derive(ledger, snap, request)
        row = derived.by_id()[request.id]
        self.assertEqual(row.inputs[0], "profit-2036")
        self.assertEqual(row.inputs[1], "pe-base")
        self.assertEqual(row.inputs[-2:], ("snap:close:2026-10-17", "snap:shares:2026-08-28"))
        self.assertNotIn("--reported", " ".join(row.inputs))
        line = citation_lines(snap, derived, {}, {})[request.id][0]
        self.assertIn("{0.0915}", line)
        self.assertIn("tool=irr", line)
        bare = _mu(shares=None)
        with self.assertRaises(ValueError):
            derive(ledger, bare, request)

    def test_peer_snapshot_prints_primary(self):
        peer = _mu(ticker="NVDA")
        annual = (
            AnnualFact(2026, date(2026, 1, 31), "revenue", Decimal("5000"), date(2026, 2, 20), "Revenue"),
        )
        peer = _mu(
            ticker="NVDA",
            annual=annual,
            filings=(
                FilingRef(
                    "10-K",
                    date(2026, 2, 20),
                    "0001045810-26-000001",
                    "https://www.sec.gov/Archives/edgar/data/1045810/nvda.htm",
                ),
            ),
        )
        path = "reports/NVIDIA/evidence/us-snapshot-NVDA.json"
        claim = PeerSnapshot(ClaimId("nvda-revenue-fy2026"), Measure("peer_nvda_revenue"), path, "revenue", 2026)
        ledger = admit(SourceLedger("MU", ()), claim, _mu())
        line = citation_lines(_mu(), ledger, {}, {path: peer})[claim.id][0]
        self.assertTrue(line.endswith("primary]"))
        self.assertIn("SEC", line)
        self.assertIn("{5000}", line)
        self.assertIn("https://www.sec.gov/Archives/edgar/data/1045810/nvda.htm", line)
        ambiguous = _mu(
            ticker="NVDA",
            annual=annual,
            filings=peer.filings
            + (
                FilingRef(
                    "8-K",
                    date(2026, 2, 20),
                    "0001045810-26-000002",
                    "https://www.sec.gov/Archives/edgar/data/1045810/nvda-8k.htm",
                ),
            ),
        )
        with self.assertRaises(ValueError):
            citation_lines(_mu(), ledger, {}, {path: ambiguous})

    def test_three_scenario_rejects_a_collapse_and_a_loss_year(self):
        snap = _mu()
        ledger = self._rates(snap)
        deep = _cited("g-deep", "growth_deep", "-1.5", CitedUnit.RATIO, "https://www.ft.com/g/deep")
        ledger = admit(ledger, deep, snap)
        collapsed = ThreeScenario(
            ClaimId("scenario-bad"),
            (ClaimId("g-deep"), ClaimId("g-base"), ClaimId("g-bear")),
            (ClaimId("pe-bull"), ClaimId("pe-base"), ClaimId("pe-bear")),
        )
        with self.assertRaises(ValueError) as caught:
            derive(ledger, snap, collapsed)
        self.assertNotIn("ConversionSyntax", str(caught.exception))
        zero = _cited("pe-zero", "pe_zero", "0", CitedUnit.MULTIPLE, "https://www.ft.com/pe/zero")
        ledger = admit(ledger, zero, snap)
        free = ThreeScenario(
            ClaimId("scenario-zero"),
            (ClaimId("g-bull"), ClaimId("g-base"), ClaimId("g-bear")),
            (ClaimId("pe-zero"), ClaimId("pe-base"), ClaimId("pe-bear")),
        )
        with self.assertRaises(ValueError):
            derive(ledger, snap, free)
        loss = _mu(
            annual=(
                AnnualFact(
                    2026,
                    date(2026, 8, 28),
                    "net_income",
                    Decimal("-100"),
                    date(2026, 10, 1),
                    "NetIncomeLoss",
                ),
            )
        )
        with self.assertRaises(ValueError) as loss_caught:
            derive(self._rates(loss), loss, ThreeScenario(
                ClaimId("scenario-loss"),
                (ClaimId("g-bull"), ClaimId("g-base"), ClaimId("g-bear")),
                (ClaimId("pe-bull"), ClaimId("pe-base"), ClaimId("pe-bear")),
            ))
        self.assertIn("loss", str(loss_caught.exception).lower())

    def test_irr_rejects_zero_years_without_a_division_error(self):
        snap = _mu()
        ledger = self._rates(snap)
        request = IrrRequest(ClaimId("irr-zero"), ClaimId("profit-2036"), ClaimId("pe-base"), years=0)
        with self.assertRaises(ValueError) as caught:
            derive(ledger, snap, request)
        self.assertNotIn("ZeroDivisionError", type(caught.exception).__name__)

    def test_derived_lines_round_prices_to_cents_and_irr_to_four_places(self):
        snap = _mu()
        ledger = self._rates(snap)
        request = ThreeScenario(
            ClaimId("scenario-mu"),
            (ClaimId("g-bull"), ClaimId("g-base"), ClaimId("g-bear")),
            (ClaimId("pe-bull"), ClaimId("pe-base"), ClaimId("pe-bear")),
        )
        derived = derive(ledger, snap, request)
        text = "\n".join(citation_lines(snap, derived, {}, {})[request.id])
        self.assertIn("{259.20}", text)
        self.assertIn("{159.72}", text)
        self.assertIn("{80.00}", text)
        irr = derive(ledger, snap, IrrRequest(ClaimId("irr-mu"), ClaimId("profit-2036"), ClaimId("pe-base")))
        line = citation_lines(snap, irr, {}, {})[ClaimId("irr-mu")][0]
        self.assertIn("{0.0915}", line)
        self.assertNotIn("{0.09149342561789697}", line)


class TestParserAndVisibleText(unittest.TestCase):
    def test_derive_parser_has_no_shares_or_reported_flag(self):
        parser = build_parser()
        flags = _option_strings(parser)
        self.assertTrue(flags.isdisjoint({"--shares", "--reported", "--tier", "--publisher"}))
        three = parser.parse_args(
            [
                "derive",
                "three-scenario",
                "--ledger",
                "L",
                "--snapshot",
                "S",
                "--id",
                "scenario-mu",
                "--growth",
                "a,b,c",
                "--pe",
                "d,e,f",
            ]
        )
        self.assertEqual(three.years, 3)
        irr = parser.parse_args(
            ["derive", "irr", "--ledger", "L", "--snapshot", "S", "--id", "irr-mu", "--profit", "p", "--pe", "e"]
        )
        self.assertEqual(irr.years, 10)
        self.assertIsNone(irr.payout)
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(
                    [
                        "derive",
                        "three-scenario",
                        "--ledger",
                        "L",
                        "--snapshot",
                        "S",
                        "--id",
                        "scenario-mu",
                        "--growth",
                        "a,b,c",
                        "--pe",
                        "d,e,f",
                        "--shares",
                        "9",
                    ]
                )
            with self.assertRaises(SystemExit):
                parser.parse_args(
                    [
                        "derive",
                        "irr",
                        "--ledger",
                        "L",
                        "--snapshot",
                        "S",
                        "--id",
                        "irr-mu",
                        "--profit",
                        "p",
                        "--pe",
                        "e",
                        "--reported",
                        "1",
                    ]
                )

    def test_visible_text_drops_script_and_style(self):
        body = (
            b"<html><style>p{color:red}</style><script>var n=1</script>"
            b"<p>The board elected Ada.</p></html>"
        )
        text = visible_text(body, "text/html")
        self.assertIn("The board elected Ada.", text)
        self.assertNotIn("var n", text)
        self.assertNotIn("color", text)
        self.assertEqual(visible_text(b"plain 7", "text/plain"), "plain 7")


_AGENT = "Ada Lovelace ada@research-desk.test"
_SENTENCE = "The board elected Ada."


def _html_filing(times: int) -> bytes:
    paragraphs = "".join(f"<p>{_SENTENCE}</p>" for _ in range(times))
    return (
        b"<html><style>.x{color:red}</style><script>var n=1</script><body>"
        + paragraphs.encode("utf-8")
        + b"</body></html>"
    )


class TestSourceLedgerCli(unittest.TestCase):
    def test_admit_cited_prints_the_paste_line(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = os.path.join(directory, "source-ledger.json")
            with open(os.path.join(directory, "us-snapshot-MU.json"), "w", encoding="utf-8"):
                pass
            argv = [
                "admit",
                "cited",
                "--ledger",
                ledger,
                "--id",
                "dram-ddr5-tf",
                "--measure",
                "dram_spot_ddr5",
                "--value",
                "5.15",
                "--unit",
                "usd_per_gb",
                "--url",
                "https://www.trendforce.com/example/ddr5",
                "--published",
                "2026-03-18",
            ]
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = source_ledger.main(argv)
            self.assertEqual(code, 0)
            self.assertEqual(
                stdout.getvalue().strip(),
                "{5.15}[c:dram-ddr5-tf https://www.trendforce.com/example/ddr5 "
                "TrendForce published=2026-03-18 measure=dram_spot_ddr5 secondary]",
            )
            with open(ledger, encoding="utf-8") as handle:
                stored = handle.read()
            self.assertNotIn('"tier"', stored)
            self.assertNotIn('"publisher"', stored)
            self.assertNotIn("@", stored)
            with contextlib.redirect_stdout(io.StringIO()):
                again = source_ledger.main(argv)
            self.assertEqual(again, 0)
            with open(ledger, encoding="utf-8") as handle:
                self.assertEqual(len(load_ledger(handle.read()).claims), 1)

    def test_excerpt_out_must_sit_beside_the_ledger(self):
        snap = _mu()
        with tempfile.TemporaryDirectory() as directory:
            snapshot_path = os.path.join(directory, "us-snapshot-MU.json")
            ledger_path = os.path.join(directory, "source-ledger.json")
            with open(snapshot_path, "w", encoding="utf-8") as handle:
                json.dump(snap.to_json(), handle)
            argv = [
                "admit",
                "excerpt",
                "--ledger",
                ledger_path,
                "--snapshot",
                snapshot_path,
                "--id",
                "proxy-ceo",
                "--measure",
                "biography",
                "--accession",
                snap.filings[0].accession,
                "--contains",
                _SENTENCE,
                "--out",
                os.path.join(directory, "other.txt"),
            ]
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = source_ledger.main(argv)
            self.assertEqual(code, 1)
            self.assertIn("excerpts/<id>.txt", stderr.getvalue())
            self.assertFalse(os.path.exists(ledger_path))
            self.assertFalse(os.path.exists(os.path.join(directory, "other.txt")))

    def test_excerpt_fetch_hides_the_user_agent_and_deletes_the_download(self):
        snap = _mu()
        filing_url = snap.filings[0].url
        calls = []
        created = []
        real_mkstemp = tempfile.mkstemp

        def fake_get(url, user_agent, **kwargs):
            calls.append((url, user_agent))
            return 200, _html_filing(1)

        def tracking_mkstemp(*args, **kwargs):
            result = real_mkstemp(*args, **kwargs)
            created.append(result[1])
            return result

        with tempfile.TemporaryDirectory() as directory:
            snapshot_path = os.path.join(directory, "us-snapshot-MU.json")
            ledger_path = os.path.join(directory, "source-ledger.json")
            out_path = os.path.join(directory, "excerpts", "proxy-ceo.txt")
            with open(snapshot_path, "w", encoding="utf-8") as handle:
                json.dump(snap.to_json(), handle)
            argv = [
                "admit",
                "excerpt",
                "--ledger",
                ledger_path,
                "--snapshot",
                snapshot_path,
                "--id",
                "proxy-ceo",
                "--measure",
                "biography",
                "--accession",
                snap.filings[0].accession,
                "--contains",
                _SENTENCE,
                "--out",
                out_path,
            ]
            stdout = io.StringIO()
            with patch.object(source_ledger, "http_get", fake_get), patch.object(
                source_ledger, "sec_user_agent", return_value=_AGENT
            ), patch.object(source_ledger.tempfile, "mkstemp", tracking_mkstemp), contextlib.redirect_stdout(stdout):
                code = source_ledger.main(argv)
            text = stdout.getvalue()
            with open(out_path, encoding="utf-8") as handle:
                slice_text = handle.read()
            with open(ledger_path, encoding="utf-8") as handle:
                ledger_text = handle.read()
            self.assertEqual(code, 0)
            self.assertEqual(calls, [(filing_url, _AGENT)])
            self.assertIn(_SENTENCE, text)
            self.assertIn("[q:proxy-ceo]", text)
            self.assertIn("[/q]", text)
            self.assertTrue(text.strip().splitlines()[0].endswith("primary]"))
            self.assertNotIn("var n", text)
            self.assertEqual(slice_text, _SENTENCE)
            for surface in (text, slice_text, ledger_text, " ".join(argv)):
                self.assertNotIn(_AGENT, surface)
                self.assertNotIn("User-Agent:", surface)
            self.assertTrue(created)
            self.assertTrue(all(not os.path.exists(path) for path in created))
            self.assertFalse(os.path.exists(out_path + ".tmp"))
            with patch.object(source_ledger, "http_get", fake_get), patch.object(
                source_ledger, "sec_user_agent", return_value=_AGENT
            ), patch.object(source_ledger.tempfile, "mkstemp", tracking_mkstemp), contextlib.redirect_stdout(io.StringIO()):
                again = source_ledger.main(argv)
            self.assertEqual(again, 0)
            with open(ledger_path, encoding="utf-8") as handle:
                self.assertEqual(len(load_ledger(handle.read()).claims), 1)

    def test_excerpt_match_failure_deletes_the_download_and_skips_the_ledger(self):
        snap = _mu()
        created = []
        real_mkstemp = tempfile.mkstemp

        def fake_get(url, user_agent, **kwargs):
            return 200, _html_filing(2)

        def tracking_mkstemp(*args, **kwargs):
            result = real_mkstemp(*args, **kwargs)
            created.append(result[1])
            return result

        with tempfile.TemporaryDirectory() as directory:
            snapshot_path = os.path.join(directory, "us-snapshot-MU.json")
            ledger_path = os.path.join(directory, "source-ledger.json")
            out_path = os.path.join(directory, "excerpts", "proxy-ceo.txt")
            with open(snapshot_path, "w", encoding="utf-8") as handle:
                json.dump(snap.to_json(), handle)
            argv = [
                "admit",
                "excerpt",
                "--ledger",
                ledger_path,
                "--snapshot",
                snapshot_path,
                "--id",
                "proxy-ceo",
                "--measure",
                "biography",
                "--accession",
                snap.filings[0].accession,
                "--contains",
                _SENTENCE,
                "--out",
                out_path,
            ]
            stderr = io.StringIO()
            with patch.object(source_ledger, "http_get", fake_get), patch.object(
                source_ledger, "sec_user_agent", return_value=_AGENT
            ), patch.object(source_ledger.tempfile, "mkstemp", tracking_mkstemp), contextlib.redirect_stdout(
                io.StringIO()
            ), contextlib.redirect_stderr(stderr):
                code = source_ledger.main(argv)
            self.assertEqual(code, 1)
            self.assertNotIn(_AGENT, stderr.getvalue())
            self.assertNotIn("User-Agent:", stderr.getvalue())
            self.assertFalse(os.path.exists(ledger_path))
            self.assertFalse(os.path.exists(out_path))
            self.assertTrue(created)
            self.assertTrue(all(not os.path.exists(path) for path in created))

    def test_diverged_excerpt_slice_exits_2(self):
        snap = _mu()

        def fake_get(url, user_agent, **kwargs):
            return 200, _html_filing(1)

        with tempfile.TemporaryDirectory() as directory:
            snapshot_path = os.path.join(directory, "us-snapshot-MU.json")
            ledger_path = os.path.join(directory, "source-ledger.json")
            out_path = os.path.join(directory, "excerpts", "proxy-ceo.txt")
            os.makedirs(os.path.dirname(out_path))
            with open(out_path, "wb") as handle:
                handle.write(b"other sentence")
            with open(snapshot_path, "w", encoding="utf-8") as handle:
                json.dump(snap.to_json(), handle)
            argv = [
                "admit",
                "excerpt",
                "--ledger",
                ledger_path,
                "--snapshot",
                snapshot_path,
                "--id",
                "proxy-ceo",
                "--measure",
                "biography",
                "--accession",
                snap.filings[0].accession,
                "--contains",
                _SENTENCE,
                "--out",
                out_path,
            ]
            stderr = io.StringIO()
            with patch.object(source_ledger, "http_get", fake_get), patch.object(
                source_ledger, "sec_user_agent", return_value=_AGENT
            ), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
                code = source_ledger.main(argv)
            self.assertEqual(code, 2)
            self.assertNotIn(_AGENT, stderr.getvalue())
            self.assertNotIn("User-Agent:", stderr.getvalue())
            with open(out_path, "rb") as handle:
                self.assertEqual(handle.read(), b"other sentence")
            self.assertFalse(os.path.exists(ledger_path))

    def test_excerpt_reads_an_8k_exhibit(self):
        accession = "0000723125-26-000099"
        cover = "https://www.sec.gov/Archives/edgar/data/723125/000072312526000099/mu-8k.htm"
        exhibit = "https://www.sec.gov/Archives/edgar/data/723125/000072312526000099/ex99-1.htm"
        index = "https://www.sec.gov/Archives/edgar/data/723125/000072312526000099/index.json"
        sentence = "Revenue was strong."
        snap = _mu(filings=(FilingRef("8-K", date(2026, 10, 1), accession, cover),))
        index_body = json.dumps({
            "directory": {"item": [
                {"name": "mu-8k.htm", "type": "8-K"},
                {"name": "ex99-1.htm", "type": "EX-99.1"},
            ]}
        }).encode()
        pages = {
            cover: b"<html><p>Cover only.</p></html>",
            index: index_body,
            exhibit: f"<html><p>{sentence}</p></html>".encode(),
        }

        def fake_get(url, user_agent, **kwargs):
            body = pages.get(url)
            if body is None:
                return 404, b""
            return 200, body

        with tempfile.TemporaryDirectory() as directory:
            snapshot_path = os.path.join(directory, "us-snapshot-MU.json")
            ledger_path = os.path.join(directory, "source-ledger.json")
            out_path = os.path.join(directory, "excerpts", "earnings-release.txt")
            with open(snapshot_path, "w", encoding="utf-8") as handle:
                json.dump(snap.to_json(), handle)
            argv = [
                "admit",
                "excerpt",
                "--ledger",
                ledger_path,
                "--snapshot",
                snapshot_path,
                "--id",
                "earnings-release",
                "--measure",
                "earnings_release",
                "--accession",
                accession,
                "--contains",
                sentence,
                "--out",
                out_path,
            ]
            stdout = io.StringIO()
            with patch.object(source_ledger, "http_get", fake_get), patch.object(
                source_ledger, "sec_user_agent", return_value=_AGENT
            ), contextlib.redirect_stdout(stdout):
                code = source_ledger.main(argv)
            self.assertEqual(code, 0, stdout.getvalue())
            stored = load_ledger(Path(ledger_path).read_text(encoding="utf-8"))
            self.assertEqual(stored.claims[0].document_url, exhibit)
            bracket = citation_lines(snap, stored, {stored.claims[0].id: sentence.encode()}, {})[stored.claims[0].id][0]
            self.assertIn(exhibit, bracket)
            self.assertNotIn(_AGENT, stdout.getvalue())

    def test_peer_path_is_stored_repo_relative(self):
        path = _ROOT / "tests" / "fixtures" / "us" / "peer-nvda.json"
        peer = _mu(
            ticker="NVDA",
            prints=(
                MarketPrint(
                    "NVDA",
                    Decimal("100"),
                    PrintKind.OFFICIAL_CLOSE,
                    datetime(2026, 10, 17, 20, 0, tzinfo=timezone.utc),
                    "nasdaq_quote",
                ),
            ),
            filings=(
                FilingRef(
                    "10-K",
                    date(2026, 10, 1),
                    "0001045810-26-000001",
                    "https://www.sec.gov/Archives/edgar/data/1045810/nvda.htm",
                ),
            ),
            annual=(
                AnnualFact(
                    2026,
                    date(2026, 8, 28),
                    "revenue",
                    Decimal("1000"),
                    date(2026, 10, 1),
                    "Revenues",
                ),
            ),
        )
        path.write_text(json.dumps(peer.to_json()), encoding="utf-8")
        try:
            with tempfile.TemporaryDirectory() as directory:
                ledger_path = os.path.join(directory, "source-ledger.json")
                write_ledger(ledger_path, SourceLedger("MU", ()), "")
                argv = [
                    "admit",
                    "peer",
                    "--ledger",
                    ledger_path,
                    "--id",
                    "nvda-revenue",
                    "--measure",
                    "peer_nvda_revenue",
                    "--snapshot",
                    str(path),
                    "--concept",
                    "revenue",
                    "--fiscal-year",
                    "2026",
                ]
                with contextlib.redirect_stdout(io.StringIO()):
                    code = source_ledger.main(argv)
                self.assertEqual(code, 0)
                stored = load_ledger(Path(ledger_path).read_text(encoding="utf-8"))
                self.assertEqual(stored.claims[0].snapshot_path, "tests/fixtures/us/peer-nvda.json")
        finally:
            path.unlink(missing_ok=True)

    def test_remove_drops_one_ledger_row(self):
        snap = _mu()
        claim = _cited("dram-ddr5-tf", "dram_spot_ddr5", "5.15", CitedUnit.USD_PER_GB, "https://www.trendforce.com/example/ddr5")
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = os.path.join(directory, "source-ledger.json")
            write_ledger(ledger_path, admit(SourceLedger("MU", ()), claim, snap), "")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = source_ledger.main(["remove", "--ledger", ledger_path, "--id", "dram-ddr5-tf"])
            self.assertEqual(code, 0, stdout.getvalue())
            self.assertEqual(load_ledger(Path(ledger_path).read_text(encoding="utf-8")).claims, ())


class TestReportAuditDelegation(unittest.TestCase):
    def test_snapshot_flag_delegates_and_bare_extract_does_not(self):
        snap = _mu()
        tool = str(_ROOT / "tools" / "report_audit.py")
        with tempfile.TemporaryDirectory() as directory:
            snap_path = os.path.join(directory, "snap.json")
            report_path = os.path.join(directory, "note.md")
            with open(snap_path, "w", encoding="utf-8") as handle:
                json.dump(snap.to_json(), handle)
            with open(report_path, "w", encoding="utf-8") as handle:
                handle.write("Shares 100 as of 2026-08-28.\n")
            passed = subprocess.run(
                [sys.executable, tool, "--report", report_path, "--snapshot", snap_path],
                capture_output=True,
                text=True,
            )
            self.assertEqual(passed.returncode, 0, passed.stderr)
            self.assertIn("audit: pass", passed.stdout)
            self.assertNotIn("报告数据抽检清单", passed.stdout)
            with open(report_path, "w", encoding="utf-8") as handle:
                handle.write("Shares 100 as of 2026-08-28.\nnet income 424242\n")
            failed = subprocess.run(
                [sys.executable, tool, "--report", report_path, "--snapshot", snap_path],
                capture_output=True,
                text=True,
            )
            self.assertEqual(failed.returncode, 1, failed.stderr)
            self.assertIn("424242", failed.stdout)
            self.assertIn("not in the snapshot", failed.stdout)
            self.assertNotIn("报告数据抽检清单", failed.stdout)
        bare = subprocess.run(
            [sys.executable, tool, "extract", "--report", str(_ROOT / "reports" / "Micron" / "final-report.md"), "--dry-run"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(bare.returncode, 0, bare.stderr)
        self.assertIn("报告数据抽检清单", bare.stdout)
        self.assertNotIn("audit: pass", bare.stdout)
        hijack = subprocess.run(
            [sys.executable, tool, "extract", "--report", str(_ROOT / "reports" / "Micron" / "final-report.md"), "--snapshot", snap_path],
            capture_output=True,
            text=True,
        )
        self.assertNotIn("audit: pass", hijack.stdout)
        self.assertNotEqual(hijack.returncode, 0)


class TestRoundThreeBypasses(unittest.TestCase):
    def test_slash_spans_and_fused_identifiers_are_scanned(self):
        snap = _mu()
        samples = (
            "`99,999,999,999 USD/yr`\n",
            "`$999B / 9.9B shares`\n",
            "`Market cap $999,999,999,999 (close/shares)`\n",
            "`DRAM ASP $3.50/GB`\n",
            "`P/E 15`\n",
            "`US$412/share`\n",
            "`USD99999`\n",
            "`Revenue_99999`\n",
        )
        for line in samples:
            result = audit_report(line, snap, None, {})
            self.assertEqual(result.status, "fail", line)

    def test_current_year_and_capital_structure_synonyms_are_blocked(self):
        snap = _mu(
            annual=_mu().annual
            + (
                AnnualFact(
                    2026,
                    date(2026, 8, 28),
                    "revenue",
                    Decimal("133188000000"),
                    date(2026, 10, 1),
                    "Revenues",
                ),
            )
        )
        empty = SourceLedger("MU", ())
        for measure in (
            "profit_2026",
            "revenue_2026",
            "net_income_2026",
            "nongaap_market_cap",
            "nongaap_shares",
            "turnover",
            "topline",
            "bottom_line",
        ):
            claim = _cited("alias", measure, "99000000000", CitedUnit.USD_ONES, "https://www.reuters.com/markets/example")
            with self.assertRaises(ValueError, msg=measure):
                admit(empty, claim, snap)
        qualified = _cited(
            "seg-rev",
            "segment_total_revenue",
            "150000000000",
            CitedUnit.USD_ONES,
            "https://www.reuters.com/markets/example",
        )
        ledger = admit(empty, qualified, snap)
        line = citation_lines(snap, ledger, {}, {})[qualified.id][0]
        hidden = audit_report(line + "\n", snap, ledger, {})
        self.assertEqual(hidden.status, "fail")
        self.assertTrue(any("133188000000" in item or "snapshot" in item for item in hidden.failures))
        prose = audit_report(f"GAAP net income {line}\n", snap, ledger, {})
        self.assertEqual(prose.status, "fail")
        self.assertIn("measure=segment_total_revenue", line)
        nongap = _cited(
            "ng-ni",
            "nongaap_net_income",
            "999999",
            CitedUnit.USD_ONES,
            "https://www.reuters.com/markets/example",
        )
        nongap_ledger = admit(SourceLedger("MU", ()), nongap, _mu())
        nongap_line = citation_lines(_mu(), nongap_ledger, {}, {})[nongap.id][0]
        worded = audit_report(f"GAAP net income 1000 {nongap_line}\n", _mu(), nongap_ledger, {})
        self.assertEqual(worded.status, "fail")
        self.assertTrue(any("gaap" in item.lower() or "worded" in item for item in worded.failures))

    def test_other_score_marks_need_a_ledger(self):
        snap = _mu()
        for text in (
            "Verdict ⭐⭐⭐⭐\nShares 100 as of 2026-08-28.\n",
            "☆☆☆\nShares 100 as of 2026-08-28.\n",
            "评级四星\nShares 100 as of 2026-08-28.\n",
        ):
            result = audit_report(text, snap, None, {})
            self.assertEqual(result.status, "fail", text)
            self.assertTrue(any("star" in item or "score" in item for item in result.failures), result.failures)

    def test_growth_of_minus_one_and_a_nonpositive_irr_profit_fail_cleanly(self):
        snap = _mu()
        base = TestDerive()._rates(snap)
        flat = _cited("g-flat", "growth_flat", "-1", CitedUnit.RATIO, "https://www.ft.com/g/flat")
        ledger = admit(base, flat, snap)
        request = ThreeScenario(
            ClaimId("scenario-flat"),
            (ClaimId("g-flat"), ClaimId("g-base"), ClaimId("g-bear")),
            (ClaimId("pe-bull"), ClaimId("pe-base"), ClaimId("pe-bear")),
        )
        with self.assertRaises(ValueError) as caught:
            derive(ledger, snap, request)
        self.assertIn("greater than -1", str(caught.exception))
        loss = _cited("profit-loss", "profit_2037", "-5", CitedUnit.USD_ONES, "https://www.trendforce.com/profit")
        zero = _cited("profit-zero", "terminal_zero", "0", CitedUnit.USD_ONES, "https://www.reuters.com/profit")
        ledger = admit(admit(ledger, loss, snap), zero, snap)
        for profit_id in ("profit-loss", "profit-zero"):
            with self.assertRaises(ValueError) as irr_caught:
                derive(ledger, snap, IrrRequest(ClaimId("irr-" + profit_id), ClaimId(profit_id), ClaimId("pe-base")))
            self.assertIn("profit", str(irr_caught.exception).lower())

    def test_fy_label_is_a_year_and_insider_words_are_not_shares(self):
        snap = _mu(
            annual=_mu().annual
            + (
                AnnualFact(
                    2026,
                    date(2026, 8, 28),
                    "revenue",
                    Decimal("133188000000"),
                    date(2026, 10, 1),
                    "Revenues",
                ),
            ),
            insiders=(
                InsiderTrade(
                    date(2026, 10, 14),
                    date(2026, 10, 15),
                    "RAY",
                    "S",
                    "D",
                    Decimal("40.00"),
                    Decimal("947.29"),
                    "https://www.sec.gov/Archives/example.xml",
                ),
            ),
        )
        year = audit_report("FY2026 revenue was 133,188,000,000.\n", snap, None, {})
        self.assertEqual(year.status, "pass", year.failures)
        bare = audit_report("shares 40.00\n", snap, None, {})
        self.assertEqual(bare.status, "fail")
        named = audit_report("owner transaction shares 40.00 price 947.29\n", snap, None, {})
        self.assertEqual(named.status, "pass", named.failures)

    def test_chinese_ratios_are_scanned(self):
        snap = _mu(
            annual=(
                AnnualFact(
                    2026,
                    date(2026, 8, 28),
                    "net_income",
                    Decimal("1001"),
                    date(2026, 10, 1),
                    "NetIncomeLoss",
                ),
            )
        )
        for text in ("增速约三成。\n", "估值三倍。\n", "仓位三分之一。\n", "利率零点五。\n", "规模壹仟。\n"):
            result = audit_report(text, snap, None, {})
            self.assertEqual(result.status, "fail", text)

    def test_exhibit_filename_without_a_hyphen_is_read(self):
        accession = "0000723125-26-000099"
        cover = "https://www.sec.gov/Archives/edgar/data/723125/000072312526000099/mu-8k.htm"
        exhibit = "https://www.sec.gov/Archives/edgar/data/723125/000072312526000099/exhibit99-1.htm"
        index = "https://www.sec.gov/Archives/edgar/data/723125/000072312526000099/index.json"
        sentence = "Revenue was strong."
        snap = _mu(filings=(FilingRef("8-K", date(2026, 10, 1), accession, cover),))
        pages = {
            cover: b"<html><p>Cover only.</p></html>",
            index: json.dumps({"directory": {"item": [
                {"name": "mu-8k.htm", "type": "8-K"},
                {"name": "exhibit99-1.htm", "type": "EXHIBIT-99.1"},
            ]}}).encode(),
            exhibit: f"<html><p>{sentence}</p></html>".encode(),
        }

        def fake_get(url, user_agent, **kwargs):
            body = pages.get(url)
            return (200, body) if body is not None else (404, b"")

        with tempfile.TemporaryDirectory() as directory:
            snapshot_path = os.path.join(directory, "us-snapshot-MU.json")
            ledger_path = os.path.join(directory, "source-ledger.json")
            out_path = os.path.join(directory, "excerpts", "earnings-release.txt")
            with open(snapshot_path, "w", encoding="utf-8") as handle:
                json.dump(snap.to_json(), handle)
            argv = [
                "admit", "excerpt",
                "--ledger", ledger_path,
                "--snapshot", snapshot_path,
                "--id", "earnings-release",
                "--measure", "earnings_release",
                "--accession", accession,
                "--contains", sentence,
                "--out", out_path,
            ]
            with patch.object(source_ledger, "http_get", fake_get), patch.object(
                source_ledger, "sec_user_agent", return_value=_AGENT
            ), contextlib.redirect_stdout(io.StringIO()):
                code = source_ledger.main(argv)
            self.assertEqual(code, 0)
            stored = load_ledger(Path(ledger_path).read_text(encoding="utf-8"))
            self.assertEqual(stored.claims[0].document_url, exhibit)

    def test_peer_rejects_the_subject_ticker_and_cik(self):
        snapshot_path = str(_ROOT / "reports" / "Micron" / "evidence" / "us-snapshot-MU.json")
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = os.path.join(directory, "source-ledger.json")
            write_ledger(ledger_path, SourceLedger("MU", ()), "")
            argv = [
                "admit", "peer",
                "--ledger", ledger_path,
                "--id", "mu-revenue",
                "--measure", "peer_mu_revenue",
                "--snapshot", snapshot_path,
                "--concept", "revenue",
                "--fiscal-year", "2026",
            ]
            stderr = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
                code = source_ledger.main(argv)
            self.assertEqual(code, 1, stderr.getvalue())
            self.assertIn("subject", stderr.getvalue().lower())
        cik_path = _ROOT / "tests" / "fixtures" / "us" / "peer-same-cik.json"
        twin = _mu(
            ticker="NVDA",
            filings=(
                FilingRef(
                    "10-K",
                    date(2026, 10, 1),
                    "0000723125-26-000099",
                    "https://www.sec.gov/Archives/edgar/data/723125/nvda.htm",
                ),
            ),
        )
        cik_path.write_text(json.dumps(twin.to_json()), encoding="utf-8")
        try:
            with tempfile.TemporaryDirectory() as directory:
                ledger_path = os.path.join(directory, "source-ledger.json")
                subject_path = os.path.join(directory, "us-snapshot-MU.json")
                write_ledger(ledger_path, SourceLedger("MU", ()), "")
                subject_path_obj = Path(subject_path)
                subject_path_obj.write_text(json.dumps(_mu().to_json()), encoding="utf-8")
                argv = [
                    "admit", "peer",
                    "--ledger", ledger_path,
                    "--id", "same-cik",
                    "--measure", "peer_same_cik",
                    "--snapshot", str(cik_path),
                    "--concept", "revenue",
                    "--fiscal-year", "2026",
                ]
                stderr = io.StringIO()
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
                    code = source_ledger.main(argv)
                self.assertEqual(code, 1, stderr.getvalue())
                self.assertIn("subject", stderr.getvalue().lower())
        finally:
            cik_path.unlink(missing_ok=True)


def _profit_snapshot() -> IssuerSnapshot:
    return _mu(
        annual=(
            AnnualFact(
                2026,
                date(2026, 8, 28),
                "net_income",
                Decimal("84969000000"),
                date(2026, 10, 1),
                "NetIncomeLoss",
            ),
            AnnualFact(
                2026,
                date(2026, 8, 28),
                "revenue",
                Decimal("133188000000"),
                date(2026, 10, 1),
                "Revenues",
            ),
        )
    )


class TestRoundFourBypasses(unittest.TestCase):
    def test_current_period_profit_aliases_cannot_replace_gaap(self):
        snap = _profit_snapshot()
        empty = SourceLedger("MU", ())
        for measure in (
            "profit_reported",
            "profit_actual",
            "reported_profit",
            "profit_fy2026",
            "profit_fy2025",
            "profit_fy26",
            "profit_ttm",
            "profit_last_year",
            "annual_profit",
            "profit_latest",
        ):
            claim = _cited(
                "alias",
                measure,
                "99000000000",
                CitedUnit.USD_ONES,
                "https://www.reuters.com/markets/example",
            )
            try:
                ledger = admit(empty, claim, snap)
            except ValueError as error:
                self.assertIn("net_income", str(error))
                continue
            line = citation_lines(snap, ledger, {}, {})[claim.id][0]
            for prose in (
                f"Fiscal 2026 GAAP net income {line}\n",
                f"净利润 {line}\n",
            ):
                result = audit_report(prose, snap, ledger, {})
                self.assertEqual(result.status, "fail", (measure, prose, result.failures))
        future = _cited(
            "forward",
            "profit_2036",
            "99000000000",
            CitedUnit.USD_ONES,
            "https://www.reuters.com/markets/example",
        )
        ledger = admit(empty, future, snap)
        line = citation_lines(snap, ledger, {}, {})[future.id][0]
        worded = audit_report(f"Fiscal 2026 GAAP net income {line}\n", snap, ledger, {})
        self.assertEqual(worded.status, "fail", worded.failures)
        chinese = audit_report(f"净利润 {line}\n", snap, ledger, {})
        self.assertEqual(chinese.status, "fail", chinese.failures)

    def test_a_named_concept_must_own_the_snapshot_number(self):
        snap = _profit_snapshot()
        stolen = audit_report("Net income 133,188,000,000\n", snap, None, {})
        self.assertEqual(stolen.status, "fail", stolen.failures)
        owned = audit_report("Revenue 133,188,000,000\n", snap, None, {})
        self.assertEqual(owned.status, "pass", owned.failures)
        same = audit_report("Fiscal 2026 net income 84,969,000,000\n", snap, None, {})
        self.assertEqual(same.status, "pass", same.failures)

    def test_english_magnitudes_are_scanned(self):
        snap = _mu()
        for text in (
            "The figure is one trillion.\n",
            "Guidance is ninety-nine billion.\n",
            "The bid is a hundred billion.\n",
            "It costs 12 billion dollars.\n",
        ):
            result = audit_report(text, snap, None, {})
            self.assertEqual(result.status, "fail", text)

    def test_memory_labels_and_operating_measures_stay_citeable(self):
        snap = _mu()
        note = (
            "HBM3E 12-Hi on 1-gamma and 1γ, 232-layer, Q4 FY2026, FY26, Q1, Top 3, 2x, DDR5 and LPDDR5X.\n"
            "Shares 100 as of 2026-08-28.\n"
        )
        result = audit_report(note, snap, None, {})
        self.assertEqual(result.status, "pass", result.failures)
        for measure in (
            "hbm_share",
            "market_share",
            "dram_bit_share",
            "inventory_days",
            "dram_cash_cost",
            "eps_growth_bull",
        ):
            claim = _cited("metric", measure, "0.12", CitedUnit.RATIO, "https://www.trendforce.com/example/ddr5")
            admit(SourceLedger("MU", ()), claim, snap)
        with self.assertRaises(ValueError) as caught:
            admit(
                SourceLedger("MU", ()),
                _cited("alias", "net_profit", "1", CitedUnit.USD_ONES, "https://www.reuters.com/markets/example"),
                snap,
            )
        self.assertIn("net_income", str(caught.exception))

    def test_more_score_marks_need_a_ledger(self):
        snap = _mu()
        for text in (
            "✪✪✪\nShares 100 as of 2026-08-28.\n",
            "✭✭✭✭\nShares 100 as of 2026-08-28.\n",
            "🌟🌟\nShares 100 as of 2026-08-28.\n",
            "****\nShares 100 as of 2026-08-28.\n",
            "●●●●○\nShares 100 as of 2026-08-28.\n",
            "■■■□□\nShares 100 as of 2026-08-28.\n",
            "four stars\nShares 100 as of 2026-08-28.\n",
        ):
            result = audit_report(text, snap, None, {})
            self.assertEqual(result.status, "fail", text)
            self.assertTrue(any("star" in item or "score" in item for item in result.failures), result.failures)

    def test_huge_scenario_years_fail_cleanly(self):
        snap = _mu()
        ledger = TestDerive()._rates(snap)
        request = ThreeScenario(
            ClaimId("scenario-huge"),
            (ClaimId("g-bull"), ClaimId("g-base"), ClaimId("g-bear")),
            (ClaimId("pe-bull"), ClaimId("pe-base"), ClaimId("pe-bear")),
            years=10000,
        )
        with self.assertRaises(ValueError) as caught:
            derive(ledger, snap, request)
        self.assertNotIn("Overflow", str(caught.exception))


def _cycle_snapshot() -> IssuerSnapshot:
    return _mu(
        prints=(
            MarketPrint(
                "MU",
                Decimal("904.9"),
                PrintKind.OFFICIAL_CLOSE,
                datetime(2026, 10, 19, 20, 0, tzinfo=timezone.utc),
                "yahoo_chart",
            ),
        ),
        shares=ShareCount(Decimal("1131423212"), date(2026, 10, 2), "EntityCommonStockSharesOutstanding"),
        annual=(
            AnnualFact(2026, date(2026, 9, 3), "net_income", Decimal("84969000000"), date(2026, 10, 9), "NetIncomeLoss"),
            AnnualFact(2026, date(2026, 9, 3), "revenue", Decimal("133188000000"), date(2026, 10, 9), "Revenues"),
            AnnualFact(2025, date(2025, 8, 28), "revenue", Decimal("37378000000"), date(2025, 10, 3), "Revenues"),
            AnnualFact(2023, date(2023, 8, 31), "net_income", Decimal("-5833000000"), date(2023, 10, 6), "NetIncomeLoss"),
            AnnualFact(2023, date(2023, 8, 31), "revenue", Decimal("15540000000"), date(2023, 10, 6), "Revenues"),
        ),
    )


def _audited(snap: IssuerSnapshot, measure: str, value: str, prose: str, unit: CitedUnit = CitedUnit.USD_ONES, url: str = "https://www.reuters.com/markets/example"):
    claim = _cited("cited", measure, value, unit, url)
    ledger = admit(SourceLedger("MU", ()), claim, snap)
    line = citation_lines(snap, ledger, {}, {})[claim.id][0]
    return audit_report(prose.format(line=line), snap, ledger, {})


class TestRoundFiveBypasses(unittest.TestCase):
    def test_prose_label_rejects_a_mislabeled_citation(self):
        snap = _cycle_snapshot()
        samples = (
            ("capex_2026", "99000000000", "Fiscal 2026 GAAP net income was {line}.\n"),
            ("buyback_amount", "2000000000000", "Market cap is {line}.\n"),
            ("wafer_starts", "2000000000", "Shares outstanding: {line}.\n", CitedUnit.COUNT),
            ("dram_cash_cost", "150000000000", "Fiscal 2026 revenue was {line}.\n"),
            ("hbm_tam", "150000000000", "收入为 {line}。\n"),
            ("hbm_tam", "99000000000", "净利润为 {line}。\n"),
            ("profit_2036", "99000000000", "Bottom line was {line}.\n"),
            ("capex_2026", "99000000000", "Bottom line was {line}.\n"),
            ("buyback_amount", "2000000000000", "EV is {line}.\n"),
        )
        for sample in samples:
            measure, value, prose = sample[0], sample[1], sample[2]
            unit = sample[3] if len(sample) > 3 else CitedUnit.USD_ONES
            result = _audited(snap, measure, value, prose, unit)
            self.assertEqual(result.status, "fail", (measure, prose, result.failures))
            self.assertTrue(any("worded" in item for item in result.failures), result.failures)
        explicit = _audited(snap, "profit_2036", "99000000000", "Bottom line in 2036 was {line}.\n")
        self.assertEqual(explicit.status, "pass", explicit.failures)

    def test_valuation_multiples_and_oversized_labels_need_a_citation(self):
        snap = _mu()
        blocked = (
            "Micron trades at 150x earnings.\n",
            "P/E of 150x.\n",
            "EV/EBITDA 12x.\n",
            "Market cap is 50x revenue.\n",
            "Net income grew 99x.\n",
            "Micron trades at 4x book.\n",
            "Top 25 customers.\n",
            "The die is 1200-layer.\n",
            "HBM12 is the roadmap.\n",
            "DDR10 is not a product.\n",
            "The stack is 40-Hi.\n",
            "The plan is FY2035.\n",
            "The node is FY1999.\n",
        )
        for text in blocked:
            result = audit_report(text, snap, None, {})
            self.assertEqual(result.status, "fail", (text, result.failures))
        allowed = (
            "The die is 4x.\nShares 100 as of 2026-08-28.\n",
            "HBM3E 12-Hi, 232-layer, Top 3, FY26, FY2031, DDR5 and LPDDR5X.\nShares 100 as of 2026-08-28.\n",
        )
        for text in allowed:
            result = audit_report(text, snap, None, {})
            self.assertEqual(result.status, "pass", (text, result.failures))

    def test_common_phrasing_owns_the_named_concept(self):
        snap = _cycle_snapshot()
        stolen = (
            "Net income for fiscal 2026 was 133,188,000,000.\n",
            "Net income, per the 10-K, was 133,188,000,000.\n",
            "Net income, per the 8-K, was 133,188,000,000.\n",
            "Net income, per Form 4, was 133,188,000,000.\n",
            "Fiscal 2023 revenue was 133,188,000,000.\n",
            "Revenue fell. Net income was 133,188,000,000.\n",
            "133,188,000,000 of net income.\n",
            "Bottom line was 133,188,000,000.\n",
            "Top line was 84,969,000,000.\n",
            "Income was 133,188,000,000.\n",
            "收入为 84,969,000,000。\n",
            "市值为 133,188,000,000。\n",
            "Net income was $133.2 billion.\n",
            "| Metric | FY2023 |\n| --- | --- |\n| Revenue | 133,188,000,000 |\n",
            "|  | FY2026 |\n| --- | --- |\n| Net income | 133,188,000,000 |\n",
        )
        for text in stolen:
            result = audit_report(text, snap, None, {})
            self.assertEqual(result.status, "fail", (text, result.failures))
        owned = (
            "Fiscal 2026 revenue was 133,188,000,000.\n",
            "Fiscal 2023 revenue was 15,540,000,000.\n",
            "133,188,000,000 of revenue.\n",
            "Bottom line was 84,969,000,000.\n",
            "Top line was 133,188,000,000.\n",
            "Income was 84,969,000,000.\n",
            "收入为 133,188,000,000。\n",
            "Revenue was $133.2 billion.\n",
            "Net income was $85.0B.\n",
            "收入为1331.88亿。\n",
            "|  | FY2026 | FY2023 |\n| --- | --- | --- |\n| Revenue | 133,188,000,000 | 15,540,000,000 |\n| Net income | 84,969,000,000 | -5,833,000,000 |\n",
        )
        for text in owned:
            result = audit_report(text, snap, None, {})
            self.assertEqual(result.status, "pass", (text, result.failures))

    def test_product_labels_rounded_figures_and_bullets_stay_quiet(self):
        snap = _cycle_snapshot()
        quiet = (
            "The plan covers the next 10 years.\n",
            "Gen 5, G9 NAND, 8-high, 24GB, 128 GB, 300mm and 7nm.\n",
            "In 2027 the node is still open. CY2026 is the filed year.\n",
            "| 2024 | 2025 | 2026 |\n| --- | --- | --- |\n| cycle | cycle | cycle |\n",
            "● DRAM is the larger slice.\n",
            "■ Note on the cycle.\n",
        )
        for text in quiet:
            result = audit_report(text, snap, None, {})
            self.assertEqual(result.status, "pass", (text, result.failures))
        for text in ("♦♦♦\n", "✶✶✶\n"):
            result = audit_report(text + "Shares outstanding are 1131423212.\n", snap, None, {})
            self.assertEqual(result.status, "fail", text)
            self.assertTrue(any("star" in item or "score" in item for item in result.failures), result.failures)
        unlabeled = audit_report("The figure is $133.2 billion.\n", snap, None, {})
        self.assertEqual(unlabeled.status, "fail", unlabeled.failures)
        tight = audit_report("Net income was $84.9 billion.\n", snap, None, {})
        self.assertEqual(tight.status, "fail", tight.failures)

    def test_realistic_micron_note_passes(self):
        snap = _cycle_snapshot()
        segment = _cited(
            "dram-rev",
            "segment_dram_revenue",
            "50000000000",
            CitedUnit.USD_ONES,
            "https://www.reuters.com/markets/micron-dram",
        )
        price = _cited(
            "asp",
            "dram_contract_price",
            "3.50",
            CitedUnit.USD_PER_GB,
            "https://www.trendforce.com/example/ddr5",
        )
        terminal = _cited(
            "terminal",
            "profit_2036",
            "99000000000",
            CitedUnit.USD_ONES,
            "https://www.reuters.com/markets/micron-terminal",
        )
        tam = _cited(
            "tam",
            "hbm_tam",
            "150000000000",
            CitedUnit.USD_ONES,
            "https://www.trendforce.com/example/hbm",
        )
        ledger = admit(admit(admit(admit(SourceLedger("MU", ()), segment, snap), price, snap), terminal, snap), tam, snap)
        lines = citation_lines(snap, ledger, {}, {})
        note = f"""---
title: Micron sample note
date: 2026-10-20
---

# Micron sample note, 2026-10-20

Data cutoff is 2026-10-20. Evidence is the issuer snapshot. Not investment advice.

The official close is 904.9 USD. Shares outstanding are 1131423212. Market cap is 1023824864538.8 USD.

Fiscal 2026 revenue was 133,188,000,000. Revenue was $133.2 billion. 收入为1331.88亿。
Net income was $85.0B. The bottom line was 84,969,000,000. Fiscal 2023 revenue was 15,540,000,000.
FY2026 revenue was 133,188,000,000 and net income was 84,969,000,000.
Revenue rose to 133,188,000,000 from 37,378,000,000, and net income to 84,969,000,000.
Shares outstanding were 1,131,423,212 and market cap was 1,023,824,864,538.8.
Revenue was $133.2 billion and net income was $85 billion. Net income was nearly $85 billion. Market cap was $1.02T.

DRAM revenue was {lines[segment.id][0]} of total revenue 133,188,000,000.
The DRAM contract price was {lines[price.id][0]}.
Terminal profit {lines[terminal.id][0]}. Fiscal 2036 net income {lines[terminal.id][0]}.
HBM TAM, roughly half of Micron's revenue, is {lines[tam.id][0]}.
PCIe Gen5 x16, 9th-gen, 1TB, and 1.5x bandwidth.

HBM3E 12-Hi, G9 NAND, 8-high, 24GB and 128 GB dies, 300mm wafers, 7nm, Gen 5.
Over the next 10 years, In 2027 the stack is still 2x. CY2026 is the latest filed year.

|  | FY2026 | FY2023 |
| --- | --- | --- |
| Revenue | 133,188,000,000 | 15,540,000,000 |
| Net income | 84,969,000,000 | -5,833,000,000 |

| 2024 | 2025 | 2026 |
| --- | --- | --- |
| cycle | cycle | cycle |

● DRAM is the larger slice.
■ Note on the cycle.
"""
        result = audit_report(note, snap, ledger, {})
        self.assertEqual(result.status, "pass", result.failures)


class TestRoundSixBypasses(unittest.TestCase):
    def test_a_leading_label_keeps_the_number_in_its_clause(self):
        snap = _cycle_snapshot()
        sentences = (
            "FY2026 revenue was 133,188,000,000 and net income was 84,969,000,000.\n",
            "Revenue was 133,188,000,000; net income was 84,969,000,000.\n",
            "Net income was 84,969,000,000 on revenue of 133,188,000,000.\n",
            "Revenue rose to 133,188,000,000 from 37,378,000,000, and net income to 84,969,000,000.\n",
            "Shares outstanding were 1,131,423,212 and market cap was 1,023,824,864,538.8.\n",
            "Revenue was $133.2 billion and net income was $85 billion.\n",
        )
        for text in sentences:
            result = audit_report(text, snap, None, {})
            self.assertEqual(result.status, "pass", (text, result.failures))
        stolen = audit_report("133,188,000,000 in net income.\n", snap, None, {})
        self.assertEqual(stolen.status, "fail", stolen.failures)

    def test_forecast_phrasing_can_name_a_future_profit(self):
        snap = _cycle_snapshot()
        for prose in (
            "Terminal profit {line}.\n",
            "Terminal-year profit {line}.\n",
            "2036 profit {line}.\n",
            "FY2036 profit {line}.\n",
            "Fiscal 2036 net income {line}.\n",
            "2036年净利润 {line}。\n",
        ):
            result = _audited(snap, "profit_2036", "99000000000", prose)
            self.assertEqual(result.status, "pass", (prose, result.failures))
        bare = _audited(snap, "profit_2036", "99000000000", "Bottom line was {line}.\n")
        self.assertEqual(bare.status, "fail", bare.failures)

    def test_rounded_suffixes_and_product_marks_stay_quiet(self):
        snap = _cycle_snapshot()
        quiet = (
            "Net income was $85bn.\n",
            "Net income was $85 bn.\n",
            "Net income was ~$85 billion.\n",
            "Net income was nearly $85 billion.\n",
            "Market cap was $1.02T.\n",
            "PCIe Gen5 x16, 9th-gen, 1TB, and 1.5x bandwidth.\n",
        )
        for text in quiet:
            result = audit_report(text, snap, None, {})
            self.assertEqual(result.status, "pass", (text, result.failures))
        aside = _audited(
            snap,
            "hbm_tam",
            "150000000000",
            "HBM TAM, roughly half of Micron's revenue, is {line}.\n",
        )
        self.assertEqual(aside.status, "pass", aside.failures)


if __name__ == "__main__":
    unittest.main()
