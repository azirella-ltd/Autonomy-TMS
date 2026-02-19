import React, { useState, useEffect } from 'react'
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import {
  ChartBarIcon,
  ArrowTrendingUpIcon,
  ExclamationTriangleIcon,
  LightBulbIcon,
  CpuChipIcon,
} from '@heroicons/react/24/outline'
import { api } from '../../services/api'

const PredictiveAnalyticsDashboard = ({ gameId, siteId, onClose }) => {
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('forecast') // forecast, bullwhip, cost, shap, whatif
  const [demandForecast, setDemandForecast] = useState(null)
  const [bullwhipPrediction, setBullwhipPrediction] = useState(null)
  const [costTrajectory, setCostTrajectory] = useState(null)
  const [shapExplanation, setShapExplanation] = useState(null)
  const [whatIfResults, setWhatIfResults] = useState(null)

  useEffect(() => {
    loadAllAnalytics()
  }, [gameId, siteId])

  const loadAllAnalytics = async () => {
    setLoading(true)
    try {
      // Load all analytics in parallel
      const [forecast, bullwhip, cost] = await Promise.all([
        loadDemandForecast(),
        loadBullwhipPrediction(),
        loadCostTrajectory(),
      ])

      setDemandForecast(forecast)
      setBullwhipPrediction(bullwhip)
      setCostTrajectory(cost)
    } catch (error) {
      console.error('Failed to load analytics:', error)
    } finally {
      setLoading(false)
    }
  }

  const loadDemandForecast = async () => {
    try {
      const response = await api.post('/predictive-analytics/forecast/demand', {
        game_id: gameId,
        site_id: siteId,
        horizon: 10,
        confidence_level: 0.95,
      })
      return response.data
    } catch (error) {
      console.error('Failed to load demand forecast:', error)
      return null
    }
  }

  const loadBullwhipPrediction = async () => {
    try {
      const response = await api.post('/predictive-analytics/predict/bullwhip', {
        game_id: gameId,
      })
      return response.data
    } catch (error) {
      console.error('Failed to load bullwhip prediction:', error)
      return null
    }
  }

  const loadCostTrajectory = async () => {
    try {
      const response = await api.post('/predictive-analytics/forecast/cost-trajectory', {
        game_id: gameId,
        site_id: siteId,
        horizon: 10,
      })
      return response.data
    } catch (error) {
      console.error('Failed to load cost trajectory:', error)
      return null
    }
  }

  const loadShapExplanation = async (roundNumber) => {
    try {
      const response = await api.post('/predictive-analytics/explain/prediction', {
        game_id: gameId,
        site_id: siteId,
        round_number: roundNumber,
      })
      setShapExplanation(response.data)
    } catch (error) {
      console.error('Failed to load SHAP explanation:', error)
    }
  }

  const runWhatIfAnalysis = async (scenarios) => {
    try {
      const response = await api.post('/predictive-analytics/analyze/what-if', {
        game_id: gameId,
        site_id: siteId,
        scenarios: scenarios,
      })
      setWhatIfResults(response.data)
    } catch (error) {
      console.error('Failed to run what-if analysis:', error)
    }
  }

  // Render Demand Forecast Tab
  const renderDemandForecast = () => {
    if (!demandForecast || !demandForecast.forecasts) {
      return <div className="text-center text-gray-600 py-8">No forecast data available</div>
    }

    const chartData = demandForecast.forecasts.map((f) => ({
      timestep: `T+${f.timestep}`,
      forecast: f.value,
      lower: f.lower_bound,
      upper: f.upper_bound,
    }))

    return (
      <div className="space-y-6">
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <div className="flex items-center">
            <ArrowTrendingUpIcon className="h-6 w-6 text-blue-600 mr-2" />
            <div>
              <div className="font-medium text-blue-900">Demand Forecasting</div>
              <div className="text-sm text-blue-700">
                Predict future demand with {(demandForecast.metadata.confidence_level * 100).toFixed(0)}% confidence bounds
              </div>
            </div>
          </div>
        </div>

        <ResponsiveContainer width="100%" height={400}>
          <AreaChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="timestep" />
            <YAxis />
            <Tooltip />
            <Legend />
            <Area
              type="monotone"
              dataKey="upper"
              stackId="1"
              stroke="#93c5fd"
              fill="#dbeafe"
              name="Upper Bound"
            />
            <Area
              type="monotone"
              dataKey="forecast"
              stackId="2"
              stroke="#3b82f6"
              fill="#60a5fa"
              name="Forecast"
            />
            <Area
              type="monotone"
              dataKey="lower"
              stackId="3"
              stroke="#2563eb"
              fill="#3b82f6"
              name="Lower Bound"
            />
          </AreaChart>
        </ResponsiveContainer>

        <div className="grid grid-cols-3 gap-4">
          <div className="bg-white border rounded-lg p-4">
            <div className="text-sm text-gray-600">Avg Forecast</div>
            <div className="text-2xl font-bold text-gray-900">
              {(
                demandForecast.forecasts.reduce((sum, f) => sum + f.value, 0) /
                demandForecast.forecasts.length
              ).toFixed(1)}
            </div>
          </div>
          <div className="bg-white border rounded-lg p-4">
            <div className="text-sm text-gray-600">Uncertainty Range</div>
            <div className="text-2xl font-bold text-gray-900">
              ±
              {(
                demandForecast.forecasts.reduce(
                  (sum, f) => sum + (f.upper_bound - f.lower_bound),
                  0
                ) / demandForecast.forecasts.length
              ).toFixed(1)}
            </div>
          </div>
          <div className="bg-white border rounded-lg p-4">
            <div className="text-sm text-gray-600">Horizon</div>
            <div className="text-2xl font-bold text-gray-900">
              {demandForecast.metadata.horizon} rounds
            </div>
          </div>
        </div>
      </div>
    )
  }

  // Render Bullwhip Prediction Tab
  const renderBullwhipPrediction = () => {
    if (!bullwhipPrediction || !bullwhipPrediction.predictions) {
      return <div className="text-center text-gray-600 py-8">No bullwhip data available</div>
    }

    const getRiskColor = (level) => {
      switch (level) {
        case 'high':
          return 'text-red-600 bg-red-50 border-red-200'
        case 'medium':
          return 'text-yellow-600 bg-yellow-50 border-yellow-200'
        case 'low':
          return 'text-green-600 bg-green-50 border-green-200'
        default:
          return 'text-gray-600 bg-gray-50 border-gray-200'
      }
    }

    return (
      <div className="space-y-6">
        <div className="bg-purple-50 border border-purple-200 rounded-lg p-4">
          <div className="flex items-center">
            <ExclamationTriangleIcon className="h-6 w-6 text-purple-600 mr-2" />
            <div>
              <div className="font-medium text-purple-900">Bullwhip Effect Prediction</div>
              <div className="text-sm text-purple-700">
                Overall Risk: {bullwhipPrediction.summary.overall_risk.toUpperCase()}
              </div>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-4">
          <div className="bg-white border rounded-lg p-4">
            <div className="text-sm text-gray-600">Avg Predicted Ratio</div>
            <div className="text-2xl font-bold text-gray-900">
              {bullwhipPrediction.summary.average_predicted_ratio.toFixed(2)}
            </div>
          </div>
          <div className="bg-white border rounded-lg p-4">
            <div className="text-sm text-gray-600">High Risk Sites</div>
            <div className="text-2xl font-bold text-red-600">
              {bullwhipPrediction.summary.high_risk_sites ?? bullwhipPrediction.summary.high_risk_nodes}
            </div>
          </div>
          <div className="bg-white border rounded-lg p-4">
            <div className="text-sm text-gray-600">Medium Risk Sites</div>
            <div className="text-2xl font-bold text-yellow-600">
              {bullwhipPrediction.summary.medium_risk_sites ?? bullwhipPrediction.summary.medium_risk_nodes}
            </div>
          </div>
        </div>

        <div className="space-y-3">
          {bullwhipPrediction.predictions.map((pred) => (
            <div
              key={pred.site_id ?? pred.node_id}
              className={`border rounded-lg p-4 ${getRiskColor(pred.risk_level)}`}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="font-medium">{pred.site_role ?? pred.node_role}</div>
                <div className="text-sm font-medium uppercase">{pred.risk_level} RISK</div>
              </div>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <div className="text-gray-600">Current Ratio</div>
                  <div className="font-medium">{pred.current_ratio.toFixed(2)}</div>
                </div>
                <div>
                  <div className="text-gray-600">Predicted Ratio</div>
                  <div className="font-medium">{pred.predicted_ratio.toFixed(2)}</div>
                </div>
              </div>
              {pred.contributing_factors && (
                <div className="mt-2 pt-2 border-t">
                  <div className="text-xs text-gray-600 mb-1">Contributing Factors:</div>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    {Object.entries(pred.contributing_factors).map(([factor, value]) => (
                      <div key={factor}>
                        <span className="text-gray-600">{factor}:</span>{' '}
                        <span className="font-medium">{value.toFixed(3)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    )
  }

  // Render Cost Trajectory Tab
  const renderCostTrajectory = () => {
    if (!costTrajectory || !costTrajectory.trajectory) {
      return <div className="text-center text-gray-600 py-8">No cost data available</div>
    }

    const traj = costTrajectory.trajectory
    const chartData = traj.forecasted_costs.map((cost, index) => ({
      round: `T+${index + 1}`,
      best: traj.risk_scenarios.best[index],
      likely: cost,
      worst: traj.risk_scenarios.worst[index],
    }))

    return (
      <div className="space-y-6">
        <div className="bg-green-50 border border-green-200 rounded-lg p-4">
          <div className="flex items-center">
            <ChartBarIcon className="h-6 w-6 text-green-600 mr-2" />
            <div>
              <div className="font-medium text-green-900">Cost Trajectory Forecast</div>
              <div className="text-sm text-green-700">{traj.node_role}</div>
            </div>
          </div>
        </div>

        <ResponsiveContainer width="100%" height={400}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="round" />
            <YAxis />
            <Tooltip />
            <Legend />
            <ReferenceLine
              y={traj.current_cost}
              label="Current"
              stroke="#6b7280"
              strokeDasharray="5 5"
            />
            <Line
              type="monotone"
              dataKey="best"
              stroke="#10b981"
              strokeWidth={2}
              name="Best Case"
            />
            <Line
              type="monotone"
              dataKey="likely"
              stroke="#3b82f6"
              strokeWidth={3}
              name="Likely"
            />
            <Line
              type="monotone"
              dataKey="worst"
              stroke="#ef4444"
              strokeWidth={2}
              name="Worst Case"
            />
          </LineChart>
        </ResponsiveContainer>

        <div className="grid grid-cols-3 gap-4">
          <div className="bg-white border border-green-200 rounded-lg p-4">
            <div className="text-sm text-gray-600">Best Case</div>
            <div className="text-2xl font-bold text-green-600">
              ${traj.risk_scenarios.best[traj.risk_scenarios.best.length - 1].toFixed(2)}
            </div>
          </div>
          <div className="bg-white border border-blue-200 rounded-lg p-4">
            <div className="text-sm text-gray-600">Likely</div>
            <div className="text-2xl font-bold text-blue-600">${traj.expected_total.toFixed(2)}</div>
          </div>
          <div className="bg-white border border-red-200 rounded-lg p-4">
            <div className="text-sm text-gray-600">Worst Case</div>
            <div className="text-2xl font-bold text-red-600">
              ${traj.risk_scenarios.worst[traj.risk_scenarios.worst.length - 1].toFixed(2)}
            </div>
          </div>
        </div>

        {costTrajectory.insights && costTrajectory.insights.length > 0 && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
            <div className="flex items-start">
              <LightBulbIcon className="h-5 w-5 text-yellow-600 mr-2 mt-0.5" />
              <div>
                <div className="font-medium text-yellow-900 mb-1">Insights</div>
                <ul className="text-sm text-yellow-800 space-y-1">
                  {costTrajectory.insights.map((insight, index) => (
                    <li key={index}>• {insight}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        )}
      </div>
    )
  }

  // Render tabs
  const tabs = [
    { id: 'forecast', label: 'Demand Forecast', icon: ArrowTrendingUpIcon },
    { id: 'bullwhip', label: 'Bullwhip Risk', icon: ExclamationTriangleIcon },
    { id: 'cost', label: 'Cost Trajectory', icon: ChartBarIcon },
  ]

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-center">
          <CpuChipIcon className="h-12 w-12 text-indigo-600 mx-auto mb-2 animate-pulse" />
          <div className="text-gray-600">Loading predictive analytics...</div>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg shadow-lg">
      {/* Header */}
      <div className="border-b px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-gray-900">Predictive Analytics</h2>
            <p className="text-sm text-gray-600 mt-1">AI-powered forecasting and insights</p>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 transition-colors"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b">
        <div className="flex space-x-1 px-6">
          {tabs.map((tab) => {
            const Icon = tab.icon
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center px-4 py-3 border-b-2 font-medium text-sm transition-colors ${
                  activeTab === tab.id
                    ? 'border-indigo-600 text-indigo-600'
                    : 'border-transparent text-gray-600 hover:text-gray-900 hover:border-gray-300'
                }`}
              >
                <Icon className="h-5 w-5 mr-2" />
                {tab.label}
              </button>
            )
          })}
        </div>
      </div>

      {/* Content */}
      <div className="p-6">
        {activeTab === 'forecast' && renderDemandForecast()}
        {activeTab === 'bullwhip' && renderBullwhipPrediction()}
        {activeTab === 'cost' && renderCostTrajectory()}
      </div>
    </div>
  )
}

export default PredictiveAnalyticsDashboard
