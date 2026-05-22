#!/usr/bin/env python3
"""Merge classified geocoding results into AccessFirst provider records."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROVIDER_JSONL_PATH = (
    PROJECT_ROOT / "data" / "processed" / "provider_records_updated_v0_2.jsonl"
)
DEFAULT_GEOCODE_CSV_PATH = (
    PROJECT_ROOT / "data" / "processed" / "mapbox_geocoding_results_classified.csv"
)
DEFAULT_OUTPUT_JSONL_PATH = (
    PROJECT_ROOT / "data" / "processed" / "provider_records_geocoded.jsonl"
)
DEFAULT_OUTPUT_JSON_PATH = (
    PROJECT_ROOT / "data" / "processed" / "provider_records_geocoded.json"
)
DEFAULT_OUTPUT_GEOJSON_PATH = (
    PROJECT_ROOT / "data" / "processed" / "provider_records_geocoded.geojson"
)
DEFAULT_SUMMARY_PATH = PROJECT_ROOT / "data" / "audit" / "geocoding_merge_summary.json"

GEOCODE_FIELDS = [
    "facility_uid",
    "longitude",
    "latitude",
    "place_name",
    "geocode_status",
    "confidence",
    "review_status",
    "review_reason",
    "geography_review_status",
    "geocode_quality_status",
    "geography_status",
    "map_inclusion_status",
    "map_inclusion_reason",
    "expected_state",
    "returned_state",
    "expected_zip",
    "returned_zip",
    "expected_city",
    "returned_city",
    "expected_county",
    "returned_region_or_county",
]

MAPBOX_MERGE_FIELDS = [
    "longitude",
    "latitude",
    "place_name",
    "geocode_status",
    "confidence",
    "review_status",
    "review_reason",
    "geography_review_status",
    "geocode_quality_status",
    "geography_status",
    "map_inclusion_status",
    "map_inclusion_reason",
    "expected_state",
    "returned_state",
    "expected_zip",
    "returned_zip",
    "expected_city",
    "returned_city",
    "expected_county",
    "returned_region_or_county",
]

MAPBOX_READY_STATUSES = {"include_default_map", "include_with_warning"}
MAPBOX_NOT_READY_STATUSES = {"manual_review", "exclude_default_map"}

GEOJSON_PROPERTY_FIELDS = [
    "facility_uid",
    "facility_name",
    "provider_display_name",
    "service_area",
    "care_setting",
    "address",
    "city",
    "zip_code",
    "phone",
    "hours",
    "languages",
    "services",
    "methods_of_delivery",
    "ada_facility",
]

GEOJSON_MAPBOX_PROPERTY_FIELDS = [
    "map_inclusion_status",
    "map_inclusion_reason",
    "geocode_quality_status",
    "geography_status",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge classified Mapbox geocodes into provider records."
    )
    parser.add_argument(
        "--providers",
        type=Path,
        default=DEFAULT_PROVIDER_JSONL_PATH,
        help=f"Provider JSONL input. Defaults to {DEFAULT_PROVIDER_JSONL_PATH}",
    )
    parser.add_argument(
        "--geocodes",
        type=Path,
        default=DEFAULT_GEOCODE_CSV_PATH,
        help=f"Classified geocode CSV input. Defaults to {DEFAULT_GEOCODE_CSV_PATH}",
    )
    parser.add_argument(
        "--output-jsonl",
        type=Path,
        default=DEFAULT_OUTPUT_JSONL_PATH,
        help=f"Merged provider JSONL output. Defaults to {DEFAULT_OUTPUT_JSONL_PATH}",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=DEFAULT_OUTPUT_JSON_PATH,
        help=f"Merged provider JSON output. Defaults to {DEFAULT_OUTPUT_JSON_PATH}",
    )
    parser.add_argument(
        "--output-geojson",
        type=Path,
        default=DEFAULT_OUTPUT_GEOJSON_PATH,
        help=f"GeoJSON output. Defaults to {DEFAULT_OUTPUT_GEOJSON_PATH}",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=DEFAULT_SUMMARY_PATH,
        help=f"Merge summary JSON output. Defaults to {DEFAULT_SUMMARY_PATH}",
    )
    return parser.parse_args()


def read_provider_records(jsonl_path: Path) -> list[dict[str, Any]]:
    if not jsonl_path.exists():
        raise FileNotFoundError(f"Provider JSONL not found: {jsonl_path}")

    records: list[dict[str, Any]] = []
    with jsonl_path.open("r", encoding="utf-8") as jsonl_file:
        for line_number, line in enumerate(jsonl_file, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON in {jsonl_path} at line {line_number}: {exc}"
                ) from exc
            if not isinstance(record, dict):
                raise ValueError(
                    f"Expected object in {jsonl_path} at line {line_number}."
                )
            records.append(record)
    return records


def read_geocode_rows(csv_path: Path) -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    if not csv_path.exists():
        raise FileNotFoundError(f"Classified geocode CSV not found: {csv_path}")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        fieldnames = reader.fieldnames or []
        missing_fields = [field for field in GEOCODE_FIELDS if field not in fieldnames]
        if missing_fields:
            missing = ", ".join(missing_fields)
            raise ValueError(f"Geocode CSV is missing required field(s): {missing}")

        rows = list(reader)

    rows_by_uid: dict[str, dict[str, str]] = {}
    duplicate_uids: list[str] = []
    for row in rows:
        facility_uid = row.get("facility_uid", "")
        if not facility_uid:
            continue
        if facility_uid in rows_by_uid:
            duplicate_uids.append(facility_uid)
        rows_by_uid[facility_uid] = row

    if duplicate_uids:
        sample = ", ".join(duplicate_uids[:5])
        raise ValueError(f"Duplicate facility_uid values in geocode CSV: {sample}")

    return rows, rows_by_uid


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def valid_coordinates(longitude: Any, latitude: Any) -> bool:
    longitude_value = parse_float(longitude)
    latitude_value = parse_float(latitude)
    if longitude_value is None or latitude_value is None:
        return False
    return -180 <= longitude_value <= 180 and -90 <= latitude_value <= 90


def normalized_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text != "" else None


def merge_mapbox(record: dict[str, Any], geocode_row: dict[str, str] | None) -> dict[str, Any]:
    existing_mapbox = record.get("mapbox")
    mapbox = dict(existing_mapbox) if isinstance(existing_mapbox, dict) else {}

    if geocode_row is None:
        mapbox["mapbox_ready"] = False
        return mapbox

    longitude = parse_float(geocode_row.get("longitude"))
    latitude = parse_float(geocode_row.get("latitude"))

    for field in MAPBOX_MERGE_FIELDS:
        if field == "longitude":
            mapbox[field] = longitude
        elif field == "latitude":
            mapbox[field] = latitude
        else:
            mapbox[field] = normalized_optional_string(geocode_row.get(field))

    map_inclusion_status = geocode_row.get("map_inclusion_status", "")
    has_coordinates = valid_coordinates(longitude, latitude)
    if map_inclusion_status in MAPBOX_READY_STATUSES and has_coordinates:
        mapbox["mapbox_ready"] = True
    elif map_inclusion_status in MAPBOX_NOT_READY_STATUSES:
        mapbox["mapbox_ready"] = False
    else:
        mapbox["mapbox_ready"] = False

    return mapbox


def merge_records(
    provider_records: list[dict[str, Any]],
    geocode_rows_by_uid: dict[str, dict[str, str]],
) -> tuple[list[dict[str, Any]], int]:
    merged_records: list[dict[str, Any]] = []
    matched_geocode_rows = 0

    for record in provider_records:
        merged_record = dict(record)
        facility_uid = str(record.get("facility_uid", ""))
        geocode_row = geocode_rows_by_uid.get(facility_uid)
        if geocode_row is not None:
            matched_geocode_rows += 1

        merged_record["mapbox"] = merge_mapbox(record, geocode_row)
        merged_records.append(merged_record)

    return merged_records, matched_geocode_rows


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as jsonl_file:
        for record in records:
            jsonl_file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            jsonl_file.write("\n")


def write_json(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as json_file:
        json.dump(records, json_file, ensure_ascii=False, indent=2)
        json_file.write("\n")


def geojson_properties(record: dict[str, Any]) -> dict[str, Any]:
    properties = {
        field: record.get(field)
        for field in GEOJSON_PROPERTY_FIELDS
    }
    mapbox = record.get("mapbox") if isinstance(record.get("mapbox"), dict) else {}
    for field in GEOJSON_MAPBOX_PROPERTY_FIELDS:
        properties[field] = mapbox.get(field)
    return properties


def build_geojson(records: list[dict[str, Any]]) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    for record in records:
        mapbox = record.get("mapbox")
        if not isinstance(mapbox, dict) or not mapbox.get("mapbox_ready"):
            continue

        longitude = parse_float(mapbox.get("longitude"))
        latitude = parse_float(mapbox.get("latitude"))
        if longitude is None or latitude is None:
            continue
        if not valid_coordinates(longitude, latitude):
            continue

        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [longitude, latitude],
                },
                "properties": geojson_properties(record),
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
    }


def write_geojson(path: Path, geojson: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as geojson_file:
        json.dump(geojson, geojson_file, ensure_ascii=False, indent=2)
        geojson_file.write("\n")


def write_summary(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as summary_file:
        json.dump(summary, summary_file, indent=2, sort_keys=True)
        summary_file.write("\n")


def build_summary(
    provider_records: list[dict[str, Any]],
    geocode_rows: list[dict[str, str]],
    matched_geocode_rows: int,
    geojson_feature_count: int,
) -> dict[str, Any]:
    inclusion_counts = Counter(
        (
            record.get("mapbox", {}).get("map_inclusion_status")
            if isinstance(record.get("mapbox"), dict)
            else None
        )
        for record in provider_records
    )
    failed_geocodes = sum(
        1
        for record in provider_records
        if isinstance(record.get("mapbox"), dict)
        and record["mapbox"].get("geocode_quality_status") == "failed"
    )
    outside_la_county = sum(
        1
        for record in provider_records
        if isinstance(record.get("mapbox"), dict)
        and record["mapbox"].get("geography_status") == "outside_la_county"
    )
    mapbox_ready_records = sum(
        1
        for record in provider_records
        if isinstance(record.get("mapbox"), dict)
        and record["mapbox"].get("mapbox_ready") is True
    )

    return {
        "total_provider_records": len(provider_records),
        "geocode_rows": len(geocode_rows),
        "matched_geocode_rows": matched_geocode_rows,
        "missing_geocode_rows": len(provider_records) - matched_geocode_rows,
        "mapbox_ready_records": mapbox_ready_records,
        "include_default_map": inclusion_counts["include_default_map"],
        "include_with_warning": inclusion_counts["include_with_warning"],
        "manual_review": inclusion_counts["manual_review"],
        "exclude_default_map": inclusion_counts["exclude_default_map"],
        "geojson_feature_count": geojson_feature_count,
        "failed_geocodes": failed_geocodes,
        "outside_la_county": outside_la_county,
    }


def main() -> int:
    args = parse_args()
    provider_records = read_provider_records(args.providers)
    geocode_rows, geocode_rows_by_uid = read_geocode_rows(args.geocodes)

    merged_records, matched_geocode_rows = merge_records(
        provider_records,
        geocode_rows_by_uid,
    )
    geojson = build_geojson(merged_records)
    summary = build_summary(
        merged_records,
        geocode_rows,
        matched_geocode_rows,
        len(geojson["features"]),
    )

    write_jsonl(args.output_jsonl, merged_records)
    write_json(args.output_json, merged_records)
    write_geojson(args.output_geojson, geojson)
    write_summary(args.summary, summary)

    print(f"Read {len(provider_records)} provider record(s) from {args.providers}")
    print(f"Read {len(geocode_rows)} geocode row(s) from {args.geocodes}")
    print(f"Matched geocode rows: {matched_geocode_rows}")
    print(f"Missing geocode rows: {summary['missing_geocode_rows']}")
    print(f"Mapbox-ready records: {summary['mapbox_ready_records']}")
    print(f"GeoJSON features: {summary['geojson_feature_count']}")
    print(f"Wrote {args.output_jsonl}")
    print(f"Wrote {args.output_json}")
    print(f"Wrote {args.output_geojson}")
    print(f"Wrote {args.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
