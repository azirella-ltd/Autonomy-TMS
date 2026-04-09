/**
 * Governance Dashboard — Decision Pipeline Inspection & Configuration
 *
 * Allows tenant admins and super users to:
 * - View the full governance pipeline (planning envelope → scoring → mode → guardrails)
 * - Adjust AIIO thresholds per action type and per site
 * - Set impact scoring dimension weights
 * - Create/manage guardrail directives
 * - Simulate how decisions would be gated
 * - View audit trail
 *
 * Controls are per-site (since agents are site-specific) with an
 * "Apply to all sites" option.
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, CardContent, Button, Badge, Alert, Modal,
  Tabs, TabsList, TabsTrigger, TabsContent,
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
  Input,
} from '../../components/common';
import {
  Shield, History, FileText, Scale, RefreshCw, Download, Eye,
  AlertTriangle, CheckCircle, Settings, Play, Plus, Trash2, Save,
  Sliders, ChevronDown, ChevronUp, Copy,
} from 'lucide-react';
import { api } from '../../services/api';
import { cn } from '../../lib/utils/cn';
import { useAuth } from '../../contexts/AuthContext';

// TMS Agent function names — grouped by decision cycle phase
// SENSE → ASSESS → ACQUIRE → PROTECT → BUILD → REFLECT
const AGENT_LABELS = {
  // SENSE phase
  capacity_promise: 'Capacity Promise Agent',
  shipment_tracking: 'Shipment Tracking Agent',
  demand_sensing: 'Demand Sensing Agent',
  // ASSESS phase
  capacity_buffer: 'Capacity Buffer Agent',
  exception_management: 'Exception Mgmt Agent',
  // ACQUIRE phase
  freight_procurement: 'Freight Procurement Agent',
  broker_routing: 'Broker Routing Agent',
  // PROTECT phase
  dock_scheduling: 'Dock Scheduling Agent',
  // BUILD phase
  load_build: 'Load Build Agent',
  intermodal_transfer: 'Intermodal Transfer Agent',
  // REFLECT phase
  equipment_reposition: 'Equipment Reposition Agent',
  // Legacy SC types (kept for backward compatibility with existing data)
  po_creation: 'Procurement Agent',
  mo_execution: 'Production Agent',
  to_execution: 'Transfer Agent',
  rebalancing: 'Rebalancing Agent',
  atp_executor: 'Order Promise Agent',
  quality_disposition: 'Quality Agent',
  maintenance_scheduling: 'Maintenance Agent',
  subcontracting: 'Subcontracting Agent',
  forecast_adjustment: 'Demand Agent',
  inventory_buffer: 'Inventory Agent',
  order_tracking: 'Order Tracking Agent',
};

const MODE_COLORS = {
  AUTOMATE: 'bg-green-100 text-green-700',
  INFORM: 'bg-blue-100 text-blue-700',
  INSPECT: 'bg-orange-100 text-orange-700',
};

const Governance = () => {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState('pipeline');
  const [pipeline, setPipeline] = useState(null);
  const [policies, setPolicies] = useState([]);
  const [directives, setDirectives] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [decisions, setDecisions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [editingPolicy, setEditingPolicy] = useState(null);
  const [simResult, setSimResult] = useState(null);
  const [simForm, setSimForm] = useState({ action_type: 'freight_procurement', estimated_impact: 5000, confidence_level: 0.8 });
  const [newDirective, setNewDirective] = useState(null);
  const [oversightConfig, setOversightConfig] = useState(null);
  const [weekSchedule, setWeekSchedule] = useState([]);
  const [holidays, setHolidays] = useState([]);

  const tenantParam = user?.is_system_admin ? `?tenant_id=${user?.viewing_tenant_id || 3}` : '';

  const loadPipeline = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get(`/v1/governance/pipeline${tenantParam}`);
      setPipeline(res.data);
      setPolicies(res.data.policies || []);
      setDirectives(res.data.active_directives || []);
    } catch (err) {
      console.error('Failed to load pipeline:', err);
    } finally {
      setLoading(false);
    }
  }, [tenantParam]);

  const loadAudit = useCallback(async () => {
    try {
      const res = await api.get(`/v1/governance/audit${tenantParam}&limit=100`);
      setAuditLogs(res.data || []);
    } catch { setAuditLogs([]); }
  }, [tenantParam]);

  const loadDecisions = useCallback(async () => {
    try {
      const res = await api.get(`/v1/governance/decisions${tenantParam}&limit=100`);
      setDecisions(res.data || []);
    } catch { setDecisions([]); }
  }, [tenantParam]);

  useEffect(() => {
    loadPipeline();
  }, [loadPipeline]);

  useEffect(() => {
    if (activeTab === 'audit') loadAudit();
    if (activeTab === 'decisions') loadDecisions();
  }, [activeTab, loadAudit, loadDecisions]);

  // Save policy
  const savePolicy = async (policy) => {
    try {
      if (policy.id) {
        await api.put(`/v1/governance/policies/${policy.id}`, policy);
      } else {
        await api.post(`/v1/governance/policies${tenantParam}`, policy);
      }
      setEditingPolicy(null);
      loadPipeline();
    } catch (err) {
      alert(`Failed to save policy: ${err.response?.data?.detail || err.message}`);
    }
  };

  // Delete policy
  const deletePolicy = async (id) => {
    if (!window.confirm('Delete this policy?')) return;
    try {
      await api.delete(`/v1/governance/policies/${id}`);
      loadPipeline();
    } catch (err) {
      alert(`Failed to delete: ${err.response?.data?.detail || err.message}`);
    }
  };

  // Simulate pipeline
  const runSimulation = async () => {
    try {
      const res = await api.post(`/v1/governance/pipeline/simulate${tenantParam}`, simForm);
      setSimResult(res.data);
    } catch (err) {
      setSimResult({ error: err.response?.data?.detail || err.message });
    }
  };

  // Create directive
  const createDirective = async () => {
    if (!newDirective?.objective) return;
    try {
      await api.post(`/v1/governance/directives${tenantParam}`, newDirective);
      setNewDirective(null);
      loadPipeline();
    } catch (err) {
      alert(`Failed to create: ${err.response?.data?.detail || err.message}`);
    }
  };

  // Apply policy to all sites
  const applyToAllSites = async (policy) => {
    if (!window.confirm('Apply these settings to ALL sites? This will create per-site policies with the same thresholds.')) return;
    // For now, creating a catch-all policy (agent_id=null covers all)
    const catchAll = { ...policy, agent_id: null, name: `${policy.name || policy.action_type} — All Sites` };
    delete catchAll.id;
    await savePolicy(catchAll);
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-primary mb-1">Decision Governance</h1>
        <p className="text-muted-foreground">
          Inspect and configure the governance pipeline that controls how agent decisions are executed
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-2 mb-1">
              <Settings className="h-5 w-5 text-primary" />
              <span className="font-semibold">Active Policies</span>
            </div>
            <p className="text-3xl font-bold">{policies.filter(p => p.is_active).length}</p>
            <p className="text-sm text-muted-foreground">Governing {Object.keys(AGENT_LABELS).length} agent types</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-2 mb-1">
              <Shield className="h-5 w-5 text-amber-600" />
              <span className="font-semibold">Active Directives</span>
            </div>
            <p className="text-3xl font-bold">{directives.length}</p>
            <p className="text-sm text-muted-foreground">Executive overrides in effect</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-2 mb-1">
              <Scale className="h-5 w-5 text-green-600" />
              <span className="font-semibold">Planning Envelope</span>
            </div>
            <p className="text-lg font-bold text-green-600">Adjust Before Create</p>
            <p className="text-sm text-muted-foreground">Glenday Sieve active</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-2 mb-1">
              <History className="h-5 w-5 text-blue-600" />
              <span className="font-semibold">Gate Decisions</span>
            </div>
            <p className="text-3xl font-bold">{decisions.length}</p>
            <p className="text-sm text-muted-foreground">Recent governance outcomes</p>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Card>
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <div className="border-b">
            <TabsList className="w-full justify-start p-0 h-auto bg-transparent">
              <TabsTrigger value="pipeline" className="flex items-center gap-2 rounded-none border-b-2 border-transparent data-[state=active]:border-primary">
                <Sliders className="h-4 w-4" />
                Pipeline
              </TabsTrigger>
              <TabsTrigger value="policies" className="flex items-center gap-2 rounded-none border-b-2 border-transparent data-[state=active]:border-primary">
                <Settings className="h-4 w-4" />
                Policies
              </TabsTrigger>
              <TabsTrigger value="directives" className="flex items-center gap-2 rounded-none border-b-2 border-transparent data-[state=active]:border-primary">
                <Shield className="h-4 w-4" />
                Directives
              </TabsTrigger>
              <TabsTrigger value="simulate" className="flex items-center gap-2 rounded-none border-b-2 border-transparent data-[state=active]:border-primary">
                <Play className="h-4 w-4" />
                Simulate
              </TabsTrigger>
              <TabsTrigger value="decisions" className="flex items-center gap-2 rounded-none border-b-2 border-transparent data-[state=active]:border-primary">
                <FileText className="h-4 w-4" />
                Decision Log
              </TabsTrigger>
              <TabsTrigger value="oversight" className="flex items-center gap-2 rounded-none border-b-2 border-transparent data-[state=active]:border-primary">
                <Settings className="h-4 w-4" />
                Oversight Schedule
              </TabsTrigger>
              <TabsTrigger value="audit" className="flex items-center gap-2 rounded-none border-b-2 border-transparent data-[state=active]:border-primary">
                <History className="h-4 w-4" />
                Audit Trail
              </TabsTrigger>
            </TabsList>
          </div>

          {/* ── Pipeline Tab ─────────────────────────────── */}
          <TabsContent value="pipeline" className="p-4">
            <h2 className="text-lg font-semibold mb-4">Governance Pipeline Flow</h2>
            {pipeline?.stages?.map((stage, i) => (
              <div key={i} className="mb-4">
                <div className="flex items-center gap-3 mb-2">
                  <div className="w-8 h-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center font-bold text-sm">
                    {i + 1}
                  </div>
                  <div>
                    <h3 className="font-semibold">{stage.name}</h3>
                    <p className="text-sm text-muted-foreground">{stage.description}</p>
                  </div>
                </div>
                {stage.dimensions && (
                  <div className="ml-11 grid grid-cols-5 gap-2">
                    {stage.dimensions.map((dim) => (
                      <div key={dim.key} className="bg-muted rounded p-2 text-center">
                        <p className="text-xs text-muted-foreground">{dim.label}</p>
                        <p className="font-bold">{(dim.default_weight * 100).toFixed(0)}%</p>
                      </div>
                    ))}
                  </div>
                )}
                {stage.modes && (
                  <div className="ml-11 flex gap-3">
                    {stage.modes.map((m) => (
                      <div key={m.mode} className={cn('rounded px-3 py-1.5 text-sm font-medium', MODE_COLORS[m.mode])}>
                        {m.label}: {m.condition}
                      </div>
                    ))}
                  </div>
                )}
                {stage.settings?.glenday_preferences && (
                  <div className="ml-11 grid grid-cols-4 gap-2 mt-2">
                    {Object.entries(stage.settings.glenday_preferences).map(([cat, pref]) => (
                      <div key={cat} className="bg-muted rounded p-2 text-center">
                        <p className="text-xs text-muted-foreground capitalize">{cat} Runners</p>
                        <p className="font-bold">{(pref * 100).toFixed(0)}% adjust preference</p>
                      </div>
                    ))}
                  </div>
                )}
                {i < (pipeline?.stages?.length || 0) - 1 && (
                  <div className="ml-[19px] border-l-2 border-primary/30 h-4 mt-1" />
                )}
              </div>
            ))}
          </TabsContent>

          {/* ── Policies Tab ─────────────────────────────── */}
          <TabsContent value="policies" className="p-4">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold">Decision Policies</h2>
              <div className="flex gap-2">
                <Button variant="outline" onClick={loadPipeline} leftIcon={<RefreshCw className="h-4 w-4" />}>
                  Refresh
                </Button>
                <Button onClick={() => setEditingPolicy({
                  action_type: '', automate_below: 20, inform_below: 50,
                  hold_minutes: 60, weight_financial: 0.30, weight_scope: 0.20,
                  weight_reversibility: 0.20, weight_confidence: 0.15, weight_override_rate: 0.15,
                  writeback_enabled: true, writeback_base_delay_minutes: 30,
                  writeback_min_delay_minutes: 5, writeback_max_delay_minutes: 480,
                  writeback_urgency_weight: 1.0, writeback_confidence_weight: 1.0,
                  is_active: true, priority: 100, name: '', description: '',
                })} leftIcon={<Plus className="h-4 w-4" />}>
                  New Policy
                </Button>
              </div>
            </div>

            <p className="text-sm text-muted-foreground mb-4">
              Policies control when agent decisions are auto-executed, when users are informed, and when decisions are held for review.
              Controls are per-site — each site&apos;s agents can have different thresholds.
            </p>

            {policies.length === 0 ? (
              <Alert>No policies configured. System defaults apply (automate &lt; 20, inform &lt; 50, inspect &ge; 50).</Alert>
            ) : (
              <div className="space-y-3">
                {policies.map((policy) => (
                  <Card key={policy.id} variant="outline">
                    <CardContent className="pt-4">
                      <div className="flex justify-between items-start">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <h3 className="font-semibold">{policy.name || 'Unnamed Policy'}</h3>
                            <Badge variant={policy.is_active ? 'success' : 'secondary'}>
                              {policy.is_active ? 'Active' : 'Inactive'}
                            </Badge>
                          </div>
                          <p className="text-sm text-muted-foreground mb-2">{policy.description}</p>
                          <div className="flex flex-wrap gap-2 text-xs">
                            <Badge variant="outline">
                              Agent: {policy.action_type ? (AGENT_LABELS[policy.action_type] || policy.action_type) : 'All'}
                            </Badge>
                            <Badge variant="outline">
                              Site: {policy.agent_id || 'All Sites'}
                            </Badge>
                            <span className={cn('px-2 py-0.5 rounded font-medium', MODE_COLORS.AUTOMATE)}>
                              Auto &lt; {policy.automate_below}
                            </span>
                            <span className={cn('px-2 py-0.5 rounded font-medium', MODE_COLORS.INFORM)}>
                              Inform &lt; {policy.inform_below}
                            </span>
                            <span className={cn('px-2 py-0.5 rounded font-medium', MODE_COLORS.INSPECT)}>
                              Inspect &ge; {policy.inform_below}
                            </span>
                            <Badge variant="secondary">Hold: {policy.hold_minutes}min</Badge>
                            {policy.writeback_enabled !== false && (
                              <Badge variant="outline">Writeback: {policy.writeback_min_delay_minutes ?? 5}-{policy.writeback_max_delay_minutes ?? 480}min</Badge>
                            )}
                            {policy.writeback_enabled === false && (
                              <Badge variant="destructive">Writeback: OFF</Badge>
                            )}
                          </div>
                        </div>
                        <div className="flex gap-1">
                          <Button variant="ghost" size="sm" onClick={() => applyToAllSites(policy)} title="Apply to all sites">
                            <Copy className="h-4 w-4" />
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => setEditingPolicy({ ...policy })}>
                            <Settings className="h-4 w-4" />
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => deletePolicy(policy.id)}>
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </TabsContent>

          {/* ── Directives Tab ────────────────────────────── */}
          <TabsContent value="directives" className="p-4">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold">Guardrail Directives</h2>
              <Button onClick={() => setNewDirective({ objective: '', context: '', reason: '', source_channel: 'manual' })} leftIcon={<Plus className="h-4 w-4" />}>
                New Directive
              </Button>
            </div>

            <p className="text-sm text-muted-foreground mb-4">
              Executive directives override normal governance thresholds for a defined period.
              Example: &quot;Tighten PO controls above $50K this quarter.&quot;
            </p>

            {directives.length === 0 ? (
              <Alert>No active directives.</Alert>
            ) : (
              <div className="space-y-3">
                {directives.map((d) => (
                  <Card key={d.id} variant="outline">
                    <CardContent className="pt-4">
                      <div className="flex items-center gap-2 mb-1">
                        <Shield className="h-4 w-4 text-amber-600" />
                        <h3 className="font-semibold">{d.objective}</h3>
                        <Badge variant="warning">{d.status}</Badge>
                        <Badge variant="outline">{d.source_channel}</Badge>
                      </div>
                      {d.context && <p className="text-sm text-muted-foreground mb-1">{d.context}</p>}
                      {d.reason && <p className="text-sm text-muted-foreground mb-1">Reason: {d.reason}</p>}
                      <div className="flex gap-2 text-xs">
                        {d.effective_from && <Badge variant="secondary">From: {new Date(d.effective_from).toLocaleDateString()}</Badge>}
                        {d.effective_until && <Badge variant="secondary">Until: {new Date(d.effective_until).toLocaleDateString()}</Badge>}
                        {d.extraction_confidence && <Badge variant="secondary">Confidence: {(d.extraction_confidence * 100).toFixed(0)}%</Badge>}
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </TabsContent>

          {/* ── Simulate Tab ──────────────────────────────── */}
          <TabsContent value="simulate" className="p-4">
            <h2 className="text-lg font-semibold mb-2">Pipeline Simulator</h2>
            <p className="text-sm text-muted-foreground mb-4">
              Test how a hypothetical decision would be gated before changing policies.
            </p>

            <div className="grid grid-cols-3 gap-4 mb-4">
              <div>
                <label className="text-sm font-medium mb-1 block">Agent Type</label>
                <select
                  className="w-full border rounded px-3 py-2 text-sm"
                  value={simForm.action_type}
                  onChange={(e) => setSimForm({ ...simForm, action_type: e.target.value })}
                >
                  {Object.entries(AGENT_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Estimated Impact ($)</label>
                <Input
                  type="number"
                  value={simForm.estimated_impact || ''}
                  onChange={(e) => setSimForm({ ...simForm, estimated_impact: parseFloat(e.target.value) || 0 })}
                />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Confidence (0-1)</label>
                <Input
                  type="number"
                  step="0.05"
                  min="0"
                  max="1"
                  value={simForm.confidence_level || ''}
                  onChange={(e) => setSimForm({ ...simForm, confidence_level: parseFloat(e.target.value) || 0 })}
                />
              </div>
            </div>
            <Button onClick={runSimulation} leftIcon={<Play className="h-4 w-4" />}>
              Run Simulation
            </Button>

            {simResult && !simResult.error && (
              <Card className="mt-4">
                <CardContent className="pt-4">
                  <div className="flex items-center gap-3 mb-3">
                    <span className="text-2xl font-bold">{simResult.impact_score}</span>
                    <span className="text-muted-foreground">/100 impact score</span>
                    <Badge className={cn('text-sm', MODE_COLORS[simResult.assigned_mode])}>
                      {simResult.assigned_mode}
                    </Badge>
                  </div>
                  <p className="text-sm mb-3">{simResult.explanation}</p>
                  {simResult.impact_breakdown && (
                    <div className="grid grid-cols-5 gap-2">
                      {Object.entries(simResult.impact_breakdown).map(([k, v]) => (
                        <div key={k} className="bg-muted rounded p-2 text-center">
                          <p className="text-xs text-muted-foreground capitalize">{k.replace('_', ' ')}</p>
                          <p className="font-bold">{v}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
            {simResult?.error && (
              <Alert variant="destructive" className="mt-4">{simResult.error}</Alert>
            )}
          </TabsContent>

          {/* ── Decision Log Tab ──────────────────────────── */}
          <TabsContent value="decisions" className="p-4">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold">Recent Governance Decisions</h2>
              <Button variant="outline" onClick={loadDecisions} leftIcon={<RefreshCw className="h-4 w-4" />}>
                Refresh
              </Button>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Agent</TableHead>
                  <TableHead>Title</TableHead>
                  <TableHead>Impact</TableHead>
                  <TableHead>Mode</TableHead>
                  <TableHead>Result</TableHead>
                  <TableHead>Overridden</TableHead>
                  <TableHead>Time</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {decisions.map((d) => (
                  <TableRow key={d.id}>
                    <TableCell className="text-xs">{AGENT_LABELS[d.action_type] || d.action_type}</TableCell>
                    <TableCell className="text-xs max-w-[200px] truncate">{d.title}</TableCell>
                    <TableCell>{d.impact_score != null ? d.impact_score.toFixed(0) : '—'}</TableCell>
                    <TableCell>
                      <Badge className={cn('text-xs', MODE_COLORS[d.mode] || '')}>
                        {d.mode}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs">{d.execution_result}</TableCell>
                    <TableCell>{d.is_overridden ? 'Yes' : '—'}</TableCell>
                    <TableCell className="text-xs">{d.created_at ? new Date(d.created_at).toLocaleString() : ''}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TabsContent>

          {/* ── Oversight Schedule Tab ─────────────────────── */}
          <TabsContent value="oversight" className="p-4">
            <div className="flex justify-between items-center mb-4">
              <div>
                <h2 className="text-lg font-semibold">Human Oversight Schedule</h2>
                <p className="text-sm text-muted-foreground">
                  Write-back delays only count down during these hours. Decisions outside hours wait for the next operating window.
                </p>
              </div>
              <Button variant="outline" onClick={async () => {
                try {
                  const res = await api.get(`/v1/governance/oversight${tenantParam}`);
                  setOversightConfig(res.data.config || {
                    timezone: 'UTC', respect_business_hours: true,
                    urgent_bypass_enabled: true, urgent_bypass_threshold: 0.85,
                    extend_delay_over_weekends: true, max_calendar_delay_hours: 72,
                    oncall_enabled: false,
                  });
                  setWeekSchedule(res.data.schedule || []);
                  setHolidays(res.data.holidays || []);
                } catch { setOversightConfig({ timezone: 'UTC', respect_business_hours: true, urgent_bypass_enabled: true, urgent_bypass_threshold: 0.85, extend_delay_over_weekends: true, max_calendar_delay_hours: 72, oncall_enabled: false }); setWeekSchedule([]); }
              }} leftIcon={<RefreshCw className="h-4 w-4" />}>
                Load
              </Button>
            </div>

            {oversightConfig && (
              <div className="space-y-6">
                {/* General Settings */}
                <Card>
                  <CardContent className="p-4 space-y-4">
                    <h3 className="font-medium">General Settings</h3>
                    <div className="grid grid-cols-3 gap-4">
                      <div>
                        <label className="text-sm font-medium mb-1 block">Timezone (IANA)</label>
                        <Input value={oversightConfig.timezone || 'UTC'}
                          onChange={(e) => setOversightConfig({ ...oversightConfig, timezone: e.target.value })}
                          placeholder="America/Chicago" />
                      </div>
                      <div>
                        <label className="text-sm font-medium mb-1 block">Max calendar delay (hours)</label>
                        <Input type="number" value={oversightConfig.max_calendar_delay_hours ?? 72}
                          onChange={(e) => setOversightConfig({ ...oversightConfig, max_calendar_delay_hours: parseInt(e.target.value) })} />
                        <p className="text-xs text-muted-foreground mt-1">Cap to prevent indefinite hold over long weekends</p>
                      </div>
                      <div className="space-y-2 pt-5">
                        <label className="flex items-center gap-2 text-sm">
                          <input type="checkbox" checked={oversightConfig.respect_business_hours !== false}
                            onChange={(e) => setOversightConfig({ ...oversightConfig, respect_business_hours: e.target.checked })}
                            className="rounded border-gray-300" />
                          Respect business hours
                        </label>
                        <label className="flex items-center gap-2 text-sm">
                          <input type="checkbox" checked={oversightConfig.extend_delay_over_weekends !== false}
                            onChange={(e) => setOversightConfig({ ...oversightConfig, extend_delay_over_weekends: e.target.checked })}
                            className="rounded border-gray-300" />
                          Pause over non-operating days
                        </label>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {/* Urgent Bypass */}
                <Card>
                  <CardContent className="p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="font-medium">Urgent Bypass</h3>
                      <label className="flex items-center gap-2 text-sm">
                        <input type="checkbox" checked={oversightConfig.urgent_bypass_enabled !== false}
                          onChange={(e) => setOversightConfig({ ...oversightConfig, urgent_bypass_enabled: e.target.checked })}
                          className="rounded border-gray-300" />
                        Enabled
                      </label>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      Decisions with urgency above the threshold ignore business hours and execute after the raw delay.
                      The write-back is still audited and visible in Decision Stream.
                    </p>
                    {oversightConfig.urgent_bypass_enabled !== false && (
                      <div className="w-64">
                        <label className="text-sm font-medium mb-1 block">Urgency threshold</label>
                        <div className="flex items-center gap-2">
                          <Input type="number" step="0.05" min="0.5" max="1.0"
                            value={oversightConfig.urgent_bypass_threshold ?? 0.85}
                            onChange={(e) => setOversightConfig({ ...oversightConfig, urgent_bypass_threshold: parseFloat(e.target.value) })} />
                          <span className="text-sm text-muted-foreground">({Math.round((oversightConfig.urgent_bypass_threshold ?? 0.85) * 100)}%)</span>
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* Weekly Schedule */}
                <Card>
                  <CardContent className="p-4">
                    <h3 className="font-medium mb-3">Weekly Operating Hours</h3>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="w-32">Day</TableHead>
                          <TableHead>Operating</TableHead>
                          <TableHead>Start</TableHead>
                          <TableHead>End</TableHead>
                          <TableHead>Hours</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'].map((day, idx) => {
                          const sched = weekSchedule.find(s => s.day_of_week === idx) || {
                            day_of_week: idx,
                            is_operating: idx < 5,
                            start_time: '08:00',
                            end_time: '17:00',
                          };
                          const updateDay = (field, value) => {
                            const updated = weekSchedule.filter(s => s.day_of_week !== idx);
                            updated.push({ ...sched, [field]: value });
                            setWeekSchedule(updated);
                          };
                          const hours = sched.is_operating
                            ? ((parseInt(sched.end_time?.split(':')[0] || 17) - parseInt(sched.start_time?.split(':')[0] || 8)))
                            : 0;
                          return (
                            <TableRow key={day}>
                              <TableCell className="font-medium">{day}</TableCell>
                              <TableCell>
                                <input type="checkbox" checked={sched.is_operating !== false}
                                  onChange={(e) => updateDay('is_operating', e.target.checked)}
                                  className="rounded border-gray-300" />
                              </TableCell>
                              <TableCell>
                                <Input type="time" value={sched.start_time || '08:00'}
                                  disabled={!sched.is_operating}
                                  onChange={(e) => updateDay('start_time', e.target.value)}
                                  className="w-28" />
                              </TableCell>
                              <TableCell>
                                <Input type="time" value={sched.end_time || '17:00'}
                                  disabled={!sched.is_operating}
                                  onChange={(e) => updateDay('end_time', e.target.value)}
                                  className="w-28" />
                              </TableCell>
                              <TableCell className="text-muted-foreground">{hours}h</TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>

                {/* Save button */}
                <div className="flex justify-end">
                  <Button onClick={async () => {
                    try {
                      await api.put(`/v1/governance/oversight${tenantParam}`, {
                        config: oversightConfig,
                        schedule: weekSchedule,
                        holidays,
                      });
                    } catch (err) { console.error('Failed to save oversight config:', err); }
                  }} leftIcon={<Save className="h-4 w-4" />}>
                    Save Oversight Schedule
                  </Button>
                </div>
              </div>
            )}

            {!oversightConfig && (
              <Alert>Click Load to view and configure the oversight schedule.</Alert>
            )}
          </TabsContent>

          {/* ── Audit Trail Tab ───────────────────────────── */}
          <TabsContent value="audit" className="p-4">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold">Audit Trail</h2>
              <Button variant="outline" onClick={loadAudit} leftIcon={<RefreshCw className="h-4 w-4" />}>
                Refresh
              </Button>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Time</TableHead>
                  <TableHead>User</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead>Resource</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Details</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {auditLogs.map((log) => (
                  <TableRow key={log.id}>
                    <TableCell className="text-xs">{log.timestamp ? new Date(log.timestamp).toLocaleString() : ''}</TableCell>
                    <TableCell className="text-xs">{log.user}</TableCell>
                    <TableCell><Badge variant="secondary" className="text-xs">{log.action}</Badge></TableCell>
                    <TableCell className="text-xs">{log.resource}</TableCell>
                    <TableCell>
                      <Badge variant={log.status === 'completed' || log.status === 'SUCCESS' ? 'success' : log.status === 'failed' ? 'destructive' : 'secondary'}>
                        {log.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs max-w-[200px] truncate">{log.description}</TableCell>
                  </TableRow>
                ))}
                {auditLogs.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                      No audit entries yet. Provisioning and governance actions will appear here.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TabsContent>
        </Tabs>
      </Card>

      {/* ── Policy Editor Modal ────────────────────────── */}
      <Modal
        isOpen={!!editingPolicy}
        onClose={() => setEditingPolicy(null)}
        title={editingPolicy?.id ? 'Edit Policy' : 'New Policy'}
        size="lg"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setEditingPolicy(null)}>Cancel</Button>
            <Button onClick={() => savePolicy(editingPolicy)} leftIcon={<Save className="h-4 w-4" />}>Save</Button>
          </div>
        }
      >
        {editingPolicy && (
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <label className="text-sm font-medium mb-1 block">Name</label>
              <Input value={editingPolicy.name || ''} onChange={(e) => setEditingPolicy({ ...editingPolicy, name: e.target.value })} />
            </div>
            <div className="col-span-2">
              <label className="text-sm font-medium mb-1 block">Description</label>
              <Input value={editingPolicy.description || ''} onChange={(e) => setEditingPolicy({ ...editingPolicy, description: e.target.value })} />
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">Agent Type</label>
              <select className="w-full border rounded px-3 py-2 text-sm" value={editingPolicy.action_type || ''} onChange={(e) => setEditingPolicy({ ...editingPolicy, action_type: e.target.value || null })}>
                <option value="">All Agents</option>
                {Object.entries(AGENT_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">Site (agent_id)</label>
              <Input placeholder="Leave blank for all sites" value={editingPolicy.agent_id || ''} onChange={(e) => setEditingPolicy({ ...editingPolicy, agent_id: e.target.value || null })} />
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">Auto-execute below (impact score)</label>
              <Input type="number" value={editingPolicy.automate_below} onChange={(e) => setEditingPolicy({ ...editingPolicy, automate_below: parseFloat(e.target.value) })} />
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">Inform below (impact score)</label>
              <Input type="number" value={editingPolicy.inform_below} onChange={(e) => setEditingPolicy({ ...editingPolicy, inform_below: parseFloat(e.target.value) })} />
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">Hold minutes (INSPECT)</label>
              <Input type="number" value={editingPolicy.hold_minutes} onChange={(e) => setEditingPolicy({ ...editingPolicy, hold_minutes: parseInt(e.target.value) })} />
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">Priority (lower = higher)</label>
              <Input type="number" value={editingPolicy.priority} onChange={(e) => setEditingPolicy({ ...editingPolicy, priority: parseInt(e.target.value) })} />
            </div>
            <div className="col-span-2">
              <label className="text-sm font-medium mb-2 block">Impact Scoring Weights (must sum to ~1.0)</label>
              <div className="grid grid-cols-5 gap-2">
                {['financial', 'scope', 'reversibility', 'confidence', 'override_rate'].map((dim) => (
                  <div key={dim}>
                    <label className="text-xs text-muted-foreground capitalize">{dim.replace('_', ' ')}</label>
                    <Input type="number" step="0.05" min="0" max="1" value={editingPolicy[`weight_${dim}`]} onChange={(e) => setEditingPolicy({ ...editingPolicy, [`weight_${dim}`]: parseFloat(e.target.value) })} />
                  </div>
                ))}
              </div>
            </div>

            {/* ── ERP Write-back Delay Settings ──────────────────── */}
            <div className="col-span-2 border-t pt-4 mt-2">
              <div className="flex items-center justify-between mb-3">
                <label className="text-sm font-semibold">ERP Write-back Delay</label>
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={editingPolicy.writeback_enabled !== false}
                    onChange={(e) => setEditingPolicy({ ...editingPolicy, writeback_enabled: e.target.checked })}
                    className="rounded border-gray-300" />
                  Enabled
                </label>
              </div>
              <p className="text-xs text-muted-foreground mb-3">
                Every agent decision waits before writing to the ERP. Higher urgency and higher confidence shorten the delay.
                During the delay, users can override in Decision Stream.
              </p>
              {editingPolicy.writeback_enabled !== false && (
                <>
                  <div className="grid grid-cols-3 gap-3 mb-3">
                    <div>
                      <label className="text-xs text-muted-foreground">Base delay (min)</label>
                      <Input type="number" min="1" max="1440" value={editingPolicy.writeback_base_delay_minutes ?? 30}
                        onChange={(e) => setEditingPolicy({ ...editingPolicy, writeback_base_delay_minutes: parseInt(e.target.value) })} />
                    </div>
                    <div>
                      <label className="text-xs text-muted-foreground">Min delay (floor)</label>
                      <Input type="number" min="0" max="60" value={editingPolicy.writeback_min_delay_minutes ?? 5}
                        onChange={(e) => setEditingPolicy({ ...editingPolicy, writeback_min_delay_minutes: parseInt(e.target.value) })} />
                    </div>
                    <div>
                      <label className="text-xs text-muted-foreground">Max delay (ceiling)</label>
                      <Input type="number" min="30" max="2880" value={editingPolicy.writeback_max_delay_minutes ?? 480}
                        onChange={(e) => setEditingPolicy({ ...editingPolicy, writeback_max_delay_minutes: parseInt(e.target.value) })} />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3 mb-2">
                    <div>
                      <label className="text-xs text-muted-foreground">Urgency weight</label>
                      <Input type="number" step="0.1" min="0" max="2" value={editingPolicy.writeback_urgency_weight ?? 1.0}
                        onChange={(e) => setEditingPolicy({ ...editingPolicy, writeback_urgency_weight: parseFloat(e.target.value) })} />
                      <p className="text-xs text-muted-foreground mt-0.5">Higher = urgency reduces delay more</p>
                    </div>
                    <div>
                      <label className="text-xs text-muted-foreground">Confidence weight</label>
                      <Input type="number" step="0.1" min="0" max="2" value={editingPolicy.writeback_confidence_weight ?? 1.0}
                        onChange={(e) => setEditingPolicy({ ...editingPolicy, writeback_confidence_weight: parseFloat(e.target.value) })} />
                      <p className="text-xs text-muted-foreground mt-0.5">Higher = confidence reduces delay more</p>
                    </div>
                  </div>
                  {/* Live preview */}
                  <div className="bg-slate-50 rounded p-3 mt-3">
                    <p className="text-xs font-medium mb-1">Delay Preview</p>
                    <div className="grid grid-cols-3 gap-2 text-xs text-muted-foreground">
                      {[
                        { label: 'Urgent + Confident', u: 0.9, c: 0.9 },
                        { label: 'Medium', u: 0.5, c: 0.5 },
                        { label: 'Low urgency + Uncertain', u: 0.2, c: 0.3 },
                      ].map(({ label, u, c }) => {
                        const base = editingPolicy.writeback_base_delay_minutes ?? 30;
                        const uw = editingPolicy.writeback_urgency_weight ?? 1.0;
                        const cw = editingPolicy.writeback_confidence_weight ?? 1.0;
                        const floor = editingPolicy.writeback_min_delay_minutes ?? 5;
                        const ceil = editingPolicy.writeback_max_delay_minutes ?? 480;
                        const raw = base * Math.max(0.05, 1 - u * uw) * Math.max(0.5, 2 - c * cw);
                        const clamped = Math.round(Math.max(floor, Math.min(ceil, raw)));
                        return (
                          <div key={label} className="bg-white rounded p-2 text-center">
                            <div className="font-medium text-foreground">{clamped} min</div>
                            <div>{label}</div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        )}
      </Modal>

      {/* ── New Directive Modal ────────────────────────── */}
      <Modal
        isOpen={!!newDirective}
        onClose={() => setNewDirective(null)}
        title="New Guardrail Directive"
        size="md"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setNewDirective(null)}>Cancel</Button>
            <Button onClick={createDirective} leftIcon={<Shield className="h-4 w-4" />}>Create Directive</Button>
          </div>
        }
      >
        {newDirective && (
          <div className="space-y-3">
            <div>
              <label className="text-sm font-medium mb-1 block">Objective</label>
              <Input placeholder="e.g., Tighten PO controls above $50K this quarter" value={newDirective.objective} onChange={(e) => setNewDirective({ ...newDirective, objective: e.target.value })} />
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">Business Context</label>
              <Input placeholder="e.g., Supplier bankruptcy concerns" value={newDirective.context || ''} onChange={(e) => setNewDirective({ ...newDirective, context: e.target.value })} />
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">Reason</label>
              <Input placeholder="e.g., Risk mitigation" value={newDirective.reason || ''} onChange={(e) => setNewDirective({ ...newDirective, reason: e.target.value })} />
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">Effective Until</label>
              <Input type="date" value={newDirective.effective_until || ''} onChange={(e) => setNewDirective({ ...newDirective, effective_until: e.target.value })} />
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default Governance;
