import React, { useEffect, useMemo, useState, useCallback } from 'react'
import { MapContainer, TileLayer, Marker, Popup, Polyline, CircleMarker, Circle, useMap, useMapEvents, Tooltip as LeafletTooltip } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

// Fix for default markers in Leaflet with Webpack
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: require('leaflet/dist/images/marker-icon-2x.png'),
  iconUrl: require('leaflet/dist/images/marker-icon.png'),
  shadowUrl: require('leaflet/dist/images/marker-shadow.png'),
})

// Small dot icon for site location
const createDotIcon = (color, size = 10) => {
  return L.divIcon({
    className: 'custom-dot-marker',
    html: `
      <div style="
        background-color: ${color};
        width: ${size}px;
        height: ${size}px;
        border-radius: 50%;
        border: 2px solid white;
        box-shadow: 0 1px 4px rgba(0,0,0,0.4);
      "></div>
    `,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -(size / 2 + 3)],
  })
}

// Default color palette for known roles (fallback when no siteTypeColors prop)
const DEFAULT_ROLE_COLORS = {
  retailer: '#10b981',
  wholesaler: '#3b82f6',
  distributor: '#8b5cf6',
  factory: '#ef4444',
  manufacturer: '#ef4444',
  supplier: '#f59e0b',
  vendor: '#f59e0b',
  market_supply: '#f59e0b',
  customer: '#10b981',
  customer: '#10b981',
  inventory: '#0ea5e9',
  cdc: '#6366f1',
  rdc: '#14b8a6',
  dc: '#0ea5e9',
}

// Lead time color scale (same as Sankey: green → orange → red)
const LEAD_COLOR_MIN = '#16a34a'
const LEAD_COLOR_MEDIAN = '#f97316'
const LEAD_COLOR_MAX = '#dc2626'

const hexToRgb = (hex) => {
  if (typeof hex !== 'string') return null
  let n = hex.trim().replace('#', '')
  if (n.length === 3) n = n.split('').map((c) => c + c).join('')
  if (n.length !== 6) return null
  const v = parseInt(n, 16)
  if (isNaN(v)) return null
  return { r: (v >> 16) & 255, g: (v >> 8) & 255, b: v & 255 }
}

const interpolateHex = (c1, c2, t) => {
  const a = hexToRgb(c1)
  const b = hexToRgb(c2)
  if (!a || !b) return c1
  const cl = Math.max(0, Math.min(1, t))
  const r = Math.round(a.r + (b.r - a.r) * cl)
  const g = Math.round(a.g + (b.g - a.g) * cl)
  const bl = Math.round(a.b + (b.b - a.b) * cl)
  return `rgb(${r}, ${g}, ${bl})`
}

const resolveLeadTimeColor = (leadTime, stats) => {
  if (!stats || !Number.isFinite(leadTime)) return '#94a3b8' // slate-400 fallback
  const { min, median, max } = stats
  if (!Number.isFinite(min) || !Number.isFinite(median) || !Number.isFinite(max)) return '#94a3b8'
  if (max - min <= 0) return LEAD_COLOR_MIN
  if (leadTime <= median) {
    const range = Math.max(median - min, 1e-9)
    return interpolateHex(LEAD_COLOR_MIN, LEAD_COLOR_MEDIAN, (leadTime - min) / range)
  }
  const range = Math.max(max - median, 1e-9)
  return interpolateHex(LEAD_COLOR_MEDIAN, LEAD_COLOR_MAX, Math.min((leadTime - median) / range, 1))
}

const getRoleColor = (role, siteTypeColors, site) => {
  // Resolve role from multiple sources: role → type → master_type
  const effectiveRole = role || (site && (site.type || site.master_type)) || null
  if (!effectiveRole) return '#6b7280'
  const key = effectiveRole.toLowerCase().replace(/[\s-]+/g, '_')
  if (siteTypeColors && siteTypeColors[key]) return siteTypeColors[key]
  return DEFAULT_ROLE_COLORS[key] || '#6b7280'
}

// Map controller for auto-fitting bounds
const MapController = ({ sites }) => {
  const map = useMap()

  useEffect(() => {
    if (sites && sites.length > 0) {
      const bounds = sites
        .filter((site) => site.latitude && site.longitude)
        .map((site) => [site.latitude, site.longitude])

      if (bounds.length > 0) {
        map.fitBounds(bounds, { padding: [50, 50] })
      }
    }
  }, [sites, map])

  return null
}

// Zoom level tracker
const ZoomTracker = ({ onZoomChange }) => {
  const map = useMapEvents({
    zoomend: () => {
      onZoomChange(map.getZoom())
    },
  })

  useEffect(() => {
    onZoomChange(map.getZoom())
  }, [map, onZoomChange])

  return null
}

const formatRoleLabel = (role) =>
  String(role || '')
    .replace(/_/g, ' ')
    .replace(/\b([a-z])/gi, (m) => m.toUpperCase())

// ---------------------------------------------------------------------------
// Semantic zoom: aggregate/disaggregate market sites by zoom level
// ---------------------------------------------------------------------------

// Continent centroid approximations for aggregated markers
const CONTINENT_CENTROIDS = {
  'Africa': { lat: 2.0, lng: 22.0 },
  'Americas': { lat: 15.0, lng: -80.0 },
  'Asia': { lat: 35.0, lng: 85.0 },
  'Europe': { lat: 50.0, lng: 15.0 },
  'Oceania': { lat: -25.0, lng: 140.0 },
  'Other': { lat: 0, lng: 0 },
}

/**
 * Build zoom-aware site and edge lists.
 *
 * - zoom <= AGGREGATE_ZOOM: Market sites are clustered by continent.
 *   Multiple SUPPLY_{region} or DEMAND_{region} sites that share the same
 *   continent attribute merge into a single aggregated marker.
 * - zoom > AGGREGATE_ZOOM: All sites shown individually (current behavior).
 *
 * Plants / manufacturers / inventory sites are always shown at every zoom.
 */
const AGGREGATE_ZOOM = 4

function buildSemanticView(allSites, allEdges, currentZoom) {
  // If zoomed in enough, show everything as-is
  if (currentZoom > AGGREGATE_ZOOM) {
    return { sites: allSites, edges: allEdges }
  }

  // Separate market sites from non-market sites
  const nonMarket = []
  const supplyByContinent = {}
  const demandByContinent = {}

  allSites.forEach((site) => {
    const mt = (site.master_type || '').toLowerCase()
    if (mt === 'vendor' || mt === 'customer') {
      const continent = site.attributes?.continent
        || site.attributes?.region  // fallback: region key may be continent name
        || 'Other'
      const bucket = mt === 'vendor' ? supplyByContinent : demandByContinent
      if (!bucket[continent]) {
        bucket[continent] = { sites: [], totalCount: 0, countries: new Set() }
      }
      bucket[continent].sites.push(site)
      bucket[continent].totalCount += (site.attributes?.vendor_count || site.attributes?.customer_count || 1)
      ;(site.attributes?.countries || []).forEach((c) => bucket[continent].countries.add(c))
    } else {
      nonMarket.push(site)
    }
  })

  // Build aggregated market sites
  const aggregatedSites = [...nonMarket]
  const siteIdMap = {} // old site id → aggregated site id

  const buildAgg = (bucket, prefix, role) => {
    Object.entries(bucket).forEach(([continent, info]) => {
      if (info.sites.length === 0) return

      // If only one site in the continent, keep it as-is
      if (info.sites.length === 1) {
        aggregatedSites.push(info.sites[0])
        return
      }

      // Compute centroid from child sites that have coords, else use continent default
      const withCoords = info.sites.filter((s) => s.latitude && s.longitude)
      let lat, lng
      if (withCoords.length > 0) {
        lat = withCoords.reduce((sum, s) => sum + s.latitude, 0) / withCoords.length
        lng = withCoords.reduce((sum, s) => sum + s.longitude, 0) / withCoords.length
      } else {
        const c = CONTINENT_CENTROIDS[continent] || CONTINENT_CENTROIDS.Other
        lat = c.lat
        lng = c.lng
      }

      const aggId = `${prefix}_${continent.toUpperCase().replace(/\s+/g, '_')}_AGG`
      const aggSite = {
        id: aggId,
        name: `${continent}`,
        role,
        master_type: role === 'Suppliers' ? 'vendor' : 'customer',
        latitude: lat,
        longitude: lng,
        capacity: 0,
        location: `${info.sites.length} regions, ${info.totalCount} partners`,
        attributes: {
          aggregated: true,
          child_count: info.sites.length,
          total_partners: info.totalCount,
          countries: Array.from(info.countries).sort(),
          continent,
        },
      }
      aggregatedSites.push(aggSite)

      // Map child site IDs to aggregated ID for edge remapping
      info.sites.forEach((s) => {
        siteIdMap[s.id] = aggId
      })
    })
  }

  buildAgg(supplyByContinent, 'SUPPLY', 'Suppliers')
  buildAgg(demandByContinent, 'DEMAND', 'Customers')

  // Remap edges: replace child site IDs with aggregated IDs, dedup
  const seenEdges = new Set()
  const aggregatedEdges = []
  allEdges.forEach((edge) => {
    const from = siteIdMap[edge.from] || edge.from
    const to = siteIdMap[edge.to] || edge.to
    const key = `${from}->${to}`
    if (seenEdges.has(key)) return
    seenEdges.add(key)
    aggregatedEdges.push({ ...edge, from, to })
  })

  return { sites: aggregatedSites, edges: aggregatedEdges }
}

// ---------------------------------------------------------------------------

const GeospatialSupplyChain = ({ sites, edges, inventoryData, activeFlows, onSiteSelect, siteTypeColors, leadTimeStats }) => {
  const [selectedSite, setSelectedSite] = useState(null)
  const [mapCenter, setMapCenter] = useState([39.8283, -98.5795])
  const [mapZoom, setMapZoom] = useState(4)
  const [currentZoom, setCurrentZoom] = useState(4)
  const [showSizeCircles, setShowSizeCircles] = useState(true)
  const [showLaneVolume, setShowLaneVolume] = useState(true)

  const handleZoomChange = useCallback((z) => setCurrentZoom(z), [])

  // Build zoom-aware view
  const { sites: visibleSites, edges: visibleEdges } = useMemo(
    () => buildSemanticView(sites, edges, currentZoom),
    [sites, edges, currentZoom]
  )

  const sitesWithCoords = visibleSites.filter((site) => site.latitude && site.longitude)

  // Compute capacity stats for scaling circles
  const capacityStats = useMemo(() => {
    const caps = sitesWithCoords.map((s) => s.capacity ?? 0).filter((c) => c > 0)
    if (caps.length === 0) return { max: 1, min: 0 }
    return { max: Math.max(...caps), min: Math.min(...caps) }
  }, [sitesWithCoords])

  // Compute lane capacity stats for scaling widths
  const laneCapStats = useMemo(() => {
    const caps = (visibleEdges || []).map((e) => e.capacity ?? 0).filter((c) => c > 0)
    if (caps.length === 0) return { max: 1 }
    return { max: Math.max(...caps) }
  }, [visibleEdges])

  // Compute lead time stats from edges if not passed in
  const effectiveLeadTimeStats = useMemo(() => {
    if (leadTimeStats) return leadTimeStats
    const lts = (visibleEdges || []).map((e) => e.leadTime).filter((v) => Number.isFinite(v))
    if (lts.length === 0) return null
    const sorted = [...lts].sort((a, b) => a - b)
    const mid = Math.floor(sorted.length / 2)
    const median = sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid]
    return { min: sorted[0], median, max: sorted[sorted.length - 1] }
  }, [visibleEdges, leadTimeStats])

  // Prepare edges with coordinates
  const edgesWithCoords = useMemo(() => {
    return visibleEdges
      .map((edge) => {
        const fromSite = visibleSites.find((n) => n.id === edge.from)
        const toSite = visibleSites.find((n) => n.id === edge.to)

        if (
          fromSite?.latitude &&
          fromSite?.longitude &&
          toSite?.latitude &&
          toSite?.longitude
        ) {
          return {
            ...edge,
            positions: [
              [fromSite.latitude, fromSite.longitude],
              [toSite.latitude, toSite.longitude],
            ],
          }
        }
        return null
      })
      .filter(Boolean)
  }, [visibleEdges, visibleSites])

  const handleSiteClick = (site) => {
    setSelectedSite(site)
    setMapCenter([site.latitude, site.longitude])
    // If clicking an aggregated site, zoom to detail level
    if (site.attributes?.aggregated) {
      setMapZoom(AGGREGATE_ZOOM + 2)
    } else {
      setMapZoom(8)
    }
    if (onSiteSelect) {
      onSiteSelect(site)
    }
  }

  // Scale site capacity to a pixel radius (8-40px range)
  const getSizeRadius = (capacity) => {
    if (!capacity || capacity <= 0 || capacityStats.max <= 0) return 8
    const ratio = capacity / capacityStats.max
    return 8 + Math.sqrt(ratio) * 32
  }

  // Scale lane capacity to pixel weight (2-14px range)
  const getLaneWeight = (capacity) => {
    if (!capacity || capacity <= 0 || laneCapStats.max <= 0) return 2
    const ratio = capacity / laneCapStats.max
    return 2 + ratio * 12
  }

  // Determine zoom level label
  const zoomLabel = currentZoom <= AGGREGATE_ZOOM ? 'Continent' : currentZoom <= 7 ? 'Region' : 'Site'

  return (
    <div className="w-full h-full relative">
      {/* Controls */}
      <div className="absolute top-4 right-4 z-[1000] bg-white rounded-lg shadow-lg p-4 space-y-2">
        <div className="text-sm font-medium mb-2">Map Controls</div>
        <label className="flex items-center text-sm">
          <input
            type="checkbox"
            checked={showSizeCircles}
            onChange={(e) => setShowSizeCircles(e.target.checked)}
            className="mr-2"
          />
          Show Site Size
        </label>
        <label className="flex items-center text-sm">
          <input
            type="checkbox"
            checked={showLaneVolume}
            onChange={(e) => setShowLaneVolume(e.target.checked)}
            className="mr-2"
          />
          Show Lane Volume
        </label>
        <button
          onClick={() => {
            setMapCenter([39.8283, -98.5795])
            setMapZoom(4)
          }}
          className="w-full px-3 py-1 text-sm bg-gray-200 hover:bg-gray-300 rounded"
        >
          Reset View
        </button>
        {/* Zoom level indicator */}
        <div className="border-t border-gray-200 pt-2 mt-2">
          <div className="text-xs text-gray-500">
            Detail: <span className="font-medium text-gray-700">{zoomLabel}</span>
          </div>
          <div className="text-[10px] text-gray-400 mt-0.5">
            Zoom {currentZoom <= AGGREGATE_ZOOM ? 'in' : 'out'} to {currentZoom <= AGGREGATE_ZOOM ? 'expand regions' : 'aggregate'}
          </div>
        </div>
      </div>

      {/* Legend */}
      {(() => {
        const roleSet = new Map()
        sitesWithCoords.forEach((site) => {
          const role = site.role || site.type || site.master_type
          if (!role) return
          const key = role.toLowerCase().replace(/[\s-]+/g, '_')
          if (!roleSet.has(key)) {
            roleSet.set(key, { key, label: formatRoleLabel(role), color: getRoleColor(role, siteTypeColors, site) })
          }
        })
        const entries = Array.from(roleSet.values())
        if (entries.length === 0) return null
        return (
          <div className="absolute bottom-4 left-4 z-[1000] bg-white rounded-lg shadow-lg p-4">
            <div className="text-sm font-medium mb-2">Legend</div>
            <div className="space-y-1 text-xs">
              {entries.map((entry) => (
                <div key={entry.key} className="flex items-center">
                  <div
                    className="w-3 h-3 rounded-full mr-2"
                    style={{ backgroundColor: entry.color }}
                  ></div>
                  <span>{entry.label}</span>
                </div>
              ))}
              <div className="border-t border-gray-200 my-1 pt-1">
                <div className="flex items-center">
                  <div className="w-3 h-3 rounded-full mr-2 border border-gray-300"
                    style={{ backgroundColor: 'rgba(59,130,246,0.1)' }}
                  ></div>
                  <span>Circle = site capacity</span>
                </div>
              </div>
              <div className="border-t border-gray-200 my-1 pt-1">
                <div className="text-[10px] text-gray-500 mb-0.5">Lane color = lead time</div>
                <div className="flex items-center gap-0.5">
                  <div className="w-3 h-1.5 rounded-sm" style={{ backgroundColor: LEAD_COLOR_MIN }}></div>
                  <span className="text-[10px]">Short</span>
                  <div className="w-3 h-1.5 rounded-sm ml-1" style={{ backgroundColor: LEAD_COLOR_MEDIAN }}></div>
                  <span className="text-[10px]">Med</span>
                  <div className="w-3 h-1.5 rounded-sm ml-1" style={{ backgroundColor: LEAD_COLOR_MAX }}></div>
                  <span className="text-[10px]">Long</span>
                </div>
                <div className="text-[10px] text-gray-500 mt-0.5">Lane width = volume</div>
              </div>
            </div>
          </div>
        )
      })()}

      {/* Selected Site Info */}
      {selectedSite && (
        <div className="absolute bottom-4 left-48 z-[1000] bg-white rounded-lg shadow-lg p-4 max-w-xs">
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm font-medium">{selectedSite.name || formatRoleLabel(selectedSite.role)}</div>
            <button
              onClick={() => setSelectedSite(null)}
              className="text-gray-400 hover:text-gray-600 ml-2"
            >
              ✕
            </button>
          </div>
          {selectedSite.location && (
            <div className="text-xs text-gray-600 mb-2">{selectedSite.location}</div>
          )}
          <div className="text-xs space-y-1">
            <div className="flex justify-between">
              <span className="text-gray-600">Type:</span>
              <span className="font-medium">{formatRoleLabel(selectedSite.role)}</span>
            </div>
            {selectedSite.attributes?.aggregated && (
              <>
                <div className="flex justify-between">
                  <span className="text-gray-600">Regions:</span>
                  <span className="font-medium">{selectedSite.attributes.child_count}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Partners:</span>
                  <span className="font-medium">{selectedSite.attributes.total_partners?.toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Countries:</span>
                  <span className="font-medium">{selectedSite.attributes.countries?.length}</span>
                </div>
                <div className="text-[10px] text-blue-600 mt-1 cursor-pointer">
                  Click to zoom in and see individual regions
                </div>
              </>
            )}
            {!selectedSite.attributes?.aggregated && (
              <>
                {selectedSite.capacity > 0 && (
                  <div className="flex justify-between">
                    <span className="text-gray-600">Capacity:</span>
                    <span className="font-medium">{selectedSite.capacity.toLocaleString()}</span>
                  </div>
                )}
                {selectedSite.attributes?.vendor_count > 0 && (
                  <div className="flex justify-between">
                    <span className="text-gray-600">Vendors:</span>
                    <span className="font-medium">{selectedSite.attributes.vendor_count.toLocaleString()}</span>
                  </div>
                )}
                {selectedSite.attributes?.customer_count > 0 && (
                  <div className="flex justify-between">
                    <span className="text-gray-600">Customers:</span>
                    <span className="font-medium">{selectedSite.attributes.customer_count.toLocaleString()}</span>
                  </div>
                )}
                {selectedSite.attributes?.countries?.length > 0 && (
                  <div className="flex justify-between">
                    <span className="text-gray-600">Countries:</span>
                    <span className="font-medium text-xs">{selectedSite.attributes.countries.join(', ')}</span>
                  </div>
                )}
                {inventoryData?.[selectedSite.id] && (
                  <>
                    <div className="flex justify-between">
                      <span className="text-gray-600">Inventory:</span>
                      <span className="font-medium">{inventoryData[selectedSite.id].inventory}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">Backlog:</span>
                      <span className="font-medium text-red-600">{inventoryData[selectedSite.id].backlog}</span>
                    </div>
                  </>
                )}
              </>
            )}
            <div className="flex justify-between">
              <span className="text-gray-600">Coordinates:</span>
              <span className="text-gray-500 text-xs">
                {selectedSite.latitude?.toFixed(4)}, {selectedSite.longitude?.toFixed(4)}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Map */}
      <MapContainer
        center={mapCenter}
        zoom={mapZoom}
        style={{ width: '100%', height: '100%' }}
        className="z-0"
      >
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        />

        <MapController sites={sitesWithCoords} />
        <ZoomTracker onZoomChange={handleZoomChange} />

        {/* Lane lines — transparent volume width + lead time color */}
        {edgesWithCoords.map((edge, index) => {
          const color = resolveLeadTimeColor(edge.leadTime, effectiveLeadTimeStats)
          const weight = showLaneVolume ? getLaneWeight(edge.capacity) : 3

          return (
            <React.Fragment key={`lane-${edge.from}-${edge.to}-${index}`}>
              {/* Volume band (transparent, wide) */}
              {showLaneVolume && edge.capacity > 0 && (
                <Polyline
                  positions={edge.positions}
                  pathOptions={{
                    color,
                    weight: weight,
                    opacity: 0.18,
                    lineCap: 'round',
                  }}
                />
              )}
              {/* Core line (solid, thin) */}
              <Polyline
                positions={edge.positions}
                pathOptions={{
                  color,
                  weight: 2,
                  opacity: 0.7,
                  lineCap: 'round',
                }}
              />
            </React.Fragment>
          )
        })}

        {/* Site size circles (transparent halos) */}
        {showSizeCircles &&
          sitesWithCoords.map((site) => {
            const cap = site.capacity ?? 0
            if (cap <= 0 && !site.attributes?.aggregated) return null
            const color = getRoleColor(site.role, siteTypeColors, site)
            const radius = site.attributes?.aggregated
              ? 20 + Math.min(site.attributes.child_count * 5, 30)
              : getSizeRadius(cap)

            return (
              <CircleMarker
                key={`size-${site.id}`}
                center={[site.latitude, site.longitude]}
                radius={radius}
                pathOptions={{
                  color: color,
                  fillColor: color,
                  fillOpacity: site.attributes?.aggregated ? 0.2 : 0.12,
                  weight: site.attributes?.aggregated ? 2 : 1,
                  opacity: site.attributes?.aggregated ? 0.5 : 0.3,
                  dashArray: site.attributes?.aggregated ? '4 4' : undefined,
                }}
                interactive={false}
              />
            )
          })}

        {/* Site dot markers */}
        {sitesWithCoords.map((site) => {
          const color = getRoleColor(site.role, siteTypeColors, site)
          const isAgg = site.attributes?.aggregated
          const dotSize = isAgg ? 16 : 10
          const icon = createDotIcon(color, dotSize)

          const tooltipLabel = isAgg
            ? `${site.name} (${site.attributes.total_partners} partners)`
            : site.name

          return (
            <Marker
              key={site.id}
              position={[site.latitude, site.longitude]}
              icon={icon}
              eventHandlers={{
                click: () => handleSiteClick(site),
              }}
            >
              <LeafletTooltip direction="top" offset={[0, -(dotSize / 2 + 3)]} opacity={0.9}>
                <span className="text-xs font-medium">{tooltipLabel}</span>
              </LeafletTooltip>
              <Popup>
                <div className="text-sm">
                  <div className="font-bold mb-1">{site.name}</div>
                  <div className="text-xs text-gray-500 mb-1">{formatRoleLabel(site.role)}</div>
                  {isAgg && (
                    <div className="text-xs space-y-0.5">
                      <div>{site.attributes.child_count} regions, {site.attributes.total_partners} partners</div>
                      <div className="text-blue-600 mt-1">Click to zoom in</div>
                    </div>
                  )}
                  {!isAgg && (
                    <>
                      {site.location && <div className="text-xs text-gray-600 mb-2">{site.location}</div>}
                      {site.capacity > 0 && (
                        <div className="text-xs">Capacity: {site.capacity.toLocaleString()}</div>
                      )}
                      {site.attributes?.vendor_count > 0 && (
                        <div className="text-xs">Vendors: {site.attributes.vendor_count.toLocaleString()}</div>
                      )}
                      {site.attributes?.customer_count > 0 && (
                        <div className="text-xs">Customers: {site.attributes.customer_count.toLocaleString()}</div>
                      )}
                    </>
                  )}
                </div>
              </Popup>
            </Marker>
          )
        })}
      </MapContainer>
    </div>
  )
}

export default GeospatialSupplyChain
