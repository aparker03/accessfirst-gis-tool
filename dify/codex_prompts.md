# Codex Prompts for AccessFirst GIS Facility Finder

Use these prompts one at a time. Do not ask Codex to build the whole product in one pass.

## 1. Repo setup
Create a production-ready project structure for an AccessFirst GIS facility finder. Use FastAPI for the backend, React with Mapbox GL JS for the frontend, JSON and GeoJSON data files for provider records, and Dify OpenAPI schema files. Keep the existing folder structure. Do not invent provider data. Use TODO comments where implementation depends on Mapbox tokens or geocoded data.

## 2. Data models
Create Pydantic models for provider records and facility search responses. Use the fields in data/processed/provider_records_updated_v0_2.jsonl. Include nested models for source_trace and mapbox. Do not remove source trace fields. Do not claim insurance acceptance when insurance_acceptance_verified is no.

## 3. Geocoding script
Create scripts/geocode_with_mapbox.py. It should read data/processed/provider_records_updated_v0_2.jsonl, call Mapbox geocoding only when mapbox.geocode_status is not_geocoded, save longitude and latitude only when a confident match is returned, and flag low-confidence records as needs_review. It must write data/processed/provider_records_geocoded.jsonl and data/audit/geocoding_audit.csv. Use environment variable MAPBOX_SECRET_TOKEN. Do not hardcode tokens.

## 4. GeoJSON export
Create scripts/export_geojson.py. It should read provider_records_geocoded.jsonl and write provider_records.geojson. Include only records with valid coordinates as point features. Put source_trace, facility_uid, facility_name, service_area, address, phone, languages, services, care_setting, methods_of_delivery, ada_facility, and review_flags in properties.

## 5. Search API
Implement FastAPI POST /search-facilities. It should load provider_records_geocoded.jsonl, resolve user location from ZIP/city/address, calculate distance, filter by radius, score matches by service_type, language, methods_of_delivery, accessibility_need, and focus terms, and return top results with interactive_map_url. Do not use insurance as a hard filter unless insurance_acceptance_verified is yes. Return payer_context as context only.

## 6. Mapbox frontend
Build a React Mapbox GL JS frontend. It should read URL parameters for location, service_type, language, accessibility_need, radius_miles, and limit. It should call POST /search-facilities and display numbered pins, a user-location marker, a sidebar of facility cards, filter chips, loading states, empty states, and a selected facility detail panel. Directions must be in the map UI, not the Dify chat.

## 7. Dify OpenAPI schema
Create dify/accessfirst_gis_openapi.yaml for a custom Dify tool named AccessFirst GIS Facility Finder. Define POST /search-facilities with parameters location, service_type, language, accessibility_need, telehealth, radius_miles, limit, and selected_facility_id. Response must include query_summary, user_location, results, interactive_map_url, and disclaimer.

## 8. Tests
Write pytest tests for geocoding status handling, distance calculation, ZIP/city lookup behavior, language scoring, accessibility scoring, empty results, interactive_map_url generation, and the rule that unverified insurance is not used as a confirmed acceptance claim.

## 9. UI polish
Refine the Mapbox UI for accessibility and high-end design. Use strong contrast, visible focus states, responsive layout, readable typography, clear cards, and plain-language labels. Do not use tiny text or raw database labels.
