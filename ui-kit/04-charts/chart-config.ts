/**
 * Chart Configuration for Recharts
 *
 * Default configuration and utilities for Recharts components.
 */

import { getCSSVariable } from '../02-components/utils/cn';

/**
 * Get default chart configuration for Recharts
 * Uses CSS variables for theme-aware colors
 */
export function getChartConfig() {
  return {
    // Chart colors (blue scale)
    colors: [
      getCSSVariable('chart-1'), // Light blue
      getCSSVariable('chart-2'), // Medium blue
      getCSSVariable('chart-3'), // Bright blue
      getCSSVariable('chart-4'), // Deep blue
      getCSSVariable('chart-5'), // Very deep blue
    ],

    // Default chart margins
    margin: {
      top: 20,
      right: 30,
      left: 20,
      bottom: 20,
    },

    // Grid styling
    gridConfig: {
      stroke: getCSSVariable('border'),
      strokeDasharray: "3 3",
    },

    // Axis styling
    axisConfig: {
      stroke: getCSSVariable('muted-foreground'),
      fontSize: 12,
      fontFamily: 'Inter, sans-serif',
    },

    // Tooltip styling
    tooltipConfig: {
      contentStyle: {
        backgroundColor: 'var(--background)',
        border: `1px solid ${getCSSVariable('border')}`,
        borderRadius: '0.625rem', // var(--radius)
        padding: '12px',
      },
      labelStyle: {
        color: getCSSVariable('foreground'),
        fontWeight: 600,
      },
    },
  };
}

/**
 * Responsive chart dimensions
 * Use these for consistent sizing across breakpoints
 */
export const chartDimensions = {
  small: {
    width: 300,
    height: 200,
  },
  medium: {
    width: 600,
    height: 400,
  },
  large: {
    width: 900,
    height: 500,
  },
};

/**
 * Example usage:
 *
 * ```tsx
 * import { getChartConfig, chartDimensions } from '@/lib/chartConfig';
 *
 * const config = getChartConfig();
 *
 * <ResponsiveContainer width="100%" height={chartDimensions.medium.height}>
 *   <LineChart data={data} margin={config.margin}>
 *     <CartesianGrid {...config.gridConfig} />
 *     <XAxis {...config.axisConfig} />
 *     <YAxis {...config.axisConfig} />
 *     <Tooltip {...config.tooltipConfig} />
 *     <Line
 *       dataKey="value"
 *       stroke={config.colors[0]}
 *       strokeWidth={2.5}
 *     />
 *   </LineChart>
 * </ResponsiveContainer>
 * ```
 */
