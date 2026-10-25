from __future__ import annotations

from datetime import date
from typing import Any

REQUIRED_TEXT_FIELDS = ("id", "company", "category", "status")


def normalize_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize one IPO record."""
    if not isinstance(raw, dict):
        raise ValueError("IPO record must be an object")

    record = dict(raw)

    for field in REQUIRED_TEXT_FIELDS:
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Missing or invalid field: {field}")
        record[field] = value.strip()

    category = record["category"].lower()
    if category not in {"mainboard", "sme"}:
        raise ValueError("category must be Mainboard or SME")
    record["category"] = "Mainboard" if category == "mainboard" else "SME"

    status = record["status"].lower()
    allowed_statuses = {"upcoming", "open", "closed", "listed"}
    if status not in allowed_statuses:
        raise ValueError("status must be one of: Upcoming, Open, Closed, Listed")
    record["status"] = status.title()

    for field in ("issuePriceLow", "issuePriceHigh", "gmp", "gmpPercent"):
        value = record.get(field)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{field} must be numeric or null")
        record[field] = float(value)

    low = record.get("issuePriceLow")
    high = record.get("issuePriceHigh")
    if low is not None and high is not None and low > high:
        raise ValueError("issuePriceLow cannot exceed issuePriceHigh")

    history = record.get("gmpHistory")
    if not isinstance(history, list):
        raise ValueError("gmpHistory must be a list")
    for observation in history:
        if not isinstance(observation, dict):
            raise ValueError("gmpHistory entries must be objects")
        observation_date = observation.get("date")
        try:
            date.fromisoformat(observation_date)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid GMP history date: {observation_date}") from exc
        value = observation.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("GMP history values must be numeric")

    for field in ("openDate", "closeDate", "allotmentDate", "listingDate"):
        value = record.get(field)
        if value is None:
            continue
        if not isinstance(value, str):
            raise ValueError(f"{field} must be an ISO date string or null")
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"Invalid ISO date for {field}: {value}") from exc

    return record


def validate_dataset(dataset: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(dataset, dict):
        raise ValueError("Dataset must be an object")

    items = dataset.get("ipos")
    if not isinstance(items, list):
        raise ValueError("Dataset must contain an 'ipos' list")

    normalized_items = []
    seen_ids = set()
    for item in items:
        normalized = normalize_record(item)
        if normalized["id"] in seen_ids:
            raise ValueError(f"Duplicate IPO id: {normalized['id']}")
        seen_ids.add(normalized["id"])
        normalized_items.append(normalized)

    dataset_copy = dict(dataset)
    dataset_copy["ipos"] = normalized_items
    return dataset_copy
