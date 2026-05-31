from __future__ import annotations

import re
from typing import Any

from .directions import build_interactive_map_url
from .models import FacilityResult, SearchRequest
from .ranking import haversine_miles, score_record


READY_STATUSES = {"include_default_map", "include_with_warning"}


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


def mapbox_object(record: dict[str, Any]) -> dict[str, Any]:
    mapbox = record.get("mapbox")
    return mapbox if isinstance(mapbox, dict) else {}


def record_is_searchable(record: dict[str, Any], request: SearchRequest) -> bool:
    mapbox = mapbox_object(record)
    inclusion_status = mapbox.get("map_inclusion_status")
    geography_status = mapbox.get("geography_status")

    if geography_status == "outside_la_county" and not request.include_outside_la_county:
        return False

    if inclusion_status == "include_default_map":
        return bool(mapbox.get("mapbox_ready"))

    if inclusion_status == "include_with_warning":
        return bool(mapbox.get("mapbox_ready")) and request.include_warning_results

    if inclusion_status == "manual_review":
        return request.include_manual_review

    if inclusion_status == "exclude_default_map":
        return (
            request.include_outside_la_county
            and geography_status == "outside_la_county"
            and mapbox.get("geocode_quality_status") != "failed"
        )

    return False


def insurance_note(record: dict[str, Any]) -> str | None:
    if str(record.get("insurance_acceptance_verified", "")).lower() == "yes":
        return None
    return "Insurance acceptance is not verified in the source data; call to confirm coverage."


def source_list(value: Any) -> list[str]:
    if isinstance(value, list):
        values = value
    elif isinstance(value, str):
        values = re.split(r";|\|", value)
    else:
        values = []

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = str(item or "").strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


def compact_list_summary(values: list[str], noun: str, limit: int = 4) -> str | None:
    if not values:
        return None

    shown = values[:limit]
    if len(values) == 1:
        return f"{noun}: {shown[0]}."
    if len(values) <= limit:
        return f"{noun}: {readable_join(shown)}."
    return f"{noun}: {readable_join(shown)}, and {len(values) - limit} more."


def readable_join(values: list[str]) -> str:
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return f"{', '.join(values[:-1])}, and {values[-1]}"


def parse_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(float(str(value).strip()))
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def practitioner_count(record: dict[str, Any]) -> int | None:
    explicit_count = parse_int(record.get("practitioner_count"))
    if explicit_count is not None:
        return explicit_count

    practitioners = record.get("practitioners")
    if isinstance(practitioners, list):
        return len(practitioners)

    names = source_list(record.get("practitioner_names"))
    return len(names) if names else None


def has_practitioner_names(record: dict[str, Any]) -> bool:
    practitioners = record.get("practitioners")
    if isinstance(practitioners, list):
        return any(
            str(item.get("practitioner_name", "")).strip()
            for item in practitioners
            if isinstance(item, dict)
        )
    return bool(source_list(record.get("practitioner_names")))


def has_npi_or_license_details(record: dict[str, Any]) -> bool:
    if source_list(record.get("npi_numbers")) or source_list(record.get("ca_licenses")):
        return True

    practitioners = record.get("practitioners")
    if not isinstance(practitioners, list):
        return False

    return any(
        (
            str(item.get("npi_number", "")).strip()
            or str(item.get("ca_license", "")).strip()
        )
        for item in practitioners
        if isinstance(item, dict)
    )


def practitioner_summary(record: dict[str, Any], count: int | None, disciplines: list[str]) -> str | None:
    if count is None and not disciplines and not has_practitioner_names(record):
        return None

    parts: list[str] = []
    if count is not None:
        label = "practitioner" if count == 1 else "practitioners"
        parts.append(f"{count} {label} listed")
    elif has_practitioner_names(record):
        parts.append("Practitioner names listed")

    if disciplines:
        shown = disciplines[:4]
        discipline_text = readable_join(shown)
        if len(disciplines) > 4:
            discipline_text = f"{discipline_text}, and {len(disciplines) - 4} more"
        parts.append(f"disciplines include {discipline_text}")

    if not parts:
        return None
    return f"{'; '.join(parts)}."


def facility_result(
    record: dict[str, Any],
    request: SearchRequest,
    distance_miles: float,
    score: float,
    origin_longitude: float,
    origin_latitude: float,
) -> FacilityResult:
    mapbox = mapbox_object(record)
    longitude = float(mapbox["longitude"])
    latitude = float(mapbox["latitude"])
    services = source_list(record.get("services"))
    methods_of_delivery = source_list(record.get("methods_of_delivery"))
    practice_focus_terms = source_list(record.get("practice_focus_terms"))
    disciplines = source_list(record.get("practitioner_disciplines"))
    count = practitioner_count(record)

    return FacilityResult(
        facility_uid=str(record.get("facility_uid", "")),
        facility_name=record.get("facility_name"),
        provider_display_name=record.get("provider_display_name"),
        service_area=record.get("service_area"),
        care_setting=record.get("care_setting"),
        address=record.get("address"),
        city=record.get("city"),
        zip_code=record.get("zip_code"),
        phone=record.get("phone"),
        website=record.get("website"),
        email=record.get("email"),
        hours=record.get("hours"),
        languages=source_list(record.get("languages")),
        services=services,
        service_summary=compact_list_summary(services, "Services"),
        methods_of_delivery=methods_of_delivery,
        delivery_summary=compact_list_summary(methods_of_delivery, "Delivery options"),
        ada_facility=record.get("ada_facility"),
        accepting_status=record.get("accepting_status"),
        insurance_acceptance_verified=record.get("insurance_acceptance_verified"),
        insurance_note=insurance_note(record),
        practice_focus_summary=compact_list_summary(practice_focus_terms, "Focus areas"),
        practitioner_summary=practitioner_summary(record, count, disciplines),
        practitioner_count=count,
        practitioner_disciplines=disciplines,
        has_practitioner_names=has_practitioner_names(record),
        has_npi_or_license_details=has_npi_or_license_details(record),
        longitude=longitude,
        latitude=latitude,
        distance_miles=round(distance_miles, 2),
        score=score,
        map_inclusion_status=mapbox.get("map_inclusion_status"),
        map_inclusion_reason=mapbox.get("map_inclusion_reason"),
        geocode_quality_status=mapbox.get("geocode_quality_status"),
        geography_status=mapbox.get("geography_status"),
        interactive_map_url=build_interactive_map_url(
            str(record.get("facility_uid", "")),
            longitude,
            latitude,
            origin_longitude,
            origin_latitude,
            request,
        ),
    )


def search_facilities(
    records: list[dict[str, Any]],
    request: SearchRequest,
    origin_longitude: float,
    origin_latitude: float,
) -> list[FacilityResult]:
    candidates: list[tuple[float, float, dict[str, Any]]] = []

    for record in records:
        if not record_is_searchable(record, request):
            continue

        mapbox = mapbox_object(record)
        longitude = parse_float(mapbox.get("longitude"))
        latitude = parse_float(mapbox.get("latitude"))
        if longitude is None or latitude is None:
            continue
        if not valid_coordinates(longitude, latitude):
            continue

        distance = haversine_miles(origin_longitude, origin_latitude, longitude, latitude)
        if distance > request.radius_miles:
            continue

        score = score_record(record, request, distance)
        candidates.append((score, distance, record))

    candidates.sort(key=lambda item: (-item[0], item[1], str(item[2].get("facility_name", ""))))
    return [
        facility_result(record, request, distance, score, origin_longitude, origin_latitude)
        for score, distance, record in candidates[: request.limit]
    ]
