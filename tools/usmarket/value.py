from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, Context, ROUND_HALF_EVEN

from usmarket.types import MarketPrint, PrintKind, TreasuryYield

_CTX = Context(prec=28, rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True)
class PrintComparison:
    relation: str
    move: Decimal | None


@dataclass(frozen=True)
class ThroughCycle:
    fiscal_years: tuple[int, ...]
    median: Decimal
    peak: Decimal
    trough: Decimal
    gaps: tuple[int, ...] = ()


def compare_prints(left: MarketPrint, right: MarketPrint) -> PrintComparison:
    same_day = left.as_of.date() == right.as_of.date()
    if left.kind != right.kind or left.ticker != right.ticker or not same_day:
        return PrintComparison("mixed_session", None)
    if left.price == 0:
        return PrintComparison("same_kind", None)
    move = _CTX.divide(right.price - left.price, left.price)
    return PrintComparison("same_kind", move)


def official_close(prints: tuple[MarketPrint, ...] | list[MarketPrint]) -> MarketPrint | None:
    closes = [item for item in prints if item.kind == PrintKind.OFFICIAL_CLOSE]
    if not closes:
        return None
    return max(closes, key=lambda item: item.as_of)


def market_cap(price: Decimal, shares: Decimal, adr_ratio: Decimal | None = None) -> Decimal:
    count = shares if adr_ratio is None else _CTX.divide(shares, adr_ratio)
    return _CTX.multiply(price, count)


def inventory_days(inventory: Decimal, cogs: Decimal, days: int) -> Decimal:
    if cogs == 0:
        raise ValueError("cogs is zero")
    if days <= 0:
        raise ValueError("period length must be positive")
    per_day = _CTX.divide(inventory, cogs)
    return _CTX.multiply(per_day, Decimal(days))


def capex_ratio(capex: Decimal, depreciation: Decimal) -> Decimal:
    if depreciation == 0:
        raise ValueError("depreciation is zero")
    return _CTX.divide(abs(capex), abs(depreciation))


def sbc_ratio(sbc: Decimal, net_income: Decimal) -> Decimal | None:
    if net_income == 0:
        return None
    return _CTX.divide(sbc, abs(net_income))


def earnings_yield(income: Decimal, cap: Decimal) -> Decimal:
    if cap == 0:
        raise ValueError("market cap is zero")
    return _CTX.divide(income, cap)


def clears_hurdle(income: Decimal, cap: Decimal, hurdle_rate: Decimal) -> bool:
    return earnings_yield(income, cap) > hurdle_rate


def through_cycle(rows: list[tuple[int, Decimal]]) -> ThroughCycle | None:
    if not rows:
        return None
    by_year: dict[int, Decimal] = {}
    for year, amount in rows:
        by_year[int(year)] = amount
    latest = max(by_year)
    start = latest - 9
    window = {year: amount for year, amount in by_year.items() if start <= year <= latest}
    if len(window) < 5:
        return None
    years = tuple(sorted(window))
    gaps = tuple(year for year in range(start, latest + 1) if year not in window)
    values = sorted(window.values(), key=lambda amount: amount)
    mid = len(values) // 2
    if len(values) % 2 == 1:
        median = values[mid]
    else:
        median = _CTX.divide(values[mid - 1] + values[mid], Decimal(2))
    return ThroughCycle(
        fiscal_years=years,
        median=median,
        peak=values[-1],
        trough=values[0],
        gaps=gaps,
    )


def select_hurdle(yields: list[TreasuryYield] | tuple[TreasuryYield, ...]) -> TreasuryYield | None:
    usable = list(yields)
    if not usable:
        return None

    def sort_key(item: TreasuryYield) -> tuple[date, int]:
        treasury_first = 1 if item.source == "treasury_par" else 0
        return (item.as_of, treasury_first)

    return max(usable, key=sort_key)


def period_days(start: date, end: date) -> int:
    return (end - start).days
