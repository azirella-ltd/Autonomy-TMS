/**
 * Execution Dashboard (Layer 5 - Foundation + TRM)
 *
 * The execution layer is the foundation of the planning cascade.
 * It surfaces MRP results, safety stock, AATP, TRM agent decisions,
 * feed-back signals flowing upstream, and CDC-based replanning triggers.
 *
 * Tabs:
 *   1. Foundation  - MRP results, safety stock, AATP
 *   2. TRM Agents  - Decision stream and agent metrics
 *   3. Feed-back Signals - Source of all signals flowing upstream
 *   4. CDC Monitor - Event-driven replanning triggers
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
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Alert,
  Chip,
  CircularProgress,
  Card,
  CardContent,
  Divider,
  LinearProgress,
} from '@mui/material';
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import LayerModeIndicator from '../../components/cascade/LayerModeIndicator';
import FeedbackSignalCards from '../../components/cascade/FeedbackSignalCards';
import { getLayerLicenses, getFeedbackSignals } from '../../services/planningCascadeApi';
import { api } from '../../services/api';

// ---------------------------------------------------------------------------
// Mock / placeholder data
// ---------------------------------------------------------------------------

const MOCK_MRP_ROWS = [
  { sku: 'FG-1001', period: 'W10', grossReq: 500, onHand: 120, netReq: 380, plannedOrder: 400 },
  { sku: 'FG-1002', period: 'W10', grossReq: 300, onHand: 350, netReq: 0, plannedOrder: 0 },
  { sku: 'FG-1003', period: 'W11', grossReq: 220, onHand: 50, netReq: 170, plannedOrder: 200 },
  { sku: 'COMP-2001', period: 'W11', grossReq: 800, onHand: 300, netReq: 500, plannedOrder: 500 },
  { sku: 'COMP-2002', period: 'W12', grossReq: 150, onHand: 200, netReq: 0, plannedOrder: 0 },
  { sku: 'FG-1001', period: 'W12', grossReq: 480, onHand: 60, netReq: 420, plannedOrder: 450 },
];

const MOCK_SAFETY_STOCK = [
  { product: 'FG-1001', site: 'DC-East', policyType: 'sl', ssQty: 150, currentInv: 210 },
  { product: 'FG-1002', site: 'DC-East', policyType: 'doc_dem', ssQty: 80, currentInv: 350 },
  { product: 'FG-1003', site: 'DC-West', policyType: 'doc_fcst', ssQty: 120, currentInv: 50 },
  { product: 'COMP-2001', site: 'Plant-1', policyType: 'abs_level', ssQty: 200, currentInv: 300 },
  { product: 'COMP-2002', site: 'Plant-1', policyType: 'sl', ssQty: 100, currentInv: 95 },
];

const MOCK_AATP = [
  { product: 'FG-1001', available: 400, committed: 280, atp: 120 },
  { product: 'FG-1002', available: 350, committed: 100, atp: 250 },
  { product: 'FG-1003', available: 200, committed: 190, atp: 10 },
  { product: 'COMP-2001', available: 500, committed: 320, atp: 180 },
  { product: 'COMP-2002', available: 200, committed: 50, atp: 150 },
];

const MOCK_ATP_PIE = [
  { name: 'FULFILL', value: 64 },
  { name: 'PARTIAL', value: 18 },
  { name: 'DEFER', value: 12 },
  { name: 'REJECT', value: 6 },
];
const PIE_COLORS = ['#4caf50', '#ff9800', '#2196f3', '#f44336'];

const MOCK_DECISION_STREAM = [
  { time: '14:32:05', agent: 'ATP', sku: 'FG-1001', decision: 'FULFILL', confidence: 0.97, outcome: 'Shipped' },
  { time: '14:31:58', agent: 'Rebalancing', sku: 'FG-1003', decision: 'TRANSFER DC-East -> DC-West', confidence: 0.85, outcome: 'In transit' },
  { time: '14:31:42', agent: 'PO Creation', sku: 'COMP-2001', decision: 'PO #4821 (qty 500)', confidence: 0.91, outcome: 'Confirmed' },
  { time: '14:31:30', agent: 'Order Tracking', sku: 'FG-1002', decision: 'Escalate - late shipment', confidence: 0.78, outcome: 'Escalated' },
  { time: '14:30:15', agent: 'ATP', sku: 'FG-1003', decision: 'PARTIAL (80%)', confidence: 0.82, outcome: 'Partial ship' },
  { time: '14:29:50', agent: 'ATP', sku: 'FG-1001', decision: 'DEFER 2 days', confidence: 0.88, outcome: 'Pending' },
  { time: '14:29:12', agent: 'PO Creation', sku: 'COMP-2002', decision: 'PO #4820 (qty 200)', confidence: 0.94, outcome: 'Confirmed' },
  { time: '14:28:45', agent: 'Rebalancing', sku: 'FG-1001', decision: 'No action needed', confidence: 0.96, outcome: '-' },
];

const MOCK_CDC_ROWS = [
  { check: 'Demand deviation vs forecast', currentValue: '8.2%', threshold: '15%', status: 'OK', severity: 'low', lastTriggered: '2026-02-07 09:15' },
  { check: 'Service level (OTIF)', currentValue: '91.3%', threshold: '95%', status: 'BREACH', severity: 'high', lastTriggered: '2026-02-09 06:00' },
  { check: 'Inventory imbalance ratio', currentValue: '0.12', threshold: '0.20', status: 'OK', severity: 'medium', lastTriggered: '2026-02-05 14:30' },
  { check: 'Lead time deviation (avg)', currentValue: '1.8 days', threshold: '2.0 days', status: 'OK', severity: 'medium', lastTriggered: '2026-02-06 11:00' },
  { check: 'Backlog growth rate', currentValue: '+12%', threshold: '5%', status: 'BREACH', severity: 'critical', lastTriggered: '2026-02-09 06:00' },
];

// ---------------------------------------------------------------------------
// Tab panel helper
// ---------------------------------------------------------------------------

function TabPanel({ children, value, index, ...other }) {
  return (
    <div role="tabpanel" hidden={value !== index} {...other}>
      {value === index && <Box sx={{ pt: 3 }}>{children}</Box>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function FoundationTab() {
  const totalPlannedOrders = MOCK_MRP_ROWS.filter((r) => r.plannedOrder > 0).length;
  const totalPlannedQty = MOCK_MRP_ROWS.reduce((s, r) => s + r.plannedOrder, 0);

  return (
    <Grid container spacing={3}>
      {/* MRP Results */}
      <Grid item xs={12}>
        <Paper sx={{ p: 3 }}>
          <Typography variant="h6" gutterBottom>
            Net Requirements
          </Typography>
          <Box display="flex" gap={4} mb={2}>
            <Box>
              <Typography variant="caption" color="text.secondary">
                Total Planned Orders
              </Typography>
              <Typography variant="h5" fontWeight="bold">
                {totalPlannedOrders}
              </Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">
                Total Planned Qty
              </Typography>
              <Typography variant="h5" fontWeight="bold">
                {totalPlannedQty.toLocaleString()}
              </Typography>
            </Box>
          </Box>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>SKU</TableCell>
                  <TableCell>Period</TableCell>
                  <TableCell align="right">Gross Req</TableCell>
                  <TableCell align="right">On Hand</TableCell>
                  <TableCell align="right">Net Req</TableCell>
                  <TableCell align="right">Planned Order</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {MOCK_MRP_ROWS.map((row, idx) => (
                  <TableRow key={idx} sx={row.plannedOrder === 0 ? { opacity: 0.5 } : undefined}>
                    <TableCell>{row.sku}</TableCell>
                    <TableCell>{row.period}</TableCell>
                    <TableCell align="right">{row.grossReq}</TableCell>
                    <TableCell align="right">{row.onHand}</TableCell>
                    <TableCell align="right">{row.netReq}</TableCell>
                    <TableCell align="right">
                      {row.plannedOrder > 0 ? row.plannedOrder : '-'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      </Grid>

      {/* Safety Stock */}
      <Grid item xs={12} md={6}>
        <Paper sx={{ p: 3, height: '100%' }}>
          <Typography variant="h6" gutterBottom>
            Safety Stock Levels
          </Typography>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Product</TableCell>
                  <TableCell>Site</TableCell>
                  <TableCell>Policy Type</TableCell>
                  <TableCell align="right">Safety Stock Qty</TableCell>
                  <TableCell align="right">Current Inventory</TableCell>
                  <TableCell>Status</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {MOCK_SAFETY_STOCK.map((row, idx) => {
                  const isAbove = row.currentInv >= row.ssQty;
                  return (
                    <TableRow key={idx}>
                      <TableCell>{row.product}</TableCell>
                      <TableCell>{row.site}</TableCell>
                      <TableCell>
                        <Chip label={row.policyType} size="small" variant="outlined" />
                      </TableCell>
                      <TableCell align="right">{row.ssQty}</TableCell>
                      <TableCell align="right">{row.currentInv}</TableCell>
                      <TableCell>
                        <Chip
                          label={isAbove ? 'OK' : 'Below SS'}
                          size="small"
                          color={isAbove ? 'success' : 'error'}
                        />
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      </Grid>

      {/* AATP */}
      <Grid item xs={12} md={6}>
        <Paper sx={{ p: 3, height: '100%' }}>
          <Typography variant="h6" gutterBottom>
            Available to Promise
          </Typography>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Product</TableCell>
                  <TableCell align="right">Available Qty</TableCell>
                  <TableCell align="right">Committed</TableCell>
                  <TableCell align="right">ATP</TableCell>
                  <TableCell sx={{ minWidth: 120 }}>Utilization</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {MOCK_AATP.map((row, idx) => {
                  const utilPct = row.available > 0
                    ? Math.round((row.committed / row.available) * 100)
                    : 0;
                  return (
                    <TableRow key={idx}>
                      <TableCell>{row.product}</TableCell>
                      <TableCell align="right">{row.available}</TableCell>
                      <TableCell align="right">{row.committed}</TableCell>
                      <TableCell align="right">
                        <Typography
                          fontWeight="bold"
                          color={row.atp < 20 ? 'error.main' : 'text.primary'}
                        >
                          {row.atp}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Box display="flex" alignItems="center" gap={1}>
                          <LinearProgress
                            variant="determinate"
                            value={utilPct}
                            sx={{ flexGrow: 1, height: 8, borderRadius: 4 }}
                            color={utilPct > 90 ? 'error' : utilPct > 70 ? 'warning' : 'primary'}
                          />
                          <Typography variant="caption" sx={{ minWidth: 32 }}>
                            {utilPct}%
                          </Typography>
                        </Box>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      </Grid>
    </Grid>
  );
}

function TRMAgentsTab({ hasTRM }) {
  if (!hasTRM) {
    return (
      <Alert severity="info" sx={{ mt: 1 }}>
        TRM agents require the AI Execution package. Contact your account team to enable
        autonomous execution agents (ATP, Rebalancing, PO Creation, Order Tracking).
      </Alert>
    );
  }

  return (
    <Box>
      {/* Agent cards - 2x2 grid */}
      <Grid container spacing={3}>
        {/* ATP Agent */}
        <Grid item xs={12} md={6}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom>
                ATP Agent
              </Typography>
              <Divider sx={{ mb: 2 }} />
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Box mb={1}>
                    <Typography variant="caption" color="text.secondary">
                      Fill Rate
                    </Typography>
                    <Typography variant="h5" fontWeight="bold" color="success.main">
                      94.2%
                    </Typography>
                  </Box>
                  <Box mb={1}>
                    <Typography variant="caption" color="text.secondary">
                      Decisions Made
                    </Typography>
                    <Typography variant="h6">1,247</Typography>
                  </Box>
                  <Box>
                    <Typography variant="caption" color="text.secondary">
                      Avg Confidence
                    </Typography>
                    <Typography variant="h6">0.91</Typography>
                  </Box>
                </Grid>
                <Grid item xs={6}>
                  <ResponsiveContainer width="100%" height={160}>
                    <PieChart>
                      <Pie
                        data={MOCK_ATP_PIE}
                        cx="50%"
                        cy="50%"
                        innerRadius={35}
                        outerRadius={60}
                        dataKey="value"
                        paddingAngle={2}
                      >
                        {MOCK_ATP_PIE.map((entry, i) => (
                          <Cell key={entry.name} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip />
                      <Legend iconSize={8} wrapperStyle={{ fontSize: 11 }} />
                    </PieChart>
                  </ResponsiveContainer>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        {/* Rebalancing Agent */}
        <Grid item xs={12} md={6}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Rebalancing Agent
              </Typography>
              <Divider sx={{ mb: 2 }} />
              <Box mb={1}>
                <Typography variant="caption" color="text.secondary">
                  Transfers Triggered
                </Typography>
                <Typography variant="h5" fontWeight="bold">
                  38
                </Typography>
              </Box>
              <Box mb={1}>
                <Typography variant="caption" color="text.secondary">
                  DOS Improvement (avg)
                </Typography>
                <Typography variant="h6" color="success.main">
                  +4.2 days
                </Typography>
              </Box>
              <Box>
                <Typography variant="caption" color="text.secondary">
                  Cost Incurred
                </Typography>
                <Typography variant="h6">$12,340</Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* PO Creation Agent */}
        <Grid item xs={12} md={6}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom>
                PO Creation Agent
              </Typography>
              <Divider sx={{ mb: 2 }} />
              <Box mb={1}>
                <Typography variant="caption" color="text.secondary">
                  Orders Placed
                </Typography>
                <Typography variant="h5" fontWeight="bold">
                  156
                </Typography>
              </Box>
              <Box mb={1}>
                <Typography variant="caption" color="text.secondary">
                  Avg Order Qty
                </Typography>
                <Typography variant="h6">342 units</Typography>
              </Box>
              <Box>
                <Typography variant="caption" color="text.secondary">
                  Expedite %
                </Typography>
                <Typography variant="h6" color="warning.main">
                  8.3%
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Order Tracking Agent */}
        <Grid item xs={12} md={6}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Order Tracking Agent
              </Typography>
              <Divider sx={{ mb: 2 }} />
              <Box mb={1}>
                <Typography variant="caption" color="text.secondary">
                  Exceptions Detected
                </Typography>
                <Typography variant="h5" fontWeight="bold">
                  23
                </Typography>
              </Box>
              <Box mb={1}>
                <Typography variant="caption" color="text.secondary">
                  Escalation Rate
                </Typography>
                <Typography variant="h6" color="warning.main">
                  17.4%
                </Typography>
              </Box>
              <Box>
                <Typography variant="caption" color="text.secondary">
                  Avg Resolution Time
                </Typography>
                <Typography variant="h6">2.1 hrs</Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Decision Stream */}
      <Paper sx={{ p: 3, mt: 3 }}>
        <Typography variant="h6" gutterBottom>
          Decision Stream
        </Typography>
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Time</TableCell>
                <TableCell>Agent</TableCell>
                <TableCell>SKU</TableCell>
                <TableCell>Decision</TableCell>
                <TableCell align="right">Confidence</TableCell>
                <TableCell>Outcome</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {MOCK_DECISION_STREAM.map((row, idx) => (
                <TableRow key={idx}>
                  <TableCell>
                    <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                      {row.time}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Chip label={row.agent} size="small" variant="outlined" />
                  </TableCell>
                  <TableCell>{row.sku}</TableCell>
                  <TableCell>{row.decision}</TableCell>
                  <TableCell align="right">
                    <Typography
                      variant="body2"
                      color={row.confidence >= 0.9 ? 'success.main' : row.confidence >= 0.8 ? 'warning.main' : 'error.main'}
                      fontWeight="bold"
                    >
                      {row.confidence.toFixed(2)}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Chip
                      label={row.outcome}
                      size="small"
                      color={
                        row.outcome === 'Shipped' || row.outcome === 'Confirmed'
                          ? 'success'
                          : row.outcome === 'Escalated'
                          ? 'error'
                          : 'default'
                      }
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>
    </Box>
  );
}

function FeedbackTab({ configId }) {
  return (
    <Box>
      <Alert severity="info" sx={{ mb: 3 }}>
        These signals flow from execution outcomes to upstream planning layers for re-tuning.
      </Alert>
      <FeedbackSignalCards configId={configId} />
    </Box>
  );
}

function CDCMonitorTab() {
  const breaches = MOCK_CDC_ROWS.filter((r) => r.status === 'BREACH');

  return (
    <Box>
      <Paper sx={{ p: 3 }}>
        <Typography variant="h6" gutterBottom>
          Change Detection &amp; Cadence Monitor
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Threshold checks that trigger event-driven replanning when breached.
        </Typography>
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Check</TableCell>
                <TableCell align="right">Current Value</TableCell>
                <TableCell align="right">Threshold</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Severity</TableCell>
                <TableCell>Last Triggered</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {MOCK_CDC_ROWS.map((row, idx) => (
                <TableRow
                  key={idx}
                  sx={row.status === 'BREACH' ? { bgcolor: 'error.50' } : undefined}
                >
                  <TableCell>{row.check}</TableCell>
                  <TableCell align="right">
                    <Typography
                      fontWeight={row.status === 'BREACH' ? 'bold' : 'normal'}
                      color={row.status === 'BREACH' ? 'error.main' : 'text.primary'}
                    >
                      {row.currentValue}
                    </Typography>
                  </TableCell>
                  <TableCell align="right">{row.threshold}</TableCell>
                  <TableCell>
                    <Chip
                      label={row.status}
                      size="small"
                      color={row.status === 'OK' ? 'success' : 'error'}
                    />
                  </TableCell>
                  <TableCell>
                    <Chip
                      label={row.severity}
                      size="small"
                      variant="outlined"
                      color={
                        row.severity === 'critical'
                          ? 'error'
                          : row.severity === 'high'
                          ? 'warning'
                          : 'default'
                      }
                    />
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                      {row.lastTriggered}
                    </Typography>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>

      {/* Active breach alerts */}
      {breaches.length > 0 && (
        <Box sx={{ mt: 3 }}>
          <Typography variant="subtitle1" gutterBottom fontWeight="bold">
            Active Breaches ({breaches.length})
          </Typography>
          {breaches.map((b, idx) => (
            <Alert
              key={idx}
              severity={b.severity === 'critical' ? 'error' : 'warning'}
              sx={{ mb: 1 }}
              action={
                <Button color="inherit" size="small">
                  Replan
                </Button>
              }
            >
              <Typography variant="subtitle2">{b.check}</Typography>
              <Typography variant="body2">
                Current: <strong>{b.currentValue}</strong> exceeds threshold of{' '}
                <strong>{b.threshold}</strong>.{' '}
                {b.severity === 'critical'
                  ? 'Immediate replanning recommended. Consider expediting open orders and adjusting safety stock.'
                  : 'Review upstream demand forecast and adjust planning parameters.'}
              </Typography>
            </Alert>
          ))}
        </Box>
      )}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

const ExecutionPage = ({ configId, groupId }) => {
  const [tabIndex, setTabIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [licenses, setLicenses] = useState(null);
  const [hasTRM, setHasTRM] = useState(false);

  useEffect(() => {
    loadLicenses();
  }, [groupId]);

  const loadLicenses = async () => {
    try {
      setLoading(true);
      if (groupId) {
        const data = await getLayerLicenses(groupId);
        setLicenses(data);
        // Check if execution layer includes TRM capability
        const execLayer = (data.layers || []).find((l) => l.layer === 'execution');
        const hasTRMPackage =
          execLayer &&
          execLayer.mode === 'active' &&
          execLayer.package_tier &&
          execLayer.package_tier !== 'foundation';
        setHasTRM(!!hasTRMPackage);
      }
    } catch (err) {
      console.error('Failed to load layer licenses', err);
      // Default: execution is always foundation, TRM may not be licensed
      setHasTRM(false);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight={300}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box>
      {/* Header */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
        <Box>
          <Typography variant="h5" fontWeight="bold">
            Execution Dashboard
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Layer 5 — Foundation + TRM Agents
          </Typography>
        </Box>
        <LayerModeIndicator layer="execution" mode="active" />
      </Box>

      <Divider sx={{ mb: 2 }} />

      {/* Tabs */}
      <Tabs
        value={tabIndex}
        onChange={(_, v) => setTabIndex(v)}
        variant="scrollable"
        scrollButtons="auto"
      >
        <Tab label="Foundation" />
        <Tab label="TRM Agents" />
        <Tab label="Feed-back Signals" />
        <Tab label="CDC Monitor" />
      </Tabs>

      <TabPanel value={tabIndex} index={0}>
        <FoundationTab />
      </TabPanel>

      <TabPanel value={tabIndex} index={1}>
        <TRMAgentsTab hasTRM={hasTRM} />
      </TabPanel>

      <TabPanel value={tabIndex} index={2}>
        <FeedbackTab configId={configId} />
      </TabPanel>

      <TabPanel value={tabIndex} index={3}>
        <CDCMonitorTab />
      </TabPanel>
    </Box>
  );
};

export default ExecutionPage;
