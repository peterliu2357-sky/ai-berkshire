from __future__ import annotations

import re
from decimal import Decimal
from typing import Mapping

from us_market import ANALYZE_PREFIXES
from usmarket.types import IssuerSnapshot

_NUMBER_TOKEN = re.compile(r"-?\d+(?:,\d{3})*(?:\.\d+)?")
_NUMBER_IN_TEXT = re.compile(r"(?<![\d.])-?\d+(?:,\d{3})*(?:\.\d+)?")
_DATE_STAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\+\d{2}:\d{2}|Z))?"
)
_SLASH_DATE = re.compile(r"\d{1,2}/\d{1,2}/\d{4}")
_FRONT_MATTER_DATE = re.compile(r"(?m)^date:\s*(\d{4}-\d{2}-\d{2})\s*$")


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


def _scan_unexcused(report: str, snapshot: IssuerSnapshot, analyze_text: str) -> list[str]:
    allowed = snapshot_allow_list(snapshot, analyze_text)
    file_dates = _date_stamps(snapshot, analyze_text)
    cutoff = _FRONT_MATTER_DATE.search(report)
    if cutoff:
        file_dates.add(cutoff.group(1))
    missed: list[str] = []
    for line in report.splitlines():
        visible = re.sub(r"`[^`]+`", " ", line)
        visible = re.sub(r"[\w./-]+\.md", " ", visible)
        present: set[str] = set()
        for stamp in file_dates:
            if stamp in line:
                for part in re.split(r"[-/T:+]", stamp):
                    if part.isdigit():
                        present.add(part)
                        present.add(str(int(part)))
        for match in _NUMBER_IN_TEXT.finditer(visible):
            raw = match.group(0)
            cleaned = raw.replace(",", "")
            if "." not in cleaned and cleaned in present:
                continue
            try:
                as_dec = format(Decimal(cleaned), "f")
            except Exception:
                missed.append(raw)
                continue
            if cleaned in allowed or as_dec in allowed:
                continue
            missed.append(raw)
    return missed


def unexcused_numbers(
    report: str,
    snapshot: IssuerSnapshot,
    analyze_text: str,
    lines: Mapping[str, tuple[str, ...]] | None,
) -> list[str]:
    if lines:
        raise NotImplementedError
    return _scan_unexcused(report, snapshot, analyze_text)
