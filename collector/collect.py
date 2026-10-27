from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from collector.schema import validate_dataset
from collector.source_ipowatch import AdapterNotConfigured, SOURCE_URL, extract_records, inspect_source

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
IPOS_FILE = DATA_DIR / "ipos.json"
STATUS_FILE = DATA_DIR / "status.json"
INSPECTION_FILE = DATA_DIR / "source-inspection.json"
HISTORY_DIR = DATA_DIR / "history"
USER_AGENT = "PersonalIPOResearchTracker/1.0 (source attribution enabled)"
TIMEOUT_SECONDS = 20
DEFAULT_IPOS_PAYLOAD = {
    "source": SOURCE_URL,
    "updated_at": None,
    "data_state": "awaiting_first_successful_collection",
    "demo": False,
    "ipos": [],
}
DEFAULT_STATUS_PAYLOAD = {
    "state": "warning",
    "status": "warning",
    "message": "Waiting for a verified, permitted source adapter.",
    "source": SOURCE_URL,
    "checked_at": None,
    "last_success_at": None,
    "source_reachable": None,
    "next_scheduled_run": "Daily, 09:00 IST",
    "lastAttemptUtc": None,
    "lastSuccessUtc": None,
    "sourceObservedAt": None,
    "nextScheduledRunUtc": None,
    "lastError": None,
}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback


def atomic_write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=str(path.parent), encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        temp_name = handle.name
    Path(temp_name).replace(path)


def inspect_source() -> dict:
    response = requests.get(
        SOURCE_URL,
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    html = response.text or ""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    tables = soup.find_all("table")
    gmp_text_detected = bool(
        re.search(r"\bGMP\b|Grey Market Premium|GMP\s*[:\-]?\s*₹?\d+", html, flags=re.IGNORECASE)
    )

    return {
        "source_url": SOURCE_URL,
        "http_status": response.status_code,
        "page_title": title,
        "table_count": len(tables),
        "gmp_text_detected": gmp_text_detected,
        "captured_at_utc": now_utc(),
    }


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    status = read_json(STATUS_FILE, DEFAULT_STATUS_PAYLOAD)
    if not isinstance(status, dict):
        status = dict(DEFAULT_STATUS_PAYLOAD)
    status["state"] = status.get("state") or status.get("status") or "warning"
    status["status"] = status["state"]
    status["source"] = SOURCE_URL
    status["checked_at"] = now_utc()
    status["next_scheduled_run"] = status.get("next_scheduled_run") or "Daily, 09:00 IST"

    current_dataset = read_json(IPOS_FILE, DEFAULT_IPOS_PAYLOAD)
    if not isinstance(current_dataset, dict):
        current_dataset = dict(DEFAULT_IPOS_PAYLOAD)

    inspection = {"source_url": SOURCE_URL, "error": None}
    try:
        inspection = inspect_source()
        status["source_reachable"] = inspection.get("http_status") == 200
        status["state"] = "warning"
        status["status"] = "warning"
        status["message"] = "Source inspection complete; live GMP extraction still needs verification against the page structure."
        status["lastError"] = None
        status["lastAttemptUtc"] = now_utc()
        status["sourceObservedAt"] = now_utc()
        status["nextScheduledRunUtc"] = "Daily, 09:00 IST"

        try:
            extracted = extract_records()
            observation_date = datetime.now(timezone.utc).date().isoformat()
            previous_records = {
                record.get("id"): record
                for record in current_dataset.get("ipos", [])
                if isinstance(record, dict) and isinstance(record.get("id"), str)
            }
            for ipo in extracted:
                previous = previous_records.get(ipo["id"], {})
                gmp = ipo.get("gmp")
                history = list(previous.get("gmpHistory", []))
                if gmp is None:
                    ipo["gmp"] = previous.get("gmp")
                    ipo["gmpPercent"] = previous.get("gmpPercent")
                else:
                    observation = {"date": observation_date, "value": gmp}
                    if history and history[-1].get("date") == observation_date:
                        history[-1] = observation
                    else:
                        history.append(observation)
                ipo["gmpHistory"] = history
                for field in ("issueSizeCr", "openDate", "closeDate", "allotmentDate", "listingDate"):
                    if ipo.get(field) is None:
                        ipo[field] = previous.get(field)
            validated = validate_dataset({**current_dataset, **{"ipos": extracted}})
            current_dataset = validated
            current_dataset["updated_at"] = now_utc()
            current_dataset["data_state"] = "live"
            current_dataset["demo"] = False
            status["state"] = "success"
            status["status"] = "success"
            status["message"] = "Live collection succeeded and records were validated."
            status["last_success_at"] = now_utc()
            status["lastSuccessUtc"] = status["last_success_at"]
            atomic_write_json(IPOS_FILE, current_dataset)
        except AdapterNotConfigured:
            status["state"] = "warning"
            status["status"] = "warning"
            status["message"] = "Waiting for a verified, permitted source adapter."
            status["last_success_at"] = status.get("last_success_at")
            status["lastSuccessUtc"] = status.get("lastSuccessUtc") or status.get("last_success_at")
            current_dataset.setdefault("data_state", "awaiting_first_successful_collection")
            current_dataset["updated_at"] = None
            current_dataset["demo"] = False
            current_dataset["ipos"] = list(current_dataset.get("ipos", []))
            # Preserve the last good dataset instead of overwriting it with empty data.
            atomic_write_json(IPOS_FILE, current_dataset)
    except requests.RequestException as exc:
        status["state"] = "failed"
        status["status"] = "failed"
        status["message"] = f"Source check failed: {exc}"
        status["source_reachable"] = False
        status["lastError"] = str(exc)
        status["lastAttemptUtc"] = now_utc()
    except Exception as exc:  # pragma: no cover - defensive fallback
        status["state"] = "failed"
        status["status"] = "failed"
        status["message"] = f"Unexpected inspection failure: {exc}"
        status["source_reachable"] = False
        status["lastError"] = str(exc)
        status["lastAttemptUtc"] = now_utc()

    status["checked_at"] = now_utc()
    status["last_success_at"] = status.get("last_success_at")
    status["lastSuccessUtc"] = status.get("lastSuccessUtc") or status.get("last_success_at")
    status["source_reachable"] = bool(status.get("source_reachable")) if status.get("source_reachable") is not None else None

    atomic_write_json(INSPECTION_FILE, inspection)
    atomic_write_json(STATUS_FILE, status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
