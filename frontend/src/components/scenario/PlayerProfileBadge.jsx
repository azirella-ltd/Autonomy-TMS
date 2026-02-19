import React, { useState, useEffect } from 'react'
import { TrophyIcon, SparklesIcon } from '@heroicons/react/24/solid'
import { toast } from 'react-toastify'

const PlayerProfileBadge = ({ playerId, compact = false }) => {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (playerId) {
      fetchStats()
      // Poll for updates every 30 seconds
      const interval = setInterval(fetchStats, 30000)
      return () => clearInterval(interval)
    }
  }, [playerId])

  const fetchStats = async () => {
    try {
      const response = await fetch(`/api/v1/gamification/players/${playerId}/stats`, {
        credentials: 'include'
      })
      if (!response.ok) throw new Error('Failed to fetch player stats')
      const data = await response.json()
      setStats(data)
    } catch (error) {
      console.error('Error fetching player stats:', error)
    } finally {
      setLoading(false)
    }
  }

  if (loading || !stats) {
    return compact ? (
      <div className="flex items-center space-x-2 px-3 py-1.5 bg-gray-100 rounded-full">
        <div className="h-4 w-4 bg-gray-300 rounded-full animate-pulse"></div>
        <div className="h-4 w-16 bg-gray-300 rounded animate-pulse"></div>
      </div>
    ) : null
  }

  const levelProgress = ((stats.total_points % ((stats.player_level) ** 2 * 10)) / ((stats.player_level) ** 2 * 10)) * 100
  const nextLevelPoints = (stats.player_level) ** 2 * 10

  if (compact) {
    // Compact version for header/toolbar
    return (
      <div className="flex items-center space-x-2 px-3 py-1.5 bg-gradient-to-r from-indigo-500 to-purple-600 rounded-full text-white shadow-md">
        <SparklesIcon className="h-4 w-4" />
        <span className="font-bold text-sm">Lvl {stats.player_level}</span>
        <span className="text-xs opacity-90">•</span>
        <TrophyIcon className="h-4 w-4" />
        <span className="font-medium text-sm">{stats.total_points}</span>
      </div>
    )
  }

  // Full version with progress bar
  return (
    <div className="bg-white rounded-lg shadow-md p-4 border-2 border-indigo-500">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center">
          <div className="h-12 w-12 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-full flex items-center justify-center text-white font-bold text-lg shadow-lg">
            {stats.player_level}
          </div>
          <div className="ml-3">
            <div className="text-lg font-bold text-gray-900">Level {stats.player_level}</div>
            <div className="text-sm text-gray-600 flex items-center">
              <TrophyIcon className="h-4 w-4 mr-1 text-yellow-500" />
              {stats.total_points} points
            </div>
          </div>
        </div>
        <div className="text-right">
          <div className="text-xs text-gray-500">Achievements</div>
          <div className="text-2xl font-bold text-indigo-600">{stats.total_achievements_unlocked}</div>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="space-y-1">
        <div className="flex justify-between text-xs text-gray-600">
          <span>{Math.floor(levelProgress)}% to Level {stats.player_level + 1}</span>
          <span>{stats.total_points % nextLevelPoints} / {nextLevelPoints} pts</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2.5">
          <div
            className="bg-gradient-to-r from-indigo-500 to-purple-600 h-2.5 rounded-full transition-all duration-500"
            style={{ width: `${Math.min(levelProgress, 100)}%` }}
          />
        </div>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-3 gap-3 mt-4 pt-4 border-t border-gray-200">
        <div className="text-center">
          <div className="text-xs text-gray-500">Games</div>
          <div className="text-lg font-bold text-gray-900">{stats.total_games_played}</div>
        </div>
        <div className="text-center">
          <div className="text-xs text-gray-500">Win Rate</div>
          <div className="text-lg font-bold text-gray-900">
            {stats.total_games_played > 0
              ? `${Math.round((stats.total_games_won / stats.total_games_played) * 100)}%`
              : '0%'}
          </div>
        </div>
        <div className="text-center">
          <div className="text-xs text-gray-500">Streak</div>
          <div className="text-lg font-bold text-gray-900">{stats.consecutive_wins}</div>
        </div>
      </div>
    </div>
  )
}

export default PlayerProfileBadge
