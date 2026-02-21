/**
 * CSV Downloads
 *
 * Lists completed deployment pipeline runs and their generated SAP CSV files.
 * Provides download buttons for Day 1 and Day 2 ZIP archives.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Paper,
  Typography,
  Card,
  CardContent,
  Grid,
  Button,
  Chip,
  CircularProgress,
  Alert,
  Divider,
  Table,
  TableBody,
  TableCell,
  TableRow,
} from '@mui/material';
import {
  Download as DownloadIcon,
  Folder as FolderIcon,
  CheckCircle as CheckIcon,
  Refresh as RefreshIcon,
} from '@mui/icons-material';
import { api } from '../../services/api';

const SAP_TABLES = [
  // Core S/4HANA tables (19 export)
  { name: 'MARA', desc: 'Material Master' },
  { name: 'MARC', desc: 'Plant Data for Material' },
  { name: 'MARD', desc: 'Storage Location Data' },
  { name: 'T001W', desc: 'Plants/Branches' },
  { name: 'LFA1', desc: 'Vendor Master' },
  { name: 'KNA1', desc: 'Customer Master' },
  { name: 'STPO', desc: 'BOM Items' },
  { name: 'EKKO', desc: 'Purchase Order Headers' },
  { name: 'EKPO', desc: 'Purchase Order Items' },
  { name: 'VBAK', desc: 'Sales Order Headers' },
  { name: 'VBAP', desc: 'Sales Order Items' },
  { name: 'LIKP', desc: 'Delivery Headers' },
  { name: 'LIPS', desc: 'Delivery Items' },
  { name: 'AFKO', desc: 'Production Order Headers' },
  { name: 'AFPO', desc: 'Production Order Items' },
  { name: 'EKET', desc: 'Schedule Lines' },
  { name: 'RESB', desc: 'Reservations' },
  // Config Builder S/4HANA tables (13 import)
  { name: 'EINA', desc: 'Purchasing Info Record Header' },
  { name: 'EINE', desc: 'Purchasing Info Record Item' },
  { name: 'EORD', desc: 'Source List' },
  { name: 'T001', desc: 'Company Codes' },
  { name: 'ADRC', desc: 'Central Addresses' },
  { name: 'KNVV', desc: 'Customer Sales Data' },
  { name: 'MVKE', desc: 'Sales Data for Material' },
  { name: 'PLKO', desc: 'Routing Header' },
  { name: 'PLPO', desc: 'Routing Operation' },
  { name: 'STKO', desc: 'BOM Header' },
  { name: 'CRHD', desc: 'Work Center Header' },
  { name: 'KAKO', desc: 'Capacity Header' },
  { name: 'MARM', desc: 'Material UOM Conversions' },
  // APO tables (9 total)
  { name: '/SAPAPO/LOC', desc: 'APO Locations' },
  { name: '/SAPAPO/SNPFC', desc: 'APO Forecast' },
  { name: '/SAPAPO/MATLOC', desc: 'APO Material-Location' },
  { name: '/SAPAPO/TRLANE', desc: 'APO Transportation Lanes' },
  { name: '/SAPAPO/PDS', desc: 'APO Product Data Structure' },
  { name: '/SAPAPO/SNPBV', desc: 'APO SNP Basic Values' },
];

function PipelineCSVCard({ pipeline }) {
  const [csvs, setCsvs] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchCSVs = async () => {
      try {
        const res = await api.get(`/v1/deployment/csvs/${pipeline.id}`);
        setCsvs(res.data.csvs || []);
      } catch (err) {
        setError(err.response?.data?.detail || 'Failed to load CSV info');
      }
      setLoading(false);
    };
    fetchCSVs();
  }, [pipeline.id]);

  const handleDownload = async (csvType) => {
    try {
      const res = await api.get(`/v1/deployment/csvs/${pipeline.id}/${csvType}`, {
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `${csvType}_sap_csvs_pipeline_${pipeline.id}.zip`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err) {
      console.error('Download failed:', err);
    }
  };

  const created = pipeline.created_at
    ? new Date(pipeline.created_at).toLocaleString()
    : 'Unknown';

  return (
    <Card variant="outlined" sx={{ mb: 2 }}>
      <CardContent>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Box>
            <Typography variant="subtitle1">
              Pipeline #{pipeline.id} — {pipeline.config_template}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Created: {created}
            </Typography>
          </Box>
          <Chip label="Completed" size="small" color="success" icon={<CheckIcon />} />
        </Box>

        {loading ? (
          <CircularProgress size={24} />
        ) : error ? (
          <Alert severity="error" variant="outlined">{error}</Alert>
        ) : csvs && csvs.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No CSV files generated for this pipeline.
          </Typography>
        ) : (
          <Grid container spacing={2}>
            {(csvs || []).map((csv) => (
              <Grid item xs={12} sm={6} key={csv.type}>
                <Card
                  variant="outlined"
                  sx={{
                    bgcolor: csv.exists ? 'background.paper' : 'action.disabledBackground'
                  }}
                >
                  <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                      <FolderIcon color={csv.exists ? 'primary' : 'disabled'} />
                      <Typography variant="subtitle2">
                        {csv.type === 'day1' ? 'Day 1 — Full Export' : 'Day 2 — Delta Export'}
                      </Typography>
                    </Box>
                    <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
                      {csv.filename}
                      {csv.profile && ` (Profile: ${csv.profile})`}
                    </Typography>
                    <Button
                      variant="contained"
                      size="small"
                      startIcon={<DownloadIcon />}
                      onClick={() => handleDownload(csv.type)}
                      disabled={!csv.exists}
                      fullWidth
                    >
                      Download
                    </Button>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        )}
      </CardContent>
    </Card>
  );
}

export default function CSVDownloads() {
  const [pipelines, setPipelines] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchCompleted = useCallback(async () => {
    try {
      const res = await api.get('/v1/deployment/pipelines', {
        params: { status: 'completed', limit: 50 }
      });
      setPipelines(res.data.pipelines || []);
      setError(null);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load pipelines');
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchCompleted();
  }, [fetchCompleted]);

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Box>
          <Typography variant="h5">SAP CSV Exports</Typography>
          <Typography variant="body2" color="text.secondary">
            Download generated SAP-format CSV files from completed pipelines
          </Typography>
        </Box>
        <Button
          variant="outlined"
          startIcon={<RefreshIcon />}
          onClick={fetchCompleted}
          size="small"
        >
          Refresh
        </Button>
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
          <Typography color="text.secondary" sx={{ mb: 1 }}>
            No completed pipelines found.
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Run a pipeline from the Demo System Builder to generate SAP CSV files.
          </Typography>
        </Paper>
      ) : (
        pipelines.map((p) => (
          <PipelineCSVCard key={p.id} pipeline={p} />
        ))
      )}

      <Divider sx={{ my: 3 }} />

      <Typography variant="subtitle2" gutterBottom>
        SAP Tables Reference (36 tables)
      </Typography>
      <Paper variant="outlined">
        <Table size="small">
          <TableBody>
            {SAP_TABLES.map((t) => (
              <TableRow key={t.name}>
                <TableCell sx={{ fontWeight: 600, fontFamily: 'monospace', width: 160 }}>
                  {t.name}
                </TableCell>
                <TableCell>{t.desc}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>
    </Box>
  );
}
