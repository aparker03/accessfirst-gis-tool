const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '')

export function initialFiltersFromUrl() {
  const params = new URLSearchParams(window.location.search)
  return {
    location: params.get('location') || '',
    service_type: params.get('service_type') || '',
    language: params.get('language') || '',
    accessibility_need: params.get('accessibility_need') || '',
    telehealth: parseTelehealth(params.get('telehealth')),
    radius_miles: Number(params.get('radius') || params.get('radius_miles') || 10),
    limit: Number(params.get('limit') || 12),
    include_warning_results: parseBoolean(params.get('include_warning_results'), true),
    include_manual_review: parseBoolean(params.get('include_manual_review'), false),
    include_outside_la_county: parseBoolean(params.get('include_outside_la_county'), false),
  }
}

export function initialFacilityLinkFromUrl() {
  const params = new URLSearchParams(window.location.search)
  return {
    facility_uid: params.get('facility_uid') || '',
    provider_lng: parseOptionalNumber(params.get('provider_lng')),
    provider_lat: parseOptionalNumber(params.get('provider_lat')),
    origin_lng: parseOptionalNumber(params.get('origin_lng')),
    origin_lat: parseOptionalNumber(params.get('origin_lat')),
  }
}

export function syncFiltersToUrl(filters) {
  const params = new URLSearchParams(window.location.search)
  SEARCH_PARAM_KEYS.forEach((key) => params.delete(key))
  FACILITY_PARAM_KEYS.forEach((key) => params.delete(key))
  setParam(params, 'location', filters.location)
  setParam(params, 'service_type', filters.service_type)
  setParam(params, 'language', filters.language)
  setParam(params, 'accessibility_need', filters.accessibility_need)
  if (filters.telehealth !== null && filters.telehealth !== undefined) {
    params.set('telehealth', String(filters.telehealth))
  }
  setParam(params, 'radius', filters.radius_miles)
  setParam(params, 'limit', filters.limit)
  if (filters.include_warning_results === false) {
    params.set('include_warning_results', 'false')
  }
  if (filters.include_manual_review) {
    params.set('include_manual_review', 'true')
  }
  if (filters.include_outside_la_county) {
    params.set('include_outside_la_county', 'true')
  }

  const nextUrl = params.toString()
    ? `${window.location.pathname}?${params.toString()}${window.location.hash}`
    : `${window.location.pathname}${window.location.hash}`
  window.history.replaceState(null, '', nextUrl)
}

export function clearSearchStateFromUrl() {
  const params = new URLSearchParams(window.location.search)
  SEARCH_PARAM_KEYS.forEach((key) => params.delete(key))
  FACILITY_PARAM_KEYS.forEach((key) => params.delete(key))
  const nextUrl = params.toString()
    ? `${window.location.pathname}?${params.toString()}${window.location.hash}`
    : `${window.location.pathname}${window.location.hash}`
  window.history.replaceState(null, '', nextUrl)
}

export async function searchFacilities(filters, signal) {
  const response = await fetch(`${API_BASE_URL}/search-facilities`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      location: filters.location,
      service_type: emptyToNull(filters.service_type),
      language: emptyToNull(filters.language),
      accessibility_need: emptyToNull(filters.accessibility_need),
      telehealth: filters.telehealth,
      radius_miles: Number(filters.radius_miles),
      limit: Number(filters.limit),
      include_warning_results: Boolean(filters.include_warning_results),
      include_manual_review: Boolean(filters.include_manual_review),
      include_outside_la_county: Boolean(filters.include_outside_la_county),
    }),
    signal,
  })

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}))
    throw new Error(errorBody.detail || `Search failed with HTTP ${response.status}`)
  }

  return response.json()
}

export async function getFacility(facilityUid, signal) {
  const response = await fetch(`${API_BASE_URL}/facility/${encodeURIComponent(facilityUid)}`, {
    method: 'GET',
    signal,
  })

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}))
    throw new Error(errorBody.detail || `Facility lookup failed with HTTP ${response.status}`)
  }

  return response.json()
}

function setParam(params, key, value) {
  if (value !== null && value !== undefined && String(value).trim() !== '') {
    params.set(key, String(value))
  }
}

function parseBoolean(value, fallback) {
  if (value === null) return fallback
  return ['1', 'true', 'yes', 'on'].includes(value.toLowerCase())
}

function parseTelehealth(value) {
  if (value === null || value === '') return null
  if (['1', 'true', 'yes', 'on'].includes(value.toLowerCase())) return true
  if (['0', 'false', 'no', 'off'].includes(value.toLowerCase())) return false
  return null
}

function emptyToNull(value) {
  return value && String(value).trim() ? String(value).trim() : null
}

function parseOptionalNumber(value) {
  if (value === null || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

const SEARCH_PARAM_KEYS = [
  'location',
  'service_type',
  'language',
  'accessibility_need',
  'telehealth',
  'radius',
  'radius_miles',
  'limit',
  'include_warning_results',
  'include_manual_review',
  'include_outside_la_county',
]

const FACILITY_PARAM_KEYS = [
  'facility_uid',
  'provider_lng',
  'provider_lat',
  'origin_lng',
  'origin_lat',
]
