from __future__ import annotations

import csv
import io
import json
import os
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from usmarket.types import (
    AnnualFact,
    FetchFailure,
    FilingRef,
    InsiderTrade,
    IssuerSnapshot,
    LabeledDecimal,
    MarketPrint,
    Percent,
    PrintKind,
    ShareCount,
    SourceLabel,
    TreasuryYield,
    UnscaledAmount,
)

_ET = ZoneInfo("America/New_York")
_ANNUAL_FORMS = ("10-K", "20-F", "40-F")
_FLOW_TAGS = {
    "revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ),
    "cogs": ("CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold"),
    "gross_profit": ("GrossProfit",),
    "operating_income": ("OperatingIncomeLoss",),
    "net_income": ("NetIncomeLoss",),
    "sbc": ("ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"),
    "depreciation": (
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
    ),
    "capex": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "cfo": ("NetCashProvidedByUsedInOperatingActivities",),
    "buybacks": ("PaymentsForRepurchaseOfCommonStock",),
}
_SHARE_TAGS = (
    "EntityCommonStockSharesOutstanding",
    "CommonStockSharesOutstanding",
)
_INSTANT_TAGS = {
    "inventory": ("InventoryNet",),
}


def repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class SecConfigError(Exception):
    pass


def sec_user_agent(path: str | None = None) -> str:
    env = os.environ.get("SEC_USER_AGENT", "").strip()
    if env:
        return env
    path = path or os.path.join(repo_root(), "local", "sec_user_agent.txt")
    try:
        with open(path, encoding="utf-8") as handle:
            line = handle.readline().strip()
    except OSError:
        line = ""
    if line:
        return line
    return "AI Berkshire peterliu2357-sky@users.noreply.github.com"


def http_get(
    url: str,
    user_agent: str,
    timeout: int = 40,
    opener=None,
    sleep=None,
    cache_dir: str | None = None,
    attempts: int = 2,
) -> tuple[int, bytes]:
    del cache_dir, attempts
    pause = time.sleep if sleep is None else sleep
    open_url = urllib.request.urlopen if opener is None else opener
    last = (0, b"")
    for _attempt in range(2):
        if "sec.gov" in url:
            pause(0.2)
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": user_agent,
                "Accept": "application/json,text/csv,text/plain,*/*",
            },
        )
        try:
            with open_url(request, timeout=timeout) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            body = error.read() if error.fp is not None else b""
            return error.code, body
        except (urllib.error.URLError, TimeoutError) as error:
            reason = getattr(error, "reason", error)
            last = (0, str(reason).encode("utf-8", "replace"))
    return last


def yahoo_chart_url(ticker: str, host: str = "query1") -> str:
    return (
        f"https://{host}.finance.yahoo.com/v8/finance/chart/"
        f"{ticker}?range=5d&interval=1d"
    )


def nasdaq_info_url(ticker: str) -> str:
    return f"https://api.nasdaq.com/api/quote/{ticker}/info?assetclass=stocks"


def nasdaq_summary_url(ticker: str) -> str:
    return f"https://api.nasdaq.com/api/quote/{ticker}/summary?assetclass=stocks"


def nasdaq_financials_url(ticker: str) -> str:
    return f"https://api.nasdaq.com/api/company/{ticker}/financials?frequency=1"


def sec_tickers_url() -> str:
    return "https://www.sec.gov/files/company_tickers.json"


def sec_submissions_url(cik: str) -> str:
    return f"https://data.sec.gov/submissions/CIK{cik}.json"


def sec_facts_url(cik: str) -> str:
    return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


def fred_dgs10_url() -> str:
    return "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"


def treasury_yield_url(year: int) -> str:
    return (
        "https://home.treasury.gov/resource-center/data-chart-center/"
        f"interest-rates/daily-treasury-rates.csv/{year}/all"
        "?type=daily_treasury_yield_curve"
        f"&field_tdr_date_value={year}&page&_format=csv"
    )


def _loads(body: bytes) -> dict | None:
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _price_text(text: str) -> Decimal | None:
    cleaned = text.strip().replace("$", "").replace(",", "")
    if cleaned in {"", "--", "N/A"}:
        return None
    try:
        return Decimal(cleaned)
    except Exception:
        return None


def _parse_et(text: str) -> datetime | None:
    cleaned = text.replace("Closed at ", "").replace(" ET", "").strip()
    try:
        parsed = datetime.strptime(cleaned, "%b %d, %Y %I:%M %p")
    except ValueError:
        return None
    return parsed.replace(tzinfo=_ET)


def parse_yahoo_chart(body: bytes, ticker: str) -> tuple[list[MarketPrint], list[LabeledDecimal], str]:
    data = _loads(body)
    if data is None:
        return [], [], "yahoo chart was not JSON"
    result = (data.get("chart") or {}).get("result") or []
    if not result:
        return [], [], "yahoo chart had no result"
    meta = result[0].get("meta") or {}
    if meta.get("currency") != "USD":
        return [], [], f"yahoo currency is {meta.get('currency')}"
    price = meta.get("regularMarketPrice")
    stamp = meta.get("regularMarketTime")
    period = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
    prints: list[MarketPrint] = []
    start = None
    if price is not None and stamp is not None and period.get("start") and period.get("end"):
        as_of = datetime.fromtimestamp(int(stamp), timezone.utc)
        start = datetime.fromtimestamp(int(period["start"]), timezone.utc)
        end = datetime.fromtimestamp(int(period["end"]), timezone.utc)
        if start <= as_of < end:
            kind = PrintKind.INTRADAY_LAST
        else:
            kind = PrintKind.OFFICIAL_CLOSE
        prints.append(
            MarketPrint(ticker, Decimal(str(price)), kind, as_of, "yahoo_chart")
        )
    if start is not None:
        timestamps = result[0].get("timestamp") or []
        quote_rows = (result[0].get("indicators") or {}).get("quote") or []
        closes = quote_rows[0].get("close") if quote_rows else None
        for bar_stamp, raw in zip(timestamps, closes or []):
            if bar_stamp is None or raw is None:
                continue
            bar_at = datetime.fromtimestamp(int(bar_stamp), timezone.utc)
            if bar_at >= start:
                continue
            cents = Decimal(str(raw)).quantize(Decimal("0.01"))
            prints.append(
                MarketPrint(ticker, cents, PrintKind.OFFICIAL_CLOSE, bar_at, "yahoo_daily_close")
            )
    ranges: list[LabeledDecimal] = []
    for label, key in (
        ("fifty_two_week_high", "fiftyTwoWeekHigh"),
        ("fifty_two_week_low", "fiftyTwoWeekLow"),
    ):
        raw = meta.get(key)
        if raw is None:
            continue
        ranges.append(LabeledDecimal(label, Decimal(str(raw)), "yahoo_chart"))
    return prints, ranges, ""


def parse_nasdaq_info(body: bytes, ticker: str) -> tuple[list[MarketPrint], str]:
    data = _loads(body)
    if data is None or not isinstance(data.get("data"), dict):
        return [], "nasdaq info was not JSON"
    payload = data["data"]
    status = str(payload.get("marketStatus") or "")
    prints: list[MarketPrint] = []
    primary = payload.get("primaryData") or {}
    primary_at = _parse_et(str(primary.get("lastTradeTimestamp") or ""))
    primary_price = _price_text(str(primary.get("lastSalePrice") or ""))
    if primary_price is not None and primary_at is not None:
        if status in {"Pre-Market", "After-Hours"}:
            kind = PrintKind.EXTENDED_HOURS
        elif status == "Open":
            kind = PrintKind.INTRADAY_LAST
        else:
            kind = PrintKind.OFFICIAL_CLOSE
        prints.append(MarketPrint(ticker, primary_price, kind, primary_at, "nasdaq_info"))
    secondary = payload.get("secondaryData") or {}
    secondary_text = str(secondary.get("lastTradeTimestamp") or "")
    secondary_at = _parse_et(secondary_text)
    secondary_price = _price_text(str(secondary.get("lastSalePrice") or ""))
    if secondary_price is not None and secondary_at is not None and "Closed at" in secondary_text:
        prints.append(
            MarketPrint(
                ticker,
                secondary_price,
                PrintKind.OFFICIAL_CLOSE,
                secondary_at,
                "nasdaq_info",
            )
        )
    return prints, ""


def nasdaq_text_labels(info_body: bytes, summary_body: bytes) -> list[SourceLabel]:
    found: list[SourceLabel] = []
    info = _loads(info_body) or {}
    data = info.get("data") if isinstance(info.get("data"), dict) else {}
    if data.get("companyName"):
        found.append(SourceLabel("company_name", str(data["companyName"]), "nasdaq_info"))
    if data.get("exchange"):
        found.append(SourceLabel("exchange", str(data["exchange"]), "nasdaq_info"))
    summary = _loads(summary_body) or {}
    block = {}
    if isinstance(summary.get("data"), dict):
        raw = (summary["data"].get("summaryData") or {})
        if isinstance(raw, dict):
            block = raw
    for key, label in (
        ("Sector", "sector"),
        ("Industry", "industry"),
        ("FiftTwoWeekHighLow", "fifty_two_week_high_low"),
    ):
        cell = block.get(key) or {}
        if not isinstance(cell, dict):
            continue
        value = str(cell.get("value") or "").strip()
        if value and value not in {"N/A", "--"}:
            found.append(SourceLabel(label, value, "nasdaq_summary"))
    return found


def parse_nasdaq_summary_cap(body: bytes) -> UnscaledAmount | None:
    data = _loads(body)
    if data is None:
        return None
    summary = (data.get("data") or {}).get("summaryData") or {}
    cell = summary.get("MarketCap") or {}
    lexeme = str(cell.get("value") or "").strip()
    if not lexeme or lexeme in {"N/A", "--"}:
        return None
    return UnscaledAmount(lexeme, "Market Cap", "", "nasdaq_summary")


def parse_nasdaq_financials(body: bytes) -> tuple[list[UnscaledAmount], list[Percent]]:
    data = _loads(body)
    if data is None:
        return [], []
    tables = data.get("data") or {}
    unscaled: list[UnscaledAmount] = []
    percents: list[Percent] = []
    for table_name in ("incomeStatementTable", "balanceSheetTable", "cashFlowTable", "financialRatiosTable"):
        table = tables.get(table_name) or {}
        headers = table.get("headers") or {}
        for row in table.get("rows") or []:
            label = str(row.get("value1") or "").strip()
            if not label:
                continue
            for key, period in headers.items():
                if key == "value1":
                    continue
                cell = str(row.get(key) or "").strip()
                if cell in {"", "--", "N/A"}:
                    continue
                period_end = str(period)
                if "%" in cell and "$" not in cell:
                    number = _price_text(cell.replace("%", ""))
                    if number is None:
                        continue
                    percents.append(Percent(number, label, period_end, "nasdaq_financials"))
                elif "$" in cell:
                    unscaled.append(UnscaledAmount(cell, label, period_end, "nasdaq_financials"))
    return unscaled, percents


def _later(current: TreasuryYield | None, candidate: TreasuryYield) -> TreasuryYield:
    if current is None or candidate.as_of > current.as_of:
        return candidate
    return current


def parse_fred_dgs10(body: bytes) -> TreasuryYield | None:
    text = body.decode("utf-8", "replace").lstrip("\ufeff")
    lines = text.splitlines()
    if not lines or "DGS10" not in lines[0]:
        return None
    latest: TreasuryYield | None = None
    for row in csv.DictReader(io.StringIO(text)):
        raw = (row.get("DGS10") or "").strip()
        if raw in {"", "."}:
            continue
        date_text = (row.get("DATE") or row.get("observation_date") or "").strip()
        try:
            rate = (Decimal(raw) / Decimal(100)).quantize(Decimal("0.0001"))
            as_of = date.fromisoformat(date_text)
        except Exception:
            continue
        latest = _later(latest, TreasuryYield(as_of, rate, "fred_dgs10"))
    return latest


def parse_treasury_par(body: bytes) -> TreasuryYield | None:
    text = body.decode("utf-8", "replace")
    lines = text.splitlines()
    if not lines or "10 Yr" not in lines[0]:
        return None
    latest: TreasuryYield | None = None
    for row in csv.DictReader(io.StringIO(text)):
        raw = (row.get("10 Yr") or "").strip()
        if raw in {"", "N/A", "."}:
            continue
        try:
            as_of = datetime.strptime(row["Date"], "%m/%d/%Y").date()
            rate = (Decimal(raw) / Decimal(100)).quantize(Decimal("0.0001"))
        except Exception:
            continue
        latest = _later(latest, TreasuryYield(as_of, rate, "treasury_par"))
    return latest


def parse_cik(body: bytes, ticker: str) -> str | None:
    data = _loads(body)
    if data is None:
        return None
    wanted = ticker.upper()
    rows = data.values() if all(isinstance(item, dict) for item in data.values()) else data
    if isinstance(data, dict) and "0" not in data and "cik_str" in data:
        rows = [data]
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("ticker", "")).upper() == wanted:
            return f"{int(row['cik_str']):010d}"
    return None


def _archive_url(cik: str, accession: str, filename: str) -> str:
    acc = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{filename}"


def parse_submissions(body: bytes, cik: str) -> list[FilingRef]:
    data = _loads(body)
    if data is None:
        return []
    recent = (data.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    dates = recent.get("filingDate") or []
    accessions = recent.get("accessionNumber") or []
    docs = recent.get("primaryDocument") or []
    items = recent.get("items") or []
    found: list[FilingRef] = []
    form4 = 0
    for index, form in enumerate(forms):
        item = items[index] if index < len(items) else ""
        keep = form in {"10-K", "10-Q", "10-K/A", "DEF 14A", "20-F", "40-F", "6-K"}
        if form == "8-K" and "2.02" in str(item):
            keep = True
        if form == "4" and form4 < 5:
            keep = True
            form4 += 1
        if not keep:
            continue
        if index >= len(accessions) or index >= len(docs) or index >= len(dates):
            continue
        accession = accessions[index]
        filename = docs[index]
        found.append(
            FilingRef(
                form=form,
                filed=date.fromisoformat(dates[index]),
                accession=accession,
                url=_archive_url(cik, accession, filename),
            )
        )
    return found


def _iso(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _instant_rows(entries: list[dict]) -> list[dict]:
    chosen: dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("start"):
            continue
        if entry.get("segment") or entry.get("segments"):
            continue
        form = str(entry.get("form") or "")
        if not form.startswith(_ANNUAL_FORMS):
            continue
        end = _iso(entry.get("end"))
        if end is None:
            continue
        key = end.isoformat()
        previous = chosen.get(key)
        if previous is None or str(entry.get("filed") or "") >= str(previous.get("filed") or ""):
            chosen[key] = entry
    return list(chosen.values())


def _annual_rows(entries: list[dict]) -> list[dict]:
    chosen: dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("segment") or entry.get("segments"):
            continue
        form = str(entry.get("form") or "")
        if not form.startswith(_ANNUAL_FORMS):
            continue
        start = _iso(entry.get("start"))
        end = _iso(entry.get("end"))
        if start is None or end is None:
            continue
        span = (end - start).days
        if span < 300 or span > 380:
            continue
        key = end.isoformat()
        previous = chosen.get(key)
        if previous is None or str(entry.get("filed") or "") >= str(previous.get("filed") or ""):
            chosen[key] = entry
    return list(chosen.values())


def _best_tag_rows(gaap: dict, tags: tuple[str, ...], row_fn) -> tuple[str, list[dict]]:
    best_tag = ""
    best_rows: list[dict] = []
    best_key = (-1, "")
    for tag in tags:
        node = gaap.get(tag) or {}
        units = (node.get("units") or {}).get("USD") or []
        rows = row_fn(units)
        if not rows:
            continue
        end = max(str(row.get("end") or "") for row in rows)
        key = (len(rows), end)
        if key > best_key:
            best_key = key
            best_tag = tag
            best_rows = rows
    return best_tag, best_rows


def _facts_from_rows(concept: str, tag: str, rows: list[dict], keep_start: bool) -> list[AnnualFact]:
    found: list[AnnualFact] = []
    for row in rows:
        end = _iso(row.get("end"))
        filed = _iso(row.get("filed"))
        if end is None or filed is None:
            continue
        found.append(
            AnnualFact(
                fiscal_year=int(row.get("fy") or end.year),
                end=end,
                concept=concept,
                ones=Decimal(str(row["val"])),
                filed=filed,
                tag=tag,
                start=_iso(row.get("start")) if keep_start else None,
            )
        )
    return found


def parse_companyfacts(body: bytes) -> tuple[list[AnnualFact], ShareCount | None]:
    data = _loads(body)
    if data is None:
        return [], None
    facts = data.get("facts") or {}
    gaap = facts.get("us-gaap") or {}
    annual: list[AnnualFact] = []
    for concept, tags in _FLOW_TAGS.items():
        tag, rows = _best_tag_rows(gaap, tags, _annual_rows)
        annual.extend(_facts_from_rows(concept, tag, rows, True))
    for concept, tags in _INSTANT_TAGS.items():
        tag, rows = _best_tag_rows(gaap, tags, _instant_rows)
        annual.extend(_facts_from_rows(concept, tag, rows, False))
    shares = _latest_shares(facts)
    return annual, shares


def _latest_shares(facts: dict) -> ShareCount | None:
    candidates: list[tuple[str, dict]] = []
    for namespace in ("dei", "us-gaap"):
        bucket = facts.get(namespace) or {}
        for tag in _SHARE_TAGS:
            units = ((bucket.get(tag) or {}).get("units") or {}).get("shares") or []
            for entry in units:
                if not isinstance(entry, dict):
                    continue
                if entry.get("start"):
                    continue
                if entry.get("segment") or entry.get("segments"):
                    continue
                end = _iso(entry.get("end"))
                if end is None:
                    continue
                candidates.append((tag, entry))
    if not candidates:
        return None
    tag, entry = max(
        candidates,
        key=lambda item: (str(item[1].get("end") or ""), str(item[1].get("filed") or "")),
    )
    end = _iso(entry.get("end"))
    if end is None:
        return None
    return ShareCount(Decimal(str(entry["val"])), end, tag)


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def parse_form4(body: bytes, url: str, filed: date) -> list[InsiderTrade]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return []
    owners = []
    for node in root.iter():
        if _local(node.tag) == "rptOwnerName" and node.text:
            owners.append(node.text.strip())
    owner = owners[0] if owners else ""
    trades: list[InsiderTrade] = []
    for node in root.iter():
        if _local(node.tag) != "nonDerivativeTransaction":
            continue
        values = {_local(child.tag): child for child in node.iter()}
        code = ""
        acquired = ""
        shares = None
        price = None
        when = filed
        for item in node.iter():
            name = _local(item.tag)
            if name == "transactionCode" and item.text:
                code = item.text.strip()
            elif name == "transactionAcquiredDisposedCode":
                for child in item.iter():
                    if _local(child.tag) == "value" and child.text:
                        acquired = child.text.strip()
            elif name == "transactionShares":
                for child in item.iter():
                    if _local(child.tag) == "value" and child.text:
                        shares = Decimal(child.text.strip())
            elif name == "transactionPricePerShare":
                for child in item.iter():
                    if _local(child.tag) == "value" and child.text:
                        price = Decimal(child.text.strip())
            elif name == "transactionDate":
                for child in item.iter():
                    if _local(child.tag) == "value" and child.text:
                        parsed = _iso(child.text.strip())
                        if parsed is not None:
                            when = parsed
        if shares is None or not code:
            continue
        trades.append(
            InsiderTrade(when, owner, code, acquired, shares, price, url)
        )
    return trades


def _failure(source: str, status: int, url: str, detail: str = "") -> FetchFailure:
    return FetchFailure(source, status, url, detail)


def fetch_quotes(ticker: str, get) -> tuple[tuple[MarketPrint, ...], tuple[FetchFailure, ...]]:
    prints: list[MarketPrint] = []
    failures: list[FetchFailure] = []
    chart_url = yahoo_chart_url(ticker)
    status, body = get(chart_url)
    if status != 200:
        alt = yahoo_chart_url(ticker, "query2")
        alt_status, alt_body = get(alt)
        if alt_status == 200:
            chart_url, status, body = alt, alt_status, alt_body
    if status == 200:
        found, _, detail = parse_yahoo_chart(body, ticker)
        prints.extend(found)
        if detail:
            failures.append(_failure("yahoo_chart", status, chart_url, detail))
    else:
        failures.append(_failure("yahoo_chart", status, chart_url))
    info_url = nasdaq_info_url(ticker)
    status, body = get(info_url)
    if status == 200:
        found, detail = parse_nasdaq_info(body, ticker)
        prints.extend(found)
        if detail:
            failures.append(_failure("nasdaq_info", status, info_url, detail))
    else:
        failures.append(_failure("nasdaq_info", status, info_url))
    return tuple(prints), tuple(failures)


def build_snapshot(ticker: str, get) -> IssuerSnapshot:
    prints: list[MarketPrint] = []
    ranges: list[LabeledDecimal] = []
    unscaled: list[UnscaledAmount] = []
    percents: list[Percent] = []
    yields: list[TreasuryYield] = []
    filings: list[FilingRef] = []
    annual: list[AnnualFact] = []
    insiders: list[InsiderTrade] = []
    failures: list[FetchFailure] = []
    labels: list[SourceLabel] = []
    shares: ShareCount | None = None
    info_body = b""
    summary_body = b""

    chart_url = yahoo_chart_url(ticker)
    status, body = get(chart_url)
    if status != 200:
        alt = yahoo_chart_url(ticker, "query2")
        alt_status, alt_body = get(alt)
        if alt_status == 200:
            chart_url, status, body = alt, alt_status, alt_body
    if status == 200:
        found, span, detail = parse_yahoo_chart(body, ticker)
        prints.extend(found)
        ranges.extend(span)
        if detail:
            failures.append(_failure("yahoo_chart", status, chart_url, detail))
    else:
        failures.append(_failure("yahoo_chart", status, chart_url))

    info_url = nasdaq_info_url(ticker)
    status, body = get(info_url)
    if status == 200:
        info_body = body
        found, detail = parse_nasdaq_info(body, ticker)
        prints.extend(found)
        if detail:
            failures.append(_failure("nasdaq_info", status, info_url, detail))
    else:
        failures.append(_failure("nasdaq_info", status, info_url))

    summary_url = nasdaq_summary_url(ticker)
    status, body = get(summary_url)
    if status == 200:
        summary_body = body
        cap = parse_nasdaq_summary_cap(body)
        if cap is not None:
            unscaled.append(cap)
    else:
        failures.append(_failure("nasdaq_summary", status, summary_url))
    labels.extend(nasdaq_text_labels(info_body, summary_body))

    fin_url = nasdaq_financials_url(ticker)
    status, body = get(fin_url)
    if status == 200:
        cells, ratios = parse_nasdaq_financials(body)
        unscaled.extend(cells)
        percents.extend(ratios)
    else:
        failures.append(_failure("nasdaq_financials", status, fin_url))

    fred_url = fred_dgs10_url()
    status, body = get(fred_url)
    if status == 200:
        found = parse_fred_dgs10(body)
        if found is not None:
            yields.append(found)
        else:
            failures.append(_failure("fred_dgs10", status, fred_url, "no numeric DGS10 row"))
    else:
        failures.append(_failure("fred_dgs10", status, fred_url))

    year = date.today().year
    treasury_url = treasury_yield_url(year)
    status, body = get(treasury_url)
    if status == 200:
        found = parse_treasury_par(body)
        if found is not None:
            yields.append(found)
        else:
            failures.append(_failure("treasury_par", status, treasury_url, "no 10 Yr row"))
    else:
        failures.append(_failure("treasury_par", status, treasury_url))

    tickers_url = sec_tickers_url()
    status, body = get(tickers_url)
    cik = None
    if status == 200:
        cik = parse_cik(body, ticker)
        if cik is None:
            failures.append(_failure("sec_company_tickers", status, tickers_url, "ticker missing"))
    else:
        failures.append(_failure("sec_company_tickers", status, tickers_url))

    if cik is not None:
        sub_url = sec_submissions_url(cik)
        status, body = get(sub_url)
        if status == 200:
            filings = parse_submissions(body, cik)
        else:
            failures.append(_failure("sec_submissions", status, sub_url))
        facts_url = sec_facts_url(cik)
        status, body = get(facts_url)
        if status == 200:
            annual, shares = parse_companyfacts(body)
        else:
            failures.append(_failure("sec_companyfacts", status, facts_url))
        for filing in filings:
            if filing.form != "4":
                continue
            status, body = get(filing.url)
            if status != 200:
                failures.append(_failure("sec_form4", status, filing.url))
                continue
            insiders.extend(parse_form4(body, filing.url, filing.filed))

    return IssuerSnapshot(
        ticker=ticker,
        prints=tuple(prints),
        filings=tuple(filings),
        annual=tuple(annual),
        shares=shares,
        yields=tuple(yields),
        unscaled=tuple(unscaled),
        percents=tuple(percents),
        ranges=tuple(ranges),
        labels=tuple(labels),
        insiders=tuple(insiders),
        failures=tuple(failures),
    )
