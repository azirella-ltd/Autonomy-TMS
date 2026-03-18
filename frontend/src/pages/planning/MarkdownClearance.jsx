import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Paper, Button, Chip, Tab, Tabs, Table, TableHead,
  TableBody, TableRow, TableCell, Dialog, DialogTitle, DialogContent,
  DialogActions, TextField, Select, MenuItem, FormControl, InputLabel,
  Grid, Card, CardContent, Alert, CircularProgress, LinearProgress,
} from '@mui/material';
import { Add } from '@mui/icons-material';
import api from '../../services/api';

const STATUS_COLORS = {
  draft: 'default', approved: 'primary', active: 'success',
  completed: 'default', cancelled: 'error',
};

function TabPanel({ children, value, index }) {
  return value === index ? <Box sx={{ pt: 2 }}>{children}</Box> : null;
}

export default function MarkdownClearance() {
  const [tab, setTab] = useState(0);
  const [plans, setPlans] = useState([]);
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState({
    name: '', start_date: '', end_date: '', product_ids: '',
    site_ids: '', markdown_schedule: '', original_price: '',
    floor_price: '', target_sell_through_pct: '100',
    disposition_if_unsold: 'scrap', notes: '',
  });

  const loadPlans = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (statusFilter) params.status = statusFilter;
      const res = await api.get('/product-lifecycle/markdown', { params });
      setPlans(res.data);
    } catch (e) {
      setError('Failed to load markdown plans');
    }
    setLoading(false);
  }, [statusFilter]);

  const loadDashboard = useCallback(async () => {
    try {
      const res = await api.get('/product-lifecycle/dashboard');
      setDashboard(res.data);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadPlans(); }, [loadPlans]);
  useEffect(() => { if (tab === 2) loadDashboard(); }, [tab, loadDashboard]);

  const createPlan = async () => {
    try {
      const payload = {
        name: form.name,
        start_date: form.start_date,
        end_date: form.end_date,
        disposition_if_unsold: form.disposition_if_unsold,
      };
      if (form.original_price) payload.original_price = parseFloat(form.original_price);
      if (form.floor_price) payload.floor_price = parseFloat(form.floor_price);
      if (form.target_sell_through_pct) payload.target_sell_through_pct = parseFloat(form.target_sell_through_pct);
      if (form.notes) payload.notes = form.notes;
      if (form.product_ids) { try { payload.product_ids = JSON.parse(form.product_ids); } catch { /* skip */ } }
      if (form.site_ids) { try { payload.site_ids = JSON.parse(form.site_ids); } catch { /* skip */ } }
      if (form.markdown_schedule) { try { payload.markdown_schedule = JSON.parse(form.markdown_schedule); } catch { /* skip */ } }
      await api.post('/product-lifecycle/markdown', payload);
      setDialogOpen(false);
      setForm({ name: '', start_date: '', end_date: '', product_ids: '', site_ids: '', markdown_schedule: '', original_price: '', floor_price: '', target_sell_through_pct: '100', disposition_if_unsold: 'scrap', notes: '' });
      loadPlans();
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to create markdown plan');
    }
  };

  const handleActivate = async (id) => {
    try {
      await api.post(`/product-lifecycle/markdown/${id}/activate`);
      loadPlans();
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to activate');
    }
  };

  const getSellThroughColor = (actual, target) => {
    if (!actual || !target) return 'grey';
    const ratio = actual / target;
    if (ratio >= 0.8) return 'success';
    if (ratio >= 0.5) return 'warning';
    return 'error';
  };

  const getDaysRemaining = (endDate) => {
    if (!endDate) return null;
    const diff = Math.ceil((new Date(endDate) - new Date()) / (1000 * 60 * 60 * 24));
    return diff > 0 ? diff : 0;
  };

  const activePlans = plans.filter(p => p.status === 'active');

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
        <Typography variant="h5">Markdown & Clearance</Typography>
        <Button variant="contained" startIcon={<Add />} onClick={() => setDialogOpen(true)}>
          Create Plan
        </Button>
      </Box>

      {error && <Alert severity="error" onClose={() => setError('')} sx={{ mb: 2 }}>{error}</Alert>}

      <Paper sx={{ mb: 2 }}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)}>
          <Tab label={`Active (${activePlans.length})`} />
          <Tab label="All Plans" />
          <Tab label="Analytics" />
        </Tabs>
      </Paper>

      {/* Active Markdowns Tab */}
      <TabPanel value={tab} index={0}>
        {loading ? <CircularProgress /> : (
          <Grid container spacing={2}>
            {activePlans.map(m => {
              const daysLeft = getDaysRemaining(m.end_date);
              const sellColor = getSellThroughColor(m.actual_sell_through_pct, m.target_sell_through_pct);
              return (
                <Grid item xs={12} md={6} lg={4} key={m.id}>
                  <Card>
                    <CardContent>
                      <Typography variant="h6" gutterBottom>{m.name}</Typography>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                        <Typography variant="body2" color="text.secondary">
                          {m.product_ids?.length || 0} products
                        </Typography>
                        <Chip size="small" label={`${m.current_discount_pct || 0}% off`} color="error" />
                      </Box>

                      <Typography variant="body2" gutterBottom>Sell-Through</Typography>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                        <LinearProgress
                          variant="determinate"
                          value={Math.min(m.actual_sell_through_pct || 0, 100)}
                          color={sellColor}
                          sx={{ flexGrow: 1, height: 8, borderRadius: 4 }}
                        />
                        <Typography variant="body2">
                          {m.actual_sell_through_pct != null ? `${m.actual_sell_through_pct}%` : '—'}
                        </Typography>
                      </Box>

                      <Grid container spacing={1}>
                        <Grid item xs={6}>
                          <Typography variant="caption" color="text.secondary">Revenue</Typography>
                          <Typography variant="body2">
                            {m.revenue_recovered != null ? `$${m.revenue_recovered.toLocaleString()}` : '—'}
                          </Typography>
                        </Grid>
                        <Grid item xs={6}>
                          <Typography variant="caption" color="text.secondary">Units Left</Typography>
                          <Typography variant="body2">
                            {m.units_remaining != null ? m.units_remaining.toLocaleString() : '—'}
                          </Typography>
                        </Grid>
                        <Grid item xs={6}>
                          <Typography variant="caption" color="text.secondary">Days Left</Typography>
                          <Typography variant="body2" color={daysLeft <= 7 ? 'error.main' : 'text.primary'}>
                            {daysLeft != null ? daysLeft : '—'}
                          </Typography>
                        </Grid>
                        <Grid item xs={6}>
                          <Typography variant="caption" color="text.secondary">If Unsold</Typography>
                          <Typography variant="body2" sx={{ textTransform: 'capitalize' }}>
                            {m.disposition_if_unsold?.replace(/_/g, ' ')}
                          </Typography>
                        </Grid>
                      </Grid>

                      {m.markdown_schedule && m.markdown_schedule.length > 0 && (
                        <Box sx={{ mt: 1 }}>
                          <Typography variant="caption" color="text.secondary">Schedule</Typography>
                          <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
                            {m.markdown_schedule.map((s, i) => (
                              <Chip key={i} size="small" variant="outlined"
                                label={`Wk${s.week}: ${s.discount_pct}%`} />
                            ))}
                          </Box>
                        </Box>
                      )}
                    </CardContent>
                  </Card>
                </Grid>
              );
            })}
            {activePlans.length === 0 && (
              <Grid item xs={12}>
                <Paper sx={{ p: 3, textAlign: 'center' }}>
                  <Typography color="text.secondary">No active markdown plans</Typography>
                </Paper>
              </Grid>
            )}
          </Grid>
        )}
      </TabPanel>

      {/* All Plans Tab */}
      <TabPanel value={tab} index={1}>
        <Box sx={{ mb: 2 }}>
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel>Status</InputLabel>
            <Select value={statusFilter} label="Status" onChange={e => setStatusFilter(e.target.value)}>
              <MenuItem value="">All</MenuItem>
              {Object.keys(STATUS_COLORS).map(s => <MenuItem key={s} value={s}>{s}</MenuItem>)}
            </Select>
          </FormControl>
        </Box>
        {loading ? <CircularProgress /> : (
          <Paper>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Name</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Products</TableCell>
                  <TableCell>Schedule</TableCell>
                  <TableCell>Sell-Through</TableCell>
                  <TableCell>Revenue</TableCell>
                  <TableCell>Dates</TableCell>
                  <TableCell>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {plans.map(m => (
                  <TableRow key={m.id}>
                    <TableCell>{m.name}</TableCell>
                    <TableCell><Chip size="small" label={m.status} color={STATUS_COLORS[m.status]} /></TableCell>
                    <TableCell>{m.product_ids?.length || 0}</TableCell>
                    <TableCell>
                      {m.markdown_schedule?.map(s => `${s.discount_pct}%`).join(' → ') || '—'}
                    </TableCell>
                    <TableCell>{m.actual_sell_through_pct != null ? `${m.actual_sell_through_pct}%` : '—'}</TableCell>
                    <TableCell>{m.revenue_recovered != null ? `$${m.revenue_recovered.toLocaleString()}` : '—'}</TableCell>
                    <TableCell>{m.start_date} — {m.end_date}</TableCell>
                    <TableCell>
                      {(m.status === 'draft' || m.status === 'approved') && (
                        <Button size="small" color="success" onClick={() => handleActivate(m.id)}>Activate</Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
                {plans.length === 0 && (
                  <TableRow><TableCell colSpan={8} align="center">No markdown plans</TableCell></TableRow>
                )}
              </TableBody>
            </Table>
          </Paper>
        )}
      </TabPanel>

      {/* Analytics Tab */}
      <TabPanel value={tab} index={2}>
        {dashboard ? (
          <Grid container spacing={2}>
            <Grid item xs={3}>
              <Card><CardContent>
                <Typography color="text.secondary" gutterBottom>Total Plans</Typography>
                <Typography variant="h4">{Object.values(dashboard.markdown_by_status || {}).reduce((a, b) => a + b, 0)}</Typography>
              </CardContent></Card>
            </Grid>
            <Grid item xs={3}>
              <Card><CardContent>
                <Typography color="text.secondary" gutterBottom>Active</Typography>
                <Typography variant="h4" color="success.main">{dashboard.markdown_active || 0}</Typography>
              </CardContent></Card>
            </Grid>
            <Grid item xs={3}>
              <Card><CardContent>
                <Typography color="text.secondary" gutterBottom>Avg Sell-Through</Typography>
                <Typography variant="h4">
                  {plans.filter(p => p.actual_sell_through_pct != null).length > 0
                    ? `${Math.round(plans.filter(p => p.actual_sell_through_pct != null).reduce((sum, p) => sum + p.actual_sell_through_pct, 0) / plans.filter(p => p.actual_sell_through_pct != null).length)}%`
                    : '—'}
                </Typography>
              </CardContent></Card>
            </Grid>
            <Grid item xs={3}>
              <Card><CardContent>
                <Typography color="text.secondary" gutterBottom>Total Revenue</Typography>
                <Typography variant="h4">
                  ${plans.reduce((sum, p) => sum + (p.revenue_recovered || 0), 0).toLocaleString()}
                </Typography>
              </CardContent></Card>
            </Grid>
            <Grid item xs={12}>
              <Card><CardContent>
                <Typography variant="subtitle2" gutterBottom>By Status</Typography>
                {Object.entries(dashboard.markdown_by_status || {}).map(([k, v]) => (
                  <Box key={k} sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                    <Chip size="small" label={k} color={STATUS_COLORS[k]} />
                    <Typography>{v}</Typography>
                  </Box>
                ))}
              </CardContent></Card>
            </Grid>
          </Grid>
        ) : <CircularProgress />}
      </TabPanel>

      {/* Create Dialog */}
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Create Markdown Plan</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 0.5 }}>
            <Grid item xs={12}>
              <TextField fullWidth label="Name" value={form.name}
                onChange={e => setForm({ ...form, name: e.target.value })} />
            </Grid>
            <Grid item xs={6}>
              <TextField fullWidth label="Start Date" type="date" InputLabelProps={{ shrink: true }}
                value={form.start_date} onChange={e => setForm({ ...form, start_date: e.target.value })} />
            </Grid>
            <Grid item xs={6}>
              <TextField fullWidth label="End Date" type="date" InputLabelProps={{ shrink: true }}
                value={form.end_date} onChange={e => setForm({ ...form, end_date: e.target.value })} />
            </Grid>
            <Grid item xs={6}>
              <TextField fullWidth label="Product IDs (JSON)" value={form.product_ids}
                onChange={e => setForm({ ...form, product_ids: e.target.value })} placeholder='["PROD-001"]' />
            </Grid>
            <Grid item xs={6}>
              <TextField fullWidth label="Site IDs (JSON)" value={form.site_ids}
                onChange={e => setForm({ ...form, site_ids: e.target.value })} placeholder='[1, 2]' />
            </Grid>
            <Grid item xs={12}>
              <TextField fullWidth label="Markdown Schedule (JSON)" value={form.markdown_schedule}
                onChange={e => setForm({ ...form, markdown_schedule: e.target.value })}
                placeholder='[{"week": 1, "discount_pct": 10}, {"week": 3, "discount_pct": 25}]'
                helperText="Week-by-week discount progression" />
            </Grid>
            <Grid item xs={4}>
              <TextField fullWidth label="Original Price" type="number" value={form.original_price}
                onChange={e => setForm({ ...form, original_price: e.target.value })} />
            </Grid>
            <Grid item xs={4}>
              <TextField fullWidth label="Floor Price" type="number" value={form.floor_price}
                onChange={e => setForm({ ...form, floor_price: e.target.value })} />
            </Grid>
            <Grid item xs={4}>
              <TextField fullWidth label="Target Sell-Through %" type="number" value={form.target_sell_through_pct}
                onChange={e => setForm({ ...form, target_sell_through_pct: e.target.value })} />
            </Grid>
            <Grid item xs={6}>
              <FormControl fullWidth>
                <InputLabel>If Unsold</InputLabel>
                <Select value={form.disposition_if_unsold} label="If Unsold"
                  onChange={e => setForm({ ...form, disposition_if_unsold: e.target.value })}>
                  <MenuItem value="scrap">Scrap</MenuItem>
                  <MenuItem value="donate">Donate</MenuItem>
                  <MenuItem value="return_to_vendor">Return to Vendor</MenuItem>
                  <MenuItem value="hold">Hold</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12}>
              <TextField fullWidth label="Notes" multiline rows={2} value={form.notes}
                onChange={e => setForm({ ...form, notes: e.target.value })} />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={createPlan}
            disabled={!form.name || !form.start_date || !form.end_date}>Create</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
