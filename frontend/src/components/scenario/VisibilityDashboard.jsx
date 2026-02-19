import { useState, useEffect } from "react";
import {
  EyeIcon,
  ChartBarIcon,
  ExclamationTriangleIcon,
  ArrowTrendingUpIcon,
  Cog6ToothIcon,
} from "@heroicons/react/24/outline";
import { toast } from "react-toastify";
import simulationApi from "../../services/api";

/**
 * VisibilityDashboard Component
 * Phase 7 Sprint 4 - Feature 3: Supply Chain Visibility
 *
 * Provides opt-in supply chain visibility with:
 * - Health score monitoring
 * - Bottleneck detection
 * - Bullwhip effect measurement
 * - Sharing permission controls
 */
const VisibilityDashboard = ({ scenarioId }) => {
  const [healthData, setHealthData] = useState(null);
  const [bottlenecks, setBottlenecks] = useState(null);
  const [bullwhipData, setBullwhipData] = useState(null);
  const [permissions, setPermissions] = useState({
    share_inventory: false,
    share_backlog: false,
    share_orders: false,
  });
  const [allPermissions, setAllPermissions] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [showSettings, setShowSettings] = useState(false);

  useEffect(() => {
    fetchVisibilityData();
  }, [scenarioId]);

  const fetchVisibilityData = async () => {
    try {
      setIsLoading(true);

      // Fetch all visibility data in parallel
      const [health, bottleneckData, bullwhip, perms] = await Promise.all([
        simulationApi.getSupplyChainHealth(scenarioId),
        simulationApi.detectBottlenecks(scenarioId),
        simulationApi.measureBullwhip(scenarioId),
        simulationApi.getVisibilityPermissions(scenarioId),
      ]);

      setHealthData(health);
      setBottlenecks(bottleneckData);
      setBullwhipData(bullwhip);
      setAllPermissions(perms);
    } catch (error) {
      console.error("Failed to fetch visibility data:", error);
      toast.error("Failed to load visibility dashboard");
    } finally {
      setIsLoading(false);
    }
  };

  const handlePermissionChange = async (permissionType, value) => {
    const newPermissions = { ...permissions, [permissionType]: value };
    setPermissions(newPermissions);

    try {
      await simulationApi.setVisibilityPermissions(gameId, newPermissions);
      toast.success("Sharing preferences updated");

      // Refresh permissions
      const perms = await simulationApi.getVisibilityPermissions(scenarioId);
      setAllPermissions(perms);
    } catch (error) {
      console.error("Failed to update permissions:", error);
      toast.error("Failed to update sharing preferences");
      // Revert on error
      setPermissions(permissions);
    }
  };

  const getHealthStatusColor = (status) => {
    switch (status) {
      case "excellent":
        return "text-green-600 bg-green-50 border-green-200";
      case "good":
        return "text-green-500 bg-green-50 border-green-100";
      case "moderate":
        return "text-yellow-600 bg-yellow-50 border-yellow-200";
      case "poor":
        return "text-orange-600 bg-orange-50 border-orange-200";
      case "critical":
        return "text-red-600 bg-red-50 border-red-200";
      default:
        return "text-gray-600 bg-gray-50 border-gray-200";
    }
  };

  const getSeverityColor = (severity) => {
    switch (severity) {
      case "critical":
        return "text-red-600 bg-red-50";
      case "high":
        return "text-orange-600 bg-orange-50";
      case "moderate":
        return "text-yellow-600 bg-yellow-50";
      case "low":
        return "text-green-600 bg-green-50";
      default:
        return "text-gray-600 bg-gray-50";
    }
  };

  const renderHealthScore = () => {
    if (!healthData) return null;

    const { health_score, components, status, insights } = healthData;

    return (
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
            <ChartBarIcon className="h-5 w-5 text-indigo-600" />
            Supply Chain Health
          </h3>
          <div
            className={`px-4 py-2 rounded-full border-2 font-semibold ${getHealthStatusColor(
              status
            )}`}
          >
            {Math.round(health_score)}/100 - {status.toUpperCase()}
          </div>
        </div>

        {/* Health Score Progress Bar */}
        <div className="mb-6">
          <div className="w-full bg-gray-200 rounded-full h-6">
            <div
              className={`h-6 rounded-full transition-all duration-500 ${
                health_score >= 80
                  ? "bg-green-500"
                  : health_score >= 50
                  ? "bg-yellow-500"
                  : "bg-red-500"
              }`}
              style={{ width: `${health_score}%` }}
            />
          </div>
        </div>

        {/* Component Scores */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
          {Object.entries(components).map(([key, value]) => (
            <div key={key} className="text-center">
              <div className="text-2xl font-bold text-gray-900">
                {Math.round(value)}
              </div>
              <div className="text-xs text-gray-500 capitalize">
                {key.replace(/_/g, " ")}
              </div>
            </div>
          ))}
        </div>

        {/* Insights */}
        {insights && insights.length > 0 && (
          <div className="border-t pt-4">
            <h4 className="text-sm font-medium text-gray-700 mb-2">Insights</h4>
            <ul className="space-y-1">
              {insights.map((insight, idx) => (
                <li key={idx} className="text-sm text-gray-600">
                  {insight}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );
  };

  const renderBottlenecks = () => {
    if (!bottlenecks) return null;

    const { bottlenecks: bottleneckList, supply_chain_flow } = bottlenecks;

    return (
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
            <ExclamationTriangleIcon className="h-5 w-5 text-orange-600" />
            Bottleneck Detection
          </h3>
          <div
            className={`px-3 py-1 rounded-full text-sm font-medium ${
              supply_chain_flow === "smooth"
                ? "bg-green-50 text-green-700"
                : supply_chain_flow === "restricted"
                ? "bg-yellow-50 text-yellow-700"
                : "bg-red-50 text-red-700"
            }`}
          >
            Flow: {supply_chain_flow}
          </div>
        </div>

        {bottleneckList.length === 0 ? (
          <div className="text-center py-8">
            <div className="text-green-600 mb-2">✅</div>
            <p className="text-sm text-gray-600">
              No bottlenecks detected - supply chain is flowing smoothly
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {bottleneckList.map((bottleneck, idx) => (
              <div
                key={idx}
                className={`border rounded-lg p-4 ${getSeverityColor(
                  bottleneck.severity
                )}`}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="font-semibold">{bottleneck.role}</div>
                  <div className="text-xs px-2 py-1 rounded bg-white">
                    {bottleneck.severity.toUpperCase()}
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-4 text-sm mb-2">
                  <div>
                    <div className="text-xs opacity-75">Backlog</div>
                    <div className="font-semibold">
                      {bottleneck.metrics.backlog}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs opacity-75">Inventory</div>
                    <div className="font-semibold">
                      {bottleneck.metrics.inventory}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs opacity-75">Service Level</div>
                    <div className="font-semibold">
                      {Math.round(bottleneck.metrics.service_level * 100)}%
                    </div>
                  </div>
                </div>

                <div className="text-sm mb-1">
                  <strong>Impact:</strong> {bottleneck.impact}
                </div>
                <div className="text-sm">
                  <strong>Recommendation:</strong> {bottleneck.recommendation}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  const renderBullwhip = () => {
    if (!bullwhipData) return null;

    const { severity, amplification_ratio, by_role, insights } = bullwhipData;

    return (
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
            <ArrowTrendingUpIcon className="h-5 w-5 text-purple-600" />
            Bullwhip Effect
          </h3>
          <div
            className={`px-3 py-1 rounded-full text-sm font-medium ${getSeverityColor(
              severity
            )}`}
          >
            {severity.toUpperCase()}
          </div>
        </div>

        {/* Amplification Ratio */}
        <div className="text-center mb-6">
          <div className="text-4xl font-bold text-gray-900">
            {amplification_ratio.toFixed(2)}x
          </div>
          <div className="text-sm text-gray-500">Demand Amplification Ratio</div>
          <div className="text-xs text-gray-400 mt-1">
            (Upstream variance / Downstream variance)
          </div>
        </div>

        {/* Role-specific metrics */}
        {by_role && Object.keys(by_role).length > 0 && (
          <div className="mb-6">
            <h4 className="text-sm font-medium text-gray-700 mb-3">
              Order Volatility by Role
            </h4>
            <div className="space-y-2">
              {Object.entries(by_role).map(([role, metrics]) => (
                <div key={role} className="flex items-center justify-between">
                  <div className="text-sm font-medium">{role}</div>
                  <div className="flex items-center gap-4 text-sm text-gray-600">
                    <div>
                      CV: <strong>{metrics.cv.toFixed(2)}</strong>
                    </div>
                    <div>
                      Avg: <strong>{metrics.avg_order.toFixed(0)}</strong>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Insights */}
        {insights && insights.length > 0 && (
          <div className="border-t pt-4">
            <h4 className="text-sm font-medium text-gray-700 mb-2">Analysis</h4>
            <ul className="space-y-1">
              {insights.map((insight, idx) => (
                <li key={idx} className="text-sm text-gray-600">
                  {insight}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );
  };

  const renderSharingSettings = () => {
    return (
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
            <Cog6ToothIcon className="h-5 w-5 text-gray-600" />
            Sharing Settings
          </h3>
          <button
            onClick={() => setShowSettings(!showSettings)}
            className="text-sm text-indigo-600 hover:text-indigo-700"
          >
            {showSettings ? "Hide" : "Configure"}
          </button>
        </div>

        {showSettings && (
          <div className="space-y-4 border-t pt-4">
            <p className="text-sm text-gray-600 mb-4">
              Opt-in to share your metrics with other players. Sharing reduces
              the bullwhip effect and improves coordination.
            </p>

            <div className="space-y-3">
              <label className="flex items-center justify-between p-3 border rounded hover:bg-gray-50 cursor-pointer">
                <div>
                  <div className="font-medium text-sm">Share Inventory Levels</div>
                  <div className="text-xs text-gray-500">
                    Let others see your current stock
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={permissions.share_inventory}
                  onChange={(e) =>
                    handlePermissionChange("share_inventory", e.target.checked)
                  }
                  className="h-5 w-5 text-indigo-600"
                />
              </label>

              <label className="flex items-center justify-between p-3 border rounded hover:bg-gray-50 cursor-pointer">
                <div>
                  <div className="font-medium text-sm">Share Backlog Levels</div>
                  <div className="text-xs text-gray-500">
                    Let others see your unfulfilled orders
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={permissions.share_backlog}
                  onChange={(e) =>
                    handlePermissionChange("share_backlog", e.target.checked)
                  }
                  className="h-5 w-5 text-indigo-600"
                />
              </label>

              <label className="flex items-center justify-between p-3 border rounded hover:bg-gray-50 cursor-pointer">
                <div>
                  <div className="font-medium text-sm">Share Order Quantities</div>
                  <div className="text-xs text-gray-500">
                    Let others see your placed orders
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={permissions.share_orders}
                  onChange={(e) =>
                    handlePermissionChange("share_orders", e.target.checked)
                  }
                  className="h-5 w-5 text-indigo-600"
                />
              </label>
            </div>
          </div>
        )}

        {/* Show who's sharing */}
        {allPermissions && allPermissions.players && (
          <div className="border-t pt-4 mt-4">
            <h4 className="text-sm font-medium text-gray-700 mb-2">
              Sharing Participation
            </h4>
            <div className="grid grid-cols-2 gap-2">
              {allPermissions.players.map((player) => {
                const isSharing =
                  player.permissions.share_inventory ||
                  player.permissions.share_backlog ||
                  player.permissions.share_orders;

                return (
                  <div
                    key={player.player_id}
                    className={`text-sm p-2 rounded ${
                      isSharing
                        ? "bg-green-50 text-green-700"
                        : "bg-gray-50 text-gray-500"
                    }`}
                  >
                    {player.role} {isSharing ? "✓" : "—"}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    );
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading visibility dashboard...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <EyeIcon className="h-6 w-6 text-indigo-600" />
          <h2 className="text-2xl font-bold text-gray-900">
            Supply Chain Visibility
          </h2>
        </div>
        <button
          onClick={fetchVisibilityData}
          className="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 text-sm"
        >
          Refresh
        </button>
      </div>

      {/* Health Score */}
      {renderHealthScore()}

      {/* Bottlenecks */}
      {renderBottlenecks()}

      {/* Bullwhip Effect */}
      {renderBullwhip()}

      {/* Sharing Settings */}
      {renderSharingSettings()}
    </div>
  );
};

export default VisibilityDashboard;
