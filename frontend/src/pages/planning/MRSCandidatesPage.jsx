/**
 * MRS / Supply Baseline Pack Page
 *
 * Three-tab layout for the MRS cascade layer:
 *   1. Input/Review  - Upload customer plan (INPUT mode) or review candidates (ACTIVE mode)
 *   2. Feed-back     - Outcome signals targeted to "mrs"
 *   3. Lineage       - Artifact hash-chain lineage for the current SupBP
 *
 * Feed-forward from: S&OP Policy Envelope
 * Feed-forward to:   Supply Agent (Supply Commit)
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
  Radio,
  RadioGroup,
  FormControlLabel,
  Divider,
} from '@mui/material';

import LayerModeIndicator from '../../components/cascade/LayerModeIndicator';
import ArtifactLineage from '../../components/cascade/ArtifactLineage';
import FeedbackSignalCards from '../../components/cascade/FeedbackSignalCards';
import TradeoffChart from '../../components/cascade/TradeoffChart';
import {
  getLayerLicenses,
  getSupplyBaselinePack,
  createSupplyBaselinePack,
} from '../../services/planningCascadeApi';

// ---------------------------------------------------------------------------
// Default empty row for the customer plan entry table
// ---------------------------------------------------------------------------
const EMPTY_ROW = {
  sku: '',
  supplier: '',
  destination: '',
  qty: '',
  order_date: '',
  receipt_date: '',
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
const MRSCandidatesPage = ({ configId, customerId, policyEnvelopeId }) => {
  // --- shared state ---
  const [activeTab, setActiveTab] = useState(0);
  const [layerMode, setLayerMode] = useState(null);   // 'active' | 'input' | 'disabled'
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // --- SupBP state (ACTIVE mode) ---
  const [currentSupbp, setCurrentSupbp] = useState(null);
  const [currentSupbpId, setCurrentSupbpId] = useState(null);
  const [selectedMethod, setSelectedMethod] = useState('');

  // --- Customer plan state (INPUT mode) ---
  const [customerPlan, setCustomerPlan] = useState([{ ...EMPTY_ROW }]);
  const [uploading, setUploading] = useState(false);
  const [uploadSuccess, setUploadSuccess] = useState(false);

  // -----------------------------------------------------------------------
  // Load layer license to determine mode
  // -----------------------------------------------------------------------
  useEffect(() => {
    if (!customerId) return;
    const loadLicense = async () => {
      try {
        const license = await getLayerLicenses(customerId);
        const mrsMode = license?.layers?.mrs?.mode || 'disabled';
        setLayerMode(mrsMode);
      } catch (err) {
        console.error('Failed to load layer licenses', err);
        setLayerMode('disabled');
      }
    };
    loadLicense();
  }, [customerId]);

  // -----------------------------------------------------------------------
  // In ACTIVE mode, load the SupBP once the mode is known
  // -----------------------------------------------------------------------
  useEffect(() => {
    if (layerMode !== 'active') {
      setLoading(false);
      return;
    }
    const loadSupBP = async () => {
      try {
        setLoading(true);
        // If a policyEnvelopeId is provided, derive supbpId; otherwise try
        // to load the latest for this config.
        if (policyEnvelopeId) {
          // The createSupplyBaselinePack call will have returned an id we can
          // re-fetch. On first visit the SupBP may not yet exist.
          const data = await getSupplyBaselinePack(policyEnvelopeId);
          setCurrentSupbp(data);
          setCurrentSupbpId(data?.id ?? policyEnvelopeId);
          // Auto-select first candidate method if available
          if (data?.candidates?.length > 0) {
            setSelectedMethod(data.candidates[0].method);
          }
        }
      } catch (err) {
        // No SupBP yet -- that is fine
        console.log('No active SupBP found for this envelope', err);
      } finally {
        setLoading(false);
      }
    };
    loadSupBP();
  }, [layerMode, policyEnvelopeId]);

  // -----------------------------------------------------------------------
  // Customer plan helpers (INPUT mode)
  // -----------------------------------------------------------------------
  const handleAddRow = () => {
    setCustomerPlan((prev) => [...prev, { ...EMPTY_ROW }]);
  };

  const handleRemoveRow = (index) => {
    setCustomerPlan((prev) => prev.filter((_, i) => i !== index));
  };

  const handlePlanFieldChange = (index, field, value) => {
    setCustomerPlan((prev) => {
      const updated = [...prev];
      updated[index] = { ...updated[index], [field]: value };
      return updated;
    });
  };

  const handleUploadCustomerPlan = async () => {
    try {
      setUploading(true);
      setUploadSuccess(false);
      setError(null);
      const result = await createSupplyBaselinePack({
        config_id: configId,
        customer_id: customerId,
        policy_envelope_id: policyEnvelopeId,
        mode: 'INPUT',
        customer_plan: customerPlan.filter(
          (row) => row.sku || row.supplier || row.destination || row.qty
        ),
      });
      setCurrentSupbp(result);
      setCurrentSupbpId(result?.id ?? null);
      setUploadSuccess(true);
    } catch (err) {
      console.error('Failed to upload customer plan', err);
      setError('Failed to upload the supply baseline pack. Please try again.');
    } finally {
      setUploading(false);
    }
  };

  // -----------------------------------------------------------------------
  // Render helpers
  // -----------------------------------------------------------------------

  /** Tab 1 -- INPUT mode: manual entry table */
  const renderInputMode = () => (
    <Box>
      {uploadSuccess && (
        <Alert severity="success" sx={{ mb: 2 }}>
          Customer replenishment plan uploaded successfully as a Supply Baseline Pack.
        </Alert>
      )}
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      <Typography variant="subtitle1" gutterBottom>
        Customer Replenishment Plan
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Enter your existing replenishment plan below. The Supply Agent will
        validate and govern execution against policy constraints.
      </Typography>

      <TableContainer component={Paper} variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>SKU</TableCell>
              <TableCell>Supplier</TableCell>
              <TableCell>Destination</TableCell>
              <TableCell>Qty</TableCell>
              <TableCell>Order Date</TableCell>
              <TableCell>Receipt Date</TableCell>
              <TableCell align="center">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {customerPlan.map((row, idx) => (
              <TableRow key={idx}>
                <TableCell>
                  <TextField
                    size="small"
                    variant="standard"
                    placeholder="e.g. SKU-001"
                    value={row.sku}
                    onChange={(e) => handlePlanFieldChange(idx, 'sku', e.target.value)}
                    fullWidth
                  />
                </TableCell>
                <TableCell>
                  <TextField
                    size="small"
                    variant="standard"
                    placeholder="e.g. SUPP-A"
                    value={row.supplier}
                    onChange={(e) => handlePlanFieldChange(idx, 'supplier', e.target.value)}
                    fullWidth
                  />
                </TableCell>
                <TableCell>
                  <TextField
                    size="small"
                    variant="standard"
                    placeholder="e.g. DC-EAST"
                    value={row.destination}
                    onChange={(e) => handlePlanFieldChange(idx, 'destination', e.target.value)}
                    fullWidth
                  />
                </TableCell>
                <TableCell>
                  <TextField
                    size="small"
                    variant="standard"
                    type="number"
                    placeholder="0"
                    value={row.qty}
                    onChange={(e) => handlePlanFieldChange(idx, 'qty', e.target.value)}
                    sx={{ width: 90 }}
                  />
                </TableCell>
                <TableCell>
                  <TextField
                    size="small"
                    variant="standard"
                    type="date"
                    value={row.order_date}
                    onChange={(e) => handlePlanFieldChange(idx, 'order_date', e.target.value)}
                    InputLabelProps={{ shrink: true }}
                  />
                </TableCell>
                <TableCell>
                  <TextField
                    size="small"
                    variant="standard"
                    type="date"
                    value={row.receipt_date}
                    onChange={(e) => handlePlanFieldChange(idx, 'receipt_date', e.target.value)}
                    InputLabelProps={{ shrink: true }}
                  />
                </TableCell>
                <TableCell align="center">
                  <Button
                    size="small"
                    color="error"
                    disabled={customerPlan.length <= 1}
                    onClick={() => handleRemoveRow(idx)}
                  >
                    Remove
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      <Box display="flex" justifyContent="space-between" alignItems="center" mt={2}>
        <Button variant="outlined" size="small" onClick={handleAddRow}>
          Add Row
        </Button>

        <Button
          variant="contained"
          onClick={handleUploadCustomerPlan}
          disabled={uploading || customerPlan.every((r) => !r.sku && !r.qty)}
        >
          {uploading ? (
            <>
              <CircularProgress size={18} sx={{ mr: 1 }} />
              Uploading...
            </>
          ) : (
            'Upload as Supply Baseline Pack'
          )}
        </Button>
      </Box>
    </Box>
  );

  /** Tab 1 -- ACTIVE mode: candidate comparison with tradeoff chart */
  const renderActiveMode = () => {
    if (!currentSupbp) {
      return (
        <Alert severity="info">
          No Supply Baseline Pack has been generated for this policy envelope yet.
          Generate candidates from the S&OP layer first.
        </Alert>
      );
    }

    const candidates = currentSupbp.candidates || [];

    return (
      <Box>
        {/* Tradeoff chart */}
        <Paper variant="outlined" sx={{ p: 2, mb: 3 }}>
          <TradeoffChart
            candidates={candidates}
            tradeoffFrontier={currentSupbp.tradeoff_frontier}
            selectedMethod={selectedMethod}
            onSelect={(method) => setSelectedMethod(method)}
          />
        </Paper>

        {/* Candidate comparison table */}
        <Typography variant="subtitle1" gutterBottom>
          Candidate Comparison
        </Typography>

        <TableContainer component={Paper} variant="outlined">
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell padding="checkbox" />
                <TableCell>Method</TableCell>
                <TableCell align="right">Total Orders</TableCell>
                <TableCell align="right">Total Spend</TableCell>
                <TableCell align="right">Proj. OTIF</TableCell>
                <TableCell align="right">Proj. DOS</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              <RadioGroup
                value={selectedMethod}
                onChange={(e) => setSelectedMethod(e.target.value)}
                name="candidate-method"
              >
                {candidates.map((c) => (
                  <TableRow
                    key={c.method}
                    hover
                    selected={selectedMethod === c.method}
                    onClick={() => setSelectedMethod(c.method)}
                    sx={{ cursor: 'pointer' }}
                  >
                    <TableCell padding="checkbox">
                      <FormControlLabel
                        value={c.method}
                        control={<Radio size="small" />}
                        label=""
                        sx={{ m: 0 }}
                      />
                    </TableCell>
                    <TableCell>{c.method}</TableCell>
                    <TableCell align="right">
                      {(c.orders?.length ?? c.total_orders ?? 0).toLocaleString()}
                    </TableCell>
                    <TableCell align="right">
                      ${(c.projected_cost ?? c.total_spend ?? 0).toLocaleString()}
                    </TableCell>
                    <TableCell align="right">
                      {((c.projected_otif ?? c.otif ?? 0) * 100).toFixed(1)}%
                    </TableCell>
                    <TableCell align="right">
                      {(c.projected_dos ?? c.dos ?? 0).toFixed(1)}
                    </TableCell>
                  </TableRow>
                ))}
              </RadioGroup>
            </TableBody>
          </Table>
        </TableContainer>

        {selectedMethod && (
          <Box mt={2}>
            <Chip
              label={`Selected: ${selectedMethod}`}
              color="primary"
              variant="outlined"
            />
          </Box>
        )}
      </Box>
    );
  };

  // -----------------------------------------------------------------------
  // Main render
  // -----------------------------------------------------------------------

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" p={6}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      {/* Page header */}
      <Typography variant="h5" gutterBottom>
        MRS / Supply Baseline Pack
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Review or provide the Supply Baseline Pack that feeds forward into the Supply Agent.
      </Typography>

      {/* Layer mode indicator */}
      {layerMode && (
        <Box mb={3}>
          <LayerModeIndicator layer="mrs" mode={layerMode} />
        </Box>
      )}

      <Divider sx={{ mb: 2 }} />

      {/* Tabs */}
      <Tabs
        value={activeTab}
        onChange={(_, v) => setActiveTab(v)}
        sx={{ mb: 3 }}
      >
        <Tab label="Input / Review" />
        <Tab label="Feed-back" />
        <Tab label="Lineage" />
      </Tabs>

      {/* Tab 1: Input / Review */}
      {activeTab === 0 && (
        <Box>
          {layerMode === 'input' && renderInputMode()}
          {layerMode === 'active' && renderActiveMode()}
          {layerMode === 'disabled' && (
            <Alert severity="warning">
              The MRS layer is not available in your current package. Contact your
              administrator to upgrade.
            </Alert>
          )}
        </Box>
      )}

      {/* Tab 2: Feed-back */}
      {activeTab === 1 && (
        <FeedbackSignalCards configId={configId} fedBackTo="mrs" />
      )}

      {/* Tab 3: Lineage */}
      {activeTab === 2 && (
        <Box>
          {currentSupbpId ? (
            <ArtifactLineage
              artifactType="supply_baseline_pack"
              artifactId={currentSupbpId}
            />
          ) : (
            <Alert severity="info">
              No Supply Baseline Pack loaded. Upload or generate one in the
              Input / Review tab to view lineage.
            </Alert>
          )}
        </Box>
      )}
    </Box>
  );
};

export default MRSCandidatesPage;
