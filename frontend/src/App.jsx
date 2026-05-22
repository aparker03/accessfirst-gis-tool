import React, { useEffect, useMemo, useRef, useState } from 'react'
import mapboxgl from 'mapbox-gl'
import {
  getFacility,
  initialFacilityLinkFromUrl,
  initialFiltersFromUrl,
  searchFacilities,
  syncFiltersToUrl,
} from './lib/api.js'

const LOS_ANGELES_CENTER = [-118.2437, 34.0522]

export default function App() {
  const [filters, setFilters] = useState(() => initialFiltersFromUrl())
  const [response, setResponse] = useState(null)
  const [selectedFacilityUid, setSelectedFacilityUid] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [mapReady, setMapReady] = useState(false)
  const facilityLinkRef = useRef(initialFacilityLinkFromUrl())
  const mapContainerRef = useRef(null)
  const mapRef = useRef(null)
  const markersRef = useRef([])
  const originMarkerRef = useRef(null)

  const results = response?.results || []
  const selectedFacility = useMemo(
    () => results.find((facility) => facility.facility_uid === selectedFacilityUid) || results[0] || null,
    [results, selectedFacilityUid],
  )

  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current || !mapboxgl.accessToken) return

    mapRef.current = new mapboxgl.Map({
      container: mapContainerRef.current,
      style: 'mapbox://styles/mapbox/light-v11',
      center: LOS_ANGELES_CENTER,
      zoom: 9,
      attributionControl: true,
    })
    mapRef.current.addControl(new mapboxgl.NavigationControl({ visualizePitch: true }), 'top-right')
    mapRef.current.addControl(new mapboxgl.ScaleControl({ unit: 'imperial' }), 'bottom-right')
    mapRef.current.on('load', () => setMapReady(true))
  }, [])

  useEffect(() => {
    const facilityLink = facilityLinkRef.current
    if (facilityLink.facility_uid && filters.location) {
      runSearch(filters, {
        syncUrl: false,
        selectFacilityUid: facilityLink.facility_uid,
        fallbackFacilityLink: facilityLink,
      })
    } else if (facilityLink.facility_uid) {
      loadFacilityLink(facilityLink)
    } else if (filters.location) {
      runSearch(filters)
    }
  }, [])

  useEffect(() => {
    renderMapResults({
      map: mapRef.current,
      results,
      origin: response?.origin,
      selectedFacilityUid: selectedFacility?.facility_uid,
      markersRef,
      originMarkerRef,
      onSelect: setSelectedFacilityUid,
    })
  }, [results, response?.origin, selectedFacility?.facility_uid, mapReady])

  function updateFilter(key, value) {
    setFilters((current) => ({ ...current, [key]: value }))
  }

  async function runSearch(nextFilters, options = {}) {
    if (!nextFilters.location.trim()) {
      setError('Enter a location to search nearby facilities.')
      setResponse(null)
      return
    }

    const controller = new AbortController()
    setIsLoading(true)
    setError('')
    if (options.syncUrl !== false) {
      syncFiltersToUrl(nextFilters)
    }

    try {
      const data = await searchFacilities(nextFilters, controller.signal)
      const requestedFacilityUid = options.selectFacilityUid
      const matchedFacility = requestedFacilityUid
        ? data.results?.find((facility) => facility.facility_uid === requestedFacilityUid)
        : null

      setResponse(data)
      if (matchedFacility) {
        setSelectedFacilityUid(matchedFacility.facility_uid)
      } else if (requestedFacilityUid && options.fallbackFacilityLink) {
        await loadFacilityLink(options.fallbackFacilityLink, {
          fallbackOrigin: data.origin,
          fallbackOriginPlaceName: data.origin_place_name,
        })
      } else {
        setSelectedFacilityUid(data.results?.[0]?.facility_uid || null)
      }
    } catch (searchError) {
      if (options.fallbackFacilityLink) {
        await loadFacilityLink(options.fallbackFacilityLink)
      } else {
        setResponse(null)
        setSelectedFacilityUid(null)
        setError(searchError.message || 'Search failed.')
      }
    } finally {
      setIsLoading(false)
    }
  }

  async function loadFacilityLink(facilityLink, options = {}) {
    const controller = new AbortController()
    setIsLoading(true)
    setError('')

    try {
      const data = await getFacility(facilityLink.facility_uid, controller.signal)
      const origin = originFromLink(facilityLink) || options.fallbackOrigin || null
      const facility = facilityFromProviderRecord(data.record, {
        facilityLink,
        origin,
      })

      if (!facility) {
        throw new Error('Facility was found, but it does not include usable coordinates.')
      }

      setResponse({
        query: filters,
        origin,
        origin_place_name: options.fallbackOriginPlaceName || (origin ? 'Map link origin' : null),
        count: 1,
        message: 'Loaded facility from map link.',
        results: [facility],
      })
      setSelectedFacilityUid(facility.facility_uid)
    } catch (facilityError) {
      setResponse(null)
      setSelectedFacilityUid(null)
      setError(facilityError.message || 'Facility link could not be loaded.')
    } finally {
      setIsLoading(false)
    }
  }

  function handleSubmit(event) {
    event.preventDefault()
    runSearch(filters)
  }

  return (
    <main className="app-shell">
      <section className="filter-bar" aria-label="Facility search filters">
        <div>
          <p className="eyebrow">AccessFirst GIS</p>
          <h1>Facility Finder</h1>
        </div>
        <form className="search-form" onSubmit={handleSubmit}>
          <label className="field field-location">
            <span>Location</span>
            <input
              value={filters.location}
              onChange={(event) => updateFilter('location', event.target.value)}
              placeholder="Address, city, or ZIP"
              autoComplete="street-address"
            />
          </label>
          <label className="field">
            <span>Service</span>
            <input
              value={filters.service_type}
              onChange={(event) => updateFilter('service_type', event.target.value)}
              placeholder="Crisis, therapy, medication"
            />
          </label>
          <label className="field">
            <span>Language</span>
            <input
              value={filters.language}
              onChange={(event) => updateFilter('language', event.target.value)}
              placeholder="Spanish"
            />
          </label>
          <label className="field">
            <span>Access</span>
            <input
              value={filters.accessibility_need}
              onChange={(event) => updateFilter('accessibility_need', event.target.value)}
              placeholder="Wheelchair, ADA"
            />
          </label>
          <label className="field compact">
            <span>Radius</span>
            <input
              type="number"
              min="1"
              max="100"
              value={filters.radius_miles}
              onChange={(event) => updateFilter('radius_miles', Number(event.target.value))}
            />
          </label>
          <label className="field compact">
            <span>Limit</span>
            <input
              type="number"
              min="1"
              max="100"
              value={filters.limit}
              onChange={(event) => updateFilter('limit', Number(event.target.value))}
            />
          </label>
          <label className="field select-field">
            <span>Visit type</span>
            <select
              value={filters.telehealth === null || filters.telehealth === undefined ? 'any' : String(filters.telehealth)}
              onChange={(event) => {
                const value = event.target.value
                updateFilter('telehealth', value === 'any' ? null : value === 'true')
              }}
            >
              <option value="any">Any</option>
              <option value="false">In person</option>
              <option value="true">Telehealth</option>
            </select>
          </label>
          <div className="toggle-group" aria-label="Result inclusion options">
            <label>
              <input
                type="checkbox"
                checked={filters.include_warning_results}
                onChange={(event) => updateFilter('include_warning_results', event.target.checked)}
              />
              Warnings
            </label>
            <label>
              <input
                type="checkbox"
                checked={filters.include_manual_review}
                onChange={(event) => updateFilter('include_manual_review', event.target.checked)}
              />
              Manual review
            </label>
            <label>
              <input
                type="checkbox"
                checked={filters.include_outside_la_county}
                onChange={(event) => updateFilter('include_outside_la_county', event.target.checked)}
              />
              Outside LA
            </label>
          </div>
          <button className="primary-button" type="submit" disabled={isLoading}>
            {isLoading ? 'Searching' : 'Search'}
          </button>
        </form>
      </section>

      <section className="workspace">
        <aside className="results-panel" aria-label="Ranked facility results">
          <div className="panel-header">
            <div>
              <h2>Results</h2>
              <p>{resultSummary(response, isLoading, error)}</p>
            </div>
          </div>
          {isLoading && <LoadingState />}
          {!isLoading && error && <NoticeState title="Search needs attention" message={error} />}
          {!isLoading && !error && !response && (
            <NoticeState title="Start with a location" message="Search from an address, city, or ZIP to find nearby facilities." />
          )}
          {!isLoading && response && results.length === 0 && (
            <NoticeState title="No matching facilities" message={response.message || 'Try a larger radius or fewer filters.'} />
          )}
          <div className="facility-list">
            {results.map((facility, index) => (
              <FacilityCard
                key={facility.facility_uid}
                facility={facility}
                rank={index + 1}
                isSelected={facility.facility_uid === selectedFacility?.facility_uid}
                onSelect={() => setSelectedFacilityUid(facility.facility_uid)}
              />
            ))}
          </div>
        </aside>

        <section className="map-region" aria-label="Facility map">
          <div className="map-container" ref={mapContainerRef}>
            {!mapboxgl.accessToken && (
              <div className="map-overlay">
                <strong>Mapbox token missing</strong>
                <span>Set VITE_MAPBOX_PUBLIC_TOKEN in frontend/.env.</span>
              </div>
            )}
          </div>
          <DetailPanel facility={selectedFacility} origin={response?.origin_place_name} />
        </section>
      </section>
    </main>
  )
}

function FacilityCard({ facility, rank, isSelected, onSelect }) {
  return (
    <button className={`facility-card ${isSelected ? 'selected' : ''}`} type="button" onClick={onSelect}>
      <span className="rank-marker">{rank}</span>
      <span className="card-main">
        <span className="facility-name">{facility.facility_name || facility.provider_display_name}</span>
        <span className="facility-meta">
          {formatDistance(facility.distance_miles)} - {facility.city} {facility.zip_code}
        </span>
        <span className="facility-meta">{facility.care_setting || 'Care setting not listed'}</span>
        <span className="badge-row">
          {facility.map_inclusion_status === 'include_with_warning' && <span className="badge warning">Warning</span>}
          {facility.ada_facility === 'yes' && <span className="badge success">ADA</span>}
          {facility.languages?.slice(0, 2).map((language) => (
            <span className="badge neutral" key={language}>{language}</span>
          ))}
        </span>
      </span>
    </button>
  )
}

function DetailPanel({ facility, origin }) {
  if (!facility) {
    return (
      <aside className="detail-panel empty" aria-label="Facility details">
        <h2>Facility details</h2>
        <p>Select a result or run a search to inspect facility details.</p>
      </aside>
    )
  }

  return (
    <aside className="detail-panel" aria-label="Facility details">
      <div className="detail-heading">
        <div>
          <p className="eyebrow">{facility.service_area || 'Service area not listed'}</p>
          <h2>{facility.facility_name || facility.provider_display_name}</h2>
        </div>
        {facility.map_inclusion_status === 'include_with_warning' && <span className="badge warning">Geocode warning</span>}
      </div>
      <dl className="detail-grid">
        <div>
          <dt>Distance</dt>
          <dd>{formatDistance(facility.distance_miles)}</dd>
        </div>
        <div>
          <dt>Address</dt>
          <dd>{facility.address || 'Not listed'}</dd>
        </div>
        <div>
          <dt>Phone</dt>
          <dd>{facility.phone || 'Not listed'}</dd>
        </div>
        <div>
          <dt>Hours</dt>
          <dd>{facility.hours || 'Not listed'}</dd>
        </div>
        <div>
          <dt>Languages</dt>
          <dd>{listText(facility.languages)}</dd>
        </div>
        <div>
          <dt>Services</dt>
          <dd>{listText(facility.services)}</dd>
        </div>
        <div>
          <dt>Delivery</dt>
          <dd>{listText(facility.methods_of_delivery)}</dd>
        </div>
        <div>
          <dt>Map status</dt>
          <dd>{facility.map_inclusion_reason || facility.map_inclusion_status}</dd>
        </div>
      </dl>
      <div className="directions-box">
        <span>Route preview</span>
        <strong>{origin || 'Search origin'} to {facility.city || 'facility'}</strong>
        <p>The map shows the selected facility and search origin. Confirm travel details with your preferred navigation tool.</p>
      </div>
      {facility.insurance_note && <p className="insurance-note">{facility.insurance_note}</p>}
    </aside>
  )
}

function LoadingState() {
  return (
    <div className="state-block" role="status">
      <span className="spinner" aria-hidden="true" />
      <strong>Searching nearby facilities</strong>
      <p>Resolving the location and ranking eligible provider records.</p>
    </div>
  )
}

function NoticeState({ title, message }) {
  return (
    <div className="state-block">
      <strong>{title}</strong>
      <p>{message}</p>
    </div>
  )
}

function facilityFromProviderRecord(record, { facilityLink, origin }) {
  if (!record) return null

  const mapbox = record.mapbox && typeof record.mapbox === 'object' ? record.mapbox : {}
  const longitude = parseCoordinate(mapbox.longitude) ?? facilityLink.provider_lng
  const latitude = parseCoordinate(mapbox.latitude) ?? facilityLink.provider_lat
  if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) {
    return null
  }

  const distance = origin
    ? haversineMiles(origin.longitude, origin.latitude, longitude, latitude)
    : null

  return {
    facility_uid: String(record.facility_uid || facilityLink.facility_uid),
    facility_name: record.facility_name || null,
    provider_display_name: record.provider_display_name || null,
    service_area: record.service_area || null,
    care_setting: record.care_setting || null,
    address: record.address || null,
    city: record.city || null,
    zip_code: record.zip_code || null,
    phone: record.phone || null,
    website: record.website || null,
    email: record.email || null,
    hours: record.hours || null,
    languages: Array.isArray(record.languages) ? record.languages : [],
    services: Array.isArray(record.services) ? record.services : [],
    methods_of_delivery: Array.isArray(record.methods_of_delivery) ? record.methods_of_delivery : [],
    ada_facility: record.ada_facility || null,
    accepting_status: record.accepting_status || null,
    insurance_acceptance_verified: record.insurance_acceptance_verified || null,
    insurance_note: insuranceNote(record),
    longitude,
    latitude,
    distance_miles: distance === null ? null : Number(distance.toFixed(2)),
    score: 0,
    map_inclusion_status: mapbox.map_inclusion_status || null,
    map_inclusion_reason: mapbox.map_inclusion_reason || null,
    geocode_quality_status: mapbox.geocode_quality_status || null,
    geography_status: mapbox.geography_status || null,
    interactive_map_url: window.location.href,
  }
}

function originFromLink(facilityLink) {
  if (!Number.isFinite(facilityLink.origin_lng) || !Number.isFinite(facilityLink.origin_lat)) {
    return null
  }
  return {
    longitude: facilityLink.origin_lng,
    latitude: facilityLink.origin_lat,
  }
}

function parseCoordinate(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function insuranceNote(record) {
  if (String(record.insurance_acceptance_verified || '').toLowerCase() === 'yes') {
    return null
  }
  return 'Insurance acceptance is not verified in the source data; call to confirm coverage.'
}

function formatDistance(distanceMiles) {
  const distance = Number(distanceMiles)
  if (!Number.isFinite(distance)) {
    return 'Distance not calculated'
  }
  return `${distance} mi`
}

function haversineMiles(originLongitude, originLatitude, destinationLongitude, destinationLatitude) {
  const earthRadiusMiles = 3958.7613
  const originLatRad = toRadians(originLatitude)
  const destinationLatRad = toRadians(destinationLatitude)
  const deltaLat = toRadians(destinationLatitude - originLatitude)
  const deltaLng = toRadians(destinationLongitude - originLongitude)
  const a = (
    Math.sin(deltaLat / 2) ** 2
    + Math.cos(originLatRad)
    * Math.cos(destinationLatRad)
    * Math.sin(deltaLng / 2) ** 2
  )
  return earthRadiusMiles * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

function toRadians(value) {
  return value * Math.PI / 180
}

function renderMapResults({ map, results, origin, selectedFacilityUid, markersRef, originMarkerRef, onSelect }) {
  if (!map) return

  markersRef.current.forEach((marker) => marker.remove())
  markersRef.current = []
  if (originMarkerRef.current) {
    originMarkerRef.current.remove()
    originMarkerRef.current = null
  }

  if (map.getLayer('route-line')) map.removeLayer('route-line')
  if (map.getSource('route-line')) map.removeSource('route-line')

  const bounds = new mapboxgl.LngLatBounds()

  if (origin?.longitude && origin?.latitude) {
    const originElement = document.createElement('div')
    originElement.className = 'origin-marker'
    originElement.setAttribute('aria-label', 'Search origin')
    originMarkerRef.current = new mapboxgl.Marker({ element: originElement })
      .setLngLat([origin.longitude, origin.latitude])
      .addTo(map)
    bounds.extend([origin.longitude, origin.latitude])
  }

  results.forEach((facility, index) => {
    const element = document.createElement('button')
    element.className = `pin-marker ${facility.facility_uid === selectedFacilityUid ? 'selected' : ''}`
    element.type = 'button'
    element.textContent = String(index + 1)
    element.setAttribute('aria-label', `Select ${facility.facility_name || 'facility'} result ${index + 1}`)
    element.addEventListener('click', () => onSelect(facility.facility_uid))

    const marker = new mapboxgl.Marker({ element })
      .setLngLat([facility.longitude, facility.latitude])
      .addTo(map)
    markersRef.current.push(marker)
    bounds.extend([facility.longitude, facility.latitude])
  })

  const selected = results.find((facility) => facility.facility_uid === selectedFacilityUid)
  if (selected && origin?.longitude && origin?.latitude && map.isStyleLoaded()) {
    map.addSource('route-line', {
      type: 'geojson',
      data: {
        type: 'Feature',
        geometry: {
          type: 'LineString',
          coordinates: [
            [origin.longitude, origin.latitude],
            [selected.longitude, selected.latitude],
          ],
        },
      },
    })
    map.addLayer({
      id: 'route-line',
      type: 'line',
      source: 'route-line',
      paint: {
        'line-color': '#0f766e',
        'line-width': 3,
        'line-dasharray': [2, 1.5],
      },
    })
  }

  if (!bounds.isEmpty()) {
    map.fitBounds(bounds, { padding: 84, maxZoom: 13, duration: 700 })
  }
}

function resultSummary(response, isLoading, error) {
  if (isLoading) return 'Loading'
  if (error) return 'Unable to complete search'
  if (!response) return 'Awaiting search'
  return `${response.count} facilities ranked`
}

function listText(values) {
  return values?.length ? values.join(', ') : 'Not listed'
}
