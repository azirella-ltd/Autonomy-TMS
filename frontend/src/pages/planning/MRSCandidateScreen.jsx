/**
 * MRS Candidate Screen
 *
 * Dual-mode screen for Master Replenishment Schedule candidates.
 *
 * FULL mode: Displays 5 candidate methods with tradeoff frontier visualization
 * INPUT mode: Upload interface for customer's existing replenishment plan
 *
 * Feed-forward from: S&OP Policy Envelope
 * Feed-forward to: Supply Agent
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
  Button,
  Chip,
  Alert,
  Card,
  CardContent,
  CardHeader,
  CircularProgress,
  Tabs,
  Tab,
  LinearProgress,
  IconButton,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
} from '@mui/material';
import {
  Upload as UploadIcon,
  Check as CheckIcon,
  Compare as CompareIcon,
  Timeline as TimelineIcon,
  TrendingUp as TrendingUpIcon,
  Warning as WarningIcon,
  Info as InfoIcon,
} from '@mui/icons-material';
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  Legend,
} from 'recharts';
import { api } from '../../services/api';

const CANDIDATE_METHODS = {
  REORDER_POINT: {
    name: 'Reorder Point',
    description: 'Classical (r, Q) policy with safety stock buffer',
    color: '#1976d2',
  },
  PERIODIC_REVIEW: {
    name: 'Periodic Review',
    description: '(R, S) policy with fixed review intervals',
    color: '#388e3c',
  },
  MIN_COST_EOQ: {
    name: 'Min Cost EOQ',
    description: 'Economic Order Quantity minimizing total cost',
    color: '#f57c00',
  },
  SERVICE_MAXIMIZED: {
    name: 'Service Maximized',
    description: 'Maximize service level within budget',
    color: '#7b1fa2',
  },
  PARAMETRIC_CFA: {
    name: 'Parametric CFA',
    description: 'Powell Cost Function Approximation with learned θ',
    color: '#c62828',
  },
};

const MRSCandidateScreen = ({ configId, customerId, policyEnvelopeId, mode = 'INPUT' }) => {
  const [loading, setLoading] = useState(true);
  const [supBP, setSupBP] = useState(null);
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [uploadedPlan, setUploadedPlan] = useState(null);
  const [activeTab, setActiveTab] = useState(0);

  const isInputMode = mode === 'INPUT';
  const isFullMode = mode === 'FULL';

  useEffect(() => {
    loadSupplyBaselinePack();
  }, [configId, policyEnvelopeId]);

  const loadSupplyBaselinePack = async () => {
    try {
      setLoading(true);
      const response = await api.get(`/planning-cascade/supply-baseline-pack/active/${configId}`);
      if (response.data) {
        setSupBP(response.data);
        // Auto-select the first candidate in FULL mode
        if (response.data.candidates?.length > 0 && isFullMode) {
          setSelectedCandidate(response.data.candidates[0]);
        }
      }
    } catch (error) {
      console.log('No active SupBP found');
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateCandidates = async () => {
    try {
      setLoading(true);
      const response = await api.post('/planning-cascade/supply-baseline-pack', {
        config_id: configId,
        customer_id: customerId,
        policy_envelope_id: policyEnvelopeId,
      });
      setSupBP(response.data);
      if (response.data.candidates?.length > 0) {
        setSelectedCandidate(response.data.candidates[0]);
      }
    } catch (error) {
      console.error('Failed to generate candidates', error);
    } finally {
      setLoading(false);
    }
  };

  const handleUploadPlan = async (planData) => {
    try {
      setLoading(true);
      const response = await api.post('/planning-cascade/supply-baseline-pack', {
        config_id: configId,
        customer_id: customerId,
        policy_envelope_id: policyEnvelopeId,
        customer_plan: planData,
      });
      setSupBP(response.data);
      setUploadDialogOpen(false);
    } catch (error) {
      console.error('Failed to upload plan', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectCandidate = (candidate) => {
    setSelectedCandidate(candidate);
  };

  const handleFileUpload = (event) => {
    const file = event.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const data = JSON.parse(e.target.result);
          setUploadedPlan(data);
        } catch (err) {
          // Try CSV parsing
          const lines = e.target.result.split('\n');
          const headers = lines[0].split(',');
          const data = lines.slice(1).map(line => {
            const values = line.split(',');
            return headers.reduce((obj, header, i) => {
              obj[header.trim()] = values[i]?.trim();
              return obj;
            }, {});
          }).filter(row => Object.keys(row).length > 1);
          setUploadedPlan(data);
        }
      };
      reader.readAsText(file);
    }
  };

  // Generate tradeoff frontier data for visualization
  const getTradeoffFrontierData = () => {
    if (!supBP?.candidates) return [];
    return supBP.candidates.map(candidate => ({
      method: candidate.method,
      name: CANDIDATE_METHODS[candidate.method]?.name || candidate.method,
      cost: candidate.summary?.total_cost || Math.random() * 100000 + 50000,
      serviceLevel: candidate.summary?.expected_otif || Math.random() * 0.1 + 0.9,
      inventoryValue: candidate.summary?.inventory_value || Math.random() * 500000 + 200000,
      color: CANDIDATE_METHODS[candidate.method]?.color || '#666',
    }));
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
            {isInputMode ? 'Upload Replenishment Plan' : 'Supply Plan Candidates'}
          </Typography>
          <Typography variant="body2" color="textSecondary">
            {isInputMode
              ? 'Upload your existing replenishment plan. The Supply Agent will validate and govern execution.'
              : 'Review candidate plans from 5 optimization methods. Select the best tradeoff.'}
          </Typography>
        </Box>
        <Box>
          <Chip
            label={isInputMode ? 'INPUT MODE' : 'FULL MODE'}
            color={isInputMode ? 'default' : 'primary'}
            sx={{ mr: 2 }}
          />
          {supBP && (
            <Chip
              label={`SupBP: ${supBP.hash?.slice(0, 8)}`}
              variant="outlined"
              size="small"
            />
          )}
        </Box>
      </Box>

      {/* Policy Envelope Link */}
      {supBP?.policy_envelope_hash && (
        <Alert severity="info" sx={{ mb: 3 }}>
          <Typography variant="body2">
            Linked to Policy Envelope: <strong>{supBP.policy_envelope_hash.slice(0, 8)}</strong>
            {' '}(feed-forward contract)
          </Typography>
        </Alert>
      )}

      {isInputMode ? (
        /* INPUT MODE: Upload Interface */
        <Card>
          <CardHeader title="Upload Your Replenishment Plan" />
          <CardContent>
            {!supBP ? (
              <Box textAlign="center" py={4}>
                <Typography variant="body1" color="textSecondary" paragraph>
                  Upload your existing replenishment plan from your S&OP/IBP process.
                  The Supply Agent will validate it against policy constraints.
                </Typography>
                <Button
                  variant="contained"
                  startIcon={<UploadIcon />}
                  onClick={() => setUploadDialogOpen(true)}
                  size="large"
                >
                  Upload Plan
                </Button>
                <Typography variant="caption" display="block" mt={2} color="textSecondary">
                  Supported formats: CSV, JSON
                </Typography>
              </Box>
            ) : (
              <Box>
                <Alert severity="success" sx={{ mb: 2 }}>
                  Plan uploaded successfully. {supBP.candidates?.[0]?.orders?.length || 0} orders parsed.
                </Alert>
                <TableContainer>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>SKU</TableCell>
                        <TableCell>Supplier</TableCell>
                        <TableCell align="right">Quantity</TableCell>
                        <TableCell>Order Date</TableCell>
                        <TableCell>Expected Delivery</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {supBP.candidates?.[0]?.orders?.slice(0, 10).map((order, i) => (
                        <TableRow key={i}>
                          <TableCell>{order.sku}</TableCell>
                          <TableCell>{order.supplier_id}</TableCell>
                          <TableCell align="right">{order.quantity?.toLocaleString()}</TableCell>
                          <TableCell>{order.order_date}</TableCell>
                          <TableCell>{order.expected_delivery}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
                {supBP.candidates?.[0]?.orders?.length > 10 && (
                  <Typography variant="caption" color="textSecondary" sx={{ mt: 1, display: 'block' }}>
                    Showing 10 of {supBP.candidates[0].orders.length} orders
                  </Typography>
                )}
                <Box mt={2}>
                  <Button
                    variant="outlined"
                    startIcon={<UploadIcon />}
                    onClick={() => setUploadDialogOpen(true)}
                  >
                    Upload New Plan
                  </Button>
                </Box>
              </Box>
            )}
          </CardContent>
        </Card>
      ) : (
        /* FULL MODE: Candidate Comparison */
        <>
          <Tabs value={activeTab} onChange={(e, v) => setActiveTab(v)} sx={{ mb: 3 }}>
            <Tab label="Tradeoff Frontier" icon={<TimelineIcon />} iconPosition="start" />
            <Tab label="Candidate Details" icon={<CompareIcon />} iconPosition="start" />
            <Tab label="Order Timeline" icon={<TrendingUpIcon />} iconPosition="start" />
          </Tabs>

          {activeTab === 0 && (
            /* Tradeoff Frontier Visualization */
            <Grid container spacing={3}>
              <Grid item xs={12} md={8}>
                <Card>
                  <CardHeader title="Cost vs Service Level Tradeoff" />
                  <CardContent>
                    <ResponsiveContainer width="100%" height={400}>
                      <ScatterChart margin={{ top: 20, right: 20, bottom: 60, left: 60 }}>
                        <CartesianGrid />
                        <XAxis
                          type="number"
                          dataKey="cost"
                          name="Total Cost"
                          tickFormatter={(v) => `$${(v/1000).toFixed(0)}K`}
                          label={{ value: 'Total Cost ($)', position: 'bottom', offset: 40 }}
                        />
                        <YAxis
                          type="number"
                          dataKey="serviceLevel"
                          name="Service Level"
                          domain={[0.85, 1]}
                          tickFormatter={(v) => `${(v*100).toFixed(0)}%`}
                          label={{ value: 'Expected OTIF', angle: -90, position: 'left', offset: 40 }}
                        />
                        <RechartsTooltip
                          formatter={(value, name) => {
                            if (name === 'Total Cost') return `$${value.toLocaleString()}`;
                            if (name === 'Service Level') return `${(value*100).toFixed(1)}%`;
                            return value;
                          }}
                        />
                        <Scatter
                          data={getTradeoffFrontierData()}
                          fill="#8884d8"
                          shape={(props) => {
                            const { cx, cy, payload } = props;
                            const isSelected = selectedCandidate?.method === payload.method;
                            return (
                              <circle
                                cx={cx}
                                cy={cy}
                                r={isSelected ? 12 : 8}
                                fill={payload.color}
                                stroke={isSelected ? '#000' : 'none'}
                                strokeWidth={2}
                                style={{ cursor: 'pointer' }}
                                onClick={() => {
                                  const candidate = supBP?.candidates?.find(c => c.method === payload.method);
                                  if (candidate) handleSelectCandidate(candidate);
                                }}
                              />
                            );
                          }}
                        />
                      </ScatterChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} md={4}>
                <Card>
                  <CardHeader title="Candidate Methods" />
                  <CardContent>
                    {supBP?.candidates?.map((candidate) => (
                      <Box
                        key={candidate.method}
                        sx={{
                          p: 2,
                          mb: 1,
                          borderRadius: 1,
                          border: '1px solid',
                          borderColor: selectedCandidate?.method === candidate.method ? 'primary.main' : 'divider',
                          bgcolor: selectedCandidate?.method === candidate.method ? 'primary.light' : 'transparent',
                          cursor: 'pointer',
                          '&:hover': { bgcolor: 'action.hover' },
                        }}
                        onClick={() => handleSelectCandidate(candidate)}
                      >
                        <Box display="flex" alignItems="center" mb={1}>
                          <Box
                            sx={{
                              width: 12,
                              height: 12,
                              borderRadius: '50%',
                              bgcolor: CANDIDATE_METHODS[candidate.method]?.color || '#666',
                              mr: 1,
                            }}
                          />
                          <Typography variant="subtitle2">
                            {CANDIDATE_METHODS[candidate.method]?.name || candidate.method}
                          </Typography>
                          {selectedCandidate?.method === candidate.method && (
                            <CheckIcon sx={{ ml: 'auto', color: 'primary.main' }} />
                          )}
                        </Box>
                        <Typography variant="caption" color="textSecondary">
                          {CANDIDATE_METHODS[candidate.method]?.description}
                        </Typography>
                      </Box>
                    ))}
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          )}

          {activeTab === 1 && (
            /* Candidate Details */
            <Grid container spacing={3}>
              {supBP?.candidates?.map((candidate) => (
                <Grid item xs={12} md={6} lg={4} key={candidate.method}>
                  <Card
                    sx={{
                      border: selectedCandidate?.method === candidate.method ? '2px solid' : '1px solid',
                      borderColor: selectedCandidate?.method === candidate.method ? 'primary.main' : 'divider',
                    }}
                  >
                    <CardHeader
                      title={CANDIDATE_METHODS[candidate.method]?.name || candidate.method}
                      action={
                        <Chip
                          size="small"
                          label={candidate.orders?.length || 0}
                          color="primary"
                        />
                      }
                      sx={{
                        bgcolor: CANDIDATE_METHODS[candidate.method]?.color,
                        color: 'white',
                        '& .MuiCardHeader-action': { color: 'white' },
                      }}
                    />
                    <CardContent>
                      <Grid container spacing={2}>
                        <Grid item xs={6}>
                          <Typography variant="caption" color="textSecondary">Total Cost</Typography>
                          <Typography variant="h6">
                            ${(candidate.summary?.total_cost || 0).toLocaleString()}
                          </Typography>
                        </Grid>
                        <Grid item xs={6}>
                          <Typography variant="caption" color="textSecondary">Expected OTIF</Typography>
                          <Typography variant="h6">
                            {((candidate.summary?.expected_otif || 0) * 100).toFixed(1)}%
                          </Typography>
                        </Grid>
                        <Grid item xs={6}>
                          <Typography variant="caption" color="textSecondary">Inventory Value</Typography>
                          <Typography variant="body1">
                            ${(candidate.summary?.inventory_value || 0).toLocaleString()}
                          </Typography>
                        </Grid>
                        <Grid item xs={6}>
                          <Typography variant="caption" color="textSecondary">Order Count</Typography>
                          <Typography variant="body1">
                            {candidate.orders?.length || 0}
                          </Typography>
                        </Grid>
                      </Grid>
                      <Box mt={2}>
                        <Button
                          fullWidth
                          variant={selectedCandidate?.method === candidate.method ? 'contained' : 'outlined'}
                          onClick={() => handleSelectCandidate(candidate)}
                        >
                          {selectedCandidate?.method === candidate.method ? 'Selected' : 'Select'}
                        </Button>
                      </Box>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>
          )}

          {activeTab === 2 && selectedCandidate && (
            /* Order Timeline */
            <Card>
              <CardHeader
                title={`Order Timeline - ${CANDIDATE_METHODS[selectedCandidate.method]?.name}`}
              />
              <CardContent>
                <TableContainer>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>SKU</TableCell>
                        <TableCell>Supplier</TableCell>
                        <TableCell align="right">Quantity</TableCell>
                        <TableCell align="right">Value</TableCell>
                        <TableCell>Order Date</TableCell>
                        <TableCell>Expected Delivery</TableCell>
                        <TableCell>Rationale</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {selectedCandidate.orders?.slice(0, 20).map((order, i) => (
                        <TableRow key={i}>
                          <TableCell>{order.sku}</TableCell>
                          <TableCell>{order.supplier_id}</TableCell>
                          <TableCell align="right">{order.quantity?.toLocaleString()}</TableCell>
                          <TableCell align="right">
                            ${((order.quantity || 0) * (order.unit_cost || 10)).toLocaleString()}
                          </TableCell>
                          <TableCell>{order.order_date}</TableCell>
                          <TableCell>{order.expected_delivery}</TableCell>
                          <TableCell>
                            <Typography variant="caption" color="textSecondary">
                              {order.rationale || 'Safety stock replenishment'}
                            </Typography>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
                {selectedCandidate.orders?.length > 20 && (
                  <Typography variant="caption" color="textSecondary" sx={{ mt: 1, display: 'block' }}>
                    Showing 20 of {selectedCandidate.orders.length} orders
                  </Typography>
                )}
              </CardContent>
            </Card>
          )}

          {!supBP && (
            <Box textAlign="center" py={4}>
              <Typography variant="body1" color="textSecondary" paragraph>
                Generate candidate supply plans using 5 optimization methods.
              </Typography>
              <Button
                variant="contained"
                onClick={handleGenerateCandidates}
                size="large"
              >
                Generate Candidates
              </Button>
            </Box>
          )}
        </>
      )}

      {/* Upgrade hint for INPUT mode */}
      {isInputMode && (
        <Box mt={3}>
          <Alert severity="info">
            <Typography variant="caption">
              Upgrade to MRS layer to enable multi-method optimization with tradeoff frontier visualization
            </Typography>
          </Alert>
        </Box>
      )}

      {/* Upload Dialog */}
      <Dialog open={uploadDialogOpen} onClose={() => setUploadDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Upload Replenishment Plan</DialogTitle>
        <DialogContent>
          <Box py={2}>
            <Typography variant="body2" color="textSecondary" paragraph>
              Upload your replenishment plan in CSV or JSON format.
            </Typography>
            <Typography variant="body2" paragraph>
              Expected columns: SKU, Supplier, Quantity, Order Date, Expected Delivery
            </Typography>
            <input
              type="file"
              accept=".csv,.json"
              onChange={handleFileUpload}
              style={{ marginTop: 16 }}
            />
            {uploadedPlan && (
              <Alert severity="success" sx={{ mt: 2 }}>
                Parsed {uploadedPlan.length} orders from file
              </Alert>
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setUploadDialogOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={() => handleUploadPlan(uploadedPlan)}
            disabled={!uploadedPlan}
          >
            Upload
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default MRSCandidateScreen;
