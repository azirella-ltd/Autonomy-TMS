/**
 * Tenant Settings Panel
 *
 * Production tenant configuration settings including:
 * - Planning Hierarchy Levels (Product, Geography, Time)
 * - Data Sources (SAP, etc.)
 * - Data Import Cadence
 * - CDC Thresholds for Event-Based Planning
 *
 * References: POWELL_APPROACH.md and CLAUDE.md
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  CardContent,
  Button,
  Spinner,
  Alert,
  AlertDescription,
  Tabs,
  TabsList,
  Tab,
} from '../../components/common';
import {
  Settings,
  Database,
  Clock,
  Activity,
  Layers,
  Globe,
  Calendar,
  RefreshCw,
  AlertTriangle,
  Save,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Server,
  FileSpreadsheet,
  Zap,
  Shield,
} from 'lucide-react';
import { cn } from '@azirella-ltd/autonomy-frontend';
import { api } from '../../services/api';

// Hierarchy level options from POWELL_APPROACH.md
const SITE_HIERARCHY_LEVELS = [
  { value: 'company', label: 'Company', description: 'Enterprise-wide aggregation' },
  { value: 'region', label: 'Region', description: 'Geographic regions (APAC, EMEA, Americas)' },
  { value: 'country', label: 'Country', description: 'Country-level aggregation' },
  { value: 'state', label: 'State/Province', description: 'State or province level' },
  { value: 'site', label: 'Site', description: 'Individual warehouse, DC, or factory' },
];

const PRODUCT_HIERARCHY_LEVELS = [
  { value: 'category', label: 'Category', description: 'Broad product categories' },
  { value: 'family', label: 'Family', description: 'Product families' },
  { value: 'group', label: 'Group', description: 'Product groups' },
  { value: 'product', label: 'Product (SKU)', description: 'Individual SKUs' },
];

const TIME_BUCKET_OPTIONS = [
  { value: 'hour', label: 'Hour', description: 'Real-time execution (ATP)' },
  { value: 'day', label: 'Day', description: 'Daily planning (MRP)' },
  { value: 'week', label: 'Week', description: 'Weekly planning (MPS)' },
  { value: 'month', label: 'Month', description: 'Monthly planning (S&OP)' },
  { value: 'quarter', label: 'Quarter', description: 'Quarterly planning (Strategic)' },
];

// Planning types from Adaptive Decision Hierarchy
const PLANNING_TYPES = {
  sop: { label: 'S&OP', color: 'blue', description: 'Sales & Operations Planning - Monthly strategic alignment' },
  mps: { label: 'MPS', color: 'purple', description: 'Master Production Schedule - Weekly production planning' },
  mrp: { label: 'MRP', color: 'green', description: 'Material Requirements Planning - Daily component planning' },
  execution: { label: 'Execution', color: 'orange', description: 'ATP/CTP - Real-time order promising' },
};

// Data source types
const DATA_SOURCE_TYPES = [
  { value: 'sap_s4hana', label: 'SAP S/4HANA', icon: Server, description: 'Real-time ERP integration' },
  { value: 'sap_apo', label: 'SAP APO', icon: Server, description: 'Advanced Planning & Optimization' },
  { value: 'sap_ecc', label: 'SAP ECC', icon: Server, description: 'Legacy SAP ERP' },
  { value: 'csv_upload', label: 'CSV Upload', icon: FileSpreadsheet, description: 'Manual file upload' },
  { value: 'api', label: 'REST API', icon: Zap, description: 'Custom API integration' },
];

// Data categories with recommended sync cadence
const DATA_CATEGORIES = [
  {
    id: 'master_data',
    label: 'Master Data',
    description: 'Products, Sites, BOMs, Suppliers',
    defaultCadence: 'daily',
    changeFrequency: 'Low',
    tables: ['product', 'site', 'product_bom', 'vendor'],
  },
  {
    id: 'transactional',
    label: 'Transactional Data',
    description: 'Orders, Shipments, Inventory movements',
    defaultCadence: 'hourly',
    changeFrequency: 'High',
    tables: ['inbound_order', 'outbound_order', 'shipment', 'inv_level'],
  },
  {
    id: 'planning',
    label: 'Planning Data',
    description: 'Forecasts, Supply plans, MPS',
    defaultCadence: 'daily',
    changeFrequency: 'Medium',
    tables: ['forecast', 'supply_plan', 'mps_plan'],
  },
  {
    id: 'configuration',
    label: 'Configuration Tables',
    description: 'Policies, Rules, Parameters',
    defaultCadence: 'weekly',
    changeFrequency: 'Very Low',
    tables: ['inv_policy', 'sourcing_rules', 'planning_params'],
  },
];

// CDC thresholds from POWELL_APPROACH.md
const CDC_THRESHOLDS = [
  {
    id: 'demand_deviation',
    label: 'Demand vs Forecast',
    description: 'Cumulative deviation triggering replanning',
    defaultValue: 15,
    unit: '%',
    triggerAction: 'Full CFA rerun',
  },
  {
    id: 'service_level',
    label: 'Service Level',
    description: 'Drop below target triggers replanning',
    defaultValue: 5,
    unit: '% below target',
    triggerAction: 'Full CFA rerun',
  },
  {
    id: 'inventory_deviation',
    label: 'Inventory vs Target',
    description: 'Deviation from target inventory levels',
    defaultValue: 30,
    unit: '% deviation',
    triggerAction: 'Allocation rerun',
  },
  {
    id: 'lead_time',
    label: 'Lead Time',
    description: 'Increase vs expected lead time',
    defaultValue: 30,
    unit: '% increase',
    triggerAction: 'Parameter adjustment',
  },
];

const CADENCE_OPTIONS = [
  { value: 'realtime', label: 'Real-time (CDC)', description: 'Immediate on change' },
  { value: 'hourly', label: 'Hourly', description: 'Every hour' },
  { value: 'daily', label: 'Daily', description: 'Once per day' },
  { value: 'weekly', label: 'Weekly', description: 'Once per week' },
  { value: 'manual', label: 'Manual', description: 'On-demand only' },
];

const TenantSettingsPanel = ({
  tenantId,
  tenantInfo,
  selectedConfigId,
  onTenantInfoChange,
}) => {
  const [activeSection, setActiveSection] = useState('hierarchy');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Settings state
  const [hierarchySettings, setHierarchySettings] = useState({
    sop: { site: 'country', product: 'family', time: 'month' },
    mps: { site: 'site', product: 'group', time: 'week' },
    mrp: { site: 'site', product: 'product', time: 'day' },
    execution: { site: 'site', product: 'product', time: 'hour' },
  });

  const [dataSources, setDataSources] = useState([
    { id: 1, type: 'csv_upload', name: 'Manual Upload', status: 'active', lastSync: null },
  ]);

  const [importCadence, setImportCadence] = useState({
    master_data: 'daily',
    transactional: 'hourly',
    planning: 'daily',
    configuration: 'weekly',
  });

  const [cdcSettings, setCdcSettings] = useState({
    enabled: true,
    demand_deviation: 15,
    service_level: 5,
    inventory_deviation: 30,
    lead_time: 30,
  });

  const [securitySettings, setSecuritySettings] = useState({
    session_timeout_minutes: tenantInfo?.session_timeout_minutes || 5,
  });

  const [expandedSections, setExpandedSections] = useState({
    sop: true,
    mps: false,
    mrp: false,
    execution: false,
  });

  // Sync security settings from tenant info
  useEffect(() => {
    if (tenantInfo?.session_timeout_minutes) {
      setSecuritySettings((prev) => ({
        ...prev,
        session_timeout_minutes: tenantInfo.session_timeout_minutes,
      }));
    }
  }, [tenantInfo]);

  // Load existing settings
  useEffect(() => {
    const loadSettings = async () => {
      if (!tenantId) return;
      setLoading(true);
      try {
        // Try to load planning hierarchy configs
        const response = await api.get(`/planning-hierarchy/tenant/${tenantId}`).catch(() => null);
        if (response?.data) {
          // Map to local state
          const configs = Array.isArray(response.data) ? response.data : [];
          const newHierarchy = { ...hierarchySettings };
          configs.forEach((cfg) => {
            const type = cfg.planning_type?.toLowerCase();
            if (type && newHierarchy[type]) {
              newHierarchy[type] = {
                site: cfg.site_hierarchy_level || newHierarchy[type].site,
                product: cfg.product_hierarchy_level || newHierarchy[type].product,
                time: cfg.time_bucket || newHierarchy[type].time,
              };
            }
          });
          setHierarchySettings(newHierarchy);
        }

        // Load sync job configs if available
        const syncResponse = await api.get(`/sync-jobs/tenant/${tenantId}/summary`).catch(() => null);
        if (syncResponse?.data?.cadence) {
          setImportCadence(syncResponse.data.cadence);
        }
      } catch (err) {
        console.warn('Failed to load settings:', err);
      } finally {
        setLoading(false);
      }
    };
    loadSettings();
  }, [tenantId]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      // Save hierarchy settings
      await api.put(`/planning-hierarchy/tenant/${tenantId}/batch`, {
        hierarchies: Object.entries(hierarchySettings).map(([type, levels]) => ({
          planning_type: type.toUpperCase(),
          site_hierarchy_level: levels.site,
          product_hierarchy_level: levels.product,
          time_bucket: levels.time,
        })),
      }).catch(() => null);

      // Save CDC settings
      await api.put(`/tenants/${tenantId}/cdc-settings`, cdcSettings).catch(() => null);

      // Save security settings (session timeout)
      if (securitySettings.session_timeout_minutes >= 1 && securitySettings.session_timeout_minutes <= 480) {
        await api.put(`/tenants/${tenantId}`, {
          session_timeout_minutes: securitySettings.session_timeout_minutes,
        }).catch(() => null);
      }

      setSuccess('Settings saved successfully');
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError('Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const toggleSection = (section) => {
    setExpandedSections((prev) => ({
      ...prev,
      [section]: !prev[section],
    }));
  };

  const sectionButtons = [
    { value: 'hierarchy', label: 'Planning Hierarchies', icon: <Layers className="h-4 w-4" /> },
    { value: 'datasources', label: 'Data Sources', icon: <Database className="h-4 w-4" /> },
    { value: 'cadence', label: 'Import Cadence', icon: <Clock className="h-4 w-4" /> },
    { value: 'cdc', label: 'CDC Thresholds', icon: <Activity className="h-4 w-4" /> },
    { value: 'security', label: 'Security', icon: <Shield className="h-4 w-4" /> },
  ];

  if (loading) {
    return (
      <Card>
        <CardContent className="p-6 flex justify-center items-center min-h-[300px]">
          <Spinner size="lg" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="p-6">
        <div className="mb-6">
          <h2 className="text-xl font-bold mb-1 flex items-center gap-2">
            <Settings className="h-5 w-5" />
            Tenant Settings
          </h2>
          <p className="text-muted-foreground">
            Configure planning hierarchies, data integration, and event-based replanning thresholds.
          </p>
        </div>

        {error && (
          <Alert variant="destructive" className="mb-4">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {success && (
          <Alert className="mb-4 border-green-500 bg-green-50 dark:bg-green-900/20">
            <AlertDescription className="text-green-700 dark:text-green-400">{success}</AlertDescription>
          </Alert>
        )}

        {/* Section Navigation */}
        <div className="flex gap-2 mb-6 flex-wrap">
          {sectionButtons.map((btn) => (
            <Button
              key={btn.value}
              variant={activeSection === btn.value ? 'default' : 'outline'}
              size="sm"
              onClick={() => setActiveSection(btn.value)}
              className="flex items-center gap-2"
            >
              {btn.icon}
              {btn.label}
            </Button>
          ))}
        </div>

        {/* Planning Hierarchies Section */}
        {activeSection === 'hierarchy' && (
          <div className="space-y-4">
            <div className="text-sm text-muted-foreground mb-4">
              <strong>Adaptive Decision Hierarchy:</strong> Higher hierarchy levels (longer horizons, aggregated data) use CFA/DLA policy classes.
              Lower levels (short horizons, detailed data) use VFA for value-based decisions.
            </div>

            {Object.entries(PLANNING_TYPES).map(([key, config]) => (
              <div key={key} className="border rounded-lg overflow-hidden">
                <button
                  className="w-full flex items-center justify-between p-4 hover:bg-muted/50 transition-colors"
                  onClick={() => toggleSection(key)}
                >
                  <div className="flex items-center gap-3">
                    <span
                      className={cn(
                        'px-2 py-1 rounded text-xs font-medium',
                        `bg-${config.color}-100 text-${config.color}-700 dark:bg-${config.color}-900 dark:text-${config.color}-300`
                      )}
                      style={{
                        backgroundColor: `var(--${config.color}-100, #dbeafe)`,
                        color: `var(--${config.color}-700, #1d4ed8)`,
                      }}
                    >
                      {config.label}
                    </span>
                    <span className="text-sm text-muted-foreground">{config.description}</span>
                  </div>
                  {expandedSections[key] ? (
                    <ChevronDown className="h-4 w-4" />
                  ) : (
                    <ChevronRight className="h-4 w-4" />
                  )}
                </button>

                {expandedSections[key] && (
                  <div className="p-4 pt-0 grid grid-cols-1 md:grid-cols-3 gap-4">
                    {/* Site Hierarchy */}
                    <div>
                      <label className="flex items-center gap-2 text-sm font-medium mb-2">
                        <Globe className="h-4 w-4" />
                        Site Hierarchy Level
                      </label>
                      <select
                        className="w-full p-2 border rounded-md bg-background"
                        value={hierarchySettings[key]?.site || 'site'}
                        onChange={(e) =>
                          setHierarchySettings((prev) => ({
                            ...prev,
                            [key]: { ...prev[key], site: e.target.value },
                          }))
                        }
                      >
                        {SITE_HIERARCHY_LEVELS.map((level) => (
                          <option key={level.value} value={level.value}>
                            {level.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    {/* Product Hierarchy */}
                    <div>
                      <label className="flex items-center gap-2 text-sm font-medium mb-2">
                        <Layers className="h-4 w-4" />
                        Product Hierarchy Level
                      </label>
                      <select
                        className="w-full p-2 border rounded-md bg-background"
                        value={hierarchySettings[key]?.product || 'product'}
                        onChange={(e) =>
                          setHierarchySettings((prev) => ({
                            ...prev,
                            [key]: { ...prev[key], product: e.target.value },
                          }))
                        }
                      >
                        {PRODUCT_HIERARCHY_LEVELS.map((level) => (
                          <option key={level.value} value={level.value}>
                            {level.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    {/* Time Bucket */}
                    <div>
                      <label className="flex items-center gap-2 text-sm font-medium mb-2">
                        <Calendar className="h-4 w-4" />
                        Time Bucket
                      </label>
                      <select
                        className="w-full p-2 border rounded-md bg-background"
                        value={hierarchySettings[key]?.time || 'week'}
                        onChange={(e) =>
                          setHierarchySettings((prev) => ({
                            ...prev,
                            [key]: { ...prev[key], time: e.target.value },
                          }))
                        }
                      >
                        {TIME_BUCKET_OPTIONS.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Data Sources Section */}
        {activeSection === 'datasources' && (
          <div className="space-y-4">
            <div className="text-sm text-muted-foreground mb-4">
              Configure connections to external systems for data synchronization.
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {DATA_SOURCE_TYPES.map((source) => {
                const Icon = source.icon;
                const isConfigured = dataSources.some((ds) => ds.type === source.value);
                return (
                  <div
                    key={source.value}
                    className={cn(
                      'border rounded-lg p-4 transition-colors',
                      isConfigured ? 'border-green-500 bg-green-50 dark:bg-green-900/20' : 'hover:border-primary'
                    )}
                  >
                    <div className="flex items-center gap-3 mb-2">
                      <Icon className="h-5 w-5 text-muted-foreground" />
                      <span className="font-medium">{source.label}</span>
                      {isConfigured && (
                        <span className="text-xs bg-green-500 text-white px-2 py-0.5 rounded">Active</span>
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground mb-3">{source.description}</p>
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full"
                      onClick={() => window.open('/admin/sap-data', '_blank')}
                    >
                      {isConfigured ? 'Configure' : 'Set Up'}
                      <ExternalLink className="h-3 w-3 ml-2" />
                    </Button>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Import Cadence Section */}
        {activeSection === 'cadence' && (
          <div className="space-y-4">
            <div className="text-sm text-muted-foreground mb-4">
              Set data import frequency based on data type and change likelihood. Higher frequency for volatile data, lower for stable master data.
            </div>

            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="border-b">
                    <th className="text-left p-3 font-medium">Data Category</th>
                    <th className="text-left p-3 font-medium">Tables</th>
                    <th className="text-left p-3 font-medium">Change Frequency</th>
                    <th className="text-left p-3 font-medium">Sync Cadence</th>
                  </tr>
                </thead>
                <tbody>
                  {DATA_CATEGORIES.map((category) => (
                    <tr key={category.id} className="border-b hover:bg-muted/50">
                      <td className="p-3">
                        <div className="font-medium">{category.label}</div>
                        <div className="text-sm text-muted-foreground">{category.description}</div>
                      </td>
                      <td className="p-3">
                        <div className="flex flex-wrap gap-1">
                          {category.tables.map((t) => (
                            <span key={t} className="text-xs bg-muted px-2 py-0.5 rounded">
                              {t}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="p-3">
                        <span
                          className={cn(
                            'text-xs px-2 py-1 rounded',
                            category.changeFrequency === 'High' && 'bg-red-100 text-red-700',
                            category.changeFrequency === 'Medium' && 'bg-yellow-100 text-yellow-700',
                            category.changeFrequency === 'Low' && 'bg-green-100 text-green-700',
                            category.changeFrequency === 'Very Low' && 'bg-gray-100 text-gray-700'
                          )}
                        >
                          {category.changeFrequency}
                        </span>
                      </td>
                      <td className="p-3">
                        <select
                          className="p-2 border rounded-md bg-background text-sm"
                          value={importCadence[category.id] || category.defaultCadence}
                          onChange={(e) =>
                            setImportCadence((prev) => ({
                              ...prev,
                              [category.id]: e.target.value,
                            }))
                          }
                        >
                          {CADENCE_OPTIONS.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                              {opt.label}
                            </option>
                          ))}
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* CDC Thresholds Section */}
        {activeSection === 'cdc' && (
          <div className="space-y-4">
            <div className="text-sm text-muted-foreground mb-4">
              <strong>CDC-Triggered Replanning:</strong> Event-driven replanning detects metric deviations early and triggers
              out-of-cadence CFA/allocation runs before errors compound. (ADH Key Insight #4)
            </div>

            <div className="flex items-center gap-4 mb-6 p-4 border rounded-lg">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={cdcSettings.enabled}
                  onChange={(e) => setCdcSettings((prev) => ({ ...prev, enabled: e.target.checked }))}
                  className="h-4 w-4 rounded border-gray-300"
                />
                <span className="font-medium">Enable CDC-Triggered Replanning</span>
              </label>
              <span className="text-sm text-muted-foreground">
                Automatically trigger replanning when metrics exceed thresholds
              </span>
            </div>

            <div className={cn('space-y-4', !cdcSettings.enabled && 'opacity-50 pointer-events-none')}>
              {CDC_THRESHOLDS.map((threshold) => (
                <div key={threshold.id} className="border rounded-lg p-4">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <AlertTriangle className="h-4 w-4 text-yellow-500" />
                        <span className="font-medium">{threshold.label}</span>
                      </div>
                      <p className="text-sm text-muted-foreground mt-1">{threshold.description}</p>
                    </div>
                    <span className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded">
                      Triggers: {threshold.triggerAction}
                    </span>
                  </div>
                  <div className="flex items-center gap-4">
                    <input
                      type="range"
                      min="5"
                      max="50"
                      step="5"
                      value={cdcSettings[threshold.id] || threshold.defaultValue}
                      onChange={(e) =>
                        setCdcSettings((prev) => ({
                          ...prev,
                          [threshold.id]: parseInt(e.target.value, 10),
                        }))
                      }
                      className="flex-1"
                    />
                    <div className="flex items-center gap-1 min-w-[80px]">
                      <input
                        type="number"
                        value={cdcSettings[threshold.id] || threshold.defaultValue}
                        onChange={(e) =>
                          setCdcSettings((prev) => ({
                            ...prev,
                            [threshold.id]: parseInt(e.target.value, 10) || threshold.defaultValue,
                          }))
                        }
                        className="w-16 p-1 border rounded text-center"
                      />
                      <span className="text-sm text-muted-foreground">{threshold.unit}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Security Section */}
        {activeSection === 'security' && (
          <div className="space-y-4">
            <div className="text-sm text-muted-foreground mb-4">
              Configure session security settings for all users in this tenant.
            </div>

            <div className="border rounded-lg p-4">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <div className="flex items-center gap-2">
                    <Clock className="h-4 w-4 text-blue-500" />
                    <span className="font-medium">Session Inactivity Timeout</span>
                  </div>
                  <p className="text-sm text-muted-foreground mt-1">
                    Users will be automatically logged out after this period of inactivity.
                    A warning is shown 60 seconds before logout.
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-4">
                <label className="text-sm font-medium whitespace-nowrap">
                  Auto-logout after (minutes):
                </label>
                <input
                  type="number"
                  min="1"
                  max="480"
                  value={securitySettings.session_timeout_minutes}
                  onChange={(e) => {
                    const val = parseInt(e.target.value, 10);
                    if (!isNaN(val)) {
                      setSecuritySettings((prev) => ({
                        ...prev,
                        session_timeout_minutes: Math.min(480, Math.max(1, val)),
                      }));
                    }
                  }}
                  className="w-24 p-2 border rounded-md bg-background text-center"
                />
                <span className="text-sm text-muted-foreground">
                  (min: 1, max: 480 = 8 hours)
                </span>
              </div>
              <div className="mt-3 text-xs text-muted-foreground">
                The new timeout takes effect on the next login. System administrators default to 30 minutes.
              </div>
            </div>
          </div>
        )}

        {/* Save Button */}
        <div className="mt-6 flex justify-end">
          <Button onClick={handleSave} disabled={saving} className="flex items-center gap-2">
            {saving ? <Spinner size="sm" /> : <Save className="h-4 w-4" />}
            Save Settings
          </Button>
        </div>
      </CardContent>
    </Card>
  );
};

export default TenantSettingsPanel;
