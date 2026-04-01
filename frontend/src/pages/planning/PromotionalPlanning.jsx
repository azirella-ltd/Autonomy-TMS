import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Paper, Button, Chip, Tab, Tabs, Table, TableHead,
  TableBody, TableRow, TableCell, Dialog, DialogTitle, DialogContent,
  DialogActions, TextField, Select, MenuItem, FormControl, InputLabel,
  Grid, Card, CardContent, IconButton, Alert, CircularProgress, Tooltip,
} from '@mui/material';
import {
  Add, Edit, CheckCircle, Cancel, CalendarMonth, TrendingUp,
  Visibility, ChevronLeft, ChevronRight,
} from '@mui/icons-material';
import api from '../../services/api';

const PROMO_TYPES = [
  'price_discount', 'bogo', 'bundle', 'display',
  'seasonal', 'clearance', 'loyalty', 'new_product_launch',
];

const STATUS_COLORS = {
  draft: 'default', planned: 'info', approved: 'primary',
  active: 'success', completed: 'default', cancelled: 'error',
};

const TYPE_COLORS = {
  price_discount: '#1976d2', bogo: '#9c27b0', bundle: '#00897b',
  seasonal: '#ef6c00', clearance: '#d32f2f', display: '#558b2f',
  loyalty: '#5c6bc0', new_product_launch: '#2e7d32',
};

function TabPanel({ children, value, index }) {
  return value === index ? <Box sx={{ pt: 2 }}>{children}</Box> : null;
}

export default function PromotionalPlanning() {
  const [tab, setTab] = useState(0);
  const [promotions, setPromotions] = useState([]);
  const [calendar, setCalendar] = useState([]);
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedPromo, setSelectedPromo] = useState(null);
  const [history, setHistory] = useState([]);
  const [calMonth, setCalMonth] = useState(new Date());
  const [form, setForm] = useState({
    name: '', promotion_type: 'price_discount', description: '',
    start_date: '', end_date: '', product_ids: '', site_ids: '',
    channel_ids: '', expected_uplift_pct: '', budget: '', notes: '',
  });

  const loadPromotions = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (statusFilter) params.status = statusFilter;
      if (typeFilter) params.promotion_type = typeFilter;
      const res = await api.get('/v1/promotions/', { params });
      setPromotions(res.data);
    } catch (e) {
      setError('Failed to load promotions');
    }
    setLoading(false);
  }, [statusFilter, typeFilter]);

  const loadCalendar = useCallback(async () => {
    const y = calMonth.getFullYear();
    const m = calMonth.getMonth();
    const start = new Date(y, m, 1).toISOString().split('T')[0];
    const end = new Date(y, m + 1, 0).toISOString().split('T')[0];
    try {
      const res = await api.get('/v1/promotions/calendar', { params: { start_date: start, end_date: end } });
      setCalendar(res.data);
    } catch (e) { /* ignore */ }
  }, [calMonth]);

  const loadDashboard = useCallback(async () => {
    try {
      const res = await api.get('/v1/promotions/dashboard');
      setDashboard(res.data);
    } catch (e) { /* ignore */ }
  }, []);

  useEffect(() => { loadPromotions(); }, [loadPromotions]);
  useEffect(() => { if (tab === 0) loadCalendar(); }, [tab, loadCalendar]);
  useEffect(() => { if (tab === 3) loadDashboard(); }, [tab, loadDashboard]);

  const handleCreate = async () => {
    try {
      const payload = {
        name: form.name,
        promotion_type: form.promotion_type,
        start_date: form.start_date,
        end_date: form.end_date,
        description: form.description || undefined,
        notes: form.notes || undefined,
      };
      if (form.expected_uplift_pct) payload.expected_uplift_pct = parseFloat(form.expected_uplift_pct);
      if (form.budget) payload.budget = parseFloat(form.budget);
      if (form.product_ids) {
        try { payload.product_ids = JSON.parse(form.product_ids); } catch { /* skip */ }
      }
      if (form.site_ids) {
        try { payload.site_ids = JSON.parse(form.site_ids); } catch { /* skip */ }
      }
      if (form.channel_ids) {
        try { payload.channel_ids = JSON.parse(form.channel_ids); } catch { /* skip */ }
      }
      await api.post('/v1/promotions/', payload);
      setDialogOpen(false);
      setForm({ name: '', promotion_type: 'price_discount', description: '', start_date: '', end_date: '', product_ids: '', site_ids: '', channel_ids: '', expected_uplift_pct: '', budget: '', notes: '' });
      loadPromotions();
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to create promotion');
    }
  };

  const handleAction = async (id, action, body = {}) => {
    try {
      await api.post(`/promotions/${id}/${action}`, body);
      loadPromotions();
      if (selectedPromo?.id === id) {
        const res = await api.get(`/promotions/${id}`);
        setSelectedPromo(res.data);
      }
    } catch (e) {
      setError(e.response?.data?.detail || `Failed to ${action} promotion`);
    }
  };

  const openDetail = async (promo) => {
    setSelectedPromo(promo);
    setDetailOpen(true);
    try {
      const res = await api.get(`/promotions/${promo.id}/history`);
      setHistory(res.data);
    } catch { /* ignore */ }
  };

  // Calendar rendering
  const renderCalendar = () => {
    const y = calMonth.getFullYear();
    const m = calMonth.getMonth();
    const firstDay = new Date(y, m, 1).getDay();
    const daysInMonth = new Date(y, m + 1, 0).getDate();
    const weeks = [];
    let day = 1 - firstDay;

    for (let w = 0; w < 6 && day <= daysInMonth; w++) {
      const week = [];
      for (let d = 0; d < 7; d++, day++) {
        if (day < 1 || day > daysInMonth) {
          week.push(<TableCell key={d} sx={{ minWidth: 100, height: 80, bgcolor: '#fafafa' }} />);
        } else {
          const dateStr = `${y}-${String(m + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
          const dayPromos = calendar.filter(p => p.start_date <= dateStr && p.end_date >= dateStr);
          week.push(
            <TableCell key={d} sx={{ minWidth: 100, height: 80, verticalAlign: 'top', p: 0.5 }}>
              <Typography variant="caption" sx={{ fontWeight: 'bold' }}>{day}</Typography>
              {dayPromos.slice(0, 3).map(p => (
                <Box
                  key={p.id}
                  onClick={() => openDetail(p)}
                  sx={{
                    bgcolor: TYPE_COLORS[p.promotion_type] || '#999',
                    color: 'white', fontSize: 10, px: 0.5, borderRadius: 0.5,
                    mb: 0.25, cursor: 'pointer', overflow: 'hidden',
                    whiteSpace: 'nowrap', textOverflow: 'ellipsis',
                  }}
                >
                  {p.name}
                </Box>
              ))}
              {dayPromos.length > 3 && (
                <Typography variant="caption" color="text.secondary">+{dayPromos.length - 3} more</Typography>
              )}
            </TableCell>
          );
        }
      }
      weeks.push(<TableRow key={w}>{week}</TableRow>);
    }
    return weeks;
  };

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
        <Typography variant="h5">Promotional Planning</Typography>
        <Button variant="contained" startIcon={<Add />} onClick={() => setDialogOpen(true)}>
          Create Promotion
        </Button>
      </Box>

      {error && <Alert severity="error" onClose={() => setError('')} sx={{ mb: 2 }}>{error}</Alert>}

      <Paper sx={{ mb: 2 }}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)}>
          <Tab icon={<CalendarMonth />} label="Calendar" />
          <Tab icon={<TrendingUp />} label="Active" />
          <Tab icon={<Visibility />} label="All Promotions" />
          <Tab label="Dashboard" />
        </Tabs>
      </Paper>

      {/* Calendar Tab */}
      <TabPanel value={tab} index={0}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2, gap: 2 }}>
          <IconButton onClick={() => setCalMonth(new Date(calMonth.getFullYear(), calMonth.getMonth() - 1))}>
            <ChevronLeft />
          </IconButton>
          <Typography variant="h6">
            {calMonth.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
          </Typography>
          <IconButton onClick={() => setCalMonth(new Date(calMonth.getFullYear(), calMonth.getMonth() + 1))}>
            <ChevronRight />
          </IconButton>
        </Box>
        <Paper>
          <Table size="small">
            <TableHead>
              <TableRow>
                {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(d => (
                  <TableCell key={d} sx={{ fontWeight: 'bold', textAlign: 'center' }}>{d}</TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>{renderCalendar()}</TableBody>
          </Table>
        </Paper>
        <Box sx={{ mt: 1, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          {PROMO_TYPES.map(t => (
            <Chip key={t} size="small" label={t.replace(/_/g, ' ')}
              sx={{ bgcolor: TYPE_COLORS[t], color: 'white', fontSize: 11 }} />
          ))}
        </Box>
      </TabPanel>

      {/* Active Tab */}
      <TabPanel value={tab} index={1}>
        {loading ? <CircularProgress /> : (
          <Paper>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Name</TableCell>
                  <TableCell>Type</TableCell>
                  <TableCell>Dates</TableCell>
                  <TableCell>Products</TableCell>
                  <TableCell>Expected Uplift</TableCell>
                  <TableCell>Actual Uplift</TableCell>
                  <TableCell>Budget</TableCell>
                  <TableCell>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {promotions.filter(p => p.status === 'active').map(p => (
                  <TableRow key={p.id} hover onClick={() => openDetail(p)} sx={{ cursor: 'pointer' }}>
                    <TableCell>{p.name}</TableCell>
                    <TableCell>
                      <Chip size="small" label={p.promotion_type.replace(/_/g, ' ')}
                        sx={{ bgcolor: TYPE_COLORS[p.promotion_type], color: 'white' }} />
                    </TableCell>
                    <TableCell>{p.start_date} — {p.end_date}</TableCell>
                    <TableCell>{p.product_ids?.length || 0}</TableCell>
                    <TableCell>{p.expected_uplift_pct != null ? `${p.expected_uplift_pct}%` : '—'}</TableCell>
                    <TableCell>{p.actual_uplift_pct != null ? `${p.actual_uplift_pct}%` : '—'}</TableCell>
                    <TableCell>{p.budget != null ? `$${p.budget.toLocaleString()}` : '—'}</TableCell>
                    <TableCell onClick={e => e.stopPropagation()}>
                      <Button size="small" color="success" onClick={() => handleAction(p.id, 'complete')}>Complete</Button>
                      <Button size="small" color="error" onClick={() => handleAction(p.id, 'cancel', { reason: '' })}>Cancel</Button>
                    </TableCell>
                  </TableRow>
                ))}
                {promotions.filter(p => p.status === 'active').length === 0 && (
                  <TableRow><TableCell colSpan={8} align="center">No active promotions</TableCell></TableRow>
                )}
              </TableBody>
            </Table>
          </Paper>
        )}
      </TabPanel>

      {/* All Promotions Tab */}
      <TabPanel value={tab} index={2}>
        <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel>Status</InputLabel>
            <Select value={statusFilter} label="Status" onChange={e => setStatusFilter(e.target.value)}>
              <MenuItem value="">All</MenuItem>
              {Object.keys(STATUS_COLORS).map(s => <MenuItem key={s} value={s}>{s}</MenuItem>)}
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 160 }}>
            <InputLabel>Type</InputLabel>
            <Select value={typeFilter} label="Type" onChange={e => setTypeFilter(e.target.value)}>
              <MenuItem value="">All</MenuItem>
              {PROMO_TYPES.map(t => <MenuItem key={t} value={t}>{t.replace(/_/g, ' ')}</MenuItem>)}
            </Select>
          </FormControl>
        </Box>
        {loading ? <CircularProgress /> : (
          <Paper>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Name</TableCell>
                  <TableCell>Type</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Start</TableCell>
                  <TableCell>End</TableCell>
                  <TableCell>Products</TableCell>
                  <TableCell>Uplift</TableCell>
                  <TableCell>Budget</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {promotions.map(p => (
                  <TableRow key={p.id} hover onClick={() => openDetail(p)} sx={{ cursor: 'pointer' }}>
                    <TableCell>{p.name}</TableCell>
                    <TableCell>
                      <Chip size="small" label={p.promotion_type.replace(/_/g, ' ')}
                        sx={{ bgcolor: TYPE_COLORS[p.promotion_type], color: 'white' }} />
                    </TableCell>
                    <TableCell><Chip size="small" label={p.status} color={STATUS_COLORS[p.status]} /></TableCell>
                    <TableCell>{p.start_date}</TableCell>
                    <TableCell>{p.end_date}</TableCell>
                    <TableCell>{p.product_ids?.length || 0}</TableCell>
                    <TableCell>{p.expected_uplift_pct != null ? `${p.expected_uplift_pct}%` : '—'}</TableCell>
                    <TableCell>{p.budget != null ? `$${p.budget.toLocaleString()}` : '—'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Paper>
        )}
      </TabPanel>

      {/* Dashboard Tab */}
      <TabPanel value={tab} index={3}>
        {dashboard ? (
          <Grid container spacing={2}>
            <Grid item xs={3}>
              <Card><CardContent>
                <Typography color="text.secondary" gutterBottom>Total Promotions</Typography>
                <Typography variant="h4">{dashboard.total}</Typography>
              </CardContent></Card>
            </Grid>
            <Grid item xs={3}>
              <Card><CardContent>
                <Typography color="text.secondary" gutterBottom>Active Now</Typography>
                <Typography variant="h4" color="success.main">{dashboard.active_count}</Typography>
              </CardContent></Card>
            </Grid>
            <Grid item xs={3}>
              <Card><CardContent>
                <Typography color="text.secondary" gutterBottom>Upcoming (30d)</Typography>
                <Typography variant="h4" color="info.main">{dashboard.upcoming_count}</Typography>
              </CardContent></Card>
            </Grid>
            <Grid item xs={3}>
              <Card><CardContent>
                <Typography color="text.secondary" gutterBottom>Avg ROI (Completed)</Typography>
                <Typography variant="h4">{dashboard.avg_roi_completed != null ? `${dashboard.avg_roi_completed}%` : '—'}</Typography>
              </CardContent></Card>
            </Grid>
            <Grid item xs={6}>
              <Card><CardContent>
                <Typography variant="subtitle2" gutterBottom>By Status</Typography>
                {Object.entries(dashboard.by_status || {}).map(([k, v]) => (
                  <Box key={k} sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                    <Chip size="small" label={k} color={STATUS_COLORS[k]} />
                    <Typography>{v}</Typography>
                  </Box>
                ))}
              </CardContent></Card>
            </Grid>
            <Grid item xs={6}>
              <Card><CardContent>
                <Typography variant="subtitle2" gutterBottom>By Type</Typography>
                {Object.entries(dashboard.by_type || {}).map(([k, v]) => (
                  <Box key={k} sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                    <Chip size="small" label={k.replace(/_/g, ' ')} sx={{ bgcolor: TYPE_COLORS[k], color: 'white' }} />
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
        <DialogTitle>Create Promotion</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 0.5 }}>
            <Grid item xs={12}>
              <TextField fullWidth label="Name" value={form.name}
                onChange={e => setForm({ ...form, name: e.target.value })} />
            </Grid>
            <Grid item xs={6}>
              <FormControl fullWidth>
                <InputLabel>Type</InputLabel>
                <Select value={form.promotion_type} label="Type"
                  onChange={e => setForm({ ...form, promotion_type: e.target.value })}>
                  {PROMO_TYPES.map(t => <MenuItem key={t} value={t}>{t.replace(/_/g, ' ')}</MenuItem>)}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={6}>
              <TextField fullWidth label="Expected Uplift %" type="number"
                value={form.expected_uplift_pct}
                onChange={e => setForm({ ...form, expected_uplift_pct: e.target.value })} />
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
              <TextField fullWidth label="Budget" type="number" value={form.budget}
                onChange={e => setForm({ ...form, budget: e.target.value })} />
            </Grid>
            <Grid item xs={6}>
              <TextField fullWidth label="Product IDs (JSON)" value={form.product_ids}
                onChange={e => setForm({ ...form, product_ids: e.target.value })}
                placeholder='["PROD-001"]' />
            </Grid>
            <Grid item xs={6}>
              <TextField fullWidth label="Site IDs (JSON)" value={form.site_ids}
                onChange={e => setForm({ ...form, site_ids: e.target.value })}
                placeholder='[1, 2, 3]' />
            </Grid>
            <Grid item xs={6}>
              <TextField fullWidth label="Channels (JSON)" value={form.channel_ids}
                onChange={e => setForm({ ...form, channel_ids: e.target.value })}
                placeholder='["retail", "online"]' />
            </Grid>
            <Grid item xs={12}>
              <TextField fullWidth label="Description" multiline rows={2}
                value={form.description}
                onChange={e => setForm({ ...form, description: e.target.value })} />
            </Grid>
            <Grid item xs={12}>
              <TextField fullWidth label="Notes" multiline rows={2}
                value={form.notes}
                onChange={e => setForm({ ...form, notes: e.target.value })} />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleCreate}
            disabled={!form.name || !form.start_date || !form.end_date}>
            Create
          </Button>
        </DialogActions>
      </Dialog>

      {/* Detail Dialog */}
      <Dialog open={detailOpen} onClose={() => setDetailOpen(false)} maxWidth="md" fullWidth>
        {selectedPromo && (
          <>
            <DialogTitle>
              {selectedPromo.name}
              <Chip size="small" label={selectedPromo.status} color={STATUS_COLORS[selectedPromo.status]} sx={{ ml: 1 }} />
              <Chip size="small" label={selectedPromo.promotion_type.replace(/_/g, ' ')}
                sx={{ ml: 1, bgcolor: TYPE_COLORS[selectedPromo.promotion_type], color: 'white' }} />
            </DialogTitle>
            <DialogContent>
              <Grid container spacing={2}>
                <Grid item xs={6}><Typography variant="body2" color="text.secondary">Start Date</Typography><Typography>{selectedPromo.start_date}</Typography></Grid>
                <Grid item xs={6}><Typography variant="body2" color="text.secondary">End Date</Typography><Typography>{selectedPromo.end_date}</Typography></Grid>
                <Grid item xs={6}><Typography variant="body2" color="text.secondary">Expected Uplift</Typography><Typography>{selectedPromo.expected_uplift_pct != null ? `${selectedPromo.expected_uplift_pct}%` : '—'}</Typography></Grid>
                <Grid item xs={6}><Typography variant="body2" color="text.secondary">Actual Uplift</Typography><Typography>{selectedPromo.actual_uplift_pct != null ? `${selectedPromo.actual_uplift_pct}%` : '—'}</Typography></Grid>
                <Grid item xs={6}><Typography variant="body2" color="text.secondary">Budget</Typography><Typography>{selectedPromo.budget != null ? `$${selectedPromo.budget.toLocaleString()}` : '—'}</Typography></Grid>
                <Grid item xs={6}><Typography variant="body2" color="text.secondary">Actual Spend</Typography><Typography>{selectedPromo.actual_spend != null ? `$${selectedPromo.actual_spend.toLocaleString()}` : '—'}</Typography></Grid>
                <Grid item xs={6}><Typography variant="body2" color="text.secondary">Products</Typography><Typography>{JSON.stringify(selectedPromo.product_ids || [])}</Typography></Grid>
                <Grid item xs={6}><Typography variant="body2" color="text.secondary">Sites</Typography><Typography>{JSON.stringify(selectedPromo.site_ids || [])}</Typography></Grid>
                {selectedPromo.description && (
                  <Grid item xs={12}><Typography variant="body2" color="text.secondary">Description</Typography><Typography>{selectedPromo.description}</Typography></Grid>
                )}
                {selectedPromo.notes && (
                  <Grid item xs={12}><Typography variant="body2" color="text.secondary">Notes</Typography><Typography>{selectedPromo.notes}</Typography></Grid>
                )}
              </Grid>

              {history.length > 0 && (
                <Box sx={{ mt: 3 }}>
                  <Typography variant="subtitle2" gutterBottom>History</Typography>
                  <Table size="small">
                    <TableHead><TableRow>
                      <TableCell>Time</TableCell><TableCell>Action</TableCell><TableCell>Details</TableCell>
                    </TableRow></TableHead>
                    <TableBody>
                      {history.map(h => (
                        <TableRow key={h.id}>
                          <TableCell>{new Date(h.created_at).toLocaleString()}</TableCell>
                          <TableCell><Chip size="small" label={h.action} /></TableCell>
                          <TableCell>{h.changes ? JSON.stringify(h.changes).substring(0, 80) : '—'}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Box>
              )}
            </DialogContent>
            <DialogActions>
              {selectedPromo.status === 'draft' && (
                <Button color="primary" startIcon={<CheckCircle />}
                  onClick={() => handleAction(selectedPromo.id, 'approve')}>Approve</Button>
              )}
              {selectedPromo.status === 'approved' && (
                <Button color="success" onClick={() => handleAction(selectedPromo.id, 'activate')}>Activate</Button>
              )}
              {selectedPromo.status === 'active' && (
                <>
                  <Button color="success" onClick={() => handleAction(selectedPromo.id, 'complete')}>Complete</Button>
                  <Button color="error" onClick={() => handleAction(selectedPromo.id, 'cancel', { reason: '' })}>Cancel</Button>
                </>
              )}
              <Button onClick={() => setDetailOpen(false)}>Close</Button>
            </DialogActions>
          </>
        )}
      </Dialog>
    </Box>
  );
}
