from __future__ import annotations

import os
import re
from typing import Any

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
    cleaned = re.sub(r"[^0-9.\-]", "", text)
    if not cleaned or cleaned in {"-", "."}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "ipo"


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

    gmp_value = _parse_numeric(cells[1])
    issue_min = _parse_numeric(cells[3])
    issue_max_and_percent = cells[4] if len(cells) > 4 else ""
    issue_max = None
    gmp_percent = None

    match = re.search(r"₹?\s*([\d,]+(?:\.\d+)?)\s*\(([-+]?\d+(?:\.\d+)?)%\)", issue_max_and_percent)
    if match:
        issue_max = float(match.group(1).replace(",", ""))
        gmp_percent = float(match.group(2))
    elif issue_min is not None:
        issue_max = issue_min

    if gmp_value is None and issue_min is not None:
        gmp_value = issue_min

    observed_date = None
    record = {
        "id": f"{_slugify(name)}-{category.lower()}",
        "company": name,
        "category": category,
        "status": status,
        "issuePriceLow": issue_min,
        "issuePriceHigh": issue_max,
        "gmp": gmp_value,
        "gmpPercent": gmp_percent,
        "gmpHistory": [],
        "openDate": None,
        "closeDate": None,
        "allotmentDate": None,
        "listingDate": None,
    }
    return record


def extract_records(html: str | None = None, timeout: int = 20) -> list[dict[str, Any]]:
    """Extract the live Current Mainboard/SME GMP tables from the IPO Watch homepage."""
    if html is None:
        headers = {"User-Agent": "IPO-GMP-Tracker/1.0 (personal research project)"}
        response = requests.get(SOURCE_URL, headers=headers, timeout=timeout)
        response.raise_for_status()
        html = response.text or ""

    soup = BeautifulSoup(html, "html.parser")
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for section_name, category in (("Current Mainboard IPO GMP", "Mainboard"), ("Current SME IPO GMP", "SME")):
        heading = soup.find(string=re.compile(re.escape(section_name), re.IGNORECASE))
        if not heading:
            continue
        table = heading.find_parent("h2")
        if table is not None:
            table = table.find_next("table")
        else:
            table = heading.find_next("table")
        if not table:
            continue
        for row in table.find_all("tr"):
            parsed = _parse_gmp_row(row, category)
            if parsed is None:
                continue
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
    return records


def _source_is_configured() -> bool:
    return os.getenv("IPOWATCH_ACCESS_CONFIRMED", "").strip().lower() in {"1", "true", "yes"}
