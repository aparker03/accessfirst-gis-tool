#!/usr/bin/env python3
"""Geocode AccessFirst provider addresses with the Mapbox Geocoding API."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_PATH = PROJECT_ROOT / "data" / "processed" / "mapbox_geocoding_input_v0_2.csv"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "mapbox_geocoding_results.csv"
DEFAULT_ENV_PATH = PROJECT_ROOT / "backend" / ".env"
MAPBOX_FORWARD_GEOCODE_URL = "https://api.mapbox.com/search/geocode/v6/forward"

OUTPUT_FIELDS = [
    "facility_uid",
    "geocode_query",
    "longitude",
    "latitude",
    "place_name",
    "geocode_status",
    "confidence",
    "relevance",
    "match_code_json",
    "raw_response_json",
    "review_status",
    "review_reason",
    "expected_state",
    "returned_state",
    "expected_zip",
    "returned_zip",
    "expected_city",
    "returned_city",
    "expected_county",
    "returned_region_or_county",
    "geography_review_status",
]

REVIEW_FIELDS = [
    "review_status",
    "review_reason",
    "expected_state",
    "returned_state",
    "expected_zip",
    "returned_zip",
    "expected_city",
    "returned_city",
    "expected_county",
    "returned_region_or_county",
    "geography_review_status",
]

GOOD_CONFIDENCE_VALUES = {"exact", "high"}
ADDRESS_FEATURE_TYPES = {"address", "secondary_address"}
EXPECTED_COUNTY = "Los Angeles County"
NORMALIZED_EXPECTED_COUNTY = "los angeles county"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Geocode mapbox_geocoding_input_v0_2.csv and write resumable Mapbox results."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of new records to geocode in this run.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate selected rows even when they already exist in the output CSV.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help=f"Input CSV path. Defaults to {DEFAULT_INPUT_PATH}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Output CSV path. Defaults to {DEFAULT_OUTPUT_PATH}",
    )
    parser.add_argument(
        "--env",
        type=Path,
        default=DEFAULT_ENV_PATH,
        help=f".env path containing MAPBOX_SECRET_TOKEN. Defaults to {DEFAULT_ENV_PATH}",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="Request timeout in seconds. Defaults to 20.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.1,
        help="Seconds to sleep between requests. Defaults to 0.1.",
    )
    return parser.parse_args()


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        print(f"Warning: env file not found at {env_path}", file=sys.stderr)
        return

    with env_path.open("r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def read_existing_output_rows(output_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not output_path.exists() or output_path.stat().st_size == 0:
        return [], []

    with output_path.open("r", encoding="utf-8", newline="") as output_file:
        reader = csv.DictReader(output_file)
        if not reader.fieldnames:
            return [], []
        if "facility_uid" not in reader.fieldnames:
            raise ValueError(
                f"Existing output file {output_path} is missing a facility_uid column."
            )
        return reader.fieldnames, list(reader)


def read_input_rows(input_path: Path) -> list[dict[str, str]]:
    if not input_path.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_path}")

    with input_path.open("r", encoding="utf-8-sig", newline="") as input_file:
        reader = csv.DictReader(input_file)
        required_fields = {"facility_uid", "address_query"}
        missing_fields = required_fields - set(reader.fieldnames or [])
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise ValueError(f"Input CSV is missing required field(s): {missing}")
        return list(reader)


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def call_mapbox_geocoding(query: str, token: str, timeout: float) -> dict[str, Any]:
    params = {
        "q": query,
        "access_token": token,
        "limit": "1",
        "country": "us",
    }
    url = f"{MAPBOX_FORWARD_GEOCODE_URL}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "accessfirst-gis-tool/0.1"})

    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed_body: Any = json.loads(body)
        except json.JSONDecodeError:
            parsed_body = body
        raise RuntimeError(
            compact_json(
                {
                    "error": "http_error",
                    "status_code": exc.code,
                    "reason": exc.reason,
                    "body": parsed_body,
                }
            )
        ) from exc
    except URLError as exc:
        raise RuntimeError(
            compact_json({"error": "url_error", "reason": str(exc.reason)})
        ) from exc
    except TimeoutError as exc:
        raise RuntimeError(compact_json({"error": "timeout"})) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(compact_json({"error": "invalid_json_response"})) from exc


def first_non_empty(*values: Any) -> str:
    for value in values:
        if value is not None and value != "":
            return str(value)
    return ""


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def normalize_zip(value: str) -> str:
    match = re.search(r"\b(\d{5})", value or "")
    return match.group(1) if match else ""


def normalize_state(value: str) -> str:
    normalized = value.strip().upper()
    if normalized == "CALIFORNIA":
        return "CA"
    return normalized


def expected_state_from_query(query: str) -> str:
    match = re.search(r"\b([A-Z]{2})\s+\d{5}(?:-\d{4})?\b", query.upper())
    return match.group(1) if match else "CA"


def expected_values(input_row: dict[str, str] | None, query: str) -> dict[str, str]:
    row = input_row or {}
    return {
        "expected_state": normalize_state(
            first_non_empty(row.get("state"), expected_state_from_query(query))
        ),
        "expected_zip": normalize_zip(first_non_empty(row.get("zip_code"), query)),
        "expected_city": first_non_empty(row.get("city")),
        "expected_county": EXPECTED_COUNTY,
    }


def parse_json_object(value: str) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def first_feature_from_response(response_json: dict[str, Any]) -> dict[str, Any]:
    features = response_json.get("features") or []
    if not features:
        return {}
    feature = features[0]
    return feature if isinstance(feature, dict) else {}


def first_feature_from_result(result: dict[str, str]) -> dict[str, Any]:
    return first_feature_from_response(parse_json_object(result.get("raw_response_json", "")))


def context_item(context: dict[str, Any], key: str) -> dict[str, Any]:
    value = context.get(key) or {}
    return value if isinstance(value, dict) else {}


def returned_values(feature: dict[str, Any], place_name: str) -> dict[str, str]:
    properties = feature.get("properties") or {}
    context = properties.get("context") or {}
    if not isinstance(context, dict):
        context = {}

    region = context_item(context, "region")
    postcode = context_item(context, "postcode")
    place = context_item(context, "place")

    returned_state = normalize_state(
        first_non_empty(region.get("region_code"), region.get("name"))
    )
    returned_zip = normalize_zip(first_non_empty(postcode.get("name"), place_name))
    returned_city = first_non_empty(place.get("name"))

    return {
        "returned_state": returned_state,
        "returned_zip": returned_zip,
        "returned_city": returned_city,
    }


def match_code_from_result(result: dict[str, str], feature: dict[str, Any]) -> dict[str, Any]:
    match_code = parse_json_object(result.get("match_code_json", ""))
    if match_code:
        return match_code

    properties = feature.get("properties") or {}
    match_code = properties.get("match_code") or feature.get("match_code") or {}
    return match_code if isinstance(match_code, dict) else {}


def feature_type(feature: dict[str, Any]) -> str:
    properties = feature.get("properties") or {}
    return first_non_empty(properties.get("feature_type"), feature.get("place_type")).lower()


def returned_county(feature: dict[str, Any]) -> str:
    properties = feature.get("properties") or {}
    context = properties.get("context") or {}
    if not isinstance(context, dict):
        return ""
    district = context_item(context, "district")
    return first_non_empty(district.get("name"))


def returned_region_or_county(feature: dict[str, Any]) -> str:
    properties = feature.get("properties") or {}
    context = properties.get("context") or {}
    if not isinstance(context, dict):
        return ""

    district = context_item(context, "district")
    region = context_item(context, "region")
    return first_non_empty(
        district.get("name"),
        region.get("name"),
        region.get("region_code"),
    )


def geography_review_status(feature: dict[str, Any]) -> str:
    county = returned_county(feature)
    if county and normalize_text(county) != NORMALIZED_EXPECTED_COUNTY:
        return "outside_la_county_review"
    return "not_flagged"


def has_usable_coordinates(result: dict[str, str]) -> bool:
    try:
        longitude = float(result.get("longitude", ""))
        latitude = float(result.get("latitude", ""))
    except ValueError:
        return False
    return -180 <= longitude <= 180 and -90 <= latitude <= 90


def coordinates_in_expected_state_area(result: dict[str, str], expected_state: str) -> bool:
    if expected_state != "CA":
        return True
    try:
        longitude = float(result.get("longitude", ""))
        latitude = float(result.get("latitude", ""))
    except ValueError:
        return False
    return -125.0 <= longitude <= -113.0 and 32.0 <= latitude <= 42.5


def review_result(
    result: dict[str, str],
    input_row: dict[str, str] | None,
) -> dict[str, str]:
    reviewed = {field: result.get(field, "") for field in OUTPUT_FIELDS}
    query = first_non_empty(reviewed.get("geocode_query"), (input_row or {}).get("address_query"))
    expected = expected_values(input_row, query)
    feature = first_feature_from_result(reviewed)
    returned = returned_values(feature, reviewed.get("place_name", ""))
    match_code = match_code_from_result(reviewed, feature)
    confidence = first_non_empty(reviewed.get("confidence"), match_code.get("confidence"))
    result_feature_type = feature_type(feature)

    reviewed.update(expected)
    reviewed.update(returned)
    reviewed["returned_region_or_county"] = returned_region_or_county(feature)
    reviewed["geography_review_status"] = geography_review_status(feature)

    if reviewed.get("geocode_status") != "success" or not has_usable_coordinates(reviewed):
        reviewed["review_status"] = "failed"
        reviewed["review_reason"] = "no_usable_coordinates"
        return reviewed

    reasons: list[str] = []
    if not confidence:
        reasons.append("missing_confidence")
    elif confidence.lower() not in GOOD_CONFIDENCE_VALUES:
        reasons.append(f"{confidence.lower()}_confidence")

    if not reviewed.get("place_name"):
        reasons.append("missing_place_name")
    if result_feature_type and result_feature_type not in ADDRESS_FEATURE_TYPES:
        reasons.append(f"non_address_result:{result_feature_type}")
    if reviewed.get("place_name") and not re.search(r"\d", reviewed["place_name"]):
        reasons.append("vague_place_name")

    expected_state = reviewed["expected_state"]
    returned_state = reviewed["returned_state"]
    expected_zip = reviewed["expected_zip"]
    returned_zip = reviewed["returned_zip"]
    expected_city = reviewed["expected_city"]
    returned_city = reviewed["returned_city"]

    if expected_state and not returned_state:
        reasons.append("missing_returned_state")
    elif expected_state and returned_state and expected_state != returned_state:
        reasons.append("state_mismatch")

    if expected_zip and not returned_zip:
        reasons.append("missing_returned_zip")
    elif expected_zip and returned_zip and expected_zip != returned_zip:
        reasons.append("zip_mismatch")

    if expected_city and not returned_city:
        reasons.append("missing_returned_city")
    elif expected_city and returned_city:
        if normalize_text(expected_city) != normalize_text(returned_city):
            reasons.append("city_mismatch")

    if not coordinates_in_expected_state_area(reviewed, expected_state):
        reasons.append("coordinates_outside_expected_state_area")

    for part in ("address_number", "street"):
        part_status = first_non_empty(match_code.get(part)).lower()
        if part_status and part_status not in {"matched", "inferred", "not_applicable"}:
            reasons.append(f"{part}_not_matched")

    if reasons:
        reviewed["review_status"] = "needs_review"
        reviewed["review_reason"] = ";".join(dict.fromkeys(reasons))
    else:
        reviewed["review_status"] = "verified"
        reviewed["review_reason"] = ""

    return reviewed


def review_existing_rows(
    rows: list[dict[str, str]],
    input_rows_by_uid: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    reviewed_rows: list[dict[str, str]] = []
    for row in rows:
        input_row = input_rows_by_uid.get(row.get("facility_uid", ""))
        reviewed = review_result(row, input_row)
        for field in REVIEW_FIELDS:
            if row.get(field):
                reviewed[field] = row[field]
        reviewed_rows.append(reviewed)
    return reviewed_rows


def write_output_rows(output_path: Path, rows: list[dict[str, str]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(f"{output_path.name}.tmp")
    with temp_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temp_path, output_path)


def feature_to_result(
    facility_uid: str,
    query: str,
    response_json: dict[str, Any],
) -> dict[str, str]:
    features = response_json.get("features") or []
    if not features:
        return {
            "facility_uid": facility_uid,
            "geocode_query": query,
            "longitude": "",
            "latitude": "",
            "place_name": "",
            "geocode_status": "no_match",
            "confidence": "",
            "relevance": "",
            "match_code_json": "",
            "raw_response_json": compact_json(response_json),
        }

    feature = features[0]
    properties = feature.get("properties") or {}
    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates") or []
    longitude = coordinates[0] if len(coordinates) >= 2 else ""
    latitude = coordinates[1] if len(coordinates) >= 2 else ""
    match_code = properties.get("match_code") or feature.get("match_code") or {}

    return {
        "facility_uid": facility_uid,
        "geocode_query": query,
        "longitude": first_non_empty(longitude),
        "latitude": first_non_empty(latitude),
        "place_name": first_non_empty(
            properties.get("full_address"),
            properties.get("place_name"),
            feature.get("place_name"),
            properties.get("name_preferred"),
            properties.get("name"),
        ),
        "geocode_status": "success" if longitude != "" and latitude != "" else "no_coordinates",
        "confidence": first_non_empty(
            properties.get("confidence"),
            match_code.get("confidence") if isinstance(match_code, dict) else "",
        ),
        "relevance": first_non_empty(properties.get("relevance"), feature.get("relevance")),
        "match_code_json": compact_json(match_code) if match_code else "",
        "raw_response_json": compact_json(response_json),
    }


def failed_result(facility_uid: str, query: str, error_json: str) -> dict[str, str]:
    return {
        "facility_uid": facility_uid,
        "geocode_query": query,
        "longitude": "",
        "latitude": "",
        "place_name": "",
        "geocode_status": "failed",
        "confidence": "",
        "relevance": "",
        "match_code_json": "",
        "raw_response_json": error_json,
    }


def exception_to_error_json(exc: Exception) -> str:
    message = str(exc)
    try:
        parsed_message = json.loads(message)
    except json.JSONDecodeError:
        parsed_message = None

    if isinstance(parsed_message, dict):
        return compact_json(parsed_message)

    return compact_json(
        {
            "error": exc.__class__.__name__,
            "message": message,
        }
    )


def output_needs_header(output_path: Path) -> bool:
    return not output_path.exists() or output_path.stat().st_size == 0


def main() -> int:
    args = parse_args()
    if args.limit is not None and args.limit < 0:
        print("Error: --limit must be 0 or greater.", file=sys.stderr)
        return 2

    load_env_file(args.env)
    token = os.environ.get("MAPBOX_SECRET_TOKEN")
    if not token:
        print(
            f"Error: MAPBOX_SECRET_TOKEN not found in environment or {args.env}.",
            file=sys.stderr,
        )
        return 2

    input_rows = read_input_rows(args.input)
    input_rows_by_uid = {
        row["facility_uid"]: row
        for row in input_rows
        if row.get("facility_uid")
    }
    existing_fieldnames, existing_rows = read_existing_output_rows(args.output)
    existing_rows = review_existing_rows(existing_rows, input_rows_by_uid)

    missing_review_fields = any(field not in existing_fieldnames for field in REVIEW_FIELDS)
    missing_output_fields = any(field not in existing_fieldnames for field in OUTPUT_FIELDS)
    needs_review_backfill = any(
        row.get("facility_uid") and not row.get("review_status")
        for row in existing_rows
    )
    if existing_rows and (missing_review_fields or missing_output_fields or needs_review_backfill):
        print("Updating existing results CSV schema with review columns.")
        print("Existing geocoding values are preserved; rows are not re-queried.")
        write_output_rows(args.output, existing_rows)

    completed_uids = {
        row["facility_uid"]
        for row in existing_rows
        if row.get("facility_uid")
    }

    if args.force:
        rows_to_geocode = input_rows
    else:
        rows_to_geocode = [
            row for row in input_rows if row.get("facility_uid") not in completed_uids
        ]
    if args.limit is not None:
        rows_to_geocode = rows_to_geocode[: args.limit]

    if args.force and existing_rows:
        forced_uids = {
            row["facility_uid"]
            for row in rows_to_geocode
            if row.get("facility_uid")
        }
        preserved_rows = [
            row for row in existing_rows if row.get("facility_uid") not in forced_uids
        ]
        print(f"--force enabled: regenerating {len(forced_uids)} existing/new row(s).")
        print(f"Preserving {len(preserved_rows)} existing result row(s) outside this run.")
        write_output_rows(args.output, preserved_rows)
        completed_uids = {
            row["facility_uid"]
            for row in preserved_rows
            if row.get("facility_uid")
        }

    print(f"Input rows: {len(input_rows)}")
    print(f"Already in results: {len(completed_uids)}")
    print(f"Queued for this run: {len(rows_to_geocode)}")
    print(f"Writing results to: {args.output}")

    if not rows_to_geocode:
        print("Nothing to geocode. Existing results are up to date for this run.")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_header = output_needs_header(args.output)
    successes = 0
    verified = 0
    needs_review = 0
    no_matches = 0
    failures = 0

    with args.output.open("a", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        if write_header:
            writer.writeheader()

        total = len(rows_to_geocode)
        for index, row in enumerate(rows_to_geocode, start=1):
            facility_uid = row["facility_uid"]
            query = row["address_query"].strip()
            print(f"[{index}/{total}] Geocoding {facility_uid}: {query}")

            if not query:
                result = failed_result(
                    facility_uid,
                    query,
                    compact_json({"error": "missing_address_query"}),
                )
                result = review_result(result, row)
                writer.writerow(result)
                output_file.flush()
                failures += 1
                print(f"[{index}/{total}] Failed {facility_uid}: missing address_query")
                continue

            try:
                response_json = call_mapbox_geocoding(query, token, args.timeout)
                result = feature_to_result(facility_uid, query, response_json)
            except Exception as exc:
                result = failed_result(
                    facility_uid,
                    query,
                    exception_to_error_json(exc),
                )
            result = review_result(result, row)

            writer.writerow(result)
            output_file.flush()

            status = result["geocode_status"]
            if status == "success":
                successes += 1
                if result["review_status"] == "verified":
                    verified += 1
                else:
                    needs_review += 1
                print(
                    f"[{index}/{total}] Success {facility_uid}: "
                    f"{result['latitude']}, {result['longitude']} "
                    f"({result['review_status']})"
                )
                if result["review_reason"]:
                    print(f"[{index}/{total}] Review reason: {result['review_reason']}")
            elif status == "no_match":
                no_matches += 1
                print(f"[{index}/{total}] No match {facility_uid}")
            else:
                failures += 1
                print(f"[{index}/{total}] {status} {facility_uid}")

            if args.sleep > 0 and index < total:
                time.sleep(args.sleep)

    print("Done.")
    print(f"Successful geocodes: {successes}")
    print(f"Verified for map: {verified}")
    print(f"Needs review: {needs_review}")
    print(f"No matches: {no_matches}")
    print(f"Failed or incomplete: {failures}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
