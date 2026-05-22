from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


MAPBOX_FORWARD_GEOCODE_URL = "https://api.mapbox.com/search/geocode/v6/forward"


class LocationGeocodingError(RuntimeError):
    pass


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        if value is not None and value != "":
            return str(value)
    return None


def geocode_location(location: str, timeout: float = 15.0) -> dict[str, Any]:
    token = os.getenv("MAPBOX_SECRET_TOKEN")
    if not token:
        raise LocationGeocodingError("MAPBOX_SECRET_TOKEN is not configured.")

    params = {
        "q": location,
        "access_token": token,
        "limit": "1",
        "country": "us",
    }
    request = Request(
        f"{MAPBOX_FORWARD_GEOCODE_URL}?{urlencode(params)}",
        headers={"User-Agent": "accessfirst-gis-tool/0.1"},
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            response_json = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise LocationGeocodingError(f"Mapbox geocoding failed with HTTP {exc.code}.") from exc
    except URLError as exc:
        raise LocationGeocodingError(f"Mapbox geocoding failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise LocationGeocodingError("Mapbox geocoding timed out.") from exc
    except json.JSONDecodeError as exc:
        raise LocationGeocodingError("Mapbox returned an invalid JSON response.") from exc

    features = response_json.get("features") or []
    if not features:
        raise LocationGeocodingError("Could not geocode the requested location.")

    feature = features[0]
    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates") or []
    if len(coordinates) < 2:
        raise LocationGeocodingError("Mapbox result did not include coordinates.")

    try:
        longitude = float(coordinates[0])
        latitude = float(coordinates[1])
    except (TypeError, ValueError) as exc:
        raise LocationGeocodingError("Mapbox result coordinates were not usable.") from exc

    properties = feature.get("properties") or {}
    return {
        "longitude": longitude,
        "latitude": latitude,
        "place_name": _first_non_empty(
            properties.get("full_address"),
            properties.get("place_name"),
            feature.get("place_name"),
            properties.get("name_preferred"),
            properties.get("name"),
        ),
    }
