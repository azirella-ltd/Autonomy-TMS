import React, { useState, useEffect } from 'react'
import { TrophyIcon, CheckCircleIcon, LockClosedIcon } from '@heroicons/react/24/outline'
import { toast } from 'react-toastify'

const AchievementsPanel = ({ scenarioId, scenarioUserId }) => {
  const [achievements, setAchievements] = useState([])
  const [allAchievements, setAllAchievements] = useState([])
  const [scenarioUserStats, setScenarioUserStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all') // all, unlocked, locked
  const [categoryFilter, setCategoryFilter] = useState('all')

  useEffect(() => {
    if (scenarioUserId) {
      fetchAchievements()
      fetchScenarioUserStats()
    }
  }, [scenarioUserId])

  const fetchAchievements = async () => {
    try {
      setLoading(true)

      // Fetch all available achievements
      const allResponse = await fetch('/api/v1/gamification/achievements', {
        credentials: 'include'
      })
      if (!allResponse.ok) throw new Error('Failed to fetch achievements')
      const allData = await allResponse.json()
      setAllAchievements(allData)

      // Fetch scenarioUser's unlocked achievements
      const playerResponse = await fetch(`/api/v1/gamification/scenarioUsers/${scenarioUserId}/achievements`, {
        credentials: 'include'
      })
      if (!playerResponse.ok) throw new Error('Failed to fetch scenarioUser achievements')
      const scenarioUserData = await playerResponse.json()
      setAchievements(scenarioUserData)
    } catch (error) {
      console.error('Error fetching achievements:', error)
      toast.error('Failed to load achievements')
    } finally {
      setLoading(false)
    }
  }

  const fetchScenarioUserStats = async () => {
    try {
      const response = await fetch(`/api/v1/gamification/scenarioUsers/${scenarioUserId}/stats`, {
        credentials: 'include'
      })
      if (!response.ok) throw new Error('Failed to fetch scenarioUser stats')
      const data = await response.json()
      setScenarioUserStats(data)
    } catch (error) {
      console.error('Error fetching scenarioUser stats:', error)
    }
  }

  const checkForNewAchievements = async () => {
    try {
      const response = await fetch(
        `/api/v1/gamification/scenarioUsers/${scenarioUserId}/check-achievements?scenario_id=${scenarioId}`,
        {
          method: 'POST',
          credentials: 'include'
        }
      )
      if (!response.ok) throw new Error('Failed to check achievements')
      const data = await response.json()

      if (data.newly_unlocked && data.newly_unlocked.length > 0) {
        // Show toast for each newly unlocked achievement
        data.newly_unlocked.forEach(achievement => {
          toast.success(
            <div className="flex items-center">
              <TrophyIcon className="h-5 w-5 text-yellow-500 mr-2" />
              <div>
                <div className="font-bold">Achievement Unlocked!</div>
                <div>{achievement.name}</div>
              </div>
            </div>,
            { autoClose: 5000 }
          )
        })

        // Refresh data
        await fetchAchievements()
        await fetchScenarioUserStats()
      }

      if (data.level_up) {
        toast.info(`🎉 Level Up! You're now Level ${data.new_level}!`, { autoClose: 5000 })
      }
    } catch (error) {
      console.error('Error checking achievements:', error)
    }
  }

  const unlockedAchievementIds = new Set(achievements.map(a => a.achievement_id))

  const filteredAchievements = allAchievements.filter(ach => {
    const isUnlocked = unlockedAchievementIds.has(ach.id)

    // Filter by unlock status
    if (filter === 'unlocked' && !isUnlocked) return false
    if (filter === 'locked' && isUnlocked) return false

    // Filter by category
    if (categoryFilter !== 'all' && ach.category !== categoryFilter) return false

    return true
  })

  const getRarityColor = (rarity) => {
    switch (rarity) {
      case 'common': return 'text-gray-600 bg-gray-100'
      case 'uncommon': return 'text-green-600 bg-green-100'
      case 'rare': return 'text-blue-600 bg-blue-100'
      case 'epic': return 'text-purple-600 bg-purple-100'
      case 'legendary': return 'text-yellow-600 bg-yellow-100'
      default: return 'text-gray-600 bg-gray-100'
    }
  }

  const getCategoryIcon = (category) => {
    switch (category) {
      case 'progression': return '📈'
      case 'performance': return '⚡'
      case 'social': return '👥'
      case 'mastery': return '🏆'
      case 'special': return '⭐'
      default: return '🎯'
    }
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
      {/* ScenarioUser Stats Header */}
      {scenarioUserStats && (
        <div className="bg-gradient-to-r from-indigo-500 to-purple-600 rounded-lg p-6 text-white">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-2xl font-bold flex items-center">
                <TrophyIcon className="h-8 w-8 mr-2" />
                Level {scenarioUserStats.scenario_user_level}
              </h2>
              <p className="text-indigo-100 mt-1">
                {scenarioUserStats.total_points} points • {scenarioUserStats.total_achievements_unlocked} achievements
              </p>
            </div>
            <button
              onClick={checkForNewAchievements}
              className="bg-white text-indigo-600 px-4 py-2 rounded-lg font-semibold hover:bg-indigo-50 transition-colors"
            >
              Check Progress
            </button>
          </div>

          {/* Progress Bar */}
          <div className="mt-4">
            <div className="flex justify-between text-sm mb-1">
              <span>Level {scenarioUserStats.scenario_user_level}</span>
              <span>Level {scenarioUserStats.scenario_user_level + 1}</span>
            </div>
            <div className="w-full bg-indigo-700 rounded-full h-3">
              <div
                className="bg-white rounded-full h-3 transition-all duration-500"
                style={{
                  width: `${Math.min(
                    (scenarioUserStats.total_points % ((scenarioUserStats.scenario_user_level) ** 2 * 10)) /
                    ((scenarioUserStats.scenario_user_level) ** 2 * 10) * 100,
                    100
                  )}%`
                }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        {/* Status Filter */}
        <div className="flex gap-2">
          <button
            onClick={() => setFilter('all')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              filter === 'all'
                ? 'bg-indigo-600 text-white'
                : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
            }`}
          >
            All ({allAchievements.length})
          </button>
          <button
            onClick={() => setFilter('unlocked')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              filter === 'unlocked'
                ? 'bg-green-600 text-white'
                : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
            }`}
          >
            Unlocked ({achievements.length})
          </button>
          <button
            onClick={() => setFilter('locked')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              filter === 'locked'
                ? 'bg-gray-600 text-white'
                : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
            }`}
          >
            Locked ({allAchievements.length - achievements.length})
          </button>
        </div>

        {/* Category Filter */}
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
        >
          <option value="all">All Categories</option>
          <option value="progression">📈 Progression</option>
          <option value="performance">⚡ Performance</option>
          <option value="social">👥 Social</option>
          <option value="mastery">🏆 Mastery</option>
          <option value="special">⭐ Special</option>
        </select>
      </div>

      {/* Achievements Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredAchievements.map((achievement) => {
          const isUnlocked = unlockedAchievementIds.has(achievement.id)
          const playerAchievement = achievements.find(a => a.achievement_id === achievement.id)

          return (
            <div
              key={achievement.id}
              className={`rounded-lg border-2 p-4 transition-all ${
                isUnlocked
                  ? 'border-green-500 bg-white shadow-md'
                  : 'border-gray-300 bg-gray-50 opacity-60'
              }`}
            >
              {/* Header */}
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center">
                  <span className="text-3xl mr-2">{getCategoryIcon(achievement.category)}</span>
                  {isUnlocked ? (
                    <CheckCircleIcon className="h-6 w-6 text-green-500" />
                  ) : (
                    <LockClosedIcon className="h-6 w-6 text-gray-400" />
                  )}
                </div>
                <span className={`px-2 py-1 rounded-full text-xs font-semibold ${getRarityColor(achievement.rarity)}`}>
                  {achievement.rarity}
                </span>
              </div>

              {/* Title */}
              <h3 className={`font-bold text-lg mb-1 ${isUnlocked ? 'text-gray-900' : 'text-gray-500'}`}>
                {achievement.name}
              </h3>

              {/* Description */}
              <p className={`text-sm mb-3 ${isUnlocked ? 'text-gray-600' : 'text-gray-400'}`}>
                {achievement.description}
              </p>

              {/* Footer */}
              <div className="flex items-center justify-between pt-3 border-t border-gray-200">
                <span className={`text-sm font-medium ${isUnlocked ? 'text-indigo-600' : 'text-gray-400'}`}>
                  {achievement.points} points
                </span>
                {isUnlocked && playerAchievement && (
                  <span className="text-xs text-gray-500">
                    {new Date(playerAchievement.unlocked_at).toLocaleDateString()}
                  </span>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* Empty State */}
      {filteredAchievements.length === 0 && (
        <div className="text-center py-12">
          <TrophyIcon className="h-16 w-16 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500 text-lg">No achievements found with current filters</p>
        </div>
      )}
    </div>
  )
}

export default AchievementsPanel
