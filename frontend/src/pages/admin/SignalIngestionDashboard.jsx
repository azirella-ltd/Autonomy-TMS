/**
 * Signal Ingestion Dashboard
 *
 * Admin page for monitoring signal capture from external channels,
 * reviewing pending signals, managing source reliability, and tracking
 * forecast adjustments driven by signals.
 */

import React, { useState, useEffect } from 'react';
import { signalApi } from '../../services/edgeAgentApi';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
  Button,
  Spinner,
  Alert,
  AlertDescription,
  Tabs,
  TabsList,
  Tab,
  Input,
  NativeSelect,
  Badge,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '../../components/common';
import {
  Zap,
  Activity,
  ChevronRight,
  CheckCircle,
  AlertTriangle,
  Clock,
  RefreshCw,
  Search,
  TrendingUp,
  TrendingDown,
  Minus,
  Eye,
  Check,
  X,
  BarChart3,
  Settings,
  Link2,
  SlidersHorizontal,
  History,
  Shield,
  Undo2,
  MessageSquare,
  Mail,
  Mic,
  Radio,
  Globe,
  Newspaper,
} from 'lucide-react';
import { cn } from '../../lib/utils/cn';

const tabItems = [
  { value: 'monitoring', label: 'Monitoring', icon: <Activity className="h-4 w-4" /> },
  { value: 'review', label: 'Review Queue', icon: <Eye className="h-4 w-4" /> },
  { value: 'sources', label: 'Source Reliability', icon: <SlidersHorizontal className="h-4 w-4" /> },
  { value: 'correlations', label: 'Correlations', icon: <Link2 className="h-4 w-4" /> },
  { value: 'history', label: 'Adjustment History', icon: <History className="h-4 w-4" /> },
];

// Direction icons
const DirectionIcon = ({ direction }) => {
  if (direction === 'increase') return <TrendingUp className="h-4 w-4 text-red-500" />;
  if (direction === 'decrease') return <TrendingDown className="h-4 w-4 text-blue-500" />;
  return <Minus className="h-4 w-4 text-gray-400" />;
};

// Source icons
const sourceIcons = {
  email: Mail,
  slack: MessageSquare,
  teams: MessageSquare,
  whatsapp: MessageSquare,
  telegram: Radio,
  voice: Mic,
  weather: Globe,
  economic_indicator: BarChart3,
  news: Newspaper,
  market_intelligence: TrendingUp,
  customer_feedback: MessageSquare,
  sales_input: MessageSquare,
};

const getSourceIcon = (source) => {
  const Icon = sourceIcons[source] || Zap;
  return <Icon className="h-4 w-4" />;
};

// Confidence badge
const ConfidenceBadge = ({ confidence }) => {
  if (confidence >= 0.8) return <Badge variant="success">{(confidence * 100).toFixed(0)}%</Badge>;
  if (confidence >= 0.3) return <Badge variant="warning">{(confidence * 100).toFixed(0)}%</Badge>;
  return <Badge variant="destructive">{(confidence * 100).toFixed(0)}%</Badge>;
};

// ============================================================================
// Monitoring Tab
// ============================================================================
const MonitoringTab = ({ dashboard, loading, onRefresh }) => {
  if (loading) {
    return <div className="flex justify-center py-12"><Spinner size="lg" /></div>;
  }

  const stats = dashboard || {};

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Signals Today</p>
                <p className="text-3xl font-bold">{stats.signals_today || 0}</p>
              </div>
              <Zap className="h-8 w-8 text-yellow-500" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Auto-Applied</p>
                <p className="text-3xl font-bold text-green-600">{stats.auto_applied || 0}</p>
              </div>
              <CheckCircle className="h-8 w-8 text-green-500" />
            </div>
            <p className="text-xs text-muted-foreground mt-1">Confidence &ge; 0.8</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Pending Review</p>
                <p className="text-3xl font-bold text-yellow-600">{stats.pending_review || 0}</p>
              </div>
              <Clock className="h-8 w-8 text-yellow-500" />
            </div>
            <p className="text-xs text-muted-foreground mt-1">Confidence 0.3-0.8</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Rejected</p>
                <p className="text-3xl font-bold text-red-600">{stats.rejected || 0}</p>
              </div>
              <X className="h-8 w-8 text-red-500" />
            </div>
            <p className="text-xs text-muted-foreground mt-1">Confidence &lt; 0.3</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Correlated</p>
                <p className="text-3xl font-bold text-purple-600">{stats.correlated_groups || 0}</p>
              </div>
              <Link2 className="h-8 w-8 text-purple-500" />
            </div>
            <p className="text-xs text-muted-foreground mt-1">Multi-source boost</p>
          </CardContent>
        </Card>
      </div>

      {/* Signal Type Breakdown */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Signal Classification Breakdown</CardTitle>
            <Button variant="outline" size="sm" onClick={onRefresh}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Refresh
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {(stats.type_breakdown || [
              { type: 'DEMAND_INCREASE', count: 0 },
              { type: 'DEMAND_DECREASE', count: 0 },
              { type: 'DISRUPTION', count: 0 },
              { type: 'PRICE_CHANGE', count: 0 },
              { type: 'LEAD_TIME_CHANGE', count: 0 },
              { type: 'QUALITY_ALERT', count: 0 },
              { type: 'NEW_OPPORTUNITY', count: 0 },
              { type: 'COMPETITOR_ACTION', count: 0 },
            ]).map((item) => (
              <div key={item.type} className="p-3 rounded-lg border bg-muted/50">
                <p className="text-xs text-muted-foreground font-mono">{item.type}</p>
                <p className="text-xl font-bold mt-1">{item.count}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Source Breakdown */}
      <Card>
        <CardHeader>
          <CardTitle>Signals by Source</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {(stats.source_breakdown || [
              { source: 'slack', count: 0, reliability: 0.7 },
              { source: 'email', count: 0, reliability: 0.5 },
              { source: 'teams', count: 0, reliability: 0.7 },
              { source: 'voice', count: 0, reliability: 0.4 },
              { source: 'weather', count: 0, reliability: 0.7 },
              { source: 'news', count: 0, reliability: 0.6 },
            ]).map((src) => (
              <div key={src.source} className="flex items-center justify-between py-2 border-b last:border-0">
                <div className="flex items-center gap-2">
                  {getSourceIcon(src.source)}
                  <span className="font-medium capitalize">{src.source.replace('_', ' ')}</span>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-sm text-muted-foreground">Reliability: {src.reliability}</span>
                  <Badge variant="secondary">{src.count} signals</Badge>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Rate Limiting Status */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Rate Limiting & Security
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="text-center">
              <p className="text-sm text-muted-foreground">Signals This Hour</p>
              <p className="text-xl font-bold">{stats.signals_this_hour || 0} / 500</p>
            </div>
            <div className="text-center">
              <p className="text-sm text-muted-foreground">Duplicates Filtered</p>
              <p className="text-xl font-bold">{stats.duplicates_filtered || 0}</p>
            </div>
            <div className="text-center">
              <p className="text-sm text-muted-foreground">Injection Attempts</p>
              <p className="text-xl font-bold text-red-600">{stats.injection_attempts || 0}</p>
            </div>
            <div className="text-center">
              <p className="text-sm text-muted-foreground">Rate-Limited</p>
              <p className="text-xl font-bold">{stats.rate_limited || 0}</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

// ============================================================================
// Review Queue Tab
// ============================================================================
const ReviewQueueTab = () => {
  const [signals, setSignals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedSignal, setSelectedSignal] = useState(null);
  const [filterSource, setFilterSource] = useState('all');

  useEffect(() => {
    loadPending();
  }, []);

  const loadPending = async () => {
    setLoading(true);
    try {
      const res = await signalApi.getPendingSignals();
      setSignals(res.data || []);
    } catch {
      setSignals([]);
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (signalId) => {
    try {
      await signalApi.approveSignal(signalId);
      setSignals(prev => prev.filter(s => s.id !== signalId));
    } catch (err) {
      console.error('Failed to approve signal:', err);
    }
  };

  const handleReject = async (signalId) => {
    try {
      await signalApi.rejectSignal(signalId, 'Manually rejected by planner');
      setSignals(prev => prev.filter(s => s.id !== signalId));
    } catch (err) {
      console.error('Failed to reject signal:', err);
    }
  };

  const filteredSignals = filterSource === 'all'
    ? signals
    : signals.filter(s => s.source === filterSource);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <NativeSelect value={filterSource} onChange={(e) => setFilterSource(e.target.value)}>
            <option value="all">All Sources</option>
            <option value="email">Email</option>
            <option value="slack">Slack</option>
            <option value="teams">Teams</option>
            <option value="voice">Voice</option>
            <option value="news">News</option>
          </NativeSelect>
          <Badge variant="warning">{filteredSignals.length} pending</Badge>
        </div>
        <Button variant="outline" size="sm" onClick={loadPending}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Refresh
        </Button>
      </div>

      {loading ? (
        <div className="flex justify-center py-12"><Spinner size="lg" /></div>
      ) : filteredSignals.length === 0 ? (
        <Card>
          <CardContent className="pt-6">
            <div className="text-center py-12 text-muted-foreground">
              <CheckCircle className="h-12 w-12 mx-auto mb-4 text-green-300" />
              <p className="font-medium">All caught up!</p>
              <p className="text-sm">No signals pending review</p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {filteredSignals.map((signal) => (
            <Card key={signal.id} className="hover:shadow-md transition-shadow">
              <CardContent className="pt-6">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      {getSourceIcon(signal.source)}
                      <Badge variant="outline" className="capitalize">{signal.source}</Badge>
                      <Badge variant="secondary">{signal.signal_type}</Badge>
                      <DirectionIcon direction={signal.direction} />
                      <ConfidenceBadge confidence={signal.confidence} />
                    </div>

                    <p className="text-sm mb-2">{signal.text || signal.summary}</p>

                    <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                      {signal.product && <span>Product: <strong>{signal.product}</strong></span>}
                      {signal.site && <span>Site: <strong>{signal.site}</strong></span>}
                      {signal.magnitude_hint && <span>Magnitude: <strong>{signal.magnitude_hint}</strong></span>}
                      <span>
                        {signal.timestamp ? new Date(signal.timestamp).toLocaleString() : '—'}
                      </span>
                    </div>

                    {signal.correlated_with && signal.correlated_with.length > 0 && (
                      <div className="mt-2">
                        <Badge variant="outline" className="text-purple-600">
                          <Link2 className="h-3 w-3 mr-1" />
                          Correlated with {signal.correlated_with.length} other signal(s)
                        </Badge>
                      </div>
                    )}
                  </div>

                  <div className="flex gap-2 ml-4">
                    <Button variant="outline" size="sm" onClick={() => setSelectedSignal(signal)}>
                      <Eye className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="default"
                      size="sm"
                      className="bg-green-600 hover:bg-green-700"
                      onClick={() => handleApprove(signal.id)}
                    >
                      <Check className="h-4 w-4 mr-1" />
                      Approve
                    </Button>
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => handleReject(signal.id)}
                    >
                      <X className="h-4 w-4 mr-1" />
                      Reject
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Signal Detail Dialog */}
      <Dialog open={!!selectedSignal} onOpenChange={() => setSelectedSignal(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Signal Details</DialogTitle>
          </DialogHeader>
          {selectedSignal && (
            <div className="space-y-4">
              <div className="p-3 bg-muted rounded-lg">
                <p className="text-sm">{selectedSignal.text || selectedSignal.summary}</p>
              </div>

              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-muted-foreground">Source</span>
                  <p className="font-medium capitalize">{selectedSignal.source}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Signal Type</span>
                  <p className="font-medium">{selectedSignal.signal_type}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Direction</span>
                  <p className="font-medium flex items-center gap-1">
                    <DirectionIcon direction={selectedSignal.direction} />
                    {selectedSignal.direction}
                  </p>
                </div>
                <div>
                  <span className="text-muted-foreground">Confidence</span>
                  <p><ConfidenceBadge confidence={selectedSignal.confidence} /></p>
                </div>
                <div>
                  <span className="text-muted-foreground">Product</span>
                  <p className="font-medium">{selectedSignal.product || '—'}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Site</span>
                  <p className="font-medium">{selectedSignal.site || '—'}</p>
                </div>
              </div>

              {/* Confidence Breakdown */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Confidence Calculation</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span>Base LLM Classification Confidence</span>
                      <span className="font-mono">{selectedSignal.base_confidence?.toFixed(2) || '—'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>&times; Source Reliability Weight</span>
                      <span className="font-mono">{selectedSignal.source_reliability?.toFixed(2) || '—'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>&times; Time Decay Factor</span>
                      <span className="font-mono">{selectedSignal.time_decay?.toFixed(2) || '—'}</span>
                    </div>
                    <div className="flex justify-between border-t pt-2 font-semibold">
                      <span>= Final Confidence</span>
                      <ConfidenceBadge confidence={selectedSignal.confidence} />
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

// ============================================================================
// Source Reliability Tab
// ============================================================================
const SourceReliabilityTab = () => {
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);

  useEffect(() => {
    loadSources();
  }, []);

  const loadSources = async () => {
    setLoading(true);
    try {
      const res = await signalApi.getSourceReliability();
      setSources(res.data || []);
    } catch {
      // Default source reliability
      setSources([
        { source: 'email', default_weight: 0.5, learned_weight: null, signals_count: 0, accuracy: null },
        { source: 'slack', default_weight: 0.7, learned_weight: null, signals_count: 0, accuracy: null },
        { source: 'teams', default_weight: 0.7, learned_weight: null, signals_count: 0, accuracy: null },
        { source: 'whatsapp', default_weight: 0.6, learned_weight: null, signals_count: 0, accuracy: null },
        { source: 'telegram', default_weight: 0.6, learned_weight: null, signals_count: 0, accuracy: null },
        { source: 'voice', default_weight: 0.4, learned_weight: null, signals_count: 0, accuracy: null },
        { source: 'market_intelligence', default_weight: 0.8, learned_weight: null, signals_count: 0, accuracy: null },
        { source: 'news', default_weight: 0.6, learned_weight: null, signals_count: 0, accuracy: null },
        { source: 'weather', default_weight: 0.7, learned_weight: null, signals_count: 0, accuracy: null },
        { source: 'economic_indicator', default_weight: 0.8, learned_weight: null, signals_count: 0, accuracy: null },
        { source: 'customer_feedback', default_weight: 0.6, learned_weight: null, signals_count: 0, accuracy: null },
        { source: 'sales_input', default_weight: 0.7, learned_weight: null, signals_count: 0, accuracy: null },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateWeight = async (source, newWeight) => {
    try {
      await signalApi.updateSourceReliability(source, newWeight);
      setSources(prev => prev.map(s =>
        s.source === source ? { ...s, default_weight: newWeight } : s
      ));
      setEditing(null);
    } catch (err) {
      console.error('Failed to update weight:', err);
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Source reliability weights determine how much to trust signals from each channel.
        The learned weight is automatically adjusted based on historical signal accuracy.
        A signal's final confidence = base_confidence &times; source_weight &times; time_decay.
      </p>

      <Card>
        <CardHeader>
          <CardTitle>Source Reliability Configuration</CardTitle>
          <CardDescription>
            Adjust default weights (0.0 - 1.0). Higher = more trusted.
            The "Learned" column shows the automatically-adjusted weight from training data.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex justify-center py-8"><Spinner size="lg" /></div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-3 px-4 font-medium">Source</th>
                  <th className="text-left py-3 px-4 font-medium">Default Weight</th>
                  <th className="text-left py-3 px-4 font-medium">Learned Weight</th>
                  <th className="text-left py-3 px-4 font-medium">Signals Processed</th>
                  <th className="text-left py-3 px-4 font-medium">Accuracy</th>
                  <th className="text-left py-3 px-4 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {sources.map((src) => (
                  <tr key={src.source} className="border-b">
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-2">
                        {getSourceIcon(src.source)}
                        <span className="font-medium capitalize">{src.source.replace('_', ' ')}</span>
                      </div>
                    </td>
                    <td className="py-3 px-4">
                      {editing === src.source ? (
                        <Input
                          type="number"
                          step="0.1"
                          min="0"
                          max="1"
                          defaultValue={src.default_weight}
                          onBlur={(e) => handleUpdateWeight(src.source, Number(e.target.value))}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') handleUpdateWeight(src.source, Number(e.target.value));
                            if (e.key === 'Escape') setEditing(null);
                          }}
                          className="w-20"
                          autoFocus
                        />
                      ) : (
                        <span className="font-mono cursor-pointer" onClick={() => setEditing(src.source)}>
                          {src.default_weight.toFixed(1)}
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 font-mono">
                      {src.learned_weight != null ? (
                        <span className={cn(
                          src.learned_weight > src.default_weight ? 'text-green-600' :
                          src.learned_weight < src.default_weight ? 'text-red-600' : ''
                        )}>
                          {src.learned_weight.toFixed(2)}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="py-3 px-4">{src.signals_count}</td>
                    <td className="py-3 px-4">
                      {src.accuracy != null ? (
                        <Badge variant={src.accuracy >= 0.7 ? 'success' : src.accuracy >= 0.5 ? 'warning' : 'destructive'}>
                          {(src.accuracy * 100).toFixed(0)}%
                        </Badge>
                      ) : (
                        <span className="text-muted-foreground">Insufficient data</span>
                      )}
                    </td>
                    <td className="py-3 px-4">
                      <Button variant="ghost" size="sm" onClick={() => setEditing(src.source)}>
                        <Settings className="h-4 w-4" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

// ============================================================================
// Correlations Tab
// ============================================================================
const CorrelationsTab = () => {
  const [correlations, setCorrelations] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadCorrelations();
  }, []);

  const loadCorrelations = async () => {
    setLoading(true);
    try {
      const res = await signalApi.getCorrelations();
      setCorrelations(res.data || []);
    } catch {
      setCorrelations([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <Alert>
        <Link2 className="h-4 w-4" />
        <AlertDescription>
          When 2+ signals from different channels agree on the same product/direction within a 2-hour window,
          their combined confidence is boosted using the formula: 1 - &prod;(1 - conf<sub>i</sub>).
          This can push signals above the auto-apply threshold (0.8) without human review.
        </AlertDescription>
      </Alert>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Active Signal Correlations</CardTitle>
            <Button variant="outline" size="sm" onClick={loadCorrelations}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Refresh
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex justify-center py-8"><Spinner size="lg" /></div>
          ) : correlations.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Link2 className="h-12 w-12 mx-auto mb-4 text-muted-foreground/50" />
              <p>No active signal correlations</p>
              <p className="text-sm">Correlations appear when multiple channels report the same signal</p>
            </div>
          ) : (
            <div className="space-y-4">
              {correlations.map((group, i) => (
                <div key={i} className="p-4 rounded-lg border bg-purple-50/50">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <Link2 className="h-5 w-5 text-purple-600" />
                      <span className="font-semibold">
                        {group.product} — {group.direction}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-muted-foreground">Combined:</span>
                      <ConfidenceBadge confidence={group.combined_confidence} />
                    </div>
                  </div>

                  <div className="space-y-2">
                    {(group.signals || []).map((sig, j) => (
                      <div key={j} className="flex items-center justify-between text-sm pl-4 border-l-2 border-purple-300">
                        <div className="flex items-center gap-2">
                          {getSourceIcon(sig.source)}
                          <span className="capitalize">{sig.source}</span>
                          <span className="text-muted-foreground">{sig.text?.substring(0, 60)}...</span>
                        </div>
                        <ConfidenceBadge confidence={sig.confidence} />
                      </div>
                    ))}
                  </div>

                  {group.combined_confidence >= 0.8 && (
                    <div className="mt-2 flex items-center gap-2 text-sm text-green-700">
                      <CheckCircle className="h-4 w-4" />
                      Auto-applied: correlated confidence exceeds threshold
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

// ============================================================================
// Adjustment History Tab
// ============================================================================
const AdjustmentHistoryTab = () => {
  const [adjustments, setAdjustments] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadHistory();
  }, []);

  const loadHistory = async () => {
    setLoading(true);
    try {
      const res = await signalApi.getAdjustmentHistory({ limit: 50 });
      setAdjustments(res.data || []);
    } catch {
      setAdjustments([]);
    } finally {
      setLoading(false);
    }
  };

  const handleRevert = async (adjustmentId) => {
    if (!window.confirm('Are you sure you want to revert this forecast adjustment?')) return;
    try {
      await signalApi.revertAdjustment(adjustmentId);
      loadHistory();
    } catch (err) {
      console.error('Failed to revert adjustment:', err);
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Signal-Driven Forecast Adjustments</CardTitle>
              <CardDescription>History of forecast changes triggered by captured signals</CardDescription>
            </div>
            <Button variant="outline" size="sm" onClick={loadHistory}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Refresh
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex justify-center py-8"><Spinner size="lg" /></div>
          ) : adjustments.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <History className="h-12 w-12 mx-auto mb-4 text-muted-foreground/50" />
              <p>No forecast adjustments from signals yet</p>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-3 px-4 font-medium">Date</th>
                  <th className="text-left py-3 px-4 font-medium">Source</th>
                  <th className="text-left py-3 px-4 font-medium">Product</th>
                  <th className="text-left py-3 px-4 font-medium">Site</th>
                  <th className="text-left py-3 px-4 font-medium">Direction</th>
                  <th className="text-left py-3 px-4 font-medium">Adjustment</th>
                  <th className="text-left py-3 px-4 font-medium">Confidence</th>
                  <th className="text-left py-3 px-4 font-medium">Applied By</th>
                  <th className="text-left py-3 px-4 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {adjustments.map((adj) => (
                  <tr key={adj.id} className="border-b hover:bg-muted/50">
                    <td className="py-3 px-4 text-xs">
                      {adj.applied_at ? new Date(adj.applied_at).toLocaleString() : '—'}
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-1">
                        {getSourceIcon(adj.source)}
                        <span className="capitalize text-xs">{adj.source}</span>
                      </div>
                    </td>
                    <td className="py-3 px-4">{adj.product || '—'}</td>
                    <td className="py-3 px-4">{adj.site || '—'}</td>
                    <td className="py-3 px-4">
                      <DirectionIcon direction={adj.direction} />
                    </td>
                    <td className="py-3 px-4 font-mono">
                      {adj.adjustment_pct ? `${adj.adjustment_pct > 0 ? '+' : ''}${adj.adjustment_pct}%` : '—'}
                    </td>
                    <td className="py-3 px-4">
                      <ConfidenceBadge confidence={adj.confidence} />
                    </td>
                    <td className="py-3 px-4">
                      <Badge variant={adj.applied_by === 'auto' ? 'secondary' : 'outline'}>
                        {adj.applied_by || 'auto'}
                      </Badge>
                    </td>
                    <td className="py-3 px-4">
                      {!adj.reverted && (
                        <Button variant="ghost" size="sm" onClick={() => handleRevert(adj.id)} title="Revert adjustment">
                          <Undo2 className="h-4 w-4" />
                        </Button>
                      )}
                      {adj.reverted && (
                        <Badge variant="destructive" className="text-xs">Reverted</Badge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

// ============================================================================
// Main Component
// ============================================================================
const SignalIngestionDashboard = () => {
  const [currentTab, setCurrentTab] = useState('monitoring');
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    setLoading(true);
    try {
      const res = await signalApi.getDashboard();
      setDashboard(res.data);
      setError(null);
    } catch {
      setDashboard({});
      setError('Unable to load signal ingestion data.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Breadcrumbs */}
      <nav className="flex items-center gap-2 text-sm text-muted-foreground mb-4">
        <a href="/admin" className="hover:text-foreground">Administration</a>
        <ChevronRight className="h-4 w-4" />
        <span className="text-foreground">Signal Ingestion</span>
      </nav>

      {/* Title */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold flex items-center gap-3">
          <Zap className="h-7 w-7 text-yellow-500" />
          Signal Ingestion Dashboard
        </h1>
        <p className="text-muted-foreground mt-1">
          Monitor and manage supply chain signals captured from email, Slack, Teams, voice, and market data feeds.
          Signals are classified, confidence-scored, and routed to the ForecastAdjustmentTRM for evaluation.
        </p>
      </div>

      {error && (
        <Alert variant="warning" className="mb-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Tabs */}
      <Tabs value={currentTab} onValueChange={setCurrentTab}>
        <TabsList className="w-full justify-start border-b rounded-none h-auto p-0 mb-6">
          {tabItems.map((tab) => (
            <Tab
              key={tab.value}
              value={tab.value}
              className="flex items-center gap-2 rounded-none border-b-2 border-transparent data-[state=active]:border-primary px-4 py-3"
            >
              {tab.icon}
              {tab.label}
            </Tab>
          ))}
        </TabsList>

        {currentTab === 'monitoring' && (
          <MonitoringTab dashboard={dashboard} loading={loading} onRefresh={loadDashboard} />
        )}
        {currentTab === 'review' && <ReviewQueueTab />}
        {currentTab === 'sources' && <SourceReliabilityTab />}
        {currentTab === 'correlations' && <CorrelationsTab />}
        {currentTab === 'history' && <AdjustmentHistoryTab />}
      </Tabs>
    </div>
  );
};

export default SignalIngestionDashboard;
