/**
 * Supply Chain Analytics Dashboard
 *
 * Balanced scorecard-based scenario comparison for Production groups.
 * Allows users to:
 * - Add scenarios to compare their balanced scorecard metrics
 * - View Financial, Customer, Operational, and Strategic perspectives
 * - Promote a scenario to become the "root" (active baseline)
 *
 * This page is the primary analytics tool for Production mode users
 * to evaluate and select optimal planning scenarios.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Button,
  Alert,
  Spinner,
} from '../components/common';
import {
  BarChart3,
  Plus,
  Trash2,
  Check,
  ChevronUp,
  ChevronDown,
  TrendingUp,
  TrendingDown,
  Target,
  Users,
  Settings,
  Shield,
  AlertTriangle,
  Crown,
  Info,
  RefreshCw,
  LayoutGrid,
  Table2,
} from 'lucide-react';
import { api } from '../services/api';

// Mock scenarios for demo (will be replaced with API data)
const DEMO_SCENARIOS = [
  {
    id: 'baseline',
    name: 'Current Baseline',
    description: 'Current production plan with standard safety stock',
    isRoot: true,
    createdAt: '2026-02-01',
    status: 'active',
    scorecard: {
      financial: {
        total_cost: { value: 2450000, target: 2300000, unit: '$', direction: 'lower_is_better', p10: 2200000, p50: 2450000, p90: 2750000 },
        inventory_holding: { value: 850000, target: 800000, unit: '$', direction: 'lower_is_better' },
        stockout_cost: { value: 320000, target: 200000, unit: '$', direction: 'lower_is_better' },
        working_capital: { value: 4200000, target: 4000000, unit: '$', direction: 'lower_is_better' },
      },
      customer: {
        service_level: { value: 94.2, target: 95.0, unit: '%', direction: 'higher_is_better', p10: 91.0, p50: 94.2, p90: 97.0 },
        otif_rate: { value: 92.5, target: 95.0, unit: '%', direction: 'higher_is_better' },
        fill_rate: { value: 96.8, target: 98.0, unit: '%', direction: 'higher_is_better' },
        order_lead_time: { value: 3.2, target: 3.0, unit: 'days', direction: 'lower_is_better' },
      },
      operational: {
        inventory_turns: { value: 8.5, target: 10.0, unit: 'x', direction: 'higher_is_better' },
        days_of_supply: { value: 42, target: 35, unit: 'days', direction: 'lower_is_better' },
        capacity_utilization: { value: 82, target: 85, unit: '%', direction: 'higher_is_better' },
        planning_accuracy: { value: 87, target: 90, unit: '%', direction: 'higher_is_better' },
      },
      strategic: {
        flexibility_score: { value: 72, target: 80, unit: '%', direction: 'higher_is_better' },
        resilience_score: { value: 78, target: 85, unit: '%', direction: 'higher_is_better' },
        risk_exposure: { value: 15, target: 10, unit: '%', direction: 'lower_is_better' },
        sustainability: { value: 68, target: 75, unit: '%', direction: 'higher_is_better' },
      },
      overall_score: 74.5,
    },
  },
  {
    id: 'scenario-1',
    name: 'Increased Safety Stock',
    description: '+20% safety stock across all products',
    isRoot: false,
    createdAt: '2026-02-05',
    status: 'evaluated',
    scorecard: {
      financial: {
        total_cost: { value: 2580000, target: 2300000, unit: '$', direction: 'lower_is_better', p10: 2350000, p50: 2580000, p90: 2850000 },
        inventory_holding: { value: 1020000, target: 800000, unit: '$', direction: 'lower_is_better' },
        stockout_cost: { value: 180000, target: 200000, unit: '$', direction: 'lower_is_better' },
        working_capital: { value: 4800000, target: 4000000, unit: '$', direction: 'lower_is_better' },
      },
      customer: {
        service_level: { value: 97.8, target: 95.0, unit: '%', direction: 'higher_is_better', p10: 95.5, p50: 97.8, p90: 99.2 },
        otif_rate: { value: 96.5, target: 95.0, unit: '%', direction: 'higher_is_better' },
        fill_rate: { value: 98.9, target: 98.0, unit: '%', direction: 'higher_is_better' },
        order_lead_time: { value: 2.8, target: 3.0, unit: 'days', direction: 'lower_is_better' },
      },
      operational: {
        inventory_turns: { value: 6.8, target: 10.0, unit: 'x', direction: 'higher_is_better' },
        days_of_supply: { value: 54, target: 35, unit: 'days', direction: 'lower_is_better' },
        capacity_utilization: { value: 85, target: 85, unit: '%', direction: 'higher_is_better' },
        planning_accuracy: { value: 89, target: 90, unit: '%', direction: 'higher_is_better' },
      },
      strategic: {
        flexibility_score: { value: 65, target: 80, unit: '%', direction: 'higher_is_better' },
        resilience_score: { value: 88, target: 85, unit: '%', direction: 'higher_is_better' },
        risk_exposure: { value: 8, target: 10, unit: '%', direction: 'lower_is_better' },
        sustainability: { value: 62, target: 75, unit: '%', direction: 'higher_is_better' },
      },
      overall_score: 76.2,
    },
  },
  {
    id: 'scenario-2',
    name: 'Lean Inventory',
    description: '-15% safety stock with improved forecasting',
    isRoot: false,
    createdAt: '2026-02-06',
    status: 'evaluated',
    scorecard: {
      financial: {
        total_cost: { value: 2280000, target: 2300000, unit: '$', direction: 'lower_is_better', p10: 2050000, p50: 2280000, p90: 2650000 },
        inventory_holding: { value: 680000, target: 800000, unit: '$', direction: 'lower_is_better' },
        stockout_cost: { value: 420000, target: 200000, unit: '$', direction: 'lower_is_better' },
        working_capital: { value: 3600000, target: 4000000, unit: '$', direction: 'lower_is_better' },
      },
      customer: {
        service_level: { value: 91.5, target: 95.0, unit: '%', direction: 'higher_is_better', p10: 86.0, p50: 91.5, p90: 95.0 },
        otif_rate: { value: 89.2, target: 95.0, unit: '%', direction: 'higher_is_better' },
        fill_rate: { value: 94.5, target: 98.0, unit: '%', direction: 'higher_is_better' },
        order_lead_time: { value: 3.8, target: 3.0, unit: 'days', direction: 'lower_is_better' },
      },
      operational: {
        inventory_turns: { value: 12.2, target: 10.0, unit: 'x', direction: 'higher_is_better' },
        days_of_supply: { value: 28, target: 35, unit: 'days', direction: 'lower_is_better' },
        capacity_utilization: { value: 88, target: 85, unit: '%', direction: 'higher_is_better' },
        planning_accuracy: { value: 92, target: 90, unit: '%', direction: 'higher_is_better' },
      },
      strategic: {
        flexibility_score: { value: 85, target: 80, unit: '%', direction: 'higher_is_better' },
        resilience_score: { value: 62, target: 85, unit: '%', direction: 'higher_is_better' },
        risk_exposure: { value: 22, target: 10, unit: '%', direction: 'lower_is_better' },
        sustainability: { value: 78, target: 75, unit: '%', direction: 'higher_is_better' },
      },
      overall_score: 72.8,
    },
  },
];

const AVAILABLE_SCENARIOS = [
  { id: 'scenario-3', name: 'Regional Sourcing', description: 'Dual-source critical materials from regional suppliers' },
  { id: 'scenario-4', name: 'Demand Shaping', description: 'Price incentives to shift demand to low-utilization periods' },
  { id: 'scenario-5', name: 'Capacity Expansion', description: '+15% production capacity at Plant A' },
];

// Format value based on unit type
const formatValue = (value, unit) => {
  if (unit === '$') {
    return value >= 1000000
      ? `$${(value / 1000000).toFixed(2)}M`
      : value >= 1000
      ? `$${(value / 1000).toFixed(0)}K`
      : `$${value.toFixed(0)}`;
  }
  if (unit === '%') return `${value.toFixed(1)}%`;
  if (unit === 'days') return `${value.toFixed(1)} days`;
  if (unit === 'x') return `${value.toFixed(1)}x`;
  return value.toFixed(1);
};

// Get status color and icon based on metric performance
const getMetricStatus = (metric) => {
  if (!metric.target) return { color: 'text-slate-500', bg: 'bg-slate-100', icon: null };

  const { value, target, direction } = metric;
  const isGood = direction === 'higher_is_better' ? value >= target : value <= target;
  const ratio = direction === 'higher_is_better' ? value / target : target / value;

  if (isGood) {
    return {
      color: 'text-green-600',
      bg: 'bg-green-100',
      icon: <TrendingUp className="h-4 w-4" />,
    };
  } else if (ratio > 0.9) {
    return {
      color: 'text-yellow-600',
      bg: 'bg-yellow-100',
      icon: <TrendingDown className="h-4 w-4" />,
    };
  } else {
    return {
      color: 'text-red-600',
      bg: 'bg-red-100',
      icon: <AlertTriangle className="h-4 w-4" />,
    };
  }
};

// Metric Row Component
const MetricRow = ({ name, metric, showComparison, baselineMetric }) => {
  const status = getMetricStatus(metric);
  const delta = baselineMetric
    ? ((metric.value - baselineMetric.value) / baselineMetric.value) * 100
    : null;
  const deltaIsGood =
    delta !== null &&
    ((metric.direction === 'higher_is_better' && delta > 0) ||
      (metric.direction === 'lower_is_better' && delta < 0));

  return (
    <div className="flex items-center justify-between py-2 border-b border-slate-100 last:border-0">
      <div className="flex items-center gap-2">
        <span className={`p-1 rounded ${status.bg}`}>{status.icon || <Target className="h-4 w-4 text-slate-400" />}</span>
        <span className="text-sm font-medium capitalize">{name.replace(/_/g, ' ')}</span>
      </div>
      <div className="flex items-center gap-3">
        <span className={`text-sm font-semibold ${status.color}`}>
          {formatValue(metric.value, metric.unit)}
        </span>
        {metric.target && (
          <span className="text-xs text-slate-400">
            Target: {formatValue(metric.target, metric.unit)}
          </span>
        )}
        {showComparison && delta !== null && (
          <span
            className={`text-xs font-medium px-2 py-0.5 rounded ${
              deltaIsGood
                ? 'bg-green-100 text-green-700'
                : 'bg-red-100 text-red-700'
            }`}
          >
            {delta > 0 ? '+' : ''}
            {delta.toFixed(1)}%
          </span>
        )}
      </div>
    </div>
  );
};

// Perspective Card Component
const PerspectiveCard = ({
  title,
  icon: Icon,
  metrics,
  baselineMetrics,
  showComparison,
  iconColor = 'text-blue-500',
}) => {
  return (
    <Card className="h-full">
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <Icon className={`h-5 w-5 ${iconColor}`} />
          <CardTitle className="text-lg">{title}</CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        {Object.entries(metrics).map(([key, metric]) => (
          <MetricRow
            key={key}
            name={key}
            metric={metric}
            showComparison={showComparison}
            baselineMetric={baselineMetrics?.[key]}
          />
        ))}
      </CardContent>
    </Card>
  );
};

// Scenario Card Component
const ScenarioCard = ({ scenario, isSelected, onSelect, onRemove, onPromote, isBaseline }) => {
  return (
    <Card
      className={`cursor-pointer transition-all ${
        isSelected
          ? 'ring-2 ring-primary border-primary'
          : 'hover:border-slate-300'
      } ${scenario.isRoot ? 'bg-amber-50 border-amber-200' : ''}`}
      onClick={() => onSelect(scenario.id)}
    >
      <CardContent className="py-4">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              {scenario.isRoot && (
                <Crown className="h-4 w-4 text-amber-500" />
              )}
              <h3 className="font-semibold text-sm">{scenario.name}</h3>
              {isSelected && (
                <Check className="h-4 w-4 text-primary" />
              )}
            </div>
            <p className="text-xs text-slate-500 mb-2">{scenario.description}</p>
            <div className="flex items-center gap-3 text-xs">
              <span
                className={`px-2 py-0.5 rounded-full ${
                  scenario.status === 'active'
                    ? 'bg-green-100 text-green-700'
                    : scenario.status === 'evaluated'
                    ? 'bg-blue-100 text-blue-700'
                    : 'bg-slate-100 text-slate-600'
                }`}
              >
                {scenario.status}
              </span>
              <span className="text-slate-400">{scenario.createdAt}</span>
            </div>
          </div>
          <div className="flex flex-col gap-1 ml-2">
            <div
              className={`text-lg font-bold ${
                scenario.scorecard.overall_score >= 75
                  ? 'text-green-600'
                  : scenario.scorecard.overall_score >= 70
                  ? 'text-yellow-600'
                  : 'text-red-600'
              }`}
            >
              {scenario.scorecard.overall_score.toFixed(1)}
            </div>
            <span className="text-[10px] text-slate-400 text-right">Score</span>
          </div>
        </div>
        <div className="flex items-center gap-2 mt-3 pt-3 border-t border-slate-100">
          {!scenario.isRoot && (
            <>
              <Button
                variant="outline"
                size="sm"
                className="text-xs h-7 px-2"
                onClick={(e) => {
                  e.stopPropagation();
                  onPromote(scenario.id);
                }}
              >
                <Crown className="h-3 w-3 mr-1" />
                Promote
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="text-xs h-7 px-2 text-red-500 hover:text-red-700"
                onClick={(e) => {
                  e.stopPropagation();
                  onRemove(scenario.id);
                }}
              >
                <Trash2 className="h-3 w-3 mr-1" />
                Remove
              </Button>
            </>
          )}
          {scenario.isRoot && (
            <span className="text-xs text-amber-600 flex items-center gap-1">
              <Info className="h-3 w-3" />
              Current active baseline
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

// Comparison Matrix Component — scenarios as columns, KPIs as rows
const ComparisonMatrix = ({ scenarios }) => {
  const baselineScenario = scenarios.find((s) => s.isRoot);

  const perspectives = [
    { key: 'financial',    label: 'Financial',    icon: TrendingUp, color: 'text-emerald-500' },
    { key: 'customer',     label: 'Customer',     icon: Users,      color: 'text-blue-500'    },
    { key: 'operational',  label: 'Operational',  icon: Settings,   color: 'text-orange-500'  },
    { key: 'strategic',    label: 'Strategic',    icon: Shield,     color: 'text-purple-500'  },
  ];

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b-2 border-slate-200 bg-slate-50">
            <th className="text-left py-3 px-4 font-semibold text-slate-600 w-52 min-w-[200px]">
              KPI
            </th>
            {scenarios.map((s) => (
              <th
                key={s.id}
                className={`text-center py-3 px-4 font-semibold min-w-[150px] ${
                  s.isRoot ? 'bg-amber-50' : ''
                }`}
              >
                <div className="flex flex-col items-center gap-0.5">
                  {s.isRoot && <Crown className="h-3.5 w-3.5 text-amber-500" />}
                  <span className="leading-tight">{s.name}</span>
                  <span
                    className={`text-[10px] font-normal px-1.5 py-0.5 rounded-full ${
                      s.status === 'active'
                        ? 'bg-green-100 text-green-700'
                        : 'bg-blue-100 text-blue-700'
                    }`}
                  >
                    {s.status}
                  </span>
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {/* Overall Score — first row */}
          <tr className="border-b-2 border-slate-300 bg-gradient-to-r from-primary/5 to-primary/10">
            <td className="py-3 px-4 font-bold text-slate-700">Overall Score</td>
            {scenarios.map((s) => {
              const delta =
                baselineScenario && s.id !== baselineScenario.id
                  ? s.scorecard.overall_score - baselineScenario.scorecard.overall_score
                  : null;
              return (
                <td key={s.id} className={`text-center py-3 px-4 ${s.isRoot ? 'bg-amber-50/60' : ''}`}>
                  <div className="flex flex-col items-center">
                    <span
                      className={`text-2xl font-bold ${
                        s.scorecard.overall_score >= 75
                          ? 'text-green-600'
                          : s.scorecard.overall_score >= 70
                          ? 'text-yellow-600'
                          : 'text-red-600'
                      }`}
                    >
                      {s.scorecard.overall_score.toFixed(1)}
                      <span className="text-sm font-normal text-slate-400">/100</span>
                    </span>
                    {delta !== null && (
                      <span
                        className={`text-xs font-medium mt-0.5 ${
                          delta >= 0 ? 'text-green-600' : 'text-red-600'
                        }`}
                      >
                        {delta > 0 ? '+' : ''}{delta.toFixed(1)} vs baseline
                      </span>
                    )}
                  </div>
                </td>
              );
            })}
          </tr>

          {/* Perspective groups */}
          {perspectives.map(({ key, label, icon: Icon, color }) => (
            <React.Fragment key={key}>
              {/* Section header */}
              <tr className="bg-slate-100 border-y border-slate-200">
                <td colSpan={scenarios.length + 1} className="py-2 px-4">
                  <div className="flex items-center gap-2">
                    <Icon className={`h-4 w-4 ${color}`} />
                    <span className="font-semibold text-slate-700 text-sm">{label}</span>
                  </div>
                </td>
              </tr>

              {/* KPI rows */}
              {Object.entries(scenarios[0].scorecard[key]).map(([metricKey]) => (
                <tr
                  key={`${key}-${metricKey}`}
                  className="border-b border-slate-100 hover:bg-slate-50 transition-colors"
                >
                  <td className="py-2 px-4 text-slate-600 capitalize">
                    {metricKey.replace(/_/g, ' ')}
                  </td>
                  {scenarios.map((s) => {
                    const metric = s.scorecard[key][metricKey];
                    const status = getMetricStatus(metric);
                    const baseMetric =
                      baselineScenario && s.id !== baselineScenario.id
                        ? baselineScenario.scorecard[key][metricKey]
                        : null;
                    const delta = baseMetric
                      ? ((metric.value - baseMetric.value) / baseMetric.value) * 100
                      : null;
                    const deltaIsGood =
                      delta !== null &&
                      ((metric.direction === 'higher_is_better' && delta > 0) ||
                        (metric.direction === 'lower_is_better' && delta < 0));

                    return (
                      <td
                        key={s.id}
                        className={`text-center py-2 px-4 ${s.isRoot ? 'bg-amber-50/40' : ''}`}
                      >
                        <div className="flex flex-col items-center">
                          <span className={`font-medium ${status.color}`}>
                            {formatValue(metric.value, metric.unit)}
                          </span>
                          {delta !== null && (
                            <span
                              className={`text-[11px] mt-0.5 ${
                                deltaIsGood ? 'text-green-600' : 'text-red-600'
                              }`}
                            >
                              {delta > 0 ? '+' : ''}{delta.toFixed(1)}%
                            </span>
                          )}
                        </div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </React.Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
};

// Main Component
const SupplyChainAnalytics = () => {
  const [scenarios, setScenarios] = useState(DEMO_SCENARIOS);
  const [selectedScenarioId, setSelectedScenarioId] = useState('baseline');
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [viewMode, setViewMode] = useState('table'); // 'scorecard' | 'table'

  const selectedScenario = scenarios.find((s) => s.id === selectedScenarioId);
  const baselineScenario = scenarios.find((s) => s.isRoot);

  const handleRemoveScenario = (scenarioId) => {
    setScenarios((prev) => prev.filter((s) => s.id !== scenarioId));
    if (selectedScenarioId === scenarioId) {
      setSelectedScenarioId('baseline');
    }
  };

  const handlePromoteScenario = async (scenarioId) => {
    // In production, this would call an API
    setScenarios((prev) =>
      prev.map((s) => ({
        ...s,
        isRoot: s.id === scenarioId,
        status: s.id === scenarioId ? 'active' : s.status === 'active' ? 'evaluated' : s.status,
      }))
    );
  };

  const handleAddScenario = (scenarioToAdd) => {
    // In production, this would evaluate the scenario via API
    const newScenario = {
      ...scenarioToAdd,
      createdAt: new Date().toISOString().split('T')[0],
      status: 'evaluated',
      isRoot: false,
      scorecard: {
        financial: {
          total_cost: { value: 2350000 + Math.random() * 200000, target: 2300000, unit: '$', direction: 'lower_is_better' },
          inventory_holding: { value: 750000 + Math.random() * 200000, target: 800000, unit: '$', direction: 'lower_is_better' },
          stockout_cost: { value: 200000 + Math.random() * 150000, target: 200000, unit: '$', direction: 'lower_is_better' },
          working_capital: { value: 3800000 + Math.random() * 500000, target: 4000000, unit: '$', direction: 'lower_is_better' },
        },
        customer: {
          service_level: { value: 92 + Math.random() * 6, target: 95.0, unit: '%', direction: 'higher_is_better' },
          otif_rate: { value: 90 + Math.random() * 8, target: 95.0, unit: '%', direction: 'higher_is_better' },
          fill_rate: { value: 95 + Math.random() * 4, target: 98.0, unit: '%', direction: 'higher_is_better' },
          order_lead_time: { value: 2.5 + Math.random() * 1.5, target: 3.0, unit: 'days', direction: 'lower_is_better' },
        },
        operational: {
          inventory_turns: { value: 8 + Math.random() * 4, target: 10.0, unit: 'x', direction: 'higher_is_better' },
          days_of_supply: { value: 30 + Math.random() * 20, target: 35, unit: 'days', direction: 'lower_is_better' },
          capacity_utilization: { value: 80 + Math.random() * 10, target: 85, unit: '%', direction: 'higher_is_better' },
          planning_accuracy: { value: 85 + Math.random() * 10, target: 90, unit: '%', direction: 'higher_is_better' },
        },
        strategic: {
          flexibility_score: { value: 70 + Math.random() * 20, target: 80, unit: '%', direction: 'higher_is_better' },
          resilience_score: { value: 70 + Math.random() * 20, target: 85, unit: '%', direction: 'higher_is_better' },
          risk_exposure: { value: 8 + Math.random() * 15, target: 10, unit: '%', direction: 'lower_is_better' },
          sustainability: { value: 65 + Math.random() * 20, target: 75, unit: '%', direction: 'higher_is_better' },
        },
        overall_score: 70 + Math.random() * 10,
      },
    };
    setScenarios((prev) => [...prev, newScenario]);
    setShowAddDialog(false);
  };

  return (
    <div className="container mx-auto py-6 px-4 max-w-7xl">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <BarChart3 className="h-8 w-8 text-primary" />
          <div>
            <h1 className="text-2xl font-bold">Supply Chain Analytics</h1>
            <p className="text-sm text-muted-foreground">
              Compare scenarios using balanced scorecard metrics
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* View toggle */}
          <div className="flex items-center border border-slate-200 rounded-md overflow-hidden text-sm">
            <button
              className={`flex items-center gap-1.5 px-3 py-1.5 transition-colors ${
                viewMode === 'table'
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-slate-50'
              }`}
              onClick={() => setViewMode('table')}
              title="Table View"
            >
              <Table2 className="h-4 w-4" />
              <span className="hidden sm:inline">Table</span>
            </button>
            <button
              className={`flex items-center gap-1.5 px-3 py-1.5 border-l border-slate-200 transition-colors ${
                viewMode === 'scorecard'
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-slate-50'
              }`}
              onClick={() => setViewMode('scorecard')}
              title="Scorecard View"
            >
              <LayoutGrid className="h-4 w-4" />
              <span className="hidden sm:inline">Scorecard</span>
            </button>
          </div>
          <Button variant="outline" size="sm" onClick={() => window.location.reload()}>
            <RefreshCw className="h-4 w-4 mr-1" />
            Refresh
          </Button>
          <Button size="sm" onClick={() => setShowAddDialog(true)}>
            <Plus className="h-4 w-4 mr-1" />
            Add Scenario
          </Button>
        </div>
      </div>

      {error && (
        <Alert variant="destructive" className="mb-4">
          {error}
        </Alert>
      )}

      {viewMode === 'table' ? (
        /* Table View — all scenarios side by side */
        <ComparisonMatrix scenarios={scenarios} />
      ) : (
        /* Scorecard View — scenario list + selected scenario detail */
        <div className="grid grid-cols-12 gap-6">
          {/* Scenarios List */}
          <div className="col-span-12 lg:col-span-4">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-semibold text-lg">Scenarios</h2>
              <span className="text-sm text-muted-foreground">
                {scenarios.length} scenarios
              </span>
            </div>
            <div className="space-y-3">
              {scenarios.map((scenario) => (
                <ScenarioCard
                  key={scenario.id}
                  scenario={scenario}
                  isSelected={selectedScenarioId === scenario.id}
                  onSelect={setSelectedScenarioId}
                  onRemove={handleRemoveScenario}
                  onPromote={handlePromoteScenario}
                  isBaseline={scenario.isRoot}
                />
              ))}
            </div>
          </div>

          {/* Balanced Scorecard */}
          <div className="col-span-12 lg:col-span-8">
            {selectedScenario ? (
              <>
                <div className="mb-4 flex items-center justify-between">
                  <div>
                    <h2 className="font-semibold text-lg">
                      {selectedScenario.name}
                      {selectedScenario.isRoot && (
                        <span className="ml-2 text-xs font-normal text-amber-600">
                          (Active Baseline)
                        </span>
                      )}
                    </h2>
                    <p className="text-sm text-muted-foreground">
                      {selectedScenario.description}
                    </p>
                  </div>
                  {!selectedScenario.isRoot && (
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Info className="h-4 w-4" />
                      Comparing to baseline
                    </div>
                  )}
                </div>

                {/* Overall Score */}
                <Card className="mb-6 bg-gradient-to-r from-primary/5 to-primary/10">
                  <CardContent className="py-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="text-sm text-muted-foreground mb-1">
                          Overall Scorecard Score
                        </div>
                        <div
                          className={`text-4xl font-bold ${
                            selectedScenario.scorecard.overall_score >= 75
                              ? 'text-green-600'
                              : selectedScenario.scorecard.overall_score >= 70
                              ? 'text-yellow-600'
                              : 'text-red-600'
                          }`}
                        >
                          {selectedScenario.scorecard.overall_score.toFixed(1)}
                          <span className="text-lg font-normal text-slate-400">
                            /100
                          </span>
                        </div>
                      </div>
                      {baselineScenario && selectedScenario.id !== baselineScenario.id && (
                        <div className="text-right">
                          <div className="text-sm text-muted-foreground mb-1">
                            vs Baseline
                          </div>
                          <div
                            className={`text-2xl font-bold ${
                              selectedScenario.scorecard.overall_score >
                              baselineScenario.scorecard.overall_score
                                ? 'text-green-600'
                                : 'text-red-600'
                            }`}
                          >
                            {selectedScenario.scorecard.overall_score >
                            baselineScenario.scorecard.overall_score
                              ? '+'
                              : ''}
                            {(
                              selectedScenario.scorecard.overall_score -
                              baselineScenario.scorecard.overall_score
                            ).toFixed(1)}
                          </div>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>

                {/* Four Perspectives */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <PerspectiveCard
                    title="Financial"
                    icon={TrendingUp}
                    iconColor="text-emerald-500"
                    metrics={selectedScenario.scorecard.financial}
                    baselineMetrics={
                      selectedScenario.id !== baselineScenario?.id
                        ? baselineScenario?.scorecard.financial
                        : null
                    }
                    showComparison={selectedScenario.id !== baselineScenario?.id}
                  />
                  <PerspectiveCard
                    title="Customer"
                    icon={Users}
                    iconColor="text-blue-500"
                    metrics={selectedScenario.scorecard.customer}
                    baselineMetrics={
                      selectedScenario.id !== baselineScenario?.id
                        ? baselineScenario?.scorecard.customer
                        : null
                    }
                    showComparison={selectedScenario.id !== baselineScenario?.id}
                  />
                  <PerspectiveCard
                    title="Operational"
                    icon={Settings}
                    iconColor="text-orange-500"
                    metrics={selectedScenario.scorecard.operational}
                    baselineMetrics={
                      selectedScenario.id !== baselineScenario?.id
                        ? baselineScenario?.scorecard.operational
                        : null
                    }
                    showComparison={selectedScenario.id !== baselineScenario?.id}
                  />
                  <PerspectiveCard
                    title="Strategic"
                    icon={Shield}
                    iconColor="text-purple-500"
                    metrics={selectedScenario.scorecard.strategic}
                    baselineMetrics={
                      selectedScenario.id !== baselineScenario?.id
                        ? baselineScenario?.scorecard.strategic
                        : null
                    }
                    showComparison={selectedScenario.id !== baselineScenario?.id}
                  />
                </div>
              </>
            ) : (
              <Card>
                <CardContent className="py-16 text-center">
                  <BarChart3 className="h-12 w-12 text-slate-300 mx-auto mb-4" />
                  <h3 className="text-lg font-semibold text-slate-500 mb-2">
                    Select a Scenario
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    Choose a scenario from the list to view its balanced scorecard
                  </p>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      )}

      {/* Add Scenario Dialog */}
      {showAddDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-lg mx-4">
            <CardHeader>
              <CardTitle>Add Scenario to Compare</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {AVAILABLE_SCENARIOS.map((scenario) => (
                  <div
                    key={scenario.id}
                    className="p-3 border rounded-lg hover:bg-slate-50 cursor-pointer transition-colors"
                    onClick={() => handleAddScenario(scenario)}
                  >
                    <div className="font-medium">{scenario.name}</div>
                    <div className="text-sm text-muted-foreground">
                      {scenario.description}
                    </div>
                  </div>
                ))}
              </div>
              <div className="flex justify-end gap-2 mt-4 pt-4 border-t">
                <Button variant="outline" onClick={() => setShowAddDialog(false)}>
                  Cancel
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
};

export default SupplyChainAnalytics;
