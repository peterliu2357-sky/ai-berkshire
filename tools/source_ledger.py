#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from datetime import date
from decimal import Decimal, InvalidOperation

_TOOLS = os.path.dirname(os.path.abspath(__file__))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from usmarket.claims import (  # noqa: E402
    Cited,
    CitedUnit,
    ClaimId,
    Derived,
    Dispute,
    Excerpt,
    IrrRequest,
    Measure,
    PeerSnapshot,
    Scored,
    SourceLedger,
    ThreeScenario,
    Withheld,
    admit,
    assert_no_secret,
    audit_report,
    build_parser,
    citation_lines,
    derive,
    load_ledger,
    visible_text,
    write_ledger,
)
from usmarket.fetch import SecConfigError, http_get, sec_user_agent  # noqa: E402
from usmarket.types import (  # noqa: E402
    IssuerSnapshot,
    snapshot_from_json,
)


def _blank_snapshot(ticker: str) -> IssuerSnapshot:
    return IssuerSnapshot(
        ticker=ticker,
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


def _read_snapshot(path: str) -> IssuerSnapshot:
    with open(path, encoding="utf-8") as handle:
        return snapshot_from_json(json.load(handle))


def _ticker_near(ledger_path: str) -> str:
    directory = os.path.dirname(os.path.abspath(ledger_path))
    if not os.path.isdir(directory):
        return ""
    found = []
    prefix = "us-snapshot-"
    for name in os.listdir(directory):
        if name.startswith(prefix) and name.endswith(".json"):
            found.append(name[len(prefix) : -len(".json")])
    if len(found) == 1:
        return found[0]
    return ""


def _load_ledger(path: str, snapshot: IssuerSnapshot | None) -> SourceLedger:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            ledger = load_ledger(handle.read())
        if snapshot is not None and ledger.ticker != snapshot.ticker:
            raise ValueError("ledger ticker does not match the snapshot")
        return ledger
    ticker = snapshot.ticker if snapshot is not None else _ticker_near(path)
    if not ticker:
        raise ValueError("pass --snapshot so the new ledger has a ticker")
    return SourceLedger(ticker, ())


def _optional_agent() -> str:
    try:
        return sec_user_agent()
    except SecConfigError:
        return ""


def _replace_bytes(path: str, payload: bytes) -> None:
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    tmp = path + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    except Exception:
        os.close(fd)
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    os.close(fd)
    os.replace(tmp, path)


def _date_or_none(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _ids(text: str) -> tuple[ClaimId, ...]:
    parts = [item.strip() for item in text.split(",") if item.strip()]
    return tuple(ClaimId(item) for item in parts)


def _snapshot_for(args, ledger: SourceLedger) -> IssuerSnapshot:
    path = getattr(args, "snapshot", None)
    if path:
        return _read_snapshot(path)
    return _blank_snapshot(ledger.ticker)


def _print_claim(snapshot: IssuerSnapshot, ledger: SourceLedger, claim_id: ClaimId, excerpts, peers, agent: str) -> None:
    found = ledger.by_id()
    claim = found[claim_id]
    subset = [claim]
    if isinstance(claim, Derived):
        extra = []
        for token in claim.inputs:
            if not token.startswith("snap:"):
                extra.append(found[ClaimId(token)])
        subset = extra + [claim]
    lines = citation_lines(snapshot, SourceLedger(ledger.ticker, tuple(subset)), excerpts, peers)
    text = "\n".join(lines[claim_id])
    assert_no_secret(text, agent)
    print(text)


def _save_and_print(path: str, snapshot: IssuerSnapshot | None, ledger: SourceLedger, claim_id: ClaimId, excerpts, peers, agent: str) -> int:
    write_ledger(path, ledger, agent)
    bound = snapshot if snapshot is not None else _blank_snapshot(ledger.ticker)
    _print_claim(bound, ledger, claim_id, excerpts, peers, agent)
    return 0


def _cmd_cited(args, agent: str) -> int:
    snapshot = _read_snapshot(args.snapshot) if args.snapshot else None
    ledger = _load_ledger(args.ledger, snapshot)
    claim = Cited(
        ClaimId(args.id),
        Measure(args.measure),
        Decimal(args.value),
        CitedUnit(args.unit),
        args.url,
        _date_or_none(args.published),
        _date_or_none(args.accessed),
        tuple(ClaimId(item) for item in (args.input or [])),
        args.quote_sha256 or "",
    )
    updated = admit(ledger, claim, snapshot)
    return _save_and_print(args.ledger, snapshot, updated, claim.id, {}, {}, agent)


def _cmd_peer(args, agent: str) -> int:
    peer = _read_snapshot(args.snapshot)
    ledger = _load_ledger(args.ledger, None)
    claim = PeerSnapshot(
        ClaimId(args.id),
        Measure(args.measure),
        args.snapshot,
        args.concept,
        args.fiscal_year,
    )
    updated = admit(ledger, claim, None)
    return _save_and_print(args.ledger, None, updated, claim.id, {}, {args.snapshot: peer}, agent)


def _peer_amount(member: PeerSnapshot) -> Decimal:
    peer = _read_snapshot(member.snapshot_path)
    rows = [
        fact
        for fact in peer.annual
        if fact.concept == member.concept and fact.fiscal_year == member.fiscal_year
    ]
    if not rows:
        raise ValueError(f"peer snapshot has no {member.concept} for {member.fiscal_year}")
    return max(rows, key=lambda fact: fact.filed).ones


def _cmd_dispute(args, agent: str) -> int:
    snapshot = _read_snapshot(args.snapshot) if args.snapshot else None
    ledger = _load_ledger(args.ledger, snapshot)
    members = tuple(ClaimId(item) for item in args.member)
    found = ledger.by_id()
    peer_values = {}
    for member_id in members:
        member = found.get(member_id)
        if isinstance(member, PeerSnapshot):
            peer_values[member_id] = _peer_amount(member)
    claim = Dispute(ClaimId(args.id), Measure(args.measure), members)
    updated = admit(ledger, claim, snapshot, peer_values)
    return _save_and_print(args.ledger, snapshot, updated, claim.id, {}, {}, agent)


def _cmd_score(args, agent: str) -> int:
    ledger = _load_ledger(args.ledger, None)
    context = tuple(args.context or [])
    if args.withhold:
        claim = Withheld(ClaimId(args.id), context)
    else:
        if args.stars is None or not args.anchor:
            raise ValueError("score needs --stars and --anchor, or --withhold")
        claim = Scored(ClaimId(args.id), args.stars, tuple(args.anchor), context)
    updated = admit(ledger, claim, None)
    return _save_and_print(args.ledger, None, updated, claim.id, {}, {}, agent)


def _markup_type(body: bytes) -> str:
    head = body.lstrip()[:400].lower()
    if head.startswith(b"<") or b"<html" in head or b"<p" in head or b"<div" in head:
        return "text/html"
    return "text/plain"


def _unique_span(text: str, needle: str) -> tuple[int, int]:
    if not needle:
        raise ValueError("excerpt text is empty")
    start = 0
    hits = []
    while True:
        index = text.find(needle, start)
        if index < 0:
            break
        hits.append(index)
        start = index + 1
    if len(hits) != 1:
        raise ValueError("excerpt match is not unique")
    byte_start = len(text[: hits[0]].encode("utf-8"))
    blob = needle.encode("utf-8")
    return byte_start, byte_start + len(blob)


def _canonical_excerpt(ledger_path: str, claim_id: str) -> str:
    return os.path.join(_excerpt_dir(ledger_path), f"{claim_id}.txt")


def _cmd_excerpt(args) -> int:
    expected = os.path.abspath(_canonical_excerpt(args.ledger, args.id))
    if os.path.abspath(args.out) != expected:
        print("excerpt --out must be excerpts/<id>.txt beside the ledger", file=sys.stderr)
        return 1
    try:
        agent = sec_user_agent()
    except SecConfigError as error:
        print(error, file=sys.stderr)
        return 1
    snapshot = _read_snapshot(args.snapshot)
    ledger = _load_ledger(args.ledger, snapshot)
    matches = [item for item in snapshot.filings if item.accession == args.accession]
    if len(matches) != 1:
        raise ValueError("excerpt accession is not on the snapshot")
    download = None
    try:
        status, body = http_get(matches[0].url, agent)
        fd, download = tempfile.mkstemp(prefix=".excerpt-download-", suffix=".tmp")
        with os.fdopen(fd, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        if status != 200:
            print(f"excerpt fetch failed with status {status}", file=sys.stderr)
            return 1
        text = visible_text(body, _markup_type(body))
        byte_start, byte_end = _unique_span(text, args.contains)
        blob = args.contains.encode("utf-8")
        assert_no_secret(args.contains, agent)
        digest = hashlib.sha256(blob).hexdigest()
        if os.path.exists(args.out):
            with open(args.out, "rb") as handle:
                current = handle.read()
            if current != blob:
                print("excerpt slice diverged", file=sys.stderr)
                return 2
        else:
            _replace_bytes(args.out, blob)
        claim = Excerpt(
            ClaimId(args.id),
            Measure(args.measure),
            args.accession,
            digest,
            byte_start,
            byte_end,
        )
        updated = admit(ledger, claim, snapshot)
        return _save_and_print(
            args.ledger,
            snapshot,
            updated,
            claim.id,
            {str(claim.id): blob},
            {},
            agent,
        )
    finally:
        if download is not None and os.path.exists(download):
            os.remove(download)


def _cmd_derive(args, agent: str) -> int:
    snapshot = _read_snapshot(args.snapshot)
    ledger = _load_ledger(args.ledger, snapshot)
    if args.kind == "three-scenario":
        growth = _ids(args.growth)
        pe = _ids(args.pe)
        if len(growth) != 3 or len(pe) != 3:
            raise ValueError("three-scenario needs three growth ids and three pe ids")
        request = ThreeScenario(ClaimId(args.id), (growth[0], growth[1], growth[2]), (pe[0], pe[1], pe[2]), args.years)
    else:
        request = IrrRequest(
            ClaimId(args.id),
            ClaimId(args.profit),
            ClaimId(args.pe),
            ClaimId(args.payout) if args.payout else None,
            args.years,
        )
    updated = derive(ledger, snapshot, request)
    return _save_and_print(args.ledger, snapshot, updated, request.id, {}, {}, agent)


def _excerpt_dir(ledger_path: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(ledger_path)), "excerpts")


def _load_excerpts(ledger_path: str, ledger: SourceLedger) -> dict[str, bytes]:
    directory = _excerpt_dir(ledger_path)
    found = {}
    for claim in ledger.claims:
        if not isinstance(claim, Excerpt):
            continue
        path = os.path.join(directory, f"{claim.id}.txt")
        if not os.path.exists(path):
            continue
        with open(path, "rb") as handle:
            found[str(claim.id)] = handle.read()
    return found


def _load_peers(ledger: SourceLedger) -> dict[str, IssuerSnapshot]:
    peers = {}
    for claim in ledger.claims:
        if isinstance(claim, PeerSnapshot) and claim.snapshot_path not in peers and os.path.exists(claim.snapshot_path):
            peers[claim.snapshot_path] = _read_snapshot(claim.snapshot_path)
    return peers


def _cmd_audit(args) -> int:
    with open(args.report, encoding="utf-8") as handle:
        report = handle.read()
    snapshot = _read_snapshot(args.snapshot) if args.snapshot else None
    ledger = None
    excerpts: dict[str, bytes] = {}
    peers: dict[str, IssuerSnapshot] = {}
    if args.ledger:
        if not os.path.exists(args.ledger):
            raise ValueError("ledger is missing")
        with open(args.ledger, encoding="utf-8") as handle:
            ledger = load_ledger(handle.read())
        excerpts = _load_excerpts(args.ledger, ledger)
        peers = _load_peers(ledger)
    result = audit_report(report, snapshot, ledger, excerpts, peers, _optional_agent())
    if result.status == "skip":
        print("audit: skipped")
        return 0
    if result.status == "pass":
        print("audit: pass")
        return 0
    for item in result.failures:
        print(item)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit as error:
        return 2 if error.code is None else int(error.code)
    if not args.command:
        parser.print_help(sys.stderr)
        return 2
    try:
        if args.command == "audit":
            return _cmd_audit(args)
        if args.command == "derive":
            if not getattr(args, "kind", None):
                parser.print_help(sys.stderr)
                return 2
            return _cmd_derive(args, _optional_agent())
        if args.command == "admit":
            if not getattr(args, "kind", None):
                parser.print_help(sys.stderr)
                return 2
            if args.kind == "excerpt":
                return _cmd_excerpt(args)
            agent = _optional_agent()
            if args.kind == "cited":
                return _cmd_cited(args, agent)
            if args.kind == "peer":
                return _cmd_peer(args, agent)
            if args.kind == "dispute":
                return _cmd_dispute(args, agent)
            if args.kind == "score":
                return _cmd_score(args, agent)
        parser.print_help(sys.stderr)
        return 2
    except (ValueError, OSError, InvalidOperation, SecConfigError) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
