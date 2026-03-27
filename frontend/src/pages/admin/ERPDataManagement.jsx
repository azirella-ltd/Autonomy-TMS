import React, { useState, useEffect } from 'react';
import {
  Box, Typography, Paper, Grid, Tabs, Tab,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Chip, Button, Alert, CircularProgress, Card, CardContent,
  Accordion, AccordionSummary, AccordionDetails,
  LinearProgress, Tooltip, IconButton
} from '@mui/material';
import {
  CloudSync as SyncIcon,
  Storage as StorageIcon,
  CheckCircle as CheckIcon,
  Warning as WarningIcon,
  ExpandMore as ExpandMoreIcon,
  PlayArrow as PlayIcon,
  Download as DownloadIcon,
  Info as InfoIcon,
} from '@mui/icons-material';
import api from '../../services/api';

const ERP_CONFIGS = {
  sap: {
    name: 'SAP S/4HANA / ECC',
    color: '#0070C0',
    icon: '🏭',
    sandbox: 'SAP FAA (IDES) — $1-3/hr compute via cal.sap.com',
    status: 'production',
    methods: ['RFC', 'OData', 'CSV', 'HANA DB', 'IDoc'],
  },
  odoo: {
    name: 'Odoo Community / Enterprise',
    color: '#714B67',
    icon: '🟣',
    sandbox: 'Docker self-hosted — Free ($0)',
    status: 'production',
    methods: ['JSON-RPC', 'XML-RPC', 'CSV'],
  },
  d365: {
    name: 'Microsoft Dynamics 365 F&O',
    color: '#0078D4',
    icon: '🔷',
    sandbox: 'Contoso demo (30-day trial) — Free ($0)',
    status: 'production',
    methods: ['OData v4', 'DMF', 'CSV'],
  },
  sap_b1: {
    name: 'SAP Business One',
    color: '#0070C0',
    icon: '🔶',
    sandbox: 'OEC Computers demo — Free (14-day via Cloudiax)',
    status: 'production',
    methods: ['Service Layer (OData v4)', 'CSV'],
  },
  netsuite: {
    name: 'Oracle NetSuite',
    color: '#1B3A5C',
    icon: '☁️',
    sandbox: 'SDN Developer — $3K-$10K/yr',
    status: 'planned',
    methods: ['REST', 'SuiteQL', 'CSV'],
  },
  epicor: {
    name: 'Epicor Kinetic',
    color: '#E4002B',
    icon: '⚙️',
    sandbox: 'Partner-only',
    status: 'planned',
    methods: ['REST v2', 'OData', 'CSV'],
  },
};

function TabPanel({ children, value, index, ...other }) {
  return (
    <div role="tabpanel" hidden={value !== index} {...other}>
      {value === index && <Box sx={{ pt: 2 }}>{children}</Box>}
    </div>
  );
}

export default function ERPDataManagement() {
  const [tab, setTab] = useState(0);
  const [supportedErps, setSupportedErps] = useState([]);
  const [odooModels, setOdooModels] = useState(null);
  const [d365Entities, setD365Entities] = useState(null);
  const [b1Entities, setB1Entities] = useState(null);
  const [odooPlan, setOdooPlan] = useState(null);
  const [d365Plan, setD365Plan] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [erps, odooM, d365E, b1E, odooP, d365P] = await Promise.all([
          api.get('/erp/supported-erps').catch(() => ({ data: { erps: [] } })),
          api.get('/erp/odoo/models').catch(() => ({ data: null })),
          api.get('/erp/d365/entities').catch(() => ({ data: null })),
          api.get('/erp/b1/entities').catch(() => ({ data: null })),
          api.get('/erp/odoo/extraction-plan').catch(() => ({ data: null })),
          api.get('/erp/d365/extraction-plan').catch(() => ({ data: null })),
        ]);
        setSupportedErps(erps.data?.erps || []);
        setOdooModels(odooM.data);
        setD365Entities(d365E.data);
        setB1Entities(b1E.data);
        setOdooPlan(odooP.data);
        setD365Plan(d365P.data);
      } catch (err) {
        console.error('Failed to load ERP data:', err);
      }
      setLoading(false);
    };
    fetchData();
  }, []);

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <SyncIcon /> ERP Data Management
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Manage connections to external ERP systems. Extract master data, transaction data,
        and change data — mapped to the AWS Supply Chain data model.
      </Typography>

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="Supported ERPs" />
        <Tab label="Odoo Integration" />
        <Tab label="D365 Integration" />
        <Tab label="SAP S/4HANA" />
        <Tab label="SAP Business One" />
        <Tab label="Field Mapping" />
      </Tabs>

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
          <CircularProgress />
        </Box>
      ) : (
        <>
          {/* Tab 0: Supported ERPs */}
          <TabPanel value={tab} index={0}>
            <Grid container spacing={2}>
              {Object.entries(ERP_CONFIGS).map(([key, cfg]) => (
                <Grid item xs={12} md={6} lg={4} key={key}>
                  <Card
                    variant="outlined"
                    sx={{
                      borderColor: cfg.status === 'production' ? cfg.color : '#ccc',
                      borderWidth: cfg.status === 'production' ? 2 : 1,
                      opacity: cfg.status === 'planned' ? 0.7 : 1,
                    }}
                  >
                    <CardContent>
                      <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <span>{cfg.icon}</span>
                        {cfg.name}
                        <Chip
                          label={cfg.status}
                          size="small"
                          color={cfg.status === 'production' ? 'success' : 'default'}
                          sx={{ ml: 'auto' }}
                        />
                      </Typography>
                      <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                        <strong>Sandbox:</strong> {cfg.sandbox}
                      </Typography>
                      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                        <strong>Methods:</strong> {cfg.methods.join(', ')}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>

            <Alert severity="info" sx={{ mt: 3 }}>
              <strong>Integration Architecture:</strong> All ERPs follow the same 3-phase extraction pipeline
              (Master Data → CDC → Transaction) with data mapped to the AWS Supply Chain data model.
              The field mapping service uses exact → pattern → fuzzy → AI matching tiers.
            </Alert>
          </TabPanel>

          {/* Tab 1: Odoo Integration */}
          <TabPanel value={tab} index={1}>
            <Alert severity="success" sx={{ mb: 2 }}>
              <strong>Odoo</strong> is fully supported via JSON-RPC. Self-host with Docker for $0 development cost.
              {odooModels && ` ${odooModels.total_models} supply chain models mapped.`}
            </Alert>

            {odooPlan && (
              <Grid container spacing={2} sx={{ mb: 3 }}>
                <Grid item xs={6}>
                  <Paper sx={{ p: 2 }}>
                    <Typography variant="subtitle2">Master Data Models</Typography>
                    <Typography variant="h4">{odooPlan.master_data?.models?.length || 0}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      {odooPlan.master_data?.total_fields || 0} fields
                    </Typography>
                  </Paper>
                </Grid>
                <Grid item xs={6}>
                  <Paper sx={{ p: 2 }}>
                    <Typography variant="subtitle2">Transaction Models</Typography>
                    <Typography variant="h4">{odooPlan.transaction?.models?.length || 0}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      {odooPlan.transaction?.total_fields || 0} fields
                    </Typography>
                  </Paper>
                </Grid>
              </Grid>
            )}

            {odooModels && (
              <TableContainer component={Paper}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Odoo Model</TableCell>
                      <TableCell align="right">Mapped Fields</TableCell>
                      <TableCell>Sample Fields</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {odooModels.models?.map((m) => (
                      <TableRow key={m.model} hover>
                        <TableCell>
                          <code style={{ fontSize: '0.85em' }}>{m.model}</code>
                        </TableCell>
                        <TableCell align="right">
                          <Chip label={m.mapped_fields} size="small" color="primary" />
                        </TableCell>
                        <TableCell>
                          <Typography variant="caption" color="text.secondary">
                            {m.fields?.slice(0, 5).join(', ')}{m.fields?.length > 5 ? '...' : ''}
                          </Typography>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </TabPanel>

          {/* Tab 2: D365 Integration */}
          <TabPanel value={tab} index={2}>
            <Alert severity="success" sx={{ mb: 2 }}>
              <strong>Dynamics 365 F&O</strong> is fully supported via OData v4 + Azure AD OAuth.
              30-day free trial with Contoso demo data (USMF).
              {d365Entities && ` ${d365Entities.total_entities} supply chain entities mapped.`}
            </Alert>

            {d365Plan && (
              <Grid container spacing={2} sx={{ mb: 3 }}>
                <Grid item xs={6}>
                  <Paper sx={{ p: 2 }}>
                    <Typography variant="subtitle2">Master Data Entities</Typography>
                    <Typography variant="h4">{d365Plan.master_data?.entities?.length || 0}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      {d365Plan.master_data?.total_fields || 0} fields
                    </Typography>
                  </Paper>
                </Grid>
                <Grid item xs={6}>
                  <Paper sx={{ p: 2 }}>
                    <Typography variant="subtitle2">Transaction Entities</Typography>
                    <Typography variant="h4">{d365Plan.transaction?.entities?.length || 0}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      {d365Plan.transaction?.total_fields || 0} fields
                    </Typography>
                  </Paper>
                </Grid>
              </Grid>
            )}

            {d365Entities && (
              <TableContainer component={Paper}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>D365 Entity</TableCell>
                      <TableCell align="right">Select Fields</TableCell>
                      <TableCell>Sample Fields</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {d365Entities.entities?.map((e) => (
                      <TableRow key={e.entity} hover>
                        <TableCell>
                          <code style={{ fontSize: '0.85em' }}>{e.entity}</code>
                        </TableCell>
                        <TableCell align="right">
                          <Chip label={e.select_fields} size="small" color="primary" />
                        </TableCell>
                        <TableCell>
                          <Typography variant="caption" color="text.secondary">
                            {e.fields?.slice(0, 5).join(', ')}{e.fields?.length > 5 ? '...' : ''}
                          </Typography>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </TabPanel>

          {/* Tab 3: SAP Integration */}
          <TabPanel value={tab} index={3}>
            <Alert severity="info" sx={{ mb: 2 }}>
              SAP integration is managed via the dedicated{' '}
              <a href="/admin/sap-data" style={{ color: 'inherit', fontWeight: 'bold' }}>
                SAP Data Management
              </a>{' '}
              page. It supports RFC, OData, CSV, HANA DB, and IDoc connections.
            </Alert>
            <Button variant="outlined" href="/admin/sap-data">
              Go to SAP Data Management
            </Button>
          </TabPanel>

          {/* Tab 4: SAP Business One */}
          <TabPanel value={tab} index={4}>
            <Typography variant="h6" gutterBottom>SAP Business One — Service Layer Integration</Typography>
            <Alert severity="info" sx={{ mb: 2 }}>
              Connects via the B1 Service Layer REST API (OData v4). Supports session-based
              authentication, automatic pagination, and CSV fallback for offline extraction.
            </Alert>

            {b1Entities ? (
              <>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>
                  {b1Entities.total_entities} entities registered across master, transaction, and CDC categories
                </Typography>
                <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 500 }}>
                  <Table size="small" stickyHeader>
                    <TableHead>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 'bold' }}>Entity</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }}>DB Table</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }}>Category</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }}>Keys</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }}>Description</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }} align="right">Mapped Fields</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {b1Entities.entities?.map((e) => (
                        <TableRow key={e.entity} hover>
                          <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>{e.entity}</TableCell>
                          <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.8rem', color: 'text.secondary' }}>{e.db_table}</TableCell>
                          <TableCell>
                            <Chip
                              label={e.category}
                              size="small"
                              color={e.category === 'master' ? 'primary' : e.category === 'transaction' ? 'warning' : 'error'}
                              variant="outlined"
                            />
                          </TableCell>
                          <TableCell sx={{ fontSize: '0.8rem' }}>{e.keys?.join(', ')}</TableCell>
                          <TableCell sx={{ fontSize: '0.85rem' }}>{e.description}</TableCell>
                          <TableCell align="right">
                            {e.mapped_fields > 0 ? (
                              <Chip label={e.mapped_fields} size="small" color="success" />
                            ) : (
                              <Chip label="0" size="small" variant="outlined" />
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>

                <Grid container spacing={2} sx={{ mt: 2 }}>
                  <Grid item xs={12} md={4}>
                    <Card variant="outlined">
                      <CardContent>
                        <Typography variant="subtitle2">Connection</Typography>
                        <Typography variant="body2" color="text.secondary">
                          Service Layer URL: https://&lt;server&gt;:50000/b1s/v2
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Auth: Session-based (POST /Login)
                        </Typography>
                      </CardContent>
                    </Card>
                  </Grid>
                  <Grid item xs={12} md={4}>
                    <Card variant="outlined">
                      <CardContent>
                        <Typography variant="subtitle2">Demo Data</Typography>
                        <Typography variant="body2" color="text.secondary">
                          OEC Computers (SBODemoUS)
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          ~4,000 items, ~500 BPs, ~30 BOMs
                        </Typography>
                      </CardContent>
                    </Card>
                  </Grid>
                  <Grid item xs={12} md={4}>
                    <Card variant="outlined">
                      <CardContent>
                        <Typography variant="subtitle2">Sandbox</Typography>
                        <Typography variant="body2" color="text.secondary">
                          Cloudiax: 14-day free trial on HANA
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Partner: OEC Computers demo DB download
                        </Typography>
                      </CardContent>
                    </Card>
                  </Grid>
                </Grid>
              </>
            ) : (
              <Alert severity="warning">B1 entity registry not loaded. Backend may need rebuild.</Alert>
            )}
          </TabPanel>

          {/* Tab 5: Field Mapping */}
          <TabPanel value={tab} index={5}>
            <Typography variant="body2" gutterBottom>
              All ERP integrations use the same 3-tier field mapping strategy:
            </Typography>
            <Grid container spacing={2} sx={{ mt: 1 }}>
              {[
                { tier: 'Tier 1: Exact', desc: 'Table-specific field → AWS SC entity mapping. Highest confidence (100%).', color: '#4caf50' },
                { tier: 'Tier 2: Pattern', desc: 'Regex patterns for common naming conventions (e.g. *_qty → quantity). Confidence 75%.', color: '#ff9800' },
                { tier: 'Tier 3: Fuzzy / AI', desc: 'String similarity + Claude AI for ambiguous or custom fields. Confidence varies.', color: '#f44336' },
              ].map((t) => (
                <Grid item xs={12} md={4} key={t.tier}>
                  <Paper sx={{ p: 2, borderLeft: `4px solid ${t.color}` }}>
                    <Typography variant="subtitle2">{t.tier}</Typography>
                    <Typography variant="body2" color="text.secondary">{t.desc}</Typography>
                  </Paper>
                </Grid>
              ))}
            </Grid>

            <Alert severity="info" sx={{ mt: 3 }}>
              All mappings target the <strong>AWS Supply Chain data model</strong> (35 entities).
              This ensures data model consistency regardless of source ERP system.
            </Alert>
          </TabPanel>
        </>
      )}
    </Box>
  );
}
