/**
 * Allocation Worklist Page
 *
 * The Allocation Agent Worklist page with three tabs:
 * 1. Worklist (ACTIVE mode) / Manual Input (INPUT mode)
 * 2. Performance - Agent performance metrics for allocation agent
 * 3. Lineage - Hash-chain artifact lineage
 *
 * Supports modular selling: when mode=INPUT the worklist tab becomes
 * a manual allocation-rules input screen.
 */
import React, { useState, useEffect } from 'react';
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
  Slider,
} from '@mui/material';

import { useAuth } from '../../contexts/AuthContext';
import { getSupplyChainConfigs } from '../../services/supplyChainConfigService';
import LayerModeIndicator from '../../components/cascade/LayerModeIndicator';
import ArtifactLineage from '../../components/cascade/ArtifactLineage';
import CommitReviewPanel from '../../components/cascade/CommitReviewPanel';
import AskWhyPanel from '../../components/cascade/AskWhyPanel';
import PerformanceMetricsPanel from '../../components/cascade/PerformanceMetricsPanel';
import AllocationTimelineTab from '../../components/cascade/AllocationTimelineTab';
import {
  getLayerLicenses,
  getAllocationWorklist,
  getAllocationCommit,
  reviewAllocationCommit,
  submitAllocationCommit,
} from '../../services/planningCascadeApi';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DEFAULT_SEGMENTS = ['strategic', 'standard', 'transactional'];

const DEFAULT_ALLOCATION_RULES = DEFAULT_SEGMENTS.map((segment, idx) => ({
  segment,
  priority: idx + 1,
  allocationPct: segment === 'strategic' ? 50 : segment === 'standard' ? 35 : 15,
  minFloorQty: 0,
}));

const STATUS_COLORS = {
  proposed: 'default',
  pending_review: 'warning',
  accepted: 'info',
  overridden: 'warning',
  rejected: 'error',
  submitted: 'success',
  auto_submitted: 'success',
};

// ---------------------------------------------------------------------------
// AllocationWorklistPage
// ---------------------------------------------------------------------------

const AllocationWorklistPage = ({ configId: propConfigId, tenantId: propTenantId }) => {
  const { user } = useAuth();

  // Auto-resolve configId and tenantId from user's organization when not provided as props
  const [resolvedConfigId, setResolvedConfigId] = useState(propConfigId || null);
  const [resolvedTenantId, setResolvedTenantId] = useState(propTenantId || user?.tenant_id || null);

  useEffect(() => {
    if (propConfigId) { setResolvedConfigId(propConfigId); return; }
    if (propTenantId) setResolvedTenantId(propTenantId);
    else if (user?.tenant_id) setResolvedTenantId(user.tenant_id);

    // Fetch organization's first SC config when configId not provided
    const resolveConfig = async () => {
      try {
        const configs = await getSupplyChainConfigs();
        if (configs?.length > 0) {
          // Pick the first config belonging to the user's organization (or the first active one)
          const userTenantId = propTenantId || user?.tenant_id;
          const tenantConfig = userTenantId
            ? configs.find(c => c.tenant_id === userTenantId)
            : null;
          const activeConfig = configs.find(c => c.is_active);
          const picked = tenantConfig || activeConfig || configs[0];
          setResolvedConfigId(picked.id);
          if (picked.tenant_id) setResolvedTenantId(picked.tenant_id);
        }
      } catch (err) {
        console.error('Failed to resolve SC config:', err);
        setError('Failed to determine supply chain configuration. Check that your organization has an active config.');
      }
    };
    resolveConfig();
  }, [propConfigId, propTenantId, user?.tenant_id]);

  const configId = resolvedConfigId;
  const tenantId = resolvedTenantId;

  // Layer license / mode
  const [mode, setMode] = useState(null); // 'active' | 'input' | 'disabled'
  const [modeLoading, setModeLoading] = useState(true);

  // Tab state
  const [activeTab, setActiveTab] = useState(0);

  // Worklist state (ACTIVE mode)
  const [worklist, setWorklist] = useState([]);
  const [worklistLoading, setWorklistLoading] = useState(false);
  const [selectedCommit, setSelectedCommit] = useState(null);
  const [selectedCommitData, setSelectedCommitData] = useState(null);
  const [commitLoading, setCommitLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);

  // Manual input state (INPUT mode)
  const [allocationRules, setAllocationRules] = useState(DEFAULT_ALLOCATION_RULES);
  const [submittingRules, setSubmittingRules] = useState(false);

  // Lineage tab
  const [selectedCommitId, setSelectedCommitId] = useState(null);

  // -------------------------------------------------------------------------
  // Load layer mode
  // -------------------------------------------------------------------------
  useEffect(() => {
    const loadMode = async () => {
      try {
        setModeLoading(true);
        const licenses = await getLayerLicenses(tenantId);
        const allocLayer = licenses?.layers?.allocation_agent
          || licenses?.allocation_agent;
        if (allocLayer) {
          setMode(allocLayer.mode || 'active');
        } else {
          // Fallback: assume active if license data is not structured as expected
          setMode('active');
        }
      } catch (err) {
        console.error('Failed to load layer licenses', err);
        // Default to active so the page is still usable
        setMode('active');
      } finally {
        setModeLoading(false);
      }
    };
    if (tenantId) {
      loadMode();
    } else {
      setMode('active');
      setModeLoading(false);
    }
  }, [tenantId]);

  // -------------------------------------------------------------------------
  // Load worklist when tab 0 is active and mode is ACTIVE
  // -------------------------------------------------------------------------
  useEffect(() => {
    if (mode === 'active' && activeTab === 0 && configId) {
      loadWorklist();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, activeTab, configId]);

  const loadWorklist = async () => {
    if (!configId) return;
    try {
      setWorklistLoading(true);
      setError(null);
      const data = await getAllocationWorklist(configId);
      const items = Array.isArray(data) ? data : data?.items || data?.commits || [];
      setWorklist(items);
    } catch (err) {
      console.error('Failed to load allocation worklist', err);
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail;
      setError(
        status === 404
          ? `No worklist endpoint found for config ${configId}. Ensure the planning cascade is configured.`
          : detail
            ? `Failed to load worklist: ${detail}`
            : `Failed to load worklist (config_id=${configId}). Please try again.`
      );
    } finally {
      setWorklistLoading(false);
    }
  };

  // -------------------------------------------------------------------------
  // View a single commit
  // -------------------------------------------------------------------------
  const handleViewCommit = async (commitId) => {
    try {
      setCommitLoading(true);
      setSelectedCommit(commitId);
      setSelectedCommitId(commitId);
      setError(null);
      const data = await getAllocationCommit(commitId);
      setSelectedCommitData(data);
    } catch (err) {
      console.error('Failed to load allocation commit', err);
      setError('Failed to load commit details.');
    } finally {
      setCommitLoading(false);
    }
  };

  // -------------------------------------------------------------------------
  // Accept / Override / Reject / Submit handlers
  // -------------------------------------------------------------------------
  const handleAccept = async (commitId) => {
    try {
      setActionLoading(true);
      setError(null);
      await reviewAllocationCommit(commitId, null, 'accept');
      setSuccessMsg('Allocation commit accepted.');
      setSelectedCommitData(null);
      setSelectedCommit(null);
      loadWorklist();
    } catch (err) {
      console.error('Failed to accept commit', err);
      setError('Failed to accept commit.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleOverride = async (commitId, overrideDetails) => {
    try {
      setActionLoading(true);
      setError(null);
      await reviewAllocationCommit(commitId, null, 'override', overrideDetails);
      setSuccessMsg('Allocation commit overridden.');
      setSelectedCommitData(null);
      setSelectedCommit(null);
      loadWorklist();
    } catch (err) {
      console.error('Failed to override commit', err);
      setError('Failed to override commit.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async (commitId, reason) => {
    try {
      setActionLoading(true);
      setError(null);
      await reviewAllocationCommit(commitId, null, 'reject', { reason });
      setSuccessMsg('Allocation commit rejected. Agent will re-generate.');
      setSelectedCommitData(null);
      setSelectedCommit(null);
      loadWorklist();
    } catch (err) {
      console.error('Failed to reject commit', err);
      setError('Failed to reject commit.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleSubmit = async (commitId) => {
    try {
      setActionLoading(true);
      setError(null);
      await submitAllocationCommit(commitId);
      setSuccessMsg('Allocation commit submitted for execution.');
      setSelectedCommitData(null);
      setSelectedCommit(null);
      loadWorklist();
    } catch (err) {
      console.error('Failed to submit commit', err);
      setError('Failed to submit commit.');
    } finally {
      setActionLoading(false);
    }
  };

  // -------------------------------------------------------------------------
  // Manual input helpers
  // -------------------------------------------------------------------------
  const handleRuleChange = (index, field, value) => {
    setAllocationRules((prev) => {
      const updated = [...prev];
      updated[index] = { ...updated[index], [field]: value };
      return updated;
    });
  };

  const handleAddRule = () => {
    setAllocationRules((prev) => [
      ...prev,
      { segment: '', priority: prev.length + 1, allocationPct: 0, minFloorQty: 0 },
    ]);
  };

  const handleRemoveRule = (index) => {
    setAllocationRules((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSubmitRules = async () => {
    try {
      setSubmittingRules(true);
      setError(null);
      // In INPUT mode, rules are submitted as manual policy input.
      // The backend treats this as a customer-provided allocation policy.
      // For now we log and show success; backend endpoint TBD.
      console.log('Submitting allocation rules:', allocationRules);
      setSuccessMsg('Allocation rules submitted successfully.');
    } catch (err) {
      console.error('Failed to submit allocation rules', err);
      setError('Failed to submit allocation rules.');
    } finally {
      setSubmittingRules(false);
    }
  };

  // -------------------------------------------------------------------------
  // Derived values
  // -------------------------------------------------------------------------
  const totalPct = allocationRules.reduce((sum, r) => sum + (Number(r.allocationPct) || 0), 0);

  const pendingCount = worklist.filter(
    (c) => c.status === 'proposed' || c.status === 'pending_review'
  ).length;

  const violationCount = worklist.reduce(
    (sum, c) => sum + (c.integrity_violations?.length || 0),
    0
  );

  const riskCount = worklist.reduce(
    (sum, c) => sum + (c.risk_flags?.length || 0),
    0
  );

  // -------------------------------------------------------------------------
  // Render: loading guard
  // -------------------------------------------------------------------------
  if (modeLoading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" p={6}>
        <CircularProgress />
      </Box>
    );
  }

  // -------------------------------------------------------------------------
  // Tab labels (dynamic based on mode)
  // -------------------------------------------------------------------------
  const tabLabel0 = mode === 'input' ? 'Manual Input' : 'Worklist';

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  return (
    <Box sx={{ p: 3 }}>
      {/* Page Header */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
        <Box>
          <Typography variant="h5" gutterBottom>
            Allocation Agent Worklist
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {mode === 'input'
              ? 'Manually define allocation rules for customer segments. These rules replace AI-generated allocations.'
              : 'Review and approve Allocation Commits generated by the Allocation Agent before execution.'}
          </Typography>
        </Box>
        <LayerModeIndicator layer="allocation_agent" mode={mode} />
      </Box>

      {/* Alerts */}
      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      {successMsg && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSuccessMsg(null)}>
          {successMsg}
        </Alert>
      )}

      {/* Tabs */}
      <Paper variant="outlined" sx={{ mb: 3 }}>
        <Tabs
          value={activeTab}
          onChange={(_, v) => setActiveTab(v)}
          indicatorColor="primary"
          textColor="primary"
          variant="fullWidth"
        >
          <Tab label={tabLabel0} />
          <Tab label="Performance" />
          <Tab label="Lineage" />
          <Tab label="Timeline" />
        </Tabs>
      </Paper>

      {/* ================================================================= */}
      {/* TAB 0 - Worklist (ACTIVE) or Manual Input (INPUT)                 */}
      {/* ================================================================= */}
      {activeTab === 0 && mode === 'active' && (
        <Box>
          {/* Summary Bar */}
          <Box display="flex" gap={2} mb={3} flexWrap="wrap">
            <Chip
              label={`${worklist.length} Total Commits`}
              variant="outlined"
            />
            <Chip
              label={`${pendingCount} Pending Review`}
              color="warning"
              variant={pendingCount > 0 ? 'filled' : 'outlined'}
            />
            {violationCount > 0 && (
              <Chip label={`${violationCount} Violations`} color="error" />
            )}
            {riskCount > 0 && (
              <Chip label={`${riskCount} Risks`} color="warning" variant="outlined" />
            )}
            <Box flexGrow={1} />
            <Button
              variant="outlined"
              size="small"
              onClick={loadWorklist}
              disabled={worklistLoading}
            >
              Refresh
            </Button>
          </Box>

          {worklistLoading ? (
            <Box display="flex" justifyContent="center" p={4}>
              <CircularProgress />
            </Box>
          ) : worklist.length === 0 ? (
            <Alert severity="info">
              No allocation commits found. Run the cascade to generate commits.
            </Alert>
          ) : (
            <Grid container spacing={3}>
              {/* Worklist Table */}
              <Grid item xs={12} md={selectedCommitData ? 6 : 12}>
                <TableContainer component={Paper} variant="outlined">
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>AC Hash</TableCell>
                        <TableCell>Created</TableCell>
                        <TableCell>Status</TableCell>
                        <TableCell align="center">Violations</TableCell>
                        <TableCell align="center">Risks</TableCell>
                        <TableCell align="center">Actions</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {worklist.map((commit) => (
                        <TableRow
                          key={commit.id}
                          hover
                          selected={selectedCommit === commit.id}
                          sx={{ cursor: 'pointer' }}
                          onClick={() => handleViewCommit(commit.id)}
                        >
                          <TableCell>
                            <Typography variant="body2" fontWeight="medium">
                              AC-{commit.hash?.slice(0, 8) || commit.id}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <Typography variant="caption">
                              {commit.created_at
                                ? new Date(commit.created_at).toLocaleString()
                                : '--'}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <Chip
                              label={commit.status?.replace(/_/g, ' ') || 'unknown'}
                              size="small"
                              color={STATUS_COLORS[commit.status] || 'default'}
                            />
                          </TableCell>
                          <TableCell align="center">
                            {(commit.integrity_violations?.length || 0) > 0 ? (
                              <Chip
                                label={commit.integrity_violations.length}
                                size="small"
                                color="error"
                              />
                            ) : (
                              <Typography variant="caption" color="text.secondary">0</Typography>
                            )}
                          </TableCell>
                          <TableCell align="center">
                            {(commit.risk_flags?.length || 0) > 0 ? (
                              <Chip
                                label={commit.risk_flags.length}
                                size="small"
                                color="warning"
                                variant="outlined"
                              />
                            ) : (
                              <Typography variant="caption" color="text.secondary">0</Typography>
                            )}
                          </TableCell>
                          <TableCell align="center">
                            <Button
                              size="small"
                              variant="outlined"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleViewCommit(commit.id);
                              }}
                            >
                              View
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </Grid>

              {/* Detail Panel */}
              {selectedCommitData && (
                <Grid item xs={12} md={6}>
                  {commitLoading ? (
                    <Box display="flex" justifyContent="center" p={4}>
                      <CircularProgress />
                    </Box>
                  ) : (
                    <Box>
                      <CommitReviewPanel
                        commit={selectedCommitData}
                        commitType="allocation"
                        onAccept={handleAccept}
                        onOverride={handleOverride}
                        onReject={handleReject}
                        onSubmit={handleSubmit}
                        loading={actionLoading}
                      />

                      <Box mt={2}>
                        <AskWhyPanel
                          commitId={selectedCommitData.id}
                          commitType="allocation"
                        />
                      </Box>
                    </Box>
                  )}
                </Grid>
              )}
            </Grid>
          )}
        </Box>
      )}

      {/* ================================================================= */}
      {/* TAB 0 - Manual Input (INPUT mode)                                 */}
      {/* ================================================================= */}
      {activeTab === 0 && mode === 'input' && (
        <Box>
          <Alert severity="info" sx={{ mb: 3 }}>
            This layer is in INPUT mode. Define allocation rules manually to
            control how supply is distributed across customer segments. These
            rules serve as input to the execution layer.
          </Alert>

          <Paper variant="outlined" sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              Allocation Rules
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Define priority, allocation percentage, and minimum floor quantity
              for each customer segment. Total allocation percentage should sum
              to 100%.
            </Typography>

            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Segment</TableCell>
                    <TableCell align="center">Priority</TableCell>
                    <TableCell align="center">Allocation %</TableCell>
                    <TableCell align="center">Min Floor Qty</TableCell>
                    <TableCell align="center">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {allocationRules.map((rule, idx) => (
                    <TableRow key={idx}>
                      <TableCell>
                        <TextField
                          select={DEFAULT_SEGMENTS.includes(rule.segment) || rule.segment === ''}
                          size="small"
                          value={rule.segment}
                          onChange={(e) => handleRuleChange(idx, 'segment', e.target.value)}
                          sx={{ minWidth: 160 }}
                          {...(!DEFAULT_SEGMENTS.includes(rule.segment) && rule.segment !== '' ? {} : {})}
                        >
                          {DEFAULT_SEGMENTS.map((s) => (
                            <MenuItem key={s} value={s}>
                              {s.charAt(0).toUpperCase() + s.slice(1)}
                            </MenuItem>
                          ))}
                          <MenuItem value="">
                            <em>Custom...</em>
                          </MenuItem>
                        </TextField>
                      </TableCell>
                      <TableCell align="center">
                        <TextField
                          type="number"
                          size="small"
                          value={rule.priority}
                          onChange={(e) =>
                            handleRuleChange(idx, 'priority', parseInt(e.target.value, 10) || 0)
                          }
                          inputProps={{ min: 1, max: 99 }}
                          sx={{ width: 80 }}
                        />
                      </TableCell>
                      <TableCell align="center">
                        <Box display="flex" alignItems="center" gap={1}>
                          <Slider
                            value={rule.allocationPct}
                            onChange={(_, val) => handleRuleChange(idx, 'allocationPct', val)}
                            min={0}
                            max={100}
                            step={1}
                            sx={{ width: 120 }}
                          />
                          <Typography variant="body2" sx={{ minWidth: 36, textAlign: 'right' }}>
                            {rule.allocationPct}%
                          </Typography>
                        </Box>
                      </TableCell>
                      <TableCell align="center">
                        <TextField
                          type="number"
                          size="small"
                          value={rule.minFloorQty}
                          onChange={(e) =>
                            handleRuleChange(idx, 'minFloorQty', parseInt(e.target.value, 10) || 0)
                          }
                          inputProps={{ min: 0 }}
                          sx={{ width: 100 }}
                        />
                      </TableCell>
                      <TableCell align="center">
                        <Button
                          size="small"
                          color="error"
                          onClick={() => handleRemoveRule(idx)}
                          disabled={allocationRules.length <= 1}
                        >
                          Remove
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>

            {/* Total percentage indicator */}
            <Box display="flex" alignItems="center" gap={2} mt={2}>
              <Typography variant="body2" color="text.secondary">
                Total Allocation:
              </Typography>
              <Chip
                label={`${totalPct}%`}
                color={totalPct === 100 ? 'success' : 'warning'}
                size="small"
              />
              {totalPct !== 100 && (
                <Typography variant="caption" color="warning.main">
                  Total should equal 100%
                </Typography>
              )}
            </Box>

            <Divider sx={{ my: 3 }} />

            <Box display="flex" justifyContent="space-between">
              <Button variant="outlined" onClick={handleAddRule}>
                Add Rule
              </Button>
              <Button
                variant="contained"
                onClick={handleSubmitRules}
                disabled={submittingRules || totalPct !== 100}
              >
                {submittingRules ? 'Submitting...' : 'Submit Allocation Rules'}
              </Button>
            </Box>
          </Paper>
        </Box>
      )}

      {/* Disabled mode message */}
      {activeTab === 0 && mode === 'disabled' && (
        <Alert severity="warning">
          The Allocation Agent layer is not available in your current package.
          Contact sales to upgrade.
        </Alert>
      )}

      {/* ================================================================= */}
      {/* TAB 1 - Performance                                               */}
      {/* ================================================================= */}
      {activeTab === 1 && (
        <Box>
          <Typography variant="h6" gutterBottom>
            Allocation Agent Performance
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Agent Performance Score, Touchless Rate, Human Override Rate,
            and other metrics for the Allocation Agent.
          </Typography>
          <PerformanceMetricsPanel configId={configId} agentType="allocation_agent" />
        </Box>
      )}

      {/* ================================================================= */}
      {/* TAB 2 - Lineage                                                   */}
      {/* ================================================================= */}
      {activeTab === 2 && (
        <Box>
          <Typography variant="h6" gutterBottom>
            Artifact Lineage
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Trace the hash-chain lineage for any selected Allocation Commit.
            See upstream dependencies (Policy Envelope, Supply Baseline Pack,
            Supply Commit) and downstream execution artifacts.
          </Typography>

          {selectedCommitId ? (
            <ArtifactLineage
              artifactType="allocation_commit"
              artifactId={selectedCommitId}
            />
          ) : (
            <Alert severity="info">
              Select a commit from the Worklist tab to view its lineage.
            </Alert>
          )}
        </Box>
      )}

      {/* ================================================================= */}
      {/* TAB 3 - Allocation Timeline                                       */}
      {/* ================================================================= */}
      {activeTab === 3 && (
        <AllocationTimelineTab configId={configId} tenantId={tenantId} />
      )}
    </Box>
  );
};

export default AllocationWorklistPage;
