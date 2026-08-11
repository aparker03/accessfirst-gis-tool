import React, { useEffect, useMemo, useRef, useState } from 'react'
import mapboxgl from 'mapbox-gl'
import {
  clearSearchStateFromUrl,
  getFacility,
  initialFacilityLinkFromUrl,
  initialFiltersFromUrl,
  searchFacilities,
  syncFiltersToUrl,
} from './lib/api.js'
import {
  getInitialLanguage,
  LANGUAGE_OPTIONS,
  setInterfaceLanguage,
  translate,
} from './lib/i18n.js'

const LOS_ANGELES_CENTER = [-118.2437, 34.0522]
const DEFAULT_FILTERS = {
  location: '',
  service_type: '',
  language: '',
  accessibility_need: '',
  telehealth: null,
  radius_miles: 10,
  limit: 12,
  include_warning_results: true,
  include_manual_review: false,
  include_outside_la_county: false,
}

export default function App() {
  const [uiLanguage, setUiLanguage] = useState(() => getInitialLanguage())
  const [isSearchOpen, setIsSearchOpen] = useState(
    () => window.matchMedia('(min-width: 1081px)').matches,
  )
  const [filters, setFilters] = useState(() => initialFiltersFromUrl())
  const [response, setResponse] = useState(null)
  const [selectedFacilityUid, setSelectedFacilityUid] = useState(null)
  const [selectedFacilityRecord, setSelectedFacilityRecord] = useState(null)
  const [isDetailLoading, setIsDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [mapReady, setMapReady] = useState(false)
  const [detailRevealRequest, setDetailRevealRequest] = useState(0)
  const facilityLinkRef = useRef(initialFacilityLinkFromUrl())
  const mapContainerRef = useRef(null)
  const mapRef = useRef(null)
  const markersRef = useRef([])
  const originMarkerRef = useRef(null)
  const mapBoundsKeyRef = useRef('')
  const detailPanelRef = useRef(null)
  const t = useMemo(
    () => (key, values) => translate(uiLanguage, key, values),
    [uiLanguage],
  )

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
      cooperativeGestures: true,
    })
    mapRef.current.addControl(new mapboxgl.NavigationControl({ visualizePitch: true }), 'top-right')
    mapRef.current.addControl(new mapboxgl.ScaleControl({ unit: 'imperial' }), 'bottom-right')
    mapRef.current.on('load', () => setMapReady(true))
  }, [])

  useEffect(() => {
    setInterfaceLanguage(uiLanguage)
    document.documentElement.lang = uiLanguage
    document.title = t('pageTitle')
  }, [uiLanguage, t])

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
      mapBoundsKeyRef,
      onSelect: handleFacilitySelect,
      t,
    })
  }, [results, response?.origin, selectedFacility?.facility_uid, mapReady, t])

  useEffect(() => {
    if (!selectedFacility?.facility_uid || detailRevealRequest === 0) return
    const panel = detailPanelRef.current
    if (!panel) return

    const bounds = panel.getBoundingClientRect()
    const isOutsideViewport = bounds.top < 0 || bounds.bottom > window.innerHeight
    if (isOutsideViewport) {
      panel.scrollIntoView({
        behavior: 'auto',
        block: 'start',
      })
    }
    panel.focus({ preventScroll: true })
  }, [detailRevealRequest, selectedFacility?.facility_uid])

  useEffect(() => {
    if (!selectedFacility?.facility_uid) {
      setSelectedFacilityRecord(null)
      setIsDetailLoading(false)
      setDetailError('')
      return
    }

    const controller = new AbortController()
    let isActive = true

    setSelectedFacilityRecord((current) => (
      current?.facility_uid === selectedFacility.facility_uid ? current : null
    ))
    setIsDetailLoading(true)
    setDetailError('')

    getFacility(selectedFacility.facility_uid, controller.signal)
      .then((data) => {
        if (isActive) {
          setSelectedFacilityRecord(data.record || null)
          setDetailRevealRequest((current) => current + 1)
        }
      })
      .catch((detailFetchError) => {
        if (!isActive || detailFetchError.name === 'AbortError') return
        setSelectedFacilityRecord(null)
        setDetailError('detailLoadFailed')
      })
      .finally(() => {
        if (isActive) setIsDetailLoading(false)
      })

    return () => {
      isActive = false
      controller.abort()
    }
  }, [selectedFacility?.facility_uid])

  function handleLanguageChange(event) {
    const nextLanguage = setInterfaceLanguage(event.target.value)
    setUiLanguage(nextLanguage)
  }

  function handleFacilitySelect(facilityUid) {
    setSelectedFacilityUid(facilityUid)
    setDetailRevealRequest((current) => current + 1)
  }

  function updateFilter(key, value) {
    setFilters((current) => ({ ...current, [key]: value }))
  }

  function clearFilters() {
    setFilters(DEFAULT_FILTERS)
    setResponse(null)
    setSelectedFacilityUid(null)
    setSelectedFacilityRecord(null)
    setDetailError('')
    setError('')
    clearSearchStateFromUrl()
  }

  async function runSearch(nextFilters, options = {}) {
    if (!nextFilters.location.trim()) {
      setError(t('enterLocation'))
      setResponse(null)
      return
    }

    const controller = new AbortController()
    setIsLoading(true)
    setError('')
    setSelectedFacilityRecord(null)
    setDetailError('')
    if (options.syncUrl !== false) {
      syncFiltersToUrl(nextFilters)
    }

    try {
      const data = await searchFacilities(nextFilters, controller.signal)
      const requestedFacilityUid = options.selectFacilityUid
      const matchedFacility = requestedFacilityUid
        ? data.results?.find((facility) => facility.facility_uid === requestedFacilityUid)
        : null

      setError('')
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
        setError(t('searchFailed'))
      }
    } finally {
      setIsLoading(false)
    }
  }

  async function loadFacilityLink(facilityLink, options = {}) {
    const controller = new AbortController()
    setIsLoading(true)
    setError('')
    setDetailError('')

    try {
      const data = await getFacility(facilityLink.facility_uid, controller.signal)
      const origin = originFromLink(facilityLink) || options.fallbackOrigin || null
      const facility = facilityFromProviderRecord(data.record, {
        facilityLink,
        origin,
      })

      if (!facility) {
        throw new Error(t('unusableCoordinates'))
      }

      setError('')
      setResponse({
        query: filters,
        origin,
        origin_place_name: options.fallbackOriginPlaceName || (origin ? t('mapLinkOrigin') : null),
        count: 1,
        message: t('loadedFromLink'),
        results: [facility],
      })
      setSelectedFacilityUid(facility.facility_uid)
      setSelectedFacilityRecord(data.record || null)
      setDetailRevealRequest((current) => current + 1)
    } catch (facilityError) {
      setResponse(null)
      setSelectedFacilityUid(null)
      setSelectedFacilityRecord(null)
      setError(
        facilityError.message === t('unusableCoordinates')
          ? facilityError.message
          : t('facilityLinkFailed'),
      )
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
      <section className="filter-bar" aria-label={t('facilitySearchFilters')}>
        <div className="brand-block">
          <div>
            <p className="eyebrow">AccessFirst GIS</p>
            <h1>{t('facilityFinder')}</h1>
          </div>
          <label className="language-selector">
            <span>{t('interfaceLanguage')}</span>
            <select value={uiLanguage} onChange={handleLanguageChange}>
              {LANGUAGE_OPTIONS.map((option) => (
                <option value={option.value} key={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
        </div>
        <details
          className="search-panel"
          open={isSearchOpen}
          onToggle={(event) => setIsSearchOpen(event.currentTarget.open)}
        >
          <summary aria-label={t('searchFilters')}>{t('searchFilters')}</summary>
          <form className="search-form" onSubmit={handleSubmit}>
            <div className="primary-fields">
              <label className="field field-location">
                <span>{t('location')}</span>
                <input
                  value={filters.location}
                  onChange={(event) => updateFilter('location', event.target.value)}
                  placeholder={t('locationPlaceholder')}
                  autoComplete="street-address"
                />
              </label>
              <label className="field">
                <span>{t('serviceType')}</span>
                <input
                  value={filters.service_type}
                  onChange={(event) => updateFilter('service_type', event.target.value)}
                  placeholder={t('servicePlaceholder')}
                />
              </label>
              <label className="field">
                <span>{t('language')}</span>
                <input
                  value={filters.language}
                  onChange={(event) => updateFilter('language', event.target.value)}
                  placeholder={t('languagePlaceholder')}
                />
              </label>
              <label className="field">
                <span>{t('accessibility')}</span>
                <input
                  value={filters.accessibility_need}
                  onChange={(event) => updateFilter('accessibility_need', event.target.value)}
                  placeholder={t('accessibilityPlaceholder')}
                />
              </label>
              <label className="field select-field">
                <span>{t('telehealth')}</span>
                <select
                  value={filters.telehealth === null || filters.telehealth === undefined ? 'any' : String(filters.telehealth)}
                  onChange={(event) => {
                    const value = event.target.value
                    updateFilter('telehealth', value === 'any' ? null : value === 'true')
                  }}
                >
                  <option value="any">{t('any')}</option>
                  <option value="false">{t('inPerson')}</option>
                  <option value="true">{t('telehealth')}</option>
                </select>
              </label>
              <label className="field compact">
                <span>{t('radius')}</span>
                <input
                  type="number"
                  min="1"
                  max="100"
                  value={filters.radius_miles}
                  onChange={(event) => updateFilter('radius_miles', Number(event.target.value))}
                />
              </label>
              <label className="field compact">
                <span>{t('limit')}</span>
                <input
                  type="number"
                  min="1"
                  max="100"
                  value={filters.limit}
                  onChange={(event) => updateFilter('limit', Number(event.target.value))}
                />
              </label>
              <div className="form-actions">
                <button className="primary-button" type="submit" disabled={isLoading}>
                  {isLoading ? t('searching') : t('search')}
                </button>
                <button className="secondary-button" type="button" onClick={clearFilters}>
                  {t('clearFilters')}
                </button>
              </div>
            </div>

            <fieldset className="advanced-filters">
              <legend>{t('dataQualityFilters')}</legend>
              <p>{t('verifiedDefault')}</p>
              <div className="advanced-toggle-grid">
                <label>
                  <input
                    type="checkbox"
                    checked={filters.include_warning_results}
                    onChange={(event) => updateFilter('include_warning_results', event.target.checked)}
                  />
                  {t('includeWarnings')}
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={filters.include_manual_review}
                    onChange={(event) => updateFilter('include_manual_review', event.target.checked)}
                  />
                  {t('includeManualReview')}
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={filters.include_outside_la_county}
                    onChange={(event) => updateFilter('include_outside_la_county', event.target.checked)}
                  />
                  {t('includeOutside')}
                </label>
              </div>
            </fieldset>
          </form>
        </details>
      </section>

      <section className="workspace">
        <aside className="results-panel" aria-label={t('rankedResults')}>
          <div className="panel-header">
            <div>
              <h2>{t('results')}</h2>
              <p>{resultSummary(response, isLoading, error, t)}</p>
            </div>
          </div>
          {isLoading && <LoadingState t={t} />}
          {!isLoading && error && <NoticeState title={t('searchAttention')} message={error} />}
          {!isLoading && !error && !response && (
            <NoticeState title={t('startLocation')} message={t('startLocationMessage')} />
          )}
          {!isLoading && response && results.length === 0 && (
            <NoticeState title={t('noMatches')} message={t('noMatchesMessage')} />
          )}
          <div className="facility-list">
            {results.map((facility, index) => (
              <FacilityCard
                key={facility.facility_uid}
                facility={facility}
                rank={index + 1}
                isSelected={facility.facility_uid === selectedFacility?.facility_uid}
                onSelect={() => handleFacilitySelect(facility.facility_uid)}
                t={t}
              />
            ))}
          </div>
        </aside>

        <section className="map-region" aria-label={t('map')}>
          <div className="map-container" ref={mapContainerRef}>
            {!mapboxgl.accessToken && (
              <div className="map-overlay">
                <strong>{t('mapTokenMissing')}</strong>
                <span>{t('mapTokenInstruction')}</span>
              </div>
            )}
          </div>
          <p className="map-instruction" role="note">{t('mapInstruction')}</p>
          {selectedFacility && (
            <button
              className="view-details-button"
              type="button"
              onClick={() => handleFacilitySelect(selectedFacility.facility_uid)}
            >
              {t('viewDetails')}
            </button>
          )}
        </section>
        <DetailPanel
          detailRef={detailPanelRef}
          facility={selectedFacility}
          origin={response?.origin_place_name}
          providerRecord={selectedFacilityRecord}
          isDetailLoading={isDetailLoading}
          detailError={detailError}
          t={t}
        />
      </section>
    </main>
  )
}

function FacilityCard({ facility, rank, isSelected, onSelect, t }) {
  const cardServices = facility.services?.slice(0, 2) || []
  const cardLanguages = facility.languages?.slice(0, 2) || []

  return (
    <button
      className={`facility-card ${isSelected ? 'selected' : ''}`}
      type="button"
      onClick={onSelect}
      aria-label={t('selectFacility', {
        name: facility.facility_name || facility.provider_display_name,
      })}
    >
      <span className="rank-marker">{rank}</span>
      <span className="card-main">
        <span className="facility-name">{facility.facility_name || facility.provider_display_name}</span>
        <span className="facility-distance">{formatDistance(facility.distance_miles, t)}</span>
        <span className="facility-meta">{facility.address || `${facility.city || ''} ${facility.zip_code || ''}`}</span>
        <span className="facility-meta">{facility.phone || t('phoneNotListed')}</span>
        <span className="facility-meta">
          {cardServices.length ? cardServices.join(', ') : facility.care_setting || t('servicesNotListed')}
        </span>
        <span className="badge-row">
          <span className={`badge ${mapStatusClass(facility)}`}>{mapStatusLabel(facility, t)}</span>
          {facility.ada_facility === 'yes' && <span className="badge success">ADA</span>}
          {cardLanguages.map((language) => (
            <span className="badge neutral" key={language}>{language}</span>
          ))}
        </span>
      </span>
    </button>
  )
}

function DetailPanel({
  detailRef,
  facility,
  origin,
  providerRecord,
  isDetailLoading,
  detailError,
  t,
}) {
  if (!facility) {
    return (
      <aside
        className="detail-panel empty"
        aria-label={t('facilityDetails')}
        ref={detailRef}
        tabIndex="-1"
      >
        <h2>{t('facilityDetails')}</h2>
        <p>{t('facilityDetailsEmpty')}</p>
      </aside>
    )
  }

  const services = sourceList(providerRecord?.services)
  const deliveryMethods = sourceList(providerRecord?.methods_of_delivery)
  const careSetting = textValue(providerRecord?.care_setting)
  const focusAreas = sourceList(providerRecord?.practice_focus_terms)
  const disciplines = sourceList(providerRecord?.practitioner_disciplines)
  const practitioners = practitionerList(providerRecord)
  const practitionerCount = practitionerCountValue(providerRecord)
  const detailIsLoading = isDetailLoading && !providerRecord

  return (
    <aside
      className="detail-panel"
      aria-label={t('facilityDetails')}
      ref={detailRef}
      tabIndex="-1"
    >
      <div className="detail-heading">
        <div>
          <p className="eyebrow">{facility.service_area || t('serviceAreaNotListed')}</p>
          <h2>{facility.facility_name || facility.provider_display_name}</h2>
        </div>
        <span className={`badge ${mapStatusClass(facility)}`}>{mapStatusLabel(facility, t)}</span>
      </div>
      <p className="distance-line">{distanceFromText(facility.distance_miles, origin, t)}</p>

      <div className="detail-sections">
        <section>
          <h3>{t('contact')}</h3>
          <dl className="detail-grid">
            <div>
              <dt>{t('address')}</dt>
              <dd>{facility.address || t('notListed')}</dd>
            </div>
            <div>
              <dt>{t('phone')}</dt>
              <dd>{facility.phone || t('notListed')}</dd>
            </div>
            <div>
              <dt>{t('hours')}</dt>
              <dd>{facility.hours || t('notListed')}</dd>
            </div>
          </dl>
        </section>

        <section>
          <h3>{t('services')}</h3>
          <SourceList values={services} isLoading={detailIsLoading} error={detailError} t={t} />
        </section>

        <section>
          <h3>{t('deliveryMethods')}</h3>
          <SourceList values={deliveryMethods} isLoading={detailIsLoading} error={detailError} t={t} />
        </section>

        <section>
          <h3>{t('careSetting')}</h3>
          <SourceText value={careSetting} isLoading={detailIsLoading} error={detailError} t={t} />
        </section>

        <section className="split-section">
          <div>
            <h3>{t('languages')}</h3>
            <p>{listText(facility.languages, t)}</p>
          </div>
          <div>
            <h3>{t('accessibility')}</h3>
            <p>{facility.ada_facility === 'yes' ? t('adaListed') : facility.ada_facility || t('notListed')}</p>
          </div>
        </section>

        <section>
          <h3>{t('focusAreas')}</h3>
          <SourceList values={focusAreas} isLoading={detailIsLoading} error={detailError} t={t} />
        </section>

        <section>
          <h3>{t('providerDisciplines')}</h3>
          <SourceList values={disciplines} isLoading={detailIsLoading} error={detailError} t={t} />
        </section>

        <PractitionerSection
          practitioners={practitioners}
          practitionerCount={practitionerCount}
          isLoading={detailIsLoading}
          error={detailError}
          t={t}
        />

        <section>
          <h3>{t('locationQuality')}</h3>
          <p>{mapStatusLabel(facility, t)}</p>
          <p className="muted-text">{facility.map_inclusion_reason || t('reviewedLocation')}</p>
        </section>

        <section className="directions-box">
          <h3>{t('openDirections')}</h3>
          <p>{t('directionsHelp')}</p>
          <a
            className="directions-link"
            href={directionsHref(facility)}
            target="_blank"
            rel="noreferrer"
            aria-label={t('directionsTo', {
              name: facility.facility_name || t('selectedFacility'),
            })}
          >
            {t('openDirections')}
          </a>
        </section>

        <section>
          <h3>{t('coverageNote')}</h3>
          <p className="insurance-note">
            {insuranceStatusText(facility, t)}
          </p>
        </section>
      </div>
    </aside>
  )
}

function SourceText({ value, isLoading, error, t }) {
  if (isLoading) {
    return <p className="muted-text">{t('loadingSource')}</p>
  }
  if (error) {
    return <p className="muted-text">{t('sourceLoadFailed')}</p>
  }
  if (!value) {
    return <p className="muted-text">{t('sourceNotListed')}</p>
  }
  return <p>{value}</p>
}

function SourceList({ values, isLoading, error, t }) {
  if (isLoading) {
    return <p className="muted-text">{t('loadingSource')}</p>
  }
  if (error) {
    return <p className="muted-text">{t('sourceLoadFailed')}</p>
  }
  if (!values.length) {
    return <p className="muted-text">{t('sourceNotListed')}</p>
  }
  return (
    <div className="chip-list" aria-label={t('sourceValues')}>
      {values.map((value) => (
        <span className="chip" key={value}>{value}</span>
      ))}
    </div>
  )
}

function PractitionerSection({ practitioners, practitionerCount, isLoading, error, t }) {
  const hasLongList = practitioners.length > 5

  return (
    <section>
      <h3>{t('practitioners')}</h3>
      <p className="source-note">{t('practitionerNotice')}</p>
      {isLoading && <p className="muted-text">{t('loadingSource')}</p>}
      {!isLoading && error && <p className="muted-text">{t('sourceLoadFailed')}</p>}
      {!isLoading && !error && !practitioners.length && (
        <p className="muted-text">
          {practitionerCount
            ? t('practitionerCountOnly', { count: practitionerCount })
            : t('sourceNotListed')}
        </p>
      )}
      {!isLoading && !error && practitioners.length > 0 && hasLongList && (
        <details className="practitioner-accordion">
          <summary aria-label={t('showPractitioners', { count: practitioners.length })}>
            {t('showPractitioners', { count: practitioners.length })}
          </summary>
          <PractitionerList practitioners={practitioners} t={t} />
        </details>
      )}
      {!isLoading && !error && practitioners.length > 0 && !hasLongList && (
        <PractitionerList practitioners={practitioners} isStandalone t={t} />
      )}
    </section>
  )
}

function PractitionerList({ practitioners, isStandalone = false, t }) {
  return (
    <div className={`practitioner-list ${isStandalone ? 'standalone' : ''}`}>
      {practitioners.map((practitioner, index) => (
        <article className="practitioner-card" key={`${practitioner.practitioner_name || 'practitioner'}-${index}`}>
          {practitioner.practitioner_name && (
            <h4>{practitioner.practitioner_name}</h4>
          )}
          <dl>
            {practitioner.discipline && (
              <div>
                <dt>{t('discipline')}</dt>
                <dd>{practitioner.discipline}</dd>
              </div>
            )}
            {practitioner.practice_focus && (
              <div>
                <dt>{t('practiceFocus')}</dt>
                <dd>{practitioner.practice_focus}</dd>
              </div>
            )}
            {practitioner.npi_number && (
              <div>
                <dt>NPI</dt>
                <dd>{practitioner.npi_number}</dd>
              </div>
            )}
            {practitioner.ca_license && (
              <div>
                <dt>{t('caLicense')}</dt>
                <dd>{practitioner.ca_license}</dd>
              </div>
            )}
          </dl>
        </article>
      ))}
    </div>
  )
}

function LoadingState({ t }) {
  return (
    <div className="state-block" role="status">
      <span className="spinner" aria-hidden="true" />
      <strong>{t('searchingNearby')}</strong>
      <p>{t('searchingNearbyMessage')}</p>
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

function mapStatusLabel(facility, t) {
  if (facility.geography_status === 'outside_la_county') {
    return t('outsideCounty')
  }
  if (
    facility.map_inclusion_status === 'include_with_warning'
    || facility.geocode_quality_status === 'verified_city_or_zip_mismatch'
    || facility.geocode_quality_status === 'needs_review_address'
  ) {
    return t('needsConfirmation')
  }
  return t('verifiedLocation')
}

function mapStatusClass(facility) {
  if (facility.geography_status === 'outside_la_county') {
    return 'warning'
  }
  if (
    facility.map_inclusion_status === 'include_with_warning'
    || facility.geocode_quality_status === 'verified_city_or_zip_mismatch'
    || facility.geocode_quality_status === 'needs_review_address'
  ) {
    return 'warning'
  }
  return 'success'
}

function distanceFromText(distanceMiles, origin, t) {
  const distance = formatDistance(distanceMiles, t)
  if (!Number.isFinite(Number(distanceMiles))) {
    return distance
  }
  if (origin) {
    return t('distanceFrom', { distance, origin })
  }
  return t('distanceFromSearch', { distance })
}

function directionsHref(facility) {
  return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(
    `${facility.latitude},${facility.longitude}`,
  )}`
}

function insuranceStatusText(facility, t) {
  if (String(facility.insurance_acceptance_verified || '').toLowerCase() === 'yes') {
    return t('insuranceVerified')
  }
  return t('insuranceUnverified')
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

function formatDistance(distanceMiles, t) {
  const distance = Number(distanceMiles)
  if (!Number.isFinite(distance)) {
    return t('distanceNotCalculated')
  }
  return t('miles', { distance })
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

function renderMapResults({
  map,
  results,
  origin,
  selectedFacilityUid,
  markersRef,
  originMarkerRef,
  mapBoundsKeyRef,
  onSelect,
  t,
}) {
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
    originElement.setAttribute('aria-label', t('searchOrigin'))
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
    element.setAttribute('aria-label', t('selectResult', {
      name: facility.facility_name || facility.provider_display_name || t('selectedFacility'),
      rank: index + 1,
    }))
    element.addEventListener('click', () => onSelect(facility.facility_uid))

    const marker = new mapboxgl.Marker({ element })
      .setLngLat([facility.longitude, facility.latitude])
      .addTo(map)
    element.setAttribute('role', 'button')
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

  const boundsKey = JSON.stringify({
    origin: origin ? [origin.longitude, origin.latitude] : null,
    results: results.map((facility) => [
      facility.facility_uid,
      facility.longitude,
      facility.latitude,
    ]),
  })
  if (!bounds.isEmpty() && boundsKey !== mapBoundsKeyRef.current) {
    mapBoundsKeyRef.current = boundsKey
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    map.fitBounds(bounds, {
      padding: 84,
      maxZoom: 13,
      duration: prefersReducedMotion ? 0 : 700,
    })
  }
}

function resultSummary(response, isLoading, error, t) {
  if (isLoading) return t('loading')
  if (error) return t('unableSearch')
  if (!response) return t('awaitingSearch')
  return t('facilitiesRanked', { count: response.count })
}

function sourceList(value) {
  const values = Array.isArray(value)
    ? value
    : typeof value === 'string'
      ? value.split(/[;|]/)
      : []
  return Array.from(new Set(
    values
      .map((item) => String(item || '').trim())
      .filter(Boolean),
  ))
}

function textValue(value) {
  const text = String(value || '').trim()
  return text || null
}

function practitionerCountValue(record) {
  if (!record) return null
  const parsedCount = Number(record.practitioner_count)
  if (Number.isFinite(parsedCount) && parsedCount >= 0) {
    return parsedCount
  }
  if (Array.isArray(record.practitioners)) {
    return record.practitioners.length
  }
  const names = sourceList(record.practitioner_names)
  return names.length || null
}

function practitionerList(record) {
  if (!record) return []

  if (Array.isArray(record.practitioners) && record.practitioners.length) {
    return record.practitioners
      .map((practitioner) => cleanPractitioner({
        practitioner_name: practitioner.practitioner_name,
        discipline: practitioner.discipline,
        practice_focus: sourceList(practitioner.practice_focus).join(', ') || practitioner.practice_focus,
        npi_number: practitioner.npi_number,
        ca_license: practitioner.ca_license,
      }))
      .filter((practitioner) => Object.values(practitioner).some(Boolean))
  }

  const names = sourceList(record.practitioner_names)
  const npiNumbers = sourceList(record.npi_numbers)
  const caLicenses = sourceList(record.ca_licenses)
  const disciplines = sourceList(record.practitioner_disciplines)

  return names
    .map((name, index) => cleanPractitioner({
      practitioner_name: name,
      discipline: disciplines.length === 1 ? disciplines[0] : '',
      npi_number: npiNumbers[index],
      ca_license: caLicenses[index],
    }))
    .filter((practitioner) => Object.values(practitioner).some(Boolean))
}

function cleanPractitioner(practitioner) {
  return Object.fromEntries(
    Object.entries(practitioner).map(([key, value]) => [key, String(value || '').trim()]),
  )
}

function listText(values, t) {
  return values?.length ? values.join(', ') : t('notListed')
}
