import React, { useState, useEffect, useCallback } from 'react';
import { cn } from '@azirella-ltd/autonomy-frontend';
import {
  Server, Database, Zap, Users, Activity, ChevronDown, ChevronRight,
  CheckCircle, Clock, Lock, Play, AlertTriangle, Upload, RefreshCw, Trash2,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, Button, Alert, AlertDescription, Badge } from '../../components/common';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '../../components/common/Dialog';
import { api } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';
import SAPDataManagement from './SAPDataManagement';

// ---------------------------------------------------------------------------
// Vendor → connection-form schema (which fields the modal asks for)
// ---------------------------------------------------------------------------
const CONNECTION_FORM_SCHEMA = {
  sap_tm: {
    method: 'odata',
    fields: [
      { key: 'base_url', label: 'OData base URL', type: 'url', required: true },
      { key: 'auth_credentials.username', label: 'Username', type: 'text' },
      { key: 'auth_credentials.password', label: 'Password', type: 'password' },
      { key: 'connection_params.client', label: 'SAP client', type: 'text', placeholder: '100' },
      { key: 'connection_params.preferred_method', label: 'Method', type: 'select',
        options: [{ value: 'odata', label: 'OData (S/4HANA Cloud)' }, { value: 'rfc', label: 'RFC (on-prem)' }] },
    ],
  },
  oracle_otm: {
    method: 'rest_api',
    fields: [
      { key: 'base_url', label: 'OTM base URL', type: 'url', required: true,
        placeholder: 'https://otmgtm.oracle.com' },
      { key: 'auth_credentials.user', label: 'Domain-qualified user', type: 'text',
        placeholder: 'DEFAULT/admin' },
      { key: 'auth_credentials.password', label: 'Password', type: 'password' },
      { key: 'connection_params.domain', label: 'OTM domain', type: 'text', placeholder: 'DEFAULT' },
    ],
  },
  blue_yonder: {
    method: 'rest_api',
    fields: [
      { key: 'base_url', label: 'Luminate TMS base URL', type: 'url', required: true,
        placeholder: 'https://luminate.blueyonder.com' },
      { key: 'auth_credentials.client_id', label: 'OAuth2 Client ID', type: 'text', required: true },
      { key: 'auth_credentials.client_secret', label: 'OAuth2 Client Secret', type: 'password', required: true },
      { key: 'connection_params.tenant_code', label: 'Tenant code', type: 'text' },
    ],
  },
  odoo: {
    method: 'json_rpc',
    fields: [
      { key: 'base_url', label: 'Odoo URL', type: 'url', required: true,
        placeholder: 'http://localhost:8069' },
      { key: 'connection_params.database', label: 'Database', type: 'text', required: true },
      { key: 'auth_credentials.username', label: 'Username', type: 'text', required: true },
      { key: 'auth_credentials.password', label: 'Password / API key', type: 'password', required: true },
    ],
  },
  d365: {
    method: 'odata',
    fields: [
      { key: 'base_url', label: 'D365 environment URL', type: 'url', required: true },
      { key: 'auth_credentials.client_id', label: 'Azure AD client ID', type: 'text', required: true },
      { key: 'auth_credentials.client_secret', label: 'Azure AD client secret', type: 'password', required: true },
      { key: 'connection_params.tenant_id_azure', label: 'Azure AD tenant ID', type: 'text', required: true },
      { key: 'connection_params.legal_entity', label: 'Legal entity', type: 'text', placeholder: 'USMF' },
    ],
  },
  sap_b1: {
    method: 'odata',
    fields: [
      { key: 'base_url', label: 'B1 Service Layer URL', type: 'url', required: true },
      { key: 'auth_credentials.username', label: 'Username', type: 'text', required: true },
      { key: 'auth_credentials.password', label: 'Password', type: 'password', required: true },
      { key: 'connection_params.company_db', label: 'Company database', type: 'text', required: true },
    ],
  },
};

// ---------------------------------------------------------------------------
// ERP type definitions
// ---------------------------------------------------------------------------

// kind: 'erp' = full ERP (master + transactional SCP data)
//       'tms' = dedicated TMS system (shipments, loads, carriers, rates)
const ERP_TYPES = [
  // Full ERPs
  { key: 'sap', label: 'SAP S/4HANA', color: '#0070C0', status: 'production', kind: 'erp' },
  { key: 'odoo', label: 'Odoo', color: '#714B67', status: 'production', kind: 'erp' },
  { key: 'd365', label: 'Dynamics 365', color: '#0078D4', status: 'production', kind: 'erp' },
  { key: 'sap_b1', label: 'SAP Business One', color: '#F0AB00', status: 'production', kind: 'erp' },
  { key: 'netsuite', label: 'NetSuite', color: '#1B3A5C', status: 'planned', kind: 'erp' },
  { key: 'epicor', label: 'Epicor', color: '#E4002B', status: 'planned', kind: 'erp' },
  // Dedicated TMS systems
  { key: 'sap_tm', label: 'SAP TM', color: '#0070C0', status: 'production', kind: 'tms' },
  { key: 'oracle_otm', label: 'Oracle OTM', color: '#C74634', status: 'production', kind: 'tms' },
  { key: 'blue_yonder', label: 'Blue Yonder TMS', color: '#F0A202', status: 'production', kind: 'tms' },
];

const ERP_PIPELINE_STEPS = {
  odoo: [
    { key: 'connect', label: 'Connect', description: 'Configure Odoo JSON-RPC connection', icon: Server, detail: 'Set up a connection to your Odoo instance via JSON-RPC or XML-RPC. Provide the server URL, database name, username, and API key.' },
    { key: 'master_data', label: 'Master Data', description: 'Import products, warehouses, BOMs, and partners', icon: Database, detail: 'Extract res.partner, product.product, stock.warehouse, mrp.bom and other master data models. Creates sites, products, trading partners, and inventory levels.' },
    { key: 'user_import', label: 'User Import', description: 'Provision SC-relevant users', icon: Users, detail: 'Map Odoo user roles to Autonomy decision levels. Import warehouse managers, procurement officers, and planners.' },
    { key: 'transaction_data', label: 'Transaction Data', description: 'Import orders, shipments, and operations', icon: Activity, detail: 'Extract sale.order, purchase.order, mrp.production, stock.picking and other transaction models. Builds demand history and supply chain activity.' },
    { key: 'warm_start', label: 'Warm Start', description: 'Provision AI models and generate plans', icon: Zap, detail: 'Run the 16-step provisioning pipeline: warm start simulation, agent training, supply plan generation, decision seeding, and conformal calibration.' },
  ],
  d365: [
    { key: 'connect', label: 'Connect', description: 'Configure D365 OData connection', icon: Server, detail: 'Set up OAuth2 client credentials for D365 F&O. Provide the Azure AD tenant ID, client ID, client secret, and environment URL.' },
    { key: 'master_data', label: 'Master Data', description: 'Import items, warehouses, vendors, and BOMs', icon: Database, detail: 'Extract ReleasedProducts, Warehouses, Vendors, BillOfMaterialHeaders, and other master entities via OData v4. Creates the supply chain topology.' },
    { key: 'user_import', label: 'User Import', description: 'Provision SC-relevant users', icon: Users, detail: 'Map D365 security roles to Autonomy decision levels. Import users from SystemUsers entity filtered by SC-relevant roles.' },
    { key: 'transaction_data', label: 'Transaction Data', description: 'Import orders, receipts, and production', icon: Activity, detail: 'Extract SalesOrderHeaders, PurchaseOrderHeaders, ProductionOrders, and transfer orders. Builds operational history for agent training.' },
    { key: 'warm_start', label: 'Warm Start', description: 'Provision AI models and generate plans', icon: Zap, detail: 'Run the 16-step provisioning pipeline: warm start simulation, agent training, supply plan generation, decision seeding, and conformal calibration.' },
  ],
  sap_b1: [
    { key: 'connect', label: 'Connect', description: 'Configure B1 Service Layer connection', icon: Server, detail: 'Set up a connection to SAP Business One via the Service Layer REST API (OData v4). Provide the server URL, company database, username, and password. CSV import also supported.' },
    { key: 'master_data', label: 'Master Data', description: 'Import items, warehouses, BPs, and BOMs', icon: Database, detail: 'Extract Warehouses, Items, BusinessPartners, ProductTrees, and ItemWarehouseInfo. Creates sites, products, trading partners, BOMs, and inventory levels.' },
    { key: 'user_import', label: 'User Import', description: 'Provision SC-relevant users', icon: Users, detail: 'Map B1 user authorizations to Autonomy decision levels. Import users with relevant warehouse and purchasing permissions.' },
    { key: 'transaction_data', label: 'Transaction Data', description: 'Import orders, deliveries, and production', icon: Activity, detail: 'Extract Orders, PurchaseOrders, ProductionOrders, DeliveryNotes, StockTransfers, and 20+ other transaction entities. Builds complete operational history.' },
    { key: 'warm_start', label: 'Warm Start', description: 'Provision AI models and generate plans', icon: Zap, detail: 'Run the 16-step provisioning pipeline: warm start simulation, agent training, supply plan generation, decision seeding, and conformal calibration.' },
  ],

  // ── Dedicated TMS systems ──────────────────────────────────────────
  sap_tm: [
    { key: 'connect', label: 'Connect', description: 'Configure SAP TM connection (RFC or OData)', icon: Server, detail: 'Connect to SAP TM via RFC (on-premise S/4HANA) or OData (S/4HANA Cloud via API_FREIGHT_ORDER / API_BUSINESS_PARTNER). Provide credentials, client, and preferred method.' },
    { key: 'carriers', label: 'Carriers + Rates', description: 'Import carrier master and freight rate catalog', icon: Database, detail: 'Extract carrier vendors (LFA1 or A_BusinessPartner with forwarding-agent role) + freight cost catalog (VFKP or customer CDS view). Creates the carrier portfolio.' },
    { key: 'user_import', label: 'User Import', description: 'Provision TMS-relevant users', icon: Users, detail: 'Map SAP users with transportation authorisations to Autonomy decision levels: shippers, dock coordinators, procurement, tower controllers.' },
    { key: 'transaction_data', label: 'Freight History', description: 'Import shipments, loads, appointments, exceptions', icon: Activity, detail: 'Extract Freight Orders (VTTK / A_FreightOrder), Freight Units (VTTS / A_FreightUnit), appointments derived from planned dates, and exception-status orders. Builds the execution history agents learn from.' },
    { key: 'warm_start', label: 'Warm Start', description: 'Provision agents and schedule extraction', icon: Zap, detail: 'Calibrate the 11 TMS execution agents on extracted history; activate the 30m / 4h / daily extraction scheduler; seed the Decision Stream with first live tenders.' },
  ],
  oracle_otm: [
    { key: 'connect', label: 'Connect', description: 'Configure Oracle OTM REST connection', icon: Server, detail: 'Connect to Oracle OTM via the glog RestServlet. Basic auth with domain-qualified user (DEFAULT/user). Provide base URL, domain, credentials, and optional domain / servprov filters.' },
    { key: 'carriers', label: 'Carriers + Rates', description: 'Import SERVPROV and RATE_OFFERING', icon: Database, detail: 'Extract OTM service providers (carriers) and rate offerings. Maps SERVPROV_GID to the Autonomy carrier portfolio and RATE_OFFERING to the rate catalog.' },
    { key: 'user_import', label: 'User Import', description: 'Provision TMS-relevant users', icon: Users, detail: 'Map OTM users with transportation roles (planner, dispatcher, tower controller) to Autonomy decision levels.' },
    { key: 'transaction_data', label: 'Freight History', description: 'Import shipments, movements, stops, statuses', icon: Activity, detail: 'Extract SHIPMENT, ORDER_MOVEMENT, SHIPMENT_STOP, and SHIPMENT_STATUS records. Builds multi-leg execution history including exception states.' },
    { key: 'warm_start', label: 'Warm Start', description: 'Provision agents and schedule extraction', icon: Zap, detail: 'Calibrate the 11 TMS execution agents on extracted history; activate the extraction scheduler; seed the Decision Stream.' },
  ],
  blue_yonder: [
    { key: 'connect', label: 'Connect', description: 'Configure Blue Yonder TMS OAuth2 connection', icon: Server, detail: 'Connect to Blue Yonder Luminate TMS via OAuth2 client credentials. Provide base URL, client ID, client secret, and tenant code. Token auto-refreshes on 401.' },
    { key: 'carriers', label: 'Carriers + Rates', description: 'Import carriers and rate agreements', icon: Database, detail: 'Extract the carrier catalog and rate agreements via /api/tms/v2/carriers and /api/tms/v2/rates. Populates the carrier portfolio and rate catalog.' },
    { key: 'user_import', label: 'User Import', description: 'Provision TMS-relevant users', icon: Users, detail: 'Map BY TMS users to Autonomy decision levels. Import planners, dock supervisors, procurement leads, exception managers.' },
    { key: 'transaction_data', label: 'Freight History', description: 'Import orders, appointments, exceptions', icon: Activity, detail: 'Extract orders (/api/tms/v2/orders), appointments (/api/tms/v2/appointments), and exceptions. Builds execution history for the 11 TMS agents.' },
    { key: 'warm_start', label: 'Warm Start', description: 'Provision agents and schedule extraction', icon: Zap, detail: 'Calibrate the 11 TMS execution agents on extracted history; activate the extraction scheduler; seed the Decision Stream.' },
  ],
};

// ---------------------------------------------------------------------------
// Generic ERP Guided Pipeline
// ---------------------------------------------------------------------------

function ERPGuidedPipeline({ erpType, erpLabel }) {
  const steps = ERP_PIPELINE_STEPS[erpType] || [];
  const [expandedStep, setExpandedStep] = useState('connect');
  const [connections, setConnections] = useState([]);
  const [loadingConns, setLoadingConns] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [runningStep, setRunningStep] = useState(null);
  const { user } = useAuth();
  const tenantId = user?.tenant_id || user?.group_id;

  const loadConnections = useCallback(async () => {
    if (!tenantId) return;
    setLoadingConns(true);
    try {
      const r = await api.get('/erp-integration/connections', {
        params: { tenant_id: tenantId, erp_type: erpType },
      });
      setConnections(r.data || []);
    } catch (e) {
      console.error('Failed to load ERP connections:', e);
    } finally {
      setLoadingConns(false);
    }
  }, [tenantId, erpType]);

  useEffect(() => { loadConnections(); }, [loadConnections]);

  const handleTest = async (connId) => {
    try {
      const r = await api.post(`/erp-integration/connections/${connId}/test`, null, {
        params: { tenant_id: tenantId },
      });
      alert(r.data.success ? 'Connection OK' : 'Connection FAILED — see logs');
      loadConnections();
    } catch (e) {
      alert(`Test failed: ${e.message}`);
    }
  };

  const handleDelete = async (connId) => {
    if (!window.confirm('Delete this connection?')) return;
    await api.delete(`/erp-integration/connections/${connId}`, {
      params: { tenant_id: tenantId },
    });
    loadConnections();
  };

  const handleRunStep = async (stepKey) => {
    if (connections.length === 0) {
      alert('Add and test a connection first.');
      return;
    }
    const conn = connections.find(c => c.is_validated) || connections[0];
    setRunningStep(stepKey);
    try {
      // Map UI step → entity_types for the extraction service.
      const entityMap = {
        carriers: ['carriers', 'rates'],
        transaction_data: ['shipments', 'loads', 'appointments', 'exceptions'],
        master_data: ['carriers', 'rates'],
        warm_start: [],
        user_import: [],
      };
      const entities = entityMap[stepKey] || [];
      if (entities.length > 0) {
        const path = ['sap_tm', 'oracle_otm', 'blue_yonder'].includes(erpType)
          ? `/tms-integration/extract/${conn.id}`
          : `/erp-integration/extract/${conn.id}`;
        const r = await api.post(path, {
          entity_types: entities,
          mode: stepKey === 'warm_start' ? 'full' : 'incremental',
        }, { params: { tenant_id: tenantId } });
        const total = (r.data.results || []).reduce(
          (acc, x) => acc + (x.records_extracted || 0), 0,
        );
        alert(`Extracted ${total} records across ${entities.join(', ')}`);
      } else if (stepKey === 'warm_start') {
        alert('Warm Start triggered — agent calibration runs in background scheduler.');
      } else {
        alert(`${stepKey}: not yet wired for this vendor`);
      }
    } catch (e) {
      alert(`Step failed: ${e?.response?.data?.detail || e.message}`);
    } finally {
      setRunningStep(null);
    }
  };

  const getStepStatus = (stepKey, idx) => {
    if (stepKey === 'connect') {
      return connections.some(c => c.is_validated) ? 'complete'
        : connections.length > 0 ? 'ready' : 'ready';
    }
    if (!connections.some(c => c.is_validated)) return 'locked';
    if (runningStep === stepKey) return 'running';
    return 'ready';
  };

  const statusConfig = {
    complete: { icon: CheckCircle, color: 'text-green-600', bg: 'bg-green-50 border-green-200', label: 'Complete' },
    running: { icon: RefreshCw, color: 'text-blue-600', bg: 'bg-blue-50 border-blue-200', label: 'Running' },
    ready: { icon: Play, color: 'text-blue-600', bg: 'bg-white border-blue-300', label: 'Ready' },
    locked: { icon: Lock, color: 'text-gray-400', bg: 'bg-gray-50 border-gray-200', label: 'Waiting' },
    error: { icon: AlertTriangle, color: 'text-red-600', bg: 'bg-red-50 border-red-200', label: 'Error' },
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Zap className="h-5 w-5 text-blue-600" />
            {erpLabel} Ingestion Pipeline
          </CardTitle>
          <p className="text-sm text-muted-foreground mt-1">
            Follow these steps in order to deploy your {erpLabel} data into the platform.
            Each step depends on the previous one completing successfully.
          </p>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {steps.map((step, idx) => {
              const status = getStepStatus(step.key, idx);
              const cfg = statusConfig[status];
              const isExpanded = expandedStep === step.key;
              const StepIcon = step.icon;
              const StatusIcon = cfg.icon;

              return (
                <div key={step.key}>
                  <div
                    className={cn(
                      "flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors",
                      cfg.bg,
                      status !== 'locked' && "hover:shadow-sm",
                    )}
                    onClick={() => status !== 'locked' && setExpandedStep(isExpanded ? null : step.key)}
                  >
                    <div className={cn(
                      "flex items-center justify-center w-8 h-8 rounded-full text-sm font-semibold",
                      status === 'complete' ? "bg-green-100 text-green-700" :
                      status === 'ready' ? "bg-blue-100 text-blue-700" :
                      "bg-gray-100 text-gray-400"
                    )}>
                      {idx + 1}
                    </div>

                    <StepIcon className={cn("h-5 w-5", cfg.color)} />

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className={cn("font-medium", status === 'locked' ? "text-gray-400" : "text-gray-900")}>
                          {step.label}
                        </span>
                        {status !== 'ready' && (
                          <Badge variant={status === 'complete' ? 'success' : status === 'locked' ? 'secondary' : 'default'}>
                            {cfg.label}
                          </Badge>
                        )}
                      </div>
                      <p className={cn("text-sm", status === 'locked' ? "text-gray-300" : "text-gray-500")}>
                        {step.description}
                      </p>
                    </div>

                    {status !== 'locked' && (
                      isExpanded
                        ? <ChevronDown className="h-5 w-5 text-gray-400" />
                        : <ChevronRight className="h-5 w-5 text-gray-400" />
                    )}
                    {status === 'locked' && <Clock className="h-5 w-5 text-gray-300" />}
                  </div>

                  {isExpanded && status !== 'locked' && (
                    <div className="ml-11 mt-2 p-4 bg-white border border-gray-200 rounded-lg space-y-3">
                      <p className="text-sm text-gray-600">{step.detail}</p>

                      {step.key === 'connect' && (
                        <div className="space-y-2">
                          <div className="flex gap-2">
                            <Button size="sm" className="gap-1" onClick={() => setShowAddModal(true)}>
                              <Upload className="h-4 w-4" />
                              Add Connection
                            </Button>
                            <Button size="sm" variant="outline" className="gap-1" onClick={loadConnections} disabled={loadingConns}>
                              <RefreshCw className={cn("h-4 w-4", loadingConns && "animate-spin")} />
                              Refresh
                            </Button>
                          </div>
                          {connections.length === 0 ? (
                            <span className="text-sm text-orange-600 flex items-center gap-1">
                              <AlertTriangle className="h-4 w-4" />
                              No connections configured yet.
                            </span>
                          ) : (
                            <div className="space-y-1">
                              {connections.map(c => (
                                <div key={c.id} className="flex items-center gap-2 text-sm border rounded p-2">
                                  <span className="font-medium flex-1">{c.name}</span>
                                  <Badge variant={c.is_validated ? 'success' : 'secondary'}>
                                    {c.is_validated ? 'Validated' : 'Untested'}
                                  </Badge>
                                  <Button size="sm" variant="outline" onClick={() => handleTest(c.id)}>Test</Button>
                                  <Button size="sm" variant="ghost" onClick={() => handleDelete(c.id)}>
                                    <Trash2 className="h-4 w-4" />
                                  </Button>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}

                      {step.key !== 'connect' && (
                        <Button size="sm" variant="outline" disabled={status === 'locked' || runningStep === step.key}
                          className="gap-1" onClick={() => handleRunStep(step.key)}>
                          <Play className={cn("h-4 w-4", runningStep === step.key && "animate-spin")} />
                          {runningStep === step.key ? `Running ${step.label}…` : `Run ${step.label}`}
                        </Button>
                      )}
                    </div>
                  )}

                  {idx < steps.length - 1 && (
                    <div className="flex justify-start ml-[1.75rem]">
                      <div className={cn(
                        "w-0.5 h-3",
                        getStepStatus(steps[idx + 1].key, idx + 1) === 'locked' ? "bg-gray-200" : "bg-blue-300"
                      )} />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <Alert>
        <Zap className="h-4 w-4" />
        <AlertDescription>
          <strong>How the phases work:</strong> Each phase uses the same {erpLabel} connection but processes different table categories.
          <ul className="list-disc ml-5 mt-1 text-sm">
            <li><strong>Master Data</strong> creates your supply chain topology (sites, products, lanes, BOMs) — run once at initial setup.</li>
            <li><strong>Transaction Data</strong> imports historical orders, shipments, and operations — run periodically for updates.</li>
            <li><strong>Warm Start</strong> provisions AI models, generates demand forecasts, and seeds the decision stream.</li>
          </ul>
        </AlertDescription>
      </Alert>

      <AddConnectionDialog
        open={showAddModal}
        onClose={() => setShowAddModal(false)}
        erpType={erpType}
        erpLabel={erpLabel}
        tenantId={tenantId}
        onCreated={() => { setShowAddModal(false); loadConnections(); }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Add Connection Dialog — vendor-aware form
// ---------------------------------------------------------------------------
function AddConnectionDialog({ open, onClose, erpType, erpLabel, tenantId, onCreated }) {
  const schema = CONNECTION_FORM_SCHEMA[erpType];
  const [name, setName] = useState('');
  const [values, setValues] = useState({});
  const [submitting, setSubmitting] = useState(false);

  if (!schema) return null;

  const setField = (key, value) => setValues(v => ({ ...v, [key]: value }));

  const submit = async () => {
    if (!name) { alert('Connection name required'); return; }
    setSubmitting(true);
    try {
      // Group dotted keys (auth_credentials.x, connection_params.y) into nested dicts
      const auth_credentials = {};
      const connection_params = {};
      let base_url = null;
      for (const f of schema.fields) {
        const v = values[f.key];
        if (!v) continue;
        if (f.key === 'base_url') base_url = v;
        else if (f.key.startsWith('auth_credentials.')) auth_credentials[f.key.slice(18)] = v;
        else if (f.key.startsWith('connection_params.')) connection_params[f.key.slice(19)] = v;
      }
      await api.post('/erp-integration/connections', {
        name,
        erp_type: erpType,
        connection_method: schema.method,
        base_url,
        auth_type: 'password',
        auth_credentials,
        connection_params,
      }, { params: { tenant_id: tenantId } });
      setName(''); setValues({});
      onCreated();
    } catch (e) {
      alert(`Create failed: ${e?.response?.data?.detail || e.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Add {erpLabel} connection</DialogTitle>
          <DialogDescription>
            Credentials are stored encrypted at rest in the tenant database.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div>
            <label className="text-sm font-medium">Connection name</label>
            <input
              className="w-full border rounded px-2 py-1.5 text-sm"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder={`${erpLabel} — production`}
            />
          </div>
          {schema.fields.map(f => (
            <div key={f.key}>
              <label className="text-sm font-medium">
                {f.label}{f.required && <span className="text-red-500">*</span>}
              </label>
              {f.type === 'select' ? (
                <select
                  className="w-full border rounded px-2 py-1.5 text-sm"
                  value={values[f.key] || ''}
                  onChange={e => setField(f.key, e.target.value)}
                >
                  <option value="">— choose —</option>
                  {f.options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              ) : (
                <input
                  type={f.type === 'password' ? 'password' : 'text'}
                  className="w-full border rounded px-2 py-1.5 text-sm"
                  value={values[f.key] || ''}
                  onChange={e => setField(f.key, e.target.value)}
                  placeholder={f.placeholder}
                />
              )}
            </div>
          ))}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} disabled={submitting}>
            {submitting ? 'Creating…' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Planned ERP placeholder
// ---------------------------------------------------------------------------

function PlannedERPView({ erpLabel }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <Database className="h-16 w-16 text-gray-300 mb-4" />
      <h3 className="text-lg font-medium text-gray-600 mb-2">{erpLabel} Integration</h3>
      <p className="text-sm text-gray-400 max-w-md">
        This integration is planned for a future release.
        Contact support if you need early access.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function ERPDataManagement() {
  const [selectedERP, setSelectedERP] = useState('sap');

  return (
    <div className="p-6 space-y-4">
      <div>
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <Database className="h-6 w-6" />
          ERP + TMS Integrations
        </h2>
        <p className="text-sm text-muted-foreground mt-1">
          Configure connections to external ERP systems (master + transaction data) and
          dedicated TMS systems (shipments, loads, carriers, rates, appointments, exceptions).
          Each connection drives a guided pipeline: connect, import, calibrate agents, schedule ongoing sync.
        </p>
      </div>

      {/* Vendor type selector tabs — grouped ERP vs TMS */}
      <div className="flex gap-1 border-b border-gray-200 overflow-x-auto items-stretch">
        <span className="self-center text-[10px] font-semibold text-gray-400 uppercase tracking-wider pr-2">
          ERP
        </span>
        {ERP_TYPES.filter(e => e.kind === 'erp').map((erp) => (
          <button
            key={erp.key}
            onClick={() => erp.status === 'production' && setSelectedERP(erp.key)}
            className={cn(
              "px-4 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 transition-colors",
              selectedERP === erp.key
                ? "border-blue-600 text-blue-600"
                : erp.status === 'planned'
                  ? "border-transparent text-gray-300 cursor-not-allowed"
                  : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 cursor-pointer",
            )}
            disabled={erp.status === 'planned'}
          >
            {erp.label}
            {erp.status === 'planned' && (
              <span className="ml-1.5 text-[10px] px-1.5 py-0.5 bg-gray-100 text-gray-400 rounded">PLANNED</span>
            )}
          </button>
        ))}
        <div className="self-stretch w-px bg-gray-200 mx-2" />
        <span className="self-center text-[10px] font-semibold text-gray-400 uppercase tracking-wider pr-2">
          TMS
        </span>
        {ERP_TYPES.filter(e => e.kind === 'tms').map((erp) => (
          <button
            key={erp.key}
            onClick={() => erp.status === 'production' && setSelectedERP(erp.key)}
            className={cn(
              "px-4 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 transition-colors",
              selectedERP === erp.key
                ? "border-blue-600 text-blue-600"
                : erp.status === 'planned'
                  ? "border-transparent text-gray-300 cursor-not-allowed"
                  : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 cursor-pointer",
            )}
            disabled={erp.status === 'planned'}
          >
            {erp.label}
          </button>
        ))}
      </div>

      {/* Per-vendor content */}
      {selectedERP === 'sap' && <SAPDataManagement />}
      {selectedERP === 'odoo' && <ERPGuidedPipeline erpType="odoo" erpLabel="Odoo" />}
      {selectedERP === 'd365' && <ERPGuidedPipeline erpType="d365" erpLabel="Dynamics 365" />}
      {selectedERP === 'sap_b1' && <ERPGuidedPipeline erpType="sap_b1" erpLabel="SAP Business One" />}
      {selectedERP === 'netsuite' && <PlannedERPView erpLabel="Oracle NetSuite" />}
      {selectedERP === 'epicor' && <PlannedERPView erpLabel="Epicor Kinetic" />}
      {selectedERP === 'sap_tm' && <ERPGuidedPipeline erpType="sap_tm" erpLabel="SAP TM" />}
      {selectedERP === 'oracle_otm' && <ERPGuidedPipeline erpType="oracle_otm" erpLabel="Oracle OTM" />}
      {selectedERP === 'blue_yonder' && <ERPGuidedPipeline erpType="blue_yonder" erpLabel="Blue Yonder TMS" />}
    </div>
  );
}
