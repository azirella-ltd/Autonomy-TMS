/**
 * Metric Configuration Page
 *
 * Tenant admin page to configure which SCOR metrics are displayed
 * on the Hierarchical Metrics Dashboard, and to set custom targets.
 *
 * Reads/writes to SupplyChainConfig.metric_config JSONB via
 * GET/PUT /api/v1/hierarchical-metrics/config
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Alert,
  Badge,
  Button,
  Spinner,
} from '../../components/common';
import {
  Settings,
  Save,
  RotateCcw,
  Eye,
  EyeOff,
  Target,
  BarChart3,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import { api } from '../../services/api';
import { toast } from 'sonner';

const TIER_LABELS = {
  tier1_assess: { label: 'Tier 1 — ASSESS (Strategic)', description: 'Is our supply chain competitive?' },
  tier2_diagnose: { label: 'Tier 2 — DIAGNOSE (Tactical)', description: 'Where is value leaking?' },
  tier3_correct: { label: 'Tier 3 — CORRECT (Operational)', description: 'What specific action fixes it?' },
};

function MetricRow({ metricKey, config, catalogue, onChange }) {
  const cat = catalogue || {};
  const label = cat.label || metricKey.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  const scorCode = cat.scor_code;
  const unit = cat.unit || '';
  const description = cat.description || '';

  return (
    <div className="flex items-center gap-4 py-2 px-3 rounded hover:bg-gray-50 dark:hover:bg-gray-800">
      {/* Toggle */}
      <button
        onClick={() => onChange({ ...config, enabled: !config.enabled })}
        className={`p-1 rounded ${config.enabled ? 'text-green-600' : 'text-gray-400'}`}
        title={config.enabled ? 'Visible on dashboard' : 'Hidden from dashboard'}
      >
        {config.enabled ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
      </button>

      {/* Label */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className={`text-sm font-medium ${config.enabled ? '' : 'text-gray-400 line-through'}`}>
            {label}
          </span>
          {scorCode && (
            <Badge className="text-xs bg-blue-50 text-blue-600 dark:bg-blue-900 dark:text-blue-300">
              {scorCode}
            </Badge>
          )}
        </div>
        {description && (
          <p className="text-xs text-muted-foreground mt-0.5 truncate">{description}</p>
        )}
      </div>

      {/* Target input */}
      <div className="flex items-center gap-1.5 shrink-0">
        <Target className="w-3.5 h-3.5 text-muted-foreground" />
        <input
          type="number"
          step="any"
          value={config.target ?? ''}
          onChange={e => {
            const val = e.target.value === '' ? null : parseFloat(e.target.value);
            onChange({ ...config, target: val });
          }}
          placeholder="—"
          className="w-20 text-sm text-right border rounded px-2 py-1 bg-background"
          disabled={!config.enabled}
        />
        {unit && <span className="text-xs text-muted-foreground w-10">{unit}</span>}
      </div>
    </div>
  );
}

export default function MetricConfigPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [configData, setConfigData] = useState(null);
  const [catalogue, setCatalogue] = useState(null);
  const [dashboard, setDashboard] = useState({});
  const [expandedTiers, setExpandedTiers] = useState({
    tier1_assess: true,
    tier2_diagnose: true,
    tier3_correct: true,
  });
  const [dirty, setDirty] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [configRes, catRes] = await Promise.all([
        api.get('/v1/hierarchical-metrics/config'),
        api.get('/v1/hierarchical-metrics/catalogue'),
      ]);
      const cfg = configRes.data?.data || configRes.data;
      const cat = catRes.data?.data || catRes.data;
      setConfigData(cfg);
      setCatalogue(cat);
      setDashboard(cfg?.dashboard || {});
      setDirty(false);
    } catch (err) {
      toast.error('Failed to load metric configuration');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleMetricChange = (tierKey, metricKey, newConfig) => {
    setDashboard(prev => ({
      ...prev,
      [tierKey]: {
        ...(prev[tierKey] || {}),
        [metricKey]: newConfig,
      },
    }));
    setDirty(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put('/v1/hierarchical-metrics/config', { dashboard });
      toast.success('Metric configuration saved');
      setDirty(false);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save configuration');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    if (configData?.dashboard) {
      setDashboard(configData.dashboard);
    }
    setDirty(false);
  };

  const toggleTier = (tierKey) => {
    setExpandedTiers(prev => ({ ...prev, [tierKey]: !prev[tierKey] }));
  };

  const toggleAllInTier = (tierKey, enabled) => {
    const tierMetrics = dashboard[tierKey] || {};
    const allKeys = catalogue?.[tierKey] ? Object.keys(catalogue[tierKey]) : Object.keys(tierMetrics);
    const updated = {};
    allKeys.forEach(k => {
      updated[k] = { ...(tierMetrics[k] || { enabled: true, target: null }), enabled };
    });
    setDashboard(prev => ({ ...prev, [tierKey]: updated }));
    setDirty(true);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner className="w-8 h-8" />
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <BarChart3 className="w-6 h-6" />
            Metric Display Configuration
          </h1>
          <p className="text-muted-foreground mt-1">
            Choose which SCOR metrics appear on the Hierarchical Metrics Dashboard and set custom targets.
            {configData?.config_name && (
              <span className="ml-1 font-medium">Config: {configData.config_name}</span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={handleReset} disabled={!dirty}>
            <RotateCcw className="w-4 h-4 mr-1" /> Reset
          </Button>
          <Button onClick={handleSave} disabled={!dirty || saving}>
            {saving ? <Spinner className="w-4 h-4 mr-1" /> : <Save className="w-4 h-4 mr-1" />}
            Save
          </Button>
        </div>
      </div>

      {dirty && (
        <Alert variant="warning">
          You have unsaved changes. Click Save to apply.
        </Alert>
      )}

      {/* Tier cards */}
      {Object.entries(TIER_LABELS).map(([tierKey, tierInfo]) => {
        const tierMetrics = dashboard[tierKey] || {};
        const catMetrics = catalogue?.[tierKey] || {};
        const allKeys = Object.keys(catMetrics).length > 0 ? Object.keys(catMetrics) : Object.keys(tierMetrics);
        const enabledCount = allKeys.filter(k => (tierMetrics[k]?.enabled ?? true)).length;
        const expanded = expandedTiers[tierKey];

        return (
          <Card key={tierKey}>
            <CardHeader className="cursor-pointer" onClick={() => toggleTier(tierKey)}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                  <CardTitle className="text-base">{tierInfo.label}</CardTitle>
                  <Badge className="text-xs">{enabledCount}/{allKeys.length} visible</Badge>
                </div>
                <div className="flex items-center gap-2" onClick={e => e.stopPropagation()}>
                  <button
                    className="text-xs text-blue-600 hover:underline"
                    onClick={() => toggleAllInTier(tierKey, true)}
                  >
                    Show All
                  </button>
                  <span className="text-xs text-muted-foreground">|</span>
                  <button
                    className="text-xs text-blue-600 hover:underline"
                    onClick={() => toggleAllInTier(tierKey, false)}
                  >
                    Hide All
                  </button>
                </div>
              </div>
              <p className="text-sm text-muted-foreground ml-6">{tierInfo.description}</p>
            </CardHeader>
            {expanded && (
              <CardContent className="pt-0">
                <div className="divide-y">
                  {allKeys.map(metricKey => (
                    <MetricRow
                      key={metricKey}
                      metricKey={metricKey}
                      config={tierMetrics[metricKey] || { enabled: true, target: catMetrics[metricKey]?.default_target ?? null }}
                      catalogue={catMetrics[metricKey]}
                      onChange={(newCfg) => handleMetricChange(tierKey, metricKey, newCfg)}
                    />
                  ))}
                </div>
              </CardContent>
            )}
          </Card>
        );
      })}
    </div>
  );
}
