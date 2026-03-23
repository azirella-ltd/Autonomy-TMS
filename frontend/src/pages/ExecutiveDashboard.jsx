/**
 * Executive Dashboard - SC_VP Landing Page
 *
 * ADH Strategic Level Dashboard - Business Outcome Focused
 *
 * Layout:
 * - Row 1 left: Portfolio Treemap (Geography × Product, revenue size, margin color)
 * - Row 1 right: Model Confidence + ROI
 * - Row 2: Supply Chain Sankey (full width)
 * - Row 3: Tier 1 ASSESS (Revenue Growth, EBIT, ROCS, Gross Margin, Cost to Serve)
 * - Row 3b: Tier 2 DIAGNOSE (POF, C2C, OFCT composites)
 * - Row 4: S&OP Worklist
 * - Row 5: Agent Performance Summary
 */

import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useActiveConfig } from '../contexts/ActiveConfigContext';
import {
  TrendingUp,
  TrendingDown,
  DollarSign,
  Gauge,
  AlertTriangle,
  Bell,
  ChevronRight,
  Bot,
  Brain,
  ArrowRight,
  Package,
  Target,
  BarChart3,
  Sparkles,
  ShieldCheck,
  RefreshCw,
} from 'lucide-react';
import { cn } from '../lib/utils/cn';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Badge,
  Button,
  Spinner,
  Alert,
  useToast,
} from '../components/common';
import { api } from '../services/api';
import { Treemap, ResponsiveContainer, Tooltip } from 'recharts';
import PlanningCascadeSankey from '../components/cascade/PlanningCascadeSankey';
import GartnerMetricCard from '../components/metrics/GartnerMetricCard';
import CompositeMetricCard from '../components/metrics/CompositeMetricCard';
import RoleTimeSeries from '../components/charts/RoleTimeSeries';

// =============================================================================
// Business Outcome KPI Card
// =============================================================================

const BusinessKPICard = ({ title, value, unit, change, changeLabel, icon: Icon, variant = 'default', action }) => {
  const isPositive = change >= 0;
  const changeColor = isPositive ? 'text-green-600' : 'text-red-600';

  const variantStyles = {
    success: 'bg-green-50 border-green-200 dark:bg-green-950/20 dark:border-green-900',
    warning: 'bg-amber-50 border-amber-200 dark:bg-amber-950/20 dark:border-amber-900',
    danger: 'bg-red-50 border-red-200 dark:bg-red-950/20 dark:border-red-900',
    info: 'bg-blue-50 border-blue-200 dark:bg-blue-950/20 dark:border-blue-900',
    default: '',
  };

  const iconStyles = {
    success: 'bg-green-100 text-green-600 dark:bg-green-900 dark:text-green-400',
    warning: 'bg-amber-100 text-amber-600 dark:bg-amber-900 dark:text-amber-400',
    danger: 'bg-red-100 text-red-600 dark:bg-red-900 dark:text-red-400',
    info: 'bg-blue-100 text-blue-600 dark:bg-blue-900 dark:text-blue-400',
    default: 'bg-primary/10 text-primary',
  };

  return (
    <Card className={cn('relative overflow-hidden border', variantStyles[variant])}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{title}</p>
            <div className="mt-1 flex items-baseline gap-1">
              <span className="text-2xl font-bold">
                {typeof value === 'number' ? value.toLocaleString() : value}
              </span>
              {unit && <span className="text-sm text-muted-foreground">{unit}</span>}
            </div>
            {change !== undefined && (
              <div className={cn('mt-1 flex items-center gap-1 text-xs', changeColor)}>
                {isPositive ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                <span>{isPositive ? '+' : ''}{change}{changeLabel || ''}</span>
              </div>
            )}
          </div>
          {Icon && (
            <div className={cn('rounded-lg p-2', iconStyles[variant])}>
              <Icon className="h-5 w-5" />
            </div>
          )}
        </div>
        {action && (
          <Button
            variant="ghost"
            size="sm"
            className="mt-2 w-full justify-between text-xs"
            onClick={action.onClick}
          >
            {action.label}
            <ChevronRight className="h-3 w-3" />
          </Button>
        )}
      </CardContent>
    </Card>
  );
};

// =============================================================================
// Portfolio Treemap Component
// =============================================================================

const getMarginColor = (margin) => {
  // Color scale from red (low margin) to green (high margin)
  // Based on industry standard beverage margins (typically 22-40%)
  if (margin >= 38) return '#16a34a'; // green-600 - excellent
  if (margin >= 34) return '#22c55e'; // green-500 - very good
  if (margin >= 30) return '#84cc16'; // lime-500 - good
  if (margin >= 26) return '#eab308'; // yellow-500 - acceptable
  if (margin >= 22) return '#f97316'; // orange-500 - needs attention
  return '#ef4444'; // red-500 - critical
};

// Helper to wrap text within a given width
const wrapText = (text, maxWidth, fontSize) => {
  const avgCharWidth = fontSize * 0.55; // Approximate average character width
  const maxChars = Math.floor(maxWidth / avgCharWidth);

  if (text.length <= maxChars) return [text];

  const words = text.split(' ');
  const lines = [];
  let currentLine = '';

  words.forEach(word => {
    if ((currentLine + ' ' + word).trim().length <= maxChars) {
      currentLine = (currentLine + ' ' + word).trim();
    } else {
      if (currentLine) lines.push(currentLine);
      currentLine = word;
    }
  });
  if (currentLine) lines.push(currentLine);

  return lines.slice(0, 3); // Max 3 lines
};

const TreemapContent = (props) => {
  const { x, y, width, height, name, revenue, margin, cost } = props;

  // Skip if no dimensions or no name
  if (!width || !height || width <= 0 || height <= 0 || !name) return null;

  // Calculate margin from cost/revenue if not provided directly
  const calculatedMargin = margin ?? (revenue && cost ? ((revenue - cost) / revenue) * 100 : 30);
  const color = getMarginColor(calculatedMargin);

  // Font sizing based on box dimensions
  const fontSize = Math.min(13, Math.max(9, Math.min(width / 10, height / 5)));
  const showDetails = width > 70 && height > 45;
  const showName = width > 40 && height > 25;

  // Wrap the name text
  const nameLines = showName ? wrapText(name, width - 8, fontSize) : [];
  const lineHeight = fontSize + 4;
  const totalTextHeight = nameLines.length * lineHeight + (showDetails ? lineHeight : 0);
  const startY = y + (height - totalTextHeight) / 2 + fontSize;

  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        style={{
          fill: color,
          stroke: '#fff',
          strokeWidth: 1.5,
          strokeOpacity: 1,
        }}
      />
      {showName && nameLines.map((line, i) => (
        <text
          key={i}
          x={x + width / 2}
          y={startY + i * lineHeight}
          textAnchor="middle"
          fill="#fff"
          fontSize={fontSize}
          fontWeight="700"
          style={{
            textShadow: '0 1px 3px rgba(0,0,0,0.6)',
            fontFamily: 'system-ui, -apple-system, sans-serif',
            letterSpacing: '0.01em',
          }}
        >
          {line}
        </text>
      ))}
      {showDetails && revenue && (
        <text
          x={x + width / 2}
          y={startY + nameLines.length * lineHeight}
          textAnchor="middle"
          fill="#fff"
          fontSize={fontSize - 1}
          fontWeight="500"
          style={{
            textShadow: '0 1px 3px rgba(0,0,0,0.6)',
            fontFamily: 'system-ui, -apple-system, sans-serif',
          }}
        >
          ${(revenue / 1000000).toFixed(0)}M • {calculatedMargin?.toFixed(0)}%
        </text>
      )}
    </g>
  );
};

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload || !payload.length) return null;

  const data = payload[0].payload;
  if (!data.revenue) return null;

  // Calculate margin from cost if margin not provided
  const margin = data.margin ?? (data.cost ? ((data.revenue - data.cost) / data.revenue) * 100 : null);

  return (
    <div className="bg-white dark:bg-gray-800 p-3 rounded-lg shadow-lg border min-w-[180px]">
      <p className="font-semibold text-sm">{data.name}</p>
      <div className="mt-1 space-y-0.5">
        <p className="text-xs text-muted-foreground flex justify-between">
          <span>Revenue:</span>
          <span className="font-medium">${(data.revenue / 1000000).toFixed(1)}M</span>
        </p>
        {data.cost && (
          <p className="text-xs text-muted-foreground flex justify-between">
            <span>Cost:</span>
            <span className="font-medium">${(data.cost / 1000000).toFixed(1)}M</span>
          </p>
        )}
        {margin != null && (
          <p className="text-xs flex justify-between">
            <span className="text-muted-foreground">Margin:</span>
            <span className={cn(
              'font-semibold',
              margin >= 30 ? 'text-green-600' : margin >= 25 ? 'text-yellow-600' : 'text-red-600'
            )}>
              {margin.toFixed(1)}%
            </span>
          </p>
        )}
      </div>
    </div>
  );
};

const PortfolioTreemap = ({ data }) => {
  if (!data) return null;

  // Flatten the hierarchy for Recharts Treemap with cost data
  const flatData = [];
  data.children?.forEach(region => {
    region.children?.forEach(product => {
      flatData.push({
        name: `${region.name} - ${product.name}`,
        size: product.revenue,
        revenue: product.revenue,
        cost: product.cost,
        margin: product.margin,
        region: region.name,
        product: product.name,
      });
    });
  });

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <div>
          <CardTitle className="text-lg flex items-center gap-2">
            <Package className="h-5 w-5" />
            Portfolio Performance
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            Revenue by Geography × Product (color = margin)
          </p>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded" style={{ backgroundColor: '#ef4444' }} />
            &lt;22%
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded" style={{ backgroundColor: '#f97316' }} />
            22-26%
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded" style={{ backgroundColor: '#eab308' }} />
            26-30%
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded" style={{ backgroundColor: '#84cc16' }} />
            30-34%
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded" style={{ backgroundColor: '#22c55e' }} />
            &gt;34%
          </span>
        </div>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={350}>
          <Treemap
            data={flatData}
            dataKey="size"
            aspectRatio={4 / 3}
            stroke="#fff"
            content={<TreemapContent />}
          >
            <Tooltip content={<CustomTooltip />} />
          </Treemap>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
};

// =============================================================================
// S&OP Worklist Preview
// =============================================================================

const SOPWorklistPreview = ({ items, onViewAll }) => {
  const urgencyStyles = {
    urgent: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
    high: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
    medium: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-lg">Top S&OP Items</CardTitle>
        <Button variant="outline" size="sm" onClick={onViewAll} className="gap-1">
          View All <ArrowRight className="h-4 w-4" />
        </Button>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th className="pb-2 pr-4 font-medium">Urgency</th>
                <th className="pb-2 pr-4 font-medium">Item</th>
                <th className="pb-2 pr-4 font-medium">Category</th>
                <th className="pb-2 pr-4 font-medium">Impact</th>
                <th className="pb-2 font-medium text-right">Due</th>
              </tr>
            </thead>
            <tbody>
              {items?.map((item) => (
                <tr
                  key={item.id}
                  className="border-b last:border-0 hover:bg-muted/50 transition-colors cursor-pointer"
                >
                  <td className="py-2.5 pr-4">
                    <Badge className={urgencyStyles[item.urgency] || urgencyStyles.medium} size="sm">
                      {item.urgency}
                    </Badge>
                  </td>
                  <td className="py-2.5 pr-4 font-medium">{item.title}</td>
                  <td className="py-2.5 pr-4 text-muted-foreground">{item.category}</td>
                  <td className="py-2.5 pr-4 text-muted-foreground">{item.impact}</td>
                  <td className="py-2.5 text-right text-muted-foreground">{item.due}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
};

// =============================================================================
// ROI Card
// =============================================================================

const ROICard = ({ data }) => {
  const fmt = (v) => (v != null ? v : '--');
  const invRed = data?.inventory_reduction_pct;
  const svcLvl = data?.service_level;
  const fcstFrom = data?.forecast_accuracy_from;
  const fcstTo = data?.forecast_accuracy_to;
  const revInc = data?.revenue_increase_pct;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-lg flex items-center gap-2">
          <DollarSign className="h-5 w-5 text-green-600" />
          ROI and Costs
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <p className={`text-2xl font-bold ${invRed != null ? 'text-green-600' : 'text-muted-foreground'}`}>
              {invRed != null ? `-${invRed}%` : '--'}
            </p>
            <p className="text-xs text-muted-foreground">
              Inventory reduced
            </p>
          </div>
          <div className="space-y-1">
            <p className={`text-2xl font-bold ${svcLvl != null ? 'text-green-600' : 'text-muted-foreground'}`}>
              {svcLvl != null ? `${svcLvl}%` : '--'}
            </p>
            <p className="text-xs text-muted-foreground">
              Service level maintained
            </p>
          </div>
          <div className="space-y-1">
            <p className={`text-2xl font-bold ${fcstFrom != null ? 'text-green-600' : 'text-muted-foreground'}`}>
              {fcstFrom != null && fcstTo != null ? `${fcstFrom}% → ${fcstTo}%` : '--'}
            </p>
            <p className="text-xs text-muted-foreground">
              Forecast accuracy
            </p>
          </div>
          <div className="space-y-1">
            <p className={`text-2xl font-bold ${revInc != null ? 'text-green-600' : 'text-muted-foreground'}`}>
              {revInc != null ? `+${revInc}%` : '--'}
            </p>
            <p className="text-xs text-muted-foreground">
              Revenue increased
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

// =============================================================================
// Model Confidence Card (Conformal Prediction Status)
// =============================================================================

const ModelConfidenceCard = ({ conformalStatus, onRecalibrate, recalibrating }) => {
  const demandCoverage = conformalStatus?.summary?.demand_coverage_actual || 0;
  const leadTimeCoverage = conformalStatus?.summary?.lead_time_coverage_actual || 0;
  const jointCoverage = conformalStatus?.joint_coverage_guarantee || 0;
  const stalePredictors = conformalStatus?.stale_predictors || [];
  const demandPredictors = conformalStatus?.summary?.demand_predictors || 0;
  const leadTimePredictors = conformalStatus?.summary?.lead_time_predictors || 0;

  // Determine overall status
  const isHealthy = demandCoverage >= 85 && leadTimeCoverage >= 80 && stalePredictors.length === 0;
  const isWarning = !isHealthy && (demandCoverage >= 70 || leadTimeCoverage >= 70);
  const isDanger = demandCoverage < 70 || leadTimeCoverage < 70;

  const statusVariant = isHealthy ? 'success' : isWarning ? 'warning' : 'danger';
  const statusText = isHealthy ? 'Healthy' : isWarning ? 'Attention Needed' : 'Recalibration Required';

  const CoverageBar = ({ label, value, target, variant }) => {
    const ratio = Math.min((value / target) * 100, 100);
    const barColor = variant === 'success' ? 'bg-green-500' : variant === 'warning' ? 'bg-amber-500' : 'bg-red-500';

    return (
      <div className="space-y-1">
        <div className="flex justify-between text-xs">
          <span className="text-muted-foreground">{label}</span>
          <span className="font-medium">{value.toFixed(0)}% / {target}%</span>
        </div>
        <div className="h-2 bg-muted rounded-full overflow-hidden">
          <div
            className={cn('h-full rounded-full transition-all', barColor)}
            style={{ width: `${ratio}%` }}
          />
        </div>
      </div>
    );
  };

  return (
    <Card className={cn(
      'border-2',
      isHealthy && 'border-green-200 bg-green-50/30 dark:border-green-900 dark:bg-green-950/10',
      isWarning && 'border-amber-200 bg-amber-50/30 dark:border-amber-900 dark:bg-amber-950/10',
      isDanger && 'border-red-200 bg-red-50/30 dark:border-red-900 dark:bg-red-950/10'
    )}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-amber-500" />
            Model Confidence
          </CardTitle>
          <Badge variant={statusVariant} className="gap-1">
            <ShieldCheck className="h-3 w-3" />
            {statusText}
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground">
          Conformal prediction coverage guarantees
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Coverage Bars */}
        <div className="space-y-3">
          <CoverageBar
            label="Demand Coverage"
            value={demandCoverage}
            target={90}
            variant={demandCoverage >= 85 ? 'success' : demandCoverage >= 70 ? 'warning' : 'danger'}
          />
          <CoverageBar
            label="Lead Time Coverage"
            value={leadTimeCoverage}
            target={85}
            variant={leadTimeCoverage >= 80 ? 'success' : leadTimeCoverage >= 65 ? 'warning' : 'danger'}
          />
        </div>

        {/* Joint Coverage */}
        <div className="p-3 bg-muted/50 rounded-lg">
          <div className="flex justify-between items-center">
            <span className="text-sm">Joint Coverage Guarantee</span>
            <span className="text-xl font-bold">{(jointCoverage * 100).toFixed(0)}%</span>
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            {demandPredictors} demand × {leadTimePredictors} lead time predictors calibrated
          </p>
        </div>

        {/* Stale Predictors Warning */}
        {stalePredictors.length > 0 && (
          <Alert variant="warning" className="py-2">
            <AlertTriangle className="h-4 w-4" />
            <span className="text-xs ml-2">
              {stalePredictors.length} predictor{stalePredictors.length > 1 ? 's' : ''} need recalibration
            </span>
          </Alert>
        )}

        {/* Recalibrate Button */}
        <Button
          variant="default"
          size="sm"
          className="w-full gap-2"
          onClick={onRecalibrate}
          disabled={recalibrating}
        >
          <RefreshCw className={`h-4 w-4 ${recalibrating ? 'animate-spin' : ''}`} />
          {recalibrating ? 'Calibrating…' : 'Recalibrate Predictors Now'}
        </Button>
      </CardContent>
    </Card>
  );
};

// =============================================================================
// Agent Performance Summary Card
// =============================================================================

const PerformanceSummary = ({ summary }) => {
  const agentScore = summary?.agent_score;
  const plannerScore = summary?.planner_score;
  const autonomousPct = summary?.autonomous_decisions_pct;

  const perfDelta = (agentScore != null && plannerScore != null)
    ? (agentScore - plannerScore).toFixed(1)
    : null;
  const overrideRate = autonomousPct != null
    ? (100 - autonomousPct).toFixed(1)
    : null;

  return (
    <div className="grid grid-cols-2 gap-4">
      <Card>
        <CardContent className="p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Agent Performance</p>
              <p className={`text-2xl font-bold ${perfDelta != null ? 'text-green-600' : 'text-muted-foreground'}`}>
                {perfDelta != null ? `+${perfDelta}%` : '--'}
              </p>
              <p className="text-xs text-muted-foreground">
                {perfDelta != null
                  ? `Agent decisions outperforming manual by ${perfDelta} points`
                  : 'No performance data yet'}
              </p>
            </div>
            <div className="p-3 bg-green-100 text-green-600 rounded-lg">
              <Bot className="h-6 w-6" />
            </div>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Human Override Rate</p>
              <p className={`text-2xl font-bold ${overrideRate != null ? 'text-amber-600' : 'text-muted-foreground'}`}>
                {overrideRate != null ? `${overrideRate}%` : '--'}
              </p>
              <p className="text-xs text-muted-foreground">
                Percentage of decisions overridden by humans
              </p>
            </div>
            <div className="p-3 bg-amber-100 text-amber-600 rounded-lg">
              <Brain className="h-6 w-6" />
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

// =============================================================================
// Main Executive Dashboard Component
// =============================================================================

const ExecutiveDashboard = () => {
  const navigate = useNavigate();
  const toast = useToast();
  const { activeConfigId } = useActiveConfig();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);
  const [planningCycle, setPlanningCycle] = useState('Q3 2025');
  const [conformalStatus, setConformalStatus] = useState(null);
  const [gartnerMetrics, setGartnerMetrics] = useState(null);
  const [recalibrating, setRecalibrating] = useState(false);
  const [planConfidence, setPlanConfidence] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const [dashResponse, metricsResponse] = await Promise.allSettled([
          api.get('/decision-metrics/executive-dashboard', {
            params: { planning_cycle: planningCycle }
          }),
          api.get('/hierarchical-metrics/dashboard'),
        ]);
        if (dashResponse.status === 'fulfilled') {
          setData(dashResponse.value.data.data);
        }
        if (metricsResponse.status === 'fulfilled') {
          const md = metricsResponse.value.data;
          setGartnerMetrics(md?.data || md);
        }
        setError(null);
      } catch (err) {
        console.error('Failed to fetch executive dashboard:', err);
        setError('Failed to load dashboard data');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [planningCycle]);

  // Fetch conformal prediction status and latest plan confidence
  useEffect(() => {
    const fetchConformalStatus = async () => {
      try {
        const response = await api.get('/conformal-prediction/suite/status');
        setConformalStatus(response.data);
      } catch (err) {
        console.error('Failed to fetch conformal status:', err);
        setConformalStatus(null);
      }
    };

    const fetchLatestPlanConfidence = async () => {
      try {
        const plansResp = await api.get('/supply-plan/list');
        const completed = (plansResp.data.plans || []).filter(p => p.status === 'COMPLETED');
        if (completed.length > 0) {
          const resultResp = await api.get(`/supply-plan/result/${completed[0].id}`);
          if (resultResp.data?.plan_confidence) {
            setPlanConfidence(resultResp.data.plan_confidence);
          }
        }
      } catch (err) {
        console.error('Failed to fetch plan confidence:', err);
      }
    };

    fetchConformalStatus();
    fetchLatestPlanConfidence();
  }, []);

  const handleRecalibrate = async () => {
    setRecalibrating(true);
    try {
      const calibrateResponse = await api.post('/conformal-prediction/demo/calibrate');
      // Refresh status after calibration
      const response = await api.get('/conformal-prediction/suite/status');
      setConformalStatus(response.data);

      const nPredictors = calibrateResponse.data?.suite_summary?.total_predictors ?? null;
      toast({
        title: 'Predictors Recalibrated',
        description: nPredictors != null
          ? `Successfully calibrated ${nPredictors} conformal predictors.`
          : 'Conformal prediction suite recalibrated successfully.',
        status: 'success',
        duration: 5000,
      });
    } catch (err) {
      console.error('Recalibration failed:', err);
      toast({
        title: 'Recalibration Failed',
        description: err.response?.data?.detail || err.message || 'An unexpected error occurred.',
        status: 'error',
        duration: 7000,
      });
    } finally {
      setRecalibrating(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <Alert variant="error">{error}</Alert>
      </div>
    );
  }

  const { summary, roi, treemap, business_outcomes, sop_worklist_preview } = data || {};

  return (
    <div className="p-6 space-y-6">
      {/* Role time series header */}
      <RoleTimeSeries roleKey="executive" configId={activeConfigId} compact />

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="text-muted-foreground">
            Performance overview across all business units
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-muted/50 rounded-lg border">
            <span className="text-xs text-muted-foreground">Period:</span>
            <select
              value={planningCycle}
              onChange={(e) => setPlanningCycle(e.target.value)}
              className="text-sm font-medium bg-transparent border-none focus:outline-none focus:ring-0 cursor-pointer pr-6"
            >
              <option value="Q3 2025">Q3 2025</option>
              <option value="Q2 2025">Q2 2025</option>
              <option value="Q1 2025">Q1 2025</option>
              <option value="Q4 2024">Q4 2024</option>
            </select>
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span className="h-1.5 w-1.5 rounded-full bg-green-500 animate-pulse" />
            <span>Live</span>
          </div>
        </div>
      </div>

      {/* Row 1: Portfolio Treemap (left) + Model Confidence & ROI (right) */}
      <div className="grid grid-cols-3 gap-4">
        <div className="col-span-2">
          <PortfolioTreemap data={treemap} />
        </div>
        <div className="space-y-4">
          <ModelConfidenceCard
            conformalStatus={conformalStatus}
            onRecalibrate={handleRecalibrate}
            recalibrating={recalibrating}
          />
          {/* Plan-Level Confidence (from last completed supply plan) */}
          {planConfidence && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-lg flex items-center gap-2">
                  <Target className="h-5 w-5 text-blue-600" />
                  Plan Confidence
                </CardTitle>
                <p className="text-xs text-muted-foreground">Latest supply plan composite score</p>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-3 mb-3">
                  <span className={`text-3xl font-bold ${
                    planConfidence.confidence_level === 'high' ? 'text-green-600' :
                    planConfidence.confidence_level === 'moderate' ? 'text-amber-600' : 'text-red-600'
                  }`}>
                    {(planConfidence.overall * 100).toFixed(0)}%
                  </span>
                  <Badge variant={
                    planConfidence.confidence_level === 'high' ? 'success' :
                    planConfidence.confidence_level === 'moderate' ? 'warning' : 'destructive'
                  }>
                    {planConfidence.confidence_level}
                  </Badge>
                </div>
                <div className="space-y-1 text-xs text-muted-foreground">
                  <div className="flex justify-between">
                    <span>Demand coverage</span>
                    <span>{(planConfidence.demand_coverage_score * 100).toFixed(0)}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Lead time coverage</span>
                    <span>{(planConfidence.lead_time_coverage_score * 100).toFixed(0)}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Safety stock adequacy</span>
                    <span>{(planConfidence.safety_stock_adequacy * 100).toFixed(0)}%</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
          <ROICard data={roi} />
        </div>
      </div>

      {/* Row 2: Supply Chain Sankey (full width) */}
      <PlanningCascadeSankey configId={activeConfigId} height={300} />

      {/* Row 3: Gartner Tier 1 ASSESS — Strategic Metrics */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-lg font-semibold">Tier 1 — ASSESS</h2>
            <p className="text-xs text-muted-foreground">Strategic performance attributes (SCOR RL/RS/AG/CO/AM)</p>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="gap-1"
            onClick={() => navigate('/planning/metrics')}
          >
            View Full Metrics <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
        {gartnerMetrics?.tiers?.tier1_assess?.metrics ? (
          <div className="grid grid-cols-5 gap-3">
            {Object.entries(gartnerMetrics.tiers.tier1_assess.metrics).map(([key, m]) => (
              <GartnerMetricCard
                key={key}
                label={m.label}
                value={m.value}
                unit={m.unit}
                target={m.target}
                trend={m.trend}
                benchmark={m.benchmark}
                status={m.status}
                tier="tier1"
                scorCode={m.scor_code}
                lowerIsBetter={m.lower_is_better}
                ciLower={m.ci_lower}
                ciUpper={m.ci_upper}
                n={m.n}
                compact
              />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-5 gap-3">
            <GartnerMetricCard label="Revenue Growth" value={8.2} unit="%" target={10} trend={1.5} status="warning" tier="tier1" scorCode="RL.1.1" compact />
            <GartnerMetricCard label="EBIT Margin" value={14.8} unit="%" target={15} trend={0.3} status="warning" tier="tier1" scorCode="CO.1.1" compact />
            <GartnerMetricCard label="Return on SC Assets" value={18.5} unit="%" target={20} trend={-0.8} status="warning" tier="tier1" scorCode="AM.1.1" compact />
            <GartnerMetricCard label="Gross Margin" value={business_outcomes?.gross_margin?.value || 32.5} unit="%" target={35} trend={business_outcomes?.gross_margin?.change || 2.1} status="success" tier="tier1" compact />
            <GartnerMetricCard label="Total Cost to Serve" value={22.3} unit="%" target={20} trend={-0.5} status="warning" tier="tier1" lowerIsBetter compact />
          </div>
        )}
      </div>

      {/* Row 3b: Gartner Tier 2 DIAGNOSE — Composite Metrics */}
      <div>
        <h2 className="text-lg font-semibold mb-3">Tier 2 — DIAGNOSE</h2>
        {gartnerMetrics?.tiers?.tier2_diagnose?.metrics ? (
          <div className="grid grid-cols-3 gap-4">
            {Object.entries(gartnerMetrics.tiers.tier2_diagnose.metrics).map(([key, m]) => (
              <CompositeMetricCard
                key={key}
                label={m.label}
                value={m.value}
                unit={m.unit}
                target={m.target}
                trend={m.trend}
                benchmark={m.benchmark}
                status={m.status}
                scorCode={m.scor_code}
                formula={m.formula}
                components={m.components}
                lowerIsBetter={m.lower_is_better}
                ciLower={m.ci_lower}
                ciUpper={m.ci_upper}
                n={m.n}
              />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-4">
            <CompositeMetricCard
              label="Perfect Order Fulfillment"
              value={91.3}
              unit="%"
              target={95}
              trend={1.2}
              status="warning"
              scorCode="RL.1.1"
              formula="POF = OTD × IF × DF × DA"
              components={{
                otd: { label: 'On-Time Delivery', value: 96.2, unit: '%', target: 98 },
                if: { label: 'In-Full', value: 97.1, unit: '%', target: 99 },
                df: { label: 'Damage-Free', value: 99.5, unit: '%', target: 99.5 },
                da: { label: 'Documentation Accuracy', value: 98.1, unit: '%', target: 99 },
              }}
            />
            <CompositeMetricCard
              label="Cash-to-Cash Cycle"
              value={42}
              unit="days"
              target={35}
              trend={-2.5}
              status="warning"
              scorCode="AM.1.1"
              formula="C2C = DIO + DSO − DPO"
              lowerIsBetter
              components={{
                dio: { label: 'Days Inventory Outstanding', value: 28, unit: 'days', target: 22 },
                dso: { label: 'Days Sales Outstanding', value: 34, unit: 'days', target: 30 },
                dpo: { label: 'Days Payable Outstanding', value: 20, unit: 'days', target: 17 },
              }}
            />
            <CompositeMetricCard
              label="Order Fulfillment Cycle Time"
              value={4.2}
              unit="days"
              target={3.5}
              trend={-0.3}
              status="warning"
              scorCode="RS.1.1"
              formula="OFCT = Source + Make + Deliver"
              lowerIsBetter
              components={{
                source: { label: 'Source Cycle Time', value: 1.8, unit: 'days', target: 1.5 },
                make: { label: 'Make Cycle Time', value: 1.2, unit: 'days', target: 1.0 },
                deliver: { label: 'Deliver Cycle Time', value: 1.2, unit: 'days', target: 1.0 },
              }}
            />
          </div>
        )}
      </div>

      {/* Row 3c: Gartner Tier 3 CORRECT — Operational Metrics */}
      <div>
        <h2 className="text-lg font-semibold mb-3">Tier 3 — CORRECT</h2>
        {gartnerMetrics?.tiers?.tier3_correct?.categories ? (
          <div className="space-y-4">
            {Object.entries(gartnerMetrics.tiers.tier3_correct.categories).map(([catKey, cat]) => (
              <div key={catKey}>
                <h3 className="text-sm font-medium text-muted-foreground mb-2">{cat.label || catKey}</h3>
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                  {cat.metrics && Object.entries(cat.metrics).map(([key, m]) => (
                    <GartnerMetricCard
                      key={key}
                      label={m.label}
                      value={m.value}
                      unit={m.unit}
                      target={m.target}
                      trend={m.trend}
                      status={m.status}
                      tier="tier3"
                      agent={m.agent}
                      lowerIsBetter={m.lower_is_better}
                      ciLower={m.ci_lower}
                      ciUpper={m.ci_upper}
                      n={m.n}
                      compact
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-sm text-muted-foreground py-4">No Tier 3 data available.</div>
        )}
      </div>

      {/* Row 4: S&OP Worklist (full width table) */}
      <SOPWorklistPreview
        items={sop_worklist_preview}
        onViewAll={() => navigate('/sop-worklist')}
      />

      {/* Row 5: Agent Performance Summary */}
      <PerformanceSummary summary={summary} />
    </div>
  );
};

export default ExecutiveDashboard;
