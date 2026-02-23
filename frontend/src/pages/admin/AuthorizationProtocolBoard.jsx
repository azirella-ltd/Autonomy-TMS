/**
 * Authorization Protocol Board
 *
 * Visualizes the Agentic Authorization Protocol (AAP):
 * - Active negotiation threads with phase tracking
 * - Balanced Scorecard comparison (baseline vs projected)
 * - Authority map browser (per-agent permissions)
 * - Thread timeline with event audit trail
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, CardContent, CardHeader, CardTitle,
  Tabs, TabsList, TabsTrigger, TabsContent,
  Alert, Badge, Button,
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
  Tooltip, TooltipContent, TooltipProvider, TooltipTrigger,
  Progress,
} from '../../components/common';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip as RechartsTooltip, ResponsiveContainer,
  Cell,
} from 'recharts';
import {
  Shield, AlertTriangle, CheckCircle, Clock, RefreshCw,
  ArrowRight, ArrowLeftRight, Ban, UserCheck, Zap,
  Handshake, Scale, FileText, Users, Eye,
} from 'lucide-react';
import { api } from '../../services/api';

// ============================================================================
// Constants
// ============================================================================

const PHASE_COLORS = {
  evaluate: '#3b82f6',
  request: '#f59e0b',
  authorize: '#8b5cf6',
  resolved: '#10b981',
  expired: '#ef4444',
};

const DECISION_COLORS = {
  authorize: '#10b981',
  deny: '#ef4444',
  counter_offer: '#f59e0b',
  escalate: '#8b5cf6',
  timeout: '#6b7280',
};

const CATEGORY_COLORS = {
  unilateral: '#10b981',
  requires_authorization: '#f59e0b',
  forbidden: '#ef4444',
};

const QUADRANT_LABELS = {
  financial: 'Financial',
  customer: 'Customer',
  operational: 'Operational',
  strategic: 'Strategic',
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

/** Thread card showing negotiation status */
const ThreadCard = ({ thread, onSelect, selected }) => {
  const phaseColor = PHASE_COLORS[thread.phase] || '#6b7280';
  const decisionColor = thread.final_decision ? DECISION_COLORS[thread.final_decision] || '#6b7280' : null;

  return (
    <Card
      className={`cursor-pointer transition-all ${selected ? 'ring-2 ring-primary' : 'hover:border-primary/50'}`}
      onClick={() => onSelect(thread)}
    >
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-2">
          <Badge style={{ backgroundColor: phaseColor, color: 'white' }}>
            {thread.phase?.toUpperCase()}
          </Badge>
          {thread.final_decision && (
            <Badge style={{ backgroundColor: decisionColor, color: 'white' }}>
              {thread.final_decision?.toUpperCase()}
            </Badge>
          )}
        </div>
        <div className="text-sm font-medium">
          {thread.request?.requesting_agent} <ArrowRight className="inline h-3 w-3" /> {thread.request?.target_agent}
        </div>
        <div className="text-xs text-muted-foreground mt-1">
          {thread.request?.proposed_action?.action_type?.replace(/_/g, ' ')}
        </div>
        <div className="flex items-center justify-between mt-2 text-xs text-muted-foreground">
          <span>NB: {thread.request?.net_benefit?.toFixed(3)}</span>
          <span>{thread.request?.priority}</span>
          {thread.duration_seconds != null && (
            <span>{thread.duration_seconds.toFixed(1)}s</span>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

/** Scorecard visualization */
const ScorecardView = ({ scorecard }) => {
  if (!scorecard?.metrics?.length) {
    return <p className="text-muted-foreground text-sm">No scorecard data</p>;
  }

  const quadrants = ['financial', 'customer', 'operational', 'strategic'];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">Net Benefit</span>
        <Badge variant={scorecard.net_benefit > 0 ? 'default' : 'destructive'}>
          {scorecard.net_benefit > 0 ? '+' : ''}{scorecard.net_benefit?.toFixed(4)}
        </Badge>
      </div>

      {quadrants.map(q => {
        const metrics = scorecard.metrics.filter(m => m.quadrant === q);
        if (metrics.length === 0) return null;
        return (
          <div key={q}>
            <h4 className="text-xs font-semibold text-muted-foreground uppercase mb-2">
              {QUADRANT_LABELS[q]}
            </h4>
            <div className="space-y-1">
              {metrics.map((m, i) => (
                <div key={i} className="flex items-center gap-2 text-sm">
                  <span className="w-32 truncate">{m.metric.replace(/_/g, ' ')}</span>
                  <div className="flex-1 h-2 bg-muted rounded-full relative">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${Math.min(Math.abs(m.delta) * 100, 100)}%`,
                        backgroundColor: m.delta * m.direction >= 0 ? '#10b981' : '#ef4444',
                      }}
                    />
                  </div>
                  <span className={`text-xs w-16 text-right ${m.delta >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {m.delta >= 0 ? '+' : ''}{m.delta.toFixed(3)}{m.unit}
                  </span>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
};

/** Event timeline */
const EventTimeline = ({ events }) => {
  if (!events?.length) return <p className="text-muted-foreground text-sm">No events</p>;

  return (
    <div className="space-y-3">
      {events.map((evt, idx) => (
        <div key={idx} className="flex items-start gap-3">
          <div className="w-2 h-2 mt-2 rounded-full bg-primary flex-shrink-0" />
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="text-[10px]">{evt.event}</Badge>
              <span className="text-xs text-muted-foreground">
                {evt.timestamp ? new Date(evt.timestamp).toLocaleTimeString() : ''}
              </span>
            </div>
            {evt.decision && (
              <span className="text-xs" style={{ color: DECISION_COLORS[evt.decision] || '#6b7280' }}>
                Decision: {evt.decision}
              </span>
            )}
            {evt.reason && <p className="text-xs text-muted-foreground mt-0.5">{evt.reason}</p>}
            {evt.net_benefit != null && (
              <span className="text-xs text-muted-foreground">Net Benefit: {evt.net_benefit.toFixed(4)}</span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
};

/** Authority map table for one agent */
const AuthorityTable = ({ role, actions }) => (
  <Card>
    <CardHeader>
      <CardTitle className="text-sm capitalize">{role.replace(/_/g, ' ')}</CardTitle>
    </CardHeader>
    <CardContent className="p-0">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="text-xs">Action</TableHead>
            <TableHead className="text-xs w-40">Category</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {Object.entries(actions).map(([action, category]) => (
            <TableRow key={action}>
              <TableCell className="text-xs">{action.replace(/_/g, ' ')}</TableCell>
              <TableCell>
                <Badge
                  className="text-[10px]"
                  style={{ backgroundColor: CATEGORY_COLORS[category] || '#6b7280', color: 'white' }}
                >
                  {category.replace(/_/g, ' ')}
                </Badge>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </CardContent>
  </Card>
);

// ============================================================================
// Main Board
// ============================================================================

const AuthorizationProtocolBoard = () => {
  const [threads, setThreads] = useState([]);
  const [authorityMap, setAuthorityMap] = useState({});
  const [stats, setStats] = useState(null);
  const [selectedThread, setSelectedThread] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const [threadsRes, mapRes, statsRes] = await Promise.all([
        api.get('/api/v1/authorization-protocol/threads'),
        api.get('/api/v1/authorization-protocol/authority-map'),
        api.get('/api/v1/authorization-protocol/stats'),
      ]);
      setThreads(threadsRes.data.threads || []);
      setAuthorityMap(mapRes.data.authority_map || {});
      setStats(statsRes.data);
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const activeThreads = threads.filter(t => !['resolved', 'expired'].includes(t.phase));
  const resolvedThreads = threads.filter(t => ['resolved', 'expired'].includes(t.phase));

  return (
    <div className="p-6 space-y-6 max-w-[1600px] mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Handshake className="h-7 w-7 text-indigo-500" />
            Authorization Protocol Board
          </h1>
          <p className="text-muted-foreground mt-1">
            Cross-functional agent negotiations, scorecard comparison, and authority governance
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchData}>
          <RefreshCw className="h-4 w-4 mr-1" /> Refresh
        </Button>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <span className="ml-2">{error}</span>
        </Alert>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <StatCard
          title="Active Threads"
          value={stats?.active_threads || activeThreads.length}
          icon={Zap}
          color="amber"
        />
        <StatCard
          title="Auto-Resolved"
          value={stats?.auto_resolved || 0}
          subtitle="by net benefit threshold"
          icon={CheckCircle}
          color="green"
        />
        <StatCard
          title="Escalated"
          value={stats?.escalated || 0}
          subtitle="to human review"
          icon={Users}
          color="purple"
        />
        <StatCard
          title="Avg Resolution"
          value={stats?.avg_resolution_seconds ? `${stats.avg_resolution_seconds.toFixed(1)}s` : '—'}
          icon={Clock}
          color="blue"
        />
        <StatCard
          title="Deny Rate"
          value={stats?.deny_rate ? `${(stats.deny_rate * 100).toFixed(0)}%` : '—'}
          icon={Ban}
          color="red"
        />
      </div>

      {/* Main Tabs */}
      <Tabs defaultValue="threads">
        <TabsList>
          <TabsTrigger value="threads">Active Negotiations</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
          <TabsTrigger value="authority">Authority Map</TabsTrigger>
          <TabsTrigger value="analytics">Analytics</TabsTrigger>
        </TabsList>

        {/* Active Negotiations Tab */}
        <TabsContent value="threads" className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Thread List */}
            <div className="space-y-3">
              <h3 className="text-sm font-semibold text-muted-foreground uppercase">
                Active ({activeThreads.length})
              </h3>
              {activeThreads.length > 0 ? (
                activeThreads.map(t => (
                  <ThreadCard
                    key={t.thread_id}
                    thread={t}
                    onSelect={setSelectedThread}
                    selected={selectedThread?.thread_id === t.thread_id}
                  />
                ))
              ) : (
                <Card>
                  <CardContent className="p-8 text-center">
                    <Handshake className="h-12 w-12 text-muted-foreground mx-auto mb-2" />
                    <p className="text-muted-foreground">No active negotiations</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Threads appear when agents request cross-authority actions
                    </p>
                  </CardContent>
                </Card>
              )}
            </div>

            {/* Detail Panel */}
            <div className="lg:col-span-2">
              {selectedThread ? (
                <div className="space-y-4">
                  {/* Thread Header */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-lg flex items-center gap-2">
                        <ArrowLeftRight className="h-5 w-5" />
                        {selectedThread.request?.requesting_agent?.replace(/_/g, ' ')}
                        <ArrowRight className="h-4 w-4" />
                        {selectedThread.request?.target_agent?.replace(/_/g, ' ')}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                        <div>
                          <p className="text-xs text-muted-foreground">Action</p>
                          <p className="text-sm font-medium">
                            {selectedThread.request?.proposed_action?.action_type?.replace(/_/g, ' ')}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground">Priority</p>
                          <Badge variant="outline">{selectedThread.request?.priority}</Badge>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground">Net Benefit</p>
                          <p className="text-sm font-bold">
                            {selectedThread.request?.net_benefit?.toFixed(4)}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground">Threshold</p>
                          <p className="text-sm">{selectedThread.request?.benefit_threshold}</p>
                        </div>
                      </div>
                      {selectedThread.request?.justification && (
                        <div className="p-3 rounded-lg bg-muted/30">
                          <p className="text-xs text-muted-foreground mb-1">Justification</p>
                          <p className="text-sm">{selectedThread.request.justification}</p>
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  {/* Scorecard */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-lg flex items-center gap-2">
                        <Scale className="h-5 w-5" /> Balanced Scorecard
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <ScorecardView scorecard={selectedThread.request?.scorecard} />
                    </CardContent>
                  </Card>

                  {/* Event Timeline */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-lg flex items-center gap-2">
                        <FileText className="h-5 w-5" /> Event Timeline
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <EventTimeline events={selectedThread.events} />
                    </CardContent>
                  </Card>
                </div>
              ) : (
                <Card>
                  <CardContent className="p-12 text-center">
                    <Eye className="h-16 w-16 text-muted-foreground mx-auto mb-3" />
                    <p className="text-muted-foreground">Select a thread to view details</p>
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        </TabsContent>

        {/* History Tab */}
        <TabsContent value="history" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Resolved Negotiations</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-xs">Thread</TableHead>
                    <TableHead className="text-xs">Requester → Target</TableHead>
                    <TableHead className="text-xs">Action</TableHead>
                    <TableHead className="text-xs">Decision</TableHead>
                    <TableHead className="text-xs">Source</TableHead>
                    <TableHead className="text-xs">Duration</TableHead>
                    <TableHead className="text-xs">Net Benefit</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {resolvedThreads.length > 0 ? resolvedThreads.map(t => (
                    <TableRow
                      key={t.thread_id}
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() => setSelectedThread(t)}
                    >
                      <TableCell className="text-xs font-mono">{t.thread_id?.slice(0, 12)}</TableCell>
                      <TableCell className="text-xs">
                        {t.request?.requesting_agent} → {t.request?.target_agent}
                      </TableCell>
                      <TableCell className="text-xs">
                        {t.request?.proposed_action?.action_type?.replace(/_/g, ' ')}
                      </TableCell>
                      <TableCell>
                        <Badge
                          className="text-[10px]"
                          style={{ backgroundColor: DECISION_COLORS[t.final_decision] || '#6b7280', color: 'white' }}
                        >
                          {t.final_decision}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs">{t.resolution_source}</TableCell>
                      <TableCell className="text-xs">
                        {t.duration_seconds != null ? `${t.duration_seconds.toFixed(1)}s` : '—'}
                      </TableCell>
                      <TableCell className="text-xs">{t.request?.net_benefit?.toFixed(4)}</TableCell>
                    </TableRow>
                  )) : (
                    <TableRow>
                      <TableCell colSpan={7} className="text-center text-muted-foreground py-8">
                        No resolved negotiations yet
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Authority Map Tab */}
        <TabsContent value="authority" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {Object.entries(authorityMap).map(([role, actions]) => (
              <AuthorityTable key={role} role={role} actions={actions} />
            ))}
            {Object.keys(authorityMap).length === 0 && (
              <Card className="col-span-full">
                <CardContent className="p-8 text-center">
                  <Shield className="h-12 w-12 text-muted-foreground mx-auto mb-2" />
                  <p className="text-muted-foreground">Authority map loading...</p>
                </CardContent>
              </Card>
            )}
          </div>
          <div className="flex gap-4">
            {Object.entries(CATEGORY_COLORS).map(([cat, color]) => (
              <div key={cat} className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
                <span className="text-xs capitalize">{cat.replace(/_/g, ' ')}</span>
              </div>
            ))}
          </div>
        </TabsContent>

        {/* Analytics Tab */}
        <TabsContent value="analytics" className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Decisions by Type</CardTitle>
              </CardHeader>
              <CardContent>
                {stats?.decisions_by_type ? (
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={Object.entries(stats.decisions_by_type).map(([k, v]) => ({ type: k, count: v }))}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="type" tick={{ fontSize: 11 }} />
                      <YAxis />
                      <RechartsTooltip />
                      <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                        {Object.keys(stats.decisions_by_type).map((key, idx) => (
                          <Cell key={idx} fill={DECISION_COLORS[key] || '#6b7280'} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <p className="text-muted-foreground text-center py-8">No analytics data yet</p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Top Requesting Agents</CardTitle>
              </CardHeader>
              <CardContent>
                {stats?.top_requesters ? (
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={stats.top_requesters} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis type="number" />
                      <YAxis dataKey="agent" type="category" width={100} tick={{ fontSize: 11 }} />
                      <RechartsTooltip />
                      <Bar dataKey="count" fill="#6366f1" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <p className="text-muted-foreground text-center py-8">No requester data yet</p>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default AuthorizationProtocolBoard;
