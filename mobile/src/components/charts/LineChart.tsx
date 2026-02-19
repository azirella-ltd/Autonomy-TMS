/**
 * Line Chart Component
 * Victory Native line chart for time series data
 */

import React from 'react';
import { View, StyleSheet, Dimensions } from 'react-native';
import { Text, useTheme } from 'react-native-paper';
import {
  VictoryChart,
  VictoryLine,
  VictoryAxis,
  VictoryTheme,
  VictoryTooltip,
  VictoryVoronoiContainer,
  VictoryLegend,
} from 'victory-native';

interface DataPoint {
  x: number | string;
  y: number;
}

interface Series {
  name: string;
  data: DataPoint[];
  color?: string;
}

interface LineChartProps {
  series: Series[];
  title?: string;
  xLabel?: string;
  yLabel?: string;
  width?: number;
  height?: number;
  showLegend?: boolean;
  showTooltip?: boolean;
}

export default function LineChart({
  series,
  title,
  xLabel,
  yLabel,
  width = Dimensions.get('window').width - 32,
  height = 300,
  showLegend = true,
  showTooltip = true,
}: LineChartProps) {
  const theme = useTheme();

  const colors = [
    theme.colors.primary,
    theme.colors.secondary,
    '#4caf50',
    '#ff9800',
    '#9c27b0',
    '#00bcd4',
  ];

  const legendData = series.map((s, index) => ({
    name: s.name,
    symbol: { fill: s.color || colors[index % colors.length] },
  }));

  return (
    <View style={styles.container}>
      {title && <Text style={styles.title}>{title}</Text>}

      <VictoryChart
        width={width}
        height={height}
        theme={VictoryTheme.material}
        containerComponent={
          showTooltip ? (
            <VictoryVoronoiContainer
              labels={({ datum }) => `${datum.x}: ${datum.y}`}
              labelComponent={
                <VictoryTooltip
                  cornerRadius={4}
                  flyoutStyle={{
                    fill: theme.dark ? '#424242' : 'white',
                    stroke: theme.colors.primary,
                  }}
                  style={{
                    fill: theme.dark ? 'white' : 'black',
                    fontSize: 12,
                  }}
                />
              }
            />
          ) : undefined
        }
      >
        {/* X Axis */}
        <VictoryAxis
          label={xLabel}
          style={{
            axisLabel: { fontSize: 12, padding: 30, fill: theme.colors.onSurface },
            tickLabels: { fontSize: 10, fill: theme.colors.onSurface },
            grid: { stroke: theme.colors.outline, strokeWidth: 0.5 },
          }}
        />

        {/* Y Axis */}
        <VictoryAxis
          dependentAxis
          label={yLabel}
          style={{
            axisLabel: { fontSize: 12, padding: 40, fill: theme.colors.onSurface },
            tickLabels: { fontSize: 10, fill: theme.colors.onSurface },
            grid: { stroke: theme.colors.outline, strokeWidth: 0.5 },
          }}
        />

        {/* Legend */}
        {showLegend && (
          <VictoryLegend
            x={width / 2 - 100}
            y={0}
            orientation="horizontal"
            gutter={20}
            data={legendData}
            style={{
              labels: { fontSize: 10, fill: theme.colors.onSurface },
            }}
          />
        )}

        {/* Data Lines */}
        {series.map((s, index) => (
          <VictoryLine
            key={s.name}
            data={s.data}
            style={{
              data: {
                stroke: s.color || colors[index % colors.length],
                strokeWidth: 2,
              },
            }}
          />
        ))}
      </VictoryChart>
    </View>
  );
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
});
