from __future__ import annotations

import os
import re
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

SOURCE_URL = "https://ipowatch.in/"


class AdapterNotConfigured(RuntimeError):
    """Raised until a permitted extraction method has been verified."""


def inspect_source(timeout: int = 20) -> dict:
    """Check that IPO Watch is reachable and the homepage has the GMP tables."""
    headers = {
        "User-Agent": "IPO-GMP-Tracker/1.0 (personal research project)",
    }
    response = requests.get(SOURCE_URL, headers=headers, timeout=timeout)
    response.raise_for_status()
    html = response.text or ""
    return {
        "source": SOURCE_URL,
        "http_status": response.status_code,
        "content_type": response.headers.get("content-type", ""),
        "bytes_received": len(response.content),
        "reachable": True,
        "has_gmp_tables": bool(re.search(r"Current\s+(Mainboard|SME)\s+IPO\s+GMP", html, flags=re.IGNORECASE)),
    }


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return re.sub(r"\s+", " ", value).replace("\xa0", " ").strip()


def _parse_numeric(value: Any) -> float | None:
    text = _clean_text(value)
    if not text:
        return None
    match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "ipo"


def _parse_date_range(value: str) -> tuple[str | None, str | None]:
    match = re.fullmatch(r"\s*(\d{1,2})\s*-\s*(\d{1,2})\s+([A-Za-z]+)\s*", value)
    if not match:
        return None, None

    start_day, end_day = int(match.group(1)), int(match.group(2))
    try:
        end_month = datetime.strptime(match.group(3)[:3].title(), "%b").month
    except ValueError:
        return None, None

    today = datetime.now(timezone.utc).date()
    end_year = today.year
    if end_month < today.month and today.month - end_month > 6:
        end_year += 1
    elif end_month > today.month and end_month - today.month > 6:
        end_year -= 1

    start_month, start_year = end_month, end_year
    if start_day > end_day:
        start_month -= 1
        if start_month == 0:
            start_month = 12
            start_year -= 1

    try:
        return (
            date(start_year, start_month, start_day).isoformat(),
            date(end_year, end_month, end_day).isoformat(),
        )
    except ValueError:
        return None, None


def _section_table(soup, section_name: str):
    heading_text = soup.find(string=re.compile(re.escape(section_name), re.IGNORECASE))
    if not heading_text:
        return None
    heading = heading_text.find_parent(["h1", "h2", "h3", "h4", "h5", "h6"])
    return heading.find_next("table") if heading else heading_text.find_next("table")


def _extract_issue_sizes(soup) -> dict[str, float]:
    issue_sizes = {}
    for section_name in ("Latest Mainboard IPO", "Latest SME IPO"):
        table = _section_table(soup, section_name)
        if not table:
            continue
        for row in table.find_all("tr"):
            if row.find("th"):
                continue
            cells = [_clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all("td")]
            if len(cells) < 3:
                continue
            amount = _parse_numeric(cells[2])
            if amount is not None:
                issue_sizes[re.sub(r"[^a-z0-9]", "", cells[0].lower())] = amount
    return issue_sizes


def _parse_history_date(value: str) -> str | None:
    match = re.fullmatch(r"\s*(\d{1,2})\s+([A-Za-z]+)(?:,?\s+(\d{4}))?\s*", value)
    if not match:
        return None
    try:
        month = datetime.strptime(match.group(2)[:3].title(), "%b").month
        today = datetime.now(timezone.utc).date()
        year = int(match.group(3)) if match.group(3) else today.year
        if not match.group(3) and month > today.month:
            year -= 1
        return date(year, month, int(match.group(1))).isoformat()
    except ValueError:
        return None


def _parse_gmp_history(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        for header_row in table.find_all("tr"):
            headers = [
                _clean_text(cell.get_text(" ", strip=True)).lower()
                for cell in header_row.find_all(["th", "td"])
            ]
            date_index = next((i for i, header in enumerate(headers) if "date" in header), None)
            gmp_index = next((i for i, header in enumerate(headers) if "gmp" in header and "trend" not in header), None)
            if date_index is None or gmp_index is None:
                continue

            history = []
            for row in table.find_all("tr"):
                cells = [_clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all("td")]
                if max(date_index, gmp_index) >= len(cells):
                    continue
                observation_date = _parse_history_date(cells[date_index])
                value = _parse_numeric(cells[gmp_index])
                if observation_date is not None and value is not None:
                    history.append({"date": observation_date, "value": value})
            if history:
                return sorted(history, key=lambda observation: observation["date"])
    return []


def _extract_status(raw_name: str) -> str:
    text = _clean_text(raw_name).lower()
    for status in ("upcoming", "open", "closed", "listed"):
        if text.endswith(status):
            return status.title()
    return "Upcoming"


def _extract_name(raw_name: str) -> str:
    text = _clean_text(raw_name)
    for status in ("Upcoming", "Open", "Closed", "Listed"):
        if text.endswith(status):
            return text[: -len(status)].strip()
    return text


def _parse_gmp_row(row, category: str) -> dict[str, Any] | None:
    if row.find("th"):
        return None

    cells = [
        _clean_text(cell.get_text(" ", strip=True))
        for cell in row.find_all("td")
    ]
    if len(cells) < 5:
        return None

    name_cell = cells[0]
    if not name_cell:
        return None

    name = _extract_name(name_cell)
    status = _extract_status(name_cell)
    if not name:
        return None

    detail_link = row.find("a", href=True)
    detail_url = urljoin(SOURCE_URL, detail_link["href"]) if detail_link else None
    if detail_url and urlparse(detail_url).hostname not in {"ipowatch.in", "www.ipowatch.in"}:
        detail_url = None

    open_date, close_date = _parse_date_range(cells[5]) if len(cells) > 5 else (None, None)

    gmp_value = _parse_numeric(cells[1])
    issue_prices = [
        float(value.replace(",", ""))
        for value in re.findall(r"\d[\d,]*(?:\.\d+)?", cells[3])
    ]
    issue_min = min(issue_prices) if issue_prices else None
    issue_max = max(issue_prices) if issue_prices else None
    issue_max_and_percent = cells[4] if len(cells) > 4 else ""
    gmp_percent = None

    match = re.search(r"₹?\s*([\d,]+(?:\.\d+)?)\s*\(([-+]?\d+(?:\.\d+)?)%\)", issue_max_and_percent)
    if match:
        gmp_percent = float(match.group(2))
    if gmp_value is None and issue_min is not None:
        gmp_value = issue_min

    record = {
        "id": f"{_slugify(name)}-{category.lower()}",
        "company": name,
        "sourceUrl": detail_url,
        "category": category,
        "status": status,
        "issuePriceLow": issue_min,
        "issuePriceHigh": issue_max,
        "gmp": gmp_value,
        "gmpPercent": gmp_percent,
        "gmpHistory": [],
        "issueSizeCr": None,
        "openDate": open_date,
        "closeDate": close_date,
        "allotmentDate": None,
        "listingDate": None,
    }
    return record


def extract_records(html: str | None = None, timeout: int = 20) -> list[dict[str, Any]]:
    """Extract the live Current Mainboard/SME GMP tables from the IPO Watch homepage."""
    fetch_detail_pages = html is None
    if html is None:
        headers = {"User-Agent": "IPO-GMP-Tracker/1.0 (personal research project)"}
        response = requests.get(SOURCE_URL, headers=headers, timeout=timeout)
        response.raise_for_status()
        html = response.text or ""

    soup = BeautifulSoup(html, "html.parser")
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    issue_sizes = _extract_issue_sizes(soup)

    for section_name, category in (("Current Mainboard IPO GMP", "Mainboard"), ("Current SME IPO GMP", "SME")):
        table = _section_table(soup, section_name)
        if not table:
            continue
        for row in table.find_all("tr"):
            parsed = _parse_gmp_row(row, category)
            if parsed is None:
                continue
            normalized_name = re.sub(r"[^a-z0-9]", "", parsed["company"].lower())
            for candidate, issue_size in issue_sizes.items():
                if candidate in normalized_name or normalized_name in candidate:
                    parsed["issueSizeCr"] = issue_size
                    break
            record_id = parsed["id"]
            index = 2
            while record_id in seen_ids:
                record_id = f"{parsed['id']}-{index}"
                index += 1
            parsed["id"] = record_id
            seen_ids.add(record_id)
            records.append(parsed)

    if not records:
        raise ValueError("No valid IPO Watch GMP rows were found in the homepage HTML.")

    if fetch_detail_pages:
        headers = {"User-Agent": "IPO-GMP-Tracker/1.0 (personal research project)"}
        for record in records:
            detail_url = record.get("sourceUrl")
            if not detail_url:
                continue
            try:
                response = requests.get(detail_url, headers=headers, timeout=min(timeout, 8))
                response.raise_for_status()
            except requests.RequestException:
                continue
            record["gmpHistory"] = _parse_gmp_history(response.text or "")
    return records


def _source_is_configured() -> bool:
    return os.getenv("IPOWATCH_ACCESS_CONFIRMED", "").strip().lower() in {"1", "true", "yes"}
