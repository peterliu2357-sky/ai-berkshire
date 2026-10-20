#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import urllib.parse

_TOOLS = os.path.dirname(os.path.abspath(__file__))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from usmarket.fetch import (
    SecConfigError,
    build_snapshot,
    default_cache_dir,
    fetch_quotes,
    http_get,
    sec_user_agent,
)
from usmarket.types import AnnualFact, IssuerSnapshot, snapshot_from_json
from usmarket.value import (
    capex_ratio,
    compare_prints,
    earnings_yield,
    inventory_days,
    market_cap,
    official_close,
    period_days,
    sbc_ratio,
    select_hurdle,
    through_cycle,
)

_TICKER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,12}(?:\.[A-Za-z]{1,4})?$")
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def live_get(url: str) -> tuple[int, bytes]:
    host = urllib.parse.urlparse(url).hostname or ""
    declared = host.endswith("sec.gov") or host.endswith("stlouisfed.org")
    agent = sec_user_agent() if declared else _BROWSER_UA
    cache = None
    if declared or host.endswith("treasury.gov"):
        cache = default_cache_dir()
    return http_get(url, agent, cache_dir=cache)


def _dec(value) -> str:
    return format(value, "f")


def _print_line(item) -> str:
    clock = " clock=bar_stamp" if item.source == "yahoo_daily_close" else ""
    return (
        f"print: price={_dec(item.price)} kind={item.kind.value} "
        f"as_of={item.as_of.isoformat()} source={item.source}{clock}"
    )


def _compare_lines(prints) -> list[str]:
    ordered = sorted(prints, key=lambda item: (item.as_of, item.source, item.kind.value))
    lines = []
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            compared = compare_prints(left, right)
            move = "none" if compared.move is None else _dec(compared.move)
            lines.append(
                "compare: "
                f"left_source={left.source} left_kind={left.kind.value} "
                f"right_source={right.source} right_kind={right.kind.value} "
                f"relation={compared.relation} move={move}"
            )
    return lines


def render_quotes(prints) -> str:
    ordered = sorted(prints, key=lambda item: (item.as_of, item.source, item.kind.value))
    return "\n".join([_print_line(item) for item in ordered] + _compare_lines(ordered))


def _latest_by_year(facts: list[AnnualFact]) -> dict[int, AnnualFact]:
    chosen: dict[int, AnnualFact] = {}
    for fact in facts:
        previous = chosen.get(fact.fiscal_year)
        if previous is None or fact.filed >= previous.filed:
            chosen[fact.fiscal_year] = fact
    return chosen


def render_analysis(snap: IssuerSnapshot) -> str:
    lines = [f"ticker: {snap.ticker}"]
    ordered = sorted(snap.prints, key=lambda item: (item.as_of, item.source, item.kind.value))
    lines.extend(_print_line(item) for item in ordered)
    lines.extend(_compare_lines(ordered))
    for item in snap.labels:
        lines.append(f"label: label={item.label} value={item.value} source={item.source}")
    for item in snap.ranges:
        lines.append(f"range: label={item.label} value={_dec(item.value)} source={item.source}")
    hurdle = select_hurdle(snap.yields)
    if hurdle is None:
        lines.append("hurdle: unavailable")
    else:
        lines.append(
            f"hurdle: rate={_dec(hurdle.rate)} as_of={hurdle.as_of.isoformat()} source={hurdle.source}"
        )
    for item in sorted(snap.percents, key=lambda row: (row.period_end, row.label)):
        lines.append(
            "percent: "
            f"label={item.label} parts_per_hundred={_dec(item.parts_per_hundred)} "
            f"period_end={item.period_end} source={item.source}"
        )
    for item in snap.unscaled:
        lines.append(
            f"unscaled: label={item.label} lexeme={item.lexeme} "
            f"period_end={item.period_end} source={item.source}"
        )
    if snap.unscaled:
        lines.append("unscaled_note: not dollars")
    if snap.annual:
        for fact in sorted(snap.annual, key=lambda row: (row.concept, row.end, row.filed)):
            start = "none" if fact.start is None else fact.start.isoformat()
            lines.append(
                "gaap: "
                f"concept={fact.concept} fiscal_year={fact.fiscal_year} "
                f"start={start} end={fact.end.isoformat()} ones={_dec(fact.ones)} "
                f"tag={fact.tag} filed={fact.filed.isoformat()}"
            )
    else:
        lines.append("gaap: unavailable")
    if snap.shares is None:
        lines.append("shares: unavailable")
    else:
        lines.append(
            f"shares: count={_dec(snap.shares.shares)} as_of={snap.shares.as_of.isoformat()} "
            f"tag={snap.shares.tag}"
        )
    close = official_close(snap.prints)
    cap = None
    if close is None or snap.shares is None:
        lines.append("market_cap: unavailable")
    else:
        cap = market_cap(close.price, snap.shares.shares)
        lines.append(
            f"market_cap: usd={_dec(cap)} price={_dec(close.price)} "
            f"shares={_dec(snap.shares.shares)} source={close.source}"
        )
    income = _latest_by_year([fact for fact in snap.annual if fact.concept == "net_income"])
    cycle = through_cycle([(year, fact.ones) for year, fact in sorted(income.items())])
    if cycle is None:
        lines.append("through_cycle: unavailable")
    else:
        lines.append(
            f"through_cycle: median={_dec(cycle.median)} peak={_dec(cycle.peak)} "
            f"trough={_dec(cycle.trough)} years={','.join(str(year) for year in cycle.fiscal_years)}"
        )
    if cycle is None or cap is None or hurdle is None:
        lines.append("hurdle_check: unavailable")
    else:
        earned = earnings_yield(cycle.median, cap)
        lines.append(
            f"hurdle_check: earnings_yield={_dec(earned)} rate={_dec(hurdle.rate)} "
            f"clears={'yes' if earned > hurdle.rate else 'no'}"
        )
    sbc = _latest_by_year([fact for fact in snap.annual if fact.concept == "sbc"])
    ratio = None
    shared_year = None
    for year in sorted(set(income) & set(sbc)):
        shared_year = year
        ratio = sbc_ratio(sbc[year].ones, income[year].ones)
    if shared_year is None or ratio is None:
        lines.append("sbc: unavailable")
    else:
        lines.append(
            f"sbc: fiscal_year={shared_year} ones={_dec(sbc[shared_year].ones)} "
            f"ratio={_dec(ratio)} note=gaap_net_income_already_deducts_sbc"
        )
    inventories = [fact for fact in snap.annual if fact.concept == "inventory"]
    cogs = [fact for fact in snap.annual if fact.concept == "cogs"]
    inventory_line = "inventory_days: unavailable"
    for inv in sorted(inventories, key=lambda fact: fact.end):
        matches = [row for row in cogs if row.end == inv.end and row.start is not None]
        if not matches:
            continue
        row = max(matches, key=lambda fact: fact.filed)
        days = inventory_days(inv.ones, row.ones, period_days(row.start, row.end))
        inventory_line = (
            f"inventory_days: end={inv.end.isoformat()} days={_dec(days)} "
            f"period_days={period_days(row.start, row.end)}"
        )
    lines.append(inventory_line)
    capex = _latest_by_year([fact for fact in snap.annual if fact.concept == "capex"])
    depreciation = _latest_by_year([fact for fact in snap.annual if fact.concept == "depreciation"])
    capex_line = "capex_ratio: unavailable"
    for year in sorted(set(capex) & set(depreciation)):
        try:
            ratio = capex_ratio(capex[year].ones, depreciation[year].ones)
        except ValueError:
            continue
        capex_line = f"capex_ratio: fiscal_year={year} ratio={_dec(ratio)}"
    lines.append(capex_line)
    for item in snap.failures:
        detail = f" detail={item.detail}" if item.detail else ""
        lines.append(f"failure: source={item.source} status={item.status} url={item.url}{detail}")
    return "\n".join(lines)


def write_snapshot(path: str, snap: IssuerSnapshot) -> None:
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    payload = json.dumps(snap.to_json(), indent=2, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(prefix=".us-snapshot-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="us_market.py")
    sub = parser.add_subparsers(dest="command")
    quote = sub.add_parser("quote")
    quote.add_argument("ticker")
    snap = sub.add_parser("snapshot")
    snap.add_argument("ticker")
    snap.add_argument("--out", required=True)
    analyze = sub.add_parser("analyze")
    analyze.add_argument("--snapshot", required=True)
    return parser


def main(argv: list[str] | None = None, get=None) -> int:
    parser = _parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if not args.command:
        parser.print_help(sys.stderr)
        return 2
    getter = live_get if get is None else get
    if args.command in {"quote", "snapshot"} and not _TICKER.fullmatch(args.ticker):
        print(f"ticker rejected: {args.ticker}", file=sys.stderr)
        return 2
    if args.command == "snapshot":
        try:
            sec_user_agent()
        except SecConfigError as error:
            print(error, file=sys.stderr)
            return 2
    if args.command == "quote":
        prints, failures = fetch_quotes(args.ticker, getter)
        text = render_quotes(prints)
        if text:
            print(text)
        for item in failures:
            print(f"failure: source={item.source} status={item.status} url={item.url}")
        return 0 if prints else 2
    if args.command == "snapshot":
        snap = build_snapshot(args.ticker, getter)
        write_snapshot(args.out, snap)
        print(args.out)
        if snap.prints or snap.yields:
            return 0
        return 2
    try:
        with open(args.snapshot, encoding="utf-8") as handle:
            data = json.load(handle)
        snap = snapshot_from_json(data)
    except (OSError, json.JSONDecodeError, ValueError, KeyError, TypeError) as error:
        print(f"not a snapshot: {error}", file=sys.stderr)
        return 1
    print(render_analysis(snap))
    return 0


if __name__ == "__main__":
    sys.exit(main())
