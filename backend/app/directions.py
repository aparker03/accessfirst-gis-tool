from __future__ import annotations

import os
from typing import Any
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
    search_context: Any | None = None,
) -> str:
    params = {}
    if search_context is not None:
        add_optional_param(params, "location", getattr(search_context, "location", None))
        add_optional_param(params, "service_type", getattr(search_context, "service_type", None))
        add_optional_param(params, "language", getattr(search_context, "language", None))
        add_optional_param(
            params,
            "accessibility_need",
            getattr(search_context, "accessibility_need", None),
        )
        add_optional_param(params, "telehealth", getattr(search_context, "telehealth", None))
        add_optional_param(params, "radius", getattr(search_context, "radius_miles", None))
        add_optional_param(params, "limit", getattr(search_context, "limit", None))

    add_optional_param(params, "facility_uid", facility_uid)
    add_optional_param(params, "provider_lng", f"{provider_longitude:.6f}")
    add_optional_param(params, "provider_lat", f"{provider_latitude:.6f}")
    add_optional_param(params, "origin_lng", f"{origin_longitude:.6f}")
    add_optional_param(params, "origin_lat", f"{origin_latitude:.6f}")

    params = urlencode(params)
    return f"{frontend_base_url()}/?{params}"


def add_optional_param(params: dict[str, str], key: str, value: Any | None) -> None:
    if value is None:
        return
    if isinstance(value, bool):
        params[key] = str(value).lower()
        return

    text_value = str(value).strip()
    if text_value:
        params[key] = text_value
