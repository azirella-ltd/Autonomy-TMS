/**
 * Edge Agent Security & Audit
 *
 * Admin page for monitoring security posture of PicoClaw and OpenClaw
 * integrations, CVE tracking, deployment checklist, and integration health.
 */

import React, { useState, useEffect } from 'react';
import { securityApi } from '../../services/edgeAgentApi';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
  Button,
  Spinner,
  Alert,
  AlertDescription,
  Tabs,
  TabsList,
  Tab,
  Badge,
} from '../../components/common';
import {
  Shield,
  Activity,
  ChevronRight,
  CheckCircle,
  AlertTriangle,
  XCircle,
  Clock,
  RefreshCw,
  Eye,
  Lock,
  Unlock,
  Bug,
  ListChecks,
  Server,
  Wifi,
  WifiOff,
  Database,
  FileWarning,
  ShieldAlert,
  ShieldCheck,
  ExternalLink,
} from 'lucide-react';
import { cn } from '../../lib/utils/cn';

const tabItems = [
  { value: 'overview', label: 'Security Overview', icon: <Shield className="h-4 w-4" /> },
  { value: 'cves', label: 'CVE Tracker', icon: <Bug className="h-4 w-4" /> },
  { value: 'checklist', label: 'Deployment Checklist', icon: <ListChecks className="h-4 w-4" /> },
  { value: 'health', label: 'Integration Health', icon: <Activity className="h-4 w-4" /> },
];

// ============================================================================
// Security Overview Tab
// ============================================================================
const SecurityOverviewTab = ({ audit, loading, onRefresh }) => {
  if (loading) {
    return <div className="flex justify-center py-12"><Spinner size="lg" /></div>;
  }

  const summary = audit || {};

  return (
    <div className="space-y-6">
      {/* Overall Security Status */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className={cn(
              "p-4 rounded-lg border-2",
              summary.openclaw_secure ? "border-green-500 bg-green-50" : "border-red-500 bg-red-50"
            )}>
              <div className="flex items-center gap-2 mb-2">
                {summary.openclaw_secure ? (
                  <ShieldCheck className="h-5 w-5 text-green-500" />
                ) : (
                  <ShieldAlert className="h-5 w-5 text-red-500" />
                )}
                <span className="font-medium">OpenClaw</span>
              </div>
              <p className="text-sm text-muted-foreground">
                {summary.openclaw_secure ? 'Secure' : `${summary.openclaw_cve_count || '?'} CVE(s) Active`}
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className={cn(
              "p-4 rounded-lg border-2",
              summary.picoclaw_secure ? "border-green-500 bg-green-50" : "border-yellow-500 bg-yellow-50"
            )}>
              <div className="flex items-center gap-2 mb-2">
                {summary.picoclaw_secure ? (
                  <ShieldCheck className="h-5 w-5 text-green-500" />
                ) : (
                  <AlertTriangle className="h-5 w-5 text-yellow-500" />
                )}
                <span className="font-medium">PicoClaw</span>
              </div>
              <p className="text-sm text-muted-foreground">
                {summary.picoclaw_secure ? 'Hardened' : 'Pre-v1.0 — Review Required'}
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className={cn(
              "p-4 rounded-lg border-2",
              summary.checklist_complete ? "border-green-500 bg-green-50" : "border-yellow-500 bg-yellow-50"
            )}>
              <div className="flex items-center gap-2 mb-2">
                {summary.checklist_complete ? (
                  <CheckCircle className="h-5 w-5 text-green-500" />
                ) : (
                  <Clock className="h-5 w-5 text-yellow-500" />
                )}
                <span className="font-medium">Checklist</span>
              </div>
              <p className="text-sm text-muted-foreground">
                {summary.checklist_passed || 0}/{summary.checklist_total || 30} passed
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className={cn(
              "p-4 rounded-lg border-2",
              summary.injection_attempts === 0 ? "border-green-500 bg-green-50" : "border-red-500 bg-red-50"
            )}>
              <div className="flex items-center gap-2 mb-2">
                {summary.injection_attempts === 0 ? (
                  <ShieldCheck className="h-5 w-5 text-green-500" />
                ) : (
                  <FileWarning className="h-5 w-5 text-red-500" />
                )}
                <span className="font-medium">Injections</span>
              </div>
              <p className="text-sm text-muted-foreground">
                {summary.injection_attempts || 0} blocked this week
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Key Risks */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Key Security Risks</CardTitle>
            <Button variant="outline" size="sm" onClick={onRefresh}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Refresh
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {[
              {
                risk: 'OpenClaw CVEs',
                severity: 'high',
                desc: '7+ CVEs including CVE-2026-25253 (RCE, CVSS 8.8). Minimum version: v2026.2.15.',
                mitigated: summary.openclaw_version_ok,
              },
              {
                risk: 'ClawHub Supply Chain',
                severity: 'critical',
                desc: 'ClawHavoc attack (Jan 2026): 1,184 malicious skills discovered. Public ClawHub disabled.',
                mitigated: true,
              },
              {
                risk: 'WhatsApp Baileys',
                severity: 'medium',
                desc: 'Unofficial API — ToS violation risk, no guaranteed stability. Use only for pilot.',
                mitigated: summary.whatsapp_pilot_only,
              },
              {
                risk: 'PicoClaw Pre-v1.0',
                severity: 'low',
                desc: '95% AI-generated code, no security audit, no SECURITY.md. Read-only containers mitigate.',
                mitigated: summary.picoclaw_readonly,
              },
              {
                risk: 'Credential Exposure',
                severity: 'high',
                desc: 'Vidar infostealer targets OpenClaw users. All credentials must be in env vars.',
                mitigated: summary.credentials_in_env,
              },
              {
                risk: 'Signal Injection',
                severity: 'medium',
                desc: 'Prompt injection via channel messages. Input sanitization + confidence gating mitigates.',
                mitigated: summary.sanitization_enabled,
              },
            ].map((item, i) => (
              <div key={i} className={cn(
                "p-3 rounded-lg border flex items-center justify-between",
                item.mitigated ? "border-green-200 bg-green-50/50" : "border-red-200 bg-red-50/50"
              )}>
                <div className="flex items-center gap-3">
                  {item.mitigated ? (
                    <ShieldCheck className="h-5 w-5 text-green-500 flex-shrink-0" />
                  ) : (
                    <ShieldAlert className="h-5 w-5 text-red-500 flex-shrink-0" />
                  )}
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{item.risk}</span>
                      <Badge variant={
                        item.severity === 'critical' ? 'destructive' :
                        item.severity === 'high' ? 'destructive' :
                        item.severity === 'medium' ? 'warning' : 'secondary'
                      }>
                        {item.severity}
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground">{item.desc}</p>
                  </div>
                </div>
                <Badge variant={item.mitigated ? 'success' : 'destructive'}>
                  {item.mitigated ? 'Mitigated' : 'Action Required'}
                </Badge>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

// ============================================================================
// CVE Tracker Tab
// ============================================================================
const CVETrackerTab = () => {
  const [cves, setCves] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadCVEs();
  }, []);

  const loadCVEs = async () => {
    setLoading(true);
    try {
      const res = await securityApi.getCVEStatus();
      setCves(res.data || []);
    } catch {
      // Default known CVEs
      setCves([
        { id: 'CVE-2026-25253', severity: 'CRITICAL', cvss: 8.8, component: 'OpenClaw', desc: 'RCE via crafted gatewayUrl in skills', fixed_in: 'v2026.2.15', status: 'unknown' },
        { id: 'CVE-2026-26325', severity: 'HIGH', cvss: 7.5, component: 'OpenClaw', desc: 'Authentication bypass via expired token reuse', fixed_in: 'v2026.2.10', status: 'unknown' },
        { id: 'CVE-2026-25474', severity: 'HIGH', cvss: 7.1, component: 'OpenClaw', desc: 'Telegram webhook forgery (missing webhookSecret validation)', fixed_in: 'v2026.2.8', status: 'unknown' },
        { id: 'CVE-2026-26324', severity: 'MEDIUM', cvss: 6.5, component: 'OpenClaw', desc: 'SSRF via skill proxy endpoint', fixed_in: 'v2026.2.12', status: 'unknown' },
        { id: 'CVE-2026-27003', severity: 'MEDIUM', cvss: 5.3, component: 'OpenClaw', desc: 'Telegram token exposure in error logs', fixed_in: 'v2026.2.14', status: 'unknown' },
        { id: 'CVE-2026-27004', severity: 'MEDIUM', cvss: 5.0, component: 'OpenClaw', desc: 'Session isolation bypass via sessions_send', fixed_in: 'v2026.2.15', status: 'unknown' },
        { id: 'GHSA-r5fq', severity: 'HIGH', cvss: 7.2, component: 'OpenClaw', desc: 'Path traversal in workspace file access', fixed_in: 'v2026.1.28', status: 'unknown' },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const severityStyles = {
    CRITICAL: { bg: 'bg-red-100', text: 'text-red-800', badge: 'destructive' },
    HIGH: { bg: 'bg-orange-100', text: 'text-orange-800', badge: 'destructive' },
    MEDIUM: { bg: 'bg-yellow-100', text: 'text-yellow-800', badge: 'warning' },
    LOW: { bg: 'bg-blue-100', text: 'text-blue-800', badge: 'secondary' },
  };

  return (
    <div className="space-y-4">
      <Alert>
        <Shield className="h-4 w-4" />
        <AlertDescription>
          CVE tracking for PicoClaw and OpenClaw components. Ensure all installed versions are patched.
          PicoClaw has no known CVEs (pre-v1.0 with limited scrutiny — does not imply absence of vulnerabilities).
        </AlertDescription>
      </Alert>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Known Vulnerabilities</CardTitle>
            <Button variant="outline" size="sm" onClick={loadCVEs}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Refresh
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex justify-center py-8"><Spinner size="lg" /></div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-3 px-4 font-medium">CVE ID</th>
                  <th className="text-left py-3 px-4 font-medium">Severity</th>
                  <th className="text-left py-3 px-4 font-medium">CVSS</th>
                  <th className="text-left py-3 px-4 font-medium">Component</th>
                  <th className="text-left py-3 px-4 font-medium">Description</th>
                  <th className="text-left py-3 px-4 font-medium">Fixed In</th>
                  <th className="text-left py-3 px-4 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {cves.map((cve) => {
                  const style = severityStyles[cve.severity] || severityStyles.MEDIUM;
                  return (
                    <tr key={cve.id} className="border-b hover:bg-muted/50">
                      <td className="py-3 px-4 font-mono text-xs font-semibold">{cve.id}</td>
                      <td className="py-3 px-4">
                        <Badge variant={style.badge}>{cve.severity}</Badge>
                      </td>
                      <td className="py-3 px-4 font-mono">{cve.cvss}</td>
                      <td className="py-3 px-4">{cve.component}</td>
                      <td className="py-3 px-4 max-w-xs">{cve.desc}</td>
                      <td className="py-3 px-4 font-mono text-xs">{cve.fixed_in}</td>
                      <td className="py-3 px-4">
                        {cve.status === 'patched' ? (
                          <Badge variant="success">
                            <CheckCircle className="h-3 w-3 mr-1" />
                            Patched
                          </Badge>
                        ) : cve.status === 'vulnerable' ? (
                          <Badge variant="destructive">
                            <XCircle className="h-3 w-3 mr-1" />
                            Vulnerable
                          </Badge>
                        ) : (
                          <Badge variant="secondary">
                            <Clock className="h-3 w-3 mr-1" />
                            Unknown
                          </Badge>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

// ============================================================================
// Deployment Checklist Tab
// ============================================================================
const DeploymentChecklistTab = () => {
  const [checklist, setChecklist] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadChecklist();
  }, []);

  const loadChecklist = async () => {
    setLoading(true);
    try {
      const res = await securityApi.getChecklist();
      setChecklist(res.data);
    } catch {
      // Default checklist
      setChecklist({
        sections: [
          {
            name: 'Infrastructure',
            items: [
              { id: 'infra-1', label: 'OpenClaw version >= v2026.2.15', checked: false },
              { id: 'infra-2', label: 'Gateway bound to 127.0.0.1 (loopback only)', checked: false },
              { id: 'infra-3', label: 'Reverse proxy configured (nginx/caddy)', checked: false },
              { id: 'infra-4', label: 'Container runs as non-root with --cap-drop ALL', checked: false },
              { id: 'infra-5', label: 'PicoClaw containers are read-only (--read-only)', checked: false },
              { id: 'infra-6', label: 'SecureClaw audit passed (OpenClaw)', checked: false },
            ],
          },
          {
            name: 'Credentials',
            items: [
              { id: 'cred-1', label: 'All credentials stored in environment variables', checked: false },
              { id: 'cred-2', label: 'Bot tokens in env vars (not config files)', checked: false },
              { id: 'cred-3', label: 'Gateway auth token rotated (not default)', checked: false },
              { id: 'cred-4', label: 'Per-site JWT scoping for PicoClaw accounts', checked: false },
              { id: 'cred-5', label: 'Service account tokens have expiry dates', checked: false },
            ],
          },
          {
            name: 'Channel Security',
            items: [
              { id: 'chan-1', label: 'Telegram webhookSecret configured', checked: false },
              { id: 'chan-2', label: 'Slack bot scoped to required channels only', checked: false },
              { id: 'chan-3', label: 'Email sender validation enabled', checked: false },
              { id: 'chan-4', label: 'DM pairing mode enabled (no group auth bypass)', checked: false },
              { id: 'chan-5', label: 'WhatsApp pilot-only flag set (if using Baileys)', checked: false },
            ],
          },
          {
            name: 'Signal Ingestion',
            items: [
              { id: 'sig-1', label: 'Rate limiting enabled (100/hour/source)', checked: false },
              { id: 'sig-2', label: 'Deduplication window active (1h)', checked: false },
              { id: 'sig-3', label: 'Input sanitization (control char stripping)', checked: false },
              { id: 'sig-4', label: 'Confidence gating thresholds configured', checked: false },
              { id: 'sig-5', label: 'Adjustment magnitude caps enabled (±50%)', checked: false },
              { id: 'sig-6', label: 'Prompt injection pattern detection active', checked: false },
            ],
          },
          {
            name: 'Monitoring',
            items: [
              { id: 'mon-1', label: 'Access logs forwarded to SIEM', checked: false },
              { id: 'mon-2', label: 'Failed authentication alerting configured', checked: false },
              { id: 'mon-3', label: 'Anomalous signal pattern detection active', checked: false },
            ],
          },
          {
            name: 'Skills',
            items: [
              { id: 'skill-1', label: 'No ClawHub marketplace skills installed', checked: false },
              { id: 'skill-2', label: 'npm audit clean for skill dependencies', checked: false },
              { id: 'skill-3', label: 'package-lock.json checked into version control', checked: false },
            ],
          },
        ],
      });
    } finally {
      setLoading(false);
    }
  };

  const handleToggle = async (itemId, checked) => {
    try {
      await securityApi.updateChecklistItem(itemId, !checked).catch(() => {});
      setChecklist(prev => ({
        ...prev,
        sections: prev.sections.map(section => ({
          ...section,
          items: section.items.map(item =>
            item.id === itemId ? { ...item, checked: !item.checked } : item
          ),
        })),
      }));
    } catch (err) {
      console.error('Failed to update checklist item:', err);
    }
  };

  if (loading) {
    return <div className="flex justify-center py-12"><Spinner size="lg" /></div>;
  }

  const totalItems = checklist?.sections?.reduce((sum, s) => sum + s.items.length, 0) || 0;
  const checkedItems = checklist?.sections?.reduce(
    (sum, s) => sum + s.items.filter(i => i.checked).length, 0
  ) || 0;
  const allPassed = checkedItems === totalItems;

  return (
    <div className="space-y-6">
      {/* Progress Bar */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between mb-3">
            <span className="font-semibold">Pre-Deployment Security Checklist</span>
            <Badge variant={allPassed ? 'success' : 'warning'}>
              {checkedItems}/{totalItems} Complete
            </Badge>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-3">
            <div
              className={cn(
                "h-3 rounded-full transition-all",
                allPassed ? "bg-green-500" : checkedItems > totalItems / 2 ? "bg-yellow-500" : "bg-red-500"
              )}
              style={{ width: `${(checkedItems / totalItems) * 100}%` }}
            />
          </div>
        </CardContent>
      </Card>

      {/* Checklist Sections */}
      {checklist?.sections?.map((section) => {
        const sectionChecked = section.items.filter(i => i.checked).length;
        const sectionTotal = section.items.length;
        const sectionComplete = sectionChecked === sectionTotal;

        return (
          <Card key={section.name}>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {sectionComplete ? (
                    <CheckCircle className="h-5 w-5 text-green-500" />
                  ) : (
                    <Clock className="h-5 w-5 text-yellow-500" />
                  )}
                  {section.name}
                </div>
                <span className="text-sm font-normal text-muted-foreground">
                  {sectionChecked}/{sectionTotal}
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {section.items.map((item) => (
                  <label
                    key={item.id}
                    className={cn(
                      "flex items-center gap-3 p-2 rounded-lg cursor-pointer hover:bg-muted/50",
                      item.checked && "bg-green-50/50"
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={item.checked}
                      onChange={() => handleToggle(item.id, item.checked)}
                      className="h-4 w-4 rounded border-gray-300"
                    />
                    <span className={cn(
                      "text-sm",
                      item.checked && "line-through text-muted-foreground"
                    )}>
                      {item.label}
                    </span>
                  </label>
                ))}
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
};

// ============================================================================
// Integration Health Tab
// ============================================================================
const IntegrationHealthTab = () => {
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadHealth();
  }, []);

  const loadHealth = async () => {
    setLoading(true);
    try {
      const res = await securityApi.getIntegrationHealth();
      setHealth(res.data);
    } catch {
      setHealth({
        services: [
          { name: 'Autonomy REST API', status: 'unknown', latency: null, last_check: null },
          { name: 'OpenClaw Gateway', status: 'unknown', latency: null, last_check: null },
          { name: 'PicoClaw Fleet', status: 'unknown', latency: null, last_check: null },
          { name: 'vLLM Service', status: 'unknown', latency: null, last_check: null },
          { name: 'PostgreSQL Database', status: 'unknown', latency: null, last_check: null },
          { name: 'Signal Ingestion Pipeline', status: 'unknown', latency: null, last_check: null },
        ],
        recent_errors: [],
      });
    } finally {
      setLoading(false);
    }
  };

  const statusIcons = {
    healthy: <CheckCircle className="h-5 w-5 text-green-500" />,
    degraded: <AlertTriangle className="h-5 w-5 text-yellow-500" />,
    down: <XCircle className="h-5 w-5 text-red-500" />,
    unknown: <Clock className="h-5 w-5 text-gray-400" />,
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Service Health</CardTitle>
            <Button variant="outline" size="sm" onClick={loadHealth}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Check All
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex justify-center py-8"><Spinner size="lg" /></div>
          ) : (
            <div className="space-y-3">
              {(health?.services || []).map((svc, i) => (
                <div key={i} className={cn(
                  "p-3 rounded-lg border flex items-center justify-between",
                  svc.status === 'healthy' ? "border-green-200" :
                  svc.status === 'degraded' ? "border-yellow-200" :
                  svc.status === 'down' ? "border-red-200" : "border-gray-200"
                )}>
                  <div className="flex items-center gap-3">
                    {statusIcons[svc.status] || statusIcons.unknown}
                    <div>
                      <span className="font-medium">{svc.name}</span>
                      {svc.latency != null && (
                        <span className="text-sm text-muted-foreground ml-2">({svc.latency}ms)</span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {svc.last_check && (
                      <span className="text-xs text-muted-foreground">
                        Last: {new Date(svc.last_check).toLocaleTimeString()}
                      </span>
                    )}
                    <Badge variant={
                      svc.status === 'healthy' ? 'success' :
                      svc.status === 'degraded' ? 'warning' :
                      svc.status === 'down' ? 'destructive' : 'secondary'
                    }>
                      {svc.status}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Recent Errors */}
      <Card>
        <CardHeader>
          <CardTitle>Recent Integration Errors</CardTitle>
          <CardDescription>Last 10 errors across all edge agent integrations</CardDescription>
        </CardHeader>
        <CardContent>
          {(health?.recent_errors || []).length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <CheckCircle className="h-12 w-12 mx-auto mb-4 text-green-300" />
              <p>No recent errors</p>
            </div>
          ) : (
            <div className="space-y-2">
              {health.recent_errors.map((err, i) => (
                <div key={i} className="p-3 rounded-lg border border-red-200 bg-red-50/50">
                  <div className="flex items-center justify-between mb-1">
                    <Badge variant="destructive">{err.service}</Badge>
                    <span className="text-xs text-muted-foreground">
                      {err.timestamp ? new Date(err.timestamp).toLocaleString() : '—'}
                    </span>
                  </div>
                  <p className="text-sm">{err.message}</p>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

// ============================================================================
// Main Component
// ============================================================================
const EdgeAgentSecurity = () => {
  const [currentTab, setCurrentTab] = useState('overview');
  const [audit, setAudit] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadAudit();
  }, []);

  const loadAudit = async () => {
    setLoading(true);
    try {
      const res = await securityApi.getAuditSummary();
      setAudit(res.data);
      setError(null);
    } catch {
      setAudit({});
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Breadcrumbs */}
      <nav className="flex items-center gap-2 text-sm text-muted-foreground mb-4">
        <a href="/admin" className="hover:text-foreground">Administration</a>
        <ChevronRight className="h-4 w-4" />
        <span className="text-foreground">Edge Agent Security</span>
      </nav>

      {/* Title */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold flex items-center gap-3">
          <Shield className="h-7 w-7 text-primary" />
          Edge Agent Security & Audit
        </h1>
        <p className="text-muted-foreground mt-1">
          Monitor security posture for PicoClaw and OpenClaw integrations.
          Track CVEs, validate deployment checklist, and monitor integration health.
        </p>
      </div>

      {/* Tabs */}
      <Tabs value={currentTab} onValueChange={setCurrentTab}>
        <TabsList className="w-full justify-start border-b rounded-none h-auto p-0 mb-6">
          {tabItems.map((tab) => (
            <Tab
              key={tab.value}
              value={tab.value}
              className="flex items-center gap-2 rounded-none border-b-2 border-transparent data-[state=active]:border-primary px-4 py-3"
            >
              {tab.icon}
              {tab.label}
            </Tab>
          ))}
        </TabsList>

        {currentTab === 'overview' && (
          <SecurityOverviewTab audit={audit} loading={loading} onRefresh={loadAudit} />
        )}
        {currentTab === 'cves' && <CVETrackerTab />}
        {currentTab === 'checklist' && <DeploymentChecklistTab />}
        {currentTab === 'health' && <IntegrationHealthTab />}
      </Tabs>
    </div>
  );
};

export default EdgeAgentSecurity;
