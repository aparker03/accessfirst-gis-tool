from __future__ import annotations

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


def facility_result(
    record: dict[str, Any],
    distance_miles: float,
    score: float,
    origin_longitude: float,
    origin_latitude: float,
) -> FacilityResult:
    mapbox = mapbox_object(record)
    longitude = float(mapbox["longitude"])
    latitude = float(mapbox["latitude"])

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
        languages=record.get("languages") if isinstance(record.get("languages"), list) else [],
        services=record.get("services") if isinstance(record.get("services"), list) else [],
        methods_of_delivery=(
            record.get("methods_of_delivery")
            if isinstance(record.get("methods_of_delivery"), list)
            else []
        ),
        ada_facility=record.get("ada_facility"),
        accepting_status=record.get("accepting_status"),
        insurance_acceptance_verified=record.get("insurance_acceptance_verified"),
        insurance_note=insurance_note(record),
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
        facility_result(record, distance, score, origin_longitude, origin_latitude)
        for score, distance, record in candidates[: request.limit]
    ]
