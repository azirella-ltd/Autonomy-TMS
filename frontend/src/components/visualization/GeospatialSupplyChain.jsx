import React, { useRef, useEffect, useState } from 'react'
import { MapContainer, TileLayer, Marker, Popup, Polyline, Circle, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

// Fix for default markers in Leaflet with Webpack
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: require('leaflet/dist/images/marker-icon-2x.png'),
  iconUrl: require('leaflet/dist/images/marker-icon.png'),
  shadowUrl: require('leaflet/dist/images/marker-shadow.png'),
})

// Custom marker icons for different site types
const createCustomIcon = (color, role) => {
  return L.divIcon({
    className: 'custom-marker',
    html: `
      <div style="
        background-color: ${color};
        width: 40px;
        height: 40px;
        border-radius: 50%;
        border: 3px solid white;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: bold;
        color: white;
        font-size: 12px;
      ">
        ${role.charAt(0).toUpperCase()}
      </div>
    `,
    iconSize: [40, 40],
    iconAnchor: [20, 20],
    popupAnchor: [0, -20],
  })
}

// Default color palette for known roles (fallback when no siteTypeColors prop)
const DEFAULT_ROLE_COLORS = {
  retailer: '#10b981',    // Green
  wholesaler: '#3b82f6',  // Blue
  distributor: '#8b5cf6', // Purple
  factory: '#ef4444',     // Red
  manufacturer: '#ef4444',// Red
  supplier: '#f59e0b',    // Orange
  market_supply: '#f59e0b', // Orange
  market_demand: '#10b981', // Green
  inventory: '#0ea5e9',   // Sky blue
}

// Get color by role, using siteTypeColors override if available
const getRoleColor = (role, siteTypeColors) => {
  if (!role) return '#6b7280'
  const key = role.toLowerCase().replace(/[\s-]+/g, '_')
  // Check override map first
  if (siteTypeColors && siteTypeColors[key]) return siteTypeColors[key]
  return DEFAULT_ROLE_COLORS[key] || '#6b7280'
}

// Animated polyline component
const AnimatedFlow = ({ positions, color, active }) => {
  const [offset, setOffset] = useState(0)

  useEffect(() => {
    if (!active) return

    const interval = setInterval(() => {
      setOffset((prev) => (prev + 1) % 20)
    }, 100)

    return () => clearInterval(interval)
  }, [active])

  return (
    <Polyline
      positions={positions}
      color={active ? color : '#cbd5e1'}
      weight={active ? 4 : 2}
      opacity={active ? 0.8 : 0.3}
      dashArray={active ? '10, 10' : undefined}
      dashOffset={active ? offset : 0}
    />
  )
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

const GeospatialSupplyChain = ({ sites, edges, inventoryData, activeFlows, onSiteSelect, siteTypeColors }) => {
  const [selectedSite, setSelectedSite] = useState(null)
  const [mapCenter, setMapCenter] = useState([39.8283, -98.5795]) // Center of USA
  const [mapZoom, setMapZoom] = useState(4)
  const [showInventoryRadius, setShowInventoryRadius] = useState(true)
  const [showFlowAnimation, setShowFlowAnimation] = useState(true)

  // Filter sites with valid coordinates
  const sitesWithCoords = sites.filter((site) => site.latitude && site.longitude)

  // Prepare edges with coordinates
  const edgesWithCoords = edges
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

  const handleSiteClick = (site) => {
    setSelectedSite(site)
    setMapCenter([site.latitude, site.longitude])
    setMapZoom(8)
    if (onSiteSelect) {
      onSiteSelect(site)
    }
  }

  // Calculate inventory radius (scaled based on inventory level)
  const getInventoryRadius = (inventory) => {
    // Radius in meters, scaled by inventory
    const baseRadius = 50000 // 50km base
    const scaleFactor = Math.sqrt(inventory / 10) // Square root for better visual scaling
    return baseRadius * scaleFactor
  }

  return (
    <div className="w-full h-full relative">
      {/* Controls */}
      <div className="absolute top-4 right-4 z-[1000] bg-white rounded-lg shadow-lg p-4 space-y-2">
        <div className="text-sm font-medium mb-2">Map Controls</div>
        <label className="flex items-center text-sm">
          <input
            type="checkbox"
            checked={showInventoryRadius}
            onChange={(e) => setShowInventoryRadius(e.target.checked)}
            className="mr-2"
          />
          Show Inventory Radius
        </label>
        <label className="flex items-center text-sm">
          <input
            type="checkbox"
            checked={showFlowAnimation}
            onChange={(e) => setShowFlowAnimation(e.target.checked)}
            className="mr-2"
          />
          Animate Flows
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

      {/* Legend - dynamic based on actual site roles in the DAG */}
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
            <div className="text-sm font-medium mb-2">Site Types</div>
            <div className="space-y-1 text-xs">
              {entries.map((entry) => (
                <div key={entry.key} className="flex items-center">
                  <div
                    className="w-4 h-4 rounded-full mr-2"
                    style={{ backgroundColor: entry.color }}
                  ></div>
                  <span>{entry.label}</span>
                </div>
              ))}
            </div>
          </div>
        )
      })()}

      {/* Selected Site Info */}
      {selectedSite && inventoryData && inventoryData[selectedSite.id] && (
        <div className="absolute bottom-4 left-48 z-[1000] bg-white rounded-lg shadow-lg p-4 max-w-xs">
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm font-medium">{selectedSite.role || selectedSite.name}</div>
            <button
              onClick={() => setSelectedSite(null)}
              className="text-gray-400 hover:text-gray-600"
            >
              ✕
            </button>
          </div>
          {selectedSite.location && (
            <div className="text-xs text-gray-600 mb-2">{selectedSite.location}</div>
          )}
          <div className="text-xs space-y-1">
            <div className="flex justify-between">
              <span className="text-gray-600">Inventory:</span>
              <span className="font-medium">{inventoryData[selectedSite.id].inventory}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Backlog:</span>
              <span className="font-medium text-red-600">
                {inventoryData[selectedSite.id].backlog}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Cost:</span>
              <span className="font-medium">
                ${inventoryData[selectedSite.id].cost?.toFixed(2)}
              </span>
            </div>
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

        {/* Flow Lines */}
        {edgesWithCoords.map((edge, index) => {
          const isActive =
            showFlowAnimation && activeFlows?.includes(`${edge.from}-${edge.to}`)
          return (
            <AnimatedFlow
              key={`${edge.from}-${edge.to}-${index}`}
              positions={edge.positions}
              color="#3b82f6"
              active={isActive}
            />
          )
        })}

        {/* Inventory Radius Circles */}
        {showInventoryRadius &&
          sitesWithCoords.map((site) => {
            const inventory = inventoryData?.[site.id]?.inventory || 0
            if (inventory === 0) return null

            return (
              <Circle
                key={`circle-${site.id}`}
                center={[site.latitude, site.longitude]}
                radius={getInventoryRadius(inventory)}
                pathOptions={{
                  color: getRoleColor(site.role, siteTypeColors),
                  fillColor: getRoleColor(site.role, siteTypeColors),
                  fillOpacity: 0.1,
                  weight: 1,
                }}
              />
            )
          })}

        {/* Site Markers */}
        {sitesWithCoords.map((site) => {
          const color = getRoleColor(site.role, siteTypeColors)
          const icon = createCustomIcon(color, site.role)
          const inventory = inventoryData?.[site.id]?.inventory || 0
          const backlog = inventoryData?.[site.id]?.backlog || 0
          const cost = inventoryData?.[site.id]?.cost || 0

          return (
            <Marker
              key={site.id}
              position={[site.latitude, site.longitude]}
              icon={icon}
              eventHandlers={{
                click: () => handleSiteClick(site),
              }}
            >
              <Popup>
                <div className="text-sm">
                  <div className="font-bold mb-1">{site.role || site.name}</div>
                  {site.location && <div className="text-xs text-gray-600 mb-2">{site.location}</div>}
                  <div className="space-y-1 text-xs">
                    <div className="flex justify-between">
                      <span>Inventory:</span>
                      <span className="font-medium">{inventory}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Backlog:</span>
                      <span className="font-medium text-red-600">{backlog}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Cost:</span>
                      <span className="font-medium">${cost.toFixed(2)}</span>
                    </div>
                  </div>
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
