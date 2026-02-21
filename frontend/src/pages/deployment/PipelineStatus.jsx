/**
 * Pipeline Status
 *
 * Table of all deployment pipeline runs with expandable step details.
 * Supports status filtering and auto-refresh for running pipelines.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Paper,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  IconButton,
  Collapse,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Button,
  CircularProgress,
  LinearProgress,
  Alert,
  Card,
  CardContent,
  Tooltip,
} from '@mui/material';
import {
  KeyboardArrowDown as ExpandIcon,
  KeyboardArrowUp as CollapseIcon,
  Refresh as RefreshIcon,
  CheckCircle as CheckIcon,
  Error as ErrorIcon,
  Schedule as PendingIcon,
  Cancel as CancelIcon,
} from '@mui/icons-material';
import { api } from '../../services/api';

const STATUS_COLORS = {
  pending: 'default',
  running: 'primary',
  completed: 'success',
  failed: 'error',
  cancelled: 'warning',
};

const STEP_NAMES = {
  1: 'Seed Config',
  2: 'Deterministic Simulation',
  3: 'Stochastic Monte Carlo',
  4: 'Convert Training Data',
  5: 'Train Models',
  6: 'Generate Day 1 CSVs',
  7: 'Generate Day 2 CSVs',
};

function PipelineRow({ pipeline, onRefresh }) {
  const [open, setOpen] = useState(false);
  const [cancelling, setCancelling] = useState(false);

  const handleCancel = async () => {
    setCancelling(true);
    try {
      await api.post(`/v1/deployment/pipelines/${pipeline.id}/cancel`);
      onRefresh();
    } catch (err) {
      console.error('Cancel failed:', err);
    }
    setCancelling(false);
  };

  const progress = pipeline.total_steps > 0
    ? (pipeline.current_step / pipeline.total_steps) * 100
    : 0;

  return (
    <>
      <TableRow hover sx={{ '& > *': { borderBottom: 'unset' } }}>
        <TableCell padding="checkbox">
          <IconButton size="small" onClick={() => setOpen(!open)}>
            {open ? <CollapseIcon /> : <ExpandIcon />}
          </IconButton>
        </TableCell>
        <TableCell>{pipeline.id}</TableCell>
        <TableCell>{pipeline.config_template}</TableCell>
        <TableCell>
          <Chip
            label={pipeline.status}
            size="small"
            color={STATUS_COLORS[pipeline.status] || 'default'}
          />
        </TableCell>
        <TableCell>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <LinearProgress
              variant="determinate"
              value={progress}
              sx={{ flex: 1, height: 6, borderRadius: 3 }}
            />
            <Typography variant="caption" sx={{ minWidth: 40 }}>
              {pipeline.current_step}/{pipeline.total_steps}
            </Typography>
          </Box>
        </TableCell>
        <TableCell>
          {pipeline.created_at
            ? new Date(pipeline.created_at).toLocaleString()
            : '-'}
        </TableCell>
        <TableCell>
          {pipeline.status === 'running' && (
            <Tooltip title="Cancel pipeline">
              <IconButton
                size="small"
                color="error"
                onClick={handleCancel}
                disabled={cancelling}
              >
                {cancelling ? <CircularProgress size={18} /> : <CancelIcon />}
              </IconButton>
            </Tooltip>
          )}
        </TableCell>
      </TableRow>
      <TableRow>
        <TableCell style={{ paddingBottom: 0, paddingTop: 0 }} colSpan={7}>
          <Collapse in={open} timeout="auto" unmountOnExit>
            <Box sx={{ py: 2, px: 1 }}>
              {pipeline.error_message && (
                <Alert severity="error" sx={{ mb: 2 }}>
                  {pipeline.error_message}
                  {pipeline.error_step && ` (Step ${pipeline.error_step})`}
                </Alert>
              )}
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                {Object.entries(STEP_NAMES).map(([num, name]) => {
                  const stepInfo = (pipeline.step_statuses || {})[num] || {};
                  const stepStatus = stepInfo.status || 'pending';
                  const isActive = parseInt(num) === pipeline.current_step && pipeline.status === 'running';

                  return (
                    <Box
                      key={num}
                      sx={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 1,
                        py: 0.5,
                        px: 1,
                        borderRadius: 1,
                        bgcolor: isActive ? 'action.selected' : undefined,
                      }}
                    >
                      {stepStatus === 'completed' ? (
                        <CheckIcon fontSize="small" color="success" />
                      ) : stepStatus === 'failed' ? (
                        <ErrorIcon fontSize="small" color="error" />
                      ) : isActive ? (
                        <CircularProgress size={16} />
                      ) : (
                        <PendingIcon fontSize="small" color="disabled" />
                      )}
                      <Typography variant="body2" sx={{ flex: 1 }}>
                        {num}. {name}
                      </Typography>
                      {stepInfo.elapsed && (
                        <Typography variant="caption" color="text.secondary">
                          {stepInfo.elapsed.toFixed(1)}s
                        </Typography>
                      )}
                    </Box>
                  );
                })}
              </Box>
              {pipeline.parameters && Object.keys(pipeline.parameters).length > 0 && (
                <Card variant="outlined" sx={{ mt: 2 }}>
                  <CardContent sx={{ py: 1, '&:last-child': { pb: 1 } }}>
                    <Typography variant="caption" color="text.secondary">
                      Parameters: periods={pipeline.parameters.periods},
                      MC runs={pipeline.parameters.monte_carlo_runs},
                      epochs={pipeline.parameters.epochs},
                      device={pipeline.parameters.device},
                      seed={pipeline.parameters.seed}
                    </Typography>
                  </CardContent>
                </Card>
              )}
            </Box>
          </Collapse>
        </TableCell>
      </TableRow>
    </>
  );
}

export default function PipelineStatus() {
  const [pipelines, setPipelines] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('');
  const [error, setError] = useState(null);

  const fetchPipelines = useCallback(async () => {
    try {
      const params = { limit: 50, offset: 0 };
      if (statusFilter) params.status = statusFilter;
      const res = await api.get('/v1/deployment/pipelines', { params });
      setPipelines(res.data.pipelines || []);
      setTotal(res.data.total || 0);
      setError(null);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load pipelines');
    }
    setLoading(false);
  }, [statusFilter]);

  useEffect(() => {
    fetchPipelines();
    // Auto-refresh every 5s if any pipeline is running
    const interval = setInterval(() => {
      fetchPipelines();
    }, 5000);
    return () => clearInterval(interval);
  }, [fetchPipelines]);

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Box>
          <Typography variant="h5">Pipeline Status</Typography>
          <Typography variant="body2" color="text.secondary">
            Monitor deployment pipeline runs ({total} total)
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
          <FormControl size="small" sx={{ minWidth: 150 }}>
            <InputLabel>Status Filter</InputLabel>
            <Select
              value={statusFilter}
              label="Status Filter"
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <MenuItem value="">All</MenuItem>
              <MenuItem value="pending">Pending</MenuItem>
              <MenuItem value="running">Running</MenuItem>
              <MenuItem value="completed">Completed</MenuItem>
              <MenuItem value="failed">Failed</MenuItem>
              <MenuItem value="cancelled">Cancelled</MenuItem>
            </Select>
          </FormControl>
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={fetchPipelines}
            size="small"
          >
            Refresh
          </Button>
        </Box>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>
      )}

      {loading ? (
        <Box sx={{ textAlign: 'center', py: 4 }}>
          <CircularProgress />
        </Box>
      ) : pipelines.length === 0 ? (
        <Paper sx={{ p: 4, textAlign: 'center' }}>
          <Typography color="text.secondary">
            No pipeline runs found. Start a new pipeline from the Demo System Builder.
          </Typography>
        </Paper>
      ) : (
        <TableContainer component={Paper}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell padding="checkbox" />
                <TableCell>ID</TableCell>
                <TableCell>Config Template</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Progress</TableCell>
                <TableCell>Created</TableCell>
                <TableCell>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {pipelines.map((p) => (
                <PipelineRow key={p.id} pipeline={p} onRefresh={fetchPipelines} />
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Box>
  );
}
