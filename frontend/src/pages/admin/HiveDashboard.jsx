/**
 * Hive Lifecycle Dashboard
 *
 * Visualizes the TRM Hive architecture for a supply chain site:
 * - Urgency vector heatmap (11 TRM slots)
 * - Signal bus timeline (active signals with decay)
 * - Decision cycle phases (SENSE → ASSESS → ACQUIRE → PROTECT → BUILD → REFLECT)
 * - Signal divergence gauge (local vs tGNN prediction)
 * - tGNN directive status panel
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  Card, CardContent, CardHeader, CardTitle,
  Tabs, TabsList, TabsTrigger, TabsContent,
  Alert, Badge, Button,
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
  Tooltip, TooltipContent, TooltipProvider, TooltipTrigger,
  Progress,
} from '../../components/common';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip as RechartsTooltip, Legend, ResponsiveContainer,
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  Cell,
} from 'recharts';
import {
  Activity, AlertTriangle, CheckCircle, Clock, RefreshCw,
  Play, Gauge, Brain, Layers, TrendingUp, Zap,
  Radio, ArrowRight, Shield, Hammer, Eye, Search,
  HeartPulse, Network, Signal, Bug,
} from 'lucide-react';
import { api } from '../../services/api';
import hiveApi from '../../services/hiveApi';

// ============================================================================
// Constants
// ============================================================================

const PHASE_CONFIG = [
  { name: 'SENSE', label: 'Sense', icon: Search, color: '#3b82f6', description: 'Scouts detect demand signals' },
  { name: 'ASSESS', label: 'Assess', icon: HeartPulse, color: '#8b5cf6', description: 'Nurses evaluate colony health' },
  { name: 'ACQUIRE', label: 'Acquire', icon: Zap, color: '#f59e0b', description: 'Foragers secure resources' },
  { name: 'PROTECT', label: 'Protect', icon: Shield, color: '#ef4444', description: 'Guards ensure integrity' },
  { name: 'BUILD', label: 'Build', icon: Hammer, color: '#10b981', description: 'Builders execute production' },
  { name: 'REFLECT', label: 'Reflect', icon: Eye, color: '#6366f1', description: 'Queen aggregates & reflects' },
];

const CASTE_COLORS = {
  scout: '#3b82f6',
  forager: '#f59e0b',
  nurse: '#8b5cf6',
  guard: '#ef4444',
  builder: '#10b981',
};

const TRM_CASTE_MAP = {
  atp_executor: 'scout',
  order_tracking: 'scout',
  po_creation: 'forager',
  inventory_rebalancing: 'forager',
  subcontracting: 'forager',
  inventory_buffer: 'nurse',
  forecast_adjustment: 'nurse',
  quality_disposition: 'guard',
  maintenance_scheduling: 'guard',
  mo_execution: 'builder',
  to_execution: 'builder',
};

// ============================================================================
// Sub-Components
// ============================================================================

const StatCard = ({ title, value, subtitle, icon: Icon, color = 'blue' }) => (
  <Card>
    <CardContent className="p-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-muted-foreground">{title}</p>
          <p className="text-2xl font-bold">{value}</p>
          {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
        </div>
        <div className={`p-3 rounded-lg bg-${color}-100 dark:bg-${color}-900/20`}>
          <Icon className={`h-6 w-6 text-${color}-600 dark:text-${color}-400`} />
        </div>
      </div>
    </CardContent>
  </Card>
);

/** Urgency cell with color intensity based on value 0-1 */
const UrgencyCell = ({ name, value, direction }) => {
  const intensity = Math.round(value * 255);
  const caste = TRM_CASTE_MAP[name] || 'scout';
  const baseColor = CASTE_COLORS[caste];
  const opacity = 0.15 + value * 0.85;
  const label = name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div
            className="rounded-lg p-3 text-center cursor-default transition-all"
            style={{
              backgroundColor: `${baseColor}${Math.round(opacity * 255).toString(16).padStart(2, '0')}`,
              border: value > 0.7 ? `2px solid ${baseColor}` : '1px solid transparent',
            }}
          >
            <div className="text-xs font-medium truncate">{label}</div>
            <div className="text-lg font-bold">{value.toFixed(2)}</div>
            {direction && (
              <div className="text-xs opacity-70">
                {direction === 'shortage' ? '▼' : direction === 'surplus' ? '▲' : '●'} {direction}
              </div>
            )}
          </div>
        </TooltipTrigger>
        <TooltipContent>
          <p>{label}: urgency {value.toFixed(3)}</p>
          <p>Direction: {direction || 'none'}</p>
          <p>Caste: {caste}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};

/** Decision cycle phase visualization */
const PhaseTimeline = ({ phases, lastCycleResult }) => (
  <div className="flex items-center gap-1 overflow-x-auto py-4">
    {PHASE_CONFIG.map((phase, idx) => {
      const PhaseIcon = phase.icon;
      const cyclePhase = lastCycleResult?.phases?.find(p => p.name === phase.name);
      const isActive = cyclePhase != null;
      const hasErrors = cyclePhase?.errors?.length > 0;

      return (
        <React.Fragment key={phase.name}>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <div
                  className={`flex flex-col items-center p-3 rounded-lg min-w-[100px] transition-all ${
                    isActive
                      ? hasErrors
                        ? 'bg-red-50 dark:bg-red-900/20 ring-2 ring-red-300'
                        : 'bg-accent ring-2 ring-primary/30'
                      : 'bg-muted/50'
                  }`}
                >
                  <PhaseIcon
                    className="h-5 w-5 mb-1"
                    style={{ color: isActive ? phase.color : '#9ca3af' }}
                  />
                  <span className="text-xs font-semibold">{phase.label}</span>
                  <span className="text-[10px] text-muted-foreground">{phase.description}</span>
                  {cyclePhase && (
                    <div className="mt-1 text-[10px] space-y-0.5">
                      <div>{cyclePhase.trms_executed?.length || 0} TRMs</div>
                      <div>{cyclePhase.signals_emitted} signals</div>
                      <div>{cyclePhase.duration_ms?.toFixed(1)}ms</div>
                    </div>
                  )}
                </div>
              </TooltipTrigger>
              <TooltipContent>
                <p className="font-semibold">{phase.label} Phase</p>
                <p>{phase.description}</p>
                {cyclePhase && (
                  <>
                    <p>TRMs: {cyclePhase.trms_executed?.join(', ') || 'none'}</p>
                    <p>Duration: {cyclePhase.duration_ms?.toFixed(2)}ms</p>
                  </>
                )}
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
          {idx < PHASE_CONFIG.length - 1 && (
            <ArrowRight className="h-4 w-4 text-muted-foreground flex-shrink-0" />
          )}
        </React.Fragment>
      );
    })}
  </div>
);

/** Signal divergence gauge */
const DivergenceGauge = ({ score, threshold = 0.30 }) => {
  const percentage = Math.min(score * 100, 100);
  const thresholdPct = threshold * 100;
  const isTriggered = score > threshold;
  const color = isTriggered ? '#ef4444' : score > threshold * 0.7 ? '#f59e0b' : '#10b981';

  return (
    <div className="space-y-2">
      <div className="flex justify-between items-center">
        <span className="text-sm font-medium">Signal Divergence</span>
        <Badge variant={isTriggered ? 'destructive' : 'outline'}>
          {isTriggered ? 'TGNN REFRESH NEEDED' : 'Normal'}
        </Badge>
      </div>
      <div className="relative h-6 bg-muted rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${percentage}%`, backgroundColor: color }}
        />
        <div
          className="absolute top-0 h-full w-0.5 bg-yellow-500"
          style={{ left: `${thresholdPct}%` }}
        />
      </div>
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>0.00</span>
        <span style={{ marginLeft: `${thresholdPct - 10}%` }}>threshold: {threshold}</span>
        <span>1.00</span>
      </div>
      <p className="text-sm">
        Score: <strong style={{ color }}>{score.toFixed(3)}</strong>
      </p>
    </div>
  );
};

/** Signal list with type badges and urgency bars */
const SignalList = ({ signals }) => {
  if (!signals || signals.length === 0) {
    return <p className="text-sm text-muted-foreground py-4">No active signals</p>;
  }

  return (
    <div className="space-y-2 max-h-[400px] overflow-y-auto">
      {signals.map((sig, idx) => (
        <div key={idx} className="flex items-center gap-3 p-2 rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors">
          <Signal className="h-4 w-4 text-muted-foreground flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="text-[10px]">
                {sig.signal_type || sig.type}
              </Badge>
              <span className="text-xs text-muted-foreground">from {sig.source_trm || sig.source}</span>
            </div>
            <div className="flex items-center gap-2 mt-1">
              <div className="flex-1 h-1.5 bg-muted rounded-full">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${(sig.urgency || 0) * 100}%`,
                    backgroundColor: sig.direction === 'shortage' ? '#ef4444'
                      : sig.direction === 'surplus' ? '#10b981'
                      : sig.direction === 'risk' ? '#f59e0b' : '#3b82f6',
                  }}
                />
              </div>
              <span className="text-[10px] text-muted-foreground w-8">{(sig.urgency || 0).toFixed(2)}</span>
            </div>
          </div>
          <span className="text-[10px] text-muted-foreground">
            {sig.direction || '—'}
          </span>
        </div>
      ))}
    </div>
  );
};

// ============================================================================
// Main Dashboard
// ============================================================================

const HiveDashboard = () => {
  const [siteKey, setSiteKey] = useState('default_site');
  const [hiveStatus, setHiveStatus] = useState(null);
  const [cycleInfo, setCycleInfo] = useState(null);
  const [lastCycleResult, setLastCycleResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [authThreads, setAuthThreads] = useState([]);
  const [authStats, setAuthStats] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const [statusRes, cycleRes] = await Promise.all([
        api.get(`/api/v1/site-agent/hive/status/${siteKey}`),
        api.get(`/api/v1/site-agent/hive/decision-cycle/${siteKey}`),
      ]);
      setHiveStatus(statusRes.data);
      setCycleInfo(cycleRes.data);
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
    // Fetch authorization data (non-blocking)
    try {
      const [threadsRes, statsRes] = await Promise.all([
        hiveApi.getAuthThreads(),
        hiveApi.getAuthStats(),
      ]);
      setAuthThreads(threadsRes.data?.threads || []);
      setAuthStats(statsRes.data);
    } catch (_) {
      // Authorization data is supplementary, don't block on failure
    }
  }, [siteKey]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchData]);

  const runCycle = async () => {
    setRunning(true);
    try {
      const res = await api.post(`/api/v1/site-agent/hive/decision-cycle/${siteKey}/run`);
      setLastCycleResult(res.data);
      await fetchData(); // Refresh status after cycle
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setRunning(false);
    }
  };

  // Build urgency data for heatmap
  const urgencyData = hiveStatus?.urgency_vector
    ? Object.entries(hiveStatus.urgency_vector).map(([name, info]) => ({
        name,
        value: typeof info === 'object' ? info.urgency || 0 : info || 0,
        direction: typeof info === 'object' ? info.direction : null,
      }))
    : [];

  // Build radar data
  const radarData = urgencyData.map(d => ({
    trm: d.name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
    urgency: d.value,
  }));

  // Signal summary for bar chart
  const signalSummary = hiveStatus?.signal_summary
    ? Object.entries(hiveStatus.signal_summary).map(([type, count]) => ({
        type: type.replace(/_/g, ' '),
        count,
      }))
    : [];

  return (
    <div className="p-6 space-y-6 max-w-[1600px] mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Activity className="h-7 w-7 text-amber-500" />
            Hive Lifecycle Dashboard
          </h1>
          <p className="text-muted-foreground mt-1">
            TRM colony coordination, signal bus, and decision cycle visualization
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <label className="text-sm">Site:</label>
            <input
              type="text"
              value={siteKey}
              onChange={(e) => setSiteKey(e.target.value)}
              className="px-3 py-1.5 text-sm border rounded-md bg-background w-40"
              placeholder="site_key"
            />
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={autoRefresh ? 'ring-2 ring-green-400' : ''}
          >
            <RefreshCw className={`h-4 w-4 mr-1 ${autoRefresh ? 'animate-spin' : ''}`} />
            {autoRefresh ? 'Live' : 'Auto'}
          </Button>
          <Button variant="outline" size="sm" onClick={fetchData}>
            <RefreshCw className="h-4 w-4 mr-1" /> Refresh
          </Button>
          <Button size="sm" onClick={runCycle} disabled={running}>
            <Play className="h-4 w-4 mr-1" />
            {running ? 'Running...' : 'Run Cycle'}
          </Button>
        </div>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <span className="ml-2">{error}</span>
        </Alert>
      )}

      {/* Summary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          title="Active Signals"
          value={hiveStatus?.signal_bus?.alive || 0}
          subtitle={`of ${hiveStatus?.signal_bus?.capacity || 200} capacity`}
          icon={Signal}
          color="blue"
        />
        <StatCard
          title="Registered TRMs"
          value={hiveStatus?.registered_trms?.length || 0}
          subtitle="of 11 total"
          icon={Brain}
          color="purple"
        />
        <StatCard
          title="Signal Divergence"
          value={(hiveStatus?.signal_divergence || 0).toFixed(3)}
          subtitle={hiveStatus?.signal_divergence > 0.30 ? 'Refresh needed' : 'Within bounds'}
          icon={Gauge}
          color={hiveStatus?.signal_divergence > 0.30 ? 'red' : 'green'}
        />
        <StatCard
          title="Last Cycle"
          value={lastCycleResult ? `${lastCycleResult.total_duration_ms?.toFixed(0)}ms` : '—'}
          subtitle={lastCycleResult ? `${lastCycleResult.total_signals_emitted} signals` : 'No cycle run'}
          icon={Clock}
          color="amber"
        />
      </div>

      {/* Main Tabs */}
      <Tabs defaultValue="urgency">
        <TabsList>
          <TabsTrigger value="urgency">Urgency Heatmap</TabsTrigger>
          <TabsTrigger value="signals">Signal Bus</TabsTrigger>
          <TabsTrigger value="cycle">Decision Cycle</TabsTrigger>
          <TabsTrigger value="directive">tGNN Directive</TabsTrigger>
          <TabsTrigger value="health">Hive Health</TabsTrigger>
          <TabsTrigger value="authorization">Authorization</TabsTrigger>
        </TabsList>

        {/* Urgency Heatmap Tab */}
        <TabsContent value="urgency" className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Heatmap Grid */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Urgency Vector (11 TRM Slots)</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
                  {urgencyData.map(d => (
                    <UrgencyCell key={d.name} name={d.name} value={d.value} direction={d.direction} />
                  ))}
                </div>
                {/* Caste Legend */}
                <div className="mt-4 flex flex-wrap gap-3">
                  {Object.entries(CASTE_COLORS).map(([caste, color]) => (
                    <div key={caste} className="flex items-center gap-1">
                      <div className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
                      <span className="text-xs capitalize">{caste}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Radar Chart */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Urgency Radar</CardTitle>
              </CardHeader>
              <CardContent>
                {radarData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={350}>
                    <RadarChart data={radarData}>
                      <PolarGrid />
                      <PolarAngleAxis dataKey="trm" tick={{ fontSize: 10 }} />
                      <PolarRadiusAxis domain={[0, 1]} />
                      <Radar
                        name="Urgency"
                        dataKey="urgency"
                        stroke="#f59e0b"
                        fill="#f59e0b"
                        fillOpacity={0.3}
                      />
                    </RadarChart>
                  </ResponsiveContainer>
                ) : (
                  <p className="text-muted-foreground text-center py-8">No urgency data</p>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Signal Bus Tab */}
        <TabsContent value="signals" className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Active Signals */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Radio className="h-4 w-4" /> Active Signals
                  <Badge variant="outline" className="ml-auto">
                    {hiveStatus?.active_signals?.length || 0}
                  </Badge>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <SignalList signals={hiveStatus?.active_signals} />
              </CardContent>
            </Card>

            {/* Signal Summary Chart */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Signal Distribution</CardTitle>
              </CardHeader>
              <CardContent>
                {signalSummary.length > 0 ? (
                  <ResponsiveContainer width="100%" height={350}>
                    <BarChart data={signalSummary} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis type="number" />
                      <YAxis dataKey="type" type="category" width={120} tick={{ fontSize: 10 }} />
                      <RechartsTooltip />
                      <Bar dataKey="count" fill="#3b82f6" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <p className="text-muted-foreground text-center py-8">No signals emitted yet</p>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Bus Stats */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Bus Statistics</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                {hiveStatus?.signal_bus && Object.entries(hiveStatus.signal_bus).map(([key, val]) => (
                  <div key={key} className="text-center">
                    <p className="text-sm text-muted-foreground">{key.replace(/_/g, ' ')}</p>
                    <p className="text-xl font-bold">{typeof val === 'number' ? val : String(val)}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Decision Cycle Tab */}
        <TabsContent value="cycle" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <Layers className="h-5 w-5" /> 6-Phase Decision Cycle
              </CardTitle>
            </CardHeader>
            <CardContent>
              <PhaseTimeline
                phases={cycleInfo?.phases || []}
                lastCycleResult={lastCycleResult}
              />
            </CardContent>
          </Card>

          {/* Phase-TRM Assignment */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Phase → TRM Assignment</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {(cycleInfo?.phases || []).map(phase => {
                  const config = PHASE_CONFIG.find(p => p.name === phase.name);
                  const PhaseIcon = config?.icon || Layers;
                  return (
                    <div key={phase.name} className="flex items-center gap-3 p-3 rounded-lg bg-muted/30">
                      <PhaseIcon className="h-5 w-5" style={{ color: config?.color || '#6b7280' }} />
                      <span className="font-medium w-24">{phase.name}</span>
                      <div className="flex flex-wrap gap-1">
                        {(phase.trms || []).map(trm => {
                          const caste = TRM_CASTE_MAP[trm];
                          const isRegistered = hiveStatus?.registered_trms?.includes(trm);
                          return (
                            <Badge
                              key={trm}
                              variant={isRegistered ? 'default' : 'outline'}
                              className="text-[10px]"
                              style={isRegistered ? { backgroundColor: CASTE_COLORS[caste] || '#6b7280' } : {}}
                            >
                              {trm.replace(/_/g, ' ')}
                            </Badge>
                          );
                        })}
                        {(!phase.trms || phase.trms.length === 0) && (
                          <span className="text-xs text-muted-foreground">No TRMs assigned</span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>

          {/* Last Cycle Result */}
          {lastCycleResult && (
            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <CheckCircle className="h-5 w-5 text-green-500" /> Last Cycle Result
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                  <div className="text-center">
                    <p className="text-sm text-muted-foreground">Duration</p>
                    <p className="text-xl font-bold">{lastCycleResult.total_duration_ms?.toFixed(2)}ms</p>
                  </div>
                  <div className="text-center">
                    <p className="text-sm text-muted-foreground">Signals Emitted</p>
                    <p className="text-xl font-bold">{lastCycleResult.total_signals_emitted}</p>
                  </div>
                  <div className="text-center">
                    <p className="text-sm text-muted-foreground">Conflicts</p>
                    <p className="text-xl font-bold">{lastCycleResult.conflicts_detected}</p>
                  </div>
                  <div className="text-center">
                    <p className="text-sm text-muted-foreground">Completed</p>
                    <p className="text-sm font-medium">{lastCycleResult.completed_at || '—'}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* tGNN Directive Tab */}
        <TabsContent value="directive" className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Divergence Gauge */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Gauge className="h-5 w-5" /> Signal Divergence Monitor
                </CardTitle>
              </CardHeader>
              <CardContent>
                <DivergenceGauge score={hiveStatus?.signal_divergence || 0} />
                <p className="text-xs text-muted-foreground mt-3">
                  Measures L1 distance between local hive signal distribution and tGNN exception predictions.
                  When divergence exceeds threshold, a TGNN_REFRESH is triggered via CDC.
                </p>
              </CardContent>
            </Card>

            {/* Directive Status */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Network className="h-5 w-5" /> tGNN Site Directive
                </CardTitle>
              </CardHeader>
              <CardContent>
                {hiveStatus?.directive ? (
                  <div className="space-y-3">
                    <div className="grid grid-cols-2 gap-3">
                      <div className="p-3 rounded-lg bg-muted/30">
                        <p className="text-xs text-muted-foreground">Criticality</p>
                        <p className="text-lg font-bold">{hiveStatus.directive.criticality_score?.toFixed(2)}</p>
                      </div>
                      <div className="p-3 rounded-lg bg-muted/30">
                        <p className="text-xs text-muted-foreground">Bottleneck Risk</p>
                        <p className="text-lg font-bold">{hiveStatus.directive.bottleneck_risk?.toFixed(2)}</p>
                      </div>
                      <div className="p-3 rounded-lg bg-muted/30">
                        <p className="text-xs text-muted-foreground">Safety Stock Multiplier</p>
                        <p className="text-lg font-bold">{hiveStatus.directive.safety_stock_multiplier?.toFixed(2)}</p>
                      </div>
                      <div className="p-3 rounded-lg bg-muted/30">
                        <p className="text-xs text-muted-foreground">Resilience</p>
                        <p className="text-lg font-bold">{hiveStatus.directive.resilience_score?.toFixed(2)}</p>
                      </div>
                    </div>
                    <div className="p-3 rounded-lg bg-muted/30">
                      <p className="text-xs text-muted-foreground">Inter-Hive Signals</p>
                      <p className="text-lg font-bold">{hiveStatus.directive.inter_hive_signal_count || 0}</p>
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-8">
                    <Network className="h-12 w-12 text-muted-foreground mx-auto mb-2" />
                    <p className="text-muted-foreground">No tGNN directive received</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Directive is pushed by the tGNN inter-hive model during network-level optimization
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Hive Health Tab */}
        <TabsContent value="health" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <HeartPulse className="h-5 w-5 text-red-500" /> Colony Health Metrics
              </CardTitle>
            </CardHeader>
            <CardContent>
              {hiveStatus?.hive_health ? (
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
                  {Object.entries(hiveStatus.hive_health).map(([key, val]) => (
                    <div key={key} className="p-3 rounded-lg bg-muted/30">
                      <p className="text-xs text-muted-foreground">{key.replace(/_/g, ' ')}</p>
                      <p className="text-lg font-bold">
                        {typeof val === 'number' ? val.toFixed(3)
                          : typeof val === 'object' ? JSON.stringify(val).slice(0, 40)
                          : String(val)}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-muted-foreground text-center py-8">No health metrics available</p>
              )}
            </CardContent>
          </Card>

          {/* Registered TRMs */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Registered TRMs</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-2">
                {(hiveStatus?.registered_trms || []).map(trm => {
                  const caste = TRM_CASTE_MAP[trm];
                  return (
                    <Badge
                      key={trm}
                      variant="default"
                      className="text-sm py-1 px-3"
                      style={{ backgroundColor: CASTE_COLORS[caste] || '#6b7280' }}
                    >
                      {trm.replace(/_/g, ' ')}
                    </Badge>
                  );
                })}
                {(!hiveStatus?.registered_trms || hiveStatus.registered_trms.length === 0) && (
                  <p className="text-muted-foreground">No TRMs registered. Connect TRMs via SiteAgent.</p>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Authorization Tab */}
        <TabsContent value="authorization" className="space-y-4">
          {/* Stats Summary */}
          {authStats && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatCard title="Active Threads" value={authStats.active_threads || 0} icon={Clock} color="blue" />
              <StatCard title="Resolved" value={authStats.resolved_threads || 0} icon={CheckCircle} color="green" />
              <StatCard title="Auto-Resolved" value={authStats.auto_resolved || 0} icon={Zap} color="amber" />
              <StatCard title="Escalated" value={authStats.escalated || 0} icon={AlertTriangle} color="red" />
            </div>
          )}

          {/* Thread List */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <Shield className="h-5 w-5" /> Authorization Threads
                <Badge variant="outline" className="ml-auto">{authThreads.length}</Badge>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {authThreads.length > 0 ? (
                <div className="space-y-3">
                  {authThreads.map((thread) => {
                    const statusColor = thread.status === 'ACCEPTED' ? '#10b981'
                      : thread.status === 'DENIED' ? '#ef4444'
                      : thread.status === 'ESCALATED' ? '#8b5cf6'
                      : thread.status === 'COUNTER_OFFERED' ? '#f59e0b'
                      : '#3b82f6';

                    return (
                      <div
                        key={thread.thread_id}
                        className="flex items-center gap-3 p-3 rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors"
                      >
                        <div
                          className="w-2 h-10 rounded-full flex-shrink-0"
                          style={{ backgroundColor: statusColor }}
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium">
                              {thread.requesting_agent}
                            </span>
                            <ArrowRight className="h-3 w-3 text-muted-foreground" />
                            <span className="text-sm font-medium">
                              {thread.target_agent}
                            </span>
                            <Badge variant="outline" className="text-[10px]" style={{ borderColor: statusColor, color: statusColor }}>
                              {thread.status}
                            </Badge>
                          </div>
                          <div className="text-xs text-muted-foreground mt-0.5">
                            {thread.site_key && `Site: ${thread.site_key} · `}
                            Priority: {thread.priority}
                            {thread.net_benefit != null && ` · Net Benefit: ${thread.net_benefit.toFixed(4)}`}
                          </div>
                        </div>
                        <div className="text-right text-xs text-muted-foreground">
                          {thread.resolution_source && (
                            <Badge variant="outline" className="text-[10px]">
                              {thread.resolution_source}
                            </Badge>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-muted-foreground text-center py-8">
                  No authorization threads. Threads are created when TRM actions cross authority boundaries.
                </p>
              )}
            </CardContent>
          </Card>

          {/* Link to full Authorization Board */}
          <Card>
            <CardContent className="p-4">
              <Link to="/admin/authorization-protocol" className="text-sm text-blue-600 hover:underline flex items-center gap-2">
                <Shield className="h-4 w-4" />
                Open full Authorization Protocol Board for detailed thread management
                <ArrowRight className="h-3 w-3" />
              </Link>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default HiveDashboard;
