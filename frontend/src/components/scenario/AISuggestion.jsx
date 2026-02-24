import { useState } from "react";
import {
  SparklesIcon,
  LightBulbIcon,
  ExclamationTriangleIcon,
  CheckCircleIcon,
  ArrowPathIcon,
  GlobeAltIcon,
} from "@heroicons/react/24/outline";
import { toast } from "react-toastify";
import simulationApi from "../../services/api";

/**
 * AISuggestion Component
 * Phase 7 Sprint 3 - Frontend Integration
 *
 * Displays AI-powered order suggestions with reasoning, confidence, and what-if analysis.
 */
const AISuggestion = ({ scenarioId, scenarioUserRole, onAcceptSuggestion }) => {
  const [suggestion, setSuggestion] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [showWhatIf, setShowWhatIf] = useState(false);
  const [whatIfAmount, setWhatIfAmount] = useState("");
  const [whatIfResult, setWhatIfResult] = useState(null);
  const [isWhatIfLoading, setIsWhatIfLoading] = useState(false);
  const [globalOptimization, setGlobalOptimization] = useState(null);
  const [isGlobalOptLoading, setIsGlobalOptLoading] = useState(false);

  const requestSuggestion = async (priority = "balance_costs") => {
    try {
      setIsLoading(true);
      setSuggestion(null);

      const response = await simulationApi.requestAISuggestion(scenarioId, scenarioUserRole.toLowerCase(), {
        priority,
        notes: "User requested suggestion from game interface",
      });

      setSuggestion(response.data);
      toast.success("AI suggestion received!");
    } catch (error) {
      console.error("Failed to request suggestion:", error);
      toast.error(error.response?.data?.detail || "Failed to get AI suggestion");
    } finally {
      setIsLoading(false);
    }
  };

  const runWhatIfAnalysis = async () => {
    if (!whatIfAmount || isNaN(whatIfAmount) || whatIfAmount < 0) {
      toast.error("Please enter a valid order quantity");
      return;
    }

    try {
      setIsWhatIfLoading(true);
      setWhatIfResult(null);

      const response = await simulationApi.runWhatIfAnalysis(scenarioId, {
        question: `What if I order ${whatIfAmount} units?`,
        scenario: {
          order_quantity: parseInt(whatIfAmount, 10),
          current_order: suggestion?.order_quantity || 0,
        },
      });

      setWhatIfResult(response.data);
      toast.info("What-if analysis in progress...");
    } catch (error) {
      console.error("Failed to run what-if analysis:", error);
      toast.error(error.response?.data?.detail || "Failed to run what-if analysis");
    } finally {
      setIsWhatIfLoading(false);
    }
  };

  const requestGlobalOptimization = async () => {
    try {
      setIsGlobalOptLoading(true);
      setGlobalOptimization(null);

      const response = await simulationApi.getGlobalOptimization(scenarioId);
      setGlobalOptimization(response);
      toast.success("Global optimization received!");
    } catch (error) {
      console.error("Failed to get global optimization:", error);
      toast.error(error.response?.data?.detail || "Failed to get global optimization");
    } finally {
      setIsGlobalOptLoading(false);
    }
  };

  const acceptSuggestion = () => {
    if (suggestion && onAcceptSuggestion) {
      onAcceptSuggestion(suggestion.order_quantity);
      toast.success(`Accepted AI suggestion: ${suggestion.order_quantity} units`);
    }
  };

  const getConfidenceColor = (confidence) => {
    if (confidence >= 0.8) return "text-green-600 bg-green-50";
    if (confidence >= 0.6) return "text-yellow-600 bg-yellow-50";
    return "text-red-600 bg-red-50";
  };

  const getConfidenceBadge = (confidence) => {
    const percentage = Math.round(confidence * 100);
    const colorClass = getConfidenceColor(confidence);

    return (
      <span className={`px-2 py-1 rounded-full text-xs font-semibold ${colorClass}`}>
        {percentage}% Confidence
      </span>
    );
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <SparklesIcon className="h-6 w-6 text-indigo-600" />
          <h3 className="text-lg font-semibold text-gray-900">AI Assistant</h3>
        </div>

        {suggestion && (
          <button
            onClick={() => setSuggestion(null)}
            className="text-sm text-gray-500 hover:text-gray-700"
          >
            Clear
          </button>
        )}
      </div>

      {/* Request Buttons */}
      {!suggestion && (
        <div className="space-y-2">
          <p className="text-sm text-gray-600">
            Get AI-powered order recommendations tailored to your role
          </p>

          <div className="grid grid-cols-3 gap-2">
            <button
              onClick={() => requestSuggestion("balance_costs")}
              disabled={isLoading}
              className="flex items-center justify-center gap-2 px-3 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:bg-gray-400 transition-colors"
            >
              {isLoading ? (
                <ArrowPathIcon className="h-5 w-5 animate-spin" />
              ) : (
                <LightBulbIcon className="h-5 w-5" />
              )}
              <span className="text-sm font-medium">
                {isLoading ? "..." : "Suggest"}
              </span>
            </button>

            <button
              onClick={requestGlobalOptimization}
              disabled={isGlobalOptLoading}
              className="flex items-center justify-center gap-2 px-3 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:bg-gray-400 transition-colors"
            >
              {isGlobalOptLoading ? (
                <ArrowPathIcon className="h-5 w-5 animate-spin" />
              ) : (
                <GlobeAltIcon className="h-5 w-5" />
              )}
              <span className="text-sm font-medium">
                {isGlobalOptLoading ? "..." : "Global"}
              </span>
            </button>

            <button
              onClick={() => setShowWhatIf(!showWhatIf)}
              className="flex items-center justify-center gap-2 px-3 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
            >
              <SparklesIcon className="h-5 w-5" />
              <span className="text-sm font-medium">What-If</span>
            </button>
          </div>
        </div>
      )}

      {/* Suggestion Display */}
      {suggestion && (
        <div className="space-y-4 border-t pt-4">
          {/* Order Quantity & Confidence */}
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">Recommended Order</p>
              <p className="text-3xl font-bold text-indigo-600">
                {suggestion.order_quantity} <span className="text-lg text-gray-500">units</span>
              </p>
            </div>
            <div>
              {getConfidenceBadge(suggestion.confidence)}
            </div>
          </div>

          {/* Rationale */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <p className="text-sm text-blue-900">{suggestion.rationale}</p>
          </div>

          {/* Reasoning Steps */}
          {suggestion.context?.llm_reasoning?.reasoning_steps?.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2">
                <CheckCircleIcon className="h-4 w-4 text-green-600" />
                Reasoning
              </h4>
              <ul className="space-y-1">
                {suggestion.context.llm_reasoning.reasoning_steps.map((step, idx) => (
                  <li key={idx} className="text-sm text-gray-600 pl-4">
                    <span className="font-medium text-gray-800">{idx + 1}.</span> {step}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Risk Factors */}
          {suggestion.context?.llm_reasoning?.risk_factors?.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2">
                <ExclamationTriangleIcon className="h-4 w-4 text-yellow-600" />
                Risk Factors
              </h4>
              <ul className="space-y-1">
                {suggestion.context.llm_reasoning.risk_factors.map((risk, idx) => (
                  <li key={idx} className="text-sm text-yellow-700 bg-yellow-50 rounded px-2 py-1">
                    {risk}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Alternative Strategies */}
          {suggestion.context?.llm_reasoning?.alternatives?.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-gray-700 mb-2">
                Alternative Strategies
              </h4>
              <div className="space-y-2">
                {suggestion.context.llm_reasoning.alternatives.map((alt, idx) => (
                  <div key={idx} className="bg-gray-50 border border-gray-200 rounded p-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-medium text-gray-800">{alt.strategy}</span>
                      <span className="text-sm font-semibold text-indigo-600">
                        {alt.order_quantity} units
                      </span>
                    </div>
                    {alt.pros && (
                      <p className="text-xs text-green-700">✓ {alt.pros}</p>
                    )}
                    {alt.cons && (
                      <p className="text-xs text-red-700">✗ {alt.cons}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex gap-2 pt-2">
            <button
              onClick={acceptSuggestion}
              className="flex-1 bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700 transition-colors font-medium"
            >
              Accept & Use This Order
            </button>
            <button
              onClick={() => setShowWhatIf(true)}
              className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
            >
              Compare Options
            </button>
          </div>
        </div>
      )}

      {/* What-If Analysis */}
      {showWhatIf && (
        <div className="border-t pt-4 space-y-3">
          <h4 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
            <SparklesIcon className="h-4 w-4 text-purple-600" />
            What-If Analysis
          </h4>

          <div className="flex gap-2">
            <input
              type="number"
              min="0"
              value={whatIfAmount}
              onChange={(e) => setWhatIfAmount(e.target.value)}
              placeholder="Enter order quantity..."
              className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            />
            <button
              onClick={runWhatIfAnalysis}
              disabled={isWhatIfLoading}
              className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:bg-gray-400 transition-colors"
            >
              {isWhatIfLoading ? (
                <ArrowPathIcon className="h-5 w-5 animate-spin" />
              ) : (
                "Analyze"
              )}
            </button>
          </div>

          {whatIfResult && whatIfResult.completed && (
            <div className="bg-purple-50 border border-purple-200 rounded-lg p-4 space-y-2">
              <h5 className="font-semibold text-purple-900">Projected Results:</h5>

              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-gray-600">Inventory</p>
                  <p className="font-semibold text-gray-900">
                    {whatIfResult.result.projected_inventory} units
                  </p>
                </div>
                <div>
                  <p className="text-gray-600">Backlog</p>
                  <p className="font-semibold text-gray-900">
                    {whatIfResult.result.projected_backlog} units
                  </p>
                </div>
                <div>
                  <p className="text-gray-600">Cost</p>
                  <p className="font-semibold text-gray-900">
                    ${whatIfResult.result.projected_cost.toFixed(2)}
                  </p>
                </div>
                <div>
                  <p className="text-gray-600">Cost Δ</p>
                  <p className={`font-semibold ${
                    whatIfResult.result.cost_difference > 0 ? "text-red-600" : "text-green-600"
                  }`}>
                    {whatIfResult.result.cost_difference > 0 ? "+" : ""}
                    ${whatIfResult.result.cost_difference.toFixed(2)}
                  </p>
                </div>
              </div>

              {whatIfResult.agent_analysis && (
                <div className="mt-3 pt-3 border-t border-purple-300">
                  <p className="text-sm text-purple-900">{whatIfResult.agent_analysis}</p>
                </div>
              )}
            </div>
          )}

          {whatIfResult && !whatIfResult.completed && (
            <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 text-center">
              <ArrowPathIcon className="h-6 w-6 animate-spin text-gray-400 mx-auto mb-2" />
              <p className="text-sm text-gray-600">Analysis in progress...</p>
              <p className="text-xs text-gray-500 mt-1">
                Results will appear when ready
              </p>
            </div>
          )}
        </div>
      )}

      {/* Global Optimization Display */}
      {globalOptimization && (
        <div className="border-t pt-4 space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="font-semibold text-gray-900 flex items-center gap-2">
              <GlobeAltIcon className="h-5 w-5 text-purple-600" />
              Global Optimization
            </h4>
            <button
              onClick={() => setGlobalOptimization(null)}
              className="text-sm text-gray-500 hover:text-gray-700"
            >
              Clear
            </button>
          </div>

          {/* Optimization Type & Strategy */}
          <div className="bg-purple-50 border border-purple-200 rounded-lg p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-purple-600 uppercase">
                {globalOptimization.optimization_type}
              </span>
              <span className="text-xs text-purple-600">
                {Math.round(globalOptimization.confidence * 100)}% confidence
              </span>
            </div>
            <p className="text-sm text-purple-900">
              {globalOptimization.coordination_strategy}
            </p>
          </div>

          {/* Recommendations Grid */}
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(globalOptimization.recommendations || {}).map(([role, rec]) => (
              <div
                key={role}
                className={`p-3 rounded-lg border-2 ${
                  role === scenarioUserRole
                    ? "bg-indigo-50 border-indigo-300"
                    : "bg-gray-50 border-gray-200"
                }`}
              >
                <div className="text-xs font-medium text-gray-600 mb-1">
                  {role}
                  {role === scenarioUserRole && (
                    <span className="ml-1 text-indigo-600">(You)</span>
                  )}
                </div>
                <div className="text-2xl font-bold text-gray-900 mb-1">
                  {rec.order}
                </div>
                <div className="text-xs text-gray-600">{rec.reasoning}</div>
                {role === scenarioUserRole && (
                  <button
                    onClick={() => onAcceptSuggestion(rec.order)}
                    className="mt-2 w-full px-2 py-1 bg-indigo-600 text-white text-xs rounded hover:bg-indigo-700"
                  >
                    Accept
                  </button>
                )}
              </div>
            ))}
          </div>

          {/* Expected Impact */}
          {globalOptimization.expected_impact && (
            <div className="grid grid-cols-3 gap-2 text-center text-xs">
              <div className="p-2 bg-green-50 rounded">
                <div className="font-semibold text-green-700">
                  -{globalOptimization.expected_impact.cost_reduction}%
                </div>
                <div className="text-gray-600">Cost Reduction</div>
              </div>
              <div className="p-2 bg-blue-50 rounded">
                <div className="font-semibold text-blue-700">
                  +{Math.round(globalOptimization.expected_impact.service_improvement * 100)}%
                </div>
                <div className="text-gray-600">Service</div>
              </div>
              <div className="p-2 bg-purple-50 rounded">
                <div className="font-semibold text-purple-700">
                  -{Math.round(globalOptimization.expected_impact.bullwhip_reduction * 100)}%
                </div>
                <div className="text-gray-600">Bullwhip</div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Info Footer */}
      <div className="text-xs text-gray-500 bg-gray-50 rounded p-2">
        💡 AI suggestions are based on historical performance, demand trends, and your role's objectives.
        {suggestion?.confidence < 0.7 && (
          <span className="block mt-1 text-yellow-700">
            ⚠️ Lower confidence may indicate high uncertainty or limited data.
          </span>
        )}
      </div>
    </div>
  );
};

export default AISuggestion;
