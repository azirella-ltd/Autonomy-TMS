/**
 * Chart color utilities for consistent visualization
 */

/** Get color based on automation rate (0-100%) */
export const getAutomationColor = (rate: number) => {
  if (rate >= 80) return "#1b5e20"; // Deep green (excellent)
  if (rate >= 60) return "#2e7d32"; // Medium green (good)
  if (rate >= 40) return "#ff9800"; // Orange (moderate)
  if (rate >= 20) return "#f57c00"; // Deep orange (low)
  return "#c62828";                 // Red (minimal)
};

/**
 * Get color for Planner Score values
 * Blue-to-orange scale based on quality score
 *
 * @param value - Score value (typically -10 to 20)
 * @returns Hex color code
 */
export const getPlannerScoreColor = (value: number) => {
  if (value >= 10) return "#003d82"; // Deep blue (excellent)
  if (value >= 5) return "#0066cc";  // Medium blue (good)
  if (value >= 0) return "#4da6ff";  // Light blue (acceptable)
  if (value >= -5) return "#ffa726"; // Orange (warning)
  return "#ff9800";                  // Deep orange (poor)
};

/**
 * Get color for Agent Score values
 * Green scale with red for negative values
 *
 * @param value - Score value (typically -5 to 25)
 * @returns Hex color code
 */
export const getAgentScoreColor = (value: number) => {
  if (value >= 20) return "#1b5e20"; // Deep green (excellent)
  if (value >= 15) return "#2e7d32"; // Medium-dark green
  if (value >= 10) return "#43a047"; // Medium green
  if (value >= 5) return "#66bb6a";  // Light-medium green
  if (value >= 0) return "#81c784";  // Light green
  return "#ef9a9a";                  // Light red (negative)
};

/**
 * Standard chart line colors for consistent visualization
 * Use these for multi-line charts to maintain visual consistency
 */
export const CHART_COLORS = {
  plannerScore: "#0066cc",       // Blue for planner metrics
  agentScore: "#2e7d32",         // Green for agent metrics
  overrideRate: "#ff9800",       // Orange for override rate/baseline
  plannerDecisions: "#0066cc",   // Blue for planner decisions
  agentDecisions: "#2e7d32",     // Green for agent decisions
};

/**
 * Example Usage:
 *
 * ```tsx
 * // In a component
 * const automationRate = 75;
 * const color = getAutomationColor(automationRate); // Returns "#2e7d32" (medium green)
 *
 * // In Recharts
 * <Line
 *   dataKey="plannerScore"
 *   stroke={CHART_COLORS.plannerScore}
 * />
 *
 * // Conditional styling
 * <div style={{ backgroundColor: getAgentScoreColor(scoreValue) }}>
 *   Score: {scoreValue}
 * </div>
 * ```
 */
