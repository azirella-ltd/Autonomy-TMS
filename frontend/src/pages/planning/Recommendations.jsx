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
} from '../../components/common';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../../components/ui/tooltip';
import {
  RefreshCw,
  CheckCircle,
  XCircle,
  TrendingUp,
  Truck,
  Leaf,
  DollarSign,
  Play,
  Info,
  Scale,
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
