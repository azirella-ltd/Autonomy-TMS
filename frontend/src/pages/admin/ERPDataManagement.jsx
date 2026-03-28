import React, { useState } from 'react';
import { cn } from '../../lib/utils/cn';
import {
  Server, Database, Zap, Users, Activity, ChevronDown, ChevronRight,
  CheckCircle, Clock, Lock, Play, AlertTriangle, Upload, RefreshCw,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, Button, Alert, AlertDescription, Badge } from '../../components/common';
import SAPDataManagement from './SAPDataManagement';

// ---------------------------------------------------------------------------
// ERP type definitions
// ---------------------------------------------------------------------------

const ERP_TYPES = [
  { key: 'sap', label: 'SAP S/4HANA', color: '#0070C0', status: 'production' },
  { key: 'odoo', label: 'Odoo', color: '#714B67', status: 'production' },
  { key: 'd365', label: 'Dynamics 365', color: '#0078D4', status: 'production' },
  { key: 'sap_b1', label: 'SAP Business One', color: '#F0AB00', status: 'production' },
  { key: 'netsuite', label: 'NetSuite', color: '#1B3A5C', status: 'planned' },
  { key: 'epicor', label: 'Epicor', color: '#E4002B', status: 'planned' },
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
};

// ---------------------------------------------------------------------------
// Generic ERP Guided Pipeline
// ---------------------------------------------------------------------------

function ERPGuidedPipeline({ erpType, erpLabel }) {
  const steps = ERP_PIPELINE_STEPS[erpType] || [];
  const [expandedStep, setExpandedStep] = useState('connect');

  // For now, all steps start as "ready" (connect) or "locked" (rest)
  const getStepStatus = (stepKey, idx) => {
    if (idx === 0) return 'ready';
    return 'locked';
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
                        <div className="flex gap-2">
                          <Button size="sm" className="gap-1">
                            <Upload className="h-4 w-4" />
                            Add Connection
                          </Button>
                          <span className="text-sm text-orange-600 flex items-center gap-1">
                            <AlertTriangle className="h-4 w-4" />
                            No connections configured yet.
                          </span>
                        </div>
                      )}

                      {step.key !== 'connect' && (
                        <Button size="sm" variant="outline" disabled className="gap-1">
                          <Play className="h-4 w-4" />
                          Run {step.label}
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
    </div>
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
          ERP Data Management
        </h2>
        <p className="text-sm text-muted-foreground mt-1">
          Configure connections to external ERP systems. Extract master data, transaction data,
          and change data — mapped to the AWS Supply Chain data model.
        </p>
      </div>

      {/* ERP type selector tabs */}
      <div className="flex gap-1 border-b border-gray-200 overflow-x-auto">
        {ERP_TYPES.map((erp) => (
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
      </div>

      {/* Per-ERP content */}
      {selectedERP === 'sap' && <SAPDataManagement />}
      {selectedERP === 'odoo' && <ERPGuidedPipeline erpType="odoo" erpLabel="Odoo" />}
      {selectedERP === 'd365' && <ERPGuidedPipeline erpType="d365" erpLabel="Dynamics 365" />}
      {selectedERP === 'sap_b1' && <ERPGuidedPipeline erpType="sap_b1" erpLabel="SAP Business One" />}
      {selectedERP === 'netsuite' && <PlannedERPView erpLabel="Oracle NetSuite" />}
      {selectedERP === 'epicor' && <PlannedERPView erpLabel="Epicor Kinetic" />}
    </div>
  );
}
