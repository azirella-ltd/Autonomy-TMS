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
  Zap,
  Activity,
  BarChart3,
} from 'lucide-react';
import { cn } from '../../lib/utils/cn';

const tabItems = [
  { value: 'overview', label: 'Overview', icon: <BarChart3 className="h-4 w-4" /> },
  { value: 'connections', label: 'Connections', icon: <Server className="h-4 w-4" /> },
  { value: 'tables', label: 'Tables & Mapping', icon: <Table2 className="h-4 w-4" /> },
  { value: 'jobs', label: 'Ingestion Jobs', icon: <Activity className="h-4 w-4" /> },
  { value: 'insights', label: 'Insights & Actions', icon: <Lightbulb className="h-4 w-4" /> },
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
const ConnectionsTab = ({ connections, onCreateConnection, onTestConnection, loading }) => {
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    system_type: 's4hana',
    connection_method: 'csv',
    csv_directory: '',
    ashost: '',
    sysnr: '',
    client: '',
    user: '',
  });

  const handleCreate = async () => {
    await onCreateConnection(formData);
    setShowCreateDialog(false);
    setFormData({
      name: '',
      system_type: 's4hana',
      connection_method: 'csv',
      csv_directory: '',
      ashost: '',
      sysnr: '',
      client: '',
      user: '',
    });
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
              <CardContent className="py-4">
                <div className="flex items-center justify-between">
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
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <Badge variant={conn.is_validated ? 'success' : 'secondary'}>
                      {conn.is_validated ? 'Validated' : 'Not Tested'}
                    </Badge>
                    <Button variant="outline" size="sm" onClick={() => onTestConnection(conn.id)}>
                      Test Connection
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create Connection Dialog */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Add SAP Connection</DialogTitle>
            <DialogDescription>
              Configure a connection to your SAP system for data extraction.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <label className="block text-sm font-medium mb-1">Connection Name</label>
              <Input
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="e.g., Production S/4HANA"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1">System Type</label>
                <NativeSelect
                  value={formData.system_type}
                  onChange={(e) => setFormData({ ...formData, system_type: e.target.value })}
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
                  onChange={(e) => setFormData({ ...formData, connection_method: e.target.value })}
                >
                  {connectionMethods.map((method) => (
                    <option key={method.value} value={method.value}>{method.label}</option>
                  ))}
                </NativeSelect>
              </div>
            </div>

            {formData.connection_method === 'csv' && (
              <div>
                <label className="block text-sm font-medium mb-1">CSV Directory Path</label>
                <Input
                  value={formData.csv_directory}
                  onChange={(e) => setFormData({ ...formData, csv_directory: e.target.value })}
                  placeholder="/path/to/csv/exports"
                />
              </div>
            )}

            {formData.connection_method === 'rfc' && (
              <>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-1">Application Server</label>
                    <Input
                      value={formData.ashost}
                      onChange={(e) => setFormData({ ...formData, ashost: e.target.value })}
                      placeholder="sap-server.example.com"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">System Number</label>
                    <Input
                      value={formData.sysnr}
                      onChange={(e) => setFormData({ ...formData, sysnr: e.target.value })}
                      placeholder="00"
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-1">Client</label>
                    <Input
                      value={formData.client}
                      onChange={(e) => setFormData({ ...formData, client: e.target.value })}
                      placeholder="100"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">User</label>
                    <Input
                      value={formData.user}
                      onChange={(e) => setFormData({ ...formData, user: e.target.value })}
                      placeholder="RFC_USER"
                    />
                  </div>
                </div>
              </>
            )}
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setShowCreateDialog(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={!formData.name}>
              Create Connection
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

// Tables & Mapping Tab Component
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

  const handleAnalyzeZTable = async (table) => {
    setMappingLoading(true);
    try {
      const response = await api.post('/sap-data/z-table-analysis', {
        table_name: table.table_name,
        table_description: table.description,
        fields: [],  // Would come from table metadata
        use_ai: true,
      });
      setSelectedTable({ ...table, analysis: response.data });
    } catch (error) {
      console.error('Failed to analyze table:', error);
    }
    setMappingLoading(false);
  };

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
                <CardTitle className="text-lg">Available Tables</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <div className="max-h-96 overflow-y-auto">
                  {tables.map((table) => (
                    <div
                      key={table.id}
                      className={cn(
                        "p-3 border-b cursor-pointer hover:bg-muted transition-colors",
                        selectedTable?.table_name === table.table_name && "bg-muted"
                      )}
                      onClick={() => setSelectedTable(table)}
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
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Table Details & Mapping */}
          <div className="col-span-2">
            {selectedTable ? (
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle>{selectedTable.table_name}</CardTitle>
                      <p className="text-sm text-muted-foreground">{selectedTable.description}</p>
                    </div>
                    {!selectedTable.is_standard && (
                      <Button
                        onClick={() => handleAnalyzeZTable(selectedTable)}
                        disabled={mappingLoading}
                      >
                        {mappingLoading ? (
                          <Spinner size="sm" className="mr-2" />
                        ) : (
                          <Zap className="h-4 w-4 mr-2" />
                        )}
                        AI Analyze Z-Table
                      </Button>
                    )}
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="text-sm font-medium">Target AWS SC Entity</label>
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

                    {/* AI Analysis Results */}
                    {selectedTable.analysis && (
                      <div className="mt-4 p-4 bg-blue-50 rounded-lg border border-blue-200">
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
                      </div>
                    )}

                    {/* Field Mappings would go here */}
                    <div className="mt-6">
                      <h4 className="font-medium mb-3">Field Mappings</h4>
                      <div className="text-sm text-muted-foreground">
                        Field mappings will be displayed here after table analysis.
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
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
const JobsTab = ({ jobs, onCreateJob, onRefresh, loading }) => {
  const [showCreateDialog, setShowCreateDialog] = useState(false);

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-semibold">Ingestion Jobs</h2>
        <div className="flex gap-2">
          <Button variant="outline" onClick={onRefresh}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
          <Button onClick={() => setShowCreateDialog(true)}>
            <Play className="h-4 w-4 mr-2" />
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
                      job.status === 'completed' ? "bg-green-100" :
                      job.status === 'running' ? "bg-blue-100" :
                      job.status === 'failed' ? "bg-red-100" : "bg-gray-100"
                    )}>
                      {job.status === 'running' ? (
                        <Spinner size="sm" />
                      ) : job.status === 'completed' ? (
                        <CheckCircle className="h-5 w-5 text-green-600" />
                      ) : job.status === 'failed' ? (
                        <AlertTriangle className="h-5 w-5 text-red-600" />
                      ) : (
                        <Clock className="h-5 w-5 text-gray-400" />
                      )}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium">Job #{job.id}</span>
                        <Badge variant="outline">{job.job_type}</Badge>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        Tables: {job.tables?.join(', ')}
                      </p>
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
                {job.status === 'running' && (
                  <div className="mt-3">
                    <div className="h-2 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full bg-blue-500 transition-all"
                        style={{ width: `${job.progress_percent}%` }}
                      />
                    </div>
                    {job.current_table && (
                      <p className="text-xs text-muted-foreground mt-1">
                        Processing: {job.current_table}
                      </p>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};

// Insights & Actions Tab Component
const InsightsTab = ({ insights, actions, onAcknowledge, onUpdateAction, loading }) => {
  const [activeSubTab, setActiveSubTab] = useState('insights');

  return (
    <div className="space-y-6">
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

// Main Component
const SAPDataManagement = () => {
  const { user, isGroupAdmin } = useAuth();
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

  // Handlers
  const handleCreateConnection = async (data) => {
    try {
      await api.post('/sap-data/connections', data);
      loadData();
    } catch (error) {
      console.error('Failed to create connection:', error);
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
              onTestConnection={handleTestConnection}
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
              onCreateJob={() => {}}
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
        </Tabs>
      </div>
    </div>
  );
};

export default SAPDataManagement;
