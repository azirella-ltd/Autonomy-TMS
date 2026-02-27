import React, { useState, useEffect } from 'react'
import {
  DocumentChartBarIcon,
  ArrowDownTrayIcon,
  ChartBarIcon,
  TableCellsIcon,
  LightBulbIcon
} from '@heroicons/react/24/outline'
import { toast } from 'react-toastify'
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts'

const ReportsPanel = ({ scenarioId }) => {
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(true)
  const [exporting, setExporting] = useState(false)
  const [activeSection, setActiveSection] = useState('overview')

  useEffect(() => {
    if (scenarioId) {
      fetchReport()
    }
  }, [scenarioId])

  const fetchReport = async () => {
    try {
      setLoading(true)
      const response = await fetch(`/api/v1/reports/scenarios/${scenarioId}`, {
        credentials: 'include'
      })

      if (!response.ok) {
        throw new Error(`Failed to fetch report: ${response.statusText}`)
      }

      const data = await response.json()
      setReport(data)
    } catch (error) {
      console.error('Error fetching report:', error)
      toast.error('Failed to load scenario report')
    } finally {
      setLoading(false)
    }
  }

  const exportReport = async (format) => {
    try {
      setExporting(true)
      const response = await fetch(
        `/api/v1/reports/scenarios/${scenarioId}/export?format=${format}&include_rounds=true`,
        {
          credentials: 'include'
        }
      )

      if (!response.ok) {
        throw new Error(`Export failed: ${response.statusText}`)
      }

      // Get filename from Content-Disposition header or use default
      const contentDisposition = response.headers.get('content-disposition')
      let filename = `game_${scenarioId}_report.${format}`
      if (contentDisposition) {
        const matches = /filename="?([^"]+)"?/.exec(contentDisposition)
        if (matches) filename = matches[1]
      }

      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)

      toast.success(`Report exported as ${format.toUpperCase()}`)
    } catch (error) {
      console.error('Error exporting report:', error)
      toast.error(`Failed to export report as ${format.toUpperCase()}`)
    } finally {
      setExporting(false)
    }
  }

  const printReport = () => {
    window.print()
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Generating report...</p>
        </div>
      </div>
    )
  }

  if (!report) {
    return (
      <div className="text-center py-12">
        <DocumentChartBarIcon className="h-16 w-16 text-gray-400 mx-auto mb-4" />
        <p className="text-gray-600">No report available for this game</p>
      </div>
    )
  }

  const { overview, scenario_user_performance, key_insights, recommendations, charts_data } = report

  return (
    <div className="space-y-6">
      {/* Header with Export Buttons */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center">
            <DocumentChartBarIcon className="h-8 w-8 text-indigo-600 mr-3" />
            <div>
              <h2 className="text-2xl font-bold text-gray-900">Scenario Report</h2>
              <p className="text-sm text-gray-600">
                {overview.config_name} - {overview.status}
              </p>
            </div>
          </div>

          {/* Export Actions */}
          <div className="flex space-x-2">
            <button
              onClick={() => exportReport('csv')}
              disabled={exporting}
              className="flex items-center px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors"
            >
              <TableCellsIcon className="h-5 w-5 mr-2" />
              CSV
            </button>
            <button
              onClick={() => exportReport('json')}
              disabled={exporting}
              className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              <ArrowDownTrayIcon className="h-5 w-5 mr-2" />
              JSON
            </button>
            <button
              onClick={() => exportReport('excel')}
              disabled={exporting}
              className="flex items-center px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
            >
              <ChartBarIcon className="h-5 w-5 mr-2" />
              Excel
            </button>
            <button
              onClick={printReport}
              className="flex items-center px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition-colors"
            >
              🖨️ Print
            </button>
          </div>
        </div>

        {/* Section Navigation */}
        <div className="flex space-x-2 border-t pt-4">
          <button
            onClick={() => setActiveSection('overview')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              activeSection === 'overview'
                ? 'bg-indigo-100 text-indigo-700'
                : 'text-gray-600 hover:bg-gray-100'
            }`}
          >
            Overview
          </button>
          <button
            onClick={() => setActiveSection('performance')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              activeSection === 'performance'
                ? 'bg-indigo-100 text-indigo-700'
                : 'text-gray-600 hover:bg-gray-100'
            }`}
          >
            Performance
          </button>
          <button
            onClick={() => setActiveSection('charts')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              activeSection === 'charts'
                ? 'bg-indigo-100 text-indigo-700'
                : 'text-gray-600 hover:bg-gray-100'
            }`}
          >
            Charts
          </button>
          <button
            onClick={() => setActiveSection('insights')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              activeSection === 'insights'
                ? 'bg-indigo-100 text-indigo-700'
                : 'text-gray-600 hover:bg-gray-100'
            }`}
          >
            Insights
          </button>
        </div>
      </div>

      {/* Overview Section */}
      {activeSection === 'overview' && (
        <div className="bg-white rounded-lg shadow-md p-6">
          <h3 className="text-xl font-bold text-gray-900 mb-4">Scenario Completeview</h3>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <MetricCard
              title="Total Cost"
              value={overview.total_cost?.toFixed(2) || 'N/A'}
              icon="💰"
              color="text-red-600"
            />
            <MetricCard
              title="Service Level"
              value={overview.service_level ? `${(overview.service_level * 100).toFixed(1)}%` : 'N/A'}
              icon="📊"
              color="text-green-600"
            />
            <MetricCard
              title="Avg Inventory"
              value={overview.avg_inventory?.toFixed(1) || 'N/A'}
              icon="📦"
              color="text-blue-600"
            />
            <MetricCard
              title="Bullwhip Effect"
              value={overview.bullwhip_effect?.toFixed(2) || 'N/A'}
              icon="📈"
              color="text-orange-600"
            />
          </div>

          <div className="mt-6 grid grid-cols-2 gap-4">
            <div className="border rounded-lg p-4">
              <p className="text-sm text-gray-600">Rounds Played</p>
              <p className="text-2xl font-bold text-gray-900">
                {overview.rounds_played} / {overview.total_rounds}
              </p>
            </div>
            <div className="border rounded-lg p-4">
              <p className="text-sm text-gray-600">Duration</p>
              <p className="text-2xl font-bold text-gray-900">{overview.duration}</p>
            </div>
          </div>
        </div>
      )}

      {/* Performance Section */}
      {activeSection === 'performance' && (
        <div className="bg-white rounded-lg shadow-md p-6">
          <h3 className="text-xl font-bold text-gray-900 mb-4">User Performance</h3>

          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Rank
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Role
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Total Cost
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Service Level
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Avg Inventory
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Orders
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Order Variance
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {scenario_user_performance.map((scenarioUser, index) => (
                  <tr key={user.scenario_user_id} className={index < 3 ? 'bg-yellow-50' : ''}>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="text-2xl">
                        {index === 0 ? '🥇' : index === 1 ? '🥈' : index === 2 ? '🥉' : index + 1}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap font-medium text-gray-900">
                      {user.role}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      ${user.total_cost.toFixed(2)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {user.service_level ? `${(user.service_level * 100).toFixed(1)}%` : 'N/A'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {user.avg_inventory?.toFixed(1) || 'N/A'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {user.orders_placed}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {user.order_variance?.toFixed(2) || 'N/A'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Charts Section */}
      {activeSection === 'charts' && (
        <div className="space-y-6">
          {/* Inventory Trend */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <h3 className="text-lg font-bold text-gray-900 mb-4">Inventory Trend</h3>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={charts_data.inventory_trend}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="round" label={{ value: 'Round', position: 'insideBottom', offset: -5 }} />
                <YAxis label={{ value: 'Inventory', angle: -90, position: 'insideLeft' }} />
                <Tooltip />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="avg_inventory"
                  stroke="#8b5cf6"
                  strokeWidth={2}
                  name="Avg Inventory"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Order Pattern */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <h3 className="text-lg font-bold text-gray-900 mb-4">Order Pattern</h3>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={charts_data.order_pattern}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="round" label={{ value: 'Round', position: 'insideBottom', offset: -5 }} />
                <YAxis label={{ value: 'Orders', angle: -90, position: 'insideLeft' }} />
                <Tooltip />
                <Legend />
                <Bar dataKey="avg_orders" fill="#3b82f6" name="Avg Orders" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Cost Accumulation */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <h3 className="text-lg font-bold text-gray-900 mb-4">Cost Accumulation</h3>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={charts_data.cost_accumulation}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="round" label={{ value: 'Round', position: 'insideBottom', offset: -5 }} />
                <YAxis label={{ value: 'Cost', angle: -90, position: 'insideLeft' }} />
                <Tooltip />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="total_cost"
                  stroke="#ef4444"
                  strokeWidth={2}
                  name="Total Cost"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Insights Section */}
      {activeSection === 'insights' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Key Insights */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <div className="flex items-center mb-4">
              <LightBulbIcon className="h-6 w-6 text-yellow-500 mr-2" />
              <h3 className="text-lg font-bold text-gray-900">Key Insights</h3>
            </div>
            <ul className="space-y-3">
              {key_insights.map((insight, index) => (
                <li key={index} className="flex items-start">
                  <span className="inline-block w-6 h-6 bg-blue-100 text-blue-600 rounded-full flex items-center justify-center text-sm font-bold mr-3 flex-shrink-0 mt-0.5">
                    {index + 1}
                  </span>
                  <span className="text-gray-700">{insight}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Recommendations */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <div className="flex items-center mb-4">
              <span className="text-2xl mr-2">💡</span>
              <h3 className="text-lg font-bold text-gray-900">Recommendations</h3>
            </div>
            <ul className="space-y-3">
              {recommendations.map((rec, index) => (
                <li key={index} className="flex items-start">
                  <span className="inline-block w-6 h-6 bg-green-100 text-green-600 rounded-full flex items-center justify-center text-sm font-bold mr-3 flex-shrink-0 mt-0.5">
                    ✓
                  </span>
                  <span className="text-gray-700">{rec}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  )
}

// Metric Card Component
const MetricCard = ({ title, value, icon, color }) => {
  return (
    <div className="bg-gradient-to-br from-gray-50 to-white border border-gray-200 rounded-lg p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-gray-600">{title}</span>
        <span className="text-2xl">{icon}</span>
      </div>
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
    </div>
  )
}

export default ReportsPanel
