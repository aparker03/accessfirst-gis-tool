from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent
DEFAULT_PROVIDER_DATA_PATH = PROJECT_ROOT / "data" / "processed" / "provider_records_geocoded.json"


load_dotenv(BACKEND_DIR / ".env")


def resolve_project_path(path_value: str | None, default_path: Path) -> Path:
    if not path_value:
        return default_path

    path = Path(path_value)
    if path.is_absolute():
        return path

    backend_relative = (BACKEND_DIR / path).resolve()
    if backend_relative.exists():
        return backend_relative

    return (PROJECT_ROOT / path).resolve()


def provider_data_path() -> Path:
    return resolve_project_path(os.getenv("PROVIDER_DATA_PATH"), DEFAULT_PROVIDER_DATA_PATH)


@lru_cache(maxsize=1)
def load_provider_records() -> list[dict[str, Any]]:
    path = provider_data_path()
    if not path.exists():
        raise FileNotFoundError(f"Provider data file not found: {path}")

    with path.open("r", encoding="utf-8") as provider_file:
        records = json.load(provider_file)

    if not isinstance(records, list):
        raise ValueError(f"Provider data file must contain a JSON list: {path}")

    return [record for record in records if isinstance(record, dict)]


@lru_cache(maxsize=1)
def provider_records_by_uid() -> dict[str, dict[str, Any]]:
    return {
        str(record.get("facility_uid")): record
        for record in load_provider_records()
        if record.get("facility_uid")
    }
