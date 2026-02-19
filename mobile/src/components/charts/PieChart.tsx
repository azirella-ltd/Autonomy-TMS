/**
 * Pie Chart Component
 * Victory Native pie chart for proportion data
 */

import React from 'react';
import { View, StyleSheet, Dimensions } from 'react-native';
import { Text, useTheme } from 'react-native-paper';
import { VictoryPie, VictoryLegend, VictoryLabel } from 'victory-native';

interface DataPoint {
  x: string;
  y: number;
  label?: string;
}

interface PieChartProps {
  data: DataPoint[];
  title?: string;
  width?: number;
  height?: number;
  showLegend?: boolean;
  showLabels?: boolean;
  colorScheme?: string[];
  innerRadius?: number; // For donut chart
}

export default function PieChart({
  data,
  title,
  width = Dimensions.get('window').width - 32,
  height = 300,
  showLegend = true,
  showLabels = true,
  colorScheme,
  innerRadius = 0,
}: PieChartProps) {
  const theme = useTheme();

  const defaultColors = [
    theme.colors.primary,
    theme.colors.secondary,
    '#4caf50',
    '#ff9800',
    '#9c27b0',
    '#00bcd4',
    '#e91e63',
    '#795548',
  ];

  const colors = colorScheme || defaultColors;

  const legendData = data.map((d, index) => ({
    name: `${d.x}: ${d.y}`,
    symbol: { fill: colors[index % colors.length] },
  }));

  return (
    <View style={styles.container}>
      {title && <Text style={styles.title}>{title}</Text>}

      <View style={styles.chartContainer}>
        <VictoryPie
          data={data}
          width={width}
          height={height}
          innerRadius={innerRadius}
          colorScale={colors}
          style={{
            labels: {
              fill: theme.dark ? 'white' : 'black',
              fontSize: showLabels ? 12 : 0,
              fontWeight: 'bold',
            },
          }}
          labelComponent={<VictoryLabel />}
          labels={({ datum }) =>
            showLabels ? `${datum.x}\n${((datum.y / totalValue) * 100).toFixed(1)}%` : ''
          }
        />

        {showLegend && (
          <VictoryLegend
            x={20}
            y={height + 20}
            orientation="horizontal"
            gutter={10}
            data={legendData}
            style={{
              labels: { fontSize: 10, fill: theme.colors.onSurface },
            }}
          />
        )}
      </View>
    </View>
  );

  // Calculate total for percentages
  function get totalValue() {
    return data.reduce((sum, d) => sum + d.y, 0);
  }
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    marginVertical: 8,
  },
  title: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 8,
  },
  chartContainer: {
    alignItems: 'center',
  },
});
