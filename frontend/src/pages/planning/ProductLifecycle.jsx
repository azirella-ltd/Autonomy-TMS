import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Paper, Button, Chip, Tab, Tabs, Table, TableHead,
  TableBody, TableRow, TableCell, Dialog, DialogTitle, DialogContent,
  DialogActions, TextField, Select, MenuItem, FormControl, InputLabel,
  Grid, Card, CardContent, Alert, CircularProgress, LinearProgress,
  Tooltip,
} from '@mui/material';
import { Add, Launch, CheckCircle, Archive, Timeline } from '@mui/icons-material';
import api from '../../services/api';

const STAGES = ['concept', 'development', 'launch', 'growth', 'maturity', 'decline', 'eol', 'discontinued'];
const STAGE_COLORS = {
  concept: '#9e9e9e', development: '#1976d2', launch: '#2e7d32', growth: '#00897b',
  maturity: '#1565c0', decline: '#ef6c00', eol: '#d32f2f', discontinued: '#616161',
};
const NPI_STATUS_COLORS = {
  planning: 'default', qualification: 'info', pilot: 'warning',
  ramp_up: 'primary', launched: 'success', cancelled: 'error',
};
const EOL_STATUS_COLORS = {
  planning: 'default', approved: 'primary', in_progress: 'warning',
  completed: 'success', cancelled: 'error',
};

function TabPanel({ children, value, index }) {
  return value === index ? <Box sx={{ pt: 2 }}>{children}</Box> : null;
}

export default function ProductLifecycle() {
  const [tab, setTab] = useState(0);
  const [lifecycles, setLifecycles] = useState([]);
  const [summary, setSummary] = useState({});
  const [npiProjects, setNpiProjects] = useState([]);
  const [eolPlans, setEolPlans] = useState([]);
  const [historyItems, setHistoryItems] = useState([]);
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Dialogs
  const [npiDialogOpen, setNpiDialogOpen] = useState(false);
  const [eolDialogOpen, setEolDialogOpen] = useState(false);
  const [detailDialog, setDetailDialog] = useState({ open: false, type: null, data: null });
  const [stageFilter, setStageFilter] = useState('');

  // NPI form
  const [npiForm, setNpiForm] = useState({
    project_name: '', project_code: '', target_launch_date: '',
    product_ids: '', site_ids: '', demand_ramp_curve: '',
    initial_forecast_qty: '', investment: '', expected_revenue_yr1: '',
    risk_assessment: '', notes: '',
  });

  // EOL form
  const [eolForm, setEolForm] = useState({
    product_ids: '', successor_product_ids: '', last_buy_date: '',
    last_manufacture_date: '', last_ship_date: '', demand_phaseout_curve: '',
    estimated_write_off: '', notes: '',
  });

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [lcRes, sumRes, npiRes, eolRes, dashRes] = await Promise.allSettled([
        api.get('/v1/product-lifecycle/lifecycles', { params: stageFilter ? { stage: stageFilter } : {} }),
        api.get('/v1/product-lifecycle/lifecycle-summary'),
        api.get('/v1/product-lifecycle/npi'),
        api.get('/v1/product-lifecycle/eol'),
        api.get('/v1/product-lifecycle/dashboard'),
      ]);
      if (lcRes.status === 'fulfilled') setLifecycles(lcRes.value.data);
      if (sumRes.status === 'fulfilled') setSummary(sumRes.value.data);
      if (npiRes.status === 'fulfilled') setNpiProjects(npiRes.value.data);
      if (eolRes.status === 'fulfilled') setEolPlans(eolRes.value.data);
      if (dashRes.status === 'fulfilled') setDashboard(dashRes.value.data);
    } catch (e) {
      setError('Failed to load lifecycle data');
    }
    setLoading(false);
  }, [stageFilter]);

  useEffect(() => { loadAll(); }, [loadAll]);

  const loadHistory = async (entityType) => {
    try {
      // Load all history for given type
      const res = await api.get(`/product-lifecycle/history/${entityType}/0`);
      setHistoryItems(res.data);
    } catch { /* ignore */ }
  };

  useEffect(() => {
    if (tab === 3) loadHistory('lifecycle');
  }, [tab]);

  const createNpi = async () => {
    try {
      const payload = { project_name: npiForm.project_name, target_launch_date: npiForm.target_launch_date };
      if (npiForm.project_code) payload.project_code = npiForm.project_code;
      if (npiForm.initial_forecast_qty) payload.initial_forecast_qty = parseFloat(npiForm.initial_forecast_qty);
      if (npiForm.investment) payload.investment = parseFloat(npiForm.investment);
      if (npiForm.expected_revenue_yr1) payload.expected_revenue_yr1 = parseFloat(npiForm.expected_revenue_yr1);
      if (npiForm.risk_assessment) payload.risk_assessment = npiForm.risk_assessment;
      if (npiForm.notes) payload.notes = npiForm.notes;
      if (npiForm.product_ids) { try { payload.product_ids = JSON.parse(npiForm.product_ids); } catch { /* skip */ } }
      if (npiForm.site_ids) { try { payload.site_ids = JSON.parse(npiForm.site_ids); } catch { /* skip */ } }
      if (npiForm.demand_ramp_curve) { try { payload.demand_ramp_curve = JSON.parse(npiForm.demand_ramp_curve); } catch { /* skip */ } }
      await api.post('/v1/product-lifecycle/npi', payload);
      setNpiDialogOpen(false);
      setNpiForm({ project_name: '', project_code: '', target_launch_date: '', product_ids: '', site_ids: '', demand_ramp_curve: '', initial_forecast_qty: '', investment: '', expected_revenue_yr1: '', risk_assessment: '', notes: '' });
      loadAll();
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to create NPI project');
    }
  };

  const createEol = async () => {
    try {
      const payload = {};
      if (eolForm.last_buy_date) payload.last_buy_date = eolForm.last_buy_date;
      if (eolForm.last_manufacture_date) payload.last_manufacture_date = eolForm.last_manufacture_date;
      if (eolForm.last_ship_date) payload.last_ship_date = eolForm.last_ship_date;
      if (eolForm.estimated_write_off) payload.estimated_write_off = parseFloat(eolForm.estimated_write_off);
      if (eolForm.notes) payload.notes = eolForm.notes;
      if (eolForm.product_ids) { try { payload.product_ids = JSON.parse(eolForm.product_ids); } catch { /* skip */ } }
      if (eolForm.successor_product_ids) { try { payload.successor_product_ids = JSON.parse(eolForm.successor_product_ids); } catch { /* skip */ } }
      if (eolForm.demand_phaseout_curve) { try { payload.demand_phaseout_curve = JSON.parse(eolForm.demand_phaseout_curve); } catch { /* skip */ } }
      await api.post('/v1/product-lifecycle/eol', payload);
      setEolDialogOpen(false);
      setEolForm({ product_ids: '', successor_product_ids: '', last_buy_date: '', last_manufacture_date: '', last_ship_date: '', demand_phaseout_curve: '', estimated_write_off: '', notes: '' });
      loadAll();
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to create EOL plan');
    }
  };

  const handleNpiAction = async (npiId, action) => {
    try {
      await api.post(`/product-lifecycle/npi/${npiId}/${action}`);
      loadAll();
    } catch (e) { setError(e.response?.data?.detail || `Failed to ${action}`); }
  };

  const handleEolAction = async (eolId, action) => {
    try {
      await api.post(`/product-lifecycle/eol/${eolId}/${action}`);
      loadAll();
    } catch (e) { setError(e.response?.data?.detail || `Failed to ${action}`); }
  };

  const renderQualityGates = (gates) => {
    if (!gates || gates.length === 0) return <Typography variant="caption" color="text.secondary">No gates</Typography>;
    return (
      <Box sx={{ display: 'flex', gap: 0.5 }}>
        {gates.map((g, i) => (
          <Tooltip key={i} title={`${g.gate}: ${g.status}`}>
            <Box sx={{
              width: 12, height: 12, borderRadius: '50%',
              bgcolor: g.status === 'passed' ? '#4caf50' : g.status === 'failed' ? '#f44336' : g.status === 'in_progress' ? '#ff9800' : '#bdbdbd',
            }} />
          </Tooltip>
        ))}
      </Box>
    );
  };

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" gutterBottom>Product Lifecycle Management</Typography>
      {error && <Alert severity="error" onClose={() => setError('')} sx={{ mb: 2 }}>{error}</Alert>}

      <Paper sx={{ mb: 2 }}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)}>
          <Tab icon={<Timeline />} label="Overview" />
          <Tab icon={<Launch />} label="NPI Pipeline" />
          <Tab icon={<Archive />} label="EOL Management" />
          <Tab label="History" />
        </Tabs>
      </Paper>

      {/* Overview Tab */}
      <TabPanel value={tab} index={0}>
        {/* Stage distribution cards */}
        <Grid container spacing={1} sx={{ mb: 3 }}>
          {STAGES.map(s => (
            <Grid item xs={1.5} key={s}>
              <Card sx={{ textAlign: 'center', borderTop: `3px solid ${STAGE_COLORS[s]}` }}>
                <CardContent sx={{ py: 1, '&:last-child': { pb: 1 } }}>
                  <Typography variant="h5">{summary[s] || 0}</Typography>
                  <Typography variant="caption" sx={{ textTransform: 'capitalize' }}>{s}</Typography>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>

        <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel>Stage</InputLabel>
            <Select value={stageFilter} label="Stage" onChange={e => setStageFilter(e.target.value)}>
              <MenuItem value="">All</MenuItem>
              {STAGES.map(s => <MenuItem key={s} value={s}>{s}</MenuItem>)}
            </Select>
          </FormControl>
        </Box>

        {loading ? <CircularProgress /> : (
          <Paper>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Product ID</TableCell>
                  <TableCell>Stage</TableCell>
                  <TableCell>Stage Entered</TableCell>
                  <TableCell>Expected Launch</TableCell>
                  <TableCell>Expected EOL</TableCell>
                  <TableCell>Successor</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {lifecycles.map(lc => (
                  <TableRow key={lc.id}>
                    <TableCell>{lc.product_id}</TableCell>
                    <TableCell>
                      <Chip size="small" label={lc.lifecycle_stage}
                        sx={{ bgcolor: STAGE_COLORS[lc.lifecycle_stage], color: 'white' }} />
                    </TableCell>
                    <TableCell>{lc.stage_entered_at ? new Date(lc.stage_entered_at).toLocaleDateString() : '—'}</TableCell>
                    <TableCell>{lc.expected_launch_date || '—'}</TableCell>
                    <TableCell>{lc.expected_eol_date || '—'}</TableCell>
                    <TableCell>{lc.successor_product_id || '—'}</TableCell>
                  </TableRow>
                ))}
                {lifecycles.length === 0 && (
                  <TableRow><TableCell colSpan={6} align="center">No lifecycle records</TableCell></TableRow>
                )}
              </TableBody>
            </Table>
          </Paper>
        )}
      </TabPanel>

      {/* NPI Pipeline Tab */}
      <TabPanel value={tab} index={1}>
        <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 2 }}>
          <Button variant="contained" startIcon={<Add />} onClick={() => setNpiDialogOpen(true)}>
            New NPI Project
          </Button>
        </Box>
        <Paper>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Project</TableCell>
                <TableCell>Code</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Target Launch</TableCell>
                <TableCell>Products</TableCell>
                <TableCell>Quality Gates</TableCell>
                <TableCell>Investment</TableCell>
                <TableCell>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {npiProjects.map(n => (
                <TableRow key={n.id}>
                  <TableCell>{n.project_name}</TableCell>
                  <TableCell>{n.project_code || '—'}</TableCell>
                  <TableCell><Chip size="small" label={n.status} color={NPI_STATUS_COLORS[n.status]} /></TableCell>
                  <TableCell>{n.target_launch_date}</TableCell>
                  <TableCell>{n.product_ids?.length || 0}</TableCell>
                  <TableCell>{renderQualityGates(n.quality_gates)}</TableCell>
                  <TableCell>{n.investment != null ? `$${n.investment.toLocaleString()}` : '—'}</TableCell>
                  <TableCell>
                    {(n.status === 'pilot' || n.status === 'ramp_up') && (
                      <Button size="small" color="success" onClick={() => handleNpiAction(n.id, 'launch')}>
                        Launch
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {npiProjects.length === 0 && (
                <TableRow><TableCell colSpan={8} align="center">No NPI projects</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </Paper>
      </TabPanel>

      {/* EOL Management Tab */}
      <TabPanel value={tab} index={2}>
        <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 2 }}>
          <Button variant="contained" startIcon={<Add />} onClick={() => setEolDialogOpen(true)}>
            New EOL Plan
          </Button>
        </Box>
        <Paper>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>ID</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Products</TableCell>
                <TableCell>Last Buy</TableCell>
                <TableCell>Last Ship</TableCell>
                <TableCell>Est. Write-Off</TableCell>
                <TableCell>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {eolPlans.map(e => (
                <TableRow key={e.id}>
                  <TableCell>{e.id}</TableCell>
                  <TableCell><Chip size="small" label={e.status} color={EOL_STATUS_COLORS[e.status]} /></TableCell>
                  <TableCell>{e.product_ids?.length || 0} products</TableCell>
                  <TableCell>{e.last_buy_date || '—'}</TableCell>
                  <TableCell>{e.last_ship_date || '—'}</TableCell>
                  <TableCell>{e.estimated_write_off != null ? `$${e.estimated_write_off.toLocaleString()}` : '—'}</TableCell>
                  <TableCell>
                    {e.status === 'planning' && (
                      <Button size="small" color="primary" onClick={() => handleEolAction(e.id, 'approve')}>Approve</Button>
                    )}
                    {(e.status === 'approved' || e.status === 'in_progress') && (
                      <Button size="small" color="success" onClick={() => handleEolAction(e.id, 'complete')}>Complete</Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {eolPlans.length === 0 && (
                <TableRow><TableCell colSpan={7} align="center">No EOL plans</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </Paper>
      </TabPanel>

      {/* History Tab */}
      <TabPanel value={tab} index={3}>
        <Paper>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Time</TableCell>
                <TableCell>Entity</TableCell>
                <TableCell>Action</TableCell>
                <TableCell>Previous</TableCell>
                <TableCell>New</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {historyItems.map(h => (
                <TableRow key={h.id}>
                  <TableCell>{new Date(h.created_at).toLocaleString()}</TableCell>
                  <TableCell><Chip size="small" label={`${h.entity_type} #${h.entity_id}`} /></TableCell>
                  <TableCell>{h.action}</TableCell>
                  <TableCell>{h.previous_value ? JSON.stringify(h.previous_value).substring(0, 50) : '—'}</TableCell>
                  <TableCell>{h.new_value ? JSON.stringify(h.new_value).substring(0, 50) : '—'}</TableCell>
                </TableRow>
              ))}
              {historyItems.length === 0 && (
                <TableRow><TableCell colSpan={5} align="center">No history records</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </Paper>
      </TabPanel>

      {/* NPI Create Dialog */}
      <Dialog open={npiDialogOpen} onClose={() => setNpiDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>New NPI Project</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 0.5 }}>
            <Grid item xs={8}>
              <TextField fullWidth label="Project Name" value={npiForm.project_name}
                onChange={e => setNpiForm({ ...npiForm, project_name: e.target.value })} />
            </Grid>
            <Grid item xs={4}>
              <TextField fullWidth label="Code" value={npiForm.project_code}
                onChange={e => setNpiForm({ ...npiForm, project_code: e.target.value })} />
            </Grid>
            <Grid item xs={6}>
              <TextField fullWidth label="Target Launch" type="date" InputLabelProps={{ shrink: true }}
                value={npiForm.target_launch_date}
                onChange={e => setNpiForm({ ...npiForm, target_launch_date: e.target.value })} />
            </Grid>
            <Grid item xs={6}>
              <TextField fullWidth label="Initial Forecast Qty" type="number"
                value={npiForm.initial_forecast_qty}
                onChange={e => setNpiForm({ ...npiForm, initial_forecast_qty: e.target.value })} />
            </Grid>
            <Grid item xs={6}>
              <TextField fullWidth label="Product IDs (JSON)" value={npiForm.product_ids}
                onChange={e => setNpiForm({ ...npiForm, product_ids: e.target.value })} placeholder='["PROD-NEW-001"]' />
            </Grid>
            <Grid item xs={6}>
              <TextField fullWidth label="Site IDs (JSON)" value={npiForm.site_ids}
                onChange={e => setNpiForm({ ...npiForm, site_ids: e.target.value })} placeholder='[1, 2]' />
            </Grid>
            <Grid item xs={12}>
              <TextField fullWidth label="Demand Ramp Curve (JSON)" value={npiForm.demand_ramp_curve}
                onChange={e => setNpiForm({ ...npiForm, demand_ramp_curve: e.target.value })}
                placeholder='[10, 25, 50, 75, 100]' helperText="Week-by-week demand ramp %" />
            </Grid>
            <Grid item xs={6}>
              <TextField fullWidth label="Investment" type="number" value={npiForm.investment}
                onChange={e => setNpiForm({ ...npiForm, investment: e.target.value })} />
            </Grid>
            <Grid item xs={6}>
              <TextField fullWidth label="Expected Revenue Yr1" type="number" value={npiForm.expected_revenue_yr1}
                onChange={e => setNpiForm({ ...npiForm, expected_revenue_yr1: e.target.value })} />
            </Grid>
            <Grid item xs={12}>
              <TextField fullWidth label="Notes" multiline rows={2} value={npiForm.notes}
                onChange={e => setNpiForm({ ...npiForm, notes: e.target.value })} />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setNpiDialogOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={createNpi}
            disabled={!npiForm.project_name || !npiForm.target_launch_date}>Create</Button>
        </DialogActions>
      </Dialog>

      {/* EOL Create Dialog */}
      <Dialog open={eolDialogOpen} onClose={() => setEolDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>New EOL Plan</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 0.5 }}>
            <Grid item xs={12}>
              <TextField fullWidth label="Product IDs (JSON)" value={eolForm.product_ids}
                onChange={e => setEolForm({ ...eolForm, product_ids: e.target.value })} placeholder='["PROD-OLD-001"]' />
            </Grid>
            <Grid item xs={12}>
              <TextField fullWidth label="Successor Product IDs (JSON)" value={eolForm.successor_product_ids}
                onChange={e => setEolForm({ ...eolForm, successor_product_ids: e.target.value })} placeholder='["PROD-NEW-001"]' />
            </Grid>
            <Grid item xs={4}>
              <TextField fullWidth label="Last Buy" type="date" InputLabelProps={{ shrink: true }}
                value={eolForm.last_buy_date} onChange={e => setEolForm({ ...eolForm, last_buy_date: e.target.value })} />
            </Grid>
            <Grid item xs={4}>
              <TextField fullWidth label="Last Manufacture" type="date" InputLabelProps={{ shrink: true }}
                value={eolForm.last_manufacture_date} onChange={e => setEolForm({ ...eolForm, last_manufacture_date: e.target.value })} />
            </Grid>
            <Grid item xs={4}>
              <TextField fullWidth label="Last Ship" type="date" InputLabelProps={{ shrink: true }}
                value={eolForm.last_ship_date} onChange={e => setEolForm({ ...eolForm, last_ship_date: e.target.value })} />
            </Grid>
            <Grid item xs={12}>
              <TextField fullWidth label="Demand Phase-Out Curve (JSON)" value={eolForm.demand_phaseout_curve}
                onChange={e => setEolForm({ ...eolForm, demand_phaseout_curve: e.target.value })}
                placeholder='[90, 75, 50, 25, 10, 0]' helperText="Week-by-week demand % reduction" />
            </Grid>
            <Grid item xs={6}>
              <TextField fullWidth label="Estimated Write-Off" type="number" value={eolForm.estimated_write_off}
                onChange={e => setEolForm({ ...eolForm, estimated_write_off: e.target.value })} />
            </Grid>
            <Grid item xs={12}>
              <TextField fullWidth label="Notes" multiline rows={2} value={eolForm.notes}
                onChange={e => setEolForm({ ...eolForm, notes: e.target.value })} />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEolDialogOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={createEol}>Create</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
