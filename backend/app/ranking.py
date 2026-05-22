from __future__ import annotations

import math
import re
from typing import Any

from .models import SearchRequest


EARTH_RADIUS_MILES = 3958.7613


def normalize_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def normalized_list(values: Any) -> list[str]:
    if isinstance(values, list):
        return [normalize_text(value) for value in values if normalize_text(value)]
    if values:
        return [normalize_text(values)]
    return []


def haversine_miles(
    origin_longitude: float,
    origin_latitude: float,
    destination_longitude: float,
    destination_latitude: float,
) -> float:
    origin_lat_rad = math.radians(origin_latitude)
    destination_lat_rad = math.radians(destination_latitude)
    delta_lat = math.radians(destination_latitude - origin_latitude)
    delta_lng = math.radians(destination_longitude - origin_longitude)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(origin_lat_rad)
        * math.cos(destination_lat_rad)
        * math.sin(delta_lng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_MILES * c


def text_contains(haystacks: list[str], needle: str) -> bool:
    if not needle:
        return False
    return any(needle in haystack for haystack in haystacks)


def telehealth_match(record: dict[str, Any]) -> bool:
    delivery_terms = normalized_list(record.get("methods_of_delivery"))
    access_mode = normalize_text(record.get("access_mode"))
    haystacks = delivery_terms + [access_mode]
    return any(
        term in haystack
        for haystack in haystacks
        for term in ("telehealth", "telephone", "phone", "video", "virtual")
    )


def accessibility_match(record: dict[str, Any], accessibility_need: str) -> bool:
    if not accessibility_need:
        return False
    need = normalize_text(accessibility_need)
    ada_facility = normalize_text(record.get("ada_facility"))
    if any(term in need for term in ("ada", "wheelchair", "accessible", "mobility")):
        return ada_facility in {"yes", "y", "true"}
    return need and need in ada_facility


def score_record(record: dict[str, Any], request: SearchRequest, distance_miles: float) -> float:
    score = 0.0
    search_terms: list[str] = []

    service_type = normalize_text(request.service_type)
    if service_type:
        search_terms.extend(
            normalized_list(record.get("services"))
            + normalized_list(record.get("practice_focus_terms"))
            + normalized_list(record.get("care_setting"))
            + normalized_list(record.get("operation"))
            + normalized_list(record.get("programs_info"))
        )
        if text_contains(search_terms, service_type):
            score += 35.0
        elif any(token and text_contains(search_terms, token) for token in service_type.split()):
            score += 15.0

    language = normalize_text(request.language)
    if language:
        if language in normalized_list(record.get("languages")):
            score += 20.0
        else:
            score -= 5.0

    if request.telehealth is True:
        score += 15.0 if telehealth_match(record) else -5.0
    elif request.telehealth is False:
        if not telehealth_match(record):
            score += 3.0

    accessibility_need = normalize_text(request.accessibility_need)
    if accessibility_need:
        score += 15.0 if accessibility_match(record, accessibility_need) else -5.0

    adult_status = normalize_text(record.get("adult_status"))
    if adult_status in {"adult listed", "adult and youth listed", "adult_listed", "adult_and_youth_listed"}:
        score += 3.0

    mapbox = record.get("mapbox") if isinstance(record.get("mapbox"), dict) else {}
    if mapbox.get("map_inclusion_status") == "include_default_map":
        score += 10.0
    elif mapbox.get("map_inclusion_status") == "include_with_warning":
        score += 5.0

    radius = max(float(request.radius_miles), 0.1)
    distance_score = max(0.0, 25.0 * (1.0 - min(distance_miles, radius) / radius))
    score += distance_score

    return round(score, 4)
