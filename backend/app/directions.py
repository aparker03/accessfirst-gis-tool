from __future__ import annotations

import os
from urllib.parse import urlencode


DEFAULT_FRONTEND_BASE_URL = "http://localhost:5173"


def frontend_base_url() -> str:
    return os.getenv("MAP_FRONTEND_BASE_URL", DEFAULT_FRONTEND_BASE_URL).rstrip("/")


def build_interactive_map_url(
    facility_uid: str,
    provider_longitude: float,
    provider_latitude: float,
    origin_longitude: float,
    origin_latitude: float,
) -> str:
    params = urlencode(
        {
            "facility_uid": facility_uid,
            "provider_lng": f"{provider_longitude:.6f}",
            "provider_lat": f"{provider_latitude:.6f}",
            "origin_lng": f"{origin_longitude:.6f}",
            "origin_lat": f"{origin_latitude:.6f}",
        }
    )
    return f"{frontend_base_url()}/?{params}"
