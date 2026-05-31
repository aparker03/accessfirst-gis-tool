from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    provider_records_loaded: int


class SearchRequest(BaseModel):
    location: str = Field(..., min_length=1)
    service_type: Optional[str] = None
    language: Optional[str] = None
    accessibility_need: Optional[str] = None
    telehealth: Optional[bool] = None
    radius_miles: float = Field(10.0, gt=0)
    limit: int = Field(10, ge=1, le=100)
    include_warning_results: bool = True
    include_manual_review: bool = False
    include_outside_la_county: bool = False


class LocationValidationRequest(BaseModel):
    location: str = Field(..., min_length=1)


class LocationValidationResponse(BaseModel):
    input: str
    is_valid_zip: Optional[bool] = None
    is_la_county: Optional[bool] = None
    normalized_location: str
    reason: str


class Coordinates(BaseModel):
    longitude: float
    latitude: float


class FacilityResult(BaseModel):
    facility_uid: str
    facility_name: Optional[str] = None
    provider_display_name: Optional[str] = None
    service_area: Optional[str] = None
    care_setting: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    zip_code: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    email: Optional[str] = None
    hours: Optional[str] = None
    languages: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    service_summary: Optional[str] = None
    methods_of_delivery: list[str] = Field(default_factory=list)
    delivery_summary: Optional[str] = None
    ada_facility: Optional[str] = None
    accepting_status: Optional[str] = None
    insurance_acceptance_verified: Optional[str] = None
    insurance_note: Optional[str] = None
    practice_focus_summary: Optional[str] = None
    practitioner_summary: Optional[str] = None
    practitioner_count: Optional[int] = None
    practitioner_disciplines: list[str] = Field(default_factory=list)
    has_practitioner_names: bool = False
    has_npi_or_license_details: bool = False
    longitude: float
    latitude: float
    distance_miles: float
    score: float
    map_inclusion_status: Optional[str] = None
    map_inclusion_reason: Optional[str] = None
    geocode_quality_status: Optional[str] = None
    geography_status: Optional[str] = None
    interactive_map_url: str


class SearchResponse(BaseModel):
    query: SearchRequest
    origin: Coordinates
    origin_place_name: Optional[str] = None
    count: int
    message: str
    results: list[FacilityResult]


class FacilityResponse(BaseModel):
    facility_uid: str
    record: dict[str, Any]
