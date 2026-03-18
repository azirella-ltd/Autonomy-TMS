/**
 * Adaptive Decision Hierarchy Dashboard
 *
 * Full visualization of the Sequential Decision Analytics and Modeling (SDAM) framework.
 * Shows the complete workflow: State → Policy → Decision → Outcome
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
  Alert,
  Badge,
  Button,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  ToggleGroup,
  ToggleGroupItem,
} from '../../components/common';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip as RechartsTooltip, Legend, ResponsiveContainer,
} from 'recharts';
import {
  Brain,
  Activity,
  Database,
  TrendingUp,
  AlertTriangle,
  CheckCircle,
  Clock,
  Layers,
  Target,
  RefreshCw,
  ChevronRight,
  Package,
  Truck,
  Factory,
  BarChart3,
  Settings,
  Play,
  Gauge,
  Sparkles,
  ShieldCheck,
  Info,
} from 'lucide-react';
import { api } from '../../services/api';

// ============================================================================
// Sub-Components
// ============================================================================

const StatCard = ({ title, value, subtitle, icon: Icon, trend, color = 'blue' }) => (
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
      {trend && (
        <div className="mt-2 flex items-center text-xs">
          <TrendingUp className={`h-3 w-3 mr-1 ${trend > 0 ? 'text-green-500' : 'text-red-500'}`} />
          <span className={trend > 0 ? 'text-green-500' : 'text-red-500'}>
            {trend > 0 ? '+' : ''}{trend}%
          </span>
          <span className="text-muted-foreground ml-1">vs last period</span>
        </div>
      )}
    </CardContent>
  </Card>
);

const PolicyCard = ({ name, type, description, active, onSelect }) => (
  <Card
    className={`cursor-pointer transition-all ${active ? 'ring-2 ring-primary' : 'hover:border-primary/50'}`}
    onClick={onSelect}
  >
    <CardContent className="p-4">
      <div className="flex items-center justify-between mb-2">
        <Badge variant={active ? 'default' : 'outline'}>{type}</Badge>
        {active && <CheckCircle className="h-4 w-4 text-green-500" />}
      </div>
      <h4 className="font-semibold">{name}</h4>
      <p className="text-sm text-muted-foreground mt-1">{description}</p>
    </CardContent>
  </Card>
);

const CDCThresholdBar = ({ label, current, threshold, unit = '%' }) => {
  const ratio = (current / threshold) * 100;
  const isExceeded = current > threshold;

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm">
        <span>{label}</span>
        <span className={isExceeded ? 'text-red-500 font-medium' : ''}>
          {current.toFixed(1)}{unit} / {threshold}{unit}
        </span>
      </div>
      <div className="h-2 bg-muted rounded-full overflow-hidden">
        <div
          className={`h-full transition-all ${isExceeded ? 'bg-red-500' : 'bg-green-500'}`}
          style={{ width: `${Math.min(ratio, 100)}%` }}
        />
      </div>
    </div>
  );
};

const DecisionCard = ({ decision, index }) => (
  <div className="flex items-start gap-3 p-3 border rounded-lg">
    <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-sm font-medium">
      {index + 1}
    </div>
    <div className="flex-1 min-w-0">
      <div className="flex items-center gap-2">
        <span className="font-medium">{decision.type}</span>
        <Badge variant={decision.source === 'trm_adjusted' ? 'default' : 'outline'} className="text-xs">
          {decision.source}
        </Badge>
      </div>
      <p className="text-sm text-muted-foreground truncate">{decision.description}</p>
      <div className="flex items-center gap-4 mt-1 text-xs text-muted-foreground">
        <span>Confidence: {(decision.confidence * 100).toFixed(0)}%</span>
        <span>{decision.timestamp}</span>
      </div>
    </div>
  </div>
);

// ============================================================================
// Main Dashboard Component
// ============================================================================

const PowellDashboard = () => {
  const [currentTab, setCurrentTab] = useState('overview');
  const [selectedSite, setSelectedSite] = useState('DC001');
  const [pipelineViewMode, setPipelineViewMode] = useState('value');
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState(null);
  const [cdcStatus, setCdcStatus] = useState(null);
  const [adjustments, setAdjustments] = useState(null);
  const [recentDecisions, setRecentDecisions] = useState([]);
  const [activePolicy, setActivePolicy] = useState('vfa');

  // Retraining state
  const [retrainingStatus, setRetrainingStatus] = useState(null);
  const [retraining, setRetraining] = useState(false);

  // Conformal prediction state
  const [conformalStatus, setConformalStatus] = useState(null);
  const [sopHistory, setSopHistory] = useState([]);
  const [learningProgress, setLearningProgress] = useState(null);
  const [calibrating, setCalibrating] = useState(false);

  // Override effectiveness state
  const [overrideData, setOverrideData] = useState(null);
  const [posteriorData, setPosteriorData] = useState(null);
  const [overrideLoading, setOverrideLoading] = useState(true);

  // Fetch data
  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [statusRes, cdcRes, adjRes, retrainRes] = await Promise.all([
        api.get(`/site-agent/status/${selectedSite}`).catch(() => ({ data: null })),
        api.get(`/site-agent/cdc/status/${selectedSite}`).catch(() => ({ data: null })),
        api.get(`/site-agent/inventory/adjustments/${selectedSite}`).catch(() => ({ data: null })),
        api.get(`/site-agent/retraining/status/${selectedSite}`).catch(() => ({ data: null })),
      ]);

      setStatus(statusRes.data);
      setCdcStatus(cdcRes.data);
      setAdjustments(adjRes.data);
      setRetrainingStatus(retrainRes.data);

      // Build recent decisions from CDC trigger history
      const triggers = cdcRes.data?.recent_triggers || [];
      const decisionsFromTriggers = triggers.slice(0, 3).map((t) => ({
        type: t.triggered ? 'CDC Trigger' : 'CDC Check',
        source: t.triggered ? 'triggered' : 'deterministic',
        description: t.triggered
          ? `${t.recommended_action}: ${(t.reasons || []).join(', ')}`
          : 'No threshold breaches detected',
        confidence: t.triggered ? 0.0 : 1.0,
        timestamp: t.timestamp || '',
      }));
      setRecentDecisions(decisionsFromTriggers.length > 0 ? decisionsFromTriggers : [
        { type: 'CDC Check', source: 'deterministic', description: 'No threshold breaches detected', confidence: 1.0, timestamp: 'N/A' },
      ]);
    } catch (err) {
      console.error('Failed to load Powell data:', err);
    } finally {
      setLoading(false);
    }
  }, [selectedSite]);

  const handleTriggerRetraining = async () => {
    setRetraining(true);
    try {
      const res = await api.post(`/site-agent/retraining/trigger/${selectedSite}`);
      if (res.data?.status === 'started') {
        alert('Retraining started in background');
      } else {
        alert(res.data?.message || 'Retraining skipped');
      }
      await loadData();
    } catch (err) {
      console.error('Retraining trigger failed:', err);
      alert('Failed to trigger retraining');
    } finally {
      setRetraining(false);
    }
  };

  // Fetch conformal prediction data
  const loadConformalData = useCallback(async () => {
    try {
      const [suiteRes, historyRes, progressRes] = await Promise.all([
        api.get('/conformal-prediction/suite/status').catch(() => ({ data: null })),
        api.get('/conformal-prediction/sop/history').catch(() => ({ data: { cycles: [] } })),
        api.get('/conformal-prediction/sop/learning-progress').catch(() => ({ data: null })),
      ]);

      setConformalStatus(suiteRes.data || {
        summary: {
          demand_predictors: 0,
          lead_time_predictors: 0,
          yield_predictors: 0,
          demand_coverage_target: 0.90,
          lead_time_coverage_target: 0.85,
        },
        joint_coverage_guarantee: 0,
        stale_predictors: [],
      });
      setSopHistory(historyRes.data?.cycles || []);
      setLearningProgress(progressRes.data);
    } catch (err) {
      console.error('Failed to load conformal data:', err);
    }
  }, []);

  const handleCalibrateDemo = async () => {
    setCalibrating(true);
    try {
      await api.post('/conformal-prediction/demo/calibrate');
      await loadConformalData();
    } catch (err) {
      console.error('Failed to calibrate:', err);
    } finally {
      setCalibrating(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    loadConformalData();
  }, [loadConformalData]);

  // Lazy-load override effectiveness data when the tab is selected
  useEffect(() => {
    if (currentTab !== 'overrides') return;
    let cancelled = false;
    const fetchOverrides = async () => {
      setOverrideLoading(true);
      try {
        const [effRes, postRes] = await Promise.all([
          api.get('/decision-metrics/override-effectiveness').catch(() => ({ data: { success: false } })),
          api.get('/decision-metrics/override-posteriors').catch(() => ({ data: { success: false } })),
        ]);
        if (cancelled) return;
        setOverrideData(effRes.data?.success ? effRes.data.data : null);
        setPosteriorData(postRes.data?.success ? { posteriors: postRes.data.posteriors || [], aggregate: postRes.data.aggregate || {}, tier_map: postRes.data.tier_map || {} } : null);
      } catch (err) {
        console.error('Failed to load override data:', err);
      } finally {
        if (!cancelled) setOverrideLoading(false);
      }
    };
    fetchOverrides();
    return () => { cancelled = true; };
  }, [currentTab]);

  const policyOptions = [
    { id: 'pfa', name: 'Base Stock (PFA)', type: 'PFA', description: 'Direct mapping from state to order quantity using base-stock levels' },
    { id: 'cfa', name: 'Parameterized (CFA)', type: 'CFA', description: 'Optimized parameters (s,S), (r,Q) from S&OP planning model' },
    { id: 'vfa', name: 'AI Agent (VFA)', type: 'VFA', description: 'Learned value function with recursive refinement' },
    { id: 'dla', name: 'MPC Lookahead (DLA)', type: 'DLA', description: 'Model predictive control with network model forecasts' },
  ];

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      {/* Breadcrumbs */}
      <nav className="flex items-center gap-2 text-sm text-muted-foreground mb-4">
        <Link to="/" className="hover:text-foreground">Home</Link>
        <ChevronRight className="h-4 w-4" />
        <Link to="/admin?section=training" className="hover:text-foreground">AI & Agents</Link>
        <ChevronRight className="h-4 w-4" />
        <span className="text-foreground">Adaptive Decision Hierarchy</span>
      </nav>

      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold mb-2">Adaptive Decision Hierarchy</h1>
          <p className="text-muted-foreground">
            Sequential Decision Analytics: State → Policy → Decision → Outcome
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Select value={selectedSite} onValueChange={setSelectedSite}>
            <SelectTrigger className="w-40">
              <SelectValue placeholder="Select site" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="DC001">DC001 (Primary)</SelectItem>
              <SelectItem value="DC002">DC002 (Secondary)</SelectItem>
              <SelectItem value="retailer">Retailer</SelectItem>
              <SelectItem value="wholesaler">Wholesaler</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" onClick={loadData} disabled={loading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Status Banner */}
      {status && (
        <Alert variant={status.model_loaded ? 'success' : 'warning'} className="mb-6">
          <div className="flex items-center gap-3">
            {status.model_loaded ? (
              <CheckCircle className="h-4 w-4" />
            ) : (
              <AlertTriangle className="h-4 w-4" />
            )}
            <span className="font-medium">
              {status.model_loaded ? 'TRM Model Active' : 'TRM Model Not Loaded'}
            </span>
            {status.param_counts && (
              <Badge variant="outline">{status.param_counts.total?.toLocaleString()} params</Badge>
            )}
            <Badge variant="outline">{status.agent_mode}</Badge>
            {cdcStatus?.enabled && (
              <Badge variant="secondary">CDC Monitoring</Badge>
            )}
          </div>
        </Alert>
      )}

      {/* Main Tabs */}
      <Tabs value={currentTab} onValueChange={setCurrentTab}>
        <TabsList className="mb-6">
          <TabsTrigger value="overview" className="flex items-center gap-2">
            <Gauge className="h-4 w-4" />
            Overview
          </TabsTrigger>
          <TabsTrigger value="state" className="flex items-center gap-2">
            <Database className="h-4 w-4" />
            State (Sₜ)
          </TabsTrigger>
          <TabsTrigger value="policy" className="flex items-center gap-2">
            <Brain className="h-4 w-4" />
            Policy (π)
          </TabsTrigger>
          <TabsTrigger value="decisions" className="flex items-center gap-2">
            <Target className="h-4 w-4" />
            Decisions (xₜ)
          </TabsTrigger>
          <TabsTrigger value="cdc" className="flex items-center gap-2">
            <Activity className="h-4 w-4" />
            CDC Monitor
          </TabsTrigger>
          <TabsTrigger value="belief-state" className="flex items-center gap-2">
            <Sparkles className="h-4 w-4" />
            Belief State
          </TabsTrigger>
          <TabsTrigger value="hive" className="flex items-center gap-2">
            <Layers className="h-4 w-4" />
            Hive Signals
          </TabsTrigger>
          <TabsTrigger value="overrides" className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4" />
            Overrides
          </TabsTrigger>
        </TabsList>

        {/* Overview Tab */}
        <TabsContent value="overview">
          <div className="grid grid-cols-4 gap-4 mb-6">
            <StatCard
              title="Model Status"
              value={status?.model_loaded ? 'Active' : 'Inactive'}
              subtitle={status?.param_counts ? `${(status.param_counts.total/1000).toFixed(0)}K params` : 'No model'}
              icon={Brain}
              color={status?.model_loaded ? 'green' : 'yellow'}
            />
            <StatCard
              title="Decisions Today"
              value="127"
              subtitle="85% AI-adjusted"
              icon={Target}
              trend={12}
              color="blue"
            />
            <StatCard
              title="Avg Confidence"
              value="0.78"
              subtitle="Above threshold (0.7)"
              icon={Gauge}
              color="purple"
            />
            <StatCard
              title="CDC Triggers"
              value="2"
              subtitle="Last 24 hours"
              icon={AlertTriangle}
              color="orange"
            />
          </div>

          {/* ADH Pipeline Visualization */}
          <Card className="mb-6">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Layers className="h-5 w-5" />
                SDAM Decision Pipeline
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-between">
                {/* State */}
                <div className="flex-1 text-center p-4 border rounded-lg bg-blue-50 dark:bg-blue-900/20">
                  <Database className="h-8 w-8 mx-auto mb-2 text-blue-600" />
                  <h4 className="font-semibold">State (Sₜ)</h4>
                  <p className="text-xs text-muted-foreground mt-1">
                    Physical + Belief
                  </p>
                  <div className="mt-2 text-sm">
                    <div>Inventory: 1,250</div>
                    <div>Pipeline: 450</div>
                    <div>Backlog: 50</div>
                  </div>
                </div>

                <ChevronRight className="h-8 w-8 text-muted-foreground mx-2" />

                {/* Policy */}
                <div className="flex-1 text-center p-4 border rounded-lg bg-purple-50 dark:bg-purple-900/20">
                  <Brain className="h-8 w-8 mx-auto mb-2 text-purple-600" />
                  <h4 className="font-semibold">Policy (π)</h4>
                  <p className="text-xs text-muted-foreground mt-1">
                    TRM (VFA) Active
                  </p>
                  <div className="mt-2 text-sm">
                    <Badge>448K params</Badge>
                  </div>
                </div>

                <ChevronRight className="h-8 w-8 text-muted-foreground mx-2" />

                {/* Decision */}
                <div className="flex-1 text-center p-4 border rounded-lg bg-green-50 dark:bg-green-900/20">
                  <Target className="h-8 w-8 mx-auto mb-2 text-green-600" />
                  <h4 className="font-semibold">Decision (xₜ)</h4>
                  <p className="text-xs text-muted-foreground mt-1">
                    Order Quantity
                  </p>
                  <div className="mt-2 text-sm">
                    <div className="font-bold text-lg">Order: 85 units</div>
                    <div>Conf: 0.82</div>
                  </div>
                </div>

                <ChevronRight className="h-8 w-8 text-muted-foreground mx-2" />

                {/* Exogenous */}
                <div className="flex-1 text-center p-4 border rounded-lg bg-orange-50 dark:bg-orange-900/20">
                  <Clock className="h-8 w-8 mx-auto mb-2 text-orange-600" />
                  <h4 className="font-semibold">Exogenous (Wₜ₊₁)</h4>
                  <p className="text-xs text-muted-foreground mt-1">
                    Demand Realization
                  </p>
                  <div className="mt-2 text-sm">
                    <div>Actual: 78 units</div>
                    <div>Forecast: 80 units</div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Recent Decisions */}
          <Card>
            <CardHeader>
              <CardTitle>Recent Decisions</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {recentDecisions.map((decision, idx) => (
                  <DecisionCard key={idx} decision={decision} index={idx} />
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* State Tab */}
        <TabsContent value="state">
          <div className="grid grid-cols-2 gap-6">
            {/* Physical State */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Package className="h-5 w-5" />
                  Physical State (Rₜ)
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-3 border rounded-lg">
                    <div className="text-sm text-muted-foreground">On-Hand Inventory</div>
                    <div className="text-2xl font-bold">1,250</div>
                    <div className="text-xs text-muted-foreground">units</div>
                  </div>
                  <div className="p-3 border rounded-lg">
                    <div className="text-sm text-muted-foreground">Pipeline (On-Order)</div>
                    <div className="text-2xl font-bold">450</div>
                    <div className="text-xs text-muted-foreground">arriving in 4 buckets</div>
                  </div>
                  <div className="p-3 border rounded-lg">
                    <div className="text-sm text-muted-foreground">Revenue-at-Risk</div>
                    <div className="text-2xl font-bold text-red-500">$127,400</div>
                    <div className="text-xs text-muted-foreground">in 50 unfulfilled orders</div>
                  </div>
                  <div className="p-3 border rounded-lg">
                    <div className="text-sm text-muted-foreground">Inventory Position</div>
                    <div className="text-2xl font-bold">1,650</div>
                    <div className="text-xs text-muted-foreground">OH + Pipeline - Backlog</div>
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="font-medium">Pipeline & Backlog by Week</h4>
                    <ToggleGroup
                      type="single"
                      value={pipelineViewMode}
                      onValueChange={(v) => v && setPipelineViewMode(v)}
                      size="sm"
                      variant="outline"
                    >
                      <ToggleGroupItem value="value" className="text-xs px-2 h-7">Value</ToggleGroupItem>
                      <ToggleGroupItem value="count" className="text-xs px-2 h-7">Count</ToggleGroupItem>
                    </ToggleGroup>
                  </div>
                  <ResponsiveContainer width="100%" height={160}>
                    <BarChart data={[
                      { week: 'Week 1', pipeline: pipelineViewMode === 'value' ? 293400 : 120, backlog: pipelineViewMode === 'value' ? 48200 : 19 },
                      { week: 'Week 2', pipeline: pipelineViewMode === 'value' ? 366750 : 150, backlog: pipelineViewMode === 'value' ? 39400 : 16 },
                      { week: 'Week 3', pipeline: pipelineViewMode === 'value' ? 244500 : 100, backlog: pipelineViewMode === 'value' ? 27300 : 11 },
                      { week: 'Week 4', pipeline: pipelineViewMode === 'value' ? 195600 : 80,  backlog: pipelineViewMode === 'value' ? 12500 : 4 },
                    ]} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                      <XAxis dataKey="week" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => pipelineViewMode === 'value' ? `$${(v / 1000).toFixed(0)}k` : v} />
                      <RechartsTooltip
                        formatter={(value, name) => [
                          pipelineViewMode === 'value'
                            ? `$${value.toLocaleString()}`
                            : `${value} ${name === 'pipeline' ? 'units' : 'orders'}`,
                          name === 'pipeline' ? 'Pipeline' : 'Backlog'
                        ]}
                      />
                      <Legend
                        formatter={(value) => value === 'pipeline' ? 'Pipeline' : 'Backlog'}
                        wrapperStyle={{ fontSize: 11 }}
                      />
                      <Bar dataKey="pipeline" fill="#3b82f6" radius={[3, 3, 0, 0]} />
                      <Bar dataKey="backlog" fill="#ef4444" radius={[3, 3, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>

            {/* Belief State */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <BarChart3 className="h-5 w-5" />
                  Belief State (Bₜ)
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Demand Forecast */}
                <div className="p-3 border rounded-lg">
                  <div className="flex items-center justify-between mb-1">
                    <div className="text-sm font-medium">Demand Forecast</div>
                    <Badge variant="outline" className="text-xs">Conformal</Badge>
                  </div>
                  <div className="flex items-baseline gap-2">
                    <span className="text-2xl font-bold">80</span>
                    <span className="text-muted-foreground">units/day</span>
                  </div>
                  <div className="text-sm text-muted-foreground mt-1">
                    90% CI: [65, 95] · Coverage: 91%
                  </div>
                  <div className="flex items-end gap-1 h-12 mt-2">
                    {[72, 85, 78, 90, 82, 75, 88, 92, 80, 77, 83, 79].map((val, idx) => (
                      <div
                        key={idx}
                        className="flex-1 bg-blue-500 rounded-t"
                        style={{ height: `${(val / 100) * 100}%` }}
                        title={`Period ${idx + 1}: ${val}`}
                      />
                    ))}
                  </div>
                  <div className="flex justify-between text-xs text-muted-foreground mt-1">
                    <span>-12</span>
                    <span>Current</span>
                  </div>
                </div>

                {/* Lead Time */}
                <div className="p-3 border rounded-lg">
                  <div className="flex items-center justify-between mb-1">
                    <div className="text-sm font-medium">Lead Time</div>
                    <Badge variant="outline" className="text-xs">Conformal</Badge>
                  </div>
                  <div className="flex items-baseline gap-2">
                    <span className="text-2xl font-bold">5.2</span>
                    <span className="text-muted-foreground">days</span>
                  </div>
                  <div className="text-sm text-muted-foreground mt-1">
                    90% CI: [3.8, 7.1] · Coverage: 89% · OTD: 94%
                  </div>
                </div>

                {/* Yield */}
                <div className="p-3 border rounded-lg">
                  <div className="flex items-center justify-between mb-1">
                    <div className="text-sm font-medium">Manufacturing Yield</div>
                    <Badge variant="outline" className="text-xs">Conformal</Badge>
                  </div>
                  <div className="flex items-baseline gap-2">
                    <span className="text-2xl font-bold">94.8%</span>
                  </div>
                  <div className="text-sm text-muted-foreground mt-1">
                    95% CI: [91.2%, 97.6%] · Coverage: 96%
                  </div>
                </div>

                {/* Price & Service Level row */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-3 border rounded-lg">
                    <div className="flex items-center justify-between mb-1">
                      <div className="text-sm font-medium">Unit Price</div>
                      <Badge variant="outline" className="text-xs">Conformal</Badge>
                    </div>
                    <div className="flex items-baseline gap-2">
                      <span className="text-xl font-bold">$24.50</span>
                    </div>
                    <div className="text-xs text-muted-foreground mt-1">
                      90% CI: [$22.80, $26.30]
                    </div>
                  </div>
                  <div className="p-3 border rounded-lg">
                    <div className="flex items-center justify-between mb-1">
                      <div className="text-sm font-medium">Service Level</div>
                      <Badge variant="outline" className="text-xs">Conformal</Badge>
                    </div>
                    <div className="flex items-baseline gap-2">
                      <span className="text-xl font-bold">96.2%</span>
                    </div>
                    <div className="text-xs text-muted-foreground mt-1">
                      90% CI: [93.5%, 98.1%]
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Policy Tab */}
        <TabsContent value="policy">
          <div className="grid grid-cols-2 gap-6">
            {/* Policy Selection */}
            <Card>
              <CardHeader>
                <CardTitle>Four Policy Classes</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-3">
                  {policyOptions.map((policy) => (
                    <PolicyCard
                      key={policy.id}
                      {...policy}
                      active={activePolicy === policy.id}
                      onSelect={() => setActivePolicy(policy.id)}
                    />
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Active Policy Details */}
            <Card>
              <CardHeader>
                <CardTitle>Active Policy: AI Agent (VFA)</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="p-4 border rounded-lg bg-purple-50 dark:bg-purple-900/20">
                  <h4 className="font-medium mb-2">Model Architecture</h4>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <div>Encoder Layers: 2</div>
                    <div>Attention Heads: 4</div>
                    <div>Embedding Dim: 128</div>
                    <div>State Dim: 26</div>
                    <div>Total Params: 448,591</div>
                    <div>Device: CPU</div>
                  </div>
                </div>

                <div>
                  <h4 className="font-medium mb-2">Agent Heads</h4>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between p-2 border rounded">
                      <span>ATP Exception Head</span>
                      <Badge variant="success">Active</Badge>
                    </div>
                    <div className="flex items-center justify-between p-2 border rounded">
                      <span>Inventory Planning Head</span>
                      <Badge variant="success">Active</Badge>
                    </div>
                    <div className="flex items-center justify-between p-2 border rounded">
                      <span>PO Timing Head</span>
                      <Badge variant="success">Active</Badge>
                    </div>
                  </div>
                </div>

                {adjustments && (
                  <div>
                    <h4 className="font-medium mb-2">Current Adjustments</h4>
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <div className="p-2 border rounded">
                        <span className="text-muted-foreground">SS Multiplier:</span>
                        <span className="font-medium ml-2">{adjustments.adjustments?.ss_multiplier?.toFixed(3) || 'N/A'}</span>
                      </div>
                      <div className="p-2 border rounded">
                        <span className="text-muted-foreground">ROP Multiplier:</span>
                        <span className="font-medium ml-2">{adjustments.adjustments?.rop_multiplier?.toFixed(3) || 'N/A'}</span>
                      </div>
                    </div>
                  </div>
                )}

                <Button className="w-full">
                  <Settings className="h-4 w-4 mr-2" />
                  Configure Policy Parameters
                </Button>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Decisions Tab */}
        <TabsContent value="decisions">
          <div className="grid grid-cols-3 gap-6">
            {/* ATP Decisions */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Package className="h-5 w-5" />
                  ATP Decisions
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="p-3 border rounded-lg">
                  <div className="flex justify-between items-center mb-2">
                    <span className="font-medium">Order ORD-1234</span>
                    <Badge variant="success">Fulfilled</Badge>
                  </div>
                  <div className="text-sm text-muted-foreground">
                    Requested: 100 → Promised: 100
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    Source: TRM Adjusted · Conf: 0.85
                  </div>
                </div>
                <div className="p-3 border rounded-lg">
                  <div className="flex justify-between items-center mb-2">
                    <span className="font-medium">Order ORD-1235</span>
                    <Badge variant="warning">Partial</Badge>
                  </div>
                  <div className="text-sm text-muted-foreground">
                    Requested: 150 → Promised: 100
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    Source: Deterministic · Shortage: 50
                  </div>
                </div>
                <Button variant="outline" className="w-full">
                  <Play className="h-4 w-4 mr-2" />
                  Test ATP Check
                </Button>
              </CardContent>
            </Card>

            {/* Replenishment Decisions */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Truck className="h-5 w-5" />
                  Replenishment
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="p-3 border rounded-lg">
                  <div className="flex justify-between items-center mb-2">
                    <span className="font-medium">PO-2024-001</span>
                    <Badge>Recommended</Badge>
                  </div>
                  <div className="text-sm">
                    <div>Quantity: 200 units</div>
                    <div className="text-muted-foreground">
                      Order: Feb 6 → Receive: Feb 11
                    </div>
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    TRM Timing: +2 days · Conf: 0.78
                  </div>
                </div>
                <div className="p-3 border rounded-lg border-orange-500">
                  <div className="flex justify-between items-center mb-2">
                    <span className="font-medium">PO-2024-002</span>
                    <Badge variant="destructive">Expedite</Badge>
                  </div>
                  <div className="text-sm">
                    <div>Quantity: 150 units</div>
                    <div className="text-muted-foreground">
                      Expedite Probability: 85%
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Inventory Adjustments */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Factory className="h-5 w-5" />
                  Inventory Policy
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="p-3 border rounded-lg">
                  <div className="font-medium mb-2">Inventory Buffer Adjustment</div>
                  <div className="flex items-center gap-2">
                    <span className="text-muted-foreground">Base:</span>
                    <span>100 units</span>
                    <ChevronRight className="h-4 w-4" />
                    <span className="font-bold text-green-600">99 units</span>
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    Multiplier: 0.993 · Conf: 0.72
                  </div>
                </div>
                <div className="p-3 border rounded-lg">
                  <div className="font-medium mb-2">Reorder Point</div>
                  <div className="flex items-center gap-2">
                    <span className="text-muted-foreground">Base:</span>
                    <span>150 units</span>
                    <ChevronRight className="h-4 w-4" />
                    <span className="font-bold text-blue-600">151 units</span>
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    Multiplier: 1.005 · Conf: 0.72
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* CDC Monitor Tab */}
        <TabsContent value="cdc">
          <div className="grid grid-cols-2 gap-6 mb-6">
            {/* Threshold Status */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Activity className="h-5 w-5" />
                  CDC Thresholds
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {cdcStatus?.thresholds ? (
                  <>
                    <CDCThresholdBar
                      label="Demand Deviation"
                      current={cdcStatus.thresholds.demand_deviation_current || 0}
                      threshold={cdcStatus.thresholds.demand_deviation || 15}
                    />
                    <CDCThresholdBar
                      label="Inventory Ratio"
                      current={cdcStatus.thresholds.inventory_ratio_current || 100}
                      threshold={cdcStatus.thresholds.inventory_low || 70}
                    />
                    <CDCThresholdBar
                      label="Service Level Gap"
                      current={cdcStatus.thresholds.service_gap_current || 0}
                      threshold={cdcStatus.thresholds.service_level_drop || 5}
                    />
                    <CDCThresholdBar
                      label="Lead Time Increase"
                      current={cdcStatus.thresholds.lead_time_current || 0}
                      threshold={cdcStatus.thresholds.lead_time_increase || 30}
                    />
                    <CDCThresholdBar
                      label="Supplier Reliability Drop"
                      current={cdcStatus.thresholds.supplier_reliability_current || 0}
                      threshold={cdcStatus.thresholds.supplier_reliability_drop || 15}
                    />
                  </>
                ) : (
                  <>
                    <CDCThresholdBar label="Demand Deviation" current={0} threshold={15} />
                    <CDCThresholdBar label="Inventory Ratio" current={100} threshold={70} />
                    <CDCThresholdBar label="Service Level Gap" current={0} threshold={5} />
                    <CDCThresholdBar label="Lead Time Increase" current={0} threshold={30} />
                    <CDCThresholdBar label="Supplier Reliability Drop" current={0} threshold={15} />
                  </>
                )}
              </CardContent>
            </Card>

            {/* CDC Actions */}
            <Card>
              <CardHeader>
                <CardTitle>CDC Actions</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {cdcStatus?.recent_triggers?.some(t => t.triggered) ? (
                  <Alert variant="warning">
                    <AlertTriangle className="h-4 w-4" />
                    <span className="ml-2">
                      {cdcStatus.recent_triggers.filter(t => t.triggered).length} trigger(s) in history
                    </span>
                  </Alert>
                ) : (
                  <Alert variant="success">
                    <CheckCircle className="h-4 w-4" />
                    <span className="ml-2">All thresholds within limits</span>
                  </Alert>
                )}

                <div>
                  <h4 className="font-medium mb-2">Action Types</h4>
                  <div className="space-y-2 text-sm">
                    <div className="flex items-center justify-between p-2 border rounded">
                      <span>FULL_CFA</span>
                      <span className="text-muted-foreground">Full policy re-optimization + retrain</span>
                    </div>
                    <div className="flex items-center justify-between p-2 border rounded">
                      <span>ALLOCATION_ONLY</span>
                      <span className="text-muted-foreground">Rerun allocation model</span>
                    </div>
                    <div className="flex items-center justify-between p-2 border rounded">
                      <span>PARAM_ADJUSTMENT</span>
                      <span className="text-muted-foreground">Light parameter tweak (±10%)</span>
                    </div>
                  </div>
                </div>

                <div className="flex gap-2">
                  <Button variant="outline" className="flex-1" onClick={loadData} disabled={loading}>
                    <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
                    Check Now
                  </Button>
                  <Button variant="destructive" className="flex-1" onClick={handleTriggerRetraining} disabled={retraining}>
                    {retraining ? (
                      <><RefreshCw className="h-4 w-4 mr-2 animate-spin" />Retraining...</>
                    ) : (
                      <><AlertTriangle className="h-4 w-4 mr-2" />Manual Trigger</>
                    )}
                  </Button>
                </div>

                {cdcStatus && (
                  <div className="p-3 border rounded-lg bg-muted/50">
                    <div className="text-sm text-muted-foreground">
                      Cooldown: {cdcStatus.thresholds?.cooldown_hours || 24} hours
                    </div>
                    <div className="text-sm text-muted-foreground">
                      Last Trigger: {cdcStatus.last_trigger ? new Date(cdcStatus.last_trigger).toLocaleString() : 'Never'}
                    </div>
                    <div className="text-sm text-muted-foreground">
                      Last Check: {cdcStatus.last_check ? new Date(cdcStatus.last_check).toLocaleString() : 'Never'}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          <div className="grid grid-cols-2 gap-6">
            {/* Retraining Status */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Brain className="h-5 w-5" />
                  Retraining Status
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {retrainingStatus ? (
                  <>
                    {/* Readiness Indicator */}
                    <div className="flex items-center gap-3">
                      <div className={`w-3 h-3 rounded-full ${
                        retrainingStatus.readiness === 'ready' ? 'bg-green-500' :
                        retrainingStatus.readiness === 'waiting_for_trigger' ? 'bg-yellow-500' :
                        retrainingStatus.readiness === 'collecting' ? 'bg-orange-500' :
                        'bg-red-500'
                      }`} />
                      <span className="font-medium capitalize">
                        {retrainingStatus.readiness?.replace(/_/g, ' ') || 'Unknown'}
                      </span>
                      <Badge variant={retrainingStatus.cooldown_ok ? 'success' : 'secondary'}>
                        {retrainingStatus.cooldown_ok ? 'Cooldown OK' : 'In Cooldown'}
                      </Badge>
                    </div>

                    {/* Experience Counts */}
                    <div className="grid grid-cols-2 gap-3">
                      <div className="p-3 border rounded-lg">
                        <div className="text-sm text-muted-foreground">Pending Experiences</div>
                        <div className="text-2xl font-bold">
                          {retrainingStatus.experiences?.pending_since_checkpoint || 0}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          / {retrainingStatus.experiences?.min_required || 100} required
                        </div>
                        <div className="h-2 bg-muted rounded-full overflow-hidden mt-2">
                          <div
                            className="h-full bg-blue-500 transition-all"
                            style={{
                              width: `${Math.min(
                                ((retrainingStatus.experiences?.pending_since_checkpoint || 0) /
                                  (retrainingStatus.experiences?.min_required || 100)) * 100,
                                100
                              )}%`,
                            }}
                          />
                        </div>
                      </div>
                      <div className="p-3 border rounded-lg">
                        <div className="text-sm text-muted-foreground">Awaiting Outcomes</div>
                        <div className="text-2xl font-bold text-orange-600">
                          {retrainingStatus.experiences?.awaiting_outcomes || 0}
                        </div>
                        <div className="text-xs text-muted-foreground">decisions in feedback horizon</div>
                      </div>
                    </div>

                    {/* Current Checkpoint */}
                    {retrainingStatus.checkpoint ? (
                      <div className="p-3 border rounded-lg">
                        <div className="text-sm font-medium mb-2">Active Checkpoint</div>
                        <div className="grid grid-cols-2 gap-2 text-sm">
                          <div>
                            <span className="text-muted-foreground">Version: </span>
                            <span className="font-mono">{retrainingStatus.checkpoint.model_version}</span>
                          </div>
                          <div>
                            <span className="text-muted-foreground">Loss: </span>
                            <span>{retrainingStatus.checkpoint.training_loss?.toFixed(4) || 'N/A'}</span>
                          </div>
                          <div>
                            <span className="text-muted-foreground">Samples: </span>
                            <span>{retrainingStatus.checkpoint.training_samples?.toLocaleString() || 'N/A'}</span>
                          </div>
                          <div>
                            <span className="text-muted-foreground">Phase: </span>
                            <span>{retrainingStatus.checkpoint.training_phase || 'N/A'}</span>
                          </div>
                        </div>
                        <div className="text-xs text-muted-foreground mt-2">
                          Created: {retrainingStatus.checkpoint.created_at
                            ? new Date(retrainingStatus.checkpoint.created_at).toLocaleString()
                            : 'N/A'}
                        </div>
                      </div>
                    ) : (
                      <div className="p-3 border rounded-lg text-center text-muted-foreground">
                        No checkpoint yet — model using default weights
                      </div>
                    )}

                    {/* Retrain Button */}
                    <Button
                      className="w-full"
                      onClick={handleTriggerRetraining}
                      disabled={retraining || retrainingStatus.readiness === 'not_ready'}
                    >
                      {retraining ? (
                        <><RefreshCw className="h-4 w-4 mr-2 animate-spin" />Retraining...</>
                      ) : (
                        <><Play className="h-4 w-4 mr-2" />Retrain Now</>
                      )}
                    </Button>
                  </>
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    <Brain className="h-12 w-12 mx-auto mb-4 opacity-30" />
                    <p>Retraining status unavailable</p>
                    <p className="text-sm mt-1">Ensure the site agent is configured</p>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Recent Trigger History */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Clock className="h-5 w-5" />
                  Recent Trigger History
                </CardTitle>
              </CardHeader>
              <CardContent>
                {cdcStatus?.recent_triggers?.length > 0 ? (
                  <div className="space-y-3 max-h-[400px] overflow-y-auto">
                    {cdcStatus.recent_triggers.map((t, idx) => (
                      <div
                        key={t.id || idx}
                        className={`p-3 border rounded-lg ${t.triggered ? 'border-orange-300 bg-orange-50 dark:bg-orange-900/10' : ''}`}
                      >
                        <div className="flex items-center justify-between mb-1">
                          <div className="flex items-center gap-2">
                            {t.triggered ? (
                              <AlertTriangle className="h-4 w-4 text-orange-500" />
                            ) : (
                              <CheckCircle className="h-4 w-4 text-green-500" />
                            )}
                            <span className="font-medium text-sm">
                              {t.triggered ? 'Triggered' : 'No Breach'}
                            </span>
                            {t.severity && (
                              <Badge variant={t.severity === 'high' ? 'destructive' : 'secondary'} className="text-xs">
                                {t.severity}
                              </Badge>
                            )}
                          </div>
                          <span className="text-xs text-muted-foreground">
                            {t.timestamp ? new Date(t.timestamp).toLocaleString() : ''}
                          </span>
                        </div>
                        {t.triggered && (
                          <>
                            <div className="text-xs text-muted-foreground">
                              Action: {t.recommended_action} | Reasons: {(t.reasons || []).join(', ')}
                            </div>
                            {t.replan_completed !== null && (
                              <div className="text-xs mt-1">
                                Replan: {t.replan_completed ? 'Completed' : 'Pending'}
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    <Activity className="h-12 w-12 mx-auto mb-4 opacity-30" />
                    <p>No trigger history yet</p>
                    <p className="text-sm mt-1">CDC checks will appear here as they run</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Belief State Tab - Conformal Prediction */}
        <TabsContent value="belief-state">
          <div className="grid grid-cols-2 gap-6">
            {/* Calibration Status */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Sparkles className="h-5 w-5 text-amber-500" />
                  Conformal Prediction Suite
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Coverage Targets */}
                <div className="grid grid-cols-3 gap-3">
                  <div className="p-3 border rounded-lg text-center">
                    <div className="text-2xl font-bold text-blue-600">
                      {conformalStatus?.summary?.demand_predictors || 0}
                    </div>
                    <div className="text-xs text-muted-foreground">Demand Predictors</div>
                  </div>
                  <div className="p-3 border rounded-lg text-center">
                    <div className="text-2xl font-bold text-green-600">
                      {conformalStatus?.summary?.lead_time_predictors || 0}
                    </div>
                    <div className="text-xs text-muted-foreground">Lead Time Predictors</div>
                  </div>
                  <div className="p-3 border rounded-lg text-center">
                    <div className="text-2xl font-bold text-purple-600">
                      {conformalStatus?.summary?.yield_predictors || 0}
                    </div>
                    <div className="text-xs text-muted-foreground">Yield Predictors</div>
                  </div>
                </div>

                {/* Coverage Bars */}
                <div className="space-y-3">
                  <div>
                    <div className="flex justify-between text-sm mb-1">
                      <span>Demand Coverage</span>
                      <span>{((conformalStatus?.summary?.demand_coverage_target || 0.9) * 100).toFixed(0)}% target</span>
                    </div>
                    <div className="h-3 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full bg-blue-500 rounded-full"
                        style={{ width: `${(conformalStatus?.summary?.demand_coverage_target || 0.9) * 100}%` }}
                      />
                    </div>
                  </div>
                  <div>
                    <div className="flex justify-between text-sm mb-1">
                      <span>Lead Time Coverage</span>
                      <span>{((conformalStatus?.summary?.lead_time_coverage_target || 0.85) * 100).toFixed(0)}% target</span>
                    </div>
                    <div className="h-3 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full bg-green-500 rounded-full"
                        style={{ width: `${(conformalStatus?.summary?.lead_time_coverage_target || 0.85) * 100}%` }}
                      />
                    </div>
                  </div>
                </div>

                {/* Joint Coverage */}
                <div className="p-4 bg-amber-50 dark:bg-amber-900/20 rounded-lg">
                  <div className="flex justify-between items-center">
                    <div className="flex items-center gap-2">
                      <ShieldCheck className="h-5 w-5 text-amber-600" />
                      <span className="font-medium">Joint Coverage Guarantee</span>
                    </div>
                    <span className="text-2xl font-bold">
                      {((conformalStatus?.joint_coverage_guarantee || 0) * 100).toFixed(0)}%
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-2">
                    Probability that BOTH demand AND lead time fall within their respective prediction intervals
                  </p>
                </div>

                {/* Stale Predictors Warning */}
                {conformalStatus?.stale_predictors?.length > 0 && (
                  <Alert variant="warning">
                    <AlertTriangle className="h-4 w-4" />
                    <span className="ml-2">
                      {conformalStatus.stale_predictors.length} predictors need recalibration
                    </span>
                  </Alert>
                )}

                {/* Actions */}
                <div className="flex gap-2">
                  <Button
                    onClick={handleCalibrateDemo}
                    disabled={calibrating}
                    className="flex-1"
                  >
                    {calibrating ? (
                      <>
                        <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                        Calibrating...
                      </>
                    ) : (
                      <>
                        <Play className="h-4 w-4 mr-2" />
                        Calibrate History
                      </>
                    )}
                  </Button>
                  <Button variant="outline" onClick={loadConformalData}>
                    <RefreshCw className="h-4 w-4 mr-2" />
                    Refresh
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* S&OP Learning Progress */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <TrendingUp className="h-5 w-5" />
                  S&OP Learning Progress
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {learningProgress ? (
                  <>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="p-3 border rounded-lg">
                        <div className="text-sm text-muted-foreground">Early Cycles (1-5)</div>
                        <div className="text-xl font-bold">
                          {(learningProgress.early_performance?.coverage_hit_rate * 100 || 0).toFixed(0)}%
                        </div>
                        <div className="text-xs text-muted-foreground">Coverage Hit Rate</div>
                      </div>
                      <div className="p-3 border rounded-lg">
                        <div className="text-sm text-muted-foreground">Recent Cycles</div>
                        <div className="text-xl font-bold text-green-600">
                          {(learningProgress.late_performance?.coverage_hit_rate * 100 || 0).toFixed(0)}%
                        </div>
                        <div className="text-xs text-muted-foreground">Coverage Hit Rate</div>
                      </div>
                    </div>

                    <div className="p-4 border rounded-lg">
                      <div className="flex justify-between items-center">
                        <span className="font-medium">Improvement</span>
                        <Badge variant={learningProgress.improvement > 0 ? 'success' : 'secondary'}>
                          {learningProgress.improvement > 0 ? '+' : ''}{(learningProgress.improvement * 100).toFixed(0)}%
                        </Badge>
                      </div>
                      <p className="text-xs text-muted-foreground mt-1">
                        {learningProgress.total_cycles} total cycles analyzed
                      </p>
                    </div>

                    <Alert>
                      <Info className="h-4 w-4" />
                      <span className="ml-2 text-sm">
                        The conformal learning loop improves predictions by comparing forecasts to actuals
                        and recalibrating uncertainty intervals.
                      </span>
                    </Alert>
                  </>
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    <Sparkles className="h-12 w-12 mx-auto mb-4 opacity-30" />
                    <p>No S&OP cycles recorded yet</p>
                    <p className="text-sm mt-1">Run planning cycles to see learning progress</p>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* S&OP Cycle History */}
            <Card className="col-span-2">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Clock className="h-5 w-5" />
                  Recent S&OP Cycles
                </CardTitle>
              </CardHeader>
              <CardContent>
                {sopHistory.length > 0 ? (
                  <div className="space-y-3">
                    {sopHistory.slice(0, 5).map((cycle, idx) => (
                      <div key={idx} className="flex items-center justify-between p-3 border rounded-lg">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-medium">{cycle.planning_date}</span>
                            <Badge variant={cycle.status === 'complete' ? 'success' : 'secondary'}>
                              {cycle.status}
                            </Badge>
                          </div>
                          <div className="text-sm text-muted-foreground">
                            {cycle.n_scenarios_generated} scenarios → {cycle.n_scenarios_reduced} reduced
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="font-medium">
                            Coverage: {((cycle.coverage_guarantee || 0) * 100).toFixed(0)}%
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {cycle.solve_time_seconds?.toFixed(1)}s solve time
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    <Database className="h-12 w-12 mx-auto mb-4 opacity-30" />
                    <p>No S&OP cycles recorded yet</p>
                    <p className="text-sm mt-1">Use the S&OP endpoints to run planning cycles</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Hive Signals Tab */}
        <TabsContent value="hive">
          <HiveSignalsTab siteKey={selectedSite} />
        </TabsContent>

        {/* Override Effectiveness Tab */}
        <TabsContent value="overrides">
          {overrideLoading ? (
            <div className="text-center py-12 text-muted-foreground">Loading override effectiveness data...</div>
          ) : !overrideData ? (
            <div className="text-center py-12 text-muted-foreground">
              <ShieldCheck className="h-12 w-12 mx-auto mb-4 opacity-30" />
              <p className="text-lg font-medium">No Override Data Available</p>
              <p className="text-sm mt-1">Override effectiveness tracking will appear once human overrides are recorded.</p>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Row 1: Summary StatCards */}
              <div className="grid grid-cols-4 gap-4">
                <StatCard
                  title="Effectiveness Rate"
                  value={`${((overrideData.effectiveness_rate || 0) * 100).toFixed(1)}%`}
                  subtitle="% of overrides that improved outcomes"
                  icon={ShieldCheck}
                  color={(overrideData.effectiveness_rate || 0) >= 0.6 ? 'green' : (overrideData.effectiveness_rate || 0) >= 0.4 ? 'yellow' : 'red'}
                />
                <StatCard
                  title="Net Reward Delta"
                  value={((overrideData.net_reward_delta || 0) >= 0 ? '+' : '') + (overrideData.net_reward_delta || 0).toFixed(2)}
                  subtitle="Cumulative reward impact of overrides"
                  icon={TrendingUp}
                  color={(overrideData.net_reward_delta || 0) >= 0 ? 'green' : 'red'}
                />
                <StatCard
                  title="Total Overrides"
                  value={overrideData.total_overrides || 0}
                  subtitle={`${overrideData.beneficial_count || 0} beneficial / ${overrideData.neutral_count || 0} neutral / ${overrideData.detrimental_count || 0} detrimental`}
                  icon={Target}
                  color="blue"
                />
                <StatCard
                  title="Bayesian Confidence"
                  value={posteriorData?.aggregate?.avg_effectiveness != null
                    ? `${(posteriorData.aggregate.avg_effectiveness * 100).toFixed(1)}%`
                    : 'N/A'}
                  subtitle={posteriorData?.aggregate?.ci_lower != null && posteriorData?.aggregate?.ci_upper != null
                    ? `90% CI: ${(posteriorData.aggregate.ci_lower * 100).toFixed(1)}% - ${(posteriorData.aggregate.ci_upper * 100).toFixed(1)}%`
                    : 'No credible interval data'}
                  icon={Sparkles}
                  color="purple"
                />
              </div>

              {/* Row 2: By TRM Type Table */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Brain className="h-5 w-5 text-blue-500" />
                    Override Effectiveness by TRM Type
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {overrideData.by_trm_type && Object.keys(overrideData.by_trm_type).length > 0 ? (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b">
                            <th className="text-left py-2 px-3 font-medium">Agent Type</th>
                            <th className="text-center py-2 px-3 font-medium">Tier</th>
                            <th className="text-right py-2 px-3 font-medium">Overrides</th>
                            <th className="text-right py-2 px-3 font-medium">Beneficial</th>
                            <th className="text-right py-2 px-3 font-medium">Detrimental</th>
                            <th className="text-right py-2 px-3 font-medium">Effectiveness %</th>
                            <th className="text-right py-2 px-3 font-medium">Net Delta</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(overrideData.by_trm_type).map(([trmType, stats]) => {
                            const tier = posteriorData?.tier_map?.[trmType] || null;
                            const tierColors = { 1: 'bg-green-100 text-green-800', 2: 'bg-yellow-100 text-yellow-800', 3: 'bg-orange-100 text-orange-800' };
                            return (
                              <tr key={trmType} className="border-b hover:bg-muted/50">
                                <td className="py-2 px-3 font-medium">{trmType.replace(/_/g, ' ')}</td>
                                <td className="py-2 px-3 text-center">
                                  {tier ? (
                                    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${tierColors[tier] || 'bg-gray-100 text-gray-800'}`}>
                                      Tier {tier}
                                    </span>
                                  ) : (
                                    <span className="text-muted-foreground">-</span>
                                  )}
                                </td>
                                <td className="py-2 px-3 text-right">{stats.total || 0}</td>
                                <td className="py-2 px-3 text-right text-green-600">{stats.beneficial || 0}</td>
                                <td className="py-2 px-3 text-right text-red-600">{stats.detrimental || 0}</td>
                                <td className="py-2 px-3 text-right">
                                  <span className={
                                    (stats.effectiveness || 0) >= 0.6 ? 'text-green-600 font-medium'
                                    : (stats.effectiveness || 0) >= 0.4 ? 'text-yellow-600 font-medium'
                                    : 'text-red-600 font-medium'
                                  }>
                                    {((stats.effectiveness || 0) * 100).toFixed(1)}%
                                  </span>
                                </td>
                                <td className="py-2 px-3 text-right">
                                  <span className={(stats.net_delta || 0) >= 0 ? 'text-green-600' : 'text-red-600'}>
                                    {(stats.net_delta || 0) >= 0 ? '+' : ''}{(stats.net_delta || 0).toFixed(2)}
                                  </span>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="text-center py-6 text-muted-foreground">No per-agent override data available</div>
                  )}
                </CardContent>
              </Card>

              {/* Row 3: Trend Chart */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <BarChart3 className="h-5 w-5 text-purple-500" />
                    Override Trend by Week
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {overrideData.trend && overrideData.trend.length > 0 ? (
                    <ResponsiveContainer width="100%" height={300}>
                      <BarChart data={overrideData.trend}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="week" />
                        <YAxis />
                        <RechartsTooltip />
                        <Legend />
                        <Bar dataKey="beneficial" stackId="a" fill="#22c55e" name="Beneficial" />
                        <Bar dataKey="neutral" stackId="a" fill="#9ca3af" name="Neutral" />
                        <Bar dataKey="detrimental" stackId="a" fill="#ef4444" name="Detrimental" />
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="text-center py-8 text-muted-foreground">
                      No trend data available yet
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Row 4: Top Beneficial / Top Detrimental */}
              <div className="grid grid-cols-2 gap-6">
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <CheckCircle className="h-5 w-5 text-green-500" />
                      Top Beneficial Overrides
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    {overrideData.top_beneficial && overrideData.top_beneficial.length > 0 ? (
                      <div className="space-y-3">
                        {overrideData.top_beneficial.map((item, idx) => (
                          <div key={idx} className="flex items-start gap-3 p-3 border rounded-lg">
                            <div className="flex-shrink-0 w-6 h-6 rounded-full bg-green-100 flex items-center justify-center text-xs font-medium text-green-700">
                              {idx + 1}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="font-medium text-sm">{(item.decision_type || '').replace(/_/g, ' ')}</span>
                                <Badge variant="outline" className="text-xs">{item.site_key || '-'}</Badge>
                              </div>
                              <p className="text-xs text-muted-foreground mt-1 truncate">{item.override_reason || 'No reason provided'}</p>
                              <div className="mt-1">
                                <span className="text-xs text-green-600 font-medium">
                                  Delta: +{(item.override_delta || 0).toFixed(3)}
                                </span>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="text-center py-6 text-muted-foreground text-sm">No beneficial overrides recorded</div>
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <AlertTriangle className="h-5 w-5 text-red-500" />
                      Top Detrimental Overrides
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    {overrideData.top_detrimental && overrideData.top_detrimental.length > 0 ? (
                      <div className="space-y-3">
                        {overrideData.top_detrimental.map((item, idx) => (
                          <div key={idx} className="flex items-start gap-3 p-3 border rounded-lg">
                            <div className="flex-shrink-0 w-6 h-6 rounded-full bg-red-100 flex items-center justify-center text-xs font-medium text-red-700">
                              {idx + 1}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="font-medium text-sm">{(item.decision_type || '').replace(/_/g, ' ')}</span>
                                <Badge variant="outline" className="text-xs">{item.site_key || '-'}</Badge>
                              </div>
                              <p className="text-xs text-muted-foreground mt-1 truncate">{item.override_reason || 'No reason provided'}</p>
                              <div className="mt-1">
                                <span className="text-xs text-red-600 font-medium">
                                  Delta: {(item.override_delta || 0).toFixed(3)}
                                </span>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="text-center py-6 text-muted-foreground text-sm">No detrimental overrides recorded</div>
                    )}
                  </CardContent>
                </Card>
              </div>

              {/* Row 5: Bayesian Posteriors Table */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Sparkles className="h-5 w-5 text-purple-500" />
                    Bayesian Override Posteriors
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {posteriorData?.posteriors && posteriorData.posteriors.length > 0 ? (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b">
                            <th className="text-left py-2 px-3 font-medium">User</th>
                            <th className="text-left py-2 px-3 font-medium">Agent Type</th>
                            <th className="text-center py-2 px-3 font-medium">Tier</th>
                            <th className="text-right py-2 px-3 font-medium">Observations</th>
                            <th className="text-right py-2 px-3 font-medium">E[Effectiveness]</th>
                            <th className="text-right py-2 px-3 font-medium">Training Weight</th>
                            <th className="text-right py-2 px-3 font-medium">90% CI</th>
                          </tr>
                        </thead>
                        <tbody>
                          {posteriorData.posteriors.map((row, idx) => {
                            const tier = row.tier || posteriorData.tier_map?.[row.trm_type] || null;
                            const tierColors = { 1: 'bg-green-100 text-green-800', 2: 'bg-yellow-100 text-yellow-800', 3: 'bg-orange-100 text-orange-800' };
                            return (
                              <tr key={idx} className="border-b hover:bg-muted/50">
                                <td className="py-2 px-3">{row.user || row.user_id || '-'}</td>
                                <td className="py-2 px-3">{(row.trm_type || '').replace(/_/g, ' ')}</td>
                                <td className="py-2 px-3 text-center">
                                  {tier ? (
                                    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${tierColors[tier] || 'bg-gray-100 text-gray-800'}`}>
                                      Tier {tier}
                                    </span>
                                  ) : (
                                    <span className="text-muted-foreground">-</span>
                                  )}
                                </td>
                                <td className="py-2 px-3 text-right">{row.observations || 0}</td>
                                <td className="py-2 px-3 text-right font-medium">
                                  {row.expected_effectiveness != null
                                    ? `${(row.expected_effectiveness * 100).toFixed(1)}%`
                                    : '-'}
                                </td>
                                <td className="py-2 px-3 text-right">
                                  {row.training_weight != null
                                    ? row.training_weight.toFixed(3)
                                    : '-'}
                                </td>
                                <td className="py-2 px-3 text-right text-muted-foreground">
                                  {row.ci_lower != null && row.ci_upper != null
                                    ? `${(row.ci_lower * 100).toFixed(1)}% - ${(row.ci_upper * 100).toFixed(1)}%`
                                    : '-'}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="text-center py-8 text-muted-foreground">
                      <Info className="h-8 w-8 mx-auto mb-3 opacity-30" />
                      <p>No Bayesian posteriors yet — overrides will be tracked as they occur</p>
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
};

/**
 * Embedded Hive Signals tab for the Powell Dashboard.
 * Shows signal bus stats, urgency vector summary, and directive status.
 */
const HiveSignalsTab = ({ siteKey }) => {
  const [hiveStatus, setHiveStatus] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);
  const effectiveSiteKey = siteKey || 'default_site';

  React.useEffect(() => {
    const fetchHive = async () => {
      try {
        setError(null);
        const res = await api.get(`/api/v1/site-agent/hive/status/${effectiveSiteKey}`);
        setHiveStatus(res.data);
      } catch (err) {
        setError(err.response?.data?.detail || err.message);
      } finally {
        setLoading(false);
      }
    };
    fetchHive();
  }, [effectiveSiteKey]);

  if (loading) return <div className="text-center py-8 text-muted-foreground">Loading hive status...</div>;
  if (error) return <Alert variant="destructive"><AlertTriangle className="h-4 w-4" /><span className="ml-2">{error}</span></Alert>;

  const urgencyEntries = hiveStatus?.urgency_vector
    ? Object.entries(hiveStatus.urgency_vector).map(([name, info]) => ({
        name: name.replace(/_/g, ' '),
        value: typeof info === 'object' ? info.urgency || 0 : info || 0,
        direction: typeof info === 'object' ? info.direction : null,
      }))
    : [];

  return (
    <div className="grid grid-cols-2 gap-6">
      {/* Signal Bus Stats */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5 text-blue-500" />
            Signal Bus Status
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-3 mb-4">
            <div className="p-3 border rounded-lg text-center">
              <div className="text-2xl font-bold text-blue-600">
                {hiveStatus?.signal_bus?.alive || 0}
              </div>
              <div className="text-xs text-muted-foreground">Active Signals</div>
            </div>
            <div className="p-3 border rounded-lg text-center">
              <div className="text-2xl font-bold text-green-600">
                {hiveStatus?.registered_trms?.length || 0}
              </div>
              <div className="text-xs text-muted-foreground">Registered TRMs</div>
            </div>
            <div className="p-3 border rounded-lg text-center">
              <div className="text-2xl font-bold" style={{ color: (hiveStatus?.signal_divergence || 0) > 0.3 ? '#ef4444' : '#10b981' }}>
                {(hiveStatus?.signal_divergence || 0).toFixed(3)}
              </div>
              <div className="text-xs text-muted-foreground">Divergence Score</div>
            </div>
          </div>

          {/* Signal Summary */}
          {hiveStatus?.signal_summary && Object.keys(hiveStatus.signal_summary).length > 0 && (
            <div className="space-y-2">
              <h4 className="text-sm font-medium">Signal Types</h4>
              {Object.entries(hiveStatus.signal_summary).map(([type, count]) => (
                <div key={type} className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">{type.replace(/_/g, ' ')}</span>
                  <Badge variant="outline">{count}</Badge>
                </div>
              ))}
            </div>
          )}

          <div className="mt-4">
            <Link to="/admin/hive" className="text-sm text-primary hover:underline flex items-center gap-1">
              Open Full Hive Dashboard <ChevronRight className="h-3 w-3" />
            </Link>
          </div>
        </CardContent>
      </Card>

      {/* Urgency Vector */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Gauge className="h-5 w-5 text-amber-500" />
            Urgency Vector
          </CardTitle>
        </CardHeader>
        <CardContent>
          {urgencyEntries.length > 0 ? (
            <div className="space-y-2">
              {urgencyEntries.map(d => (
                <div key={d.name} className="flex items-center gap-2">
                  <span className="text-xs w-28 truncate capitalize">{d.name}</span>
                  <div className="flex-1 h-3 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{
                        width: `${d.value * 100}%`,
                        backgroundColor: d.value > 0.7 ? '#ef4444' : d.value > 0.3 ? '#f59e0b' : '#10b981',
                      }}
                    />
                  </div>
                  <span className="text-xs w-10 text-right">{d.value.toFixed(2)}</span>
                  {d.direction && (
                    <span className="text-[10px] text-muted-foreground w-16">
                      {d.direction === 'shortage' ? '▼' : d.direction === 'surplus' ? '▲' : '●'} {d.direction}
                    </span>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <Layers className="h-12 w-12 mx-auto mb-4 opacity-30" />
              <p>No urgency data</p>
              <p className="text-sm mt-1">Connect TRMs to the SiteAgent to see urgency values</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* tGNN Directive Status */}
      <Card className="col-span-2">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5" />
            Network Agent Site Directive
          </CardTitle>
        </CardHeader>
        <CardContent>
          {hiveStatus?.directive ? (
            <div className="grid grid-cols-5 gap-4">
              <div className="p-3 border rounded-lg text-center">
                <div className="text-lg font-bold">{hiveStatus.directive.criticality_score?.toFixed(2)}</div>
                <div className="text-xs text-muted-foreground">Criticality</div>
              </div>
              <div className="p-3 border rounded-lg text-center">
                <div className="text-lg font-bold">{hiveStatus.directive.bottleneck_risk?.toFixed(2)}</div>
                <div className="text-xs text-muted-foreground">Bottleneck Risk</div>
              </div>
              <div className="p-3 border rounded-lg text-center">
                <div className="text-lg font-bold">{hiveStatus.directive.safety_stock_multiplier?.toFixed(2)}</div>
                <div className="text-xs text-muted-foreground">SS Multiplier</div>
              </div>
              <div className="p-3 border rounded-lg text-center">
                <div className="text-lg font-bold">{hiveStatus.directive.resilience_score?.toFixed(2)}</div>
                <div className="text-xs text-muted-foreground">Resilience</div>
              </div>
              <div className="p-3 border rounded-lg text-center">
                <div className="text-lg font-bold">{hiveStatus.directive.inter_hive_signal_count || 0}</div>
                <div className="text-xs text-muted-foreground">Inter-Hive Signals</div>
              </div>
            </div>
          ) : (
            <div className="text-center py-6 text-muted-foreground">
              No network agent directive active — waiting for network-level optimization
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default PowellDashboard;
