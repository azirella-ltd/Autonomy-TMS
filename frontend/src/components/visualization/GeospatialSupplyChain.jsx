import React, { useEffect, useMemo, useState } from 'react'
import { MapContainer, TileLayer, Marker, Popup, Polyline, CircleMarker, Circle, useMap, Tooltip as LeafletTooltip } from 'react-leaflet'
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
const createDotIcon = (color) => {
  return L.divIcon({
    className: 'custom-dot-marker',
    html: `
      <div style="
        background-color: ${color};
        width: 10px;
        height: 10px;
        border-radius: 50%;
        border: 2px solid white;
        box-shadow: 0 1px 4px rgba(0,0,0,0.4);
      "></div>
    `,
    iconSize: [10, 10],
    iconAnchor: [5, 5],
    popupAnchor: [0, -8],
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
  market_supply: '#f59e0b',
  market_demand: '#10b981',
  inventory: '#0ea5e9',
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

const getRoleColor = (role, siteTypeColors) => {
  if (!role) return '#6b7280'
  const key = role.toLowerCase().replace(/[\s-]+/g, '_')
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

const formatRoleLabel = (role) =>
  String(role || '')
    .replace(/_/g, ' ')
    .replace(/\b([a-z])/gi, (m) => m.toUpperCase())

const GeospatialSupplyChain = ({ sites, edges, inventoryData, activeFlows, onSiteSelect, siteTypeColors, leadTimeStats }) => {
  const [selectedSite, setSelectedSite] = useState(null)
  const [mapCenter, setMapCenter] = useState([39.8283, -98.5795])
  const [mapZoom, setMapZoom] = useState(4)
  const [showSizeCircles, setShowSizeCircles] = useState(true)
  const [showLaneVolume, setShowLaneVolume] = useState(true)

  const sitesWithCoords = sites.filter((site) => site.latitude && site.longitude)

  // Compute capacity stats for scaling circles
  const capacityStats = useMemo(() => {
    const caps = sitesWithCoords.map((s) => s.capacity ?? 0).filter((c) => c > 0)
    if (caps.length === 0) return { max: 1, min: 0 }
    return { max: Math.max(...caps), min: Math.min(...caps) }
  }, [sitesWithCoords])

  // Compute lane capacity stats for scaling widths
  const laneCapStats = useMemo(() => {
    const caps = (edges || []).map((e) => e.capacity ?? 0).filter((c) => c > 0)
    if (caps.length === 0) return { max: 1 }
    return { max: Math.max(...caps) }
  }, [edges])

  // Compute lead time stats from edges if not passed in
  const effectiveLeadTimeStats = useMemo(() => {
    if (leadTimeStats) return leadTimeStats
    const lts = (edges || []).map((e) => e.leadTime).filter((v) => Number.isFinite(v))
    if (lts.length === 0) return null
    const sorted = [...lts].sort((a, b) => a - b)
    const mid = Math.floor(sorted.length / 2)
    const median = sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid]
    return { min: sorted[0], median, max: sorted[sorted.length - 1] }
  }, [edges, leadTimeStats])

  // Prepare edges with coordinates
  const edgesWithCoords = useMemo(() => {
    return edges
      .map((edge) => {
        const fromSite = sites.find((n) => n.id === edge.from)
        const toSite = sites.find((n) => n.id === edge.to)

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
  }, [edges, sites])

  const handleSiteClick = (site) => {
    setSelectedSite(site)
    setMapCenter([site.latitude, site.longitude])
    setMapZoom(8)
    if (onSiteSelect) {
      onSiteSelect(site)
    }
  }

  // Scale site capacity to a pixel radius (8–40px range)
  const getSizeRadius = (capacity) => {
    if (!capacity || capacity <= 0 || capacityStats.max <= 0) return 8
    const ratio = capacity / capacityStats.max
    return 8 + Math.sqrt(ratio) * 32
  }

  // Scale lane capacity to pixel weight (2–14px range)
  const getLaneWeight = (capacity) => {
    if (!capacity || capacity <= 0 || laneCapStats.max <= 0) return 2
    const ratio = capacity / laneCapStats.max
    return 2 + ratio * 12
  }

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
      </div>

      {/* Legend */}
      {(() => {
        const roleSet = new Map()
        sitesWithCoords.forEach((site) => {
          const role = site.role
          if (!role) return
          const key = role.toLowerCase().replace(/[\s-]+/g, '_')
          if (!roleSet.has(key)) {
            roleSet.set(key, { key, label: formatRoleLabel(role), color: getRoleColor(role, siteTypeColors) })
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
            {selectedSite.capacity > 0 && (
              <div className="flex justify-between">
                <span className="text-gray-600">Capacity:</span>
                <span className="font-medium">{selectedSite.capacity.toLocaleString()}</span>
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
            if (cap <= 0) return null
            const color = getRoleColor(site.role, siteTypeColors)
            const radius = getSizeRadius(cap)

            return (
              <CircleMarker
                key={`size-${site.id}`}
                center={[site.latitude, site.longitude]}
                radius={radius}
                pathOptions={{
                  color: color,
                  fillColor: color,
                  fillOpacity: 0.12,
                  weight: 1,
                  opacity: 0.3,
                }}
                interactive={false}
              />
            )
          })}

        {/* Site dot markers */}
        {sitesWithCoords.map((site) => {
          const color = getRoleColor(site.role, siteTypeColors)
          const icon = createDotIcon(color)

          return (
            <Marker
              key={site.id}
              position={[site.latitude, site.longitude]}
              icon={icon}
              eventHandlers={{
                click: () => handleSiteClick(site),
              }}
            >
              <LeafletTooltip direction="top" offset={[0, -8]} opacity={0.9}>
                <span className="text-xs font-medium">{site.name}</span>
              </LeafletTooltip>
              <Popup>
                <div className="text-sm">
                  <div className="font-bold mb-1">{site.name}</div>
                  <div className="text-xs text-gray-500 mb-1">{formatRoleLabel(site.role)}</div>
                  {site.location && <div className="text-xs text-gray-600 mb-2">{site.location}</div>}
                  {site.capacity > 0 && (
                    <div className="text-xs">Capacity: {site.capacity.toLocaleString()}</div>
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
