import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, CardContent, CardTitle, Alert, Badge, Button, Spinner,
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
  Modal, ModalHeader, ModalTitle, ModalBody, ModalFooter,
  Input, Label, Textarea, NativeSelect, SelectOption, Text, H4, Progress,
  Collapsible, CollapsibleTrigger, CollapsibleContent,
} from '../common';
import {
  CheckCircle, XCircle, Edit3, HelpCircle, RefreshCw,
  ChevronDown, ChevronRight, BarChart3, Clock, ThumbsUp, AlertTriangle,
} from 'lucide-react';
import { api } from '../../services/api';

const REASON_CODES = [
  { value: 'MARKET_INTELLIGENCE', label: 'Market Intelligence' },
  { value: 'CUSTOMER_COMMITMENT', label: 'Customer Commitment' },
  { value: 'SUPPLY_DISRUPTION', label: 'Supply Disruption' },
  { value: 'REGULATORY_CHANGE', label: 'Regulatory Change' },
  { value: 'CAPACITY_CONSTRAINT', label: 'Capacity Constraint' },
  { value: 'COST_OPTIMIZATION', label: 'Cost Optimization' },
  { value: 'RISK_MITIGATION', label: 'Risk Mitigation' },
  { value: 'SEASONAL_PATTERN', label: 'Seasonal Pattern' },
  { value: 'QUALITY_CONCERN', label: 'Quality Concern' },
  { value: 'STRATEGIC_PRIORITY', label: 'Strategic Priority' },
  { value: 'HISTORICAL_PATTERN', label: 'Historical Pattern' },
  { value: 'OTHER', label: 'Other' },
];

const SCOPE_COLORS = {
  sop_policy: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
  execution_directive: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  allocation_refresh: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200',
};

const formatKeyValues = (values) => {
  if (!values || typeof values !== 'object') return '-';
  return Object.entries(values).slice(0, 3)
    .map(([k, v]) => `${k}: ${typeof v === 'number' ? v.toFixed(2) : v}`)
    .join(', ');
};

const ScopeBadge = ({ scope }) => (
  <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${SCOPE_COLORS[scope] || 'bg-gray-100 text-gray-800'}`}>
    {scope || '-'}
  </span>
);

const SummaryCard = ({ icon: Icon, iconBg, label, value, badge }) => (
  <Card className="p-4">
    <div className="flex items-center gap-3">
      <div className={`p-2 rounded-lg ${iconBg}`}><Icon className="h-5 w-5" /></div>
      <div>
        <Text className="text-sm text-muted-foreground">{label}</Text>
        <div className="flex items-center gap-2">
          <span className="text-2xl font-bold">{value}</span>
          {badge}
        </div>
      </div>
    </div>
  </Card>
);

const GNNDirectiveReview = () => {
  const [directives, setDirectives] = useState([]);
  const [pendingCount, setPendingCount] = useState(0);
  const [effectiveness, setEffectiveness] = useState(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(null);
  const [selectedDirective, setSelectedDirective] = useState(null);
  const [overrideModal, setOverrideModal] = useState(false);
  const [askWhyData, setAskWhyData] = useState({});
  const [expandedAskWhy, setExpandedAskWhy] = useState({});
  const [overrideForm, setOverrideForm] = useState({ values: {}, reason_code: '', reason_text: '' });
  const [error, setError] = useState(null);
  const [effectivenessOpen, setEffectivenessOpen] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [allRes, pendingRes, effRes] = await Promise.all([
        api.get('/site-agent/gnn/directives'),
        api.get('/site-agent/gnn/directives', { params: { status: 'PROPOSED' } }),
        api.get('/site-agent/gnn/override-effectiveness'),
      ]);
      setDirectives(allRes.data || []);
      setPendingCount(Array.isArray(pendingRes.data) ? pendingRes.data.length : 0);
      setEffectiveness(effRes.data || null);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load directives');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const pendingDirectives = directives.filter((d) => d.status === 'PROPOSED');
  const acceptedCount = directives.filter((d) => d.status === 'ACCEPTED').length;
  const overriddenCount = directives.filter((d) => d.status === 'OVERRIDDEN').length;
  const beneficialRate = effectiveness?.beneficial_rate;

  const handleReview = async (directive, action) => {
    setActionLoading(directive.id);
    try {
      await api.post(`/site-agent/gnn/directives/${directive.id}/review`, {
        action, override_values: null, reason_code: null, reason_text: null,
      });
      await fetchData();
    } catch (err) {
      setError(err.response?.data?.detail || `Failed to ${action.toLowerCase()} directive`);
    } finally { setActionLoading(null); }
  };

  const handleOverrideOpen = (directive) => {
    setSelectedDirective(directive);
    setOverrideForm({ values: { ...(directive.proposed_values || {}) }, reason_code: '', reason_text: '' });
    setOverrideModal(true);
  };

  const handleOverrideSubmit = async () => {
    if (!selectedDirective) return;
    setActionLoading(selectedDirective.id);
    try {
      await api.post(`/site-agent/gnn/directives/${selectedDirective.id}/review`, {
        action: 'OVERRIDDEN',
        override_values: overrideForm.values,
        reason_code: overrideForm.reason_code,
        reason_text: overrideForm.reason_text,
      });
      setOverrideModal(false);
      setSelectedDirective(null);
      await fetchData();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to submit override');
    } finally { setActionLoading(null); }
  };

  const handleAskWhy = async (directive) => {
    const id = directive.id;
    if (expandedAskWhy[id]) { setExpandedAskWhy((p) => ({ ...p, [id]: false })); return; }
    if (askWhyData[id]) { setExpandedAskWhy((p) => ({ ...p, [id]: true })); return; }
    setActionLoading(id);
    try {
      const res = await api.get(`/site-agent/gnn/directives/${id}/ask-why`);
      setAskWhyData((p) => ({ ...p, [id]: res.data }));
      setExpandedAskWhy((p) => ({ ...p, [id]: true }));
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load explanation');
    } finally { setActionLoading(null); }
  };

  const overrideHasChanges = () => {
    if (!selectedDirective) return false;
    const proposed = selectedDirective.proposed_values || {};
    return Object.keys(overrideForm.values).some((k) => String(overrideForm.values[k]) !== String(proposed[k]));
  };
  const overrideCanSubmit = overrideForm.reason_code && overrideHasChanges();

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Spinner size="lg" />
        <Text className="ml-3 text-muted-foreground">Loading directives...</Text>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <H4>GNN Directive Review</H4>
          <Text className="text-muted-foreground">Review and act on GNN-generated site directives</Text>
        </div>
        <Button variant="outline" onClick={fetchData} disabled={loading} leftIcon={<RefreshCw className="h-4 w-4" />}>
          Refresh
        </Button>
      </div>

      {error && <Alert variant="error" onClose={() => setError(null)}>{error}</Alert>}

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <SummaryCard icon={Clock} iconBg="bg-amber-100 dark:bg-amber-900 text-amber-600 dark:text-amber-400" label="Pending Review" value={pendingCount}
          badge={pendingCount > 0 ? <Badge variant="warning" size="sm">Action Needed</Badge> : null} />
        <SummaryCard icon={CheckCircle} iconBg="bg-emerald-100 dark:bg-emerald-900 text-emerald-600 dark:text-emerald-400" label="Accepted" value={acceptedCount} />
        <SummaryCard icon={Edit3} iconBg="bg-blue-100 dark:bg-blue-900 text-blue-600 dark:text-blue-400" label="Overridden" value={overriddenCount} />
        <SummaryCard icon={BarChart3} iconBg="bg-violet-100 dark:bg-violet-900 text-violet-600 dark:text-violet-400" label="Override Effectiveness"
          value={beneficialRate != null ? `${Math.round(beneficialRate)}%` : '-'}
          badge={beneficialRate != null ? (
            <Badge variant={beneficialRate >= 70 ? 'success' : beneficialRate >= 40 ? 'warning' : 'destructive'} size="sm">
              {beneficialRate >= 70 ? 'Good' : beneficialRate >= 40 ? 'Mixed' : 'Low'}
            </Badge>
          ) : null} />
      </div>

      {/* Pending Directives Table */}
      <Card>
        <CardContent className="p-6">
          <CardTitle as="h5" className="text-lg mb-4">Pending Directives ({pendingDirectives.length})</CardTitle>
          {pendingDirectives.length === 0 ? (
            <Alert variant="info">No pending directives to review.</Alert>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Site</TableHead>
                    <TableHead>Scope</TableHead>
                    <TableHead>Model</TableHead>
                    <TableHead>Confidence</TableHead>
                    <TableHead>Key Values</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {pendingDirectives.map((d) => (
                    <React.Fragment key={d.id}>
                      <TableRow>
                        <TableCell className="font-medium">{d.site_key || d.site_id || '-'}</TableCell>
                        <TableCell><ScopeBadge scope={d.scope} /></TableCell>
                        <TableCell className="text-sm text-muted-foreground">{d.model_version || d.model || '-'}</TableCell>
                        <TableCell>
                          {d.confidence != null ? (
                            <div className="flex items-center gap-2 min-w-[100px]">
                              <Progress value={d.confidence * 100} size="sm" className="flex-1" />
                              <span className="text-xs text-muted-foreground w-10 text-right">{(d.confidence * 100).toFixed(0)}%</span>
                            </div>
                          ) : '-'}
                        </TableCell>
                        <TableCell className="text-sm max-w-[250px] truncate">{formatKeyValues(d.proposed_values)}</TableCell>
                        <TableCell><Badge variant="warning" size="sm">PROPOSED</Badge></TableCell>
                        <TableCell>
                          <div className="flex items-center justify-end gap-1">
                            <Button size="sm" variant="outline" onClick={() => handleReview(d, 'ACCEPTED')} disabled={actionLoading === d.id}
                              className="text-emerald-600 border-emerald-300 hover:bg-emerald-50 dark:hover:bg-emerald-950">
                              <CheckCircle className="h-3.5 w-3.5 mr-1" />Accept
                            </Button>
                            <Button size="sm" variant="outline" onClick={() => handleOverrideOpen(d)} disabled={actionLoading === d.id}
                              className="text-amber-600 border-amber-300 hover:bg-amber-50 dark:hover:bg-amber-950">
                              <Edit3 className="h-3.5 w-3.5 mr-1" />Override
                            </Button>
                            <Button size="sm" variant="outline" onClick={() => handleReview(d, 'REJECTED')} disabled={actionLoading === d.id}
                              className="text-red-600 border-red-300 hover:bg-red-50 dark:hover:bg-red-950">
                              <XCircle className="h-3.5 w-3.5 mr-1" />Reject
                            </Button>
                            <Button size="sm" variant="ghost" onClick={() => handleAskWhy(d)} disabled={actionLoading === d.id}>
                              <HelpCircle className="h-3.5 w-3.5 mr-1" />Ask Why
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                      {/* Ask Why Expanded Panel */}
                      {expandedAskWhy[d.id] && askWhyData[d.id] && (
                        <TableRow>
                          <TableCell colSpan={7} className="bg-muted/30 p-4">
                            <div className="space-y-3">
                              <Text className="font-semibold text-sm">Explanation</Text>
                              {askWhyData[d.id].reasoning?.length > 0 ? (
                                <ul className="space-y-2">
                                  {askWhyData[d.id].reasoning.map((r, i) => (
                                    <li key={i} className="text-sm">
                                      <span className="font-medium">{r.factor}:</span>{' '}
                                      <span className="text-muted-foreground">{r.detail}</span>
                                    </li>
                                  ))}
                                </ul>
                              ) : <Text className="text-sm text-muted-foreground">No reasoning available.</Text>}
                              {askWhyData[d.id].confidence != null && (
                                <div className="flex items-center gap-2 mt-2">
                                  <Text className="text-sm font-medium">Model Confidence:</Text>
                                  <Progress value={askWhyData[d.id].confidence * 100} size="sm" className="w-40" />
                                  <span className="text-sm text-muted-foreground">{(askWhyData[d.id].confidence * 100).toFixed(1)}%</span>
                                </div>
                              )}
                              {askWhyData[d.id].outcome && (
                                <div className="mt-2 p-3 rounded bg-muted/50">
                                  <Text className="text-sm font-medium mb-1">Outcome Data</Text>
                                  <div className="flex gap-4 text-sm">
                                    <span>Override Delta: <strong>{askWhyData[d.id].outcome.override_delta ?? '-'}</strong></span>
                                    <span>Classification:{' '}
                                      <Badge size="sm" variant={
                                        askWhyData[d.id].outcome.classification === 'beneficial' ? 'success'
                                        : askWhyData[d.id].outcome.classification === 'detrimental' ? 'destructive' : 'secondary'
                                      }>{askWhyData[d.id].outcome.classification || '-'}</Badge>
                                    </span>
                                  </div>
                                </div>
                              )}
                            </div>
                          </TableCell>
                        </TableRow>
                      )}
                    </React.Fragment>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Override Effectiveness Section */}
      <Collapsible open={effectivenessOpen} onOpenChange={setEffectivenessOpen}>
        <Card>
          <CardContent className="p-6">
            <CollapsibleTrigger className="flex items-center justify-between w-full">
              <CardTitle as="h5" className="text-lg">Override Effectiveness</CardTitle>
              {effectivenessOpen
                ? <ChevronDown className="h-5 w-5 text-muted-foreground" />
                : <ChevronRight className="h-5 w-5 text-muted-foreground" />}
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div className="mt-4 space-y-4">
                {effectiveness?.by_scope && Object.keys(effectiveness.by_scope).length > 0 ? (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Scope</TableHead>
                        <TableHead className="text-right">Overrides</TableHead>
                        <TableHead className="text-right">Beneficial</TableHead>
                        <TableHead className="text-right">Neutral</TableHead>
                        <TableHead className="text-right">Detrimental</TableHead>
                        <TableHead className="text-right">Rate</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {Object.entries(effectiveness.by_scope).map(([scope, data]) => (
                        <TableRow key={scope}>
                          <TableCell><ScopeBadge scope={scope} /></TableCell>
                          <TableCell className="text-right">{data.total ?? '-'}</TableCell>
                          <TableCell className="text-right text-emerald-600">{data.beneficial ?? '-'}</TableCell>
                          <TableCell className="text-right text-muted-foreground">{data.neutral ?? '-'}</TableCell>
                          <TableCell className="text-right text-red-600">{data.detrimental ?? '-'}</TableCell>
                          <TableCell className="text-right font-medium">{data.rate != null ? `${Math.round(data.rate)}%` : '-'}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : <Alert variant="info">No override effectiveness data available yet.</Alert>}
                {effectiveness?.by_status && (
                  <div>
                    <Text className="text-sm font-medium mb-2">Status Summary</Text>
                    <div className="flex flex-wrap gap-3">
                      {Object.entries(effectiveness.by_status).map(([status, count]) => (
                        <div key={status} className="flex items-center gap-1.5 text-sm">
                          <Badge size="sm" variant={
                            status === 'PROPOSED' ? 'warning' : status === 'ACCEPTED' ? 'success'
                            : status === 'OVERRIDDEN' ? 'info' : status === 'REJECTED' ? 'destructive' : 'secondary'
                          }>{status}</Badge>
                          <span className="font-medium">{count}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </CollapsibleContent>
          </CardContent>
        </Card>
      </Collapsible>

      {/* Override Modal */}
      <Modal isOpen={overrideModal} onClose={() => setOverrideModal(false)} size="lg">
        <ModalHeader><ModalTitle>Override Directive</ModalTitle></ModalHeader>
        <ModalBody>
          {selectedDirective && (
            <div className="space-y-4">
              <div className="flex gap-4 text-sm">
                <span><strong>Site:</strong> {selectedDirective.site_key || selectedDirective.site_id}</span>
                <span><strong>Scope:</strong> {selectedDirective.scope}</span>
              </div>
              <div>
                <Label className="mb-2 block">Override Values</Label>
                <div className="space-y-2 max-h-60 overflow-y-auto">
                  {Object.entries(overrideForm.values).map(([key, value]) => (
                    <div key={key} className="flex items-center gap-3">
                      <Label className="w-1/3 text-sm text-right truncate">{key}</Label>
                      <Input className="flex-1" value={value ?? ''} onChange={(e) =>
                        setOverrideForm((p) => ({ ...p, values: { ...p.values, [key]: e.target.value } }))} />
                    </div>
                  ))}
                  {Object.keys(overrideForm.values).length === 0 && (
                    <Text className="text-sm text-muted-foreground">No proposed values to edit.</Text>
                  )}
                </div>
              </div>
              <div>
                <Label className="mb-1 block">Reason Code *</Label>
                <NativeSelect value={overrideForm.reason_code} onChange={(e) => setOverrideForm((p) => ({ ...p, reason_code: e.target.value }))}>
                  <SelectOption value="">Select a reason...</SelectOption>
                  {REASON_CODES.map((rc) => <SelectOption key={rc.value} value={rc.value}>{rc.label}</SelectOption>)}
                </NativeSelect>
              </div>
              <div>
                <Label className="mb-1 block">Reason Details</Label>
                <Textarea value={overrideForm.reason_text} rows={3} placeholder="Explain the override rationale..."
                  onChange={(e) => setOverrideForm((p) => ({ ...p, reason_text: e.target.value }))} />
              </div>
              {!overrideCanSubmit && overrideForm.reason_code && (
                <Alert variant="warning">
                  <AlertTriangle className="h-4 w-4 inline mr-1" />Change at least one value to submit an override.
                </Alert>
              )}
            </div>
          )}
        </ModalBody>
        <ModalFooter className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => setOverrideModal(false)}>Cancel</Button>
          <Button onClick={handleOverrideSubmit} disabled={!overrideCanSubmit || actionLoading === selectedDirective?.id}>
            {actionLoading === selectedDirective?.id
              ? <Spinner size="sm" className="mr-2" />
              : <ThumbsUp className="h-4 w-4 mr-2" />}
            Submit Override
          </Button>
        </ModalFooter>
      </Modal>
    </div>
  );
};

export default GNNDirectiveReview;
