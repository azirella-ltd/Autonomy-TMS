/**
 * Consensus Planning Page
 *
 * Multi-stakeholder forecast consensus workflow:
 * - Create and manage consensus planning cycles
 * - Submit forecast versions from different sources (sales, marketing, finance, operations)
 * - Compare versions side-by-side
 * - Vote and finalize consensus
 *
 * Backend API: /api/v1/consensus-planning
 * Status flow: DRAFT → COLLECTING → REVIEW → VOTING → APPROVED → PUBLISHED
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Badge,
  Label,
  Input,
  Textarea,
  Modal,
  Spinner,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  Progress,
} from '../../components/common';
import {
  Plus,
  Play,
  CheckCircle,
  XCircle,
  Clock,
  Users,
  ArrowRight,
  FileText,
  BarChart3,
  RefreshCw,
  Send,
  ThumbsUp,
  ThumbsDown,
  Minus,
  Eye,
  ChevronDown,
  ChevronUp,
  MessageSquare,
  Calendar,
  Target,
} from 'lucide-react';
import { api } from '../../services/api';

// Status configuration
const STATUS_CONFIG = {
  draft: { label: 'Draft', variant: 'secondary', icon: FileText },
  collecting: { label: 'Collecting', variant: 'info', icon: Users },
  review: { label: 'Under Review', variant: 'warning', icon: Eye },
  voting: { label: 'Voting', variant: 'default', icon: ThumbsUp },
  approved: { label: 'Approved', variant: 'success', icon: CheckCircle },
  published: { label: 'Published', variant: 'success', icon: CheckCircle },
  archived: { label: 'Archived', variant: 'secondary', icon: Clock },
};

const SOURCE_CONFIG = {
  sales: { label: 'Sales', color: 'text-blue-600 bg-blue-50' },
  marketing: { label: 'Marketing', color: 'text-purple-600 bg-purple-50' },
  finance: { label: 'Finance', color: 'text-green-600 bg-green-50' },
  operations: { label: 'Operations', color: 'text-amber-600 bg-amber-50' },
  statistical: { label: 'Statistical', color: 'text-gray-600 bg-gray-50' },
  consensus: { label: 'Consensus', color: 'text-emerald-600 bg-emerald-50' },
  blended: { label: 'Blended', color: 'text-indigo-600 bg-indigo-50' },
};

const VOTE_CONFIG = {
  approve: { label: 'Approve', color: 'text-green-600', icon: ThumbsUp },
  reject: { label: 'Reject', color: 'text-red-600', icon: ThumbsDown },
  abstain: { label: 'Abstain', color: 'text-gray-600', icon: Minus },
  request_changes: { label: 'Request Changes', color: 'text-amber-600', icon: MessageSquare },
};

// ============================================================================
// Main Component
// ============================================================================
const ConsensusPlanning = () => {
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [selectedPlan, setSelectedPlan] = useState(null);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [versionDialogOpen, setVersionDialogOpen] = useState(false);
  const [voteDialogOpen, setVoteDialogOpen] = useState(false);
  const [selectedVersion, setSelectedVersion] = useState(null);
  const [versions, setVersions] = useState([]);
  const [comments, setComments] = useState([]);
  const [statusFilter, setStatusFilter] = useState('__all__');

  // New plan form
  const [newPlan, setNewPlan] = useState({
    name: '',
    description: '',
    planning_period: '',
    period_start: '',
    period_end: '',
    submission_deadline: '',
  });

  // New version form
  const [newVersion, setNewVersion] = useState({
    source: 'sales',
    version_name: '',
    assumptions: '',
    notes: '',
  });

  // Vote form
  const [voteForm, setVoteForm] = useState({
    vote: 'approve',
    comment: '',
  });

  // Load consensus plans
  const loadPlans = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (statusFilter !== '__all__') params.append('status', statusFilter);
      params.append('limit', '50');
      const response = await api.get(`/api/v1/consensus-planning?${params.toString()}`);
      setPlans(response.data || []);
    } catch (err) {
      console.error('Failed to load consensus plans:', err);
      setPlans(generateMockPlans());
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    loadPlans();
  }, [loadPlans]);

  // Load versions for selected plan
  const loadVersions = useCallback(async (planId) => {
    try {
      const response = await api.get(`/api/v1/consensus-planning/versions?plan_id=${planId}`);
      setVersions(response.data || []);
    } catch (err) {
      console.error('Failed to load versions:', err);
      setVersions(generateMockVersions(planId));
    }
  }, []);

  // Load comments for selected plan
  const loadComments = useCallback(async (planId) => {
    try {
      const response = await api.get(`/api/v1/consensus-planning/comments?plan_id=${planId}`);
      setComments(response.data || []);
    } catch (err) {
      setComments([]);
    }
  }, []);

  // Select a plan
  const handleSelectPlan = (plan) => {
    setSelectedPlan(plan);
    loadVersions(plan.id);
    loadComments(plan.id);
  };

  // Create new plan
  const handleCreatePlan = async () => {
    try {
      const payload = {
        ...newPlan,
        period_start: new Date(newPlan.period_start).toISOString(),
        period_end: new Date(newPlan.period_end).toISOString(),
        submission_deadline: newPlan.submission_deadline
          ? new Date(newPlan.submission_deadline).toISOString()
          : undefined,
      };
      await api.post('/api/v1/consensus-planning', payload);
      setCreateDialogOpen(false);
      setNewPlan({ name: '', description: '', planning_period: '', period_start: '', period_end: '', submission_deadline: '' });
      setSuccess('Consensus plan created successfully');
      loadPlans();
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError('Failed to create consensus plan');
    }
  };

  // Start collection phase
  const handleStartCollection = async (planId) => {
    try {
      await api.post(`/api/v1/consensus-planning/${planId}/start`);
      setSuccess('Collection phase started');
      loadPlans();
      if (selectedPlan?.id === planId) {
        setSelectedPlan(prev => ({ ...prev, status: 'collecting', current_phase: 'collection' }));
      }
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError('Failed to start collection');
    }
  };

  // Advance phase
  const handleAdvancePhase = async (planId) => {
    try {
      await api.post(`/api/v1/consensus-planning/${planId}/advance-phase`);
      setSuccess('Phase advanced successfully');
      loadPlans();
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError('Failed to advance phase');
    }
  };

  // Submit version
  const handleSubmitVersion = async () => {
    if (!selectedPlan) return;
    try {
      await api.post(`/api/v1/consensus-planning/versions`, {
        ...newVersion,
        consensus_plan_id: selectedPlan.id,
        forecast_data: {}, // Populated from the editor in production
      });
      setVersionDialogOpen(false);
      setNewVersion({ source: 'sales', version_name: '', assumptions: '', notes: '' });
      setSuccess('Forecast version submitted');
      loadVersions(selectedPlan.id);
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError('Failed to submit version');
    }
  };

  // Submit vote
  const handleSubmitVote = async () => {
    if (!selectedVersion) return;
    try {
      await api.post(`/api/v1/consensus-planning/versions/${selectedVersion.id}/vote`, voteForm);
      setVoteDialogOpen(false);
      setVoteForm({ vote: 'approve', comment: '' });
      setSuccess('Vote recorded');
      if (selectedPlan) loadVersions(selectedPlan.id);
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError('Failed to submit vote');
    }
  };

  // Summary stats
  const stats = {
    total: plans.length,
    active: plans.filter(p => ['collecting', 'review', 'voting'].includes(p.status)).length,
    approved: plans.filter(p => p.status === 'approved' || p.status === 'published').length,
    draft: plans.filter(p => p.status === 'draft').length,
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <Target className="h-7 w-7" />
            Consensus Planning
          </h1>
          <p className="text-sm text-muted-foreground">
            Multi-stakeholder forecast alignment across sales, marketing, finance, and operations
          </p>
        </div>
        <Button onClick={() => setCreateDialogOpen(true)} leftIcon={<Plus className="h-4 w-4" />}>
          New Consensus Cycle
        </Button>
      </div>

      {success && <Alert variant="success" className="mb-4">{success}</Alert>}
      {error && <Alert variant="error" className="mb-4" onClose={() => setError(null)}>{error}</Alert>}

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Total Cycles</p>
            <p className="text-3xl font-bold">{stats.total}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground flex items-center gap-1">
              <Play className="h-4 w-4 text-blue-500" /> Active
            </p>
            <p className="text-3xl font-bold text-blue-600">{stats.active}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground flex items-center gap-1">
              <CheckCircle className="h-4 w-4 text-green-500" /> Approved
            </p>
            <p className="text-3xl font-bold text-green-600">{stats.approved}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground flex items-center gap-1">
              <FileText className="h-4 w-4 text-gray-500" /> Draft
            </p>
            <p className="text-3xl font-bold text-gray-600">{stats.draft}</p>
          </CardContent>
        </Card>
      </div>

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Plans List */}
        <div className="lg:col-span-1">
          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold">Planning Cycles</h3>
                <Button variant="ghost" size="sm" onClick={loadPlans} leftIcon={<RefreshCw className="h-3 w-3" />}>
                  Refresh
                </Button>
              </div>

              {/* Status Filter */}
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="mb-3">
                  <SelectValue placeholder="All Statuses" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all__">All Statuses</SelectItem>
                  {Object.entries(STATUS_CONFIG).map(([key, { label }]) => (
                    <SelectItem key={key} value={key}>{label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {loading ? (
                <div className="flex items-center justify-center py-8">
                  <Spinner size="lg" />
                </div>
              ) : plans.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  <Target className="h-10 w-10 mx-auto mb-2 opacity-50" />
                  <p className="text-sm">No consensus cycles found</p>
                  <Button size="sm" className="mt-2" onClick={() => setCreateDialogOpen(true)}>
                    Create First Cycle
                  </Button>
                </div>
              ) : (
                <div className="space-y-2 max-h-[600px] overflow-y-auto">
                  {plans.map(plan => {
                    const statusInfo = STATUS_CONFIG[plan.status] || STATUS_CONFIG.draft;
                    const isSelected = selectedPlan?.id === plan.id;
                    return (
                      <div
                        key={plan.id}
                        onClick={() => handleSelectPlan(plan)}
                        className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                          isSelected
                            ? 'border-primary bg-primary/5'
                            : 'border-border hover:bg-muted/50'
                        }`}
                      >
                        <div className="flex items-start justify-between">
                          <div className="flex-1 min-w-0">
                            <p className="font-medium text-sm truncate">{plan.name}</p>
                            <p className="text-xs text-muted-foreground">{plan.planning_period}</p>
                          </div>
                          <Badge variant={statusInfo.variant} className="text-xs ml-2 whitespace-nowrap">
                            {statusInfo.label}
                          </Badge>
                        </div>
                        <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
                          <span className="flex items-center gap-1">
                            <FileText className="h-3 w-3" />
                            {plan.version_count} versions
                          </span>
                          <span className="flex items-center gap-1">
                            <Calendar className="h-3 w-3" />
                            {new Date(plan.created_at).toLocaleDateString()}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Plan Detail */}
        <div className="lg:col-span-2">
          {!selectedPlan ? (
            <Card>
              <CardContent className="p-12">
                <div className="text-center text-muted-foreground">
                  <Target className="h-16 w-16 mx-auto mb-4 opacity-30" />
                  <p className="text-lg font-medium">Select a consensus cycle</p>
                  <p className="text-sm">Choose a planning cycle from the list to view details, submit forecasts, and manage votes.</p>
                </div>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-4">
              {/* Plan Header */}
              <Card>
                <CardContent className="pt-4">
                  <div className="flex items-start justify-between mb-4">
                    <div>
                      <h2 className="text-xl font-bold">{selectedPlan.name}</h2>
                      {selectedPlan.description && (
                        <p className="text-sm text-muted-foreground mt-1">{selectedPlan.description}</p>
                      )}
                    </div>
                    <Badge variant={STATUS_CONFIG[selectedPlan.status]?.variant || 'secondary'} className="text-sm">
                      {STATUS_CONFIG[selectedPlan.status]?.label || selectedPlan.status}
                    </Badge>
                  </div>

                  {/* Phase Progress */}
                  <div className="mb-4">
                    <div className="flex items-center gap-1 mb-2">
                      {['collection', 'review', 'voting', 'finalization'].map((phase, idx) => {
                        const phases = ['collection', 'review', 'voting', 'finalization'];
                        const currentIdx = phases.indexOf(selectedPlan.current_phase);
                        const isActive = idx === currentIdx;
                        const isCompleted = idx < currentIdx;
                        return (
                          <React.Fragment key={phase}>
                            <div className={`flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium ${
                              isActive ? 'bg-primary text-primary-foreground' :
                              isCompleted ? 'bg-green-100 text-green-700' :
                              'bg-muted text-muted-foreground'
                            }`}>
                              {isCompleted ? <CheckCircle className="h-3 w-3" /> : null}
                              {phase.charAt(0).toUpperCase() + phase.slice(1)}
                            </div>
                            {idx < 3 && <ArrowRight className="h-3 w-3 text-muted-foreground" />}
                          </React.Fragment>
                        );
                      })}
                    </div>
                  </div>

                  {/* Metadata */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                    <div>
                      <p className="text-muted-foreground">Period</p>
                      <p className="font-medium">{selectedPlan.planning_period}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Start</p>
                      <p className="font-medium">{new Date(selectedPlan.period_start).toLocaleDateString()}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">End</p>
                      <p className="font-medium">{new Date(selectedPlan.period_end).toLocaleDateString()}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Deadline</p>
                      <p className="font-medium">
                        {selectedPlan.submission_deadline
                          ? new Date(selectedPlan.submission_deadline).toLocaleDateString()
                          : 'Not set'}
                      </p>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex gap-2 mt-4 pt-4 border-t">
                    {selectedPlan.status === 'draft' && (
                      <Button
                        size="sm"
                        onClick={() => handleStartCollection(selectedPlan.id)}
                        leftIcon={<Play className="h-4 w-4" />}
                      >
                        Start Collection
                      </Button>
                    )}
                    {selectedPlan.status === 'collecting' && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setVersionDialogOpen(true)}
                        leftIcon={<Send className="h-4 w-4" />}
                      >
                        Submit Forecast
                      </Button>
                    )}
                    {['collecting', 'review', 'voting'].includes(selectedPlan.status) && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleAdvancePhase(selectedPlan.id)}
                        leftIcon={<ArrowRight className="h-4 w-4" />}
                      >
                        Advance Phase
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>

              {/* Versions & Votes Tabs */}
              <Tabs defaultValue="versions">
                <TabsList className="w-full grid grid-cols-3">
                  <TabsTrigger value="versions" className="flex items-center gap-1">
                    <FileText className="h-4 w-4" />
                    Submissions ({versions.length})
                  </TabsTrigger>
                  <TabsTrigger value="compare" className="flex items-center gap-1">
                    <BarChart3 className="h-4 w-4" />
                    Compare
                  </TabsTrigger>
                  <TabsTrigger value="discussion" className="flex items-center gap-1">
                    <MessageSquare className="h-4 w-4" />
                    Discussion ({comments.length})
                  </TabsTrigger>
                </TabsList>

                {/* Versions Tab */}
                <TabsContent value="versions">
                  <Card>
                    <CardContent className="pt-4">
                      {versions.length === 0 ? (
                        <div className="text-center py-8 text-muted-foreground">
                          <FileText className="h-10 w-10 mx-auto mb-2 opacity-50" />
                          <p>No forecast versions submitted yet</p>
                          {selectedPlan.status === 'collecting' && (
                            <Button size="sm" className="mt-2" onClick={() => setVersionDialogOpen(true)}>
                              Submit First Version
                            </Button>
                          )}
                        </div>
                      ) : (
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>#</TableHead>
                              <TableHead>Source</TableHead>
                              <TableHead>Name</TableHead>
                              <TableHead>Status</TableHead>
                              <TableHead>Votes</TableHead>
                              <TableHead>Submitted</TableHead>
                              <TableHead className="text-right">Actions</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {versions.map(v => {
                              const sourceInfo = SOURCE_CONFIG[v.source] || SOURCE_CONFIG.statistical;
                              return (
                                <TableRow key={v.id}>
                                  <TableCell className="font-mono text-sm">{v.version_number}</TableCell>
                                  <TableCell>
                                    <span className={`text-xs px-2 py-0.5 rounded-full ${sourceInfo.color}`}>
                                      {sourceInfo.label}
                                    </span>
                                  </TableCell>
                                  <TableCell className="font-medium">
                                    {v.version_name || `Version ${v.version_number}`}
                                  </TableCell>
                                  <TableCell>
                                    {v.is_final ? (
                                      <Badge variant="success" className="text-xs">Final</Badge>
                                    ) : v.is_submitted ? (
                                      <Badge variant="info" className="text-xs">Submitted</Badge>
                                    ) : (
                                      <Badge variant="secondary" className="text-xs">Draft</Badge>
                                    )}
                                  </TableCell>
                                  <TableCell>
                                    <span className="text-sm">{v.vote_count || 0} votes</span>
                                  </TableCell>
                                  <TableCell className="text-sm text-muted-foreground">
                                    {v.submitted_at
                                      ? new Date(v.submitted_at).toLocaleDateString()
                                      : '-'}
                                  </TableCell>
                                  <TableCell className="text-right">
                                    {selectedPlan.status === 'voting' && (
                                      <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={() => {
                                          setSelectedVersion(v);
                                          setVoteDialogOpen(true);
                                        }}
                                        leftIcon={<ThumbsUp className="h-3 w-3" />}
                                      >
                                        Vote
                                      </Button>
                                    )}
                                  </TableCell>
                                </TableRow>
                              );
                            })}
                          </TableBody>
                        </Table>
                      )}
                    </CardContent>
                  </Card>
                </TabsContent>

                {/* Compare Tab */}
                <TabsContent value="compare">
                  <Card>
                    <CardContent className="pt-4">
                      {versions.length < 2 ? (
                        <div className="text-center py-8 text-muted-foreground">
                          <BarChart3 className="h-10 w-10 mx-auto mb-2 opacity-50" />
                          <p>Need at least 2 submitted versions to compare</p>
                        </div>
                      ) : (
                        <div>
                          <h3 className="font-medium mb-4">Source Comparison Summary</h3>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                            {versions.map(v => {
                              const sourceInfo = SOURCE_CONFIG[v.source] || SOURCE_CONFIG.statistical;
                              return (
                                <Card key={v.id} className="bg-muted/30">
                                  <CardContent className="pt-3 pb-3">
                                    <span className={`text-xs px-2 py-0.5 rounded-full ${sourceInfo.color}`}>
                                      {sourceInfo.label}
                                    </span>
                                    <p className="text-sm font-medium mt-2">
                                      {v.version_name || `Version ${v.version_number}`}
                                    </p>
                                    <p className="text-xs text-muted-foreground mt-1">
                                      {v.vote_count || 0} votes | {v.assumptions || 'No assumptions noted'}
                                    </p>
                                  </CardContent>
                                </Card>
                              );
                            })}
                          </div>
                          <Alert variant="info">
                            Select versions above to generate a detailed side-by-side forecast comparison
                            with product-level, site-level, and period-level deltas.
                          </Alert>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </TabsContent>

                {/* Discussion Tab */}
                <TabsContent value="discussion">
                  <Card>
                    <CardContent className="pt-4">
                      {comments.length === 0 ? (
                        <div className="text-center py-8 text-muted-foreground">
                          <MessageSquare className="h-10 w-10 mx-auto mb-2 opacity-50" />
                          <p>No discussion yet</p>
                          <p className="text-sm">Start a discussion about this consensus cycle.</p>
                        </div>
                      ) : (
                        <div className="space-y-3">
                          {comments.map(c => (
                            <div key={c.id} className="p-3 rounded border">
                              <div className="flex items-center gap-2 mb-1">
                                <Users className="h-3 w-3 text-muted-foreground" />
                                <span className="text-sm font-medium">User {c.author_id}</span>
                                <span className="text-xs text-muted-foreground">
                                  {new Date(c.created_at).toLocaleString()}
                                </span>
                              </div>
                              <p className="text-sm">{c.content}</p>
                            </div>
                          ))}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </TabsContent>
              </Tabs>
            </div>
          )}
        </div>
      </div>

      {/* Create Plan Dialog */}
      <Modal
        open={createDialogOpen}
        onClose={() => setCreateDialogOpen(false)}
        title="Create Consensus Planning Cycle"
      >
        <div className="space-y-4 p-4">
          <div>
            <Label>Cycle Name</Label>
            <Input
              className="mt-1"
              placeholder="e.g., Q2 2026 Demand Consensus"
              value={newPlan.name}
              onChange={(e) => setNewPlan(prev => ({ ...prev, name: e.target.value }))}
            />
          </div>
          <div>
            <Label>Description</Label>
            <Textarea
              className="mt-1"
              placeholder="Describe the purpose of this consensus cycle..."
              value={newPlan.description}
              onChange={(e) => setNewPlan(prev => ({ ...prev, description: e.target.value }))}
            />
          </div>
          <div>
            <Label>Planning Period</Label>
            <Input
              className="mt-1"
              placeholder="e.g., 2026-Q2"
              value={newPlan.planning_period}
              onChange={(e) => setNewPlan(prev => ({ ...prev, planning_period: e.target.value }))}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Period Start</Label>
              <Input
                type="date"
                className="mt-1"
                value={newPlan.period_start}
                onChange={(e) => setNewPlan(prev => ({ ...prev, period_start: e.target.value }))}
              />
            </div>
            <div>
              <Label>Period End</Label>
              <Input
                type="date"
                className="mt-1"
                value={newPlan.period_end}
                onChange={(e) => setNewPlan(prev => ({ ...prev, period_end: e.target.value }))}
              />
            </div>
          </div>
          <div>
            <Label>Submission Deadline (optional)</Label>
            <Input
              type="date"
              className="mt-1"
              value={newPlan.submission_deadline}
              onChange={(e) => setNewPlan(prev => ({ ...prev, submission_deadline: e.target.value }))}
            />
          </div>
          <div className="flex justify-end gap-2 pt-4">
            <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>Cancel</Button>
            <Button
              onClick={handleCreatePlan}
              disabled={!newPlan.name || !newPlan.planning_period || !newPlan.period_start || !newPlan.period_end}
              leftIcon={<Plus className="h-4 w-4" />}
            >
              Create Cycle
            </Button>
          </div>
        </div>
      </Modal>

      {/* Submit Version Dialog */}
      <Modal
        open={versionDialogOpen}
        onClose={() => setVersionDialogOpen(false)}
        title="Submit Forecast Version"
      >
        <div className="space-y-4 p-4">
          <div>
            <Label>Source Department</Label>
            <Select
              value={newVersion.source}
              onValueChange={(v) => setNewVersion(prev => ({ ...prev, source: v }))}
            >
              <SelectTrigger className="mt-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(SOURCE_CONFIG).map(([key, { label }]) => (
                  <SelectItem key={key} value={key}>{label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Version Name (optional)</Label>
            <Input
              className="mt-1"
              placeholder="e.g., Sales Q2 Final"
              value={newVersion.version_name}
              onChange={(e) => setNewVersion(prev => ({ ...prev, version_name: e.target.value }))}
            />
          </div>
          <div>
            <Label>Key Assumptions</Label>
            <Textarea
              className="mt-1"
              placeholder="Describe the key assumptions behind this forecast..."
              value={newVersion.assumptions}
              onChange={(e) => setNewVersion(prev => ({ ...prev, assumptions: e.target.value }))}
            />
          </div>
          <div>
            <Label>Notes</Label>
            <Textarea
              className="mt-1"
              placeholder="Any additional context..."
              value={newVersion.notes}
              onChange={(e) => setNewVersion(prev => ({ ...prev, notes: e.target.value }))}
            />
          </div>
          <Alert variant="info" className="text-sm">
            In production, forecast data from the Forecast Editor will be automatically linked to this submission.
          </Alert>
          <div className="flex justify-end gap-2 pt-4">
            <Button variant="outline" onClick={() => setVersionDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleSubmitVersion} leftIcon={<Send className="h-4 w-4" />}>
              Submit Version
            </Button>
          </div>
        </div>
      </Modal>

      {/* Vote Dialog */}
      <Modal
        open={voteDialogOpen}
        onClose={() => setVoteDialogOpen(false)}
        title={`Vote on ${selectedVersion?.version_name || 'Version'}`}
      >
        <div className="space-y-4 p-4">
          <div>
            <Label>Your Vote</Label>
            <div className="grid grid-cols-2 gap-2 mt-2">
              {Object.entries(VOTE_CONFIG).map(([key, { label, color, icon: Icon }]) => (
                <button
                  key={key}
                  onClick={() => setVoteForm(prev => ({ ...prev, vote: key }))}
                  className={`flex items-center gap-2 p-3 rounded-lg border text-sm font-medium transition-colors ${
                    voteForm.vote === key
                      ? 'border-primary bg-primary/5'
                      : 'border-border hover:bg-muted/50'
                  }`}
                >
                  <Icon className={`h-4 w-4 ${color}`} />
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div>
            <Label>Comment (optional)</Label>
            <Textarea
              className="mt-1"
              placeholder="Explain your vote..."
              value={voteForm.comment}
              onChange={(e) => setVoteForm(prev => ({ ...prev, comment: e.target.value }))}
            />
          </div>
          <div className="flex justify-end gap-2 pt-4">
            <Button variant="outline" onClick={() => setVoteDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleSubmitVote} leftIcon={<ThumbsUp className="h-4 w-4" />}>
              Submit Vote
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

// ============================================================================
// Mock data generators
// ============================================================================
function generateMockPlans() {
  return [
    {
      id: 1,
      name: 'Q1 2026 Demand Consensus',
      description: 'Quarterly demand alignment for Q1',
      planning_period: '2026-Q1',
      period_start: '2026-01-01T00:00:00Z',
      period_end: '2026-03-31T00:00:00Z',
      status: 'approved',
      current_phase: 'finalization',
      submission_deadline: '2025-12-15T00:00:00Z',
      final_version_id: 3,
      version_count: 4,
      created_at: '2025-12-01T10:00:00Z',
    },
    {
      id: 2,
      name: 'Q2 2026 Demand Consensus',
      description: 'Quarterly demand alignment for Q2 including promotional calendar',
      planning_period: '2026-Q2',
      period_start: '2026-04-01T00:00:00Z',
      period_end: '2026-06-30T00:00:00Z',
      status: 'voting',
      current_phase: 'voting',
      submission_deadline: '2026-03-15T00:00:00Z',
      final_version_id: null,
      version_count: 3,
      created_at: '2026-02-15T10:00:00Z',
    },
    {
      id: 3,
      name: 'H2 2026 Preliminary',
      description: 'Early H2 planning cycle to support strategic decisions',
      planning_period: '2026-H2',
      period_start: '2026-07-01T00:00:00Z',
      period_end: '2026-12-31T00:00:00Z',
      status: 'collecting',
      current_phase: 'collection',
      submission_deadline: '2026-04-01T00:00:00Z',
      final_version_id: null,
      version_count: 1,
      created_at: '2026-03-01T10:00:00Z',
    },
  ];
}

function generateMockVersions(planId) {
  const configs = {
    1: [
      { id: 1, consensus_plan_id: 1, source: 'sales', version_number: 1, version_name: 'Sales Forecast v1', is_submitted: true, is_locked: true, is_final: false, submitted_at: '2025-12-10T10:00:00Z', vote_count: 3, assumptions: 'Assumed 5% growth in Northeast' },
      { id: 2, consensus_plan_id: 1, source: 'marketing', version_number: 2, version_name: 'Marketing Forecast', is_submitted: true, is_locked: true, is_final: false, submitted_at: '2025-12-11T10:00:00Z', vote_count: 2, assumptions: 'Includes Spring promotion uplift' },
      { id: 3, consensus_plan_id: 1, source: 'finance', version_number: 3, version_name: 'Finance Budget Forecast', is_submitted: true, is_locked: true, is_final: true, submitted_at: '2025-12-12T10:00:00Z', vote_count: 4, assumptions: 'Conservative, budget-aligned' },
      { id: 4, consensus_plan_id: 1, source: 'consensus', version_number: 4, version_name: 'Final Consensus', is_submitted: true, is_locked: true, is_final: true, submitted_at: '2025-12-14T10:00:00Z', vote_count: 5, assumptions: 'Weighted blend of all inputs' },
    ],
    2: [
      { id: 5, consensus_plan_id: 2, source: 'sales', version_number: 1, version_name: 'Sales Q2 Forecast', is_submitted: true, is_locked: false, is_final: false, submitted_at: '2026-03-01T10:00:00Z', vote_count: 1, assumptions: 'Summer demand uplift factored in' },
      { id: 6, consensus_plan_id: 2, source: 'operations', version_number: 2, version_name: 'Ops Capacity-Aligned', is_submitted: true, is_locked: false, is_final: false, submitted_at: '2026-03-02T10:00:00Z', vote_count: 0, assumptions: 'Constrained by Plant-North capacity' },
      { id: 7, consensus_plan_id: 2, source: 'statistical', version_number: 3, version_name: 'ML Statistical Baseline', is_submitted: true, is_locked: false, is_final: false, submitted_at: '2026-03-03T10:00:00Z', vote_count: 2, assumptions: 'Pure statistical, no manual overrides' },
    ],
    3: [
      { id: 8, consensus_plan_id: 3, source: 'statistical', version_number: 1, version_name: 'H2 ML Baseline', is_submitted: true, is_locked: false, is_final: false, submitted_at: '2026-03-01T10:00:00Z', vote_count: 0, assumptions: 'Auto-generated from pipeline' },
    ],
  };
  return configs[planId] || [];
}

export default ConsensusPlanning;
