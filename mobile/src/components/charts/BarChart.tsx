/**
 * Bar Chart Component
 * Victory Native bar chart for categorical data
 */

import React from 'react';
import { View, StyleSheet, Dimensions } from 'react-native';
import { Text, useTheme } from 'react-native-paper';
import {
  VictoryChart,
  VictoryBar,
  VictoryAxis,
  VictoryTheme,
  VictoryTooltip,
  VictoryGroup,
} from 'victory-native';

interface DataPoint {
  x: string | number;
  y: number;
  label?: string;
}

interface Series {
  name: string;
  data: DataPoint[];
  color?: string;
}

interface BarChartProps {
  series: Series[];
  title?: string;
  xLabel?: string;
  yLabel?: string;
  width?: number;
  height?: number;
  grouped?: boolean;
  showTooltip?: boolean;
}

export default function BarChart({
  series,
  title,
  xLabel,
  yLabel,
  width = Dimensions.get('window').width - 32,
  height = 300,
  grouped = false,
  showTooltip = true,
}: BarChartProps) {
  const theme = useTheme();

  const colors = [
    theme.colors.primary,
    theme.colors.secondary,
    '#4caf50',
    '#ff9800',
    '#9c27b0',
    '#00bcd4',
  ];

  return (
    <View style={styles.container}>
      {title && <Text style={styles.title}>{title}</Text>}

      <VictoryChart
        width={width}
        height={height}
        theme={VictoryTheme.material}
        domainPadding={{ x: grouped ? 20 : 40 }}
      >
        {/* X Axis */}
        <VictoryAxis
          label={xLabel}
          style={{
            axisLabel: { fontSize: 12, padding: 30, fill: theme.colors.onSurface },
            tickLabels: { fontSize: 10, fill: theme.colors.onSurface, angle: -45 },
            grid: { stroke: 'transparent' },
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

        {/* Bars */}
        {grouped ? (
          <VictoryGroup offset={15} colorScale={colors}>
            {series.map((s, index) => (
              <VictoryBar
                key={s.name}
                data={s.data}
                style={{
                  data: {
                    fill: s.color || colors[index % colors.length],
                  },
                }}
                labelComponent={
                  showTooltip ? (
                    <VictoryTooltip
                      cornerRadius={4}
                      flyoutStyle={{
                        fill: theme.dark ? '#424242' : 'white',
                        stroke: s.color || colors[index % colors.length],
                      }}
                      style={{
                        fill: theme.dark ? 'white' : 'black',
                        fontSize: 12,
                      }}
                    />
                  ) : undefined
                }
              />
            ))}
          </VictoryGroup>
        ) : (
          series.map((s, index) => (
            <VictoryBar
              key={s.name}
              data={s.data}
              style={{
                data: {
                  fill: s.color || colors[index % colors.length],
                },
              }}
              labelComponent={
                showTooltip ? (
                  <VictoryTooltip
                    cornerRadius={4}
                    flyoutStyle={{
                      fill: theme.dark ? '#424242' : 'white',
                      stroke: s.color || colors[index % colors.length],
                    }}
                    style={{
                      fill: theme.dark ? 'white' : 'black',
                      fontSize: 12,
                    }}
                  />
                ) : undefined
              }
            />
          ))
        )}
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
