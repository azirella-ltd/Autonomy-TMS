/**
 * Allocation Timeline Tab
 *
 * Stacked bar chart of allocations by priority class (P1-P5) across
 * daily time buckets, plus an inline-editable override table.
 * Used by the allocmgr to inspect and fine-tune tGNN-generated allocations.
 *
 * Shows the active S&OP Policy Envelope as context (guardrails, not hard
 * constraints). The allocmgr may violate guardrails but must provide a reason.
 */
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Box,
  Paper,
  Typography,
  TextField,
  MenuItem,
  Button,
  Alert,
  Chip,
  CircularProgress,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Collapse,
  IconButton,
  Divider,
} from '@mui/material';
import {
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  WarningAmber as WarningIcon,
} from '@mui/icons-material';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts';
import { getAllocationTimeline, submitAllocationOverrides } from '../../services/planningCascadeApi';
import { api } from '../../services/api';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PRIORITIES = [1, 2, 3, 4, 5];

const PRIORITY_COLORS = {
  P1: '#1565c0',
  P2: '#2e7d32',
  P3: '#f57c00',
  P4: '#7b1fa2',
  P5: '#c62828',
};

const PRIORITY_LABELS = {
  P1: 'P1 - Key Account',
  P2: 'P2 - Contract',
  P3: 'P3 - Retail',
  P4: 'P4 - Wholesale',
  P5: 'P5 - Spot Market',
};

// Maps priority tiers to policy envelope segments
const PRIORITY_TO_SEGMENT = {
  1: 'key_account',
  2: 'contract',
  3: 'retail',
  4: 'wholesale',
  5: 'spot_market',
};

const formatDate = (isoDate) => {
  const d = new Date(isoDate + 'T00:00:00');
  return `${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')}`;
};

const formatPct = (val) => `${Math.round(val * 100)}%`;

// ---------------------------------------------------------------------------
// Custom Tooltip
// ---------------------------------------------------------------------------

const TimelineTooltip = ({ active, payload, label }) => {
  if (!active || !payload || payload.length === 0) return null;
  const total = payload.reduce((sum, p) => sum + (p.value || 0), 0);
  return (
    <Paper sx={{ p: 1.5, maxWidth: 220 }} elevation={3}>
      <Typography variant="caption" fontWeight="bold" display="block" gutterBottom>
        {label}
      </Typography>
      {payload.map((p) => (
        <Box key={p.dataKey} display="flex" justifyContent="space-between" gap={2}>
          <Typography variant="caption" sx={{ color: p.fill }}>
            {p.name}
          </Typography>
          <Typography variant="caption" fontWeight="medium">
            {Math.round(p.value)}
          </Typography>
        </Box>
      ))}
      <Box display="flex" justifyContent="space-between" gap={2} mt={0.5} borderTop={1} borderColor="divider" pt={0.5}>
        <Typography variant="caption" fontWeight="bold">Total</Typography>
        <Typography variant="caption" fontWeight="bold">{Math.round(total)}</Typography>
      </Box>
    </Paper>
  );
};

// ---------------------------------------------------------------------------
// S&OP Policy Context Panel
// ---------------------------------------------------------------------------

const PolicyContextPanel = ({ policy }) => {
  const [expanded, setExpanded] = useState(true);

  if (!policy) return null;

  const sourceLabels = {
    CUSTOMER_INPUT: 'Customer Input',
    customer_input: 'Customer Input',
    AUTONOMY_SIM: 'Autonomy Simulation',
    autonomy_sim: 'Autonomy Simulation',
    SYSTEM_DEFAULT: 'System Default',
    system_default: 'System Default',
  };

  return (
    <Paper variant="outlined" sx={{ mb: 3 }}>
      <Box
        display="flex"
        alignItems="center"
        justifyContent="space-between"
        px={2}
        py={1}
        sx={{ cursor: 'pointer' }}
        onClick={() => setExpanded((prev) => !prev)}
      >
        <Box display="flex" alignItems="center" gap={1}>
          <Typography variant="subtitle2">
            S&OP Policy Context
          </Typography>
          <Chip
            label={sourceLabels[policy.generated_by] || policy.generated_by || 'Unknown'}
            size="small"
            variant="outlined"
            color="info"
          />
          {policy.effective_date && (
            <Typography variant="caption" color="text.secondary">
              Effective: {policy.effective_date}
            </Typography>
          )}
        </Box>
        <IconButton size="small">
          {expanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
        </IconButton>
      </Box>
      <Collapse in={expanded}>
        <Divider />
        <Box px={2} py={1.5} display="flex" gap={4} flexWrap="wrap">
          {/* Allocation Reserves */}
          {policy.allocation_reserves && (
            <Box>
              <Typography variant="caption" color="text.secondary" fontWeight="bold" gutterBottom display="block">
                Allocation Reserves (% of supply)
              </Typography>
              {Object.entries(policy.allocation_reserves).map(([seg, pct]) => (
                <Box key={seg} display="flex" justifyContent="space-between" gap={2} minWidth={180}>
                  <Typography variant="caption" sx={{ textTransform: 'capitalize' }}>
                    {seg.replace('_', ' ')}
                  </Typography>
                  <Typography variant="caption" fontWeight="medium">{formatPct(pct)}</Typography>
                </Box>
              ))}
            </Box>
          )}

          {/* OTIF Floors */}
          {policy.otif_floors && (
            <Box>
              <Typography variant="caption" color="text.secondary" fontWeight="bold" gutterBottom display="block">
                OTIF Floors (min service level)
              </Typography>
              {Object.entries(policy.otif_floors).map(([seg, pct]) => (
                <Box key={seg} display="flex" justifyContent="space-between" gap={2} minWidth={180}>
                  <Typography variant="caption" sx={{ textTransform: 'capitalize' }}>
                    {seg.replace('_', ' ')}
                  </Typography>
                  <Typography variant="caption" fontWeight="medium">{formatPct(pct)}</Typography>
                </Box>
              ))}
            </Box>
          )}

          {/* Safety Stock */}
          {policy.safety_stock_targets && (
            <Box>
              <Typography variant="caption" color="text.secondary" fontWeight="bold" gutterBottom display="block">
                Safety Stock (weeks of supply)
              </Typography>
              {Object.entries(policy.safety_stock_targets).map(([cat, wos]) => (
                <Box key={cat} display="flex" justifyContent="space-between" gap={2} minWidth={180}>
                  <Typography variant="caption" sx={{ textTransform: 'capitalize' }}>
                    {cat.replace('_', ' ')}
                  </Typography>
                  <Typography variant="caption" fontWeight="medium">{wos} WOS</Typography>
                </Box>
              ))}
            </Box>
          )}

          {/* Financial */}
          {(policy.total_inventory_cap || policy.gmroi_target) && (
            <Box>
              <Typography variant="caption" color="text.secondary" fontWeight="bold" gutterBottom display="block">
                Financial Guardrails
              </Typography>
              {policy.total_inventory_cap && (
                <Box display="flex" justifyContent="space-between" gap={2} minWidth={180}>
                  <Typography variant="caption">Inventory Cap</Typography>
                  <Typography variant="caption" fontWeight="medium">
                    ${policy.total_inventory_cap.toLocaleString()}
                  </Typography>
                </Box>
              )}
              {policy.gmroi_target && (
                <Box display="flex" justifyContent="space-between" gap={2} minWidth={180}>
                  <Typography variant="caption">GMROI Target</Typography>
                  <Typography variant="caption" fontWeight="medium">{policy.gmroi_target}x</Typography>
                </Box>
              )}
            </Box>
          )}
        </Box>
        <Box px={2} pb={1.5}>
          <Typography variant="caption" color="text.secondary" sx={{ fontStyle: 'italic' }}>
            These are S&OP-level guardrails, not hard constraints. You may override allocations outside
            these bounds — a reason is required when doing so.
          </Typography>
        </Box>
      </Collapse>
    </Paper>
  );
};

// ---------------------------------------------------------------------------
// AllocationTimelineTab
// ---------------------------------------------------------------------------

const AllocationTimelineTab = ({ configId, tenantId }) => {
  // Product & location selection
  const [products, setProducts] = useState([]);
  const [locations, setLocations] = useState([]);
  const [selectedProduct, setSelectedProduct] = useState('');
  const [selectedLocation, setSelectedLocation] = useState('');

  // Timeline data
  const [timelineData, setTimelineData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Inline editing
  const [editedCells, setEditedCells] = useState({});
  const [editingCell, setEditingCell] = useState(null);
  const [editValue, setEditValue] = useState('');

  // Save
  const [saving, setSaving] = useState(false);
  const [successMsg, setSuccessMsg] = useState(null);
  const [reasonDialog, setReasonDialog] = useState(false);
  const [overrideReason, setOverrideReason] = useState('');

  // -------------------------------------------------------------------------
  // Load product and location lists
  // -------------------------------------------------------------------------
  useEffect(() => {
    const loadOptions = async () => {
      try {
        // Fetch products for this config
        const prodRes = await api.get(`/supply-chain-config/${configId}/products`);
        const prods = prodRes.data || [];
        setProducts(prods);

        // Fetch sites for this config (inventory type only)
        const siteRes = await api.get(`/supply-chain-config/${configId}/sites`);
        const sites = (siteRes.data || []).filter(
          (s) => s.master_type === 'INVENTORY' || s.dag_type === 'INVENTORY'
        );
        setLocations(sites);

        // Auto-select first if available
        if (prods.length > 0) setSelectedProduct(prods[0].id || prods[0].product_id || '');
        if (sites.length > 0) setSelectedLocation(String(sites[0].id));
      } catch (err) {
        console.error('Failed to load products/sites', err);
        setError('Failed to load product and site options.');
      }
    };
    if (configId) loadOptions();
  }, [configId]);

  // -------------------------------------------------------------------------
  // Load timeline data
  // -------------------------------------------------------------------------
  const loadTimeline = useCallback(async () => {
    if (!selectedProduct || !selectedLocation) return;
    try {
      setLoading(true);
      setError(null);
      const data = await getAllocationTimeline(configId, selectedProduct, selectedLocation);
      setTimelineData(data);
      setEditedCells({});
      setEditingCell(null);
    } catch (err) {
      console.error('Failed to load allocation timeline', err);
      setError('Failed to load allocation timeline. Check that allocation data has been seeded.');
    } finally {
      setLoading(false);
    }
  }, [configId, selectedProduct, selectedLocation]);

  useEffect(() => {
    loadTimeline();
  }, [loadTimeline]);

  // -------------------------------------------------------------------------
  // Guardrail violation detection
  // -------------------------------------------------------------------------
  const violations = useMemo(() => {
    if (!timelineData?.buckets || !timelineData?.policy_context?.allocation_reserves) return {};

    const reserves = timelineData.policy_context.allocation_reserves;
    const result = {};

    for (const bucket of timelineData.buckets) {
      // Compute daily total (original values)
      let originalTotal = 0;
      for (const p of PRIORITIES) {
        originalTotal += bucket[`P${p}`] || 0;
      }
      if (originalTotal === 0) continue;

      for (const p of PRIORITIES) {
        const cellKey = `P${p}_${bucket.date}`;
        if (editedCells[cellKey] === undefined) continue;

        const segment = PRIORITY_TO_SEGMENT[p];
        const reservePct = reserves[segment];
        if (reservePct === undefined) continue;

        // Recompute the day's total with edits applied
        let editedTotal = 0;
        for (const q of PRIORITIES) {
          const qKey = `P${q}_${bucket.date}`;
          editedTotal += editedCells[qKey] !== undefined ? editedCells[qKey] : (bucket[`P${q}`] || 0);
        }
        if (editedTotal === 0) continue;

        const editedShare = editedCells[cellKey] / editedTotal;
        if (editedShare < reservePct) {
          result[cellKey] = {
            segment,
            expected: reservePct,
            actual: editedShare,
          };
        }
      }
    }
    return result;
  }, [editedCells, timelineData]);

  const hasViolations = Object.keys(violations).length > 0;

  // -------------------------------------------------------------------------
  // Inline editing handlers
  // -------------------------------------------------------------------------
  const handleCellClick = (cellKey, currentValue) => {
    setEditingCell(cellKey);
    setEditValue(String(Math.round(currentValue)));
  };

  const handleEditSave = (cellKey) => {
    const val = parseFloat(editValue);
    if (isNaN(val) || val < 0) {
      setEditingCell(null);
      return;
    }
    setEditedCells((prev) => ({ ...prev, [cellKey]: val }));
    setEditingCell(null);
    setEditValue('');
  };

  const handleEditCancel = () => {
    setEditingCell(null);
    setEditValue('');
  };

  const handleDiscard = () => {
    setEditedCells({});
    setEditingCell(null);
  };

  // -------------------------------------------------------------------------
  // Save overrides
  // -------------------------------------------------------------------------
  const handleSaveClick = () => {
    setReasonDialog(true);
  };

  const handleSaveConfirm = async () => {
    setReasonDialog(false);
    try {
      setSaving(true);
      setError(null);

      // Build override cells from editedCells: "P{n}_{date}" => qty
      const overrides = Object.entries(editedCells).map(([key, qty]) => {
        const [pStr, ...dateParts] = key.split('_');
        const priority = parseInt(pStr.replace('P', ''), 10);
        const dateStr = dateParts.join('_');
        return { priority, date: dateStr, allocated_qty: qty };
      });

      await submitAllocationOverrides(configId, selectedProduct, selectedLocation, overrides, overrideReason || null);
      setSuccessMsg(`${overrides.length} allocation override(s) saved.`);
      setEditedCells({});
      setOverrideReason('');
      // Reload to reflect changes
      loadTimeline();
    } catch (err) {
      console.error('Failed to save overrides', err);
      setError('Failed to save allocation overrides.');
    } finally {
      setSaving(false);
    }
  };

  // -------------------------------------------------------------------------
  // Build chart data (merge original + edits for live preview)
  // -------------------------------------------------------------------------
  const chartData = timelineData?.buckets?.map((bucket) => {
    const row = { date: formatDate(bucket.date), rawDate: bucket.date, is_today: bucket.is_today };
    for (const p of PRIORITIES) {
      const cellKey = `P${p}_${bucket.date}`;
      row[`P${p}`] = editedCells[cellKey] !== undefined ? editedCells[cellKey] : bucket[`P${p}`];
    }
    return row;
  });

  const todayLabel = chartData?.find((d) => d.is_today)?.date;
  const editCount = Object.keys(editedCells).length;
  const violationCount = Object.keys(violations).length;

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  return (
    <Box>
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

      {/* Selectors */}
      <Box display="flex" gap={2} mb={3} flexWrap="wrap" alignItems="center">
        <TextField
          select
          label="Product"
          size="small"
          value={selectedProduct}
          onChange={(e) => setSelectedProduct(e.target.value)}
          sx={{ minWidth: 200 }}
        >
          {products.map((p) => (
            <MenuItem key={p.id || p.product_id} value={p.id || p.product_id}>
              {p.product_name || p.name || p.id || p.product_id}
            </MenuItem>
          ))}
        </TextField>

        <TextField
          select
          label="Location"
          size="small"
          value={selectedLocation}
          onChange={(e) => setSelectedLocation(e.target.value)}
          sx={{ minWidth: 200 }}
        >
          {locations.map((s) => (
            <MenuItem key={s.id} value={String(s.id)}>
              {s.name || s.site_name || String(s.id)}
            </MenuItem>
          ))}
        </TextField>

        <Button variant="outlined" size="small" onClick={loadTimeline} disabled={loading}>
          Refresh
        </Button>

        <Box flexGrow={1} />

        {editCount > 0 && (
          <>
            <Chip label={`${editCount} change${editCount > 1 ? 's' : ''}`} color="warning" size="small" />
            {hasViolations && (
              <Chip
                icon={<WarningIcon />}
                label={`${violationCount} guardrail violation${violationCount > 1 ? 's' : ''}`}
                color="error"
                size="small"
                variant="outlined"
              />
            )}
            <Button variant="outlined" size="small" color="inherit" onClick={handleDiscard}>
              Discard
            </Button>
            <Button variant="contained" size="small" onClick={handleSaveClick} disabled={saving}>
              {saving ? 'Saving...' : 'Save Changes'}
            </Button>
          </>
        )}
      </Box>

      {/* Loading */}
      {loading && (
        <Box display="flex" justifyContent="center" p={6}>
          <CircularProgress />
        </Box>
      )}

      {/* No data */}
      {!loading && !timelineData && !error && (
        <Alert severity="info">
          Select a product and location to view the allocation timeline.
        </Alert>
      )}

      {/* Chart + Table */}
      {!loading && timelineData && chartData && (
        <>
          {/* S&OP Policy Context */}
          <PolicyContextPanel policy={timelineData.policy_context} />

          {/* Stacked Bar Chart */}
          <Paper variant="outlined" sx={{ p: 2, mb: 3 }}>
            <Typography variant="subtitle2" gutterBottom>
              Allocation by Priority Class (Daily)
            </Typography>
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} label={{ value: 'Qty', angle: -90, position: 'insideLeft', style: { fontSize: 11 } }} />
                <Tooltip content={<TimelineTooltip />} />
                <Legend wrapperStyle={{ fontSize: '11px' }} />
                {todayLabel && (
                  <ReferenceLine
                    x={todayLabel}
                    stroke="#ef4444"
                    strokeWidth={2}
                    strokeDasharray="5 5"
                    label={{ value: 'Today', position: 'top', fill: '#ef4444', fontSize: 10 }}
                  />
                )}
                <Bar dataKey="P1" stackId="a" fill={PRIORITY_COLORS.P1} name={PRIORITY_LABELS.P1} />
                <Bar dataKey="P2" stackId="a" fill={PRIORITY_COLORS.P2} name={PRIORITY_LABELS.P2} />
                <Bar dataKey="P3" stackId="a" fill={PRIORITY_COLORS.P3} name={PRIORITY_LABELS.P3} />
                <Bar dataKey="P4" stackId="a" fill={PRIORITY_COLORS.P4} name={PRIORITY_LABELS.P4} />
                <Bar dataKey="P5" stackId="a" fill={PRIORITY_COLORS.P5} name={PRIORITY_LABELS.P5} />
              </BarChart>
            </ResponsiveContainer>
          </Paper>

          {/* Override Table */}
          <Paper variant="outlined">
            <Box px={2} pt={2} pb={1}>
              <Typography variant="subtitle2">
                Override Allocations
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Click any cell to edit. Changes preview instantly in the chart above.
                Cells that breach S&OP allocation reserves are flagged in red.
              </Typography>
            </Box>
            <TableContainer sx={{ maxHeight: 350 }}>
              <Table size="small" stickyHeader>
                <TableHead>
                  <TableRow>
                    <TableCell
                      sx={{
                        minWidth: 150,
                        position: 'sticky',
                        left: 0,
                        zIndex: 3,
                        bgcolor: 'background.paper',
                        fontWeight: 'bold',
                      }}
                    >
                      Priority
                    </TableCell>
                    {timelineData.buckets.map((bucket) => (
                      <TableCell
                        key={bucket.date}
                        align="center"
                        sx={{
                          minWidth: 72,
                          bgcolor: bucket.is_today ? 'warning.light' : 'background.paper',
                          fontWeight: bucket.is_today ? 'bold' : 'normal',
                          fontSize: '0.75rem',
                        }}
                      >
                        {formatDate(bucket.date)}
                        {bucket.is_today && (
                          <Typography variant="caption" display="block" sx={{ fontSize: '0.6rem', color: 'warning.dark' }}>
                            TODAY
                          </Typography>
                        )}
                      </TableCell>
                    ))}
                    {/* Reserve column */}
                    {timelineData.policy_context?.allocation_reserves && (
                      <TableCell
                        align="center"
                        sx={{
                          minWidth: 80,
                          bgcolor: 'grey.100',
                          fontWeight: 'bold',
                          fontSize: '0.7rem',
                        }}
                      >
                        S&OP
                        <Typography variant="caption" display="block" sx={{ fontSize: '0.6rem', color: 'text.secondary' }}>
                          Reserve
                        </Typography>
                      </TableCell>
                    )}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {PRIORITIES.map((priority) => {
                    const segment = PRIORITY_TO_SEGMENT[priority];
                    const reservePct = timelineData.policy_context?.allocation_reserves?.[segment];

                    return (
                      <TableRow key={priority} hover>
                        <TableCell
                          sx={{
                            position: 'sticky',
                            left: 0,
                            zIndex: 2,
                            bgcolor: 'background.paper',
                          }}
                        >
                          <Chip
                            label={PRIORITY_LABELS[`P${priority}`]}
                            size="small"
                            sx={{
                              bgcolor: PRIORITY_COLORS[`P${priority}`],
                              color: 'white',
                              fontWeight: 'bold',
                              fontSize: '0.7rem',
                            }}
                          />
                        </TableCell>
                        {timelineData.buckets.map((bucket) => {
                          const cellKey = `P${priority}_${bucket.date}`;
                          const isEdited = editedCells[cellKey] !== undefined;
                          const value = isEdited ? editedCells[cellKey] : bucket[`P${priority}`];
                          const isEditing = editingCell === cellKey;
                          const violation = violations[cellKey];

                          return (
                            <TableCell
                              key={bucket.date}
                              align="center"
                              onClick={() => !isEditing && handleCellClick(cellKey, value)}
                              sx={{
                                cursor: 'pointer',
                                bgcolor: violation
                                  ? 'rgba(211, 47, 47, 0.12)'
                                  : isEdited
                                  ? 'rgba(245, 158, 11, 0.15)'
                                  : bucket.is_today
                                  ? 'rgba(245, 158, 11, 0.05)'
                                  : 'inherit',
                                fontWeight: isEdited ? 'bold' : 'normal',
                                '&:hover': {
                                  bgcolor: violation
                                    ? 'rgba(211, 47, 47, 0.2)'
                                    : isEdited
                                    ? 'rgba(245, 158, 11, 0.25)'
                                    : 'action.hover',
                                },
                                fontSize: '0.8rem',
                                p: 0.5,
                                borderBottom: violation ? '2px solid #d32f2f' : undefined,
                              }}
                              title={
                                violation
                                  ? `Below S&OP reserve: ${formatPct(violation.actual)} vs ${formatPct(violation.expected)} target for ${violation.segment.replace('_', ' ')}`
                                  : undefined
                              }
                            >
                              {isEditing ? (
                                <TextField
                                  type="number"
                                  size="small"
                                  value={editValue}
                                  onChange={(e) => setEditValue(e.target.value)}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter') handleEditSave(cellKey);
                                    if (e.key === 'Escape') handleEditCancel();
                                  }}
                                  autoFocus
                                  sx={{ width: 65 }}
                                  inputProps={{ min: 0, step: 1, style: { textAlign: 'center', fontSize: '0.8rem', padding: '4px' } }}
                                />
                              ) : (
                                <Box display="flex" alignItems="center" justifyContent="center" gap={0.3}>
                                  {Math.round(value)}
                                  {violation && <WarningIcon sx={{ fontSize: 12, color: 'error.main' }} />}
                                </Box>
                              )}
                            </TableCell>
                          );
                        })}
                        {/* S&OP Reserve % column */}
                        {timelineData.policy_context?.allocation_reserves && (
                          <TableCell
                            align="center"
                            sx={{
                              bgcolor: 'grey.50',
                              fontSize: '0.75rem',
                              fontWeight: 'medium',
                            }}
                          >
                            {reservePct !== undefined ? formatPct(reservePct) : '-'}
                          </TableCell>
                        )}
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>
        </>
      )}

      {/* Reason Dialog */}
      <Dialog open={reasonDialog} onClose={() => setReasonDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          Override Reason
          {hasViolations && (
            <Chip
              icon={<WarningIcon />}
              label="Guardrail violation(s) detected"
              color="error"
              size="small"
              sx={{ ml: 1 }}
            />
          )}
        </DialogTitle>
        <DialogContent>
          {hasViolations ? (
            <>
              <Alert severity="warning" sx={{ mb: 2 }}>
                Your changes breach {violationCount} S&OP allocation reserve guardrail{violationCount > 1 ? 's' : ''}.
                A reason is <strong>required</strong> to proceed.
              </Alert>
              <Box mb={2}>
                <Typography variant="caption" color="text.secondary" fontWeight="bold" display="block" gutterBottom>
                  Violations:
                </Typography>
                {Object.entries(violations).map(([cellKey, v]) => (
                  <Typography key={cellKey} variant="caption" display="block" color="error">
                    {cellKey.replace('_', ' ')}: {formatPct(v.actual)} share (S&OP reserve: {formatPct(v.expected)})
                  </Typography>
                ))}
              </Box>
            </>
          ) : (
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Provide a reason for this allocation override (optional but recommended for audit trail).
            </Typography>
          )}
          <TextField
            fullWidth
            multiline
            rows={2}
            placeholder={
              hasViolations
                ? 'e.g., Temporary P3 increase for promotional event overrides reserve policy'
                : 'e.g., Upcoming promotion requires P3 increase'
            }
            value={overrideReason}
            onChange={(e) => setOverrideReason(e.target.value)}
            error={hasViolations && !overrideReason.trim()}
            helperText={hasViolations && !overrideReason.trim() ? 'Reason is required when overriding S&OP guardrails' : ''}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setReasonDialog(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleSaveConfirm}
            disabled={hasViolations && !overrideReason.trim()}
            color={hasViolations ? 'warning' : 'primary'}
          >
            {hasViolations ? 'Override Guardrails' : `Save ${editCount} Override${editCount > 1 ? 's' : ''}`}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default AllocationTimelineTab;
