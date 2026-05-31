from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from .data_loader import load_provider_records
from .models import LocationValidationResponse


ZIP_RE = re.compile(r"^\s*(\d{5})(?:-\d{4})?\s*$")
ZIP_LIKE_RE = re.compile(r"^\s*[\d\s-]+\s*$")


@lru_cache(maxsize=1)
def provider_location_coverage() -> dict[str, dict[str, set[str]]]:
    coverage: dict[str, dict[str, set[str]]] = {"zips": {}, "cities": {}}
    for record in load_provider_records():
        geography_status = record_geography_status(record)
        zip_code = normalize_zip(record.get("zip_code"))
        if zip_code:
            coverage["zips"].setdefault(zip_code, set()).add(geography_status)

        city = normalize_text(record.get("city"))
        if city:
            coverage["cities"].setdefault(city, set()).add(geography_status)

    return coverage


def validate_location(location: str) -> LocationValidationResponse:
    input_value = str(location or "").strip()
    zip_match = ZIP_RE.match(input_value)

    if zip_match:
        normalized_zip = zip_match.group(1)
        statuses = provider_location_coverage()["zips"].get(normalized_zip)
        if statuses and coverage_in_la_county(statuses):
            return LocationValidationResponse(
                input=input_value,
                is_valid_zip=True,
                is_la_county=True,
                normalized_location=normalized_zip,
                reason="ZIP appears in the AccessFirst provider directory coverage.",
            )

        return LocationValidationResponse(
            input=input_value,
            is_valid_zip=True,
            is_la_county=False,
            normalized_location=normalized_zip,
            reason="This location is outside AccessFirst's Los Angeles County coverage.",
        )

    if ZIP_LIKE_RE.match(input_value):
        return LocationValidationResponse(
            input=input_value,
            is_valid_zip=False,
            is_la_county=False,
            normalized_location=input_value,
            reason="Enter a five-digit ZIP code, or search by city, neighborhood, or address.",
        )

    normalized_text = normalize_text(input_value)
    city_statuses = provider_location_coverage()["cities"].get(normalized_text)
    if city_statuses:
        if coverage_in_la_county(city_statuses):
            return LocationValidationResponse(
                input=input_value,
                is_valid_zip=None,
                is_la_county=True,
                normalized_location=input_value,
                reason="City appears in the AccessFirst provider directory coverage.",
            )

        return LocationValidationResponse(
            input=input_value,
            is_valid_zip=None,
            is_la_county=False,
            normalized_location=input_value,
            reason="This location is outside AccessFirst's Los Angeles County coverage.",
        )

    return LocationValidationResponse(
        input=input_value,
        is_valid_zip=None,
        is_la_county=None,
        normalized_location=input_value,
        reason="Non-ZIP locations are resolved during facility search.",
    )


def normalize_zip(value: Any) -> str | None:
    if value is None:
        return None
    match = ZIP_RE.match(str(value).strip())
    return match.group(1) if match else None


def normalize_text(value: Any) -> str:
    text = str(value or "").casefold().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def record_geography_status(record: dict[str, Any]) -> str:
    mapbox = record.get("mapbox")
    if isinstance(mapbox, dict):
        return str(mapbox.get("geography_status") or "").strip()
    return ""


def coverage_in_la_county(statuses: set[str]) -> bool:
    return any(status != "outside_la_county" for status in statuses)
