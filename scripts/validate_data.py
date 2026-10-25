import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "ipos.json"
STATUS_FILE = ROOT / "data" / "status.json"


def fail(message):
    print(f"ERROR: {message}")
    sys.exit(1)


def valid_date(value, field, ipo_id):
    if not isinstance(value, str):
        fail(f"{ipo_id}: {field} must be a date string")
    try:
        date.fromisoformat(value)
    except ValueError:
        fail(f"{ipo_id}: invalid {field}: {value}")


def main():
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        status = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"Cannot read JSON: {exc}")

    if not isinstance(data.get("ipos"), list):
        fail("'ipos' must be a list")
    if not isinstance(data.get("demo"), bool):
        fail("'demo' must be a boolean")
    if not isinstance(status.get("status"), str):
        fail("status.json must contain a status string")

    ids = set()
    for ipo in data["ipos"]:
        ipo_id = ipo.get("id")
        if not isinstance(ipo_id, str) or not ipo_id.strip():
            fail("Every IPO must have a non-empty id")
        if ipo_id in ids:
            fail(f"Duplicate IPO id: {ipo_id}")
        ids.add(ipo_id)

        for field in ("company", "category", "status"):
            if not isinstance(ipo.get(field), str) or not ipo[field].strip():
                fail(f"{ipo_id}: {field} must be a non-empty string")

        for field in ("issuePriceLow", "issuePriceHigh", "gmp"):
            value = ipo.get(field)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
                fail(f"{ipo_id}: {field} must be numeric or null")

        low, high = ipo.get("issuePriceLow"), ipo.get("issuePriceHigh")
        if low is not None and high is not None and low > high:
            fail(f"{ipo_id}: lower issue price exceeds upper issue price")

        history = ipo.get("gmpHistory")
        if not isinstance(history, list):
            fail(f"{ipo_id}: gmpHistory must be a list")

        seen, previous_date = set(), None
        for observation in history:
            if not isinstance(observation, dict):
                fail(f"{ipo_id}: each history observation must be an object")
            valid_date(observation.get("date"), "history date", ipo_id)
            obs_date = observation["date"]
            if obs_date in seen:
                fail(f"{ipo_id}: duplicate GMP date {obs_date}")
            seen.add(obs_date)
            if previous_date and obs_date < previous_date:
                fail(f"{ipo_id}: GMP history must be ordered by date")
            previous_date = obs_date
            value = observation.get("value")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                fail(f"{ipo_id}: GMP value must be numeric")

        for field in ("openDate", "closeDate", "allotmentDate", "listingDate"):
            if ipo.get(field) is not None:
                valid_date(ipo[field], field, ipo_id)
        if history and ipo.get("gmp") is not None and float(ipo["gmp"]) != float(history[-1]["value"]):
            fail(f"{ipo_id}: gmp differs from the latest history value")

    print(f"OK: validated {len(ids)} IPO records")
    print(f"Dataset mode: {'DEMO' if data['demo'] else 'LIVE'}")


if __name__ == "__main__":
    main()
