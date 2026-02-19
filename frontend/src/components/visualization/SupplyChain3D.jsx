import React, { useRef, useEffect, useState, useMemo } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import {
  OrbitControls,
  PerspectiveCamera,
  Environment,
  Grid,
  Html,
  Line,
  Text,
  Box,
  Sphere,
  Cylinder,
} from '@react-three/drei'
import * as THREE from 'three'

// Site Component - represents a supply chain site in 3D space
const SupplyChainSite = ({ site, position, selected, onSelect, inventoryLevel }) => {
  const meshRef = useRef()
  const [hovered, setHovered] = useState(false)

  // Animate node based on inventory level
  useFrame((state) => {
    if (meshRef.current) {
      // Pulse animation for selected nodes
      if (selected) {
        meshRef.current.scale.setScalar(1 + Math.sin(state.clock.elapsedTime * 3) * 0.1)
      } else {
        meshRef.current.scale.setScalar(1)
      }

      // Rotate slowly
      meshRef.current.rotation.y += 0.01
    }
  })

  // Color based on site role and inventory status
  const getSiteColor = () => {
    if (selected) return '#fbbf24' // Amber for selected
    if (hovered) return '#60a5fa' // Blue for hovered

    // Color by role
    switch (site.role?.toLowerCase()) {
      case 'retailer':
        return '#10b981' // Green
      case 'wholesaler':
        return '#3b82f6' // Blue
      case 'distributor':
        return '#8b5cf6' // Purple
      case 'factory':
        return '#ef4444' // Red
      case 'supplier':
        return '#f59e0b' // Orange
      default:
        return '#6b7280' // Gray
    }
  }

  // Size based on inventory level
  const getSiteSize = () => {
    const baseSize = 1
    const inventoryFactor = Math.min(inventoryLevel / 50, 2) // Cap at 2x size
    return baseSize * (0.5 + inventoryFactor * 0.5)
  }

  const color = getSiteColor()
  const size = getSiteSize()

  return (
    <group position={position}>
      <mesh
        ref={meshRef}
        onClick={() => onSelect(site)}
        onPointerOver={() => setHovered(true)}
        onPointerOut={() => setHovered(false)}
      >
        <boxGeometry args={[size, size, size]} />
        <meshStandardMaterial
          color={color}
          metalness={0.4}
          roughness={0.6}
          emissive={selected ? '#fbbf24' : hovered ? '#60a5fa' : '#000000'}
          emissiveIntensity={selected ? 0.5 : hovered ? 0.3 : 0}
        />
      </mesh>

      {/* Site label */}
      <Html distanceFactor={10} position={[0, size / 2 + 0.5, 0]}>
        <div
          className="bg-white px-2 py-1 rounded shadow-lg text-xs font-medium pointer-events-none"
          style={{ whiteSpace: 'nowrap' }}
        >
          {site.role || site.name}
          {inventoryLevel !== undefined && (
            <div className="text-gray-600 text-xs">Inv: {inventoryLevel}</div>
          )}
        </div>
      </Html>

      {/* Inventory visualization (height indicator) */}
      {inventoryLevel > 0 && (
        <Cylinder
          args={[0.2, 0.2, inventoryLevel / 10, 8]}
          position={[0, -size / 2 - inventoryLevel / 20, 0]}
        >
          <meshStandardMaterial color="#22c55e" transparent opacity={0.6} />
        </Cylinder>
      )}
    </group>
  )
}

// Edge/Lane Component - represents material flow between sites
const SupplyChainEdge = ({ startPos, endPos, active, flowSpeed }) => {
  const lineRef = useRef()
  const [particles, setParticles] = useState([])

  useEffect(() => {
    // Create flow particles
    if (active) {
      const newParticles = Array.from({ length: 5 }, (_, i) => ({
        id: i,
        progress: i / 5,
      }))
      setParticles(newParticles)
    } else {
      setParticles([])
    }
  }, [active])

  // Animate particles
  useFrame(() => {
    if (active && particles.length > 0) {
      setParticles((prev) =>
        prev.map((p) => ({
          ...p,
          progress: (p.progress + flowSpeed * 0.01) % 1,
        }))
      )
    }
  })

  const points = [new THREE.Vector3(...startPos), new THREE.Vector3(...endPos)]

  // Calculate particle positions along the line
  const getParticlePosition = (progress) => {
    const x = startPos[0] + (endPos[0] - startPos[0]) * progress
    const y = startPos[1] + (endPos[1] - startPos[1]) * progress
    const z = startPos[2] + (endPos[2] - startPos[2]) * progress
    return [x, y, z]
  }

  return (
    <group>
      {/* Main line */}
      <Line
        ref={lineRef}
        points={points}
        color={active ? '#3b82f6' : '#9ca3af'}
        lineWidth={active ? 3 : 1.5}
        transparent
        opacity={active ? 0.8 : 0.3}
      />

      {/* Flow particles */}
      {particles.map((particle) => {
        const pos = getParticlePosition(particle.progress)
        return (
          <Sphere key={particle.id} args={[0.1, 8, 8]} position={pos}>
            <meshBasicMaterial color="#fbbf24" />
          </Sphere>
        )
      })}

      {/* Arrow at endpoint */}
      {active && (
        <mesh position={endPos} lookAt={startPos}>
          <coneGeometry args={[0.2, 0.4, 8]} />
          <meshBasicMaterial color="#3b82f6" />
        </mesh>
      )}
    </group>
  )
}

// Camera Controller
const CameraController = ({ focusSite }) => {
  const { camera } = useThree()

  useEffect(() => {
    if (focusSite) {
      camera.position.set(
        focusSite.position[0] + 5,
        focusSite.position[1] + 3,
        focusSite.position[2] + 5
      )
      camera.lookAt(new THREE.Vector3(...focusSite.position))
    }
  }, [focusSite, camera])

  return null
}

// Main 3D Visualization Component
const SupplyChain3D = ({ sites, edges, inventoryData, activeFlows, onSiteSelect }) => {
  const [selectedSite, setSelectedSite] = useState(null)
  const [showGrid, setShowGrid] = useState(true)
  const [cameraView, setCameraView] = useState('default') // default, top, side

  // Calculate site positions (auto-layout)
  const sitePositions = useMemo(() => {
    const positions = {}
    const levels = {}

    // Group sites by supply chain level (retailer=0, wholesaler=1, distributor=2, factory=3)
    sites.forEach((site) => {
      let level = 0
      switch (site.role?.toLowerCase()) {
        case 'retailer':
          level = 0
          break
        case 'wholesaler':
          level = 1
          break
        case 'distributor':
          level = 2
          break
        case 'factory':
          level = 3
          break
        case 'supplier':
          level = 4
          break
        default:
          level = 0
      }

      if (!levels[level]) levels[level] = []
      levels[level].push(site)
    })

    // Position sites in a grid
    Object.entries(levels).forEach(([level, levelSites]) => {
      const levelNum = parseInt(level)
      const spacing = 4
      const offsetX = -((levelSites.length - 1) * spacing) / 2

      levelSites.forEach((site, index) => {
        positions[site.id] = [
          offsetX + index * spacing, // X: spread horizontally
          0, // Y: ground level
          levelNum * -spacing, // Z: depth by level
        ]
      })
    })

    return positions
  }, [sites])

  const handleSiteSelect = (site) => {
    setSelectedSite(site)
    if (onSiteSelect) {
      onSiteSelect(site)
    }
  }

  const setCameraPreset = (view) => {
    setCameraView(view)
    // Camera positions will be handled by OrbitControls
  }

  return (
    <div className="w-full h-full relative">
      {/* Controls */}
      <div className="absolute top-4 right-4 z-10 bg-white rounded-lg shadow-lg p-4 space-y-2">
        <div className="text-sm font-medium mb-2">View Controls</div>
        <button
          onClick={() => setCameraPreset('default')}
          className={`w-full px-3 py-1 text-sm rounded ${
            cameraView === 'default'
              ? 'bg-indigo-600 text-white'
              : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
          }`}
        >
          Default View
        </button>
        <button
          onClick={() => setCameraPreset('top')}
          className={`w-full px-3 py-1 text-sm rounded ${
            cameraView === 'top'
              ? 'bg-indigo-600 text-white'
              : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
          }`}
        >
          Top View
        </button>
        <button
          onClick={() => setCameraPreset('side')}
          className={`w-full px-3 py-1 text-sm rounded ${
            cameraView === 'side'
              ? 'bg-indigo-600 text-white'
              : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
          }`}
        >
          Side View
        </button>
        <div className="border-t pt-2 mt-2">
          <label className="flex items-center text-sm">
            <input
              type="checkbox"
              checked={showGrid}
              onChange={(e) => setShowGrid(e.target.checked)}
              className="mr-2"
            />
            Show Grid
          </label>
        </div>
      </div>

      {/* Legend */}
      <div className="absolute top-4 left-4 z-10 bg-white rounded-lg shadow-lg p-4">
        <div className="text-sm font-medium mb-2">Site Types</div>
        <div className="space-y-1 text-xs">
          <div className="flex items-center">
            <div className="w-3 h-3 rounded bg-green-500 mr-2"></div>
            <span>Retailer</span>
          </div>
          <div className="flex items-center">
            <div className="w-3 h-3 rounded bg-blue-500 mr-2"></div>
            <span>Wholesaler</span>
          </div>
          <div className="flex items-center">
            <div className="w-3 h-3 rounded bg-purple-500 mr-2"></div>
            <span>Distributor</span>
          </div>
          <div className="flex items-center">
            <div className="w-3 h-3 rounded bg-red-500 mr-2"></div>
            <span>Factory</span>
          </div>
          <div className="flex items-center">
            <div className="w-3 h-3 rounded bg-orange-500 mr-2"></div>
            <span>Supplier</span>
          </div>
        </div>
      </div>

      {/* Selected Site Info */}
      {selectedSite && (
        <div className="absolute bottom-4 left-4 z-10 bg-white rounded-lg shadow-lg p-4 max-w-xs">
          <div className="text-sm font-medium mb-2">{selectedSite.role || selectedSite.name}</div>
          {inventoryData && inventoryData[selectedSite.id] && (
            <div className="text-xs space-y-1">
              <div>
                <span className="font-medium">Inventory:</span>{' '}
                {inventoryData[selectedSite.id].inventory}
              </div>
              <div>
                <span className="font-medium">Backlog:</span>{' '}
                {inventoryData[selectedSite.id].backlog}
              </div>
              <div>
                <span className="font-medium">Cost:</span> $
                {inventoryData[selectedSite.id].cost?.toFixed(2)}
              </div>
            </div>
          )}
          <button
            onClick={() => setSelectedSite(null)}
            className="mt-2 text-xs text-indigo-600 hover:text-indigo-700"
          >
            Close
          </button>
        </div>
      )}

      {/* 3D Canvas */}
      <Canvas shadows>
        <PerspectiveCamera makeDefault position={[10, 10, 10]} />
        <OrbitControls
          enableDamping
          dampingFactor={0.05}
          minDistance={5}
          maxDistance={50}
          maxPolarAngle={Math.PI / 2}
        />

        {/* Lighting */}
        <ambientLight intensity={0.5} />
        <directionalLight
          position={[10, 10, 5]}
          intensity={1}
          castShadow
          shadow-mapSize-width={2048}
          shadow-mapSize-height={2048}
        />
        <pointLight position={[-10, 10, -10]} intensity={0.5} />

        {/* Environment */}
        <Environment preset="city" />

        {/* Grid */}
        {showGrid && <Grid args={[50, 50]} cellSize={1} cellColor="#94a3b8" sectionColor="#64748b" />}

        {/* Sites */}
        {sites.map((site) => (
          <SupplyChainSite
            key={site.id}
            site={site}
            position={sitePositions[site.id] || [0, 0, 0]}
            selected={selectedSite?.id === site.id}
            onSelect={handleSiteSelect}
            inventoryLevel={inventoryData?.[site.id]?.inventory || 0}
          />
        ))}

        {/* Edges */}
        {edges.map((edge, index) => (
          <SupplyChainEdge
            key={`${edge.from}-${edge.to}-${index}`}
            startPos={sitePositions[edge.from] || [0, 0, 0]}
            endPos={sitePositions[edge.to] || [0, 0, 0]}
            active={activeFlows?.includes(`${edge.from}-${edge.to}`)}
            flowSpeed={edge.flowSpeed || 1}
          />
        ))}

        {/* Camera controller */}
        <CameraController
          focusSite={
            selectedSite && sitePositions[selectedSite.id]
              ? { position: sitePositions[selectedSite.id] }
              : null
          }
        />
      </Canvas>
    </div>
  )
}

export default SupplyChain3D
