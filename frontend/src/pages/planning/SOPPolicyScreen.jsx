/**
 * S&OP Policy Screen
 *
 * Dual-mode screen for S&OP policy parameters.
 *
 * FULL mode: Displays agent-optimized targets, enables what-if scenarios
 * INPUT mode: Accepts customer-provided parameters from their existing S&OP process
 *
 * Same UI, different source of values.
 */

import React, { useState, useEffect } from 'react';
import {
  Box,
  Paper,
  Typography,
  Grid,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Button,
  Chip,
  Alert,
  IconButton,
  Tooltip,
  Card,
  CardContent,
  CardHeader,
  Divider,
  CircularProgress,
} from '@mui/material';
import {
  PlayArrow as SimulateIcon,
  Check as AcceptIcon,
  Edit as EditIcon,
  Info as InfoIcon,
  Warning as WarningIcon,
  TrendingUp as TrendingUpIcon,
} from '@mui/icons-material';
import { api } from '../../services/api';

const SOPPolicyScreen = ({ configId, tenantId, mode = 'INPUT' }) => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [envelope, setEnvelope] = useState(null);
  const [editMode, setEditMode] = useState(mode === 'INPUT');
  const [feedbackSignals, setFeedbackSignals] = useState([]);

  // Form state
  const [serviceTiers, setServiceTiers] = useState([
    { segment: 'strategic', otif_floor: 0.99, fill_rate_target: 0.99 },
    { segment: 'standard', otif_floor: 0.95, fill_rate_target: 0.98 },
    { segment: 'transactional', otif_floor: 0.90, fill_rate_target: 0.95 },
  ]);

  const [categoryPolicies, setCategoryPolicies] = useState([
    { category: 'frozen_proteins', safety_stock_wos: 2.0, dos_ceiling: 21, expedite_cap: 15000 },
    { category: 'refrigerated_dairy', safety_stock_wos: 1.5, dos_ceiling: 14, expedite_cap: 10000 },
    { category: 'dry_pantry', safety_stock_wos: 3.0, dos_ceiling: 45, expedite_cap: 5000 },
    { category: 'frozen_desserts', safety_stock_wos: 2.0, dos_ceiling: 28, expedite_cap: 8000 },
    { category: 'beverages', safety_stock_wos: 2.5, dos_ceiling: 35, expedite_cap: 6000 },
  ]);

  const [financialGuardrails, setFinancialGuardrails] = useState({
    total_inventory_cap: 2500000,
    gmroi_target: 3.0,
    max_expedite_total: 50000,
  });

  const isInputMode = mode === 'INPUT';
  const isFullMode = mode === 'FULL';

  useEffect(() => {
    loadPolicyEnvelope();
    if (!isInputMode) {
      loadFeedbackSignals();
    }
  }, [configId]);

  const loadPolicyEnvelope = async () => {
    try {
      setLoading(true);
      const response = await api.get(`/planning-cascade/policy-envelope/active/${configId}`);
      if (response.data) {
        setEnvelope(response.data);
        // Populate form from envelope
        if (response.data.otif_floors) {
          setServiceTiers(Object.entries(response.data.otif_floors).map(([segment, floor]) => ({
            segment,
            otif_floor: floor,
            fill_rate_target: 0.98,
          })));
        }
        if (response.data.safety_stock_targets && response.data.dos_ceilings && response.data.expedite_caps) {
          setCategoryPolicies(Object.entries(response.data.safety_stock_targets).map(([category, wos]) => ({
            category,
            safety_stock_wos: wos,
            dos_ceiling: response.data.dos_ceilings[category] || 30,
            expedite_cap: response.data.expedite_caps[category] || 10000,
          })));
        }
      }
    } catch (error) {
      console.log('No active policy envelope');
    } finally {
      setLoading(false);
    }
  };

  const loadFeedbackSignals = async () => {
    try {
      const response = await api.get(`/planning-cascade/policy-envelope/feedback/${configId}`);
      setFeedbackSignals(response.data.signals || []);
    } catch (error) {
      console.error('Failed to load feedback signals', error);
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      const response = await api.post('/planning-cascade/policy-envelope', {
        config_id: configId,
        tenant_id: tenantId,
        mode: mode,
        service_tiers: serviceTiers,
        category_policies: categoryPolicies,
        total_inventory_cap: financialGuardrails.total_inventory_cap,
        gmroi_target: financialGuardrails.gmroi_target,
      });
      setEnvelope(response.data);
      setEditMode(false);
    } catch (error) {
      console.error('Failed to save policy envelope', error);
    } finally {
      setSaving(false);
    }
  };

  const handleRunWhatIf = async () => {
    // In FULL mode, run what-if simulation
    alert('What-if simulation would run here (FULL mode only)');
  };

  const updateServiceTier = (index, field, value) => {
    const updated = [...serviceTiers];
    updated[index][field] = parseFloat(value);
    setServiceTiers(updated);
  };

  const updateCategoryPolicy = (index, field, value) => {
    const updated = [...categoryPolicies];
    updated[index][field] = field === 'category' ? value : parseFloat(value);
    setCategoryPolicies(updated);
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" p={4}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      {/* Header */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Box>
          <Typography variant="h5">
            {isInputMode ? 'S&OP Policy Parameters' : 'S&OP Policy Optimization'}
          </Typography>
          <Typography variant="body2" color="textSecondary">
            {isInputMode
              ? 'Enter your policy targets. The Supply and Allocation Agents will enforce these constraints.'
              : 'Agent-optimized targets based on simulation. Review and adjust as needed.'}
          </Typography>
        </Box>
        <Box>
          <Chip
            label={isInputMode ? 'INPUT MODE' : 'FULL MODE'}
            color={isInputMode ? 'default' : 'primary'}
            sx={{ mr: 2 }}
          />
          {envelope && (
            <Chip
              label={`Envelope: ${envelope.hash?.slice(0, 8)}`}
              variant="outlined"
              size="small"
            />
          )}
        </Box>
      </Box>

      {/* Feedback Signals Alert (FULL mode) */}
      {isFullMode && feedbackSignals.length > 0 && (
        <Alert severity="warning" sx={{ mb: 3 }}>
          <Typography variant="subtitle2">
            {feedbackSignals.length} feed-back signal(s) suggest parameter re-tuning
          </Typography>
          {feedbackSignals.slice(0, 3).map((signal, i) => (
            <Typography key={i} variant="body2">
              {signal.signal_type}: {signal.metric_name} = {signal.metric_value?.toFixed(2)}
              {signal.threshold && ` (threshold: ${signal.threshold})`}
            </Typography>
          ))}
        </Alert>
      )}

      <Grid container spacing={3}>
        {/* Service Level Targets */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardHeader
              title="Service Level Targets"
              subheader="OTIF floors by customer segment"
              action={
                isFullMode && (
                  <Tooltip title="Agent recommendations available">
                    <TrendingUpIcon color="primary" />
                  </Tooltip>
                )
              }
            />
            <CardContent>
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Segment</TableCell>
                      <TableCell>OTIF Floor</TableCell>
                      <TableCell>Fill Rate Target</TableCell>
                      {isFullMode && <TableCell>Recommendation</TableCell>}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {serviceTiers.map((tier, index) => (
                      <TableRow key={tier.segment}>
                        <TableCell>
                          <Chip
                            label={tier.segment}
                            size="small"
                            color={tier.segment === 'strategic' ? 'primary' : 'default'}
                          />
                        </TableCell>
                        <TableCell>
                          {editMode ? (
                            <TextField
                              type="number"
                              size="small"
                              value={tier.otif_floor}
                              onChange={(e) => updateServiceTier(index, 'otif_floor', e.target.value)}
                              inputProps={{ min: 0, max: 1, step: 0.01 }}
                              sx={{ width: 80 }}
                            />
                          ) : (
                            <Typography>{(tier.otif_floor * 100).toFixed(0)}%</Typography>
                          )}
                        </TableCell>
                        <TableCell>
                          {editMode ? (
                            <TextField
                              type="number"
                              size="small"
                              value={tier.fill_rate_target}
                              onChange={(e) => updateServiceTier(index, 'fill_rate_target', e.target.value)}
                              inputProps={{ min: 0, max: 1, step: 0.01 }}
                              sx={{ width: 80 }}
                            />
                          ) : (
                            <Typography>{(tier.fill_rate_target * 100).toFixed(0)}%</Typography>
                          )}
                        </TableCell>
                        {isFullMode && (
                          <TableCell>
                            <Tooltip title="Agent suggests increasing to 99.5%">
                              <Chip label="+0.5%" size="small" color="info" />
                            </Tooltip>
                          </TableCell>
                        )}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </Grid>

        {/* Safety Stock & DOS Targets */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardHeader
              title="Inventory Policies by Category"
              subheader="Safety stock (WOS), DOS ceiling, expedite caps"
            />
            <CardContent>
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Category</TableCell>
                      <TableCell>SS (WOS)</TableCell>
                      <TableCell>DOS Ceiling</TableCell>
                      <TableCell>Expedite Cap</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {categoryPolicies.map((policy, index) => (
                      <TableRow key={policy.category}>
                        <TableCell>
                          <Typography variant="body2">
                            {policy.category.replace(/_/g, ' ')}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          {editMode ? (
                            <TextField
                              type="number"
                              size="small"
                              value={policy.safety_stock_wos}
                              onChange={(e) => updateCategoryPolicy(index, 'safety_stock_wos', e.target.value)}
                              inputProps={{ min: 0, step: 0.5 }}
                              sx={{ width: 70 }}
                            />
                          ) : (
                            <Typography>{policy.safety_stock_wos}</Typography>
                          )}
                        </TableCell>
                        <TableCell>
                          {editMode ? (
                            <TextField
                              type="number"
                              size="small"
                              value={policy.dos_ceiling}
                              onChange={(e) => updateCategoryPolicy(index, 'dos_ceiling', e.target.value)}
                              inputProps={{ min: 1 }}
                              sx={{ width: 70 }}
                            />
                          ) : (
                            <Typography>{policy.dos_ceiling} days</Typography>
                          )}
                        </TableCell>
                        <TableCell>
                          {editMode ? (
                            <TextField
                              type="number"
                              size="small"
                              value={policy.expedite_cap}
                              onChange={(e) => updateCategoryPolicy(index, 'expedite_cap', e.target.value)}
                              inputProps={{ min: 0, step: 1000 }}
                              sx={{ width: 100 }}
                            />
                          ) : (
                            <Typography>${policy.expedite_cap.toLocaleString()}</Typography>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </Grid>

        {/* Financial Guardrails */}
        <Grid item xs={12}>
          <Card>
            <CardHeader title="Financial Guardrails" />
            <CardContent>
              <Grid container spacing={3}>
                <Grid item xs={12} md={4}>
                  <TextField
                    fullWidth
                    label="Total Inventory Cap ($)"
                    type="number"
                    value={financialGuardrails.total_inventory_cap}
                    onChange={(e) => setFinancialGuardrails({
                      ...financialGuardrails,
                      total_inventory_cap: parseFloat(e.target.value),
                    })}
                    disabled={!editMode}
                    InputProps={{
                      startAdornment: '$',
                    }}
                  />
                </Grid>
                <Grid item xs={12} md={4}>
                  <TextField
                    fullWidth
                    label="GMROI Target"
                    type="number"
                    value={financialGuardrails.gmroi_target}
                    onChange={(e) => setFinancialGuardrails({
                      ...financialGuardrails,
                      gmroi_target: parseFloat(e.target.value),
                    })}
                    disabled={!editMode}
                    inputProps={{ step: 0.1 }}
                  />
                </Grid>
                <Grid item xs={12} md={4}>
                  <TextField
                    fullWidth
                    label="Max Expedite Total ($/month)"
                    type="number"
                    value={financialGuardrails.max_expedite_total}
                    onChange={(e) => setFinancialGuardrails({
                      ...financialGuardrails,
                      max_expedite_total: parseFloat(e.target.value),
                    })}
                    disabled={!editMode}
                    InputProps={{
                      startAdornment: '$',
                    }}
                  />
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Actions */}
      <Box display="flex" justifyContent="flex-end" mt={3} gap={2}>
        {isInputMode ? (
          <>
            {!editMode && (
              <Button
                variant="outlined"
                startIcon={<EditIcon />}
                onClick={() => setEditMode(true)}
              >
                Edit Parameters
              </Button>
            )}
            {editMode && (
              <>
                <Button onClick={() => setEditMode(false)}>
                  Cancel
                </Button>
                <Button
                  variant="contained"
                  onClick={handleSave}
                  disabled={saving}
                >
                  {saving ? 'Saving...' : 'Save Policy Parameters'}
                </Button>
              </>
            )}
          </>
        ) : (
          <>
            <Button
              variant="outlined"
              startIcon={<SimulateIcon />}
              onClick={handleRunWhatIf}
            >
              Run What-If Scenario
            </Button>
            <Button
              variant="contained"
              startIcon={<AcceptIcon />}
              onClick={handleSave}
              disabled={saving}
            >
              Accept Agent Recommendations
            </Button>
          </>
        )}
      </Box>

      {/* Upgrade hint for INPUT mode */}
      {isInputMode && (
        <Box mt={3}>
          <Alert severity="info">
            <Typography variant="caption">
              Upgrade to S&OP layer to enable simulation-based optimization and what-if scenarios
            </Typography>
          </Alert>
        </Box>
      )}
    </Box>
  );
};

export default SOPPolicyScreen;
