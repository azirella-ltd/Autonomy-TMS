/**
 * Stochastic Parameters Editor
 *
 * Per-agent stochastic variable management:
 * - View distribution parameters grouped by TRM agent type
 * - Edit individual distributions (marks them as manually edited)
 * - Reset to industry defaults
 * - Visual indicator of default vs edited/SAP-imported values
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
  RotateCcw,
  Save,
  Edit3,
  CheckCircle,
  Database,
  Upload,
  ChevronDown,
  ChevronRight,
  BarChart3,
  Sliders,
} from 'lucide-react';
import { api } from '../../services/api';
import { toast } from 'react-hot-toast';

const SOURCE_BADGES = {
  industry_default: { label: 'Industry Default', color: 'bg-blue-100 text-blue-700' },
  sap_import: { label: 'SAP Import', color: 'bg-green-100 text-green-700' },
  manual_edit: { label: 'Manual Edit', color: 'bg-amber-100 text-amber-700' },
};

const DIST_TYPE_LABELS = {
  lognormal: 'Lognormal',
  normal: 'Normal',
  beta: 'Beta',
  triangular: 'Triangular',
  weibull: 'Weibull',
  gamma: 'Gamma',
};

function DistributionSummary({ dist }) {
  if (!dist) return <span className="text-gray-400">None</span>;

  const type = DIST_TYPE_LABELS[dist.type] || dist.type;

  switch (dist.type) {
    case 'lognormal':
      return (
        <span>
          {type}: mean={dist.mean}, stddev={dist.stddev}
        </span>
      );
    case 'normal':
      return (
        <span>
          {type}: mean={dist.mean}, stddev={dist.stddev}
        </span>
      );
    case 'beta':
      return (
        <span>
          {type}: alpha={dist.alpha}, beta={dist.beta} (mean={dist.mean})
        </span>
      );
    case 'triangular':
      return (
        <span>
          {type}: min={dist.min}, mode={dist.mode}, max={dist.max}
        </span>
      );
    default:
      return <span>{type}: {JSON.stringify(dist)}</span>;
  }
}

function DistributionEditor({ distribution, onChange, onCancel, onSave }) {
  const [json, setJson] = useState(JSON.stringify(distribution, null, 2));
  const [error, setError] = useState(null);

  const handleSave = () => {
    try {
      const parsed = JSON.parse(json);
      if (!parsed.type) {
        setError('Distribution must have a "type" field');
        return;
      }
      setError(null);
      onSave(parsed);
    } catch (e) {
      setError('Invalid JSON: ' + e.message);
    }
  };

  return (
    <div className="mt-2 space-y-2">
      <textarea
        className="w-full font-mono text-xs bg-gray-50 border border-gray-300 rounded p-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        rows={6}
        value={json}
        onChange={(e) => setJson(e.target.value)}
      />
      {error && (
        <div className="text-red-600 text-xs">{error}</div>
      )}
      <div className="flex gap-2">
        <button
          onClick={handleSave}
          className="px-3 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 flex items-center gap-1"
        >
          <Save size={12} /> Save
        </button>
        <button
          onClick={onCancel}
          className="px-3 py-1 text-xs bg-gray-200 text-gray-700 rounded hover:bg-gray-300"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

function ParamRow({ param, onEdit, onReset }) {
  const [editing, setEditing] = useState(false);
  const badge = SOURCE_BADGES[param.source] || SOURCE_BADGES.industry_default;

  const handleSave = async (newDist) => {
    await onEdit(param.id, newDist);
    setEditing(false);
  };

  return (
    <div className="border-b border-gray-100 py-3 px-4 hover:bg-gray-50/50">
      <div className="flex items-center justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className="font-medium text-sm text-gray-900">
              {param.param_label}
            </span>
            <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${badge.color}`}>
              {badge.label}
            </span>
          </div>
          <div className="text-xs text-gray-500 mt-1 font-mono">
            <DistributionSummary dist={param.distribution} />
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setEditing(!editing)}
            className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded"
            title="Edit distribution"
          >
            <Edit3 size={14} />
          </button>
          {!param.is_default && (
            <button
              onClick={() => onReset(param.id)}
              className="p-1.5 text-gray-400 hover:text-orange-600 hover:bg-orange-50 rounded"
              title="Reset to industry default"
            >
              <RotateCcw size={14} />
            </button>
          )}
        </div>
      </div>
      {editing && (
        <DistributionEditor
          distribution={param.distribution}
          onCancel={() => setEditing(false)}
          onSave={handleSave}
        />
      )}
    </div>
  );
}

function TRMSection({ trmType, trmLabel, params, onEdit, onReset }) {
  const [expanded, setExpanded] = useState(true);
  const editedCount = params.filter((p) => !p.is_default).length;

  return (
    <div className="border border-gray-200 rounded-lg mb-3 overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-gray-100 transition-colors"
      >
        <div className="flex items-center gap-2">
          {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          <Sliders size={16} className="text-blue-600" />
          <span className="font-semibold text-sm text-gray-800">{trmLabel}</span>
          <span className="text-xs text-gray-500">
            ({params.length} parameter{params.length !== 1 ? 's' : ''})
          </span>
        </div>
        <div className="flex items-center gap-2">
          {editedCount > 0 && (
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-700">
              {editedCount} edited
            </span>
          )}
          {editedCount === 0 && (
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-700">
              All defaults
            </span>
          )}
        </div>
      </button>
      {expanded && (
        <div className="divide-y divide-gray-100">
          {params.map((p) => (
            <ParamRow
              key={p.id}
              param={p}
              onEdit={onEdit}
              onReset={onReset}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function PipelineSettings({ configId }) {
  const [settings, setSettings] = useState(null);
  const [labels, setLabels] = useState({});
  const [defaults, setDefaults] = useState({});
  const [editing, setEditing] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!configId) return;
    setLoading(true);
    api
      .get(`/agent-stochastic-params/pipeline-config/${configId}`)
      .then((res) => {
        setSettings(res.data.settings);
        setLabels(res.data.labels);
        setDefaults(res.data.defaults);
        setEditing({ ...res.data.settings });
      })
      .catch(() => toast.error('Failed to load pipeline settings'))
      .finally(() => setLoading(false));
  }, [configId]);

  const handleSave = async () => {
    try {
      const res = await api.put(
        `/agent-stochastic-params/pipeline-config/${configId}`,
        { settings: editing }
      );
      setSettings(res.data.settings);
      setEditing({ ...res.data.settings });
      toast.success('Pipeline settings saved');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save settings');
    }
  };

  const handleReset = () => {
    setEditing({ ...defaults });
  };

  const hasChanges =
    settings && JSON.stringify(editing) !== JSON.stringify(settings);

  if (loading || !settings) return null;

  return (
    <div className="mb-6 border border-gray-200 rounded-lg overflow-hidden">
      <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Settings size={16} className="text-gray-600" />
            <span className="font-semibold text-sm text-gray-800">
              Pipeline Settings
            </span>
            <span className="text-xs text-gray-500">
              (SAP extraction thresholds and distribution fitting)
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleReset}
              className="px-3 py-1 text-xs bg-gray-200 text-gray-700 rounded hover:bg-gray-300 flex items-center gap-1"
            >
              <RotateCcw size={12} /> Reset to Defaults
            </button>
            <button
              onClick={handleSave}
              disabled={!hasChanges}
              className={`px-3 py-1 text-xs rounded flex items-center gap-1 ${
                hasChanges
                  ? 'bg-blue-600 text-white hover:bg-blue-700'
                  : 'bg-gray-100 text-gray-400 cursor-not-allowed'
              }`}
            >
              <Save size={12} /> Save
            </button>
          </div>
        </div>
      </div>
      <div className="p-4 grid grid-cols-2 gap-4">
        {Object.entries(labels).map(([key, label]) => {
          const isDefault = editing[key] === defaults[key];
          return (
            <div key={key} className="space-y-1">
              <label className="block text-xs font-medium text-gray-700">
                {label}
                {isDefault && (
                  <span className="ml-1 text-gray-400 font-normal">
                    (default)
                  </span>
                )}
              </label>
              <input
                type="number"
                step={key === 'cv_lognormal_threshold' ? '0.1' : '1'}
                className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                value={editing[key] ?? ''}
                onChange={(e) => {
                  const val =
                    key === 'cv_lognormal_threshold'
                      ? parseFloat(e.target.value)
                      : parseInt(e.target.value, 10);
                  setEditing((prev) => ({ ...prev, [key]: isNaN(val) ? '' : val }));
                }}
              />
              <div className="text-xs text-gray-400">
                System default: {defaults[key]}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const StochasticParamsEditor = () => {
  const [loading, setLoading] = useState(true);
  const [params, setParams] = useState([]);
  const [configs, setConfigs] = useState([]);
  const [selectedConfigId, setSelectedConfigId] = useState(null);
  const [error, setError] = useState(null);

  // Load supply chain configs on mount
  useEffect(() => {
    const loadConfigs = async () => {
      try {
        const res = await api.get('/supply-chain-configs');
        const cfgs = res.data || [];
        setConfigs(cfgs);
        if (cfgs.length > 0) {
          setSelectedConfigId(cfgs[0].id);
        }
      } catch (err) {
        setError('Failed to load supply chain configs');
      }
    };
    loadConfigs();
  }, []);

  // Load params whenever config changes
  const loadParams = useCallback(async () => {
    if (!selectedConfigId) return;
    setLoading(true);
    try {
      const res = await api.get('/agent-stochastic-params/', {
        params: { config_id: selectedConfigId },
      });
      setParams(res.data || []);
      setError(null);
    } catch (err) {
      setError('Failed to load stochastic parameters');
      setParams([]);
    } finally {
      setLoading(false);
    }
  }, [selectedConfigId]);

  useEffect(() => {
    loadParams();
  }, [loadParams]);

  const handleEdit = async (paramId, newDist) => {
    try {
      await api.put(`/agent-stochastic-params/${paramId}`, {
        distribution: newDist,
      });
      toast.success('Parameter updated');
      loadParams();
    } catch (err) {
      toast.error('Failed to update parameter');
    }
  };

  const handleReset = async (paramId) => {
    try {
      await api.post(`/agent-stochastic-params/${paramId}/reset`);
      toast.success('Reset to industry default');
      loadParams();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to reset parameter');
    }
  };

  // Group params by TRM type
  const grouped = {};
  params.forEach((p) => {
    if (!grouped[p.trm_type]) {
      grouped[p.trm_type] = {
        label: p.trm_label,
        params: [],
      };
    }
    grouped[p.trm_type].params.push(p);
  });

  const totalParams = params.length;
  const defaultCount = params.filter((p) => p.is_default).length;
  const editedCount = totalParams - defaultCount;
  const sapCount = params.filter((p) => p.source === 'sap_import').length;

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <BarChart3 className="text-blue-600" size={28} />
            Stochastic Parameters
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Per-agent distribution parameters for stochastic simulation and planning
          </p>
        </div>
      </div>

      {/* Config selector */}
      <div className="mb-4">
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Supply Chain Configuration
        </label>
        <select
          className="w-full max-w-md border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          value={selectedConfigId || ''}
          onChange={(e) => setSelectedConfigId(Number(e.target.value))}
        >
          {configs.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} (ID: {c.id})
            </option>
          ))}
        </select>
      </div>

      {/* Pipeline settings */}
      {selectedConfigId && <PipelineSettings configId={selectedConfigId} />}

      {/* Stats bar */}
      {!loading && params.length > 0 && (
        <div className="grid grid-cols-4 gap-3 mb-6">
          <div className="bg-white border border-gray-200 rounded-lg p-3 text-center">
            <div className="text-2xl font-bold text-gray-900">{totalParams}</div>
            <div className="text-xs text-gray-500">Total Parameters</div>
          </div>
          <div className="bg-white border border-blue-200 rounded-lg p-3 text-center">
            <div className="text-2xl font-bold text-blue-600">{defaultCount}</div>
            <div className="text-xs text-gray-500 flex items-center justify-center gap-1">
              <Database size={10} /> Industry Defaults
            </div>
          </div>
          <div className="bg-white border border-amber-200 rounded-lg p-3 text-center">
            <div className="text-2xl font-bold text-amber-600">{editedCount}</div>
            <div className="text-xs text-gray-500 flex items-center justify-center gap-1">
              <Edit3 size={10} /> Manually Edited
            </div>
          </div>
          <div className="bg-white border border-green-200 rounded-lg p-3 text-center">
            <div className="text-2xl font-bold text-green-600">{sapCount}</div>
            <div className="text-xs text-gray-500 flex items-center justify-center gap-1">
              <Upload size={10} /> SAP Imported
            </div>
          </div>
        </div>
      )}

      {error && (
        <Alert variant="destructive" className="mb-4">
          {error}
        </Alert>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Spinner size="lg" />
          <span className="ml-3 text-gray-500">Loading parameters...</span>
        </div>
      ) : params.length === 0 ? (
        <div className="text-center py-20 bg-white border border-gray-200 rounded-lg">
          <Settings size={48} className="mx-auto text-gray-300 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-2">No Parameters Found</h3>
          <p className="text-sm text-gray-500 max-w-md mx-auto">
            Stochastic parameters are automatically populated when a tenant is created with
            an industry selection. If this config was created before the industry feature,
            update the tenant's industry to generate defaults.
          </p>
        </div>
      ) : (
        <div>
          {Object.entries(grouped).map(([trmType, group]) => (
            <TRMSection
              key={trmType}
              trmType={trmType}
              trmLabel={group.label}
              params={group.params}
              onEdit={handleEdit}
              onReset={handleReset}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export default StochasticParamsEditor;
