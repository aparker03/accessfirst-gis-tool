#!/usr/bin/env python3
"""Classify cleaned Mapbox geocoding results for map inclusion."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_PATH = PROJECT_ROOT / "data" / "processed" / "mapbox_geocoding_results_clean.csv"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "mapbox_geocoding_results_classified.csv"
DEFAULT_SUMMARY_PATH = PROJECT_ROOT / "data" / "audit" / "geocoding_classification_summary.json"

REQUIRED_FIELDS = [
    "geocode_status",
    "longitude",
    "latitude",
    "place_name",
    "confidence",
    "review_status",
    "review_reason",
    "geography_review_status",
    "expected_city",
    "returned_city",
    "expected_state",
    "returned_state",
    "expected_zip",
    "returned_zip",
]

NEW_FIELDS = [
    "geocode_quality_status",
    "geography_status",
    "map_inclusion_status",
    "map_inclusion_reason",
]

GOOD_CONFIDENCE_VALUES = {"exact", "high"}
CITY_OR_ZIP_MISMATCH_REASONS = {"zip_mismatch", "city_mismatch"}
ADDRESS_QUALITY_REASON_MARKERS = {
    "address_number_not_matched",
    "street_not_matched",
    "vague_place_name",
    "missing_confidence",
    "low_confidence",
    "medium_confidence",
    "missing_place_name",
    "missing_returned_state",
    "state_mismatch",
    "missing_returned_zip",
    "missing_returned_city",
    "coordinates_outside_expected_state_area",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify cleaned geocoding results for default map inclusion."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help=f"Cleaned geocoding results CSV. Defaults to {DEFAULT_INPUT_PATH}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Classified output CSV. Defaults to {DEFAULT_OUTPUT_PATH}",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=DEFAULT_SUMMARY_PATH,
        help=f"Summary JSON output. Defaults to {DEFAULT_SUMMARY_PATH}",
    )
    return parser.parse_args()


def read_rows(input_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not input_path.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_path}")

    with input_path.open("r", encoding="utf-8-sig", newline="") as input_file:
        reader = csv.DictReader(input_file)
        fieldnames = reader.fieldnames or []
        missing_fields = [field for field in REQUIRED_FIELDS if field not in fieldnames]
        if missing_fields:
            missing = ", ".join(missing_fields)
            raise ValueError(f"Input CSV is missing required field(s): {missing}")
        return fieldnames, list(reader)


def write_rows(output_path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_fields = [field for field in fieldnames if field not in NEW_FIELDS] + NEW_FIELDS

    with output_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=output_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_summary(summary_path: Path, summary: dict[str, Any]) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as summary_file:
        json.dump(summary, summary_file, indent=2, sort_keys=True)
        summary_file.write("\n")


def parse_float(value: str) -> float | None:
    try:
        return float((value or "").strip())
    except ValueError:
        return None


def has_usable_coordinates(row: dict[str, str]) -> bool:
    longitude = parse_float(row.get("longitude", ""))
    latitude = parse_float(row.get("latitude", ""))
    if longitude is None or latitude is None:
        return False
    return -180 <= longitude <= 180 and -90 <= latitude <= 90


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def normalize_status(value: str) -> str:
    return (value or "").strip().lower()


def reason_tokens(review_reason: str) -> set[str]:
    return {
        token.strip().lower()
        for token in (review_reason or "").split(";")
        if token.strip()
    }


def parse_match_code(row: dict[str, str]) -> dict[str, Any]:
    raw_match_code = row.get("match_code_json", "")
    if not raw_match_code:
        return {}
    try:
        parsed = json.loads(raw_match_code)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def confidence_value(row: dict[str, str], match_code: dict[str, Any]) -> str:
    return (row.get("confidence") or str(match_code.get("confidence") or "")).strip().lower()


def is_address_level_match(row: dict[str, str], match_code: dict[str, Any]) -> bool:
    confidence = confidence_value(row, match_code)
    if confidence not in GOOD_CONFIDENCE_VALUES:
        return False

    place_name = row.get("place_name", "")
    if not place_name or not re.search(r"\d", place_name):
        return False

    address_number = str(match_code.get("address_number") or "").lower()
    street = str(match_code.get("street") or "").lower()
    bad_statuses = {"unmatched", "not_matched", "plausible"}
    if address_number in bad_statuses or street in bad_statuses:
        return False

    return True


def has_address_quality_concern(row: dict[str, str], reasons: set[str]) -> bool:
    confidence = (row.get("confidence") or "").strip().lower()
    if not confidence or confidence not in GOOD_CONFIDENCE_VALUES:
        return True

    if any(reason in ADDRESS_QUALITY_REASON_MARKERS for reason in reasons):
        return True

    if any(reason.startswith("non_address_result:") for reason in reasons):
        return True

    return bool(reasons - CITY_OR_ZIP_MISMATCH_REASONS)


def classify_geocode_quality(row: dict[str, str]) -> str:
    geocode_status = normalize_status(row.get("geocode_status", ""))
    if geocode_status == "failed" or not has_usable_coordinates(row):
        return "failed"

    match_code = parse_match_code(row)
    review_status = normalize_status(row.get("review_status", ""))
    reasons = reason_tokens(row.get("review_reason", ""))

    if review_status == "verified" and geocode_status == "success":
        return "verified_address"

    if (
        geocode_status == "success"
        and reasons
        and reasons <= CITY_OR_ZIP_MISMATCH_REASONS
        and is_address_level_match(row, match_code)
    ):
        return "verified_city_or_zip_mismatch"

    if has_address_quality_concern(row, reasons):
        return "needs_review_address"

    if geocode_status == "success" and is_address_level_match(row, match_code):
        return "verified_address"

    return "needs_review_address"


def classify_geography(row: dict[str, str]) -> str:
    geography_review_status = normalize_status(row.get("geography_review_status", ""))
    if geography_review_status == "outside_la_county_review":
        return "outside_la_county"
    if geography_review_status == "not_flagged":
        return "in_la_county"
    return "geography_uncertain"


def classify_map_inclusion(
    geocode_quality_status: str,
    geography_status: str,
) -> tuple[str, str]:
    if geography_status == "outside_la_county":
        if geocode_quality_status == "verified_address":
            return (
                "exclude_default_map",
                "correctly geocoded but outside Los Angeles County",
            )
        return "exclude_default_map", "outside Los Angeles County"

    if geocode_quality_status == "failed":
        return "exclude_default_map", "failed geocode or missing usable coordinates"

    if geography_status == "geography_uncertain":
        return "manual_review", "geography could not be classified"

    if geocode_quality_status == "verified_address":
        return "include_default_map", "verified address in Los Angeles County"

    if geocode_quality_status == "verified_city_or_zip_mismatch":
        return (
            "include_with_warning",
            "address-level match with city or ZIP mismatch warning",
        )

    return "manual_review", "address match quality needs review"


def classify_row(row: dict[str, str]) -> dict[str, str]:
    classified = dict(row)
    geocode_quality_status = classify_geocode_quality(row)
    geography_status = classify_geography(row)
    map_inclusion_status, map_inclusion_reason = classify_map_inclusion(
        geocode_quality_status,
        geography_status,
    )

    classified["geocode_quality_status"] = geocode_quality_status
    classified["geography_status"] = geography_status
    classified["map_inclusion_status"] = map_inclusion_status
    classified["map_inclusion_reason"] = map_inclusion_reason
    return classified


def counter_to_dict(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def build_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    geocode_quality_counts = Counter(row["geocode_quality_status"] for row in rows)
    geography_counts = Counter(row["geography_status"] for row in rows)
    inclusion_counts = Counter(row["map_inclusion_status"] for row in rows)

    return {
        "total_records": len(rows),
        "geocode_quality_status": counter_to_dict(geocode_quality_counts),
        "geography_status": counter_to_dict(geography_counts),
        "map_inclusion_status": counter_to_dict(inclusion_counts),
        "outside_la_county_records": geography_counts["outside_la_county"],
        "include_default_map_records": inclusion_counts["include_default_map"],
        "include_with_warning_records": inclusion_counts["include_with_warning"],
        "manual_review_records": inclusion_counts["manual_review"],
        "excluded_records": inclusion_counts["exclude_default_map"],
    }


def main() -> int:
    args = parse_args()
    fieldnames, rows = read_rows(args.input)
    classified_rows = [classify_row(row) for row in rows]
    summary = build_summary(classified_rows)

    write_rows(args.output, fieldnames, classified_rows)
    write_summary(args.summary, summary)

    print(f"Read {len(rows)} record(s) from {args.input}")
    print(f"Wrote classified results to {args.output}")
    print(f"Wrote classification summary to {args.summary}")
    print(f"include_default_map: {summary['include_default_map_records']}")
    print(f"include_with_warning: {summary['include_with_warning_records']}")
    print(f"manual_review: {summary['manual_review_records']}")
    print(f"exclude_default_map: {summary['excluded_records']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
