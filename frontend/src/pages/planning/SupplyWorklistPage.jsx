/**
 * Supply Agent Worklist Page
 *
 * Three-tab layout for the Supply Agent layer:
 * 1. Worklist (mode=ACTIVE) / Manual Input (mode=INPUT)
 * 2. Performance - Agent performance metrics
 * 3. Lineage - Artifact hash-chain visualization
 *
 * Uses the AI-as-Labor worklist pattern: agent owns the decision,
 * human reviews via Accept / Override / Reject before submission.
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Paper,
  Typography,
  Grid,
  Tabs,
  Tab,
  Button,
  TextField,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Alert,
  Chip,
  CircularProgress,
  Divider,
  MenuItem,
} from '@mui/material';

import LayerModeIndicator from '../../components/cascade/LayerModeIndicator';
import ArtifactLineage from '../../components/cascade/ArtifactLineage';
import CommitReviewPanel from '../../components/cascade/CommitReviewPanel';
import AskWhyPanel from '../../components/cascade/AskWhyPanel';
import PerformanceMetricsPanel from '../../components/cascade/PerformanceMetricsPanel';
import {
  getLayerLicenses,
  getSupplyWorklist,
  getSupplyCommit,
  reviewSupplyCommit,
  submitSupplyCommit,
} from '../../services/planningCascadeApi';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const EMPTY_ORDER = {
  type: 'PO',
  sku: '',
  supplier: '',
  destination: '',
  qty: '',
  order_date: '',
  expected_receipt: '',
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const SupplyWorklistPage = ({ configId, tenantId }) => {
  // Tab state
  const [activeTab, setActiveTab] = useState(0);

  // Layer mode (active | input | disabled)
  const [mode, setMode] = useState(null);
  const [modeLoading, setModeLoading] = useState(true);

  // Worklist state (ACTIVE mode)
  const [worklistItems, setWorklistItems] = useState([]);
  const [worklistLoading, setWorklistLoading] = useState(false);
  const [selectedCommit, setSelectedCommit] = useState(null);
  const [selectedCommitDetail, setSelectedCommitDetail] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState(null);

  // Manual input state (INPUT mode)
  const [manualOrders, setManualOrders] = useState([{ ...EMPTY_ORDER }]);
  const [manualSubmitting, setManualSubmitting] = useState(false);
  const [manualSuccess, setManualSuccess] = useState(null);

  // ---------------------------------------------------------------------------
  // Load layer license to determine mode
  // ---------------------------------------------------------------------------

  const loadMode = useCallback(async () => {
    try {
      setModeLoading(true);
      const licenses = await getLayerLicenses(tenantId);
      const supplyLayer = licenses?.layers?.supply_agent || licenses?.supply_agent;
      if (supplyLayer) {
        setMode(supplyLayer.mode || supplyLayer);
      } else {
        // Default to active when license data shape is unexpected
        setMode('active');
      }
    } catch (err) {
      console.error('Failed to load layer licenses', err);
      // Fallback to active so the page is still usable
      setMode('active');
    } finally {
      setModeLoading(false);
    }
  }, [tenantId]);

  // ---------------------------------------------------------------------------
  // Load worklist items (ACTIVE mode)
  // ---------------------------------------------------------------------------

  const loadWorklist = useCallback(async () => {
    try {
      setWorklistLoading(true);
      setError(null);
      const data = await getSupplyWorklist(configId);
      setWorklistItems(data || []);
    } catch (err) {
      console.error('Failed to load supply worklist', err);
      setError('Failed to load worklist. Please try again.');
    } finally {
      setWorklistLoading(false);
    }
  }, [configId]);

  // ---------------------------------------------------------------------------
  // Effects
  // ---------------------------------------------------------------------------

  useEffect(() => {
    loadMode();
  }, [loadMode]);

  useEffect(() => {
    if (mode === 'active') {
      loadWorklist();
    }
  }, [mode, loadWorklist]);

  // ---------------------------------------------------------------------------
  // Worklist helpers
  // ---------------------------------------------------------------------------

  const pendingCount = worklistItems.filter(
    (c) => c.status === 'pending_review' || c.status === 'proposed' || c.requires_review
  ).length;
  const violationCount = worklistItems.reduce(
    (sum, c) => sum + (c.integrity_violations?.length || 0),
    0
  );
  const riskCount = worklistItems.reduce(
    (sum, c) => sum + (c.risk_flags?.length || 0),
    0
  );

  // ---------------------------------------------------------------------------
  // Worklist actions
  // ---------------------------------------------------------------------------

  const handleViewCommit = async (commit) => {
    setSelectedCommit(commit);
    try {
      const detail = await getSupplyCommit(commit.id);
      setSelectedCommitDetail(detail);
    } catch (err) {
      console.error('Failed to load commit detail', err);
      setSelectedCommitDetail(commit);
    }
  };

  const handleAccept = async (commitId) => {
    try {
      setActionLoading(true);
      // userId not available from props; API treats null as current user
      await reviewSupplyCommit(commitId, null, 'accept');
      await loadWorklist();
      setSelectedCommit(null);
      setSelectedCommitDetail(null);
    } catch (err) {
      console.error('Failed to accept commit', err);
    } finally {
      setActionLoading(false);
    }
  };

  const handleOverride = async (commitId, overrideDetails) => {
    try {
      setActionLoading(true);
      await reviewSupplyCommit(commitId, null, 'override', overrideDetails);
      await loadWorklist();
      setSelectedCommit(null);
      setSelectedCommitDetail(null);
    } catch (err) {
      console.error('Failed to override commit', err);
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async (commitId, reason) => {
    try {
      setActionLoading(true);
      await reviewSupplyCommit(commitId, null, 'reject', { reason });
      await loadWorklist();
      setSelectedCommit(null);
      setSelectedCommitDetail(null);
    } catch (err) {
      console.error('Failed to reject commit', err);
    } finally {
      setActionLoading(false);
    }
  };

  const handleSubmit = async (commitId) => {
    try {
      setActionLoading(true);
      await submitSupplyCommit(commitId);
      await loadWorklist();
      setSelectedCommit(null);
      setSelectedCommitDetail(null);
    } catch (err) {
      console.error('Failed to submit commit', err);
    } finally {
      setActionLoading(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Manual input helpers (INPUT mode)
  // ---------------------------------------------------------------------------

  const handleAddRow = () => {
    setManualOrders((prev) => [...prev, { ...EMPTY_ORDER }]);
  };

  const handleRemoveRow = (index) => {
    setManualOrders((prev) => prev.filter((_, i) => i !== index));
  };

  const handleOrderChange = (index, field, value) => {
    setManualOrders((prev) => {
      const updated = [...prev];
      updated[index] = { ...updated[index], [field]: value };
      return updated;
    });
  };

  const handleManualSubmit = async () => {
    try {
      setManualSubmitting(true);
      setManualSuccess(null);

      // Build payload matching the supply commit structure
      const payload = {
        config_id: configId,
        source: 'manual_input',
        recommendations: manualOrders
          .filter((o) => o.sku && o.qty)
          .map((o) => ({
            order_type: o.type,
            sku: o.sku,
            supplier_id: o.supplier,
            destination_id: o.destination,
            order_qty: Number(o.qty) || 0,
            order_date: o.order_date,
            expected_receipt: o.expected_receipt,
          })),
      };

      // Post as a manual supply commit
      const { api } = await import('../../services/api');
      await api.post('/planning-cascade/supply-commit/manual', payload);

      setManualSuccess('Supply Commit created from manual input.');
      setManualOrders([{ ...EMPTY_ORDER }]);
    } catch (err) {
      console.error('Failed to submit manual orders', err);
      setError('Failed to create Supply Commit from manual input.');
    } finally {
      setManualSubmitting(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Loading gate
  // ---------------------------------------------------------------------------

  if (modeLoading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" p={6}>
        <CircularProgress />
      </Box>
    );
  }

  // ---------------------------------------------------------------------------
  // Determine tab labels based on mode
  // ---------------------------------------------------------------------------

  const tab1Label = mode === 'input' ? 'Manual Input' : 'Worklist';

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <Box sx={{ p: 3 }}>
      {/* Header */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
        <Box>
          <Typography variant="h5" gutterBottom>
            Supply Agent Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {mode === 'input'
              ? 'Enter supply orders manually. The downstream Allocation Agent will consume this as its input.'
              : 'Review Supply Commits proposed by the AI agent. Accept, override, or reject before submission.'}
          </Typography>
        </Box>
        <LayerModeIndicator layer="supply_agent" mode={mode} />
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Tabs */}
      <Paper variant="outlined" sx={{ mb: 3 }}>
        <Tabs
          value={activeTab}
          onChange={(_, v) => setActiveTab(v)}
          indicatorColor="primary"
          textColor="primary"
          sx={{ borderBottom: 1, borderColor: 'divider' }}
        >
          <Tab label={tab1Label} />
          <Tab label="Performance" />
          <Tab label="Lineage" />
        </Tabs>
      </Paper>

      {/* ================================================================= */}
      {/* Tab 1A: Worklist (ACTIVE mode)                                    */}
      {/* ================================================================= */}
      {activeTab === 0 && mode === 'active' && (
        <Box>
          {/* Summary chips */}
          <Box display="flex" gap={2} mb={3}>
            <Chip
              label={`${pendingCount} Pending`}
              color={pendingCount > 0 ? 'warning' : 'default'}
              variant={pendingCount > 0 ? 'filled' : 'outlined'}
            />
            <Chip
              label={`${violationCount} Violation${violationCount !== 1 ? 's' : ''}`}
              color={violationCount > 0 ? 'error' : 'default'}
              variant={violationCount > 0 ? 'filled' : 'outlined'}
            />
            <Chip
              label={`${riskCount} Risk Flag${riskCount !== 1 ? 's' : ''}`}
              color={riskCount > 0 ? 'warning' : 'default'}
              variant={riskCount > 0 ? 'filled' : 'outlined'}
            />
          </Box>

          {worklistLoading ? (
            <Box display="flex" justifyContent="center" p={4}>
              <CircularProgress />
            </Box>
          ) : worklistItems.length === 0 ? (
            <Alert severity="success">
              No Supply Commits pending review. The worklist is empty.
            </Alert>
          ) : (
            <>
              {/* Worklist Table */}
              <TableContainer component={Paper} variant="outlined" sx={{ mb: 3 }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>SC Hash</TableCell>
                      <TableCell>Created</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell align="right">Violations</TableCell>
                      <TableCell align="right">Risks</TableCell>
                      <TableCell align="right">Confidence</TableCell>
                      <TableCell align="center">Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {worklistItems.map((commit) => {
                      const violations = commit.integrity_violations?.length || 0;
                      const risks = commit.risk_flags?.length || 0;
                      const confidence = commit.agent_confidence ?? commit.confidence_score;
                      const isSelected = selectedCommit?.id === commit.id;

                      return (
                        <TableRow
                          key={commit.id}
                          hover
                          selected={isSelected}
                          sx={{ cursor: 'pointer' }}
                        >
                          <TableCell>
                            <Typography variant="body2" fontWeight="medium">
                              SC-{commit.hash?.slice(0, 8) || commit.id}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            {commit.created_at
                              ? new Date(commit.created_at).toLocaleString()
                              : '--'}
                          </TableCell>
                          <TableCell>
                            <Chip
                              label={commit.status?.replace(/_/g, ' ')}
                              size="small"
                              color={
                                commit.status === 'submitted' || commit.status === 'auto_submitted'
                                  ? 'success'
                                  : commit.status === 'accepted' || commit.status === 'approved'
                                  ? 'info'
                                  : commit.status === 'overridden'
                                  ? 'warning'
                                  : commit.status === 'rejected'
                                  ? 'error'
                                  : 'default'
                              }
                            />
                          </TableCell>
                          <TableCell align="right">
                            {violations > 0 ? (
                              <Chip label={violations} size="small" color="error" />
                            ) : (
                              <Typography variant="body2" color="text.secondary">0</Typography>
                            )}
                          </TableCell>
                          <TableCell align="right">
                            {risks > 0 ? (
                              <Chip label={risks} size="small" color="warning" />
                            ) : (
                              <Typography variant="body2" color="text.secondary">0</Typography>
                            )}
                          </TableCell>
                          <TableCell align="right">
                            {confidence != null
                              ? `${(confidence * 100).toFixed(0)}%`
                              : '--'}
                          </TableCell>
                          <TableCell align="center">
                            <Button
                              size="small"
                              variant={isSelected ? 'contained' : 'outlined'}
                              onClick={() => handleViewCommit(commit)}
                            >
                              View
                            </Button>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </TableContainer>

              {/* Selected Commit: Review Panel */}
              {selectedCommit && selectedCommitDetail && (
                <Box mb={3}>
                  <CommitReviewPanel
                    commit={selectedCommitDetail}
                    commitType="supply"
                    onAccept={handleAccept}
                    onOverride={handleOverride}
                    onReject={handleReject}
                    onSubmit={handleSubmit}
                    loading={actionLoading}
                  />

                  <Box mt={2}>
                    <AskWhyPanel commitId={selectedCommit.id} commitType="supply" />
                  </Box>
                </Box>
              )}
            </>
          )}
        </Box>
      )}

      {/* ================================================================= */}
      {/* Tab 1B: Manual Input (INPUT mode)                                 */}
      {/* ================================================================= */}
      {activeTab === 0 && mode === 'input' && (
        <Box>
          <Alert severity="info" sx={{ mb: 3 }}>
            Your organization does not have the Supply Agent layer active.
            Enter purchase, transfer, or manufacturing orders manually below.
            These will be packaged as a Supply Commit for the downstream Allocation Agent.
          </Alert>

          {manualSuccess && (
            <Alert severity="success" sx={{ mb: 2 }} onClose={() => setManualSuccess(null)}>
              {manualSuccess}
            </Alert>
          )}

          <TableContainer component={Paper} variant="outlined" sx={{ mb: 2 }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ width: 120 }}>Type</TableCell>
                  <TableCell>SKU</TableCell>
                  <TableCell>Supplier</TableCell>
                  <TableCell>Destination</TableCell>
                  <TableCell sx={{ width: 100 }}>Qty</TableCell>
                  <TableCell sx={{ width: 150 }}>Order Date</TableCell>
                  <TableCell sx={{ width: 150 }}>Expected Receipt</TableCell>
                  <TableCell sx={{ width: 80 }} align="center">Remove</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {manualOrders.map((order, index) => (
                  <TableRow key={index}>
                    <TableCell>
                      <TextField
                        select
                        size="small"
                        fullWidth
                        value={order.type}
                        onChange={(e) => handleOrderChange(index, 'type', e.target.value)}
                      >
                        <MenuItem value="PO">PO</MenuItem>
                        <MenuItem value="TO">TO</MenuItem>
                        <MenuItem value="MO">MO</MenuItem>
                      </TextField>
                    </TableCell>
                    <TableCell>
                      <TextField
                        size="small"
                        fullWidth
                        value={order.sku}
                        onChange={(e) => handleOrderChange(index, 'sku', e.target.value)}
                        placeholder="SKU"
                      />
                    </TableCell>
                    <TableCell>
                      <TextField
                        size="small"
                        fullWidth
                        value={order.supplier}
                        onChange={(e) => handleOrderChange(index, 'supplier', e.target.value)}
                        placeholder="Supplier ID"
                      />
                    </TableCell>
                    <TableCell>
                      <TextField
                        size="small"
                        fullWidth
                        value={order.destination}
                        onChange={(e) => handleOrderChange(index, 'destination', e.target.value)}
                        placeholder="Destination ID"
                      />
                    </TableCell>
                    <TableCell>
                      <TextField
                        size="small"
                        fullWidth
                        type="number"
                        value={order.qty}
                        onChange={(e) => handleOrderChange(index, 'qty', e.target.value)}
                        inputProps={{ min: 0 }}
                        placeholder="0"
                      />
                    </TableCell>
                    <TableCell>
                      <TextField
                        size="small"
                        fullWidth
                        type="date"
                        value={order.order_date}
                        onChange={(e) => handleOrderChange(index, 'order_date', e.target.value)}
                        InputLabelProps={{ shrink: true }}
                      />
                    </TableCell>
                    <TableCell>
                      <TextField
                        size="small"
                        fullWidth
                        type="date"
                        value={order.expected_receipt}
                        onChange={(e) => handleOrderChange(index, 'expected_receipt', e.target.value)}
                        InputLabelProps={{ shrink: true }}
                      />
                    </TableCell>
                    <TableCell align="center">
                      <Button
                        size="small"
                        color="error"
                        onClick={() => handleRemoveRow(index)}
                        disabled={manualOrders.length <= 1}
                      >
                        Remove
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          <Box display="flex" gap={2}>
            <Button variant="outlined" size="small" onClick={handleAddRow}>
              Add Row
            </Button>
            <Button
              variant="contained"
              color="primary"
              onClick={handleManualSubmit}
              disabled={
                manualSubmitting ||
                manualOrders.every((o) => !o.sku || !o.qty)
              }
            >
              {manualSubmitting ? (
                <CircularProgress size={20} sx={{ mr: 1 }} />
              ) : null}
              Submit as Supply Commit
            </Button>
          </Box>
        </Box>
      )}

      {/* ================================================================= */}
      {/* Tab 2: Performance                                                */}
      {/* ================================================================= */}
      {activeTab === 1 && (
        <Box>
          <PerformanceMetricsPanel configId={configId} agentType="supply_agent" />
        </Box>
      )}

      {/* ================================================================= */}
      {/* Tab 3: Lineage                                                    */}
      {/* ================================================================= */}
      {activeTab === 2 && (
        <Box>
          {selectedCommit ? (
            <ArtifactLineage
              artifactType="supply_commit"
              artifactId={selectedCommit.id}
            />
          ) : (
            <Alert severity="info">
              Select a Supply Commit from the Worklist tab to view its artifact lineage.
            </Alert>
          )}
        </Box>
      )}
    </Box>
  );
};

export default SupplyWorklistPage;
