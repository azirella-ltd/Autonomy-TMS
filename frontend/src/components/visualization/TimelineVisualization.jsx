import React, { useState, useEffect, useRef } from 'react'
import {
  PlayIcon,
  PauseIcon,
  BackwardIcon,
  ForwardIcon,
  ArrowPathIcon,
} from '@heroicons/react/24/solid'
import SupplyChain3D from './SupplyChain3D'

const TimelineVisualization = ({ gameHistory, nodes, edges }) => {
  const [currentRound, setCurrentRound] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [playbackSpeed, setPlaybackSpeed] = useState(1) // 0.5x, 1x, 2x, 4x
  const [selectedNode, setSelectedNode] = useState(null)
  const intervalRef = useRef(null)

  const maxRounds = gameHistory?.length || 0

  // Playback control
  useEffect(() => {
    if (isPlaying && currentRound < maxRounds - 1) {
      intervalRef.current = setInterval(() => {
        setCurrentRound((prev) => {
          if (prev >= maxRounds - 1) {
            setIsPlaying(false)
            return prev
          }
          return prev + 1
        })
      }, 1000 / playbackSpeed)
    } else {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
    }
  }, [isPlaying, playbackSpeed, currentRound, maxRounds])

  const handlePlay = () => {
    if (currentRound >= maxRounds - 1) {
      setCurrentRound(0)
    }
    setIsPlaying(true)
  }

  const handlePause = () => {
    setIsPlaying(false)
  }

  const handleReset = () => {
    setIsPlaying(false)
    setCurrentRound(0)
  }

  const handleStepBack = () => {
    setIsPlaying(false)
    setCurrentRound((prev) => Math.max(0, prev - 1))
  }

  const handleStepForward = () => {
    setIsPlaying(false)
    setCurrentRound((prev) => Math.min(maxRounds - 1, prev + 1))
  }

  const handleSpeedChange = (speed) => {
    setPlaybackSpeed(speed)
  }

  const handleSliderChange = (e) => {
    const round = parseInt(e.target.value)
    setCurrentRound(round)
    setIsPlaying(false)
  }

  // Get current round data
  const currentRoundData = gameHistory?.[currentRound] || {}

  // Prepare inventory data for 3D visualization
  const inventoryData = {}
  const activeFlows = []

  if (currentRoundData.scenarioUsers) {
    currentRoundData.scenarioUsers.forEach((scenarioUser) => {
      inventoryData[scenarioUser.scenario_user_id] = {
        inventory: scenarioUser.inventory_end || 0,
        backlog: scenarioUser.backlog || 0,
        cost: scenarioUser.total_cost || 0,
        order_placed: scenarioUser.order_placed || 0,
      }

      // Mark active flows (nodes that placed orders)
      if (scenarioUser.order_placed > 0 && scenarioUser.upstream_scenario_user_id) {
        activeFlows.push(`${scenarioUser.scenario_user_id}-${scenarioUser.upstream_scenario_user_id}`)
      }
    })
  }

  // Get statistics for current round
  const getTotalCost = () => {
    if (!currentRoundData.scenarioUsers) return 0
    return currentRoundData.scenarioUsers.reduce((sum, p) => sum + (p.total_cost || 0), 0)
  }

  const getTotalInventory = () => {
    if (!currentRoundData.scenarioUsers) return 0
    return currentRoundData.scenarioUsers.reduce((sum, p) => sum + (p.inventory_end || 0), 0)
  }

  const getTotalBacklog = () => {
    if (!currentRoundData.scenarioUsers) return 0
    return currentRoundData.scenarioUsers.reduce((sum, p) => sum + (p.backlog || 0), 0)
  }

  const getSelectedNodeData = () => {
    if (!selectedNode || !currentRoundData.scenarioUsers) return null
    return currentRoundData.scenarioUsers.find((p) => p.scenario_user_id === selectedNode.id)
  }

  const selectedNodeData = getSelectedNodeData()

  return (
    <div className="w-full h-full flex flex-col bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-gray-900">Supply Chain Timeline</h2>
            <p className="text-sm text-gray-600 mt-1">
              Visualize historical supply chain states over time
            </p>
          </div>
          <div className="flex items-center space-x-4">
            <div className="text-right">
              <div className="text-sm text-gray-600">Round</div>
              <div className="text-2xl font-bold text-indigo-600">
                {currentRound + 1} / {maxRounds}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Statistics Panel */}
      <div className="bg-white border-b px-6 py-3">
        <div className="grid grid-cols-3 gap-4">
          <div className="text-center">
            <div className="text-sm text-gray-600">Total Cost</div>
            <div className="text-xl font-bold text-gray-900">${getTotalCost().toFixed(2)}</div>
          </div>
          <div className="text-center">
            <div className="text-sm text-gray-600">Total Inventory</div>
            <div className="text-xl font-bold text-green-600">{getTotalInventory()}</div>
          </div>
          <div className="text-center">
            <div className="text-sm text-gray-600">Total Backlog</div>
            <div className="text-xl font-bold text-red-600">{getTotalBacklog()}</div>
          </div>
        </div>
      </div>

      {/* 3D Visualization */}
      <div className="flex-1 relative">
        <SupplyChain3D
          nodes={nodes}
          edges={edges}
          inventoryData={inventoryData}
          activeFlows={activeFlows}
          onNodeSelect={setSelectedNode}
        />
      </div>

      {/* Selected Node Details */}
      {selectedNodeData && (
        <div className="bg-white border-t px-6 py-4">
          <div className="max-w-4xl mx-auto">
            <h3 className="text-lg font-medium mb-3">{selectedNode.role || selectedNode.name}</h3>
            <div className="grid grid-cols-5 gap-4">
              <div>
                <div className="text-xs text-gray-600">Inventory</div>
                <div className="text-lg font-bold text-green-600">
                  {selectedNodeData.inventory_end || 0}
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-600">Backlog</div>
                <div className="text-lg font-bold text-red-600">
                  {selectedNodeData.backlog || 0}
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-600">Order Placed</div>
                <div className="text-lg font-bold text-blue-600">
                  {selectedNodeData.order_placed || 0}
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-600">Incoming Order</div>
                <div className="text-lg font-bold text-purple-600">
                  {selectedNodeData.incoming_order || 0}
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-600">Round Cost</div>
                <div className="text-lg font-bold text-gray-900">
                  ${(selectedNodeData.round_cost || 0).toFixed(2)}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Timeline Controls */}
      <div className="bg-white border-t px-6 py-4">
        <div className="max-w-4xl mx-auto">
          {/* Playback Controls */}
          <div className="flex items-center justify-center space-x-4 mb-4">
            <button
              onClick={handleReset}
              className="p-2 rounded-lg bg-gray-200 hover:bg-gray-300 text-gray-700 transition-colors"
              title="Reset to start"
            >
              <ArrowPathIcon className="h-5 w-5" />
            </button>

            <button
              onClick={handleStepBack}
              className="p-2 rounded-lg bg-gray-200 hover:bg-gray-300 text-gray-700 transition-colors"
              disabled={currentRound === 0}
              title="Previous round"
            >
              <BackwardIcon className="h-5 w-5" />
            </button>

            <button
              onClick={isPlaying ? handlePause : handlePlay}
              className="p-3 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white transition-colors shadow-lg"
              title={isPlaying ? 'Pause' : 'Play'}
            >
              {isPlaying ? (
                <PauseIcon className="h-6 w-6" />
              ) : (
                <PlayIcon className="h-6 w-6" />
              )}
            </button>

            <button
              onClick={handleStepForward}
              className="p-2 rounded-lg bg-gray-200 hover:bg-gray-300 text-gray-700 transition-colors"
              disabled={currentRound >= maxRounds - 1}
              title="Next round"
            >
              <ForwardIcon className="h-5 w-5" />
            </button>

            {/* Speed Control */}
            <div className="flex items-center space-x-2 ml-4">
              <span className="text-sm text-gray-600">Speed:</span>
              {[0.5, 1, 2, 4].map((speed) => (
                <button
                  key={speed}
                  onClick={() => handleSpeedChange(speed)}
                  className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
                    playbackSpeed === speed
                      ? 'bg-indigo-600 text-white'
                      : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                  }`}
                >
                  {speed}x
                </button>
              ))}
            </div>
          </div>

          {/* Timeline Slider */}
          <div className="relative">
            <input
              type="range"
              min="0"
              max={maxRounds - 1}
              value={currentRound}
              onChange={handleSliderChange}
              className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer slider"
              style={{
                background: `linear-gradient(to right, #4f46e5 0%, #4f46e5 ${
                  (currentRound / (maxRounds - 1)) * 100
                }%, #e5e7eb ${(currentRound / (maxRounds - 1)) * 100}%, #e5e7eb 100%)`,
              }}
            />

            {/* Round markers */}
            <div className="flex justify-between mt-2 px-1">
              <span className="text-xs text-gray-600">Round 1</span>
              <span className="text-xs text-gray-600">Round {Math.floor(maxRounds / 2)}</span>
              <span className="text-xs text-gray-600">Round {maxRounds}</span>
            </div>
          </div>

          {/* Legend */}
          <div className="mt-4 flex items-center justify-center space-x-6 text-xs text-gray-600">
            <div className="flex items-center">
              <div className="w-3 h-3 rounded-full bg-blue-500 mr-1"></div>
              <span>Active Flow</span>
            </div>
            <div className="flex items-center">
              <div className="w-3 h-3 rounded-full bg-green-500 mr-1"></div>
              <span>High Inventory</span>
            </div>
            <div className="flex items-center">
              <div className="w-3 h-3 rounded-full bg-amber-500 mr-1"></div>
              <span>Selected</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default TimelineVisualization
