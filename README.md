# AccessFirst GIS Facility Finder

Starter repo scaffold for a Mapbox-based LA County mental health facility finder integrated into Dify as a custom OpenAPI tool.

Current status:
- Provider records have been normalized from JSONL.
- Records are not geocoded yet.
- Mapbox-ready coordinates still need to be added.
- Insurance acceptance is not verified in the current source data, so the app must not claim plan acceptance.

Recommended flow:
1. Review normalized provider records.
2. Geocode addresses with Mapbox.
3. Create geocoded JSON and GeoJSON.
4. Build FastAPI search API.
5. Build Mapbox frontend.
6. Import OpenAPI schema into Dify as custom tool.
7. Add the tool inside the Resource Navigator Agent.
