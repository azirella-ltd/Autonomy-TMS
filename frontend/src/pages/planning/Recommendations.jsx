import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Badge,
  Label,
  Input,
  Textarea,
  Spinner,
  Modal,
  Progress,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  Checkbox,
  Tabs,
  TabsList,
  TabsTrigger,
} from '../../components/common';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../../components/ui/tooltip';
import {
  RefreshCw,
  CheckCircle,
  XCircle,
  TrendingUp,
  TrendingDown,
  Truck,
  Leaf,
  DollarSign,
  Play,
  Info,
  Scale,
  BarChart3,
  Target,
} from 'lucide-react';
import { api } from '../../services/api';
import InlineComments from '../../components/common/InlineComments';
import { RebalancingWizard } from '../../components/recommendations';

const Recommendations = () => {
  const [recommendations, setRecommendations] = useState([]);
  const [loading, setLoading] = useState(false);
  const [typeFilter, setTypeFilter] = useState('ALL');
  const [statusFilter, setStatusFilter] = useState('pending');
  const [minScore, setMinScore] = useState(0);
  const [selectedRecommendation, setSelectedRecommendation] = useState(null);
  const [selectedIds, setSelectedIds] = useState([]);
  const [detailDialogOpen, setDetailDialogOpen] = useState(false);
  const [approvalDialogOpen, setApprovalDialogOpen] = useState(false);
  const [simulationDialogOpen, setSimulationDialogOpen] = useState(false);
  const [batchApprovalDialogOpen, setBatchApprovalDialogOpen] = useState(false);
  const [batchAction, setBatchAction] = useState(null);
  const [approvalReason, setApprovalReason] = useState('');
  const [simulationResult, setSimulationResult] = useState(null);
  const [rebalancingDialogOpen, setRebalancingDialogOpen] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [activeView, setActiveView] = useState('recommendations');

  // Performance tracking data
  const [performanceData] = useState({
    summary: {
      totalRecommendations: 156,
      acceptanceRate: 72.4,
      overrideRate: 18.6,
      autoExecutedRate: 9.0,
      avgScoreAccepted: 78.3,
      avgScoreOverridden: 42.1,
      netSavingsRealized: 284500,
      netSavingsPredicted: 312000,
      realizationRate: 91.2,
    },
    byType: [
      { type: 'rebalance', total: 82, accepted: 65, overridden: 12, executed: 5, avgScore: 71.2, savingsRealized: 145000, savingsPredicted: 158000 },
      { type: 'expedite', total: 45, accepted: 28, overridden: 14, executed: 3, avgScore: 62.8, savingsRealized: 89000, savingsPredicted: 98000 },
      { type: 'inventory_buffer', total: 29, accepted: 20, overridden: 3, executed: 6, avgScore: 81.5, savingsRealized: 50500, savingsPredicted: 56000 },
    ],
    recentOutcomes: [
      { id: 'REC-142', type: 'rebalance', score: 85, action: 'accepted', predictedSavings: 4200, actualSavings: 3980, predictedServiceImpact: 2.1, actualServiceImpact: 1.8, effective: true },
      { id: 'REC-139', type: 'expedite', score: 67, action: 'accepted', predictedSavings: 1800, actualSavings: 2100, predictedServiceImpact: 3.5, actualServiceImpact: 4.1, effective: true },
      { id: 'REC-137', type: 'rebalance', score: 45, action: 'overridden', predictedSavings: 2500, actualSavings: -800, predictedServiceImpact: 1.2, actualServiceImpact: -0.5, effective: false },
      { id: 'REC-135', type: 'inventory_buffer', score: 91, action: 'accepted', predictedSavings: 5600, actualSavings: 5200, predictedServiceImpact: 1.8, actualServiceImpact: 2.0, effective: true },
      { id: 'REC-131', type: 'expedite', score: 38, action: 'overridden', predictedSavings: 900, actualSavings: 1200, predictedServiceImpact: 0.8, actualServiceImpact: 1.5, effective: true },
      { id: 'REC-128', type: 'rebalance', score: 74, action: 'accepted', predictedSavings: 3100, actualSavings: 2900, predictedServiceImpact: 2.4, actualServiceImpact: 2.2, effective: true },
    ],
  });

  const fetchRecommendations = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {
        status: statusFilter !== 'ALL' ? statusFilter : undefined,
        recommendation_type: typeFilter !== 'ALL' ? typeFilter : undefined,
        min_score: minScore,
      };
      const response = await api.get('/recommendations/', { params });
      setRecommendations(response.data);
    } catch (error) {
      console.error('Failed to fetch recommendations:', error);
      setError('Failed to load recommendations. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const generateRecommendations = async () => {
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const response = await api.post('/recommendations/generate');
      setRecommendations(response.data);
      setSuccess(`Generated ${response.data.length} recommendations`);
    } catch (error) {
      console.error('Failed to generate recommendations:', error);
      setError('Failed to generate recommendations. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const simulateRecommendation = async (recId) => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.post(`/api/recommendations/${recId}/simulate`);
      setSimulationResult(response.data);
      setSimulationDialogOpen(true);
    } catch (error) {
      console.error('Failed to simulate recommendation:', error);
      setError('Failed to simulate recommendation impact.');
    } finally {
      setLoading(false);
    }
  };

  const handleApproval = async (action) => {
    if (!selectedRecommendation) return;

    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      await api.post(`/api/recommendations/${selectedRecommendation.id}/approve`, {
        action,
        reason: approvalReason,
      });
      setSuccess(`Recommendation ${action} successfully`);
      setApprovalDialogOpen(false);
      setApprovalReason('');
      setSelectedRecommendation(null);
      fetchRecommendations();
    } catch (error) {
      console.error('Failed to process approval:', error);
      setError(`Failed to ${action} recommendation.`);
    } finally {
      setLoading(false);
    }
  };

  const handleBatchApproval = async (action) => {
    if (selectedIds.length === 0) return;

    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      await api.post('/api/recommendations/batch-approve', {
        recommendation_ids: selectedIds,
        action,
        reason: approvalReason,
      });
      setSuccess(`${selectedIds.length} recommendations ${action} successfully`);
      setBatchApprovalDialogOpen(false);
      setApprovalReason('');
      setSelectedIds([]);
      setBatchAction(null);
      fetchRecommendations();
    } catch (error) {
      console.error('Failed to process batch approval:', error);
      setError(`Failed to ${action} recommendations.`);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectAllClick = (checked) => {
    if (checked) {
      const pendingRecs = recommendations.filter((r) => r.status === 'pending');
      setSelectedIds(pendingRecs.map((r) => r.id));
      return;
    }
    setSelectedIds([]);
  };

  const handleSelectClick = (id) => {
    const selectedIndex = selectedIds.indexOf(id);
    let newSelected = [];

    if (selectedIndex === -1) {
      newSelected = [...selectedIds, id];
    } else {
      newSelected = selectedIds.filter((i) => i !== id);
    }

    setSelectedIds(newSelected);
  };

  const isSelected = (id) => selectedIds.indexOf(id) !== -1;
  const pendingCount = recommendations.filter((r) => r.status === 'pending').length;

  useEffect(() => {
    fetchRecommendations();
  }, [statusFilter, typeFilter, minScore]);

  const getScoreVariant = (score) => {
    if (score >= 75) return 'success';
    if (score >= 50) return 'info';
    if (score >= 25) return 'warning';
    return 'secondary';
  };

  const getStatusVariant = (status) => {
    switch (status) {
      case 'accepted':
        return 'success';
      case 'rejected':
        return 'destructive';
      case 'pending':
        return 'warning';
      case 'executed':
        return 'info';
      default:
        return 'secondary';
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Recommended Actions</h1>
        <p className="text-sm text-muted-foreground">
          AI-powered inventory rebalancing recommendations to optimize service levels and reduce costs
        </p>
      </div>

      {error && (
        <Alert variant="destructive" className="mb-4" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      {success && (
        <Alert variant="success" className="mb-4" onClose={() => setSuccess(null)}>
          {success}
        </Alert>
      )}

      {/* View Tabs */}
      <Tabs value={activeView} onValueChange={setActiveView} className="mb-6">
        <TabsList>
          <TabsTrigger value="recommendations">Recommendations</TabsTrigger>
          <TabsTrigger value="performance">Performance Tracking</TabsTrigger>
        </TabsList>
      </Tabs>

      {activeView === 'performance' && (
        <div className="space-y-6">
          {/* Summary KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <Card>
              <CardContent className="pt-4 pb-4 text-center">
                <p className="text-xs text-muted-foreground mb-1">Total Recommendations</p>
                <p className="text-2xl font-bold">{performanceData.summary.totalRecommendations}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4 pb-4 text-center">
                <p className="text-xs text-muted-foreground mb-1">Acceptance Rate</p>
                <p className="text-2xl font-bold text-green-600">{performanceData.summary.acceptanceRate}%</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4 pb-4 text-center">
                <p className="text-xs text-muted-foreground mb-1">Override Rate</p>
                <p className="text-2xl font-bold text-amber-600">{performanceData.summary.overrideRate}%</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4 pb-4 text-center">
                <p className="text-xs text-muted-foreground mb-1">Savings Realized</p>
                <p className="text-2xl font-bold">${(performanceData.summary.netSavingsRealized / 1000).toFixed(0)}K</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4 pb-4 text-center">
                <p className="text-xs text-muted-foreground mb-1">Realization Rate</p>
                <p className="text-2xl font-bold text-primary">{performanceData.summary.realizationRate}%</p>
              </CardContent>
            </Card>
          </div>

          {/* Performance by Type */}
          <Card>
            <CardContent className="pt-6">
              <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <BarChart3 className="h-5 w-5 text-primary" />
                Performance by Recommendation Type
              </h3>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Type</TableHead>
                    <TableHead className="text-right">Total</TableHead>
                    <TableHead className="text-right">Accepted</TableHead>
                    <TableHead className="text-right">Overridden</TableHead>
                    <TableHead className="text-right">Auto-Executed</TableHead>
                    <TableHead className="text-right">Acceptance %</TableHead>
                    <TableHead className="text-right">Avg Score</TableHead>
                    <TableHead className="text-right">Predicted Savings</TableHead>
                    <TableHead className="text-right">Actual Savings</TableHead>
                    <TableHead className="text-right">Realization %</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {performanceData.byType.map((row) => {
                    const acceptPct = ((row.accepted / row.total) * 100).toFixed(1);
                    const realPct = ((row.savingsRealized / row.savingsPredicted) * 100).toFixed(1);
                    return (
                      <TableRow key={row.type}>
                        <TableCell className="font-medium capitalize">{row.type.replace('_', ' ')}</TableCell>
                        <TableCell className="text-right font-mono">{row.total}</TableCell>
                        <TableCell className="text-right font-mono text-green-600">{row.accepted}</TableCell>
                        <TableCell className="text-right font-mono text-amber-600">{row.overridden}</TableCell>
                        <TableCell className="text-right font-mono text-blue-600">{row.executed}</TableCell>
                        <TableCell className="text-right font-mono">{acceptPct}%</TableCell>
                        <TableCell className="text-right">
                          <Badge variant={getScoreVariant(row.avgScore)}>{row.avgScore}</Badge>
                        </TableCell>
                        <TableCell className="text-right font-mono">${row.savingsPredicted.toLocaleString()}</TableCell>
                        <TableCell className="text-right font-mono">${row.savingsRealized.toLocaleString()}</TableCell>
                        <TableCell className="text-right">
                          <span className={parseFloat(realPct) >= 90 ? 'text-green-600' : 'text-amber-600'}>
                            {realPct}%
                          </span>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          {/* Recent Outcomes */}
          <Card>
            <CardContent className="pt-6">
              <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <Target className="h-5 w-5 text-primary" />
                Recent Outcomes — Predicted vs Actual
              </h3>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>ID</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Score</TableHead>
                    <TableHead>Action</TableHead>
                    <TableHead className="text-right">Predicted $</TableHead>
                    <TableHead className="text-right">Actual $</TableHead>
                    <TableHead className="text-right">Predicted SL Impact</TableHead>
                    <TableHead className="text-right">Actual SL Impact</TableHead>
                    <TableHead>Effective</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {performanceData.recentOutcomes.map((row) => (
                    <TableRow key={row.id}>
                      <TableCell className="font-mono text-sm">{row.id}</TableCell>
                      <TableCell className="capitalize">{row.type.replace('_', ' ')}</TableCell>
                      <TableCell><Badge variant={getScoreVariant(row.score)}>{row.score}</Badge></TableCell>
                      <TableCell>
                        <Badge variant={row.action === 'accepted' ? 'success' : 'warning'}>{row.action}</Badge>
                      </TableCell>
                      <TableCell className="text-right font-mono">${row.predictedSavings.toLocaleString()}</TableCell>
                      <TableCell className={`text-right font-mono ${row.actualSavings >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        ${row.actualSavings.toLocaleString()}
                      </TableCell>
                      <TableCell className="text-right font-mono">+{row.predictedServiceImpact}%</TableCell>
                      <TableCell className={`text-right font-mono ${row.actualServiceImpact >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        {row.actualServiceImpact >= 0 ? '+' : ''}{row.actualServiceImpact}%
                      </TableCell>
                      <TableCell>
                        {row.effective ? (
                          <CheckCircle className="h-4 w-4 text-green-600" />
                        ) : (
                          <XCircle className="h-4 w-4 text-red-600" />
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          {/* Score Effectiveness Insight */}
          <Card>
            <CardContent className="pt-6">
              <h3 className="text-lg font-semibold mb-4">Score Effectiveness Analysis</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="p-4 bg-muted/30 rounded-lg">
                  <p className="text-sm text-muted-foreground mb-1">Avg Score of Accepted Recommendations</p>
                  <p className="text-3xl font-bold text-green-600">{performanceData.summary.avgScoreAccepted}</p>
                  <p className="text-xs text-muted-foreground mt-1">Higher scores correlate with better outcomes</p>
                </div>
                <div className="p-4 bg-muted/30 rounded-lg">
                  <p className="text-sm text-muted-foreground mb-1">Avg Score of Overridden Recommendations</p>
                  <p className="text-3xl font-bold text-amber-600">{performanceData.summary.avgScoreOverridden}</p>
                  <p className="text-xs text-muted-foreground mt-1">Low scores are overridden more frequently</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {activeView === 'recommendations' && <>
      {/* Filters and Actions */}
      <Card className="mb-6">
        <CardContent className="pt-4">
          <div className="grid grid-cols-1 md:grid-cols-7 gap-4 items-end">
            <div className="md:col-span-1">
              <Label>Status</Label>
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ALL">All Status</SelectItem>
                  <SelectItem value="pending">Pending</SelectItem>
                  <SelectItem value="accepted">Accepted</SelectItem>
                  <SelectItem value="rejected">Overridden</SelectItem>
                  <SelectItem value="executed">Executed</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="md:col-span-1">
              <Label>Type</Label>
              <Select value={typeFilter} onValueChange={setTypeFilter}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ALL">All Types</SelectItem>
                  <SelectItem value="rebalance">Rebalance</SelectItem>
                  <SelectItem value="expedite">Expedite</SelectItem>
                  <SelectItem value="inventory_buffer">Inventory Buffer</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="md:col-span-1">
              <Label>Min Score</Label>
              <Input
                type="number"
                value={minScore}
                onChange={(e) => setMinScore(Number(e.target.value))}
                min={0}
                max={100}
              />
            </div>
            <div className="md:col-span-1">
              <Button
                className="w-full"
                variant="outline"
                onClick={fetchRecommendations}
                disabled={loading}
                leftIcon={<RefreshCw className="h-4 w-4" />}
              >
                Refresh
              </Button>
            </div>
            <div className="md:col-span-1">
              <Button
                className="w-full"
                onClick={generateRecommendations}
                disabled={loading}
                leftIcon={<Play className="h-4 w-4" />}
              >
                Generate
              </Button>
            </div>
            <div className="md:col-span-2">
              <Button
                className="w-full"
                variant="outline"
                onClick={() => setRebalancingDialogOpen(true)}
                leftIcon={<Scale className="h-4 w-4" />}
              >
                Rebalancing Wizard
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {loading && <Progress className="mb-4" />}

      {/* Batch Actions Toolbar */}
      {selectedIds.length > 0 && (
        <div className="flex items-center gap-4 p-4 mb-4 bg-primary/10 rounded-lg">
          <span className="font-medium">{selectedIds.length} selected</span>
          <Button
            size="sm"
            variant="success"
            onClick={() => {
              setBatchAction('accepted');
              setBatchApprovalDialogOpen(true);
            }}
            leftIcon={<CheckCircle className="h-4 w-4" />}
          >
            Accept All
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setBatchAction('rejected');
              setBatchApprovalDialogOpen(true);
            }}
            leftIcon={<XCircle className="h-4 w-4" />}
          >
            Override All
          </Button>
        </div>
      )}

      {/* Recommendations Table */}
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10">
                  <Checkbox
                    checked={pendingCount > 0 && selectedIds.length === pendingCount}
                    onCheckedChange={handleSelectAllClick}
                    disabled={pendingCount === 0}
                  />
                </TableHead>
                <TableHead>Score</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Product</TableHead>
                <TableHead>From Site</TableHead>
                <TableHead>To Site</TableHead>
                <TableHead>Quantity</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {recommendations.length === 0 && !loading && (
                <TableRow>
                  <TableCell colSpan={9} className="text-center text-muted-foreground py-8">
                    No recommendations found. Click "Generate" to create new recommendations.
                  </TableCell>
                </TableRow>
              )}
              {recommendations.map((rec) => {
                const isItemSelected = isSelected(rec.id);
                const isPending = rec.status === 'pending';
                return (
                  <TableRow key={rec.id} className={isItemSelected ? 'bg-primary/5' : ''}>
                    <TableCell>
                      {isPending && (
                        <Checkbox
                          checked={isItemSelected}
                          onCheckedChange={() => handleSelectClick(rec.id)}
                        />
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge variant={getScoreVariant(rec.total_score)}>
                        {rec.total_score ? rec.total_score.toFixed(1) : 'N/A'}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge>{rec.recommendation_type}</Badge>
                    </TableCell>
                    <TableCell>{rec.product_id}</TableCell>
                    <TableCell>{rec.from_site_id || 'N/A'}</TableCell>
                    <TableCell>{rec.to_site_id || 'N/A'}</TableCell>
                    <TableCell>{rec.quantity.toFixed(2)}</TableCell>
                    <TableCell>
                      <Badge variant={getStatusVariant(rec.status)}>{rec.status}</Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => {
                                  setSelectedRecommendation(rec);
                                  setDetailDialogOpen(true);
                                }}
                              >
                                <Info className="h-4 w-4" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>View Details</TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                        {rec.status === 'pending' && (
                          <>
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button variant="ghost" size="sm" onClick={() => simulateRecommendation(rec.id)}>
                                    <TrendingUp className="h-4 w-4" />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>Simulate Impact</TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => {
                                      setSelectedRecommendation(rec);
                                      setApprovalDialogOpen(true);
                                    }}
                                  >
                                    <CheckCircle className="h-4 w-4 text-green-600" />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>Accept</TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => {
                                      setSelectedRecommendation(rec);
                                      setApprovalDialogOpen(true);
                                    }}
                                  >
                                    <XCircle className="h-4 w-4 text-red-600" />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>Override</TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                          </>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      </>}

      {/* Detail Dialog */}
      <Modal
        isOpen={detailDialogOpen}
        onClose={() => setDetailDialogOpen(false)}
        title="Recommendation Details"
        size="lg"
        footer={<Button variant="outline" onClick={() => setDetailDialogOpen(false)}>Close</Button>}
      >
        {selectedRecommendation && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Product ID</p>
                <p className="font-medium">{selectedRecommendation.product_id}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Quantity</p>
                <p className="font-medium">{selectedRecommendation.quantity.toFixed(2)}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">From Site</p>
                <p className="font-medium">{selectedRecommendation.from_site_id || 'N/A'}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">To Site</p>
                <p className="font-medium">{selectedRecommendation.to_site_id || 'N/A'}</p>
              </div>
            </div>

            <div>
              <h3 className="text-lg font-semibold mt-4 mb-2">Scoring Breakdown</h3>
              <div className="grid grid-cols-2 gap-4">
                <div className="flex items-center gap-2">
                  <TrendingUp className="h-4 w-4" />
                  <span className="text-sm">Risk Resolution:</span>
                  <span className="font-medium">{selectedRecommendation.risk_resolution_score?.toFixed(1) || 'N/A'}/40</span>
                </div>
                <div className="flex items-center gap-2">
                  <Truck className="h-4 w-4" />
                  <span className="text-sm">Distance:</span>
                  <span className="font-medium">{selectedRecommendation.distance_score?.toFixed(1) || 'N/A'}/20</span>
                </div>
                <div className="flex items-center gap-2">
                  <Leaf className="h-4 w-4" />
                  <span className="text-sm">Sustainability:</span>
                  <span className="font-medium">{selectedRecommendation.sustainability_score?.toFixed(1) || 'N/A'}/15</span>
                </div>
                <div className="flex items-center gap-2">
                  <CheckCircle className="h-4 w-4" />
                  <span className="text-sm">Service Level:</span>
                  <span className="font-medium">{selectedRecommendation.service_level_score?.toFixed(1) || 'N/A'}/15</span>
                </div>
                <div className="flex items-center gap-2">
                  <DollarSign className="h-4 w-4" />
                  <span className="text-sm">Cost:</span>
                  <span className="font-medium">{selectedRecommendation.cost_score?.toFixed(1) || 'N/A'}/10</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-sm">Total Score:</span>
                  <Badge variant={getScoreVariant(selectedRecommendation.total_score)}>
                    {selectedRecommendation.total_score?.toFixed(1) || 'N/A'}/100
                  </Badge>
                </div>
              </div>
            </div>

            <InlineComments
              entityType="recommendation"
              entityId={selectedRecommendation.id}
              title="Recommendation Comments"
              collapsible={true}
              defaultExpanded={false}
            />
          </div>
        )}
      </Modal>

      {/* Approval Dialog */}
      <Modal
        isOpen={approvalDialogOpen}
        onClose={() => setApprovalDialogOpen(false)}
        title="Review Recommendation"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setApprovalDialogOpen(false)}>Cancel</Button>
            <Button variant="destructive" onClick={() => handleApproval('rejected')} disabled={loading}>Override</Button>
            <Button variant="success" onClick={() => handleApproval('accepted')} disabled={loading}>Accept</Button>
          </div>
        }
      >
        <div>
          <Label>Reason (optional)</Label>
          <Textarea
            rows={4}
            value={approvalReason}
            onChange={(e) => setApprovalReason(e.target.value)}
          />
        </div>
      </Modal>

      {/* Simulation Dialog */}
      <Modal
        isOpen={simulationDialogOpen}
        onClose={() => setSimulationDialogOpen(false)}
        title="Impact Simulation Results"
        size="lg"
        footer={<Button variant="outline" onClick={() => setSimulationDialogOpen(false)}>Close</Button>}
      >
        {simulationResult && (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-semibold mb-2">Service Level Impact</h3>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">From Site Before:</p>
                  <p className="text-xl font-semibold">{simulationResult.from_site_service_level_before.toFixed(1)}%</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">From Site After:</p>
                  <p className="text-xl font-semibold">{simulationResult.from_site_service_level_after.toFixed(1)}%</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">To Site Before:</p>
                  <p className="text-xl font-semibold">{simulationResult.to_site_service_level_before.toFixed(1)}%</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">To Site After:</p>
                  <p className="text-xl font-semibold text-green-600">{simulationResult.to_site_service_level_after.toFixed(1)}%</p>
                </div>
              </div>
            </div>

            <div>
              <h3 className="text-lg font-semibold mb-2">Cost Impact</h3>
              <p className="text-sm text-muted-foreground">Net Savings:</p>
              <p className="text-2xl font-bold text-green-600">${simulationResult.net_cost_savings.toLocaleString()}</p>
            </div>

            <div>
              <h3 className="text-lg font-semibold mb-2">Risk Reduction</h3>
              <p className="text-sm text-muted-foreground">Stockout Risk Reduction:</p>
              <p className="text-2xl font-bold text-green-600">{simulationResult.risk_reduction_pct.toFixed(1)}%</p>
            </div>

            <div>
              <h3 className="text-lg font-semibold mb-2">Sustainability</h3>
              <p className="text-sm text-muted-foreground">Estimated CO2 Emissions:</p>
              <p className="text-2xl font-bold">{simulationResult.estimated_co2_emissions_kg.toFixed(1)} kg</p>
            </div>
          </div>
        )}
      </Modal>

      {/* Batch Approval Dialog */}
      <Modal
        isOpen={batchApprovalDialogOpen}
        onClose={() => setBatchApprovalDialogOpen(false)}
        title={`${batchAction === 'accepted' ? 'Accept' : 'Override'} ${selectedIds.length} Recommendations`}
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setBatchApprovalDialogOpen(false)}>Cancel</Button>
            <Button
              variant={batchAction === 'accepted' ? 'success' : 'destructive'}
              onClick={() => handleBatchApproval(batchAction)}
              disabled={loading}
            >
              {loading ? 'Processing...' : `${batchAction === 'accepted' ? 'Accept' : 'Override'} All`}
            </Button>
          </div>
        }
      >
        <div>
          <p className="text-sm text-muted-foreground mb-4">
            You are about to {batchAction === 'accepted' ? 'accept' : 'override'} {selectedIds.length} recommendations. This
            action will be applied to all selected items.
          </p>
          <Label>Reason (optional)</Label>
          <Textarea
            rows={4}
            value={approvalReason}
            onChange={(e) => setApprovalReason(e.target.value)}
            placeholder="Enter a reason for this batch action..."
          />
        </div>
      </Modal>

      {/* Rebalancing Wizard Dialog */}
      <Modal
        isOpen={rebalancingDialogOpen}
        onClose={() => setRebalancingDialogOpen(false)}
        title="Inventory Rebalancing Wizard"
        size="xl"
        footer={<Button variant="outline" onClick={() => setRebalancingDialogOpen(false)}>Close</Button>}
      >
        <RebalancingWizard
          onComplete={(savedCount) => {
            setRebalancingDialogOpen(false);
            if (savedCount > 0) {
              setSuccess(`Saved ${savedCount} rebalancing recommendations`);
              fetchRecommendations();
            }
          }}
        />
      </Modal>
    </div>
  );
};

export default Recommendations;
