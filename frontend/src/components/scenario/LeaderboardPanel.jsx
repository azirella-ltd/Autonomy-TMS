import React, { useState, useEffect } from 'react'
import {
  TrophyIcon,
  ChartBarIcon,
  ClockIcon,
  CurrencyDollarIcon,
  CheckCircleIcon
} from '@heroicons/react/24/outline'
import { toast } from 'react-toastify'

const LeaderboardPanel = ({ playerId }) => {
  const [leaderboards, setLeaderboards] = useState([])
  const [selectedLeaderboard, setSelectedLeaderboard] = useState(null)
  const [leaderboardData, setLeaderboardData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchLeaderboards()
  }, [])

  useEffect(() => {
    if (selectedLeaderboard) {
      fetchLeaderboardData(selectedLeaderboard.id)
    }
  }, [selectedLeaderboard, playerId])

  const fetchLeaderboards = async () => {
    try {
      setLoading(true)
      const response = await fetch('/api/v1/gamification/leaderboards?active_only=true', {
        credentials: 'include'
      })
      if (!response.ok) throw new Error('Failed to fetch leaderboards')
      const data = await response.json()
      setLeaderboards(data)
      if (data.length > 0) {
        setSelectedLeaderboard(data[0]) // Select first leaderboard by default
      }
    } catch (error) {
      console.error('Error fetching leaderboards:', error)
      toast.error('Failed to load leaderboards')
    } finally {
      setLoading(false)
    }
  }

  const fetchLeaderboardData = async (leaderboardId) => {
    try {
      const url = playerId
        ? `/api/v1/gamification/leaderboards/${leaderboardId}?limit=50&player_id=${playerId}`
        : `/api/v1/gamification/leaderboards/${leaderboardId}?limit=50`

      const response = await fetch(url, {
        credentials: 'include'
      })
      if (!response.ok) throw new Error('Failed to fetch leaderboard data')
      const data = await response.json()
      setLeaderboardData(data)
    } catch (error) {
      console.error('Error fetching leaderboard data:', error)
      toast.error('Failed to load leaderboard data')
    }
  }

  const getLeaderboardIcon = (type) => {
    switch (type) {
      case 'global': return <TrophyIcon className="h-5 w-5" />
      case 'weekly': return <ClockIcon className="h-5 w-5" />
      case 'monthly': return <ClockIcon className="h-5 w-5" />
      default: return <ChartBarIcon className="h-5 w-5" />
    }
  }

  const getMetricIcon = (metric) => {
    switch (metric) {
      case 'total_points': return <TrophyIcon className="h-4 w-4" />
      case 'win_rate': return <CheckCircleIcon className="h-4 w-4" />
      case 'avg_cost': return <CurrencyDollarIcon className="h-4 w-4" />
      case 'service_level': return <ChartBarIcon className="h-4 w-4" />
      default: return <ChartBarIcon className="h-4 w-4" />
    }
  }

  const formatScore = (score, metric) => {
    switch (metric) {
      case 'total_points':
        return Math.round(score).toLocaleString()
      case 'win_rate':
      case 'service_level':
        return `${score.toFixed(1)}%`
      case 'avg_cost':
        return `$${score.toFixed(2)}`
      case 'efficiency':
        return score.toFixed(2)
      default:
        return score.toFixed(2)
    }
  }

  const getRankMedal = (rank) => {
    switch (rank) {
      case 1: return '🥇'
      case 2: return '🥈'
      case 3: return '🥉'
      default: return null
    }
  }

  const getRankColor = (rank) => {
    if (rank === 1) return 'bg-yellow-50 border-yellow-400'
    if (rank === 2) return 'bg-gray-50 border-gray-400'
    if (rank === 3) return 'bg-orange-50 border-orange-400'
    return 'bg-white border-gray-200'
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Leaderboard Selector */}
      <div className="bg-white rounded-lg shadow-sm p-4">
        <h2 className="text-lg font-bold text-gray-900 mb-4 flex items-center">
          <TrophyIcon className="h-6 w-6 mr-2 text-indigo-600" />
          Leaderboards
        </h2>
        <div className="flex flex-wrap gap-2">
          {leaderboards.map((lb) => (
            <button
              key={lb.id}
              onClick={() => setSelectedLeaderboard(lb)}
              className={`flex items-center px-4 py-2 rounded-lg font-medium transition-colors ${
                selectedLeaderboard?.id === lb.id
                  ? 'bg-indigo-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {getLeaderboardIcon(lb.leaderboard_type)}
              <span className="ml-2">{lb.name}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Selected Leaderboard */}
      {selectedLeaderboard && leaderboardData && (
        <div className="bg-white rounded-lg shadow-sm overflow-hidden">
          {/* Header */}
          <div className="bg-gradient-to-r from-indigo-500 to-purple-600 p-6 text-white">
            <h3 className="text-2xl font-bold flex items-center">
              {getLeaderboardIcon(selectedLeaderboard.leaderboard_type)}
              <span className="ml-2">{selectedLeaderboard.name}</span>
            </h3>
            {selectedLeaderboard.description && (
              <p className="text-indigo-100 mt-2">{selectedLeaderboard.description}</p>
            )}
            <div className="mt-3 flex items-center text-sm text-indigo-100">
              {getMetricIcon(selectedLeaderboard.metric)}
              <span className="ml-1">
                Ranked by: {selectedLeaderboard.metric.replace(/_/g, ' ')}
              </span>
              <span className="ml-4">• {leaderboardData.total_entries} players</span>
            </div>

            {/* Player's Rank */}
            {leaderboardData.player_rank && (
              <div className="mt-4 bg-white bg-opacity-20 rounded-lg p-3">
                <p className="text-sm font-medium">Your Rank</p>
                <p className="text-2xl font-bold">#{leaderboardData.player_rank}</p>
              </div>
            )}
          </div>

          {/* Leaderboard Table */}
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Rank
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Player
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Score
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {leaderboardData.entries.map((entry) => {
                  const isCurrentPlayer = entry.player_id === playerId
                  const medal = getRankMedal(entry.rank)

                  return (
                    <tr
                      key={entry.id}
                      className={`transition-colors ${
                        isCurrentPlayer
                          ? 'bg-indigo-50 font-semibold'
                          : entry.rank <= 3
                          ? getRankColor(entry.rank)
                          : 'hover:bg-gray-50'
                      } ${entry.rank <= 3 ? 'border-l-4' : ''}`}
                    >
                      {/* Rank */}
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="flex items-center">
                          {medal && <span className="text-2xl mr-2">{medal}</span>}
                          <span className={`text-lg ${entry.rank <= 3 ? 'font-bold' : 'font-medium'} text-gray-900`}>
                            #{entry.rank}
                          </span>
                        </div>
                      </td>

                      {/* Player */}
                      <td className="px-6 py-4">
                        <div className="flex items-center">
                          <div className="flex-shrink-0 h-10 w-10 rounded-full bg-indigo-600 flex items-center justify-center text-white font-bold">
                            {entry.player_name ? entry.player_name[0].toUpperCase() : '?'}
                          </div>
                          <div className="ml-4">
                            <div className="text-sm font-medium text-gray-900">
                              {entry.player_name || `Player ${entry.player_id}`}
                              {isCurrentPlayer && (
                                <span className="ml-2 px-2 py-1 text-xs bg-indigo-600 text-white rounded-full">
                                  You
                                </span>
                              )}
                            </div>
                            {entry.player_role && (
                              <div className="text-sm text-gray-500">{entry.player_role}</div>
                            )}
                          </div>
                        </div>
                      </td>

                      {/* Score */}
                      <td className="px-6 py-4 whitespace-nowrap text-right">
                        <div className="flex items-center justify-end">
                          {getMetricIcon(selectedLeaderboard.metric)}
                          <span className={`ml-2 text-lg ${entry.rank <= 3 ? 'font-bold' : 'font-medium'}`}>
                            {formatScore(entry.score, selectedLeaderboard.metric)}
                          </span>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* Empty State */}
          {leaderboardData.entries.length === 0 && (
            <div className="text-center py-12">
              <ChartBarIcon className="h-16 w-16 text-gray-300 mx-auto mb-4" />
              <p className="text-gray-500 text-lg">No rankings yet</p>
              <p className="text-gray-400 text-sm mt-2">Be the first to play and get ranked!</p>
            </div>
          )}
        </div>
      )}

      {/* No Leaderboards */}
      {leaderboards.length === 0 && (
        <div className="text-center py-12 bg-white rounded-lg shadow-sm">
          <TrophyIcon className="h-16 w-16 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500 text-lg">No leaderboards available</p>
        </div>
      )}
    </div>
  )
}

export default LeaderboardPanel
