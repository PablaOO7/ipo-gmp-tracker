from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
IPOS_FILE = DATA_DIR / "ipos.json"
STATUS_FILE = DATA_DIR / "status.json"
HISTORY_DIR = DATA_DIR / "history"
SOURCE_URL = "https://ipowatch.in/"
USER_AGENT = "PersonalIPOResearchTracker/1.0 (source attribution enabled)"
TIMEOUT_SECONDS = 20


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def inspect_source() -> dict:
    response = requests.get(
        SOURCE_URL,
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    html = response.text or ""
    soup = BeautifulSoup(html, "html.parser")
    page_title = soup.title.get_text(" ", strip=True) if soup.title else ""
    tables = soup.find_all("table")
    gmp_text_detected = bool(
        re.search(r"\bGMP\b|Grey Market Premium|GMP\s*[:\-]?\s*₹?\d+", html, flags=re.IGNORECASE)
    )

    return {
        "source_url": SOURCE_URL,
        "http_status": response.status_code,
        "page_title": page_title,
        "table_count": len(tables),
        "gmp_text_detected": gmp_text_detected,
        "captured_at_utc": now_utc(),
    }


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    status = read_json(
        STATUS_FILE,
        {
            "demo": True,
            "status": "warning",
            "message": "Waiting for the first verified collection.",
            "source": SOURCE_URL,
            "checked_at": None,
            "last_success_at": None,
            "source_reachable": None,
        },
    )

    status["demo"] = bool(status.get("demo", True))
    status["source"] = SOURCE_URL
    status["checked_at"] = now_utc()

    inspection = {"source_url": SOURCE_URL, "error": None}
    try:
        inspection = inspect_source()
        status["status"] = "warning"
        status["message"] = "Source inspection complete; live GMP extraction still needs verification against the page structure."
        status["source_reachable"] = inspection.get("http_status") == 200
        status["lastError"] = None
    except requests.RequestException as exc:
        status["status"] = "error"
        status["message"] = f"Source check failed: {exc}"
        status["source_reachable"] = False
        status["lastError"] = str(exc)
    except Exception as exc:  # pragma: no cover - defensive fallback
        status["status"] = "error"
        status["message"] = f"Unexpected inspection failure: {exc}"
        status["source_reachable"] = False
        status["lastError"] = str(exc)

    write_json(DATA_DIR / "source-inspection.json", inspection)
    write_json(STATUS_FILE, status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
