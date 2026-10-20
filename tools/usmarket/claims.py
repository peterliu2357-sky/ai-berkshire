from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Context, Decimal
from enum import Enum
from typing import Mapping
from urllib.parse import urlsplit

from financial_rigor import scenario_target_price
from terminal_value import irr_from_terminal
from us_market import ANALYZE_PREFIXES, render_analysis
from usmarket.fetch import _FLOW_TAGS, _INSTANT_TAGS, _SHARE_TAGS
from usmarket.types import IssuerSnapshot
from usmarket.value import market_cap, official_close

_CTX = Context(prec=28, rounding=ROUND_HALF_EVEN)


class Tier(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    LOW = "low"


class CitedUnit(str, Enum):
    USD_ONES = "usd_ones"
    USD_PER_GB = "usd_per_gb"
    USD_PER_SHARE = "usd_per_share"
    MULTIPLE = "multiple"
    RATIO = "ratio"
    PERCENT = "percent"
    COUNT = "count"


class DeriveTool(str, Enum):
    THREE_SCENARIO = "three_scenario"
    IRR = "irr"


_TRUST_RANK = {Tier.PRIMARY: 2, Tier.SECONDARY: 1, Tier.LOW: 0}

PRIMARY_HOSTS: tuple[tuple[str, str], ...] = (
    ("federalregister.gov", "Federal Register"),
    ("bis.gov", "BIS"),
    ("bis.doc.gov", "BIS"),
)

SECONDARY_HOSTS: tuple[tuple[str, str], ...] = (
    ("trendforce.com", "TrendForce"),
    ("dramexchange.com", "DRAMeXchange"),
    ("reuters.com", "Reuters"),
    ("bloomberg.com", "Bloomberg"),
    ("wsj.com", "WSJ"),
    ("ft.com", "FT"),
    ("samsung.com", "Samsung"),
    ("skhynix.com", "SK hynix"),
    ("tsmc.com", "TSMC"),
    ("gartner.com", "Gartner"),
    ("idc.com", "IDC"),
)

_CLAIM_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_FORBIDDEN_LEDGER_TEXT = ("--shares", "--reported", "User-Agent:", "SEC_USER_AGENT")
_FORBIDDEN_JSON_KEYS = frozenset({"tier", "publisher", "user_agent", "email", "headers"})
_NUMBER_TOKEN = re.compile(r"-?\d+(?:,\d{3})*(?:\.\d+)?")
_NUMBER_IN_TEXT = re.compile(r"(?<![\d.])-?\d+(?:,\d{3})*(?:\.\d+)?")
_DATE_STAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\+\d{2}:\d{2}|Z))?"
)
_SLASH_DATE = re.compile(r"\d{1,2}/\d{1,2}/\d{4}")
_FRONT_MATTER_DATE = re.compile(r"(?m)^date:\s*(\d{4}-\d{2}-\d{2})\s*$")
_US_MARKET = re.compile(r"(?m)^market:\s*us\s*$")
_BRACKET_OPEN = re.compile(r"\[(c|q|d|s|dispute):")
_URL_IN_TEXT = re.compile(r"https?://[^\s<>\"']+")
_RESERVED_MEASURES = frozenset({"shares", "market_cap"})


class ClaimId(str):
    def __new__(cls, value: str) -> "ClaimId":
        if not isinstance(value, str) or _CLAIM_ID.fullmatch(value) is None:
            raise ValueError("claim id must match [a-z0-9][a-z0-9-]{0,63}")
        return str.__new__(cls, value)


class Measure(str):
    pass


def weakest(tiers: tuple[Tier, ...]) -> Tier:
    if not tiers:
        raise ValueError("weakest tier needs at least one input")
    return min(tiers, key=lambda item: _TRUST_RANK[item])


def _host_name(url: str) -> str:
    if not url.startswith("https://"):
        raise ValueError("cited url must be https")
    host = urlsplit(url).hostname
    if not host:
        raise ValueError("cited url has no host")
    if host.startswith("www."):
        host = host[4:]
    return host.lower().rstrip(".")


_HOST_PREFIXES = frozenset({"ir", "investors", "investor", "news", "newsroom"})
_ISSUER_SITES = {"MU": "micron.com"}


def _host_prefix(host: str, name: str) -> str | None:
    if host == name:
        return ""
    suffix = "." + name
    if not host.endswith(suffix):
        return None
    label = host[: -len(suffix)]
    if "." in label or label not in _HOST_PREFIXES:
        return None
    return label


def _match_host(host: str, rules: tuple[tuple[str, str], ...]) -> str | None:
    for name, publisher in rules:
        if _host_prefix(host, name) is not None:
            return publisher
    return None


def tier_of_host(url: str) -> tuple[Tier, str]:
    host = _host_name(url)
    primary = _match_host(host, PRIMARY_HOSTS)
    if primary is not None:
        return Tier.PRIMARY, primary
    secondary = _match_host(host, SECONDARY_HOSTS)
    if secondary is not None:
        return Tier.SECONDARY, secondary
    return Tier.LOW, host


_WEBSITE_LABELS = frozenset({"website", "companywebsite", "ir", "companyir"})


def _measure_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _snapshot_measure_keys() -> frozenset[str]:
    keys = {
        "shares",
        "sharecount",
        "sharesoutstanding",
        "marketcap",
        "equityvalue",
        "mcap",
    }
    for concept, tags in {**_FLOW_TAGS, **_INSTANT_TAGS}.items():
        keys.add(_measure_key(concept))
        keys.update(_measure_key(tag) for tag in tags)
    keys.update(_measure_key(tag) for tag in _SHARE_TAGS)
    for prefix in ANALYZE_PREFIXES:
        keys.add(_measure_key(prefix.rstrip(":")))
    return frozenset(keys)


_SNAPSHOT_MEASURE_KEYS = _snapshot_measure_keys()


_CORE_TOKENS = frozenset({
    "income",
    "profit",
    "revenue",
    "sales",
    "eps",
    "earnings",
    "share",
    "shares",
    "equity",
    "ebit",
    "ebitda",
    "cash",
    "debt",
    "asset",
    "assets",
    "cap",
    "capitalization",
    "mktcap",
    "marketcap",
    "ni",
    "rev",
    "fcf",
})
_CORE_JOINED = (
    "netincome",
    "totalrevenue",
    "marketcap",
    "enterprisevalue",
    "dilutedeps",
    "sharesoutstanding",
)
_QUALIFIER_TOKENS = frozenset({"nongaap", "adjusted", "segment", "nonifrs"})


def _measure_tokens(measure: str) -> list[str]:
    return re.findall(r"[a-z]+|\d+", measure.casefold())


def _has_qualifier(measure: str) -> bool:
    tokens = _measure_tokens(measure)
    joined = "".join(tokens)
    if "nongaap" in joined or "nonifrs" in joined:
        return True
    return any(token in _QUALIFIER_TOKENS for token in tokens)


def _profit_blocks(tokens: list[str]) -> bool:
    words = [token for token in tokens if not token.isdigit()]
    if "profit" not in words:
        return False
    companions = [token for token in words if token != "profit"]
    if any(token in {"net", "gross", "operating", "total", "gaap", "pretax"} for token in companions):
        return True
    return not companions and not any(token.isdigit() for token in tokens)


def _core_stem(measure: str) -> bool:
    if _has_qualifier(measure):
        return False
    tokens = _measure_tokens(measure)
    if _profit_blocks(tokens):
        return True
    joined = "".join(re.findall(r"[a-z0-9]+", measure.casefold()))
    if any(token in _CORE_TOKENS and token != "profit" for token in tokens):
        return True
    return any(stem in joined for stem in _CORE_JOINED)


def _measure_blocked(measure: str, snapshot: IssuerSnapshot | None) -> bool:
    if _measure_key(measure) in _SNAPSHOT_MEASURE_KEYS:
        return True
    if snapshot is not None and measure in _blocked_measures(snapshot):
        return True
    return False


def _cited_measure_blocked(measure: str, snapshot: IssuerSnapshot | None) -> bool:
    return _measure_blocked(measure, snapshot) or _core_stem(measure)


def _website_hosts(snapshot: IssuerSnapshot) -> set[str]:
    hosts: set[str] = set()
    for item in snapshot.labels:
        if _measure_key(item.label) not in _WEBSITE_LABELS:
            continue
        for text in (item.label, item.value):
            for match in _URL_IN_TEXT.finditer(text):
                raw = match.group(0).rstrip(".,);]")
                if raw.startswith("http://"):
                    raw = "https://" + raw[len("http://") :]
                try:
                    hosts.add(_host_name(raw))
                except ValueError:
                    continue
    fallback = _ISSUER_SITES.get(snapshot.ticker.upper())
    if fallback:
        hosts.add(fallback)
    return hosts


def _on_issuer_site(url_host: str, issuer_host: str) -> bool:
    return _host_prefix(url_host, issuer_host) is not None


def cited_binding(url: str, snapshot: IssuerSnapshot | None) -> tuple[Tier, str]:
    if snapshot is not None:
        host = _host_name(url)
        if any(_on_issuer_site(host, site) for site in _website_hosts(snapshot)):
            return Tier.PRIMARY, "company IR"
    return tier_of_host(url)


def _sec_host(url: str) -> bool:
    host = _host_name(url)
    return host == "sec.gov" or host.endswith(".sec.gov")


def canonical_decimal(value: Decimal) -> str:
    return format(value, "f")


def _printed_derived(value: Decimal, tool: DeriveTool) -> str:
    quantum = Decimal("0.01") if tool == DeriveTool.THREE_SCENARIO else Decimal("0.0001")
    return format(value.quantize(quantum, rounding=ROUND_HALF_EVEN), "f")


@dataclass(frozen=True)
class Cited:
    id: ClaimId
    measure: Measure
    value: Decimal
    unit: CitedUnit
    url: str
    published: date | None
    accessed: date | None
    inputs: tuple[ClaimId, ...]
    quote_sha256: str

    def __post_init__(self) -> None:
        if self.published is None and self.accessed is None:
            raise ValueError("cited claim needs published or accessed")
        tier_of_host(self.url)
        if len(self.inputs) != len(set(self.inputs)):
            raise ValueError("estimate inputs must be unique")

    @property
    def is_estimate(self) -> bool:
        return len(self.inputs) > 0


@dataclass(frozen=True)
class Excerpt:
    id: ClaimId
    measure: Measure
    accession: str
    sha256: str
    byte_start: int
    byte_end: int
    document_url: str = ""

    def __post_init__(self) -> None:
        if not self.accession or self.byte_start < 0 or self.byte_end <= self.byte_start:
            raise ValueError("excerpt slice must be a non-empty accession range")
        if len(self.sha256) != 64:
            raise ValueError("excerpt sha256 must be 64 hex chars")


@dataclass(frozen=True)
class PeerSnapshot:
    id: ClaimId
    measure: Measure
    snapshot_path: str
    concept: str
    fiscal_year: int


@dataclass(frozen=True)
class Derived:
    id: ClaimId
    tool: DeriveTool
    inputs: tuple[str, ...]
    years: int

    def __post_init__(self) -> None:
        if self.years <= 0:
            raise ValueError("derived years must be positive")
        if any(token in " ".join(self.inputs) for token in ("--shares", "--reported")):
            raise ValueError("derived inputs cannot name --shares or --reported")


@dataclass(frozen=True)
class Dispute:
    id: ClaimId
    measure: Measure
    members: tuple[ClaimId, ...]

    def __post_init__(self) -> None:
        if len(self.members) < 2 or len(self.members) != len(set(self.members)):
            raise ValueError("dispute needs two or more distinct members")


@dataclass(frozen=True)
class Scored:
    id: ClaimId
    stars: int
    anchor: tuple[str, ...]
    context: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.stars, bool) or not isinstance(self.stars, int) or not 1 <= self.stars <= 5:
            raise ValueError("stars must be 1 to 5")
        if len(self.anchor) == 0:
            raise ValueError("a scored verdict needs an anchor")
        if len(self.anchor) != len(set(self.anchor)):
            raise ValueError("anchors must be unique")


@dataclass(frozen=True)
class Withheld:
    id: ClaimId
    context: tuple[str, ...] = ()


Claim = Cited | Excerpt | PeerSnapshot | Derived | Dispute | Scored | Withheld


@dataclass(frozen=True)
class SourceLedger:
    ticker: str
    claims: tuple[Claim, ...]

    def by_id(self) -> dict[ClaimId, Claim]:
        found: dict[ClaimId, Claim] = {}
        for claim in self.claims:
            if claim.id in found:
                raise ValueError(f"duplicate claim id {claim.id}")
            found[claim.id] = claim
        return found


@dataclass(frozen=True)
class AuditResult:
    status: str
    failures: tuple[str, ...]


@dataclass(frozen=True)
class ThreeScenario:
    id: ClaimId
    growth_ids: tuple[ClaimId, ClaimId, ClaimId]
    pe_ids: tuple[ClaimId, ClaimId, ClaimId]
    years: int = 3


@dataclass(frozen=True)
class IrrRequest:
    id: ClaimId
    profit_id: ClaimId
    pe_id: ClaimId
    payout_id: ClaimId | None = None
    years: int = 10


def _reject_ledger_text(text: str) -> None:
    if "@" in text or any(token in text for token in _FORBIDDEN_LEDGER_TEXT):
        raise ValueError("ledger text is rejected")


def _walk_ledger_json(node: object) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _FORBIDDEN_JSON_KEYS or "@" in str(key):
                raise ValueError("ledger text is rejected")
            _walk_ledger_json(value)
    elif isinstance(node, list):
        for item in node:
            _walk_ledger_json(item)
    elif isinstance(node, str) and "@" in node:
        raise ValueError("ledger text is rejected")


def _date_or_none(value: object) -> date | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError("date must be YYYY-MM-DD")
    return date.fromisoformat(value)


def _decimal_value(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("value must be a decimal string")
    try:
        number = Decimal(str(value))
    except Exception as error:
        raise ValueError("value must be a decimal string") from error
    if not number.is_finite():
        raise ValueError("value must be finite")
    return number


def _id_tuple(value: object) -> tuple[ClaimId, ...]:
    if not isinstance(value, list):
        raise ValueError("claim ids must be a list")
    return tuple(ClaimId(item) for item in value)


def _str_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("claim fields must be strings")
    return tuple(value)


def _measure(value: object) -> Measure:
    if not isinstance(value, str) or not value or any(ch.isspace() for ch in value):
        raise ValueError("measure must be a token")
    return Measure(value)


_CITED_FIELDS = (
    "type",
    "id",
    "measure",
    "value",
    "unit",
    "url",
    "published",
    "accessed",
    "inputs",
    "quote_sha256",
)
_EXCERPT_FIELDS = ("type", "id", "measure", "accession", "sha256", "byte_start", "byte_end")
_PEER_FIELDS = ("type", "id", "measure", "snapshot_path", "concept", "fiscal_year")
_DERIVED_FIELDS = ("type", "id", "tool", "inputs", "years")
_DISPUTE_FIELDS = ("type", "id", "measure", "members")
_SCORED_FIELDS = ("type", "id", "stars", "anchor", "context")
_WITHHELD_FIELDS = ("type", "id", "context")
_FIELDS = {
    "cited": _CITED_FIELDS,
    "excerpt": _EXCERPT_FIELDS,
    "peer_snapshot": _PEER_FIELDS,
    "derived": _DERIVED_FIELDS,
    "dispute": _DISPUTE_FIELDS,
    "scored": _SCORED_FIELDS,
    "withheld": _WITHHELD_FIELDS,
}


def _exact_fields(item: dict, fields: tuple[str, ...]) -> None:
    if set(item) != set(fields):
        raise ValueError("ledger claim fields do not match the claim type")


def _claim_from_json(item: object) -> Claim:
    if not isinstance(item, dict):
        raise ValueError("ledger claim must be an object")
    kind = item.get("type")
    fields = _FIELDS.get(kind) if isinstance(kind, str) else None
    if fields is None:
        raise ValueError("unknown claim type")
    claim_id = ClaimId(item["id"])
    if kind == "excerpt":
        keys = set(item)
        if keys != set(fields) and keys != set(fields) | {"document_url"}:
            raise ValueError("ledger claim fields do not match the claim type")
        document_url = item.get("document_url", "")
        if not isinstance(document_url, str):
            raise ValueError("excerpt document url is rejected")
        return Excerpt(
            claim_id,
            _measure(item["measure"]),
            str(item["accession"]),
            str(item["sha256"]),
            int(item["byte_start"]),
            int(item["byte_end"]),
            document_url,
        )
    _exact_fields(item, fields)
    if kind == "cited":
        return Cited(
            claim_id,
            _measure(item["measure"]),
            _decimal_value(item["value"]),
            CitedUnit(item["unit"]),
            item["url"],
            _date_or_none(item["published"]),
            _date_or_none(item["accessed"]),
            _id_tuple(item["inputs"]),
            item["quote_sha256"] if isinstance(item["quote_sha256"], str) else "",
        )
    if kind == "peer_snapshot":
        return PeerSnapshot(
            claim_id,
            _measure(item["measure"]),
            str(item["snapshot_path"]),
            str(item["concept"]),
            int(item["fiscal_year"]),
        )
    if kind == "derived":
        return Derived(
            claim_id,
            DeriveTool(item["tool"]),
            _str_tuple(item["inputs"]),
            int(item["years"]),
        )
    if kind == "dispute":
        return Dispute(claim_id, _measure(item["measure"]), _id_tuple(item["members"]))
    if kind == "scored":
        stars = item["stars"]
        if isinstance(stars, bool) or not isinstance(stars, int):
            raise ValueError("stars must be 1 to 5")
        return Scored(claim_id, stars, _str_tuple(item["anchor"]), _str_tuple(item["context"]))
    return Withheld(claim_id, _str_tuple(item["context"]))


def load_ledger(text: str) -> SourceLedger:
    _reject_ledger_text(text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError("ledger json is invalid") from error
    _walk_ledger_json(data)
    if not isinstance(data, dict) or set(data) != {"ticker", "claims"}:
        raise ValueError("ledger shape is invalid")
    if not isinstance(data["ticker"], str) or not isinstance(data["claims"], list):
        raise ValueError("ledger shape is invalid")
    ledger = SourceLedger(data["ticker"], tuple(_claim_from_json(item) for item in data["claims"]))
    ledger.by_id()
    return ledger


def _date_json(value: date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _claim_json(claim: Claim) -> dict:
    if isinstance(claim, Cited):
        return {
            "type": "cited",
            "id": str(claim.id),
            "measure": str(claim.measure),
            "value": canonical_decimal(claim.value),
            "unit": claim.unit.value,
            "url": claim.url,
            "published": _date_json(claim.published),
            "accessed": _date_json(claim.accessed),
            "inputs": [str(item) for item in claim.inputs],
            "quote_sha256": claim.quote_sha256,
        }
    if isinstance(claim, Excerpt):
        return {
            "type": "excerpt",
            "id": str(claim.id),
            "measure": str(claim.measure),
            "accession": claim.accession,
            "sha256": claim.sha256,
            "byte_start": claim.byte_start,
            "byte_end": claim.byte_end,
            **({"document_url": claim.document_url} if claim.document_url else {}),
        }
    if isinstance(claim, PeerSnapshot):
        return {
            "type": "peer_snapshot",
            "id": str(claim.id),
            "measure": str(claim.measure),
            "snapshot_path": claim.snapshot_path,
            "concept": claim.concept,
            "fiscal_year": claim.fiscal_year,
        }
    if isinstance(claim, Derived):
        return {
            "type": "derived",
            "id": str(claim.id),
            "tool": claim.tool.value,
            "inputs": list(claim.inputs),
            "years": claim.years,
        }
    if isinstance(claim, Dispute):
        return {
            "type": "dispute",
            "id": str(claim.id),
            "measure": str(claim.measure),
            "members": [str(item) for item in claim.members],
        }
    if isinstance(claim, Scored):
        return {
            "type": "scored",
            "id": str(claim.id),
            "stars": claim.stars,
            "anchor": list(claim.anchor),
            "context": list(claim.context),
        }
    return {"type": "withheld", "id": str(claim.id), "context": list(claim.context)}


def dumps_ledger(ledger: SourceLedger) -> str:
    payload = {
        "ticker": ledger.ticker,
        "claims": [_claim_json(claim) for claim in ledger.claims],
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    _reject_ledger_text(text)
    _walk_ledger_json(json.loads(text))
    return text


def assert_no_secret(text: str, agent: str) -> None:
    if "User-Agent:" in text or "SEC_USER_AGENT" in text:
        raise ValueError("artifact contains a user-agent header")
    if agent and agent in text:
        raise ValueError("artifact contains the SEC user agent")


def write_ledger(path: str, ledger: SourceLedger, agent: str) -> None:
    payload = dumps_ledger(ledger)
    assert_no_secret(payload, agent)
    tmp = path + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            if handle.read() == payload:
                return
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, payload.encode("utf-8"))
        os.fsync(fd)
    except Exception:
        os.close(fd)
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    os.close(fd)
    os.replace(tmp, path)


def visible_text(body: bytes, content_type: str) -> str:
    text = body.decode("utf-8", "replace")
    kind = (content_type or "").lower()
    if kind:
        markup = "html" in kind or "xml" in kind
    else:
        markup = text.lstrip().startswith("<")
    if not markup:
        return text
    text = re.sub(r"(?is)<!--.*?-->", " ", text)
    text = re.sub(r"(?is)<(script|style)\b[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    return html.unescape(text)


def _blocked_measures(snapshot: IssuerSnapshot) -> set[str]:
    blocked = set(_RESERVED_MEASURES)
    blocked.update(fact.concept for fact in snapshot.annual)
    for prefix in ANALYZE_PREFIXES:
        blocked.add(prefix)
        if prefix.endswith(":"):
            blocked.add(prefix[:-1])
    return blocked


def _measure_of(claim: Claim) -> str | None:
    measure = getattr(claim, "measure", None)
    if measure is None:
        return None
    return str(measure)


def _append(ledger: SourceLedger, claim: Claim) -> SourceLedger:
    found = ledger.by_id()
    existing = found.get(claim.id)
    if existing is not None:
        if existing == claim:
            return ledger
        raise ValueError(f"claim {claim.id} already exists with a different payload")
    return SourceLedger(ledger.ticker, ledger.claims + (claim,))


def _dispute_values(ledger: SourceLedger, claim: Dispute, peer_values: Mapping[ClaimId, Decimal]) -> None:
    found = ledger.by_id()
    seen: list[Decimal] = []
    for member_id in claim.members:
        member = found.get(member_id)
        if not isinstance(member, (Cited, PeerSnapshot)):
            raise ValueError(f"dispute member {member_id} must be cited or a peer snapshot")
        if _measure_of(member) != str(claim.measure):
            raise ValueError("dispute members must share one measure")
        if isinstance(member, Cited):
            value = member.value
        else:
            if member_id not in peer_values:
                raise ValueError(f"dispute member {member_id} has no peer value")
            value = peer_values[member_id]
        if any(value == prior for prior in seen):
            raise ValueError("dispute member values must differ")
        seen.append(value)


def admit(
    ledger: SourceLedger,
    claim: Claim,
    snapshot: IssuerSnapshot | None = None,
    peer_values: Mapping[ClaimId, Decimal] | None = None,
) -> SourceLedger:
    if isinstance(claim, Cited) and _sec_host(claim.url):
        raise ValueError("cited claim cannot use a sec.gov host")
    measure = _measure_of(claim)
    blocked = False
    if measure is not None:
        if isinstance(claim, Cited):
            blocked = _cited_measure_blocked(measure, snapshot)
        else:
            blocked = _measure_blocked(measure, snapshot)
    if blocked:
        raise ValueError(f"measure collides with the snapshot: {measure}")
    if isinstance(claim, Cited):
        found = ledger.by_id()
        for item in claim.inputs:
            if item not in found:
                raise ValueError(f"estimate input {item} is missing")
    if isinstance(claim, Excerpt):
        if snapshot is None or not any(item.accession == claim.accession for item in snapshot.filings):
            raise ValueError("excerpt accession is not on the snapshot")
    if isinstance(claim, PeerSnapshot) and (not claim.snapshot_path or not claim.concept):
        raise ValueError("peer snapshot needs a path and a concept")
    if isinstance(claim, Dispute):
        _dispute_values(ledger, claim, peer_values or {})
    return _append(ledger, claim)


def _latest_net_income(snapshot: IssuerSnapshot):
    rows = [fact for fact in snapshot.annual if fact.concept == "net_income"]
    if not rows:
        raise ValueError("snapshot has no net_income")
    return max(rows, key=lambda fact: (fact.filed, fact.fiscal_year, fact.end))


def _close_and_shares(snapshot: IssuerSnapshot):
    close = official_close(snapshot.prints)
    if close is None or snapshot.shares is None:
        raise ValueError("snapshot has no official close or share count")
    return close, snapshot.shares


def _gaap_rows(snapshot: IssuerSnapshot, concept: str, year: int):
    return [
        fact
        for fact in snapshot.annual
        if fact.concept == concept and fact.fiscal_year == year
    ]


def _resolve_snap(snapshot: IssuerSnapshot, token: str) -> Decimal:
    parts = token.split(":")
    if len(parts) < 2 or parts[0] != "snap":
        raise ValueError(f"missing snap ref {token}")
    kind = parts[1]
    if kind == "gaap" and len(parts) == 4:
        rows = _gaap_rows(snapshot, parts[2], int(parts[3]))
        if not rows:
            raise ValueError(f"missing snap ref {token}")
        return max(rows, key=lambda fact: fact.filed).ones
    if kind == "shares" and len(parts) == 3:
        if snapshot.shares is None or snapshot.shares.as_of.isoformat() != parts[2]:
            raise ValueError(f"missing snap ref {token}")
        return snapshot.shares.shares
    if kind == "close" and len(parts) == 3:
        close = official_close(snapshot.prints)
        if close is None or close.as_of.date().isoformat() != parts[2]:
            raise ValueError(f"missing snap ref {token}")
        return close.price
    if kind == "market_cap" and len(parts) == 2:
        return _recomputed_cap(snapshot)
    raise ValueError(f"missing snap ref {token}")


def _recomputed_cap(snapshot: IssuerSnapshot) -> Decimal:
    close, shares = _close_and_shares(snapshot)
    needs_ratio = snapshot.listing != "domestic"
    if needs_ratio and snapshot.adr_ratio is None:
        raise ValueError("market cap unavailable")
    cap = market_cap(close.price, shares.shares, snapshot.adr_ratio if needs_ratio else None)
    text = render_analysis(snapshot)
    if f"market_cap: usd={canonical_decimal(cap)}" not in text:
        raise ValueError("market cap unavailable")
    return cap


def _as_cited(found: Mapping[ClaimId, Claim], claim_id: ClaimId) -> Cited:
    claim = found.get(claim_id)
    if isinstance(claim, Excerpt):
        raise ValueError(f"{claim_id} is an excerpt and has no stored number")
    if not isinstance(claim, Cited):
        raise ValueError(f"{claim_id} must be cited or excerpt")
    return claim


def _growth_rate(claim: Cited) -> Decimal:
    if claim.unit == CitedUnit.RATIO:
        rate = claim.value
    elif claim.unit == CitedUnit.PERCENT:
        rate = _CTX.divide(claim.value, Decimal("100"))
    else:
        raise ValueError(f"{claim.id} growth must be ratio or percent")
    if rate < Decimal("-1"):
        raise ValueError(f"{claim.id} growth must be greater than -1")
    return rate


def _multiple(claim: Cited) -> Decimal:
    if claim.unit != CitedUnit.MULTIPLE:
        raise ValueError(f"{claim.id} pe must be a multiple")
    if claim.value <= 0:
        raise ValueError(f"{claim.id} pe must be positive")
    return claim.value


def _ratio_value(claim: Cited) -> Decimal:
    if claim.unit == CitedUnit.RATIO:
        return claim.value
    if claim.unit == CitedUnit.PERCENT:
        return _CTX.divide(claim.value, Decimal("100"))
    raise ValueError(f"{claim.id} payout must be ratio or percent")


def _scenario_prices(ledger: SourceLedger, snapshot: IssuerSnapshot, inputs: tuple[str, ...], years: int) -> tuple[Decimal, ...]:
    if len(inputs) != 9:
        raise ValueError("three-scenario inputs are incomplete")
    found = ledger.by_id()
    income = _resolve_snap(snapshot, inputs[6])
    shares = _resolve_snap(snapshot, inputs[7])
    _resolve_snap(snapshot, inputs[8])
    if shares == 0:
        raise ValueError("share count is zero")
    if income < 0:
        raise ValueError("three-scenario does not price a loss year")
    eps = _CTX.divide(income, shares)
    if eps < 0:
        raise ValueError("three-scenario does not price a loss year")
    prices = []
    for index in range(3):
        growth = _growth_rate(_as_cited(found, ClaimId(inputs[index])))
        pe = _multiple(_as_cited(found, ClaimId(inputs[index + 3])))
        prices.append(scenario_target_price(eps, growth, pe, years))
    return tuple(prices)


def _irr_rate(ledger: SourceLedger, snapshot: IssuerSnapshot, inputs: tuple[str, ...], years: int) -> Decimal:
    if len(inputs) not in (4, 5):
        raise ValueError("irr inputs are incomplete")
    found = ledger.by_id()
    profit = _as_cited(found, ClaimId(inputs[0]))
    if profit.unit != CitedUnit.USD_ONES:
        raise ValueError("irr profit must use usd_ones")
    pe = _multiple(_as_cited(found, ClaimId(inputs[1])))
    if len(inputs) == 5:
        payout = _ratio_value(_as_cited(found, ClaimId(inputs[2])))
        close_ref, share_ref = inputs[3], inputs[4]
    else:
        payout = Decimal("0")
        close_ref, share_ref = inputs[2], inputs[3]
    price = _resolve_snap(snapshot, close_ref)
    shares = _resolve_snap(snapshot, share_ref)
    needs_ratio = snapshot.listing != "domestic"
    if needs_ratio and snapshot.adr_ratio is None:
        raise ValueError("market cap unavailable")
    cap = market_cap(price, shares, snapshot.adr_ratio if needs_ratio else None)
    if f"market_cap: usd={canonical_decimal(cap)}" not in render_analysis(snapshot):
        raise ValueError("market cap unavailable")
    if cap == 0:
        raise ValueError("market cap is zero")
    rate = irr_from_terminal(float(profit.value), float(cap), float(pe), years=years, payout=float(payout))
    return Decimal(str(rate))


def _three_inputs(snapshot: IssuerSnapshot, request: ThreeScenario) -> tuple[str, ...]:
    income = _latest_net_income(snapshot)
    close, shares = _close_and_shares(snapshot)
    return (
        str(request.growth_ids[0]),
        str(request.growth_ids[1]),
        str(request.growth_ids[2]),
        str(request.pe_ids[0]),
        str(request.pe_ids[1]),
        str(request.pe_ids[2]),
        f"snap:gaap:net_income:{income.fiscal_year}",
        f"snap:shares:{shares.as_of.isoformat()}",
        f"snap:close:{close.as_of.date().isoformat()}",
    )


def _irr_inputs(snapshot: IssuerSnapshot, request: IrrRequest) -> tuple[str, ...]:
    close, shares = _close_and_shares(snapshot)
    head = [str(request.profit_id), str(request.pe_id)]
    if request.payout_id is not None:
        head.append(str(request.payout_id))
    head.append(f"snap:close:{close.as_of.date().isoformat()}")
    head.append(f"snap:shares:{shares.as_of.isoformat()}")
    return tuple(head)


def _same_derive(existing: Claim | None, request: ThreeScenario | IrrRequest) -> bool:
    if not isinstance(existing, Derived):
        return False
    if isinstance(request, ThreeScenario):
        if existing.tool != DeriveTool.THREE_SCENARIO or existing.years != request.years:
            return False
        want = tuple(str(item) for item in (*request.growth_ids, *request.pe_ids))
        return existing.inputs[:6] == want
    if existing.tool != DeriveTool.IRR or existing.years != request.years:
        return False
    head = [str(request.profit_id), str(request.pe_id)]
    if request.payout_id is not None:
        head.append(str(request.payout_id))
    prefix = tuple(head)
    return len(existing.inputs) == len(prefix) + 2 and existing.inputs[: len(prefix)] == prefix


def _require_years(years: int) -> None:
    if isinstance(years, bool) or not isinstance(years, int) or years < 1:
        raise ValueError("derived years must be positive")


def derive(
    ledger: SourceLedger,
    snapshot: IssuerSnapshot,
    request: ThreeScenario | IrrRequest,
) -> SourceLedger:
    _require_years(request.years)
    existing = ledger.by_id().get(request.id)
    if isinstance(request, ThreeScenario):
        inputs = _three_inputs(snapshot, request)
        _scenario_prices(ledger, snapshot, inputs, request.years)
        claim = Derived(request.id, DeriveTool.THREE_SCENARIO, inputs, request.years)
    else:
        inputs = _irr_inputs(snapshot, request)
        _irr_rate(ledger, snapshot, inputs, request.years)
        claim = Derived(request.id, DeriveTool.IRR, inputs, request.years)
    if existing is None:
        return SourceLedger(ledger.ticker, ledger.claims + (claim,))
    if not _same_derive(existing, request):
        raise ValueError(f"claim {request.id} already exists with a different payload")
    if existing == claim or _refs_resolve(snapshot, existing.inputs):
        return ledger
    replaced = tuple(claim if item.id == request.id else item for item in ledger.claims)
    return SourceLedger(ledger.ticker, replaced)


def _refs_resolve(snapshot: IssuerSnapshot, inputs: tuple[str, ...]) -> bool:
    try:
        for token in inputs:
            if token.startswith("snap:"):
                _resolve_snap(snapshot, token)
    except ValueError:
        return False
    return True


def _input_tier(
    token: str,
    ledger: SourceLedger,
    snapshot: IssuerSnapshot,
) -> Tier:
    if token.startswith("snap:"):
        _resolve_snap(snapshot, token)
        return Tier.PRIMARY
    claim = ledger.by_id().get(ClaimId(token))
    if isinstance(claim, Cited):
        return _cited_tier(claim, ledger, snapshot)
    if isinstance(claim, (Excerpt, PeerSnapshot)):
        return Tier.PRIMARY
    raise ValueError(f"derived input {token} has no tier")


def _derived_tier(claim: Derived, ledger: SourceLedger, snapshot: IssuerSnapshot) -> Tier:
    return weakest(tuple(_input_tier(token, ledger, snapshot) for token in claim.inputs))


def _cited_tier(
    claim: Cited,
    ledger: SourceLedger,
    snapshot: IssuerSnapshot | None,
    seen: set[str] | None = None,
) -> Tier:
    tier, _publisher = cited_binding(claim.url, snapshot)
    if not claim.inputs:
        return tier
    seen = set() if seen is None else set(seen)
    if str(claim.id) in seen:
        raise ValueError(f"estimate inputs cycle at {claim.id}")
    seen.add(str(claim.id))
    found = ledger.by_id()
    ranks = [tier]
    for item in claim.inputs:
        other = found.get(item)
        if not isinstance(other, Cited):
            raise ValueError(f"estimate input {item} must be cited")
        ranks.append(_cited_tier(other, ledger, snapshot, seen))
    return weakest(tuple(ranks))


def _cited_line(claim: Cited, ledger: SourceLedger, snapshot: IssuerSnapshot | None) -> str:
    tier = _cited_tier(claim, ledger, snapshot)
    _tier, publisher = cited_binding(claim.url, snapshot)
    when = "published" if claim.published is not None else "accessed"
    day = claim.published if claim.published is not None else claim.accessed
    pieces = [f"[c:{claim.id}", claim.url, publisher, f"{when}={day.isoformat()}"]
    if claim.is_estimate:
        pieces.append("estimate")
        pieces.append("inputs=" + ",".join(str(item) for item in claim.inputs))
    pieces.append(tier.value)
    return "{" + canonical_decimal(claim.value) + "}" + " ".join(pieces) + "]"


def _filing_by_accession(snapshot: IssuerSnapshot, accession: str):
    matches = [item for item in snapshot.filings if item.accession == accession]
    if len(matches) != 1:
        raise ValueError(f"accession {accession} is not on the snapshot")
    return matches[0]


def _filing_for_date(snapshot: IssuerSnapshot, filed: date):
    same = [item for item in snapshot.filings if item.filed == filed]
    if len(same) != 1:
        raise ValueError(f"peer fact filed {filed.isoformat()} does not match one filing")
    return same[0]


def _sec_bracket(claim_id: ClaimId, url: str, filed: date) -> str:
    return f"[c:{claim_id} {url} SEC published={filed.isoformat()} primary]"


def _excerpt_text(claim: Excerpt, excerpts: Mapping[str, bytes]) -> str:
    blob = excerpts.get(str(claim.id))
    if blob is None:
        raise ValueError(f"missing excerpt {claim.id}")
    if hashlib.sha256(blob).hexdigest() != claim.sha256:
        raise ValueError(f"excerpt {claim.id} does not match the stored hash")
    if len(blob) != claim.byte_end - claim.byte_start:
        raise ValueError(f"excerpt {claim.id} length does not match the stored range")
    return blob.decode("utf-8")


def _peer_fact(snapshot: IssuerSnapshot, concept: str, year: int):
    rows = _gaap_rows(snapshot, concept, year)
    if not rows:
        raise ValueError(f"peer snapshot has no {concept} for {year}")
    return max(rows, key=lambda fact: fact.filed)


def citation_lines(
    snapshot: IssuerSnapshot,
    ledger: SourceLedger,
    excerpts: Mapping[str, bytes],
    peers: Mapping[str, IssuerSnapshot],
) -> dict[ClaimId, tuple[str, ...]]:
    lines: dict[ClaimId, tuple[str, ...]] = {}
    for claim in ledger.claims:
        if isinstance(claim, Cited):
            lines[claim.id] = (_cited_line(claim, ledger, snapshot),)
        elif isinstance(claim, Excerpt):
            filing = _filing_by_accession(snapshot, claim.accession)
            quote = _excerpt_text(claim, excerpts)
            block = f"[q:{claim.id}]\n{quote}\n[/q]"
            url = claim.document_url or filing.url
            lines[claim.id] = (_sec_bracket(claim.id, url, filing.filed), block)
        elif isinstance(claim, PeerSnapshot):
            peer = peers.get(claim.snapshot_path)
            if peer is None:
                raise ValueError(f"missing peer snapshot {claim.snapshot_path}")
            fact = _peer_fact(peer, claim.concept, claim.fiscal_year)
            filing = _filing_for_date(peer, fact.filed)
            canon = canonical_decimal(fact.ones)
            lines[claim.id] = (f"{{{canon}}}{_sec_bracket(claim.id, filing.url, fact.filed)}",)
        elif isinstance(claim, Derived):
            tier = _derived_tier(claim, ledger, snapshot)
            if claim.tool == DeriveTool.THREE_SCENARIO:
                values = _scenario_prices(ledger, snapshot, claim.inputs, claim.years)
                cases = ("bull", "base", "bear")
            else:
                values = (_irr_rate(ledger, snapshot, claim.inputs, claim.years),)
                cases = ("",)
            rows = []
            for value, case in zip(values, cases):
                case_bit = f" case={case}" if case else ""
                row_body = (
                    f"[d:{claim.id} derived tool={claim.tool.value} "
                    f"inputs={','.join(claim.inputs)}{case_bit} tier={tier.value}]"
                )
                shown = _printed_derived(value, claim.tool)
                rows.append("{" + shown + "}" + row_body)
            lines[claim.id] = tuple(rows)
        elif isinstance(claim, Dispute):
            members = ",".join(str(item) for item in claim.members)
            lines[claim.id] = (f"[dispute:{claim.id} members={members}]",)
        elif isinstance(claim, Scored):
            context = f" context={','.join(claim.context)}" if claim.context else ""
            anchor = ",".join(claim.anchor)
            lines[claim.id] = (f"[s:{claim.id} stars={claim.stars} anchor={anchor}{context}]",)
        else:
            lines[claim.id] = (f"[s:{claim.id} withheld]",)
    return lines


def _walk_json(node: object, tokens: list[str]) -> None:
    if isinstance(node, dict):
        for value in node.values():
            _walk_json(value, tokens)
    elif isinstance(node, list):
        for value in node:
            _walk_json(value, tokens)
    elif isinstance(node, str):
        tokens.append(node)
    elif isinstance(node, (int, float)):
        tokens.append(str(node))


def _whole_numbers(token: str) -> set[str]:
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


def _evidence_tokens(snapshot: IssuerSnapshot, analyze_text: str) -> list[str]:
    tokens: list[str] = []
    _walk_json(snapshot.to_json(), tokens)
    for line in analyze_text.splitlines():
        if line.startswith(ANALYZE_PREFIXES):
            tokens.extend(_NUMBER_TOKEN.findall(line))
    return tokens


def snapshot_allow_list(snapshot: IssuerSnapshot, analyze_text: str) -> set[str]:
    allowed: set[str] = set()
    for token in _evidence_tokens(snapshot, analyze_text):
        allowed.update(_whole_numbers(token))
    return allowed


def _date_stamps(snapshot: IssuerSnapshot, analyze_text: str) -> set[str]:
    dates: set[str] = set()
    for token in _evidence_tokens(snapshot, analyze_text):
        dates.update(_DATE_STAMP.findall(token))
        dates.update(_SLASH_DATE.findall(token))
    return dates


def _mask_exact(report: str, rows: tuple[str, ...]) -> str:
    masked = report
    for row in sorted((row for row in rows if row), key=len, reverse=True):
        blank = "".join("\n" if char == "\n" else " " for char in row)
        masked = masked.replace(row, blank)
    return masked


_FORM_SPAN = re.compile(r"(?i)^(?:form\s+)?(?:10-k/?a?|10-q|8-k|20-f|40-f|6-k|def\s*14a|s-1|4)$")
_TICKER_SPAN = re.compile(r"(?i)^[a-z]{1,6}(?:\.[a-z]{1,4})?$|^\d{1,6}\.[a-z]{1,4}$")
_IDENT_SPAN = re.compile(r"^[A-Za-z_][\w./:-]*$")
_CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_UNITS = {"十": 10, "百": 100, "千": 1000}
_CN_BIG = {"万": 10000, "亿": 100000000}
_CN_CHARS = frozenset(_CN_DIGITS) | frozenset(_CN_UNITS) | frozenset(_CN_BIG)
_CN_RUN = re.compile(r"[零〇一二两三四五六七八九十百千万亿]+")


def _span_exempt(inner: str) -> bool:
    text = inner.strip()
    if _FORM_SPAN.fullmatch(text) or _TICKER_SPAN.fullmatch(text):
        return True
    if "/" in text or "\\" in text or text.lower().endswith((".md", ".py", ".json", ".txt", ".html", ".xml")):
        return True
    return " " not in text and _IDENT_SPAN.fullmatch(text) is not None


def _mask_inline(line: str) -> str:
    def rewrite(match: re.Match[str]) -> str:
        inner = match.group(0)[1:-1]
        if _span_exempt(inner):
            return " " * len(match.group(0))
        kept = "".join(char if char.isdigit() or char in ".,-" or char in _CN_CHARS else " " for char in inner)
        return " " + kept + " "

    line = re.sub(r"`[^`]*`", rewrite, line)
    return re.sub(r"[\w./-]+\.md", lambda match: " " * len(match.group(0)), line)


def _parse_chinese(text: str) -> int | None:
    if not any(char in _CN_UNITS or char in _CN_BIG for char in text):
        return None
    total = 0
    section = 0
    number = 0
    for char in text:
        if char in _CN_DIGITS:
            number = _CN_DIGITS[char]
        elif char in _CN_UNITS:
            if number == 0:
                number = 1
            section += number * _CN_UNITS[char]
            number = 0
        elif char in _CN_BIG:
            section += number
            total += section * _CN_BIG[char]
            section = 0
            number = 0
        else:
            return None
    return total + section + number


def _word_has(line: str, words: frozenset[str]) -> bool:
    folded = line.casefold()
    return any(re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", folded) for word in words)


def _quantity_tokens(value: Decimal) -> set[str]:
    return _whole_numbers(format(value, "f"))


def _protected_tokens(snapshot: IssuerSnapshot, analyze_text: str) -> set[str]:
    found: set[str] = set()
    for item in snapshot.prints:
        found.update(_quantity_tokens(item.price))
    for fact in snapshot.annual:
        found.update(_quantity_tokens(fact.ones))
    if snapshot.shares is not None:
        found.update(_quantity_tokens(snapshot.shares.shares))
    for item in snapshot.yields:
        found.update(_quantity_tokens(item.rate))
    for item in snapshot.percents:
        found.update(_quantity_tokens(item.parts_per_hundred))
    for item in snapshot.ranges:
        found.update(_quantity_tokens(item.value))
    for item in snapshot.unscaled:
        found.update(_whole_numbers(item.lexeme))
    for line in analyze_text.splitlines():
        if not line.startswith(ANALYZE_PREFIXES):
            continue
        for token in _NUMBER_TOKEN.findall(line):
            for piece in _whole_numbers(token):
                if re.fullmatch(r"\d{4}", piece) and 1900 <= int(piece) <= 2100:
                    continue
                found.add(piece)
    return found


def _suppressed_tokens(snapshot: IssuerSnapshot, allowed: set[str], analyze_text: str) -> set[str]:
    drop: set[str] = set()
    for trade in snapshot.insiders:
        drop.update(_quantity_tokens(trade.shares))
        if trade.price is not None:
            drop.update(_quantity_tokens(trade.price))
    for fact in snapshot.annual:
        if 1900 <= fact.fiscal_year <= 2100:
            drop.update(_quantity_tokens(Decimal(fact.fiscal_year)))
    for failure in snapshot.failures:
        drop.update(_quantity_tokens(Decimal(failure.status)))
    for token in allowed:
        if not re.fullmatch(r"-?\d+", token):
            continue
        if abs(int(token)) < 1000:
            drop.add(token)
    return drop - _protected_tokens(snapshot, analyze_text)


def _same_quantity(cleaned: str, token: str) -> bool:
    try:
        left = Decimal(cleaned)
        right = Decimal(token)
    except Exception:
        return False
    if left != right or abs(left) < 1000:
        return False
    return True


def _listed(cleaned: str, allowed: set[str]) -> bool:
    try:
        as_dec = format(Decimal(cleaned), "f")
    except Exception:
        return False
    if cleaned in allowed or as_dec in allowed:
        return True
    return any(_same_quantity(cleaned, token) for token in allowed)


def _contextual_hit(line: str, cleaned: str, snapshot: IssuerSnapshot) -> bool:
    try:
        want = Decimal(cleaned)
    except Exception:
        return False
    for trade in snapshot.insiders:
        if want == trade.shares and _word_has(line, frozenset({"shares"})):
            return True
        if trade.price is not None and want == trade.price and _word_has(line, frozenset({"price"})):
            return True
    if want == want.to_integral_value():
        year = abs(int(want))
        years = {fact.fiscal_year for fact in snapshot.annual}
        if year in years and _word_has(line, frozenset({"fiscal"})):
            return True
    for failure in snapshot.failures:
        if want == Decimal(failure.status) and _word_has(line, frozenset({"status", "http"})):
            return True
    return False


def _broken_spans(masked: str) -> tuple[tuple[int, int], ...]:
    spans = []
    for match in _BRACKET_OPEN.finditer(masked):
        start = match.start()
        if start > 0 and masked[start - 1] == "}":
            brace = masked.rfind("{", 0, start)
            if brace >= 0 and "\n" not in masked[brace:start]:
                start = brace
        if match.group(1) == "q":
            close = masked.find("[/q]", match.start())
            end = len(masked) if close < 0 else close + len("[/q]")
        else:
            close = masked.find("]", match.start())
            end = len(masked) if close < 0 else close + 1
        spans.append((start, end))
    return tuple(spans)


def _line_body(part: str) -> str:
    if part.endswith("\r\n"):
        return part[:-2]
    if part.endswith("\n") or part.endswith("\r"):
        return part[:-1]
    return part


_FORM_IN_LINE = re.compile(r"(?i)\b(?:form\s+4|10-k/?a?|10-q|8-k|20-f|40-f|6-k|def\s*14a)\b")


def _overlap(start: int, end: int, spans: tuple[tuple[int, int], ...]) -> bool:
    return any(start < right and end > left for left, right in spans)


def _inside_form(text: str, start: int, end: int) -> bool:
    return any(start >= match.start() and end <= match.end() for match in _FORM_IN_LINE.finditer(text))


def _classified_numbers(
    report: str,
    snapshot: IssuerSnapshot,
    analyze_text: str,
    lines: Mapping[ClaimId, tuple[str, ...]] | None,
) -> list[tuple[str, str]]:
    if lines:
        rows = tuple(row for group in lines.values() for row in group)
        masked = _mask_exact(report, rows)
        broken = _broken_spans(masked)
    else:
        masked = report
        broken = ()
    allowed = snapshot_allow_list(snapshot, analyze_text)
    free = allowed - _suppressed_tokens(snapshot, allowed, analyze_text)
    file_dates = _date_stamps(snapshot, analyze_text)
    cutoff = _FRONT_MATTER_DATE.search(report)
    if cutoff:
        file_dates.add(cutoff.group(1))
    missed: list[tuple[str, str]] = []
    offset = 0
    originals = report.splitlines()
    parts = masked.splitlines(keepends=True)
    if report and not parts:
        parts = [report]
    for index, part in enumerate(parts):
        original = originals[index] if index < len(originals) else ""
        visible = _mask_inline(_line_body(part))
        present: set[str] = set()
        for stamp in file_dates:
            if stamp in original:
                for piece in re.split(r"[-/T:+]", stamp):
                    if piece.isdigit():
                        present.add(piece)
                        present.add(str(int(piece)))
        for match in _NUMBER_IN_TEXT.finditer(visible):
            raw = match.group(0)
            cleaned = raw.replace(",", "")
            if _inside_form(visible, match.start(), match.end()):
                continue
            if "." not in cleaned and cleaned in present:
                continue
            if _listed(cleaned, free) or _contextual_hit(original, cleaned, snapshot):
                continue
            kind = "broken" if _overlap(offset + match.start(), offset + match.end(), broken) else "outside"
            missed.append((raw, kind))
        for match in _CN_RUN.finditer(visible):
            parsed = _parse_chinese(match.group(0))
            if parsed is None:
                continue
            rendered = str(parsed)
            if _listed(rendered, free) or _contextual_hit(original, rendered, snapshot):
                continue
            kind = "broken" if _overlap(offset + match.start(), offset + match.end(), broken) else "outside"
            missed.append((rendered, kind))
        offset += len(part)
    return missed


def unexcused_numbers(
    report: str,
    snapshot: IssuerSnapshot,
    analyze_text: str,
    lines: Mapping[ClaimId, tuple[str, ...]] | None,
) -> list[str]:
    return [raw for raw, _kind in _classified_numbers(report, snapshot, analyze_text, lines)]


def _excusing_lines(
    snapshot: IssuerSnapshot,
    ledger: SourceLedger,
    lines: Mapping[ClaimId, tuple[str, ...]],
) -> dict[ClaimId, tuple[str, ...]]:
    found = ledger.by_id()
    kept: dict[ClaimId, tuple[str, ...]] = {}
    for claim_id, rows in lines.items():
        claim = found.get(claim_id)
        measure = _measure_of(claim) if claim is not None else None
        if measure is not None:
            blocked = _cited_measure_blocked(measure, snapshot) if isinstance(claim, Cited) else _measure_blocked(measure, snapshot)
            if blocked:
                continue
        kept[claim_id] = rows
    return kept


def _us_signal(report: str, snapshot: IssuerSnapshot | None, ledger: SourceLedger | None) -> bool:
    if snapshot is not None or ledger is not None:
        return True
    if _US_MARKET.search(report):
        return True
    return _BRACKET_OPEN.search(report) is not None


def _sections(report: str) -> list[str]:
    parts = re.split(r"(?m)^(#{1,6}[ \t]+.*)$", report)
    if len(parts) == 1:
        return parts
    sections = []
    if parts[0].strip():
        sections.append(parts[0])
    index = 1
    while index < len(parts):
        heading = parts[index]
        body = parts[index + 1] if index + 1 < len(parts) else ""
        sections.append(heading + body)
        index += 2
    return sections or [report]


def _rows_in(section: str, rows: tuple[str, ...]) -> bool:
    return any(row and row in section for row in rows)


def _dispute_failures(report: str, ledger: SourceLedger, lines: Mapping[ClaimId, tuple[str, ...]]) -> list[str]:
    failures = []
    for claim in ledger.claims:
        if not isinstance(claim, Dispute):
            continue
        dispute_rows = lines.get(claim.id, ())
        for section in _sections(report):
            present = [member for member in claim.members if _rows_in(section, lines.get(member, ()))]
            shown = bool(present) or _rows_in(section, dispute_rows)
            if not shown:
                continue
            if not _rows_in(section, dispute_rows) or len(present) != len(claim.members):
                failures.append(f"dispute {claim.id} hides a member")
    return failures


def _anchor_failure(anchor: str, ledger: SourceLedger, snapshot: IssuerSnapshot) -> str | None:
    if anchor.startswith("snap:"):
        try:
            _resolve_snap(snapshot, anchor)
        except ValueError:
            return f"score anchor {anchor} is missing"
        return f"score anchor {anchor} is only a snapshot figure"
    try:
        claim_id = ClaimId(anchor)
    except ValueError:
        return f"score anchor {anchor} is missing"
    claim = ledger.by_id().get(claim_id)
    if claim is None:
        return f"score anchor {anchor} is missing"
    if isinstance(claim, (Derived, Dispute, Scored, Withheld)):
        return f"score anchor {anchor} cannot support a star"
    if isinstance(claim, Cited):
        if _cited_tier(claim, ledger, snapshot) == Tier.LOW:
            return f"score anchor {anchor} is low"
        return None
    return None


def _derived_row_failures(
    report: str,
    ledger: SourceLedger,
    lines: Mapping[ClaimId, tuple[str, ...]],
) -> list[str]:
    failures = []
    for claim in ledger.claims:
        if not isinstance(claim, Derived) or claim.tool != DeriveTool.THREE_SCENARIO:
            continue
        rows = lines.get(claim.id, ())
        shown = [row for row in rows if row and row in report]
        if shown and len(shown) != len(rows):
            failures.append(f"derived {claim.id} hides a scenario")
    return failures


def _score_failures(
    report: str,
    ledger: SourceLedger,
    snapshot: IssuerSnapshot,
    lines: Mapping[ClaimId, tuple[str, ...]],
) -> list[str]:
    failures = []
    scored = [claim for claim in ledger.claims if isinstance(claim, Scored)]
    for claim in scored:
        thesis = False
        for anchor in claim.anchor:
            problem = _anchor_failure(anchor, ledger, snapshot)
            if problem is None:
                thesis = True
                continue
            if problem.endswith("is only a snapshot figure"):
                continue
            failures.append(problem)
        if not thesis:
            failures.append(f"score {claim.id} needs a thesis anchor")
    runs = [len(match) for match in re.findall(r"★+", report)]
    printed = [claim for claim in scored if _rows_in(report, lines.get(claim.id, ()))]
    if runs and not printed:
        failures.append("star glyphs have no scored citation")
    if printed and sorted(runs) != sorted(claim.stars for claim in printed):
        failures.append("star glyph count disagrees with stars")
    return failures


def _bracket_failures(report: str, lines: Mapping[ClaimId, tuple[str, ...]]) -> list[str]:
    rows = tuple(row for group in lines.values() for row in group)
    masked = _mask_exact(report, rows)
    if _BRACKET_OPEN.search(masked):
        return ["printed bracket disagrees with citation_lines"]
    return []


def audit_report(
    report: str,
    snapshot: IssuerSnapshot | None,
    ledger: SourceLedger | None,
    excerpts: Mapping[str, bytes],
    peers: Mapping[str, IssuerSnapshot] | None = None,
    agent: str = "",
) -> AuditResult:
    if not _us_signal(report, snapshot, ledger):
        return AuditResult("skip", ())
    if snapshot is None:
        return AuditResult("fail", ("missing snapshot",))
    if ledger is not None and ledger.ticker != snapshot.ticker:
        return AuditResult("fail", ("ledger ticker does not match the snapshot",))
    peers = {} if peers is None else peers
    failures: list[str] = []
    if ledger is None and "★" in report:
        failures.append("star glyphs have no scored citation")
    try:
        if agent and agent in report:
            raise ValueError("artifact contains the SEC user agent")
        for blob in excerpts.values():
            assert_no_secret(blob.decode("utf-8", "replace"), agent)
    except ValueError as error:
        failures.append(str(error))
    lines: dict[ClaimId, tuple[str, ...]] = {}
    if ledger is not None:
        try:
            assert_no_secret(dumps_ledger(ledger), agent)
        except ValueError as error:
            failures.append(str(error))
        for claim in ledger.claims:
            if isinstance(claim, Cited) and _sec_host(claim.url):
                failures.append(f"cited {claim.id} uses a sec.gov host")
        try:
            lines = citation_lines(snapshot, ledger, excerpts, peers)
        except ValueError as error:
            failures.append(str(error))
        failures.extend(_bracket_failures(report, lines))
        failures.extend(_dispute_failures(report, ledger, lines))
        failures.extend(_derived_row_failures(report, ledger, lines))
        failures.extend(_score_failures(report, ledger, snapshot, lines))
    analyze = render_analysis(snapshot)
    usable = _excusing_lines(snapshot, ledger, lines) if ledger is not None else None
    name = snapshot.ticker
    for raw, kind in _classified_numbers(report, snapshot, analyze, usable):
        if kind == "broken":
            failures.append(f"{name} number {raw} has no tiered citation")
        else:
            failures.append(f"{name} cites {raw} which is not in the snapshot")
    if failures:
        return AuditResult("fail", tuple(failures))
    return AuditResult("pass", ())


def _add_common(parser: argparse.ArgumentParser, snapshot: bool = False, snapshot_required: bool = False) -> None:
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--id", required=True)
    if snapshot:
        parser.add_argument("--snapshot", required=snapshot_required)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="source_ledger.py")
    sub = parser.add_subparsers(dest="command")

    admit = sub.add_parser("admit")
    admit_sub = admit.add_subparsers(dest="kind")

    cited = admit_sub.add_parser("cited")
    _add_common(cited, snapshot=True)
    cited.add_argument("--measure", required=True)
    cited.add_argument("--value", required=True)
    cited.add_argument("--unit", required=True)
    cited.add_argument("--url", required=True)
    cited.add_argument("--published")
    cited.add_argument("--accessed")
    cited.add_argument("--input", action="append")
    cited.add_argument("--quote-sha256", default="")

    excerpt = admit_sub.add_parser("excerpt")
    _add_common(excerpt, snapshot=True, snapshot_required=True)
    excerpt.add_argument("--measure", required=True)
    excerpt.add_argument("--accession", required=True)
    excerpt.add_argument("--contains", required=True)
    excerpt.add_argument("--out", required=True)

    peer = admit_sub.add_parser("peer")
    _add_common(peer)
    peer.add_argument("--measure", required=True)
    peer.add_argument("--snapshot", required=True)
    peer.add_argument("--concept", required=True)
    peer.add_argument("--fiscal-year", type=int, required=True)

    dispute = admit_sub.add_parser("dispute")
    _add_common(dispute, snapshot=True)
    dispute.add_argument("--measure", required=True)
    dispute.add_argument("--member", action="append", required=True)

    score = admit_sub.add_parser("score")
    _add_common(score)
    score.add_argument("--stars", type=int)
    score.add_argument("--anchor", action="append")
    score.add_argument("--context", action="append")
    score.add_argument("--withhold", action="store_true")

    derive = sub.add_parser("derive")
    derive_sub = derive.add_subparsers(dest="kind")

    three = derive_sub.add_parser("three-scenario")
    _add_common(three, snapshot=True, snapshot_required=True)
    three.add_argument("--growth", required=True)
    three.add_argument("--pe", required=True)
    three.add_argument("--years", type=int, default=3)

    irr = derive_sub.add_parser("irr")
    _add_common(irr, snapshot=True, snapshot_required=True)
    irr.add_argument("--profit", required=True)
    irr.add_argument("--pe", required=True)
    irr.add_argument("--payout")
    irr.add_argument("--years", type=int, default=10)

    remove = sub.add_parser("remove")
    remove.add_argument("--ledger", required=True)
    remove.add_argument("--id", required=True)

    audit = sub.add_parser("audit")
    audit.add_argument("--report", required=True)
    audit.add_argument("--snapshot")
    audit.add_argument("--ledger")
    return parser
