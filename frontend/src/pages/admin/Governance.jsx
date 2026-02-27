/**
 * Governance Dashboard
 *
 * System administration page for compliance, audit logs, and governance policies.
 * Provides oversight of system usage, data retention, and regulatory compliance.
 */

import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Button,
  Badge,
  Alert,
  Modal,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '../../components/common';
import {
  Landmark,
  Shield,
  History,
  FileText,
  Scale,
  RefreshCw,
  Download,
  Eye,
  AlertTriangle,
  CheckCircle,
} from 'lucide-react';
import { api } from '../../services/api';

const Governance = () => {
  const [activeTab, setActiveTab] = useState('audit');
  const [auditLogs, setAuditLogs] = useState([]);
  const [policies, setPolicies] = useState([]);
  const [complianceStatus, setComplianceStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [selectedLog, setSelectedLog] = useState(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  useEffect(() => {
    loadMockData();
  }, []);

  const loadMockData = () => {
    setAuditLogs([
      { id: 1, timestamp: new Date().toISOString(), user: 'systemadmin@autonomy.ai', action: 'LOGIN', resource: 'System', status: 'SUCCESS', ip: '172.29.56.211' },
      { id: 2, timestamp: new Date(Date.now() - 3600000).toISOString(), user: 'tenantadmin@company.com', action: 'CREATE_USER', resource: 'User: john.doe@company.com', status: 'SUCCESS', ip: '172.29.56.200' },
      { id: 3, timestamp: new Date(Date.now() - 7200000).toISOString(), user: 'scenarioUser@company.com', action: 'VIEW_SCENARIO', resource: 'Scenario ID: 42', status: 'SUCCESS', ip: '172.29.56.150' },
      { id: 4, timestamp: new Date(Date.now() - 10800000).toISOString(), user: 'systemadmin@autonomy.ai', action: 'UPDATE_CONFIG', resource: 'Supply Chain Config: Default Demo', status: 'SUCCESS', ip: '172.29.56.211' },
      { id: 5, timestamp: new Date(Date.now() - 14400000).toISOString(), user: 'scenarioUser@company.com', action: 'LOGIN', resource: 'System', status: 'FAILED', ip: '172.29.56.155' },
    ]);

    setPolicies([
      { id: 1, name: 'Data Retention Policy', type: 'DATA_RETENTION', status: 'ACTIVE', lastUpdated: new Date(Date.now() - 86400000 * 30).toISOString(), description: 'Audit logs retained for 90 days, game data for 1 year' },
      { id: 2, name: 'Password Policy', type: 'SECURITY', status: 'ACTIVE', lastUpdated: new Date(Date.now() - 86400000 * 60).toISOString(), description: 'Minimum 12 characters, complexity requirements, 90-day rotation' },
      { id: 3, name: 'Access Control Policy', type: 'RBAC', status: 'ACTIVE', lastUpdated: new Date(Date.now() - 86400000 * 45).toISOString(), description: 'Role-based access control with capability-based permissions' },
      { id: 4, name: 'GDPR Compliance', type: 'COMPLIANCE', status: 'ACTIVE', lastUpdated: new Date(Date.now() - 86400000 * 90).toISOString(), description: 'Data protection and privacy compliance for EU users' },
      { id: 5, name: 'SOC 2 Compliance', type: 'COMPLIANCE', status: 'PENDING_REVIEW', lastUpdated: new Date(Date.now() - 86400000 * 10).toISOString(), description: 'Service Organization Control 2 Type II certification' },
    ]);

    setComplianceStatus({
      overall: 'COMPLIANT',
      checks: [
        { name: 'Data Encryption at Rest', status: 'PASS', lastCheck: new Date().toISOString() },
        { name: 'Data Encryption in Transit', status: 'PASS', lastCheck: new Date().toISOString() },
        { name: 'Access Logs Enabled', status: 'PASS', lastCheck: new Date().toISOString() },
        { name: 'Password Complexity', status: 'PASS', lastCheck: new Date().toISOString() },
        { name: 'MFA Enabled for Admins', status: 'WARNING', lastCheck: new Date().toISOString(), message: 'Some admin accounts do not have MFA enabled' },
        { name: 'Regular Security Audits', status: 'PASS', lastCheck: new Date(Date.now() - 86400000 * 30).toISOString() },
      ],
    });
  };

  const handleViewLog = (log) => {
    setSelectedLog(log);
    setDialogOpen(true);
  };

  const handleExportAuditLogs = () => {
    alert('Audit logs export initiated. This would download a CSV file.');
  };

  const formatTimestamp = (timestamp) => {
    return new Date(timestamp).toLocaleString();
  };

  const getStatusVariant = (status) => {
    switch (status) {
      case 'SUCCESS':
      case 'PASS':
      case 'ACTIVE':
      case 'COMPLIANT':
        return 'success';
      case 'FAILED':
      case 'FAIL':
        return 'destructive';
      case 'WARNING':
      case 'PENDING_REVIEW':
        return 'warning';
      default:
        return 'secondary';
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-primary mb-1">Governance & Compliance</h1>
        <p className="text-muted-foreground">
          System administration for compliance, audit logs, and governance policies
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-2 mb-2">
              <Scale className="h-5 w-5 text-green-600" />
              <span className="font-semibold">Compliance</span>
            </div>
            <p className="text-3xl font-bold text-green-600">COMPLIANT</p>
            <p className="text-sm text-muted-foreground">All checks passing</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-2 mb-2">
              <History className="h-5 w-5 text-primary" />
              <span className="font-semibold">Audit Logs</span>
            </div>
            <p className="text-3xl font-bold">{auditLogs.length}</p>
            <p className="text-sm text-muted-foreground">Recent entries</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-2 mb-2">
              <FileText className="h-5 w-5 text-blue-600" />
              <span className="font-semibold">Active Policies</span>
            </div>
            <p className="text-3xl font-bold">{policies.filter(p => p.status === 'ACTIVE').length}</p>
            <p className="text-sm text-muted-foreground">Of {policies.length} total</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-2 mb-2">
              <Shield className="h-5 w-5 text-amber-600" />
              <span className="font-semibold">Security Alerts</span>
            </div>
            <p className="text-3xl font-bold text-amber-600">1</p>
            <p className="text-sm text-muted-foreground">Requires attention</p>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Card>
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <div className="border-b">
            <TabsList className="w-full justify-start p-0 h-auto bg-transparent">
              <TabsTrigger value="audit" className="flex items-center gap-2 rounded-none border-b-2 border-transparent data-[state=active]:border-primary">
                <History className="h-4 w-4" />
                Audit Logs
              </TabsTrigger>
              <TabsTrigger value="policies" className="flex items-center gap-2 rounded-none border-b-2 border-transparent data-[state=active]:border-primary">
                <FileText className="h-4 w-4" />
                Policies
              </TabsTrigger>
              <TabsTrigger value="compliance" className="flex items-center gap-2 rounded-none border-b-2 border-transparent data-[state=active]:border-primary">
                <Scale className="h-4 w-4" />
                Compliance Checks
              </TabsTrigger>
            </TabsList>
          </div>

          <TabsContent value="audit" className="p-4">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold">Audit Trail</h2>
              <div className="flex gap-2">
                <Button variant="outline" onClick={loadMockData} leftIcon={<RefreshCw className="h-4 w-4" />}>
                  Refresh
                </Button>
                <Button onClick={handleExportAuditLogs} leftIcon={<Download className="h-4 w-4" />}>
                  Export
                </Button>
              </div>
            </div>

            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Timestamp</TableHead>
                  <TableHead>User</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead>Resource</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>IP Address</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {auditLogs.map((log) => (
                  <TableRow key={log.id}>
                    <TableCell>{formatTimestamp(log.timestamp)}</TableCell>
                    <TableCell>{log.user}</TableCell>
                    <TableCell><Badge variant="secondary">{log.action}</Badge></TableCell>
                    <TableCell>{log.resource}</TableCell>
                    <TableCell>
                      <Badge variant={getStatusVariant(log.status)}>{log.status}</Badge>
                    </TableCell>
                    <TableCell>{log.ip}</TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="sm" onClick={() => handleViewLog(log)}>
                        <Eye className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TabsContent>

          <TabsContent value="policies" className="p-4">
            <h2 className="text-lg font-semibold mb-4">Governance Policies</h2>
            <div className="space-y-4">
              {policies.map((policy) => (
                <Card key={policy.id} variant="outline">
                  <CardContent className="pt-4">
                    <div className="flex justify-between items-start">
                      <div className="flex-1">
                        <h3 className="text-lg font-semibold mb-1">{policy.name}</h3>
                        <p className="text-sm text-muted-foreground mb-3">{policy.description}</p>
                        <div className="flex gap-2">
                          <Badge variant="outline">{policy.type}</Badge>
                          <Badge variant={getStatusVariant(policy.status)}>{policy.status}</Badge>
                          <Badge variant="secondary">Updated: {formatTimestamp(policy.lastUpdated)}</Badge>
                        </div>
                      </div>
                      <Button variant="outline" size="sm">Edit</Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </TabsContent>

          <TabsContent value="compliance" className="p-4">
            <h2 className="text-lg font-semibold mb-2">Compliance Status</h2>
            <Alert variant="success" className="mb-4">
              Overall Status: <strong>COMPLIANT</strong> - All critical checks passing
            </Alert>

            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Check Name</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Last Checked</TableHead>
                  <TableHead>Notes</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {complianceStatus?.checks.map((check, index) => (
                  <TableRow key={index}>
                    <TableCell>{check.name}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        {check.status === 'PASS' && <CheckCircle className="h-4 w-4 text-green-600" />}
                        {check.status === 'WARNING' && <AlertTriangle className="h-4 w-4 text-amber-600" />}
                        <Badge variant={getStatusVariant(check.status)}>{check.status}</Badge>
                      </div>
                    </TableCell>
                    <TableCell>{formatTimestamp(check.lastCheck)}</TableCell>
                    <TableCell>
                      {check.message && (
                        <span className="text-amber-600 text-sm">{check.message}</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TabsContent>
        </Tabs>
      </Card>

      {/* Audit Log Detail Modal */}
      <Modal
        isOpen={dialogOpen}
        onClose={() => setDialogOpen(false)}
        title="Audit Log Details"
        size="md"
        footer={
          <div className="flex justify-end">
            <Button onClick={() => setDialogOpen(false)}>Close</Button>
          </div>
        }
      >
        {selectedLog && (
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-sm text-muted-foreground">Timestamp</p>
              <p>{formatTimestamp(selectedLog.timestamp)}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">User</p>
              <p>{selectedLog.user}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Action</p>
              <Badge>{selectedLog.action}</Badge>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Status</p>
              <Badge variant={getStatusVariant(selectedLog.status)}>{selectedLog.status}</Badge>
            </div>
            <div className="col-span-2">
              <p className="text-sm text-muted-foreground">Resource</p>
              <p>{selectedLog.resource}</p>
            </div>
            <div className="col-span-2">
              <p className="text-sm text-muted-foreground">IP Address</p>
              <p>{selectedLog.ip}</p>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default Governance;
