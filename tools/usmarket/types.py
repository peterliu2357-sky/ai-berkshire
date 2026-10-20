from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class PrintKind(str, Enum):
    OFFICIAL_CLOSE = "official_close"
    INTRADAY_LAST = "intraday_last"
    EXTENDED_HOURS = "extended_hours"


def _dec(value: Decimal) -> str:
    return format(value, "f")


@dataclass(frozen=True)
class MarketPrint:
    ticker: str
    price: Decimal
    kind: PrintKind
    as_of: datetime
    source: str

    def to_json(self) -> dict[str, Any]:
        return {
            "type": "market_print",
            "ticker": self.ticker,
            "price": _dec(self.price),
            "kind": self.kind.value,
            "as_of": self.as_of.isoformat(),
            "source": self.source,
        }


@dataclass(frozen=True)
class UnscaledAmount:
    lexeme: str
    label: str
    period_end: str
    source: str

    def to_json(self) -> dict[str, Any]:
        return {
            "type": "unscaled_amount",
            "lexeme": self.lexeme,
            "label": self.label,
            "period_end": self.period_end,
            "source": self.source,
        }


@dataclass(frozen=True)
class Percent:
    parts_per_hundred: Decimal
    label: str
    period_end: str
    source: str

    def to_json(self) -> dict[str, Any]:
        return {
            "type": "percent",
            "parts_per_hundred": _dec(self.parts_per_hundred),
            "label": self.label,
            "period_end": self.period_end,
            "source": self.source,
        }


@dataclass(frozen=True)
class TreasuryYield:
    as_of: date
    rate: Decimal
    source: str

    def to_json(self) -> dict[str, Any]:
        return {
            "type": "treasury_yield",
            "as_of": self.as_of.isoformat(),
            "rate": _dec(self.rate),
            "source": self.source,
        }


@dataclass(frozen=True)
class FilingRef:
    form: str
    filed: date
    accession: str
    url: str

    def to_json(self) -> dict[str, Any]:
        return {
            "type": "filing_ref",
            "form": self.form,
            "filed": self.filed.isoformat(),
            "accession": self.accession,
            "url": self.url,
        }


@dataclass(frozen=True)
class AnnualFact:
    fiscal_year: int
    end: date
    concept: str
    ones: Decimal
    filed: date
    tag: str
    start: date | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "type": "annual_fact",
            "fiscal_year": self.fiscal_year,
            "end": self.end.isoformat(),
            "start": None if self.start is None else self.start.isoformat(),
            "concept": self.concept,
            "ones": _dec(self.ones),
            "filed": self.filed.isoformat(),
            "tag": self.tag,
        }


@dataclass(frozen=True)
class ShareCount:
    shares: Decimal
    as_of: date
    tag: str

    def to_json(self) -> dict[str, Any]:
        return {
            "type": "share_count",
            "shares": _dec(self.shares),
            "as_of": self.as_of.isoformat(),
            "tag": self.tag,
        }


@dataclass(frozen=True)
class FetchFailure:
    source: str
    status: int
    url: str
    detail: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "type": "fetch_failure",
            "source": self.source,
            "status": self.status,
            "url": self.url,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class SourceLabel:
    label: str
    value: str
    source: str

    def to_json(self) -> dict[str, Any]:
        return {
            "type": "source_label",
            "label": self.label,
            "value": self.value,
            "source": self.source,
        }


@dataclass(frozen=True)
class LabeledDecimal:
    label: str
    value: Decimal
    source: str

    def to_json(self) -> dict[str, Any]:
        return {
            "type": "labeled_decimal",
            "label": self.label,
            "value": _dec(self.value),
            "source": self.source,
        }


@dataclass(frozen=True)
class InsiderTrade:
    transaction_date: date
    filed: date
    owner: str
    code: str
    acquired_disposed: str
    shares: Decimal
    price: Decimal | None
    url: str
    derivative: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "type": "insider_trade",
            "transaction_date": self.transaction_date.isoformat(),
            "filed": self.filed.isoformat(),
            "owner": self.owner,
            "code": self.code,
            "acquired_disposed": self.acquired_disposed,
            "shares": _dec(self.shares),
            "price": None if self.price is None else _dec(self.price),
            "url": self.url,
            "derivative": self.derivative,
        }


@dataclass(frozen=True)
class CacheHit:
    url: str
    cached_at: str
    age_seconds: str

    def to_json(self) -> dict[str, Any]:
        return {
            "type": "cache_hit",
            "url": self.url,
            "cached_at": self.cached_at,
            "age_seconds": self.age_seconds,
        }


@dataclass(frozen=True)
class IssuerSnapshot:
    ticker: str
    prints: tuple[MarketPrint, ...]
    filings: tuple[FilingRef, ...]
    annual: tuple[AnnualFact, ...]
    shares: ShareCount | None
    yields: tuple[TreasuryYield, ...]
    unscaled: tuple[UnscaledAmount, ...]
    percents: tuple[Percent, ...]
    ranges: tuple[LabeledDecimal, ...]
    labels: tuple[SourceLabel, ...]
    insiders: tuple[InsiderTrade, ...]
    failures: tuple[FetchFailure, ...]
    adr_ratio: Decimal | None = None
    cache: tuple[CacheHit, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "type": "issuer_snapshot",
            "ticker": self.ticker,
            "prints": [item.to_json() for item in self.prints],
            "filings": [item.to_json() for item in self.filings],
            "annual": [item.to_json() for item in self.annual],
            "shares": None if self.shares is None else self.shares.to_json(),
            "yields": [item.to_json() for item in self.yields],
            "unscaled": [item.to_json() for item in self.unscaled],
            "percents": [item.to_json() for item in self.percents],
            "ranges": [item.to_json() for item in self.ranges],
            "labels": [item.to_json() for item in self.labels],
            "insiders": [item.to_json() for item in self.insiders],
            "failures": [item.to_json() for item in self.failures],
            "adr_ratio": None if self.adr_ratio is None else _dec(self.adr_ratio),
            "cache": [item.to_json() for item in self.cache],
        }


def snapshot_from_json(data: dict[str, Any]) -> IssuerSnapshot:
    if data.get("type") != "issuer_snapshot":
        raise ValueError("not an issuer snapshot")
    shares = data.get("shares")
    return IssuerSnapshot(
        ticker=data["ticker"],
        prints=tuple(_print_from_json(item) for item in data["prints"]),
        filings=tuple(_filing_from_json(item) for item in data["filings"]),
        annual=tuple(_annual_from_json(item) for item in data["annual"]),
        shares=None if shares is None else _shares_from_json(shares),
        yields=tuple(_yield_from_json(item) for item in data["yields"]),
        unscaled=tuple(_unscaled_from_json(item) for item in data["unscaled"]),
        percents=tuple(_percent_from_json(item) for item in data["percents"]),
        ranges=tuple(_range_from_json(item) for item in data["ranges"]),
        labels=tuple(_label_from_json(item) for item in data["labels"]),
        insiders=tuple(_insider_from_json(item) for item in data["insiders"]),
        failures=tuple(_failure_from_json(item) for item in data["failures"]),
        adr_ratio=None if data.get("adr_ratio") in (None, "") else Decimal(str(data["adr_ratio"])),
        cache=tuple(_cache_from_json(item) for item in data.get("cache") or []),
    )


def _print_from_json(item: dict[str, Any]) -> MarketPrint:
    return MarketPrint(
        ticker=item["ticker"],
        price=Decimal(item["price"]),
        kind=PrintKind(item["kind"]),
        as_of=datetime.fromisoformat(item["as_of"]),
        source=item["source"],
    )


def _filing_from_json(item: dict[str, Any]) -> FilingRef:
    return FilingRef(
        form=item["form"],
        filed=date.fromisoformat(item["filed"]),
        accession=item["accession"],
        url=item["url"],
    )


def _annual_from_json(item: dict[str, Any]) -> AnnualFact:
    start = item.get("start")
    return AnnualFact(
        fiscal_year=int(item["fiscal_year"]),
        end=date.fromisoformat(item["end"]),
        concept=item["concept"],
        ones=Decimal(item["ones"]),
        filed=date.fromisoformat(item["filed"]),
        tag=item["tag"],
        start=None if not start else date.fromisoformat(start),
    )


def _shares_from_json(item: dict[str, Any]) -> ShareCount:
    return ShareCount(
        shares=Decimal(item["shares"]),
        as_of=date.fromisoformat(item["as_of"]),
        tag=item["tag"],
    )


def _yield_from_json(item: dict[str, Any]) -> TreasuryYield:
    return TreasuryYield(
        as_of=date.fromisoformat(item["as_of"]),
        rate=Decimal(item["rate"]),
        source=item["source"],
    )


def _unscaled_from_json(item: dict[str, Any]) -> UnscaledAmount:
    if "ones" in item or "number" in item:
        raise ValueError("unscaled amount has no dollar field")
    return UnscaledAmount(
        lexeme=item["lexeme"],
        label=item["label"],
        period_end=item["period_end"],
        source=item["source"],
    )


def _percent_from_json(item: dict[str, Any]) -> Percent:
    return Percent(
        parts_per_hundred=Decimal(item["parts_per_hundred"]),
        label=item["label"],
        period_end=item["period_end"],
        source=item["source"],
    )


def _label_from_json(item: dict[str, Any]) -> SourceLabel:
    return SourceLabel(label=item["label"], value=item["value"], source=item["source"])


def _range_from_json(item: dict[str, Any]) -> LabeledDecimal:
    return LabeledDecimal(
        label=item["label"],
        value=Decimal(item["value"]),
        source=item["source"],
    )


def _insider_from_json(item: dict[str, Any]) -> InsiderTrade:
    price = item.get("price")
    return InsiderTrade(
        transaction_date=date.fromisoformat(item["transaction_date"]),
        filed=date.fromisoformat(item["filed"]),
        owner=item["owner"],
        code=item["code"],
        acquired_disposed=item["acquired_disposed"],
        shares=Decimal(item["shares"]),
        price=None if price is None else Decimal(price),
        url=item["url"],
        derivative=bool(item.get("derivative", False)),
    )


def _cache_from_json(item: dict[str, Any]) -> CacheHit:
    return CacheHit(
        url=item["url"],
        cached_at=str(item["cached_at"]),
        age_seconds=str(item["age_seconds"]),
    )


def _failure_from_json(item: dict[str, Any]) -> FetchFailure:
    return FetchFailure(
        source=item["source"],
        status=int(item["status"]),
        url=item["url"],
        detail=item.get("detail", ""),
    )
