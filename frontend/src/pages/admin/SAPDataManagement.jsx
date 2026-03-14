import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { api } from '../../services/api';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Button,
  Spinner,
  Alert,
  AlertDescription,
  Tabs,
  TabsList,
  Tab,
  Input,
  NativeSelect,
  Badge,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '../../components/common';
import {
  Database,
  Server,
  FileText,
  Table2,
  ArrowUpDown,
  AlertTriangle,
  CheckCircle,
  Clock,
  Play,
  RefreshCw,
  Settings,
  Lightbulb,
  Wrench,
  Upload,
  Download,
  Search,
  ChevronRight,
  ChevronDown,
  Zap,
  Activity,
  BarChart3,
  Users,
  Trash2,
  Plus,
  Eye,
  Shield,
  MapPin,
} from 'lucide-react';
import { cn } from '../../lib/utils/cn';

const tabItems = [
  { value: 'overview', label: 'Overview', icon: <BarChart3 className="h-4 w-4" /> },
  { value: 'connections', label: 'Connections', icon: <Server className="h-4 w-4" /> },
  { value: 'tables', label: 'Tables & Mapping', icon: <Table2 className="h-4 w-4" /> },
  { value: 'jobs', label: 'Ingestion Jobs', icon: <Activity className="h-4 w-4" /> },
  { value: 'insights', label: 'Insights & Actions', icon: <Lightbulb className="h-4 w-4" /> },
  { value: 'user-import', label: 'User Import', icon: <Users className="h-4 w-4" /> },
  { value: 'staging', label: 'Staging & Sync', icon: <RefreshCw className="h-4 w-4" /> },
];

const systemTypes = [
  { value: 's4hana', label: 'SAP S/4HANA' },
  { value: 'apo', label: 'SAP APO' },
  { value: 'ecc', label: 'SAP ECC' },
  { value: 'bw', label: 'SAP BW' },
];

const connectionMethods = [
  { value: 'csv', label: 'CSV File Import' },
  { value: 'rfc', label: 'RFC Connection' },
  { value: 'odata', label: 'OData API' },
  { value: 'idoc', label: 'IDoc Interface' },
  { value: 'hana_db', label: 'HANA DB (Direct SQL)' },
];

// Overview Tab Component
const OverviewTab = ({ dashboardData, deploymentStatus, loading }) => {
  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Deployment Progress */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5" />
            Deployment Status
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className={cn(
              "p-4 rounded-lg border-2",
              deploymentStatus?.connection_tested ? "border-green-500 bg-green-50" : "border-gray-300"
            )}>
              <div className="flex items-center gap-2 mb-2">
                {deploymentStatus?.connection_tested ? (
                  <CheckCircle className="h-5 w-5 text-green-500" />
                ) : (
                  <Clock className="h-5 w-5 text-gray-400" />
                )}
                <span className="font-medium">Connection</span>
              </div>
              <p className="text-sm text-muted-foreground">
                {deploymentStatus?.connection_tested ? 'Configured & Tested' : 'Not Configured'}
              </p>
            </div>

            <div className={cn(
              "p-4 rounded-lg border-2",
              deploymentStatus?.tables_enabled > 0 ? "border-green-500 bg-green-50" : "border-gray-300"
            )}>
              <div className="flex items-center gap-2 mb-2">
                {deploymentStatus?.tables_enabled > 0 ? (
                  <CheckCircle className="h-5 w-5 text-green-500" />
                ) : (
                  <Clock className="h-5 w-5 text-gray-400" />
                )}
                <span className="font-medium">Tables</span>
              </div>
              <p className="text-sm text-muted-foreground">
                {deploymentStatus?.tables_enabled || 0} tables enabled
              </p>
            </div>

            <div className={cn(
              "p-4 rounded-lg border-2",
              deploymentStatus?.unmapped_fields === 0 ? "border-green-500 bg-green-50" : "border-yellow-500 bg-yellow-50"
            )}>
              <div className="flex items-center gap-2 mb-2">
                {deploymentStatus?.unmapped_fields === 0 ? (
                  <CheckCircle className="h-5 w-5 text-green-500" />
                ) : (
                  <AlertTriangle className="h-5 w-5 text-yellow-500" />
                )}
                <span className="font-medium">Field Mapping</span>
              </div>
              <p className="text-sm text-muted-foreground">
                {deploymentStatus?.mapped_fields || 0}/{deploymentStatus?.total_fields || 0} mapped
              </p>
            </div>

            <div className={cn(
              "p-4 rounded-lg border-2",
              deploymentStatus?.ready_for_production ? "border-green-500 bg-green-50" : "border-gray-300"
            )}>
              <div className="flex items-center gap-2 mb-2">
                {deploymentStatus?.ready_for_production ? (
                  <CheckCircle className="h-5 w-5 text-green-500" />
                ) : (
                  <Clock className="h-5 w-5 text-gray-400" />
                )}
                <span className="font-medium">Production Ready</span>
              </div>
              <p className="text-sm text-muted-foreground">
                {deploymentStatus?.ready_for_production ? 'Ready' : 'Not Ready'}
              </p>
            </div>
          </div>

          {/* Z-Fields Status */}
          {deploymentStatus?.z_fields_count > 0 && (
            <div className="mt-4 p-4 bg-blue-50 rounded-lg border border-blue-200">
              <div className="flex items-center gap-2 mb-2">
                <Zap className="h-5 w-5 text-blue-500" />
                <span className="font-medium">Z-Field Mapping Status</span>
              </div>
              <p className="text-sm text-muted-foreground">
                {deploymentStatus?.z_fields_mapped || 0} of {deploymentStatus?.z_fields_count} Z-fields mapped
              </p>
              {deploymentStatus?.z_fields_mapped < deploymentStatus?.z_fields_count && (
                <p className="text-sm text-blue-600 mt-1">
                  Use AI-powered mapping to resolve unmapped Z-fields in the Tables & Mapping tab.
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Dashboard Summary */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Active Jobs</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{dashboardData?.active_jobs || 0}</div>
            <p className="text-sm text-muted-foreground">
              {dashboardData?.total_jobs_completed || 0} total completed
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Insights</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{dashboardData?.unacknowledged_insights || 0}</div>
            <div className="flex gap-2 mt-2">
              {dashboardData?.insights_by_severity?.critical > 0 && (
                <Badge variant="destructive">{dashboardData.insights_by_severity.critical} critical</Badge>
              )}
              {dashboardData?.insights_by_severity?.error > 0 && (
                <Badge variant="warning">{dashboardData.insights_by_severity.error} errors</Badge>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Pending Actions</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{dashboardData?.pending_actions || 0}</div>
            <p className="text-sm text-muted-foreground">
              Recommended remediation actions
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Recent Jobs */}
      {dashboardData?.recent_jobs?.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Recent Jobs</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {dashboardData.recent_jobs.slice(0, 5).map((job, idx) => (
                <div key={idx} className="flex items-center justify-between p-3 bg-muted rounded-lg">
                  <div className="flex items-center gap-3">
                    <Badge variant={
                      job.status === 'completed' ? 'success' :
                      job.status === 'running' ? 'default' :
                      job.status === 'failed' ? 'destructive' : 'secondary'
                    }>
                      {job.status}
                    </Badge>
                    <span className="font-medium">{job.job_type}</span>
                    {job.phase && <Badge variant="outline" className="text-xs">{job.phase}</Badge>}
                    <span className="text-muted-foreground">
                      {job.tables?.join(', ')}
                    </span>
                  </div>
                  <div className="text-sm text-muted-foreground">
                    {job.progress_percent?.toFixed(1)}%
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

// Connections Tab Component
const ConnectionsTab = ({ connections, onCreateConnection, onTestConnection, onUpdateConnection, onDeleteConnection, onConfirmFileMapping, loading }) => {
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [expandedMappings, setExpandedMappings] = useState({});
  const [editingMappings, setEditingMappings] = useState({});
  const defaultFormData = {
    name: '',
    description: '',
    system_type: 's4hana',
    connection_method: 'odata',
    hostname: '',
    port: '',
    use_ssl: true,
    ssl_verify: false,
    sid: '',
    ashost: '',
    sysnr: '00',
    client: '100',
    user: '',
    password: '',
    language: 'EN',
    odata_base_path: '/sap/opu/odata/sap/',
    csv_directory: '',
    csv_pattern: '*.csv',
    hana_schema: 'SAPHANADB',
    hana_port: '',
    sap_router_string: '',
    cloud_connector_location_id: '',
  };
  const [formData, setFormData] = useState(defaultFormData);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [importDirs, setImportDirs] = useState(null); // null = not loaded, [] = empty
  const [browsingPath, setBrowsingPath] = useState('');
  const [editingConnection, setEditingConnection] = useState(null);

  const isNetworkMethod = formData.connection_method !== 'csv';
  const isOData = formData.connection_method === 'odata';
  const isRFC = formData.connection_method === 'rfc';
  const isCSV = formData.connection_method === 'csv';
  const isHANA = formData.connection_method === 'hana_db';

  // Valid connection methods per SAP system type
  const methodsBySystemType = {
    s4hana: ['odata', 'rfc', 'hana_db', 'csv', 'idoc'],  // Full modern stack + HANA direct
    ecc:    ['rfc', 'idoc', 'csv'],            // No native OData (requires Gateway add-on)
    apo:    ['rfc', 'idoc', 'csv'],            // Legacy planning — RFC/IDoc for CIF
    bw:     ['rfc', 'csv'],                    // Data warehouse — RFC extraction only
  };

  // Default methods per system type (first valid option)
  const defaultMethodBySystemType = {
    s4hana: 'odata',
    ecc: 'rfc',
    apo: 'rfc',
    bw: 'rfc',
  };

  // SAP client presets (from SAP S/4HANA FAA Getting Started Guide §1.4)
  const clientPresets = [
    { value: '100', label: '100 — Trial & Exploration (demo data, US locale, company 1710)' },
    { value: '200', label: '200 — Ready-to-Activate (empty, custom BP setup)' },
    { value: '400', label: '400 — Best Practices Reference (43 localizations, master data only)' },
    { value: '000', label: '000 — Standard Delivery (admin only)' },
  ];

  const availableMethods = connectionMethods.filter(
    (m) => (methodsBySystemType[formData.system_type] || methodsBySystemType.s4hana).includes(m.value)
  );

  // When system type changes, reset connection method if current is invalid
  const handleSystemTypeChange = (systemType) => {
    const validMethods = methodsBySystemType[systemType] || methodsBySystemType.s4hana;
    const currentMethodValid = validMethods.includes(formData.connection_method);
    const newMethod = currentMethodValid ? formData.connection_method : (defaultMethodBySystemType[systemType] || validMethods[0]);
    let port = formData.port;
    if (!currentMethodValid) {
      if (newMethod === 'odata') port = 44301;
      else if (newMethod === 'rfc' || newMethod === 'idoc') port = 3300;
      else port = '';
    }
    setFormData({ ...formData, system_type: systemType, connection_method: newMethod, port });
  };

  // Set sensible default port when method changes
  const handleMethodChange = async (method) => {
    let port = formData.port;
    if (method === 'odata') port = 44301;
    else if (method === 'rfc') port = 3300;
    else if (method === 'idoc') port = 3300;
    else if (method === 'hana_db') port = 30215;
    else port = '';
    const updates = { connection_method: method, port };
    // Auto-populate CSV directory with default when switching to CSV method
    if (method === 'csv' && !formData.csv_directory) {
      try {
        const resp = await api.get('/sap-data/import-directories/default');
        if (resp.data.path) {
          updates.csv_directory = resp.data.path;
        }
      } catch { /* ignore */ }
    }
    setFormData({ ...formData, ...updates });
  };

  const handleCreate = async () => {
    if (editingConnection) {
      await onUpdateConnection(editingConnection, formData);
    } else {
      await onCreateConnection(formData);
    }
    setShowCreateDialog(false);
    setEditingConnection(null);
    setFormData(defaultFormData);
    setShowAdvanced(false);
    setImportDirs(null);
    setBrowsingPath('');
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-semibold">SAP Connections</h2>
        <Button onClick={() => setShowCreateDialog(true)}>
          <Server className="h-4 w-4 mr-2" />
          Add Connection
        </Button>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Spinner size="lg" />
        </div>
      ) : connections.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <Server className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
            <p className="text-muted-foreground">No connections configured yet.</p>
            <Button className="mt-4" onClick={() => setShowCreateDialog(true)}>
              Create Your First Connection
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4">
          {connections.map((conn) => (
            <Card key={conn.id}>
              <CardContent className="py-4 space-y-3">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-4">
                    <div className={cn(
                      "p-2 rounded-lg",
                      conn.is_validated ? "bg-green-100" : "bg-gray-100"
                    )}>
                      <Server className={cn(
                        "h-6 w-6",
                        conn.is_validated ? "text-green-600" : "text-gray-400"
                      )} />
                    </div>
                    <div>
                      <h3 className="font-medium">{conn.name}</h3>
                      <p className="text-sm text-muted-foreground">
                        {systemTypes.find(s => s.value === conn.system_type)?.label || conn.system_type}
                        {' • '}
                        {connectionMethods.find(m => m.value === conn.connection_method)?.label || conn.connection_method}
                        {conn.hostname && ` • ${conn.hostname}${conn.port ? ':' + conn.port : ''}`}
                        {conn.csv_directory && ` • ${conn.csv_directory}`}
                        {conn.sid && ` (${conn.sid})`}
                      </p>
                      {conn.description && (
                        <p className="text-xs text-muted-foreground mt-0.5">{conn.description}</p>
                      )}
                    </div>
                  </div>
                  <Badge variant={conn.is_validated ? 'success' : 'secondary'}>
                    {conn.is_validated ? 'Validated' : 'Not Tested'}
                  </Badge>
                </div>
                <div className="flex items-center gap-2 border-t pt-3">
                  <Button variant="outline" size="sm" onClick={() => onTestConnection(conn.id)}>
                    Test Connection
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => {
                    setFormData({
                      name: conn.name || '',
                      description: conn.description || '',
                      system_type: conn.system_type || 's4hana',
                      connection_method: conn.connection_method || 'odata',
                      hostname: conn.hostname || '',
                      port: conn.port || '',
                      use_ssl: conn.use_ssl ?? true,
                      ssl_verify: conn.ssl_verify ?? false,
                      sid: conn.sid || '',
                      ashost: '',
                      sysnr: '00',
                      client: conn.client || '100',
                      user: conn.user || '',
                      password: '',
                      language: conn.language || 'EN',
                      odata_base_path: conn.odata_base_path || '/sap/opu/odata/sap/',
                      csv_directory: conn.csv_directory || '',
                      csv_pattern: conn.csv_pattern || '*.csv',
                      hana_schema: conn.hana_schema || 'SAPHANADB',
                      hana_port: conn.hana_port || '',
                      sap_router_string: '',
                      cloud_connector_location_id: '',
                    });
                    setEditingConnection(conn.id);
                    setShowCreateDialog(true);
                  }}>
                    Edit
                  </Button>
                  <div className="flex-1" />
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-red-600 hover:bg-red-50 border-red-200"
                    onClick={() => {
                      if (window.confirm(`Delete connection "${conn.name}"? This will also delete all associated jobs.`)) {
                        onDeleteConnection(conn.id);
                      }
                    }}
                  >
                    Delete
                  </Button>
                </div>

                {/* File-to-Table Mapping (shown after test for CSV connections) */}
                {conn.file_table_mapping && conn.file_table_mapping.length > 0 && (
                  <div className="border-t pt-3">
                    <button
                      className="flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground w-full"
                      onClick={() => setExpandedMappings(prev => ({ ...prev, [conn.id]: !prev[conn.id] }))}
                    >
                      {expandedMappings[conn.id]
                        ? <ChevronDown className="h-4 w-4" />
                        : <ChevronRight className="h-4 w-4" />}
                      <FileText className="h-4 w-4" />
                      {conn.file_table_mapping.length} files identified
                      {conn.file_table_mapping.some(f => !f.confirmed) && (
                        <Badge variant="warning" className="ml-2">
                          {conn.file_table_mapping.filter(f => !f.confirmed).length} need review
                        </Badge>
                      )}
                      {conn.file_table_mapping.every(f => f.confirmed) && (
                        <Badge variant="success" className="ml-2">All confirmed</Badge>
                      )}
                    </button>

                    {expandedMappings[conn.id] && (
                      <div className="mt-3 space-y-1">
                        <div className="grid grid-cols-[1fr_120px_80px_60px_40px] gap-2 text-xs font-medium text-muted-foreground px-2 pb-1 border-b">
                          <span>File</span>
                          <span>SAP Table</span>
                          <span>Confidence</span>
                          <span>Rows</span>
                          <span></span>
                        </div>
                        {conn.file_table_mapping.map((file, idx) => {
                          const isEditing = editingMappings[`${conn.id}_${idx}`];
                          const confidence = file.confidence || 0;
                          return (
                            <div
                              key={idx}
                              className={cn(
                                "grid grid-cols-[1fr_120px_80px_60px_40px] gap-2 items-center text-sm px-2 py-1 rounded",
                                !file.confirmed && "bg-yellow-50 border border-yellow-200",
                                file.confirmed && "bg-green-50/50"
                              )}
                            >
                              <span className="truncate text-xs font-mono">{file.filename}</span>
                              {isEditing ? (
                                <Input
                                  className="h-6 text-xs"
                                  defaultValue={file.table || ''}
                                  onBlur={(e) => {
                                    const newTable = e.target.value.toUpperCase().trim() || null;
                                    onConfirmFileMapping(conn.id, [{
                                      filename: file.filename,
                                      table: newTable,
                                      confirmed: !!newTable,
                                    }]);
                                    setEditingMappings(prev => ({ ...prev, [`${conn.id}_${idx}`]: false }));
                                  }}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter') e.target.blur();
                                  }}
                                  autoFocus
                                />
                              ) : (
                                <span className={cn(
                                  "text-xs font-mono",
                                  !file.table && "text-red-500 italic"
                                )}>
                                  {file.table || 'Unknown'}
                                </span>
                              )}
                              <Badge
                                variant={confidence >= 0.7 ? 'success' : confidence >= 0.3 ? 'warning' : 'destructive'}
                                className="text-[10px] px-1.5 py-0"
                              >
                                {(confidence * 100).toFixed(0)}%
                              </Badge>
                              <span className="text-xs text-muted-foreground">{file.row_count?.toLocaleString()}</span>
                              <div className="flex gap-0.5">
                                {!file.confirmed ? (
                                  <>
                                    {file.table && (
                                      <button
                                        className="text-green-600 hover:text-green-800"
                                        title="Confirm this mapping"
                                        onClick={() => onConfirmFileMapping(conn.id, [{
                                          filename: file.filename,
                                          table: file.table,
                                          confirmed: true,
                                        }])}
                                      >
                                        <CheckCircle className="h-4 w-4" />
                                      </button>
                                    )}
                                    <button
                                      className="text-blue-600 hover:text-blue-800"
                                      title="Edit table assignment"
                                      onClick={() => setEditingMappings(prev => ({ ...prev, [`${conn.id}_${idx}`]: true }))}
                                    >
                                      <Settings className="h-3.5 w-3.5" />
                                    </button>
                                  </>
                                ) : (
                                  <CheckCircle className="h-4 w-4 text-green-500" />
                                )}
                              </div>
                            </div>
                          );
                        })}
                        {conn.file_table_mapping.some(f => !f.confirmed) && (
                          <div className="flex justify-end pt-2">
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => {
                                const confirmable = conn.file_table_mapping
                                  .filter(f => !f.confirmed && f.table && f.confidence >= 0.3)
                                  .map(f => ({ filename: f.filename, table: f.table, confirmed: true }));
                                if (confirmable.length > 0) {
                                  onConfirmFileMapping(conn.id, confirmable);
                                }
                              }}
                            >
                              <CheckCircle className="h-4 w-4 mr-1" />
                              Confirm All ({conn.file_table_mapping.filter(f => !f.confirmed && f.table && f.confidence >= 0.3).length})
                            </Button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create Connection Dialog */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editingConnection ? 'Edit SAP Connection' : 'Add SAP Connection'}</DialogTitle>
            <DialogDescription>
              Configure a connection to your SAP system for data extraction.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-5 py-4">
            {/* Always visible */}
            <div>
              <label className="block text-sm font-medium mb-1">Connection Name *</label>
              <Input
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="e.g., S/4HANA FAA Production"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Description</label>
              <textarea
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm min-h-[60px]"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="Optional description of this connection"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1">System Type</label>
                <NativeSelect
                  value={formData.system_type}
                  onChange={(e) => handleSystemTypeChange(e.target.value)}
                >
                  {systemTypes.map((type) => (
                    <option key={type.value} value={type.value}>{type.label}</option>
                  ))}
                </NativeSelect>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Connection Method</label>
                <NativeSelect
                  value={formData.connection_method}
                  onChange={(e) => handleMethodChange(e.target.value)}
                >
                  {availableMethods.map((method) => (
                    <option key={method.value} value={method.value}>{method.label}</option>
                  ))}
                </NativeSelect>
              </div>
            </div>

            {/* Network section (OData, RFC, IDoc — not CSV) */}
            {isNetworkMethod && (
              <div className="space-y-3 border rounded-lg p-4">
                <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Network</h4>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-1">Hostname / IP Address *</label>
                    <Input
                      value={formData.hostname}
                      onChange={(e) => setFormData({ ...formData, hostname: e.target.value })}
                      placeholder="e.g., 54.174.177.100 or vhcals4hcs.dummy.nodomain"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Port *</label>
                    <Input
                      type="number"
                      value={formData.port}
                      onChange={(e) => setFormData({ ...formData, port: e.target.value ? parseInt(e.target.value) : '' })}
                      placeholder={isOData ? '44301' : '3300'}
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="use_ssl"
                      checked={formData.use_ssl}
                      onChange={(e) => setFormData({ ...formData, use_ssl: e.target.checked })}
                      className="rounded border-gray-300"
                    />
                    <label htmlFor="use_ssl" className="text-sm font-medium">Use SSL (HTTPS)</label>
                  </div>
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="ssl_verify"
                      checked={formData.ssl_verify}
                      onChange={(e) => setFormData({ ...formData, ssl_verify: e.target.checked })}
                      className="rounded border-gray-300"
                    />
                    <div>
                      <label htmlFor="ssl_verify" className="text-sm font-medium">Verify SSL Certificate</label>
                      <p className="text-xs text-muted-foreground">Disable for self-signed certificates</p>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* SAP System section (OData, RFC, IDoc — not CSV) */}
            {isNetworkMethod && (
              <div className="space-y-3 border rounded-lg p-4">
                <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">SAP System</h4>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-1">SID</label>
                    <Input
                      value={formData.sid}
                      onChange={(e) => setFormData({ ...formData, sid: e.target.value })}
                      placeholder="S4H"
                    />
                    <p className="text-xs text-muted-foreground mt-0.5">System ID</p>
                  </div>
                  {isRFC && (
                    <div>
                      <label className="block text-sm font-medium mb-1">System Number</label>
                      <Input
                        value={formData.sysnr}
                        onChange={(e) => setFormData({ ...formData, sysnr: e.target.value })}
                        placeholder="00"
                      />
                    </div>
                  )}
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-1">Client</label>
                    <NativeSelect
                      value={formData.client}
                      onChange={(e) => setFormData({ ...formData, client: e.target.value })}
                    >
                      {clientPresets.map((c) => (
                        <option key={c.value} value={c.value}>{c.label}</option>
                      ))}
                    </NativeSelect>
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Language</label>
                    <Input
                      value={formData.language}
                      onChange={(e) => setFormData({ ...formData, language: e.target.value })}
                      placeholder="EN"
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Authentication section (OData, RFC, IDoc — not CSV) */}
            {isNetworkMethod && (
              <div className="space-y-3 border rounded-lg p-4">
                <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Authentication</h4>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-1">SAP Username *</label>
                    <Input
                      value={formData.user}
                      onChange={(e) => setFormData({ ...formData, user: e.target.value })}
                      placeholder="DDIC or S4H_MM_DEM"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">SAP Password *</label>
                    <Input
                      type="password"
                      value={formData.password}
                      onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                      placeholder="Master Password from SAP CAL"
                    />
                  </div>
                </div>
              </div>
            )}

            {/* OData section */}
            {isOData && (
              <div className="space-y-3 border rounded-lg p-4">
                <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">OData Settings</h4>
                <div>
                  <label className="block text-sm font-medium mb-1">OData Base Path</label>
                  <Input
                    value={formData.odata_base_path}
                    onChange={(e) => setFormData({ ...formData, odata_base_path: e.target.value })}
                    placeholder="/sap/opu/odata/sap/"
                  />
                  <p className="text-xs text-muted-foreground mt-0.5">OData service base path</p>
                </div>
              </div>
            )}

            {/* CSV section */}
            {isCSV && (
              <div className="space-y-3 border rounded-lg p-4">
                <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">CSV Import Settings</h4>
                <div className="space-y-3">
                  <div>
                    <label className="block text-sm font-medium mb-1">CSV Directory Path *</label>
                    <div className="flex gap-2">
                      <Input
                        value={formData.csv_directory}
                        onChange={(e) => setFormData({ ...formData, csv_directory: e.target.value })}
                        placeholder="/app/imports/SAP/IDES_1710"
                        className="flex-1"
                      />
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={async () => {
                          try {
                            const resp = await api.get('/sap-data/import-directories', { params: { subpath: browsingPath } });
                            setImportDirs(resp.data);
                          } catch (err) {
                            console.error('Failed to browse directories:', err);
                            setImportDirs([]);
                          }
                        }}
                      >
                        Browse
                      </Button>
                    </div>
                    {importDirs !== null && (
                      <div className="mt-2 border rounded-lg max-h-48 overflow-y-auto">
                        {browsingPath && (
                          <button
                            className="w-full text-left px-3 py-1.5 text-sm hover:bg-muted flex items-center gap-2 border-b"
                            onClick={async () => {
                              const parent = browsingPath.split('/').slice(0, -1).join('/');
                              setBrowsingPath(parent);
                              try {
                                const resp = await api.get('/sap-data/import-directories', { params: { subpath: parent } });
                                setImportDirs(resp.data);
                              } catch { setImportDirs([]); }
                            }}
                          >
                            ⬆ ..
                          </button>
                        )}
                        {importDirs.length === 0 ? (
                          <p className="px-3 py-2 text-sm text-muted-foreground">No import directories found. Mount CSV files to <code>/app/imports/</code></p>
                        ) : importDirs.map((entry) => (
                          <button
                            key={entry.path}
                            className="w-full text-left px-3 py-1.5 text-sm hover:bg-muted flex items-center justify-between"
                            onClick={async () => {
                              if (entry.is_dir) {
                                const rel = entry.path.replace(/^\/app\/imports\/?/, '');
                                setBrowsingPath(rel);
                                try {
                                  const resp = await api.get('/sap-data/import-directories', { params: { subpath: rel } });
                                  setImportDirs(resp.data);
                                } catch { setImportDirs([]); }
                              }
                              // Always set the path when clicked
                              setFormData({ ...formData, csv_directory: entry.path });
                            }}
                          >
                            <span className="flex items-center gap-2">
                              {entry.is_dir ? '📁' : '📄'} {entry.name}
                            </span>
                            {entry.is_dir && entry.csv_count > 0 && (
                              <span className="text-xs text-muted-foreground">{entry.csv_count} CSVs</span>
                            )}
                            {!entry.is_dir && entry.size && (
                              <span className="text-xs text-muted-foreground">{(entry.size / 1024).toFixed(0)} KB</span>
                            )}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">CSV File Pattern</label>
                    <Input
                      value={formData.csv_pattern}
                      onChange={(e) => setFormData({ ...formData, csv_pattern: e.target.value })}
                      placeholder="*.csv"
                    />
                  </div>
                </div>
              </div>
            )}

            {/* HANA DB Direct section */}
            {isHANA && (
              <div className="space-y-3 border rounded-lg p-4">
                <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">HANA Database Settings</h4>
                <p className="text-xs text-muted-foreground">Direct SQL connection to the underlying HANA database. Use when OData/RFC are unavailable (e.g., FAA instances).</p>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-1">HANA SQL Port</label>
                    <Input
                      type="number"
                      value={formData.hana_port}
                      onChange={(e) => setFormData({ ...formData, hana_port: e.target.value })}
                      placeholder="30215"
                    />
                    <p className="text-xs text-muted-foreground mt-0.5">HANA indexserver SQL port (typically 3NN15 where NN=instance)</p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">HANA Schema</label>
                    <Input
                      value={formData.hana_schema}
                      onChange={(e) => setFormData({ ...formData, hana_schema: e.target.value })}
                      placeholder="SAPHANADB"
                    />
                    <p className="text-xs text-muted-foreground mt-0.5">Database schema containing SAP tables</p>
                  </div>
                </div>
              </div>
            )}

            {/* Advanced section (collapsible) */}
            {isNetworkMethod && (
              <div className="border rounded-lg">
                <button
                  type="button"
                  className="w-full flex items-center justify-between p-4 text-sm font-semibold text-muted-foreground uppercase tracking-wide hover:bg-muted/50 transition-colors"
                  onClick={() => setShowAdvanced(!showAdvanced)}
                >
                  <span>Advanced</span>
                  <ChevronRight className={cn("h-4 w-4 transition-transform", showAdvanced && "rotate-90")} />
                </button>
                {showAdvanced && (
                  <div className="space-y-3 px-4 pb-4">
                    <div>
                      <label className="block text-sm font-medium mb-1">SAP Router String</label>
                      <Input
                        value={formData.sap_router_string}
                        onChange={(e) => setFormData({ ...formData, sap_router_string: e.target.value })}
                        placeholder="/H/saprouter.example.com/H/"
                      />
                      <p className="text-xs text-muted-foreground mt-0.5">For connections via SAP Router</p>
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-1">Cloud Connector Location ID</label>
                      <Input
                        value={formData.cloud_connector_location_id}
                        onChange={(e) => setFormData({ ...formData, cloud_connector_location_id: e.target.value })}
                        placeholder="e.g., MyLocationID"
                      />
                      <p className="text-xs text-muted-foreground mt-0.5">SAP Cloud Connector virtual host</p>
                    </div>
                    {isRFC && (
                      <div>
                        <label className="block text-sm font-medium mb-1">Application Server Host (ashost)</label>
                        <Input
                          value={formData.ashost}
                          onChange={(e) => setFormData({ ...formData, ashost: e.target.value })}
                          placeholder="sap-server.example.com"
                        />
                        <p className="text-xs text-muted-foreground mt-0.5">Override if different from Hostname</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
          <div className="flex justify-end gap-2 pt-2 border-t">
            <Button variant="outline" onClick={() => { setShowCreateDialog(false); setEditingConnection(null); setFormData(defaultFormData); }}>
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={!formData.name}>
              {editingConnection ? 'Save Changes' : 'Create Connection'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

// Tables & Mapping Tab Component
const confidenceColor = (conf) => {
  if (!conf) return 'secondary';
  const c = conf.toLowerCase();
  if (c === 'high') return 'success';
  if (c === 'medium') return 'warning';
  if (c === 'low') return 'destructive';
  return 'secondary';
};

const TablesTab = ({ connections, selectedConnectionId, onSelectConnection }) => {
  const [tables, setTables] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedTable, setSelectedTable] = useState(null);
  const [fieldMappings, setFieldMappings] = useState([]);
  const [mappingLoading, setMappingLoading] = useState(false);

  useEffect(() => {
    if (selectedConnectionId) {
      loadTables(selectedConnectionId);
    }
  }, [selectedConnectionId]);

  const loadTables = async (connectionId) => {
    setLoading(true);
    try {
      const response = await api.get(`/sap-data/connections/${connectionId}/tables`);
      setTables(response.data);
    } catch (error) {
      console.error('Failed to load tables:', error);
    }
    setLoading(false);
  };

  const handleSelectTable = async (table) => {
    setSelectedTable(table);
    setFieldMappings([]);
    setMappingLoading(true);
    try {
      const resp = await api.get(
        `/sap-data/connections/${selectedConnectionId}/tables/${encodeURIComponent(table.table_name)}/fields`
      );
      setFieldMappings(resp.data);
    } catch (err) {
      console.error('Failed to load field mappings:', err);
    }
    setMappingLoading(false);
  };

  const handleRunAIMapping = async () => {
    if (!selectedTable) return;
    setMappingLoading(true);
    try {
      const resp = await api.get(
        `/sap-data/connections/${selectedConnectionId}/tables/${encodeURIComponent(selectedTable.table_name)}/fields`,
        { params: { use_ai: true } }
      );
      setFieldMappings(resp.data);
    } catch (err) {
      console.error('Failed to run AI mapping:', err);
    }
    setMappingLoading(false);
  };

  const handleAnalyzeZTable = async (table) => {
    setMappingLoading(true);
    try {
      const response = await api.post('/sap-data/z-table-analysis', {
        table_name: table.table_name,
        table_description: table.description,
        fields: [],
        use_ai: true,
      });
      setSelectedTable({ ...table, analysis: response.data });
    } catch (error) {
      console.error('Failed to analyze table:', error);
    }
    setMappingLoading(false);
  };

  const mappedCount = fieldMappings.filter(f => f.aws_sc_field).length;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-4">
          <h2 className="text-xl font-semibold">Tables & Field Mapping</h2>
          {connections.length > 0 && (
            <NativeSelect
              value={selectedConnectionId || ''}
              onChange={(e) => onSelectConnection(e.target.value)}
              className="w-64"
            >
              <option value="">Select a connection...</option>
              {connections.map((conn) => (
                <option key={conn.id} value={conn.id}>{conn.name}</option>
              ))}
            </NativeSelect>
          )}
        </div>
        <Button variant="outline">
          <Download className="h-4 w-4 mr-2" />
          Export Mappings
        </Button>
      </div>

      {!selectedConnectionId ? (
        <Card>
          <CardContent className="py-12 text-center">
            <Table2 className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
            <p className="text-muted-foreground">Select a connection to view available tables.</p>
          </CardContent>
        </Card>
      ) : loading ? (
        <div className="flex justify-center py-12">
          <Spinner size="lg" />
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-6">
          {/* Table List */}
          <div className="col-span-1">
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Available Tables ({tables.length})</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <div className="max-h-[600px] overflow-y-auto">
                  {tables.map((table) => (
                    <div
                      key={table.id}
                      className={cn(
                        "p-3 border-b cursor-pointer hover:bg-muted transition-colors",
                        selectedTable?.table_name === table.table_name && "bg-muted"
                      )}
                      onClick={() => handleSelectTable(table)}
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <span className={cn(
                            "font-mono text-sm",
                            !table.is_standard && "text-blue-600"
                          )}>
                            {table.table_name}
                          </span>
                          {!table.is_standard && (
                            <Badge variant="outline" className="ml-2 text-xs">Z-table</Badge>
                          )}
                        </div>
                        <Badge variant={table.is_enabled ? 'success' : 'secondary'} className="text-xs">
                          {table.is_enabled ? 'Enabled' : 'Disabled'}
                        </Badge>
                      </div>
                      <p className="text-xs text-muted-foreground mt-1 truncate">
                        {table.description}
                      </p>
                      {table.aws_sc_entity && (
                        <p className="text-xs text-blue-500 mt-0.5">
                          → {table.aws_sc_entity}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Table Details & Mapping */}
          <div className="col-span-2">
            {selectedTable ? (
              <div className="space-y-4">
                <Card>
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <div>
                        <CardTitle>{selectedTable.table_name}</CardTitle>
                        <p className="text-sm text-muted-foreground">{selectedTable.description}</p>
                      </div>
                      <div className="flex gap-2">
                        {!selectedTable.is_standard && (
                          <Button
                            variant="outline"
                            onClick={() => handleAnalyzeZTable(selectedTable)}
                            disabled={mappingLoading}
                          >
                            <Zap className="h-4 w-4 mr-1" />
                            AI Analyze Z-Table
                          </Button>
                        )}
                        <Button
                          onClick={handleRunAIMapping}
                          disabled={mappingLoading}
                        >
                          {mappingLoading ? (
                            <Spinner size="sm" className="mr-2" />
                          ) : (
                            <Search className="h-4 w-4 mr-2" />
                          )}
                          AI Match Fields
                        </Button>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="text-sm font-medium">Target Autonomy SC Entity</label>
                        <NativeSelect
                          value={selectedTable.aws_sc_entity || ''}
                          onChange={() => {}}
                          className="mt-1"
                        >
                          <option value="">Select entity...</option>
                          <option value="product">Product</option>
                          <option value="site">Site</option>
                          <option value="inv_level">Inventory Level</option>
                          <option value="trading_partner">Trading Partner</option>
                          <option value="inbound_order">Inbound Order</option>
                          <option value="outbound_order">Outbound Order</option>
                          <option value="forecast">Forecast</option>
                        </NativeSelect>
                      </div>
                      <div>
                        <label className="text-sm font-medium">Extraction Mode</label>
                        <NativeSelect value="full" onChange={() => {}} className="mt-1">
                          <option value="full">Full Extract</option>
                          <option value="delta">Delta Extract</option>
                          <option value="incremental">Incremental</option>
                        </NativeSelect>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {/* AI Analysis Results (Z-tables) */}
                {selectedTable.analysis && (
                  <Card>
                    <CardContent className="py-4">
                      <div className="flex items-center gap-2 mb-3">
                        <Zap className="h-5 w-5 text-blue-500" />
                        <span className="font-medium">AI Analysis Results</span>
                      </div>
                      <div className="space-y-2">
                        <p className="text-sm">
                          <strong>Suggested Entity:</strong> {selectedTable.analysis.suggested_entity}
                          <span className="text-muted-foreground ml-2">
                            ({(selectedTable.analysis.entity_confidence * 100).toFixed(0)}% confidence)
                          </span>
                        </p>
                        {selectedTable.analysis.ai_purpose_analysis && (
                          <p className="text-sm">
                            <strong>Purpose:</strong> {selectedTable.analysis.ai_purpose_analysis}
                          </p>
                        )}
                        {selectedTable.analysis.ai_integration_guidance && (
                          <p className="text-sm">
                            <strong>Guidance:</strong> {selectedTable.analysis.ai_integration_guidance}
                          </p>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* Field Mappings */}
                <Card>
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-lg">
                        Field Mappings
                        {fieldMappings.length > 0 && (
                          <span className="text-sm font-normal text-muted-foreground ml-2">
                            ({mappedCount}/{fieldMappings.length} mapped)
                          </span>
                        )}
                      </CardTitle>
                    </div>
                  </CardHeader>
                  <CardContent className="p-0">
                    {mappingLoading ? (
                      <div className="flex justify-center py-8">
                        <Spinner size="sm" />
                        <span className="ml-2 text-sm text-muted-foreground">Analyzing fields...</span>
                      </div>
                    ) : fieldMappings.length === 0 ? (
                      <div className="py-8 text-center text-sm text-muted-foreground">
                        Click a table on the left to auto-detect fields and match them to Autonomy Supply Chain entities.
                      </div>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b bg-muted/50">
                              <th className="text-left py-2 px-3 font-medium">SAP Field</th>
                              <th className="text-left py-2 px-3 font-medium">Autonomy Entity</th>
                              <th className="text-left py-2 px-3 font-medium">Autonomy Field</th>
                              <th className="text-center py-2 px-3 font-medium">Confidence</th>
                              <th className="text-left py-2 px-3 font-medium">Source</th>
                            </tr>
                          </thead>
                          <tbody>
                            {fieldMappings.map((fm, idx) => (
                              <tr key={idx} className="border-b hover:bg-muted/30">
                                <td className="py-2 px-3">
                                  <span className="font-mono text-xs">{fm.sap_field}</span>
                                  {fm.is_z_field && (
                                    <Badge variant="outline" className="ml-1 text-[10px] py-0">Z</Badge>
                                  )}
                                  {fm.sap_field_description && fm.sap_field_description !== fm.sap_field && (
                                    <p className="text-[11px] text-muted-foreground truncate max-w-[180px]">
                                      {fm.sap_field_description}
                                    </p>
                                  )}
                                </td>
                                <td className="py-2 px-3">
                                  {fm.aws_sc_entity ? (
                                    <span className="text-xs">{fm.aws_sc_entity}</span>
                                  ) : (
                                    <span className="text-xs text-muted-foreground italic">unmapped</span>
                                  )}
                                </td>
                                <td className="py-2 px-3">
                                  {fm.aws_sc_field ? (
                                    <span className="font-mono text-xs">{fm.aws_sc_field}</span>
                                  ) : (
                                    <span className="text-xs text-muted-foreground">—</span>
                                  )}
                                </td>
                                <td className="py-2 px-3 text-center">
                                  {fm.confidence ? (
                                    <Badge variant={confidenceColor(fm.confidence)} className="text-[10px]">
                                      {fm.confidence} ({(fm.confidence_score * 100).toFixed(0)}%)
                                    </Badge>
                                  ) : (
                                    <span className="text-xs text-muted-foreground">—</span>
                                  )}
                                </td>
                                <td className="py-2 px-3">
                                  <span className="text-[11px] text-muted-foreground">{fm.match_source || '—'}</span>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>
            ) : (
              <Card>
                <CardContent className="py-12 text-center">
                  <ArrowUpDown className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
                  <p className="text-muted-foreground">Select a table to view and configure field mappings.</p>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

// Ingestion Jobs Tab Component
// Table classifications for phase-based filtering
const MASTER_DATA_PREFIXES = new Set([
  'T001', 'TJ02T', 'T001W', 'T001L', 'ADRC',
  'MARA', 'MAKT', 'MARC', 'MARM', 'MVKE',
  'LFA1', 'KNA1', 'CRHD', 'EQUI',
  'MBEW', 'MARD', 'EORD', 'EINA', 'EINE', 'EBAN',
  'STKO', 'STPO', 'PLKO', 'PLPO',
  'PBIM', 'PBED', 'PLAF',
]);
const TRANSACTION_PREFIXES = new Set([
  'EKKO', 'EKPO', 'EKET', 'VBAK', 'VBAP', 'VBUK', 'VBUP',
  'LIKP', 'LIPS', 'AFKO', 'AFPO', 'AFVC', 'RESB',
  'MKPF', 'MSEG', 'LTAK', 'LTAP',
  'JEST', 'QMEL', 'QALS', 'QASE',
]);

const getTablePrefix = (name) => {
  const upper = name.toUpperCase();
  // Handle multi-part prefixes like T001W_plant_data
  for (const prefix of ['T001W', 'T001L', 'TJ02T', 'T001']) {
    if (upper.startsWith(prefix + '_') || upper === prefix) return prefix;
  }
  const parts = upper.split('_');
  return parts[0];
};

const PHASE_LABELS = {
  master_data: 'Phase 1: Master Data → SC Config',
  cdc: 'Phase 2: CDC (Change Detection)',
  transaction: 'Phase 3: Transaction Import',
};

const PHASE_COLORS = {
  master_data: 'bg-blue-100 text-blue-800',
  cdc: 'bg-purple-100 text-purple-800',
  transaction: 'bg-amber-100 text-amber-800',
};

/** Geocoding progress bar with current address label on the right. */
const GeocodingProgressBar = ({ done, total, currentLabel }) => {
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  return (
    <div className="pl-8 pr-3 py-1.5 border-t bg-muted/30 space-y-1">
      <div className="h-1.5 bg-muted rounded-full overflow-hidden">
        <div
          className="h-full bg-emerald-500 transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>{done}/{total} locations</span>
        {currentLabel && <span className="truncate ml-2 italic">{currentLabel}</span>}
      </div>
    </div>
  );
};

const JobsTab = ({ jobs, connections = [], onCreateJob, onStartJob, onCancelJob, onDeleteJob, onRerunJob, onScheduleJob, onRefresh, loading }) => {
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [selectedConnectionId, setSelectedConnectionId] = useState('');
  const [jobType, setJobType] = useState('full_extract');
  const [jobPhase, setJobPhase] = useState('master_data');
  const [availableTables, setAvailableTables] = useState([]);
  const [allTables, setAllTables] = useState([]);
  const [selectedTables, setSelectedTables] = useState([]);
  const [loadingTables, setLoadingTables] = useState(false);
  const [identifiedFiles, setIdentifiedFiles] = useState(null); // null = not scanned, [] = empty
  const [scanningFiles, setScanningFiles] = useState(false);
  const [expandedJobs, setExpandedJobs] = useState({}); // { jobId: bool }

  // Scan files to identify SAP tables via the identify-files endpoint
  const handleScanFiles = async () => {
    if (!selectedConnectionId) return;
    setScanningFiles(true);
    setIdentifiedFiles(null);
    try {
      const resp = await api.post(`/sap-data/connections/${selectedConnectionId}/identify-files`);
      setIdentifiedFiles(resp.data || []);
    } catch (err) {
      console.error('Failed to identify files:', err);
      setIdentifiedFiles([]);
    }
    setScanningFiles(false);
  };

  // Toggle per-file list expansion on a job card
  const toggleJobExpanded = (jobId) => {
    setExpandedJobs(prev => ({ ...prev, [jobId]: !prev[jobId] }));
  };

  // Determine if a job's file list should be expanded by default
  const isJobExpanded = (job) => {
    if (expandedJobs[job.id] !== undefined) return expandedJobs[job.id];
    // Auto-collapse file list once all files are read (building phase)
    const tableStatuses = job.table_status ? Object.values(job.table_status) : [];
    const completedFiles = tableStatuses.filter(s => s.status === 'completed').length;
    const totalFiles = job.tables?.length || 0;
    const allFilesRead = totalFiles > 0 && completedFiles >= totalFiles;
    if (job.status === 'running' && allFilesRead) return false;
    return job.status === 'running';
  };

  // The 9 build steps from SAPConfigBuilder
  const BUILD_STEPS = [
    "Creating supply chain config",
    "Geocoding company addresses",
    "Creating sites from plants & storage locations",
    "Creating products from material master",
    "Creating trading partners & sourcing rules",
    "Building bill of materials",
    "Generating forecasts & inventory policies",
    "Importing orders & transactional data",
    "Inferring transportation lanes from sourcing & shipping data",
  ];

  // Filter tables by phase
  const filterTablesByPhase = (tables, phase) => {
    if (phase === 'master_data') {
      return tables.filter(t => MASTER_DATA_PREFIXES.has(getTablePrefix(t)));
    } else if (phase === 'transaction') {
      return tables.filter(t => TRANSACTION_PREFIXES.has(getTablePrefix(t)));
    }
    // CDC uses master data tables
    return tables.filter(t => MASTER_DATA_PREFIXES.has(getTablePrefix(t)));
  };

  // Load available CSV files / tables when connection changes
  const handleConnectionChange = async (connId) => {
    setSelectedConnectionId(connId);
    setSelectedTables([]);
    setAvailableTables([]);
    setAllTables([]);
    setIdentifiedFiles(null);
    if (!connId) return;

    const conn = connections.find(c => c.id === parseInt(connId));
    if (!conn) return;

    setLoadingTables(true);
    try {
      let allFiles = [];
      if (conn.connection_method === 'csv' && conn.csv_directory) {
        const basePath = '/app/imports';
        const subpath = conn.csv_directory.replace(basePath + '/', '').replace(basePath, '');
        const resp = await api.get('/sap-data/import-directories', { params: { subpath } });
        allFiles = resp.data.filter(e => !e.is_dir).map(e => e.name.replace('.csv', ''));
      } else {
        try {
          const resp = await api.get(`/sap-data/connections/${connId}/tables`);
          allFiles = resp.data.map(t => t.sap_table_name || t.name);
        } catch { allFiles = []; }
      }
      setAllTables(allFiles);
      const filtered = filterTablesByPhase(allFiles, jobPhase);
      setAvailableTables(filtered);
      setSelectedTables(filtered);
    } catch (err) {
      console.error('Failed to load tables:', err);
    }
    setLoadingTables(false);
  };

  // Re-filter tables when phase changes
  const handlePhaseChange = (phase) => {
    setJobPhase(phase);
    if (allTables.length > 0) {
      const filtered = filterTablesByPhase(allTables, phase);
      setAvailableTables(filtered);
      setSelectedTables(filtered);
    }
  };

  const handleSubmitJob = async () => {
    if (!selectedConnectionId || selectedTables.length === 0) return;
    await onCreateJob({
      connection_id: parseInt(selectedConnectionId),
      job_type: jobType,
      phase: jobPhase,
      tables: selectedTables,
    });
    setShowCreateDialog(false);
    setSelectedConnectionId('');
    setSelectedTables([]);
    setAvailableTables([]);
    setAllTables([]);
    setIdentifiedFiles(null);
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-semibold">Ingestion Jobs</h2>
        <div className="flex gap-2">
          <Button variant="outline" onClick={onRefresh}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
          <Button variant="outline" onClick={onScheduleJob}>
            <Clock className="h-4 w-4 mr-2" />
            Schedule
          </Button>
          <Button onClick={() => setShowCreateDialog(true)} disabled={connections.length === 0}>
            <Plus className="h-4 w-4 mr-2" />
            New Job
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Spinner size="lg" />
        </div>
      ) : jobs.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <Activity className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
            <p className="text-muted-foreground">No ingestion jobs yet.</p>
            <Button className="mt-4" onClick={() => setShowCreateDialog(true)}>
              Create Your First Job
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {jobs.map((job) => (
            <Card key={job.id}>
              <CardContent className="py-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className={cn(
                      "p-2 rounded-lg",
                      job.status === 'completed' || job.status === 'partial' ? "bg-green-100" :
                      job.status === 'running' ? "bg-blue-100" :
                      job.status === 'failed' ? "bg-red-100" :
                      job.status === 'cancelled' ? "bg-orange-100" : "bg-gray-100"
                    )}>
                      {job.status === 'running' ? (
                        <Spinner size="sm" />
                      ) : job.status === 'completed' || job.status === 'partial' ? (
                        <CheckCircle className="h-5 w-5 text-green-600" />
                      ) : job.status === 'failed' ? (
                        <AlertTriangle className="h-5 w-5 text-red-600" />
                      ) : job.status === 'cancelled' ? (
                        <AlertTriangle className="h-5 w-5 text-orange-500" />
                      ) : (
                        <Clock className="h-5 w-5 text-gray-400" />
                      )}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium">Job #{job.id}</span>
                        <Badge variant="outline">{job.job_type}</Badge>
                        <span className={cn("text-xs px-2 py-0.5 rounded-full font-medium", PHASE_COLORS[job.phase] || 'bg-gray-100 text-gray-800')}>
                          {PHASE_LABELS[job.phase] || job.phase}
                        </span>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        Tables: {job.tables?.join(', ')}
                      </p>
                      {job.config_id && (
                        <p className="text-sm text-green-600 font-medium mt-1">
                          SC Config #{job.config_id} generated
                          {job.build_summary?.sites && ` — ${job.build_summary.sites} sites, ${job.build_summary.products} products, ${job.build_summary.lanes} lanes`}
                          {job.build_summary?.cdc_result === 'no_changes' && ' — No topology changes detected'}
                          {job.build_summary?.cdc_result === 'changes_detected' && ` — Changes: +${job.build_summary.sites_added || 0} sites, +${job.build_summary.products_added || 0} products`}
                          {job.build_summary?.transaction_import && ` — Transactions imported`}
                        </p>
                      )}
                      {job.status === 'failed' && job.error_message && (
                        <p className="text-sm text-red-600 mt-1">
                          <span className="font-medium">Error:</span> {job.error_message}
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-lg font-medium">
                      {job.progress_percent?.toFixed(1)}%
                    </div>
                    <p className="text-sm text-muted-foreground">
                      {job.total_rows_processed?.toLocaleString()} rows processed
                    </p>
                    {job.total_rows_failed > 0 && (
                      <p className="text-sm text-red-500">
                        {job.total_rows_failed?.toLocaleString()} failed
                      </p>
                    )}
                  </div>
                </div>
                {/* Progress section */}
                {(() => {
                  const tableStatuses = job.table_status ? Object.values(job.table_status) : [];
                  const completedFiles = tableStatuses.filter(s => s.status === 'completed').length;
                  const totalFiles = job.tables?.length || 0;
                  const allFilesRead = totalFiles > 0 && completedFiles >= totalFiles;
                  const buildStep = job.build_summary?.build_step;
                  const buildTotal = job.build_summary?.build_total || 9;
                  const buildDesc = job.build_summary?.build_description;
                  const isBuilding = job.status === 'running' && allFilesRead;
                  const isReading = job.status === 'running' && !allFilesRead;

                  return (
                    <div className="mt-3 space-y-2">
                      {/* File reading progress */}
                      {isReading && (
                        <>
                          <div className="h-2 bg-muted rounded-full overflow-hidden">
                            <div
                              className="h-full bg-blue-500 transition-all"
                              style={{ width: `${job.progress_percent}%` }}
                            />
                          </div>
                          <p className="text-xs text-muted-foreground">
                            Reading files: {completedFiles}/{totalFiles} completed
                            {job.current_table && ` — ${job.current_table}`}
                          </p>
                          {/* Expandable file list while reading */}
                          <div>
                            <button
                              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                              onClick={() => toggleJobExpanded(job.id)}
                            >
                              {isJobExpanded(job)
                                ? <ChevronDown className="h-3.5 w-3.5" />
                                : <ChevronRight className="h-3.5 w-3.5" />}
                              Show files
                            </button>
                            {isJobExpanded(job) && (
                              <div className="mt-1 border rounded-lg overflow-hidden max-h-48 overflow-y-auto">
                                {(job.tables || []).map((tableName) => {
                                  const fileStatus = job.table_status?.[tableName];
                                  const status = fileStatus?.status || 'pending';
                                  const rows = fileStatus?.rows ?? 0;
                                  return (
                                    <div key={tableName} className="flex items-center gap-2 px-3 py-1 text-xs border-b last:border-b-0">
                                      {status === 'completed' ? <CheckCircle className="h-3.5 w-3.5 text-green-500 flex-shrink-0" />
                                        : status === 'in_progress' ? <Spinner size="sm" className="flex-shrink-0" />
                                        : status === 'failed' ? <AlertTriangle className="h-3.5 w-3.5 text-red-500 flex-shrink-0" />
                                        : <Clock className="h-3.5 w-3.5 text-gray-300 flex-shrink-0" />}
                                      <span className="flex-1 truncate font-mono">{tableName}</span>
                                      {rows > 0 && <span className="text-muted-foreground">{rows.toLocaleString()}</span>}
                                    </div>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        </>
                      )}

                      {/* All files read — collapsed summary + build progress */}
                      {isBuilding && (
                        <>
                          <div className="flex items-center gap-2 text-xs text-green-600">
                            <CheckCircle className="h-4 w-4" />
                            <span>{totalFiles} files read successfully ({job.total_rows_processed?.toLocaleString()} rows)</span>
                            <button
                              className="text-muted-foreground hover:text-foreground ml-1"
                              onClick={() => toggleJobExpanded(job.id)}
                            >
                              {isJobExpanded(job) ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                            </button>
                          </div>
                          {isJobExpanded(job) && (
                            <div className="border rounded-lg overflow-hidden max-h-48 overflow-y-auto">
                              {(job.tables || []).map((tableName) => {
                                const rows = job.table_status?.[tableName]?.rows ?? 0;
                                return (
                                  <div key={tableName} className="flex items-center gap-2 px-3 py-1 text-xs border-b last:border-b-0">
                                    <CheckCircle className="h-3.5 w-3.5 text-green-500 flex-shrink-0" />
                                    <span className="flex-1 truncate font-mono">{tableName}</span>
                                    {rows > 0 && <span className="text-muted-foreground">{rows.toLocaleString()}</span>}
                                  </div>
                                );
                              })}
                            </div>
                          )}
                          {/* Build steps checklist */}
                          <div className="border rounded-lg overflow-hidden">
                            {BUILD_STEPS.map((stepName, idx) => {
                              const stepNum = idx + 1;
                              const isCurrent = buildStep === stepNum;
                              const isDone = buildStep > stepNum;
                              const isPending = !buildStep || buildStep < stepNum;
                              return (
                                <React.Fragment key={stepNum}>
                                  <div className="flex items-center gap-2 px-3 py-1.5 text-xs border-b last:border-b-0">
                                    {isDone ? <CheckCircle className="h-3.5 w-3.5 text-green-500 flex-shrink-0" />
                                      : isCurrent ? <Spinner size="sm" className="flex-shrink-0" />
                                      : <Clock className="h-3.5 w-3.5 text-gray-300 flex-shrink-0" />}
                                    <span className={isCurrent ? 'font-medium' : isPending ? 'text-muted-foreground' : ''}>
                                      {stepName}
                                      {isCurrent && stepNum === 2 && job.build_summary?.geocoding_total > 0 && (
                                        <span className="text-muted-foreground font-normal ml-1">
                                          ({job.build_summary.geocoding_done || 0}/{job.build_summary.geocoding_total})
                                        </span>
                                      )}
                                    </span>
                                  </div>
                                  {/* Geocoding progress bar for step 2 */}
                                  {isCurrent && stepNum === 2 && job.build_summary?.geocoding_total > 0 && (
                                    <GeocodingProgressBar
                                      done={job.build_summary.geocoding_done || 0}
                                      total={job.build_summary.geocoding_total}
                                      currentLabel={job.build_summary.geocoding_addresses?.[job.build_summary.geocoding_active] || ''}
                                    />
                                  )}
                                </React.Fragment>
                              );
                            })}
                          </div>
                        </>
                      )}

                      {/* Completed/failed job — collapsed file summary */}
                      {job.status !== 'running' && totalFiles > 0 && (
                        <div>
                          <button
                            className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground"
                            onClick={() => toggleJobExpanded(job.id)}
                          >
                            {isJobExpanded(job)
                              ? <ChevronDown className="h-3.5 w-3.5" />
                              : <ChevronRight className="h-3.5 w-3.5" />}
                            <CheckCircle className="h-3.5 w-3.5 text-green-500" />
                            {completedFiles}/{totalFiles} files read
                          </button>
                          {isJobExpanded(job) && (
                            <div className="mt-1 border rounded-lg overflow-hidden max-h-48 overflow-y-auto">
                              {(job.tables || []).map((tableName) => {
                                const fileStatus = job.table_status?.[tableName];
                                const status = fileStatus?.status || 'completed';
                                const rows = fileStatus?.rows ?? 0;
                                return (
                                  <div key={tableName} className="flex items-center gap-2 px-3 py-1 text-xs border-b last:border-b-0">
                                    {status === 'failed'
                                      ? <AlertTriangle className="h-3.5 w-3.5 text-red-500 flex-shrink-0" />
                                      : <CheckCircle className="h-3.5 w-3.5 text-green-500 flex-shrink-0" />}
                                    <span className="flex-1 truncate font-mono">{tableName}</span>
                                    {rows > 0 && <span className="text-muted-foreground">{rows.toLocaleString()}</span>}
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })()}
                <div className="flex items-center gap-2 border-t pt-3 mt-3">
                  {job.status === 'pending' && (
                    <Button variant="outline" size="sm" onClick={() => onStartJob(job.id)}>
                      <Play className="h-4 w-4 mr-1" />
                      Run
                    </Button>
                  )}
                  {job.status === 'running' && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-orange-600 hover:bg-orange-50 border-orange-200"
                      onClick={() => {
                        if (window.confirm(`Cancel running Job #${job.id}?`)) {
                          onCancelJob(job.id);
                        }
                      }}
                    >
                      Cancel
                    </Button>
                  )}
                  {(job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled') && (
                    <Button variant="outline" size="sm" onClick={() => onStartJob(job.id)}>
                      <RefreshCw className="h-4 w-4 mr-1" />
                      Re-run
                    </Button>
                  )}
                  {job.duration_seconds != null && job.duration_seconds > 0 && (
                    <span className="text-xs text-muted-foreground">
                      {job.duration_seconds < 60
                        ? `${job.duration_seconds.toFixed(1)}s`
                        : `${(job.duration_seconds / 60).toFixed(1)}m`}
                    </span>
                  )}
                  <div className="flex-1" />
                  {job.status !== 'running' && (
                    <>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          if (window.confirm(`Rerun Job #${job.id}? All stats will be reset.`)) {
                            onRerunJob(job.id);
                          }
                        }}
                      >
                        <RefreshCw className="h-4 w-4 mr-1" />
                        Rerun
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="text-red-600 hover:bg-red-50 border-red-200"
                        onClick={() => {
                          if (window.confirm(`Delete Job #${job.id}?`)) {
                            onDeleteJob(job.id);
                          }
                        }}
                      >
                        <Trash2 className="h-4 w-4 mr-1" />
                        Delete
                      </Button>
                    </>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create Job Dialog */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Create Ingestion Job</DialogTitle>
            <DialogDescription>
              Import data from an SAP connection into the platform.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <label className="block text-sm font-medium mb-1">Connection *</label>
              <NativeSelect
                value={selectedConnectionId}
                onChange={(e) => handleConnectionChange(e.target.value)}
              >
                <option value="">Select a connection...</option>
                {connections.map((conn) => (
                  <option key={conn.id} value={conn.id}>
                    {conn.name} ({conn.connection_method})
                  </option>
                ))}
              </NativeSelect>
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">Ingestion Phase *</label>
              <NativeSelect value={jobPhase} onChange={(e) => handlePhaseChange(e.target.value)}>
                <option value="master_data">Phase 1: Master Data → Generate SC Config</option>
                <option value="cdc">Phase 2: CDC — Detect Master Data Changes</option>
                <option value="transaction">Phase 3: Transaction Data Import</option>
              </NativeSelect>
              <p className="text-xs text-muted-foreground mt-1">
                {jobPhase === 'master_data' && 'Imports master data (sites, products, BOMs, etc.) and generates a new Supply Chain Config.'}
                {jobPhase === 'cdc' && 'Compares master data against the active SC Config. Creates a child config if topology changed.'}
                {jobPhase === 'transaction' && 'Imports transaction data (orders, production, inventory movements) against the active SC Config.'}
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">Job Type</label>
              <NativeSelect value={jobType} onChange={(e) => setJobType(e.target.value)}>
                <option value="full_extract">Full Extract</option>
                <option value="delta_extract">Delta Extract</option>
                <option value="incremental">Incremental</option>
              </NativeSelect>
            </div>

            {selectedConnectionId && (
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="block text-sm font-medium">
                    Tables {loadingTables ? '(loading...)' : `(${selectedTables.length}/${availableTables.length} selected)`}
                  </label>
                  {availableTables.length > 0 && (
                    <div className="flex gap-2">
                      <button className="text-xs text-blue-600 hover:underline" onClick={() => setSelectedTables([...availableTables])}>
                        Select All
                      </button>
                      <button className="text-xs text-blue-600 hover:underline" onClick={() => setSelectedTables([])}>
                        Clear
                      </button>
                    </div>
                  )}
                </div>
                <div className="border rounded-lg max-h-56 overflow-y-auto">
                  {availableTables.length === 0 && !loadingTables ? (
                    <p className="px-3 py-4 text-sm text-muted-foreground text-center">
                      No tables found. Check connection configuration.
                    </p>
                  ) : availableTables.map((table) => (
                    <label key={table} className="flex items-center gap-2 px-3 py-1.5 hover:bg-muted cursor-pointer text-sm">
                      <input
                        type="checkbox"
                        checked={selectedTables.includes(table)}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setSelectedTables([...selectedTables, table]);
                          } else {
                            setSelectedTables(selectedTables.filter(t => t !== table));
                          }
                        }}
                      />
                      {table}
                    </label>
                  ))}
                </div>
              </div>
            )}

            {/* Scan Files / File Identification */}
            {selectedConnectionId && (
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="block text-sm font-medium">File Identification</label>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleScanFiles}
                    disabled={scanningFiles}
                  >
                    {scanningFiles ? (
                      <>
                        <Spinner size="sm" className="mr-1" />
                        Scanning...
                      </>
                    ) : (
                      <>
                        <Search className="h-3 w-3 mr-1" />
                        Scan Files
                      </>
                    )}
                  </Button>
                </div>
                {identifiedFiles && identifiedFiles.length > 0 && (
                  <div className="border rounded-lg max-h-48 overflow-y-auto">
                    <table className="w-full text-sm">
                      <thead className="bg-muted sticky top-0">
                        <tr>
                          <th className="text-left px-3 py-1.5 font-medium">Filename</th>
                          <th className="text-left px-3 py-1.5 font-medium">SAP Table</th>
                          <th className="text-center px-3 py-1.5 font-medium">Confidence</th>
                          <th className="text-right px-3 py-1.5 font-medium">Rows</th>
                        </tr>
                      </thead>
                      <tbody>
                        {identifiedFiles.map((file, idx) => (
                          <tr key={idx} className="border-t hover:bg-muted/50">
                            <td className="px-3 py-1.5 truncate max-w-[160px]" title={file.filename}>
                              {file.filename}
                            </td>
                            <td className="px-3 py-1.5">
                              {(file.confidence ?? 0) < 0.3 ? (
                                <span className="text-muted-foreground italic">Unknown</span>
                              ) : (
                                file.sap_table || file.table_name || 'Unknown'
                              )}
                            </td>
                            <td className="px-3 py-1.5 text-center">
                              <Badge variant={
                                (file.confidence ?? 0) > 0.7 ? 'success' :
                                (file.confidence ?? 0) >= 0.3 ? 'warning' : 'destructive'
                              }>
                                {((file.confidence ?? 0) * 100).toFixed(0)}%
                              </Badge>
                            </td>
                            <td className="px-3 py-1.5 text-right text-muted-foreground">
                              {file.row_count?.toLocaleString() ?? '-'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {identifiedFiles && identifiedFiles.length === 0 && (
                  <p className="text-sm text-muted-foreground mt-1">
                    No files could be identified. Check your connection configuration.
                  </p>
                )}
              </div>
            )}
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setShowCreateDialog(false)}>Cancel</Button>
            <Button
              onClick={handleSubmitJob}
              disabled={!selectedConnectionId || selectedTables.length === 0}
            >
              {jobPhase === 'master_data' ? 'Create & Build SC Config' :
               jobPhase === 'cdc' ? 'Run Change Detection' :
               'Import Transactions'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

// Geography Geocoding Card
const GeographyGeocoding = () => {
  const [status, setStatus] = useState(null);
  const [geocoding, setGeocoding] = useState(false);
  const [result, setResult] = useState(null);

  const loadStatus = useCallback(async () => {
    try {
      const res = await api.get('/sap-data/geography/status');
      setStatus(res.data);
    } catch (err) {
      console.error('Failed to load geography status:', err);
    }
  }, []);

  useEffect(() => { loadStatus(); }, [loadStatus]);

  const handleGeocode = async () => {
    setGeocoding(true);
    setResult(null);
    try {
      const res = await api.post('/sap-data/geography/geocode');
      setResult(res.data);
      loadStatus();
    } catch (err) {
      console.error('Geocoding failed:', err);
      setResult({ error: err.response?.data?.detail || 'Geocoding failed' });
    } finally {
      setGeocoding(false);
    }
  };

  if (!status) return null;
  if (status.total === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <MapPin className="h-4 w-4" />
          Geography Coordinates
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center gap-4 text-sm">
          <span>{status.with_coordinates} / {status.total} sites have coordinates</span>
          {status.missing_coordinates > 0 && (
            <Badge variant="warning">{status.missing_coordinates} missing</Badge>
          )}
          {status.missing_coordinates === 0 && (
            <Badge variant="outline" className="text-green-600 border-green-300">All geocoded</Badge>
          )}
        </div>
        {status.missing_coordinates > 0 && (
          <div className="flex items-center gap-3">
            <button
              className="px-4 py-2 text-sm font-medium bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50"
              onClick={handleGeocode}
              disabled={geocoding}
            >
              {geocoding ? 'Geocoding...' : `Geocode ${status.missing_coordinates} addresses`}
            </button>
            <span className="text-xs text-muted-foreground">
              Uses OpenStreetMap (~1 sec/address)
            </span>
          </div>
        )}
        {result && !result.error && (
          <div className="text-sm text-green-600">
            {result.message}
            {result.failed?.length > 0 && (
              <div className="mt-1 text-yellow-600">
                Failed: {result.failed.map(f => f.city || f.id).join(', ')}
              </div>
            )}
          </div>
        )}
        {result?.error && (
          <div className="text-sm text-red-600">{result.error}</div>
        )}
      </CardContent>
    </Card>
  );
};

// Insights & Actions Tab Component
const InsightsTab = ({ insights, actions, onAcknowledge, onUpdateAction, loading }) => {
  const [activeSubTab, setActiveSubTab] = useState('insights');

  return (
    <div className="space-y-6">
      <GeographyGeocoding />
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-4">
          <h2 className="text-xl font-semibold">Insights & Actions</h2>
          <div className="flex border rounded-lg overflow-hidden">
            <button
              className={cn(
                "px-4 py-2 text-sm font-medium transition-colors",
                activeSubTab === 'insights' ? "bg-primary text-primary-foreground" : "bg-background hover:bg-muted"
              )}
              onClick={() => setActiveSubTab('insights')}
            >
              <Lightbulb className="h-4 w-4 inline mr-2" />
              Insights ({insights.length})
            </button>
            <button
              className={cn(
                "px-4 py-2 text-sm font-medium transition-colors",
                activeSubTab === 'actions' ? "bg-primary text-primary-foreground" : "bg-background hover:bg-muted"
              )}
              onClick={() => setActiveSubTab('actions')}
            >
              <Wrench className="h-4 w-4 inline mr-2" />
              Actions ({actions.length})
            </button>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Spinner size="lg" />
        </div>
      ) : activeSubTab === 'insights' ? (
        <div className="space-y-4">
          {insights.length === 0 ? (
            <Card>
              <CardContent className="py-12 text-center">
                <CheckCircle className="h-12 w-12 mx-auto mb-4 text-green-500" />
                <p className="text-muted-foreground">No active insights. Everything looks good!</p>
              </CardContent>
            </Card>
          ) : (
            insights.map((insight) => (
              <Card key={insight.id} className={cn(
                "border-l-4",
                insight.severity === 'critical' ? "border-l-red-500" :
                insight.severity === 'error' ? "border-l-orange-500" :
                insight.severity === 'warning' ? "border-l-yellow-500" : "border-l-blue-500"
              )}>
                <CardContent className="py-4">
                  <div className="flex items-start justify-between">
                    <div className="flex items-start gap-3">
                      <div className={cn(
                        "p-2 rounded-lg mt-0.5",
                        insight.severity === 'critical' ? "bg-red-100" :
                        insight.severity === 'error' ? "bg-orange-100" :
                        insight.severity === 'warning' ? "bg-yellow-100" : "bg-blue-100"
                      )}>
                        {insight.severity === 'critical' || insight.severity === 'error' ? (
                          <AlertTriangle className={cn(
                            "h-5 w-5",
                            insight.severity === 'critical' ? "text-red-600" : "text-orange-600"
                          )} />
                        ) : (
                          <Lightbulb className={cn(
                            "h-5 w-5",
                            insight.severity === 'warning' ? "text-yellow-600" : "text-blue-600"
                          )} />
                        )}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="font-medium">{insight.title}</h3>
                          <Badge variant="outline" className="text-xs">{insight.category}</Badge>
                        </div>
                        <p className="text-sm text-muted-foreground mt-1">
                          {insight.description}
                        </p>
                        {insight.affected_entity && (
                          <p className="text-xs text-muted-foreground mt-2">
                            Affected: {insight.affected_entity}
                            {insight.affected_table && ` / ${insight.affected_table}`}
                          </p>
                        )}
                        {insight.suggested_actions?.length > 0 && (
                          <div className="mt-3 flex gap-2">
                            {insight.suggested_actions.map((action, idx) => (
                              <Button key={idx} variant="outline" size="sm">
                                {action.title}
                              </Button>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                    {!insight.is_acknowledged && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onAcknowledge(insight.id)}
                      >
                        Acknowledge
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </div>
      ) : (
        <div className="space-y-4">
          {actions.length === 0 ? (
            <Card>
              <CardContent className="py-12 text-center">
                <CheckCircle className="h-12 w-12 mx-auto mb-4 text-green-500" />
                <p className="text-muted-foreground">No pending actions.</p>
              </CardContent>
            </Card>
          ) : (
            actions.map((action) => (
              <Card key={action.id}>
                <CardContent className="py-4">
                  <div className="flex items-start justify-between">
                    <div className="flex items-start gap-3">
                      <div className="p-2 rounded-lg bg-purple-100 mt-0.5">
                        <Wrench className="h-5 w-5 text-purple-600" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="font-medium">{action.title}</h3>
                          <Badge variant="outline" className="text-xs">{action.action_type}</Badge>
                          <Badge variant={
                            action.status === 'completed' ? 'success' :
                            action.status === 'in_progress' ? 'default' :
                            action.status === 'dismissed' ? 'secondary' : 'warning'
                          } className="text-xs">
                            {action.status}
                          </Badge>
                        </div>
                        <p className="text-sm text-muted-foreground mt-1">
                          {action.description}
                        </p>
                        {action.affected_entity && (
                          <p className="text-xs text-muted-foreground mt-2">
                            Affected: {action.affected_entity}
                            {action.affected_table && ` / ${action.affected_table}`}
                          </p>
                        )}
                      </div>
                    </div>
                    {action.status === 'suggested' && (
                      <div className="flex gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => onUpdateAction(action.id, 'dismissed')}
                        >
                          Dismiss
                        </Button>
                        <Button
                          size="sm"
                          onClick={() => onUpdateAction(action.id, 'in_progress')}
                        >
                          Start
                        </Button>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </div>
      )}
    </div>
  );
};

// User Import Tab Component
const UserImportTab = () => {
  const [roleMappings, setRoleMappings] = useState([]);
  const [importLogs, setImportLogs] = useState([]);
  const [scFilterConfig, setScFilterConfig] = useState(null);
  const [previewData, setPreviewData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [showAddMapping, setShowAddMapping] = useState(false);
  const [csvFiles, setCsvFiles] = useState({});

  // New mapping form
  const [newMapping, setNewMapping] = useState({
    agr_name_pattern: '',
    pattern_type: 'glob',
    powell_role: 'MPS_MANAGER',
    priority: 100,
    description: '',
  });

  const powellRoles = [
    'SC_VP', 'SOP_DIRECTOR', 'MPS_MANAGER', 'PO_ANALYST', 'ALLOCATION_MANAGER',
  ];

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [mappingsRes, logsRes, filterRes] = await Promise.all([
        api.get('/sap-data/user-import/role-mappings'),
        api.get('/sap-data/user-import/logs?limit=10'),
        api.get('/sap-data/user-import/sc-filter-config'),
      ]);
      setRoleMappings(mappingsRes.data || []);
      setImportLogs(logsRes.data?.items || []);
      setScFilterConfig(filterRes.data);
    } catch (err) {
      console.error('Failed to load user import data:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleAddMapping = async () => {
    try {
      await api.post('/sap-data/user-import/role-mappings', newMapping);
      setShowAddMapping(false);
      setNewMapping({ agr_name_pattern: '', pattern_type: 'glob', powell_role: 'MPS_MANAGER', priority: 100, description: '' });
      loadData();
    } catch (err) {
      console.error('Failed to create mapping:', err);
    }
  };

  const handleDeleteMapping = async (id) => {
    try {
      await api.delete(`/sap-data/user-import/role-mappings/${id}`);
      loadData();
    } catch (err) {
      console.error('Failed to delete mapping:', err);
    }
  };

  const handleFileChange = (tableName, file) => {
    setCsvFiles(prev => ({ ...prev, [tableName]: file }));
  };

  const parseCSV = (text) => {
    const lines = text.trim().split('\n');
    if (lines.length < 2) return [];
    const headers = lines[0].split(',').map(h => h.trim().toUpperCase());
    return lines.slice(1).map(line => {
      const values = line.split(',').map(v => v.trim());
      const row = {};
      headers.forEach((h, i) => { row[h] = values[i] || ''; });
      return row;
    });
  };

  const buildRawData = async () => {
    const tables = ['usr02', 'usr21', 'adrp', 'agr_users', 'agr_define', 'agr_1251', 'agr_tcodes'];
    const raw = {};
    for (const t of tables) {
      if (csvFiles[t]) {
        const text = await csvFiles[t].text();
        raw[t] = parseCSV(text);
      } else {
        raw[t] = [];
      }
    }
    return raw;
  };

  const handlePreview = async () => {
    setUploading(true);
    try {
      const rawData = await buildRawData();
      const res = await api.post('/sap-data/user-import/preview', rawData);
      setPreviewData(res.data);
    } catch (err) {
      console.error('Preview failed:', err);
    } finally {
      setUploading(false);
    }
  };

  const handleExecute = async () => {
    if (!window.confirm(`This will create/update ${previewData?.sc_eligible_users || 0} users. Continue?`)) return;
    setUploading(true);
    try {
      const rawData = await buildRawData();
      await api.post('/sap-data/user-import/execute', rawData);
      setPreviewData(null);
      setCsvFiles({});
      loadData();
    } catch (err) {
      console.error('Import failed:', err);
    } finally {
      setUploading(false);
    }
  };

  const csvTableDefs = [
    { key: 'usr02', label: 'USR02 (User Logon)', required: true },
    { key: 'agr_users', label: 'AGR_USERS (Role Assignments)', required: true },
    { key: 'usr21', label: 'USR21 (Name/Address Key)', required: false },
    { key: 'adrp', label: 'ADRP (Person Data)', required: false },
    { key: 'agr_define', label: 'AGR_DEFINE (Role Definitions)', required: false },
    { key: 'agr_1251', label: 'AGR_1251 (Auth Values)', required: false },
    { key: 'agr_tcodes', label: 'AGR_TCODES (Transaction Codes)', required: false },
  ];

  if (loading) {
    return <div className="flex justify-center py-12"><Spinner size="lg" /></div>;
  }

  return (
    <div className="space-y-6">
      {/* Role Mapping Rules */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5" />
              Role Mapping Rules
            </CardTitle>
            <Button size="sm" onClick={() => setShowAddMapping(true)}>
              <Plus className="h-4 w-4 mr-1" /> Add Rule
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground mb-4">
            Map SAP role patterns (AGR_NAME) to platform roles. Rules are evaluated by priority (lower = first match wins).
          </p>
          {roleMappings.length === 0 ? (
            <p className="text-muted-foreground text-sm italic">
              No custom rules. Heuristic fallback will be used.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-2 px-3">Pattern</th>
                    <th className="text-left py-2 px-3">Type</th>
                    <th className="text-left py-2 px-3">Platform Role</th>
                    <th className="text-left py-2 px-3">Priority</th>
                    <th className="text-left py-2 px-3">Description</th>
                    <th className="py-2 px-3"></th>
                  </tr>
                </thead>
                <tbody>
                  {roleMappings.map(m => (
                    <tr key={m.id} className="border-b hover:bg-muted/50">
                      <td className="py-2 px-3 font-mono text-xs">{m.agr_name_pattern}</td>
                      <td className="py-2 px-3"><Badge variant="outline">{m.pattern_type}</Badge></td>
                      <td className="py-2 px-3"><Badge>{m.powell_role}</Badge></td>
                      <td className="py-2 px-3">{m.priority}</td>
                      <td className="py-2 px-3 text-muted-foreground">{m.description || '—'}</td>
                      <td className="py-2 px-3">
                        <Button variant="ghost" size="sm" onClick={() => handleDeleteMapping(m.id)}>
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Add Mapping Dialog */}
          <Dialog open={showAddMapping} onOpenChange={setShowAddMapping}>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Add Role Mapping Rule</DialogTitle>
                <DialogDescription>
                  Map a SAP role name pattern to a platform role.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4 mt-4">
                <div>
                  <label className="text-sm font-medium">AGR_NAME Pattern</label>
                  <Input
                    value={newMapping.agr_name_pattern}
                    onChange={e => setNewMapping(p => ({ ...p, agr_name_pattern: e.target.value }))}
                    placeholder="*SC_VP*"
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm font-medium">Pattern Type</label>
                    <NativeSelect
                      value={newMapping.pattern_type}
                      onChange={e => setNewMapping(p => ({ ...p, pattern_type: e.target.value }))}
                    >
                      <option value="glob">Glob</option>
                      <option value="regex">Regex</option>
                    </NativeSelect>
                  </div>
                  <div>
                    <label className="text-sm font-medium">Platform Role</label>
                    <NativeSelect
                      value={newMapping.powell_role}
                      onChange={e => setNewMapping(p => ({ ...p, powell_role: e.target.value }))}
                    >
                      {powellRoles.map(r => <option key={r} value={r}>{r}</option>)}
                    </NativeSelect>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm font-medium">Priority</label>
                    <Input
                      type="number"
                      value={newMapping.priority}
                      onChange={e => setNewMapping(p => ({ ...p, priority: parseInt(e.target.value) || 100 }))}
                    />
                  </div>
                  <div>
                    <label className="text-sm font-medium">Description</label>
                    <Input
                      value={newMapping.description}
                      onChange={e => setNewMapping(p => ({ ...p, description: e.target.value }))}
                      placeholder="Optional"
                    />
                  </div>
                </div>
                <div className="flex justify-end gap-2 pt-2">
                  <Button variant="outline" onClick={() => setShowAddMapping(false)}>Cancel</Button>
                  <Button onClick={handleAddMapping} disabled={!newMapping.agr_name_pattern}>Save</Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>
        </CardContent>
      </Card>

      {/* CSV Upload & Preview */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Upload className="h-5 w-5" />
            Data Upload & Preview
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground mb-4">
            Upload SAP user/role CSV extracts. USR02 and AGR_USERS are required; others improve accuracy.
          </p>
          <div className="grid grid-cols-2 gap-3 mb-4">
            {csvTableDefs.map(t => (
              <div key={t.key} className="flex items-center gap-2">
                <label className="text-sm w-64 flex items-center gap-1">
                  {t.label}
                  {t.required && <span className="text-destructive">*</span>}
                </label>
                <input
                  type="file"
                  accept=".csv"
                  className="text-sm"
                  onChange={e => handleFileChange(t.key, e.target.files[0])}
                />
                {csvFiles[t.key] && <CheckCircle className="h-4 w-4 text-green-600" />}
              </div>
            ))}
          </div>

          <div className="flex gap-2">
            <Button
              onClick={handlePreview}
              disabled={uploading || !csvFiles.usr02 || !csvFiles.agr_users}
            >
              {uploading ? <Spinner size="sm" className="mr-2" /> : <Eye className="h-4 w-4 mr-1" />}
              Preview Import
            </Button>
            {previewData && (
              <Button variant="default" onClick={handleExecute} disabled={uploading}>
                {uploading ? <Spinner size="sm" className="mr-2" /> : <Play className="h-4 w-4 mr-1" />}
                Execute Import ({previewData.sc_eligible_users} users)
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Preview Results */}
      {previewData && (
        <Card>
          <CardHeader>
            <CardTitle>Preview Results</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-4 gap-4 mb-4">
              <div className="text-center p-3 rounded bg-muted">
                <div className="text-2xl font-bold">{previewData.total_users}</div>
                <div className="text-xs text-muted-foreground">Total SAP Users</div>
              </div>
              <div className="text-center p-3 rounded bg-blue-50 dark:bg-blue-950">
                <div className="text-2xl font-bold text-blue-600">{previewData.sc_eligible_users}</div>
                <div className="text-xs text-muted-foreground">SC Eligible</div>
              </div>
              <div className="text-center p-3 rounded bg-green-50 dark:bg-green-950">
                <div className="text-2xl font-bold text-green-600">
                  {previewData.preview_rows?.filter(r => r.action === 'create').length || 0}
                </div>
                <div className="text-xs text-muted-foreground">To Create</div>
              </div>
              <div className="text-center p-3 rounded bg-yellow-50 dark:bg-yellow-950">
                <div className="text-2xl font-bold text-yellow-600">
                  {previewData.preview_rows?.filter(r => r.action === 'update').length || 0}
                </div>
                <div className="text-xs text-muted-foreground">To Update</div>
              </div>
            </div>

            {previewData.unmapped_roles?.length > 0 && (
              <Alert className="mb-4">
                <AlertTriangle className="h-4 w-4" />
                <AlertDescription>
                  {previewData.unmapped_roles.length} SAP roles have no mapping rule (using heuristic fallback):
                  <span className="font-mono text-xs ml-1">{previewData.unmapped_roles.slice(0, 5).join(', ')}</span>
                  {previewData.unmapped_roles.length > 5 && ` +${previewData.unmapped_roles.length - 5} more`}
                </AlertDescription>
              </Alert>
            )}

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-2 px-2">SAP Username</th>
                    <th className="text-left py-2 px-2">Name</th>
                    <th className="text-left py-2 px-2">Email</th>
                    <th className="text-left py-2 px-2">SC Roles</th>
                    <th className="text-left py-2 px-2">Platform Role</th>
                    <th className="text-left py-2 px-2">Site Scope</th>
                    <th className="text-left py-2 px-2">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {(previewData.preview_rows || []).map((row, i) => (
                    <tr key={i} className="border-b hover:bg-muted/50">
                      <td className="py-2 px-2 font-mono text-xs">{row.sap_username}</td>
                      <td className="py-2 px-2">{row.full_name}</td>
                      <td className="py-2 px-2 text-xs">{row.email}</td>
                      <td className="py-2 px-2 text-xs">
                        {row.sc_roles?.slice(0, 2).map((r, j) => (
                          <Badge key={j} variant="outline" className="mr-1 mb-1">{r}</Badge>
                        ))}
                        {row.sc_roles?.length > 2 && <span className="text-muted-foreground">+{row.sc_roles.length - 2}</span>}
                      </td>
                      <td className="py-2 px-2"><Badge>{row.proposed_powell_role}</Badge></td>
                      <td className="py-2 px-2 text-xs">
                        {row.proposed_site_scope ? row.proposed_site_scope.join(', ') : 'All'}
                      </td>
                      <td className="py-2 px-2">
                        <Badge variant={row.action === 'create' ? 'default' : 'secondary'}>
                          {row.action}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Import History */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Clock className="h-5 w-5" />
            Import History
          </CardTitle>
        </CardHeader>
        <CardContent>
          {importLogs.length === 0 ? (
            <p className="text-muted-foreground text-sm italic">No imports yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-2 px-2">Date</th>
                    <th className="text-left py-2 px-2">Discovered</th>
                    <th className="text-left py-2 px-2">SC Eligible</th>
                    <th className="text-left py-2 px-2">Created</th>
                    <th className="text-left py-2 px-2">Updated</th>
                    <th className="text-left py-2 px-2">Skipped</th>
                    <th className="text-left py-2 px-2">Failed</th>
                    <th className="text-left py-2 px-2">Duration</th>
                  </tr>
                </thead>
                <tbody>
                  {importLogs.map(log => (
                    <tr key={log.id} className="border-b hover:bg-muted/50">
                      <td className="py-2 px-2 text-xs">
                        {log.started_at ? new Date(log.started_at).toLocaleString() : '—'}
                      </td>
                      <td className="py-2 px-2">{log.users_discovered}</td>
                      <td className="py-2 px-2 font-medium text-blue-600">{log.users_sc_eligible}</td>
                      <td className="py-2 px-2 text-green-600">{log.users_created}</td>
                      <td className="py-2 px-2 text-yellow-600">{log.users_updated}</td>
                      <td className="py-2 px-2 text-muted-foreground">{log.users_skipped}</td>
                      <td className="py-2 px-2 text-destructive">{log.users_failed}</td>
                      <td className="py-2 px-2 text-xs">{log.duration_seconds ? `${log.duration_seconds}s` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* SC Filter Reference */}
      {scFilterConfig && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5" />
              SC Relevance Filter
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground mb-3">
              Only SAP users whose roles contain these authorization objects or transaction codes are imported.
            </p>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <h4 className="text-sm font-medium mb-2">Authorization Objects ({scFilterConfig.auth_objects?.length})</h4>
                <div className="flex flex-wrap gap-1">
                  {scFilterConfig.auth_objects?.map(o => (
                    <Badge key={o} variant="outline" className="text-xs font-mono">{o}</Badge>
                  ))}
                </div>
              </div>
              <div>
                <h4 className="text-sm font-medium mb-2">Transaction Codes ({scFilterConfig.transaction_codes?.length})</h4>
                <div className="flex flex-wrap gap-1">
                  {scFilterConfig.transaction_codes?.map(t => (
                    <Badge key={t} variant="outline" className="text-xs font-mono">{t}</Badge>
                  ))}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

// Staging & Sync Tab
const StagingTab = ({ connections }) => {
  const [selectedConnectionId, setSelectedConnectionId] = useState('');
  const [selectedConfigId, setSelectedConfigId] = useState('');
  const [configs, setConfigs] = useState([]);
  const [running, setRunning] = useState(false);
  const [reconciling, setReconciling] = useState(false);
  const [result, setResult] = useState(null);
  const [reconcileResult, setReconcileResult] = useState(null);
  const [error, setError] = useState(null);
  const [history, setHistory] = useState([]);

  // Load supply chain configs
  useEffect(() => {
    api.get('/supply-chain-configs').then(res => {
      const list = Array.isArray(res.data) ? res.data : res.data?.configs || [];
      setConfigs(list);
      if (list.length > 0 && !selectedConfigId) setSelectedConfigId(String(list[0].id));
    }).catch(() => {});
  }, []);

  // Auto-select first connection
  useEffect(() => {
    if (connections.length > 0 && !selectedConnectionId) {
      setSelectedConnectionId(String(connections[0].id));
    }
  }, [connections]);

  const handleRunStaging = async () => {
    if (!selectedConnectionId || !selectedConfigId) return;
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.post('/sap-data/staging/run', {
        connection_id: parseInt(selectedConnectionId),
        config_id: parseInt(selectedConfigId),
      });
      setResult(res.data);
      setHistory(prev => [{ ...res.data, timestamp: new Date().toISOString() }, ...prev].slice(0, 10));
    } catch (err) {
      setError(err.response?.data?.detail || 'Staging pipeline failed');
    }
    setRunning(false);
  };

  const handleReconcile = async () => {
    if (!selectedConnectionId || !selectedConfigId) return;
    setReconciling(true);
    setError(null);
    setReconcileResult(null);
    try {
      const res = await api.post('/sap-data/staging/reconcile', {
        connection_id: parseInt(selectedConnectionId),
        config_id: parseInt(selectedConfigId),
      });
      setReconcileResult(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Reconciliation failed');
    }
    setReconciling(false);
  };

  const entityResults = result?.entities || {};
  const reconData = reconcileResult?.reconciliation || reconcileResult || {};

  return (
    <div className="space-y-6">
      {/* Controls */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <RefreshCw className="h-5 w-5" />
            SAP → AWS SC Staging Pipeline
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground mb-4">
            Extract data from SAP, map to AWS Supply Chain entities, and upsert into the operational database.
            Automated sync runs every 6 hours with daily reconciliation at 01:00.
          </p>
          <div className="flex flex-wrap items-end gap-4">
            <div className="min-w-[200px]">
              <label className="text-sm font-medium mb-1 block">SAP Connection</label>
              <NativeSelect value={selectedConnectionId} onChange={e => setSelectedConnectionId(e.target.value)}>
                <option value="">Select connection...</option>
                {connections.map(c => (
                  <option key={c.id} value={String(c.id)}>{c.name} ({c.system_type})</option>
                ))}
              </NativeSelect>
            </div>
            <div className="min-w-[200px]">
              <label className="text-sm font-medium mb-1 block">Target Config</label>
              <NativeSelect value={selectedConfigId} onChange={e => setSelectedConfigId(e.target.value)}>
                <option value="">Select config...</option>
                {configs.map(c => (
                  <option key={c.id} value={String(c.id)}>{c.name}</option>
                ))}
              </NativeSelect>
            </div>
            <Button onClick={handleRunStaging} disabled={running || !selectedConnectionId || !selectedConfigId}>
              {running ? <><Spinner className="h-4 w-4 mr-2" /> Running...</> : <><Play className="h-4 w-4 mr-2" /> Run Staging</>}
            </Button>
            <Button variant="outline" onClick={handleReconcile} disabled={reconciling || !selectedConnectionId || !selectedConfigId}>
              {reconciling ? <><Spinner className="h-4 w-4 mr-2" /> Checking...</> : <><ArrowUpDown className="h-4 w-4 mr-2" /> Reconcile</>}
            </Button>
          </div>
          {error && (
            <Alert variant="destructive" className="mt-4">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>

      {/* Staging Results */}
      {Object.keys(entityResults).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CheckCircle className="h-5 w-5 text-green-500" />
              Staging Results
              {result?.duration_seconds && (
                <Badge variant="outline" className="ml-2">{result.duration_seconds.toFixed(1)}s</Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-2 px-3 font-medium">Entity</th>
                    <th className="text-right py-2 px-3 font-medium">Inserted</th>
                    <th className="text-right py-2 px-3 font-medium">Updated</th>
                    <th className="text-right py-2 px-3 font-medium">Skipped</th>
                    <th className="text-right py-2 px-3 font-medium">Errors</th>
                    <th className="text-center py-2 px-3 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(entityResults).map(([entity, r]) => (
                    <tr key={entity} className="border-b hover:bg-muted/50">
                      <td className="py-2 px-3 font-mono text-xs">{entity}</td>
                      <td className="text-right py-2 px-3 text-green-600">{r.inserted || 0}</td>
                      <td className="text-right py-2 px-3 text-blue-600">{r.updated || 0}</td>
                      <td className="text-right py-2 px-3 text-muted-foreground">{r.skipped || 0}</td>
                      <td className="text-right py-2 px-3 text-red-600">{(r.validation_errors || []).length}</td>
                      <td className="text-center py-2 px-3">
                        {(r.validation_errors || []).length > 0 ? (
                          <Badge variant="destructive">Error</Badge>
                        ) : (r.inserted || 0) + (r.updated || 0) > 0 ? (
                          <Badge variant="default">Synced</Badge>
                        ) : (
                          <Badge variant="secondary">No Change</Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Reconciliation Results */}
      {Object.keys(reconData).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ArrowUpDown className="h-5 w-5" />
              Reconciliation — SAP vs Postgres
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-2 px-3 font-medium">Entity</th>
                    <th className="text-right py-2 px-3 font-medium">SAP Count</th>
                    <th className="text-right py-2 px-3 font-medium">DB Count</th>
                    <th className="text-right py-2 px-3 font-medium">Diff</th>
                    <th className="text-center py-2 px-3 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(reconData).map(([entity, r]) => {
                    const diff = (r.sap_count || 0) - (r.db_count || 0);
                    const match = diff === 0;
                    return (
                      <tr key={entity} className="border-b hover:bg-muted/50">
                        <td className="py-2 px-3 font-mono text-xs">{entity}</td>
                        <td className="text-right py-2 px-3">{r.sap_count ?? '—'}</td>
                        <td className="text-right py-2 px-3">{r.db_count ?? '—'}</td>
                        <td className={cn("text-right py-2 px-3 font-medium", match ? "text-green-600" : "text-amber-600")}>
                          {diff === 0 ? '0' : (diff > 0 ? `+${diff}` : diff)}
                        </td>
                        <td className="text-center py-2 px-3">
                          {match ? (
                            <Badge variant="default"><CheckCircle className="h-3 w-3 mr-1" /> Match</Badge>
                          ) : (
                            <Badge variant="outline" className="text-amber-600 border-amber-300">
                              <AlertTriangle className="h-3 w-3 mr-1" /> Mismatch
                            </Badge>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Run History */}
      {history.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Clock className="h-5 w-5" />
              Recent Runs
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {history.map((run, i) => {
                const entities = run.entities || {};
                const totalInserted = Object.values(entities).reduce((s, r) => s + (r.inserted || 0), 0);
                const totalUpdated = Object.values(entities).reduce((s, r) => s + (r.updated || 0), 0);
                const totalErrors = Object.values(entities).reduce((s, r) => s + (r.validation_errors || []).length, 0);
                return (
                  <div key={i} className="flex items-center justify-between p-2 rounded border text-sm">
                    <span className="text-muted-foreground">{new Date(run.timestamp).toLocaleString()}</span>
                    <div className="flex gap-3">
                      <span className="text-green-600">+{totalInserted} inserted</span>
                      <span className="text-blue-600">{totalUpdated} updated</span>
                      {totalErrors > 0 && <span className="text-red-600">{totalErrors} errors</span>}
                      {run.duration_seconds && <span className="text-muted-foreground">{run.duration_seconds.toFixed(1)}s</span>}
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

// Main Component
const SAPDataManagement = () => {
  const { user, isTenantAdmin } = useAuth();
  const [activeTab, setActiveTab] = useState('overview');
  const [loading, setLoading] = useState(true);

  // State
  const [dashboardData, setDashboardData] = useState(null);
  const [deploymentStatus, setDeploymentStatus] = useState(null);
  const [connections, setConnections] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [insights, setInsights] = useState([]);
  const [actions, setActions] = useState([]);
  const [selectedConnectionId, setSelectedConnectionId] = useState(null);

  // Load data
  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [dashboardRes, statusRes, connectionsRes, jobsRes, insightsRes, actionsRes] = await Promise.all([
        api.get('/sap-data/dashboard').catch(() => ({ data: {} })),
        api.get('/sap-data/deployment-status').catch(() => ({ data: {} })),
        api.get('/sap-data/connections').catch(() => ({ data: [] })),
        api.get('/sap-data/jobs').catch(() => ({ data: [] })),
        api.get('/sap-data/insights?unacknowledged_only=true').catch(() => ({ data: [] })),
        api.get('/sap-data/actions?status=suggested').catch(() => ({ data: [] })),
      ]);

      setDashboardData(dashboardRes.data);
      setDeploymentStatus(statusRes.data);
      setConnections(connectionsRes.data);
      setJobs(jobsRes.data);
      setInsights(insightsRes.data);
      setActions(actionsRes.data);

      // Auto-select first connection
      if (connectionsRes.data.length > 0 && !selectedConnectionId) {
        setSelectedConnectionId(connectionsRes.data[0].id);
      }
    } catch (error) {
      console.error('Failed to load SAP data:', error);
    }
    setLoading(false);
  }, [selectedConnectionId]);

  useEffect(() => {
    loadData();
  }, []);

  // Auto-refresh every 3s when any job is running
  useEffect(() => {
    const hasRunning = jobs.some(j => j.status === 'running');
    if (!hasRunning) return;
    const interval = setInterval(() => { loadData(); }, 3000);
    return () => clearInterval(interval);
  }, [jobs, loadData]);

  // Handlers
  const handleCreateConnection = async (data) => {
    try {
      // Convert empty strings to null for optional fields so Pydantic accepts them
      const required = new Set(['name', 'system_type', 'connection_method']);
      const cleaned = Object.fromEntries(
        Object.entries(data).map(([k, v]) => [k, !required.has(k) && v === '' ? null : v])
      );
      await api.post('/sap-data/connections', cleaned);
      loadData();
    } catch (error) {
      console.error('Failed to create connection:', error);
    }
  };

  const handleUpdateConnection = async (connectionId, data) => {
    try {
      const required = new Set(['name', 'system_type', 'connection_method']);
      const cleaned = Object.fromEntries(
        Object.entries(data).map(([k, v]) => [k, !required.has(k) && v === '' ? null : v])
      );
      await api.put(`/sap-data/connections/${connectionId}`, cleaned);
      loadData();
    } catch (error) {
      console.error('Failed to update connection:', error);
    }
  };

  const handleDeleteConnection = async (connectionId) => {
    try {
      await api.delete(`/sap-data/connections/${connectionId}`);
      loadData();
    } catch (error) {
      console.error('Failed to delete connection:', error);
    }
  };

  const handleTestConnection = async (connectionId) => {
    try {
      const response = await api.post(`/sap-data/connections/${connectionId}/test`);
      alert(response.data.message);
      loadData();
    } catch (error) {
      console.error('Failed to test connection:', error);
      alert('Connection test failed');
    }
  };

  const handleConfirmFileMapping = async (connectionId, updates) => {
    try {
      await api.post(`/sap-data/connections/${connectionId}/confirm-file-mapping`, updates);
      loadData();
    } catch (error) {
      console.error('Failed to update file mapping:', error);
      alert('Failed to update file mapping: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleCreateJob = async (jobData) => {
    try {
      await api.post('/sap-data/jobs', jobData);
      loadData();
    } catch (error) {
      console.error('Failed to create job:', error);
      alert('Failed to create ingestion job: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleStartJob = async (jobId) => {
    try {
      await api.post(`/sap-data/jobs/${jobId}/start`);
      loadData();
    } catch (error) {
      console.error('Failed to start job:', error);
      alert('Failed to start job: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleDeleteJob = async (jobId) => {
    try {
      await api.delete(`/sap-data/jobs/${jobId}`);
      loadData();
    } catch (error) {
      console.error('Failed to delete job:', error);
      alert('Failed to delete job: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleRerunJob = async (jobId) => {
    try {
      await api.post(`/sap-data/jobs/${jobId}/rerun`);
      loadData();
    } catch (error) {
      console.error('Failed to rerun job:', error);
      alert('Failed to rerun job: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleCancelJob = async (jobId) => {
    try {
      await api.post(`/sap-data/jobs/${jobId}/cancel`);
      loadData();
    } catch (error) {
      console.error('Failed to cancel job:', error);
      alert('Failed to cancel job: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleScheduleJob = () => {
    alert('Job scheduling — coming soon. Use "New Job" + "Run" for manual ingestion.');
  };

  const handleAcknowledgeInsight = async (insightId) => {
    try {
      await api.post(`/sap-data/insights/${insightId}/acknowledge`);
      loadData();
    } catch (error) {
      console.error('Failed to acknowledge insight:', error);
    }
  };

  const handleUpdateAction = async (actionId, status) => {
    try {
      await api.patch(`/sap-data/actions/${actionId}`, { status });
      loadData();
    } catch (error) {
      console.error('Failed to update action:', error);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto py-6 px-4">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Database className="h-6 w-6" />
            SAP Data Management
          </h1>
          <p className="text-muted-foreground mt-1">
            Configure SAP connections, manage field mappings, and monitor data ingestion
          </p>
        </div>

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="mb-6">
            {tabItems.map((tab) => (
              <Tab key={tab.value} value={tab.value}>
                {tab.icon}
                <span className="ml-2">{tab.label}</span>
              </Tab>
            ))}
          </TabsList>

          {/* Tab Content */}
          {activeTab === 'overview' && (
            <OverviewTab
              dashboardData={dashboardData}
              deploymentStatus={deploymentStatus}
              loading={loading}
            />
          )}

          {activeTab === 'connections' && (
            <ConnectionsTab
              connections={connections}
              onCreateConnection={handleCreateConnection}
              onUpdateConnection={handleUpdateConnection}
              onDeleteConnection={handleDeleteConnection}
              onTestConnection={handleTestConnection}
              onConfirmFileMapping={handleConfirmFileMapping}
              loading={loading}
            />
          )}

          {activeTab === 'tables' && (
            <TablesTab
              connections={connections}
              selectedConnectionId={selectedConnectionId}
              onSelectConnection={setSelectedConnectionId}
            />
          )}

          {activeTab === 'jobs' && (
            <JobsTab
              jobs={jobs}
              connections={connections}
              onCreateJob={handleCreateJob}
              onStartJob={handleStartJob}
              onDeleteJob={handleDeleteJob}
              onRerunJob={handleRerunJob}
              onCancelJob={handleCancelJob}
              onScheduleJob={handleScheduleJob}
              onRefresh={loadData}
              loading={loading}
            />
          )}

          {activeTab === 'insights' && (
            <InsightsTab
              insights={insights}
              actions={actions}
              onAcknowledge={handleAcknowledgeInsight}
              onUpdateAction={handleUpdateAction}
              loading={loading}
            />
          )}

          {activeTab === 'user-import' && (
            <UserImportTab />
          )}

          {activeTab === 'staging' && (
            <StagingTab connections={connections} />
          )}
        </Tabs>
      </div>
    </div>
  );
};

export default SAPDataManagement;
