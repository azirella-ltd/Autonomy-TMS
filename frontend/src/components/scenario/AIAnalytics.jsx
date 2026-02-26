import { useState, useEffect } from "react";
import {
  ChartBarIcon,
  SparklesIcon,
  TrophyIcon,
  LightBulbIcon,
  ClockIcon,
} from "@heroicons/react/24/outline";
import { toast } from "react-toastify";
import simulationApi from "../../services/api";

/**
 * AIAnalytics Component
 * Phase 7 Sprint 4 - Feature 2: Pattern Analysis
 *
 * Displays AI suggestion analytics including:
 * - ScenarioUser behavior patterns
 * - AI effectiveness metrics
 * - Suggestion history
 * - Acceptance trends
 * - Generated insights
 */
const AIAnalytics = ({ scenarioId, scenarioUserRole }) => {
  const [patterns, setPatterns] = useState(null);
  const [effectiveness, setEffectiveness] = useState(null);
  const [history, setHistory] = useState([]);
  const [insights, setInsights] = useState([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetchAnalytics();
  }, [scenarioId]);

  const fetchAnalytics = async () => {
    try {
      setIsLoading(true);

      // Fetch all analytics data in parallel
      const [patternsData, effectivenessData, historyData, insightsData] =
        await Promise.all([
          simulationApi.getScenarioUserPatterns(scenarioId),
          simulationApi.getAIEffectiveness(scenarioId),
          simulationApi.getSuggestionHistory(scenarioId, 20),
          simulationApi.getInsights(scenarioId),
        ]);

      setPatterns(patternsData);
      setEffectiveness(effectivenessData);
      setHistory(historyData.suggestions || []);
      setInsights(insightsData.insights || []);
    } catch (error) {
      console.error("Failed to fetch analytics:", error);
      toast.error("Failed to load AI analytics");
    } finally {
      setIsLoading(false);
    }
  };

  const getPatternColor = (patternType) => {
    switch (patternType) {
      case "conservative":
        return "bg-blue-50 text-blue-700 border-blue-200";
      case "aggressive":
        return "bg-red-50 text-red-700 border-red-200";
      case "balanced":
        return "bg-green-50 text-green-700 border-green-200";
      case "reactive":
        return "bg-purple-50 text-purple-700 border-purple-200";
      default:
        return "bg-gray-50 text-gray-700 border-gray-200";
    }
  };

  const getPatternDescription = (patternType) => {
    switch (patternType) {
      case "conservative":
        return "You trust AI recommendations highly and make minimal modifications";
      case "aggressive":
        return "You frequently modify or reject AI suggestions with significant changes";
      case "balanced":
        return "You balance AI guidance with your own judgment";
      case "reactive":
        return "Your decision-making shows high volatility and quick responses";
      default:
        return "Pattern analysis in progress";
    }
  };

  const renderPatternCard = () => {
    if (!patterns) return null;

    const { pattern_type, acceptance_rate, avg_modification } = patterns;

    return (
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
            <SparklesIcon className="h-5 w-5 text-indigo-600" />
            Your Decision Pattern
          </h3>
          <div
            className={`px-4 py-2 rounded-full border-2 font-semibold capitalize ${getPatternColor(
              pattern_type
            )}`}
          >
            {pattern_type}
          </div>
        </div>

        <p className="text-sm text-gray-600 mb-6">
          {getPatternDescription(pattern_type)}
        </p>

        {/* Metrics Grid */}
        <div className="grid grid-cols-2 gap-4">
          <div className="text-center p-4 bg-gray-50 rounded-lg">
            <div className="text-3xl font-bold text-indigo-600">
              {Math.round(acceptance_rate * 100)}%
            </div>
            <div className="text-xs text-gray-500 mt-1">Acceptance Rate</div>
            <div className="text-xs text-gray-400 mt-1">
              How often you follow AI suggestions
            </div>
          </div>

          <div className="text-center p-4 bg-gray-50 rounded-lg">
            <div className="text-3xl font-bold text-purple-600">
              {Math.round(avg_modification * 100)}%
            </div>
            <div className="text-xs text-gray-500 mt-1">Avg Modification</div>
            <div className="text-xs text-gray-400 mt-1">
              How much you adjust recommendations
            </div>
          </div>
        </div>
      </div>
    );
  };

  const renderEffectiveness = () => {
    if (!effectiveness) return null;

    const { acceptance_rate, performance_comparison } = effectiveness;
    const { ai_suggested, scenario_user_modified, improvement } =
      performance_comparison || {};

    return (
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
            <TrophyIcon className="h-5 w-5 text-yellow-600" />
            AI Effectiveness
          </h3>
          <div className="text-sm text-gray-500">
            Overall Acceptance: {Math.round(acceptance_rate * 100)}%
          </div>
        </div>

        {ai_suggested && scenario_user_modified && (
          <div className="space-y-4">
            {/* Performance Comparison */}
            <div className="grid grid-cols-3 gap-4">
              <div className="text-center p-3 bg-indigo-50 rounded-lg">
                <div className="text-xs font-medium text-indigo-600 mb-1">
                  AI Suggested
                </div>
                <div className="text-2xl font-bold text-gray-900">
                  {ai_suggested.avg_performance_score?.toFixed(1) || "N/A"}
                </div>
                <div className="text-xs text-gray-500 mt-1">Avg Score</div>
              </div>

              <div className="text-center p-3 bg-gray-50 rounded-lg">
                <div className="text-xs font-medium text-gray-600 mb-1">
                  ScenarioUser Modified
                </div>
                <div className="text-2xl font-bold text-gray-900">
                  {scenario_user_modified.avg_performance_score?.toFixed(1) || "N/A"}
                </div>
                <div className="text-xs text-gray-500 mt-1">Avg Score</div>
              </div>

              <div className="text-center p-3 bg-green-50 rounded-lg">
                <div className="text-xs font-medium text-green-600 mb-1">
                  Improvement
                </div>
                <div className="text-2xl font-bold text-green-700">
                  {improvement?.score_improvement > 0 ? "+" : ""}
                  {improvement?.score_improvement?.toFixed(1) || "0"}
                </div>
                <div className="text-xs text-gray-500 mt-1">Points</div>
              </div>
            </div>

            {/* Cost Savings */}
            {improvement && (
              <div className="border-t pt-4">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-gray-600">Cost Savings:</span>
                    <span className="font-semibold text-green-600">
                      ${improvement.cost_savings?.toFixed(2) || "0.00"} /round
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-600">Service Improvement:</span>
                    <span className="font-semibold text-blue-600">
                      {improvement.service_improvement > 0 ? "+" : ""}
                      {(improvement.service_improvement * 100)?.toFixed(1) ||
                        "0"}
                      %
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  const renderHistory = () => {
    if (history.length === 0) return null;

    return (
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
            <ClockIcon className="h-5 w-5 text-gray-600" />
            Suggestion History
          </h3>
          <div className="text-sm text-gray-500">Last {history.length} rounds</div>
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">
                  Round
                </th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">
                  AI Suggested
                </th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">
                  You Ordered
                </th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">
                  Status
                </th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">
                  Score
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {history.map((item, idx) => (
                <tr key={idx} className="hover:bg-gray-50">
                  <td className="px-4 py-2 text-sm text-gray-900">
                    {item.round_number || idx + 1}
                  </td>
                  <td className="px-4 py-2 text-sm font-medium text-indigo-600">
                    {item.suggested_order || "N/A"}
                  </td>
                  <td className="px-4 py-2 text-sm font-medium text-gray-900">
                    {item.actual_order || "N/A"}
                  </td>
                  <td className="px-4 py-2 text-sm">
                    {item.accepted ? (
                      <span className="px-2 py-1 rounded text-xs bg-green-100 text-green-800">
                        Accepted
                      </span>
                    ) : item.modified ? (
                      <span className="px-2 py-1 rounded text-xs bg-yellow-100 text-yellow-800">
                        Modified
                      </span>
                    ) : (
                      <span className="px-2 py-1 rounded text-xs bg-red-100 text-red-800">
                        Rejected
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-sm">
                    {item.performance_score ? (
                      <span
                        className={`font-semibold ${
                          item.performance_score >= 70
                            ? "text-green-600"
                            : item.performance_score >= 50
                            ? "text-yellow-600"
                            : "text-red-600"
                        }`}
                      >
                        {item.performance_score.toFixed(1)}
                      </span>
                    ) : (
                      <span className="text-gray-400">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  const renderInsights = () => {
    if (insights.length === 0) return null;

    return (
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center gap-2 mb-4">
          <LightBulbIcon className="h-5 w-5 text-yellow-600" />
          <h3 className="text-lg font-semibold text-gray-900">
            Actionable Insights
          </h3>
        </div>

        <ul className="space-y-3">
          {insights.map((insight, idx) => (
            <li
              key={idx}
              className="flex items-start gap-3 p-3 bg-yellow-50 rounded-lg"
            >
              <span className="text-yellow-600 mt-0.5">💡</span>
              <span className="text-sm text-gray-700">{insight}</span>
            </li>
          ))}
        </ul>
      </div>
    );
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading AI analytics...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <ChartBarIcon className="h-6 w-6 text-indigo-600" />
          <h2 className="text-2xl font-bold text-gray-900">AI Analytics</h2>
        </div>
        <button
          onClick={fetchAnalytics}
          className="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 text-sm"
        >
          Refresh
        </button>
      </div>

      {/* Pattern Card */}
      {renderPatternCard()}

      {/* Effectiveness Card */}
      {renderEffectiveness()}

      {/* History Table */}
      {renderHistory()}

      {/* Insights */}
      {renderInsights()}

      {/* Empty State */}
      {!patterns && !effectiveness && history.length === 0 && (
        <div className="text-center py-12">
          <ChartBarIcon className="h-16 w-16 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-600 mb-2">
            No analytics available yet
          </p>
          <p className="text-sm text-gray-400">
            Start using AI suggestions to see your patterns and effectiveness
          </p>
        </div>
      )}
    </div>
  );
};

export default AIAnalytics;
