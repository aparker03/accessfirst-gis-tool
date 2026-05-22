from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .data_loader import load_provider_records, provider_records_by_uid
from .geocode import LocationGeocodingError, geocode_location
from .models import Coordinates, FacilityResponse, HealthResponse, SearchRequest, SearchResponse
from .search import search_facilities


app = FastAPI(
    title="AccessFirst GIS Facility Finder API",
    version="0.1.0",
    description="Search LA County mental health provider records using pre-geocoded Mapbox data.",
)

frontend_origin = os.getenv("MAP_FRONTEND_BASE_URL", "http://localhost:5173").rstrip("/")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin, "http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", provider_records_loaded=len(load_provider_records()))


@app.get("/facility/{facility_uid}", response_model=FacilityResponse)
def get_facility(facility_uid: str) -> FacilityResponse:
    record = provider_records_by_uid().get(facility_uid)
    if record is None:
        raise HTTPException(status_code=404, detail="Facility not found.")
    return FacilityResponse(facility_uid=facility_uid, record=record)


@app.post("/search-facilities", response_model=SearchResponse)
def post_search_facilities(request: SearchRequest) -> SearchResponse:
    try:
        origin = geocode_location(request.location)
    except LocationGeocodingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    results = search_facilities(
        load_provider_records(),
        request,
        origin["longitude"],
        origin["latitude"],
    )
    message = (
        f"Found {len(results)} matching facilities."
        if results
        else "No records matched the requested filters and radius."
    )

    return SearchResponse(
        query=request,
        origin=Coordinates(
            longitude=origin["longitude"],
            latitude=origin["latitude"],
        ),
        origin_place_name=origin.get("place_name"),
        count=len(results),
        message=message,
        results=results,
    )
