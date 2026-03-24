import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { api } from '../../services/api';
import {
  BookOpen,
  Upload,
  Search,
  Settings,
  Trash2,
  FileText,
  AlertTriangle,
  CheckCircle,
  Loader2,
  Database,
  Cpu,
  Hash,
  Link,
  Plus,
} from 'lucide-react';

// ============================================================================
// Constants
// ============================================================================

const CATEGORIES = [
  { value: 'sop_ibp', label: 'S&OP / Integrated Business Planning' },
  { value: 'demand_planning', label: 'Demand Planning & Forecasting' },
  { value: 'supply_planning', label: 'Supply Planning' },
  { value: 'mps_mrp', label: 'MPS / Material Requirements Planning' },
  { value: 'inventory_optimization', label: 'Inventory Optimization' },
  { value: 'atp_ctp', label: 'ATP / CTP / Available-to-Promise' },
  { value: 'capacity_planning', label: 'Capacity Planning' },
  { value: 'network_design', label: 'Network Design' },
  { value: 'order_execution', label: 'Order Execution' },
  { value: 'drp_distribution', label: 'DRP / Distribution' },
  { value: 'scor_framework', label: 'SCOR Framework' },
  { value: 'decision_framework', label: 'Decision Framework (Powell SDAM)' },
  { value: 'ai_planning', label: 'AI / Agentic Planning' },
  { value: 'ai_ml', label: 'AI / ML Models' },
  { value: 'stochastic_planning', label: 'Stochastic / Probabilistic Planning' },
  { value: 'analyst_reports', label: 'Analyst Reports (Gartner, McKinsey, etc.)' },
  { value: 'academic_planning', label: 'Academic / Research' },
  { value: 'planning_strategy', label: 'Planning Methodology & Strategy' },
  { value: 'existing_research', label: 'Internal / Private Research' },
  { value: 'strategy', label: 'Business Strategy' },
  { value: 'internal_docs', label: 'Internal Documents' },
  { value: 'general', label: 'General' },
];

// ============================================================================
// Sub-components
// ============================================================================

const StatusBadge = ({ status }) => {
  const colors = {
    indexed: 'bg-green-100 text-green-800',
    processing: 'bg-blue-100 text-blue-800',
    pending: 'bg-yellow-100 text-yellow-800',
    failed: 'bg-red-100 text-red-800',
  };
  return (
    <span className={`px-2 py-1 rounded-full text-xs font-medium ${colors[status] || 'bg-gray-100 text-gray-800'}`}>
      {status}
    </span>
  );
};

const formatFileSize = (bytes) => {
  if (!bytes) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

// ============================================================================
// Documents Tab
// ============================================================================

const DocumentsTab = ({ documents, loading, onUpload, onDelete, onRefresh }) => {
  const [uploading, setUploading] = useState(false);
  const [uploadForm, setUploadForm] = useState({
    title: '',
    category: '',
    description: '',
    tags: '',
  });

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      if (uploadForm.title) formData.append('title', uploadForm.title);
      if (uploadForm.category) formData.append('category', uploadForm.category);
      if (uploadForm.description) formData.append('description', uploadForm.description);
      if (uploadForm.tags) formData.append('tags', uploadForm.tags);

      await api.post('/knowledge-base/documents', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setUploadForm({ title: '', category: '', description: '', tags: '' });
      onRefresh();
    } catch (err) {
      alert(`Upload failed: ${err.response?.data?.detail || err.message}`);
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  return (
    <div className="space-y-6">
      {/* Upload Section */}
      <div className="bg-white rounded-lg border p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Upload className="w-5 h-5" />
          Upload Document
        </h3>
        <div className="grid grid-cols-2 gap-4 mb-4">
          <input
            type="text"
            placeholder="Title (optional)"
            value={uploadForm.title}
            onChange={(e) => setUploadForm({ ...uploadForm, title: e.target.value })}
            className="border rounded px-3 py-2 text-sm"
          />
          <select
            value={uploadForm.category}
            onChange={(e) => setUploadForm({ ...uploadForm, category: e.target.value })}
            className="border rounded px-3 py-2 text-sm"
          >
            <option value="">Category (optional)</option>
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
          <input
            type="text"
            placeholder="Description (optional)"
            value={uploadForm.description}
            onChange={(e) => setUploadForm({ ...uploadForm, description: e.target.value })}
            className="border rounded px-3 py-2 text-sm"
          />
          <input
            type="text"
            placeholder="Tags (comma-separated)"
            value={uploadForm.tags}
            onChange={(e) => setUploadForm({ ...uploadForm, tags: e.target.value })}
            className="border rounded px-3 py-2 text-sm"
          />
        </div>
        <label className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded cursor-pointer hover:bg-blue-700 transition-colors text-sm">
          {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
          {uploading ? 'Processing...' : 'Choose File (PDF, DOCX, TXT, MD)'}
          <input
            type="file"
            accept=".pdf,.docx,.txt,.md,.csv"
            onChange={handleFileUpload}
            disabled={uploading}
            className="hidden"
          />
        </label>
      </div>

      {/* Documents List */}
      <div className="bg-white rounded-lg border">
        <div className="px-6 py-4 border-b flex items-center justify-between">
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <FileText className="w-5 h-5" />
            Documents ({documents.length})
          </h3>
          <button
            onClick={onRefresh}
            className="text-sm text-blue-600 hover:text-blue-800"
          >
            Refresh
          </button>
        </div>

        {loading ? (
          <div className="p-8 text-center text-gray-500">
            <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" />
            Loading documents...
          </div>
        ) : documents.length === 0 ? (
          <div className="p-8 text-center text-gray-500">
            No documents uploaded yet. Upload a PDF, DOCX, or TXT file to get started.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left font-medium text-gray-600">Title</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-600">Type</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-600">Size</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-600">Chunks</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-600">Category</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-600">Status</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-600">Uploaded</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-600">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {documents.map((doc) => (
                  <tr key={doc.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium">{doc.title}</td>
                    <td className="px-4 py-3 uppercase text-gray-500">{doc.file_type}</td>
                    <td className="px-4 py-3 text-gray-500">{formatFileSize(doc.file_size)}</td>
                    <td className="px-4 py-3">{doc.chunk_count}</td>
                    <td className="px-4 py-3 text-gray-500">{doc.category || '—'}</td>
                    <td className="px-4 py-3"><StatusBadge status={doc.status} /></td>
                    <td className="px-4 py-3 text-gray-500">
                      {doc.created_at ? new Date(doc.created_at).toLocaleDateString() : '—'}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => onDelete(doc.id)}
                        className="text-red-500 hover:text-red-700"
                        title="Delete document"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

// ============================================================================
// Search Tab
// ============================================================================

const SearchTab = () => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setSearching(true);
    setSearched(true);
    try {
      const response = await api.post('/knowledge-base/search', {
        query: query.trim(),
        top_k: 10,
      });
      setResults(response.data.results || []);
    } catch (err) {
      alert(`Search failed: ${err.response?.data?.detail || err.message}`);
      setResults([]);
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Search Input */}
      <div className="bg-white rounded-lg border p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Search className="w-5 h-5" />
          Semantic Search
        </h3>
        <div className="flex gap-3">
          <input
            type="text"
            placeholder="Ask a question about your documents... (e.g., 'What are the Q3 safety stock targets?')"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            className="flex-1 border rounded px-4 py-2"
          />
          <button
            onClick={handleSearch}
            disabled={searching || !query.trim()}
            className="px-6 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {searching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
            Search
          </button>
        </div>
      </div>

      {/* Results */}
      {searching ? (
        <div className="text-center py-8 text-gray-500">
          <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" />
          Searching knowledge base...
        </div>
      ) : results.length > 0 ? (
        <div className="space-y-4">
          {results.map((result, idx) => (
            <div key={result.chunk_id} className="bg-white rounded-lg border p-4">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-gray-400">#{idx + 1}</span>
                  <span className="text-sm font-semibold">{result.document_title}</span>
                  {result.page_number && (
                    <span className="text-xs text-gray-500">p. {result.page_number}</span>
                  )}
                </div>
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                  result.score > 0.8 ? 'bg-green-100 text-green-700' :
                  result.score > 0.6 ? 'bg-yellow-100 text-yellow-700' :
                  'bg-gray-100 text-gray-600'
                }`}>
                  {(result.score * 100).toFixed(1)}% match
                </span>
              </div>
              <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">
                {result.content}
              </p>
            </div>
          ))}
        </div>
      ) : searched ? (
        <div className="text-center py-8 text-gray-500">
          No results found. Try a different query or upload more documents.
        </div>
      ) : null}
    </div>
  );
};

// ============================================================================
// Market Intelligence Tab — Standard + Custom Sources
// ============================================================================

// Tier definitions for badge rendering
const TIER_OPEN = 'open';
const TIER_FREE = 'free';
const TIER_PAID = 'paid';

const TIER_META = {
  [TIER_OPEN]: { label: 'Open', color: 'bg-green-100 text-green-700', dot: 'bg-green-500' },
  [TIER_FREE]: { label: 'Free', color: 'bg-blue-100 text-blue-700', dot: 'bg-blue-500' },
  [TIER_PAID]: { label: 'Paid', color: 'bg-purple-100 text-purple-700', dot: 'bg-purple-500' },
};

// ── Standard source definitions with tier classification ─────────────────────

const STANDARD_SOURCES = [
  // Completely Open (no registration)
  { key: 'open_meteo', name: 'Open-Meteo', desc: 'Temperature extremes, precipitation, severe weather by site and lane locations', tier: TIER_OPEN },
  { key: 'gdelt', name: 'GDELT', desc: 'Supply chain disruptions, port strikes, trade sanctions, factory shutdowns', tier: TIER_OPEN },
  { key: 'openfda', name: 'openFDA', desc: 'FDA recalls, safety alerts, enforcement actions matching your product categories', tier: TIER_OPEN },
  { key: 'google_trends', name: 'Google Trends', desc: 'Consumer search interest for your product keywords (demand sensing)', tier: TIER_OPEN },
  { key: 'reddit_sentiment', name: 'Reddit', desc: 'Frontline worker sentiment from industry subreddits — leading indicator for demand and supply shifts', tier: TIER_OPEN },

  // Free with Registration
  { key: 'fred', name: 'FRED API', desc: 'Economic indicators: CPI, PPI, unemployment, consumer sentiment, oil, gas, treasury, dollar index', tier: TIER_FREE, keyEnv: 'FRED_API_KEY', keyUrl: 'https://fred.stlouisfed.org/docs/api/api_key.html' },
  { key: 'eia', name: 'EIA API', desc: 'Energy prices: WTI crude, natural gas, diesel — affects logistics and manufacturing costs', tier: TIER_FREE, keyEnv: 'EIA_API_KEY', keyUrl: 'https://www.eia.gov/opendata/register.php' },

  // Paid Subscription
  { key: 'newsapi', name: 'NewsAPI', desc: 'Headline sentiment analysis from 80K+ sources. Free tier: 100 req/day', tier: TIER_PAID, keyEnv: 'NEWSAPI_KEY', keyUrl: 'https://newsapi.org/pricing' },
];

const SourcesTab = ({ onRefresh }) => {
  // ── Standard sources state ──────────────────────────────────────────
  const [sources, setSources] = useState([]);
  const [sourcesLoading, setSourcesLoading] = useState(true);
  const [activating, setActivating] = useState(false);
  const [expandedApiKey, setExpandedApiKey] = useState(null);

  // ── Config selector ─────────────────────────────────────────────────
  const [configs, setConfigs] = useState([]);
  const [selectedConfigId, setSelectedConfigId] = useState(null);

  // ── Custom URL sources state ────────────────────────────────────────
  const [customForm, setCustomForm] = useState({ url: '', title: '', category: '', tags: '', refreshFreq: 'one-time', username: '', password: '', apiKey: '' });
  const [ingesting, setIngesting] = useState(false);
  const [ingestResult, setIngestResult] = useState(null);
  const [ingestError, setIngestError] = useState(null);
  const [showCustomForm, setShowCustomForm] = useState(false);

  // ── Load ────────────────────────────────────────────────────────────

  const loadSources = useCallback(async () => {
    setSourcesLoading(true);
    try {
      const res = await api.get('/external-signals/sources');
      setSources(res.data?.sources || []);
    } catch { /* ignore */ }
    setSourcesLoading(false);
  }, []);

  const loadConfigs = useCallback(async () => {
    try {
      const res = await api.get('/supply-chain-configs');
      const cfgs = Array.isArray(res.data) ? res.data : res.data?.configs || [];
      setConfigs(cfgs);
      const active = cfgs.find(c => c.is_active);
      if (active) setSelectedConfigId(active.id);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadSources(); loadConfigs(); }, [loadSources, loadConfigs]);

  // ── Standard source actions ─────────────────────────────────────────

  const getSource = (key) => sources.find(s => s.source_key === key);

  const handleActivateAll = async () => {
    if (!selectedConfigId) return;
    setActivating(true);
    try {
      await api.post(`/external-signals/sources/activate-defaults?config_id=${selectedConfigId}`);
      await loadSources();
    } catch { /* ignore */ }
    setActivating(false);
  };

  const handleToggle = async (sourceKey) => {
    const src = getSource(sourceKey);
    if (src) {
      try {
        await api.put(`/external-signals/sources/${src.id}/toggle?is_active=${!src.is_active}`);
        await loadSources();
      } catch { /* ignore */ }
    } else if (selectedConfigId) {
      try {
        await api.post(`/external-signals/sources?source_key=${sourceKey}&config_id=${selectedConfigId}`);
        await loadSources();
      } catch { /* ignore */ }
    }
  };

  const handleRefreshSource = async (sourceKey) => {
    const src = getSource(sourceKey);
    if (!src) return;
    try {
      await api.post(`/external-signals/refresh/${src.id}`);
      await loadSources();
    } catch { /* ignore */ }
  };

  // ── Custom URL actions ──────────────────────────────────────────────

  const handleIngestUrl = async () => {
    if (!customForm.url.trim()) return;
    setIngesting(true);
    setIngestResult(null);
    setIngestError(null);
    try {
      const payload = {
        url: customForm.url.trim(),
        title: customForm.title.trim() || null,
        category: customForm.category || null,
        tags: customForm.tags ? customForm.tags.split(',').map(t => t.trim()).filter(Boolean) : null,
      };
      if (customForm.username) payload.auth_username = customForm.username;
      if (customForm.password) payload.auth_password = customForm.password;
      if (customForm.apiKey) payload.auth_api_key = customForm.apiKey;

      const response = await api.post('/knowledge-base/ingest-url', payload);
      setIngestResult(response.data.document);
      setCustomForm({ url: '', title: '', category: '', tags: '', refreshFreq: 'one-time', username: '', password: '', apiKey: '' });
      setShowCustomForm(false);
      onRefresh();
    } catch (err) {
      setIngestError(err.response?.data?.detail || err.message);
    } finally {
      setIngesting(false);
    }
  };

  // ── Tier badge component ────────────────────────────────────────────
  const TierBadge = ({ tier }) => {
    const meta = TIER_META[tier];
    if (!meta) return null;
    return (
      <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${meta.color}`}>
        {meta.label}
      </span>
    );
  };

  // ── Toggle switch component ─────────────────────────────────────────
  const ToggleSwitch = ({ checked, onChange, disabled }) => (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={onChange}
      className={`relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 disabled:opacity-50 disabled:cursor-not-allowed ${
        checked ? 'bg-blue-600' : 'bg-gray-200'
      }`}
    >
      <span
        className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
          checked ? 'translate-x-4' : 'translate-x-0'
        }`}
      />
    </button>
  );

  // ── Group sources by tier ───────────────────────────────────────────
  const tierGroups = [
    { tier: TIER_OPEN, title: 'Completely Open', subtitle: 'No registration required' },
    { tier: TIER_FREE, title: 'Free with Registration', subtitle: 'Requires a free API key' },
    { tier: TIER_PAID, title: 'Paid Subscription', subtitle: 'Commercial API plans' },
  ];

  // ── Render ──────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* ── Config selector ──────────────────────────────────────────── */}
      <div className="bg-white rounded-lg border p-5">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-base font-semibold">Supply Chain Configuration</h3>
            <p className="text-sm text-gray-500">
              Sources are auto-configured from your network — site locations, freight lanes, products, and industry.
            </p>
          </div>
          <button
            onClick={handleActivateAll}
            disabled={activating || !selectedConfigId}
            className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium"
          >
            {activating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Database className="w-4 h-4" />}
            {sources.length > 0 ? 'Reconfigure from Network' : 'Configure from Network'}
          </button>
        </div>
        <select
          value={selectedConfigId || ''}
          onChange={e => setSelectedConfigId(e.target.value ? Number(e.target.value) : null)}
          className="w-full max-w-lg border rounded-md px-3 py-2 text-sm"
        >
          <option value="">Select a supply chain config...</option>
          {configs.map(c => (
            <option key={c.id} value={c.id}>
              {c.name} {c.is_active ? '(active)' : ''}
            </option>
          ))}
        </select>
      </div>

      {/* ── Standard Sources ─────────────────────────────────────────── */}
      <div className="bg-white rounded-lg border">
        <div className="px-5 py-3 border-b">
          <h3 className="text-base font-semibold">Standard Sources</h3>
          <p className="text-xs text-gray-500">Built-in market intelligence feeds — auto-configured from your DAG topology. Refreshed daily at 05:30.</p>
        </div>

        {tierGroups.map(group => {
          const groupSources = STANDARD_SOURCES.filter(s => s.tier === group.tier);
          if (groupSources.length === 0) return null;

          return (
            <div key={group.tier}>
              {/* Tier group header */}
              <div className="px-5 py-2 bg-gray-50 border-b border-t flex items-center gap-2">
                <TierBadge tier={group.tier} />
                <span className="text-xs font-medium text-gray-600">{group.title}</span>
                <span className="text-[10px] text-gray-400">— {group.subtitle}</span>
              </div>

              <div className="divide-y">
                {groupSources.map(std => {
                  const src = getSource(std.key);
                  const active = src?.is_active ?? false;
                  const hasSignals = (src?.signals_collected || 0) > 0;
                  const lastRefresh = src?.last_refresh_at;
                  const needsKey = !!std.keyEnv;
                  const apiKeyExpanded = expandedApiKey === std.key;

                  const isPaid = std.tier === TIER_PAID;
                  const isFree = std.tier === TIER_FREE;
                  const isOpen = std.tier === TIER_OPEN;
                  // Free/Paid: disable toggle until API key is configured
                  const keyConfigured = src?.api_key_encrypted || false;
                  const canToggle = isOpen || keyConfigured;

                  return (
                    <div key={std.key} className="px-5 py-3 hover:bg-gray-50/50 transition-colors">
                      <div className="flex items-center gap-3">
                        {/* Toggle switch — disabled for Free/Paid until API key entered */}
                        <div className="relative">
                          <ToggleSwitch
                            checked={active}
                            onChange={() => canToggle ? handleToggle(std.key) : setExpandedApiKey(std.key)}
                          />
                          {!canToggle && (
                            <div className="absolute -bottom-3 left-0 text-[9px] text-amber-600 whitespace-nowrap">
                              Key required
                            </div>
                          )}
                        </div>

                        {/* Name and description */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className={`text-sm font-medium ${active ? 'text-gray-900' : 'text-gray-500'}`}>
                              {std.name}
                            </span>
                          </div>
                          <p className="text-xs text-gray-400 leading-tight mt-0.5">{std.desc}</p>

                          {/* Free tier: API key always visible inline */}
                          {isFree && (
                            <div className="mt-2 flex items-center gap-2 max-w-md">
                              <input
                                type="password"
                                placeholder={`Enter ${std.keyEnv} key`}
                                className="flex-1 border rounded px-2 py-1 text-xs font-mono"
                                autoComplete="new-password"
                              />
                              {std.keyUrl && (
                                <a
                                  href={std.keyUrl}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-[10px] text-blue-600 hover:text-blue-800 whitespace-nowrap"
                                >
                                  Get free key &rarr;
                                </a>
                              )}
                              <button className="text-xs px-2 py-1 rounded bg-primary text-white hover:bg-primary/90">
                                Save
                              </button>
                            </div>
                          )}

                          {/* Paid tier: API key + Advanced config, expandable */}
                          {isPaid && (
                            <div className="mt-2">
                              <div className="flex items-center gap-2 max-w-md">
                                <input
                                  type="password"
                                  placeholder={`Enter ${std.keyEnv || 'API'} key`}
                                  className="flex-1 border rounded px-2 py-1 text-xs font-mono"
                                  autoComplete="new-password"
                                />
                                <button className="text-xs px-2 py-1 rounded bg-primary text-white hover:bg-primary/90">
                                  Save
                                </button>
                              </div>
                              <button
                                onClick={() => setExpandedApiKey(apiKeyExpanded ? null : std.key)}
                                className="text-[10px] text-gray-500 hover:text-gray-700 mt-1"
                              >
                                {apiKeyExpanded ? '▾ Hide advanced' : '▸ Advanced settings'}
                              </button>
                              {apiKeyExpanded && (
                                <div className="mt-1 space-y-1 max-w-md pl-2 border-l-2 border-gray-200">
                                  <input placeholder="Subscription tier" className="w-full border rounded px-2 py-1 text-xs" />
                                  <input placeholder="Rate limit (req/day)" className="w-full border rounded px-2 py-1 text-xs" />
                                  <input placeholder="Custom endpoint URL" className="w-full border rounded px-2 py-1 text-xs" />
                                  <p className="text-[10px] text-gray-400">Contact provider for API access details</p>
                                </div>
                              )}
                            </div>
                          )}

                          {/* Open tier: nothing extra needed — just the toggle */}
                          {/* Show DAG-derived params when active */}
                          {active && src?.source_params && (
                            <div className="flex flex-wrap gap-x-4 gap-y-0.5 mt-1">
                              {src.source_params.locations?.length > 0 && (
                                <span className="text-[10px] text-blue-600">{src.source_params.locations.length} locations</span>
                              )}
                              {src.source_params.states?.length > 0 && (
                                <span className="text-[10px] text-blue-600">States: {src.source_params.states.join(', ')}</span>
                              )}
                              {src.source_params.keywords?.length > 0 && (
                                <span className="text-[10px] text-blue-600">{src.source_params.keywords.length} keywords</span>
                              )}
                              {src.source_params.route_keywords?.length > 0 && (
                                <span className="text-[10px] text-blue-600">Routes: {src.source_params.route_keywords.slice(0, 5).join(', ')}</span>
                              )}
                              {src.source_params.corridors?.length > 0 && (
                                <span className="text-[10px] text-blue-600">{src.source_params.corridors.length} freight corridors</span>
                              )}
                            </div>
                          )}
                        </div>

                        {/* Last refresh + signal count */}
                        <div className="flex-shrink-0 text-right min-w-[100px]">
                          {active && hasSignals && (
                            <span className="text-xs text-gray-500">{src.signals_collected?.toLocaleString()} signals</span>
                          )}
                          {active && lastRefresh && (
                            <p className="text-[10px] text-gray-400">
                              {src.last_refresh_status === 'success' ? 'OK' : src.last_refresh_status === 'error' ? 'Error' : 'Pending'}{' '}
                              {new Date(lastRefresh).toLocaleDateString()}
                            </p>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Custom Sources ────────────────────────────────────────────── */}
      <div className="bg-white rounded-lg border">
        <div className="px-5 py-3 border-b flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold">Custom Sources</h3>
            <p className="text-xs text-gray-500">Add proprietary URLs, industry feeds, or subscription sources with optional authentication.</p>
          </div>
          <button
            onClick={() => setShowCustomForm(!showCustomForm)}
            className="flex items-center gap-1 px-3 py-1.5 text-sm border rounded-md hover:bg-gray-50"
          >
            <Plus className="w-3.5 h-3.5" />
            Add Source
          </button>
        </div>

        {/* Add form */}
        {showCustomForm && (
          <div className="px-5 py-4 border-b bg-gray-50">
            <div className="space-y-3 max-w-2xl">
              <input
                type="url"
                placeholder="https://example.com/feed.json or https://intranet.company.com/data"
                value={customForm.url}
                onChange={e => setCustomForm({ ...customForm, url: e.target.value })}
                onKeyDown={e => e.key === 'Enter' && handleIngestUrl()}
                className="w-full border rounded px-3 py-2 text-sm font-mono"
              />
              <div className="grid grid-cols-3 gap-3">
                <input
                  type="text"
                  placeholder="Name"
                  value={customForm.title}
                  onChange={e => setCustomForm({ ...customForm, title: e.target.value })}
                  className="border rounded px-3 py-2 text-sm"
                />
                <select
                  value={customForm.category}
                  onChange={e => setCustomForm({ ...customForm, category: e.target.value })}
                  className="border rounded px-3 py-2 text-sm"
                >
                  <option value="">Category</option>
                  {CATEGORIES.map(c => (
                    <option key={c.value} value={c.value}>{c.label}</option>
                  ))}
                </select>
                <select
                  value={customForm.refreshFreq}
                  onChange={e => setCustomForm({ ...customForm, refreshFreq: e.target.value })}
                  className="border rounded px-3 py-2 text-sm"
                >
                  <option value="one-time">One-time fetch</option>
                  <option value="daily">Daily refresh</option>
                  <option value="weekly">Weekly refresh</option>
                </select>
              </div>
              <input
                type="text"
                placeholder="Tags (comma-separated)"
                value={customForm.tags}
                onChange={e => setCustomForm({ ...customForm, tags: e.target.value })}
                className="w-full border rounded px-3 py-2 text-sm"
              />

              {/* Authentication (collapsed) */}
              <details className="text-sm">
                <summary className="cursor-pointer text-gray-500 hover:text-gray-700 select-none">
                  Authentication (optional — for subscription or intranet sources)
                </summary>
                <div className="space-y-2 mt-2">
                  <input
                    type="text"
                    placeholder="API key"
                    value={customForm.apiKey}
                    onChange={e => setCustomForm({ ...customForm, apiKey: e.target.value })}
                    className="w-full border rounded px-3 py-2 text-sm"
                    autoComplete="off"
                  />
                  <div className="grid grid-cols-2 gap-3">
                    <input
                      type="text"
                      placeholder="Username (if basic auth)"
                      value={customForm.username}
                      onChange={e => setCustomForm({ ...customForm, username: e.target.value })}
                      className="border rounded px-3 py-2 text-sm"
                      autoComplete="off"
                    />
                    <input
                      type="password"
                      placeholder="Password (if basic auth)"
                      value={customForm.password}
                      onChange={e => setCustomForm({ ...customForm, password: e.target.value })}
                      className="border rounded px-3 py-2 text-sm"
                      autoComplete="new-password"
                    />
                  </div>
                </div>
              </details>

              <div className="flex gap-2">
                <button
                  onClick={handleIngestUrl}
                  disabled={ingesting || !customForm.url.trim()}
                  className="flex items-center gap-2 px-5 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                >
                  {ingesting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                  {ingesting ? 'Testing & Indexing...' : 'Test & Add'}
                </button>
                <button
                  onClick={() => { setShowCustomForm(false); setIngestError(null); }}
                  className="px-4 py-2 text-sm text-gray-500 hover:text-gray-700"
                >
                  Cancel
                </button>
              </div>

              {ingestError && (
                <div className="bg-red-50 border border-red-200 text-red-700 rounded p-3 text-sm flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                  {ingestError}
                </div>
              )}
              {ingestResult && (
                <div className="bg-green-50 border border-green-200 rounded p-3 text-sm">
                  <div className="flex items-center gap-2 text-green-700 font-medium">
                    <CheckCircle className="w-4 h-4" />
                    Indexed: {ingestResult.title} ({ingestResult.chunk_count} chunks)
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Placeholder when no custom sources */}
        {!showCustomForm && (
          <div className="px-5 py-6 text-center text-sm text-gray-400">
            No custom sources added yet. Click "Add Source" to add a subscription feed, intranet page, or industry report.
          </div>
        )}
      </div>

      {/* ── Notes ────────────────────────────────────────────────────── */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-800">
        <p className="font-medium mb-1">How it works</p>
        <ul className="list-disc pl-4 space-y-1 text-blue-700">
          <li><b>Standard sources</b> are built-in market intelligence feeds — auto-configured from your supply chain network (site locations, freight lanes, products).</li>
          <li>They refresh daily at 05:30 and inject signals into Azirella's context for outside-in planning awareness.</li>
          <li>Expired signals (e.g., yesterday's weather) are automatically cleaned up — only current intelligence is used.</li>
          <li><b>Custom sources</b> are URLs you add manually — HTML pages, PDFs, or JSON feeds. They are fetched, chunked, and embedded into the knowledge base.</li>
          <li>For sites requiring login (e.g., intranet, paid subscriptions), expand "Authentication" and enter credentials. The URL is tested on save.</li>
        </ul>
      </div>
    </div>
  );
};

// ============================================================================
// Settings Tab
// ============================================================================

const SettingsTab = ({ status, loading }) => {
  if (loading) {
    return (
      <div className="text-center py-8 text-gray-500">
        <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" />
        Loading status...
      </div>
    );
  }

  const embeddingOk = status?.embedding_service?.status === 'ok';

  return (
    <div className="space-y-6">
      {/* Statistics */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-white rounded-lg border p-4">
          <div className="flex items-center gap-2 text-gray-500 mb-1">
            <FileText className="w-4 h-4" />
            <span className="text-sm">Documents</span>
          </div>
          <p className="text-2xl font-bold">{status?.total_documents || 0}</p>
        </div>
        <div className="bg-white rounded-lg border p-4">
          <div className="flex items-center gap-2 text-gray-500 mb-1">
            <CheckCircle className="w-4 h-4" />
            <span className="text-sm">Indexed</span>
          </div>
          <p className="text-2xl font-bold">{status?.indexed_documents || 0}</p>
        </div>
        <div className="bg-white rounded-lg border p-4">
          <div className="flex items-center gap-2 text-gray-500 mb-1">
            <Hash className="w-4 h-4" />
            <span className="text-sm">Total Chunks</span>
          </div>
          <p className="text-2xl font-bold">{status?.total_chunks || 0}</p>
        </div>
        <div className="bg-white rounded-lg border p-4">
          <div className="flex items-center gap-2 text-gray-500 mb-1">
            <Database className="w-4 h-4" />
            <span className="text-sm">RAG Enabled</span>
          </div>
          <p className="text-2xl font-bold">{status?.rag_enabled ? 'Yes' : 'No'}</p>
        </div>
      </div>

      {/* Embedding Service Status */}
      <div className="bg-white rounded-lg border p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Cpu className="w-5 h-5" />
          Embedding Service
        </h3>
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            {embeddingOk ? (
              <CheckCircle className="w-5 h-5 text-green-500" />
            ) : (
              <AlertTriangle className="w-5 h-5 text-red-500" />
            )}
            <span className={embeddingOk ? 'text-green-700' : 'text-red-700'}>
              {embeddingOk ? 'Connected' : 'Unavailable'}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-gray-500">Endpoint:</span>{' '}
              <code className="bg-gray-100 px-2 py-0.5 rounded">
                {status?.embedding_service?.api_base || '—'}
              </code>
            </div>
            <div>
              <span className="text-gray-500">Model:</span>{' '}
              <code className="bg-gray-100 px-2 py-0.5 rounded">
                {status?.embedding_service?.model || '—'}
              </code>
            </div>
          </div>
          {!embeddingOk && status?.embedding_service?.error && (
            <div className="bg-red-50 text-red-700 rounded p-3 text-sm">
              {status.embedding_service.error}
            </div>
          )}
        </div>
      </div>

      {/* RAG Configuration */}
      <div className="bg-white rounded-lg border p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Settings className="w-5 h-5" />
          RAG Configuration
        </h3>
        <div className="grid grid-cols-3 gap-4 text-sm">
          <div>
            <span className="text-gray-500">Chunk Size:</span>{' '}
            <span className="font-medium">{status?.chunk_size || 1024} chars</span>
          </div>
          <div>
            <span className="text-gray-500">Chunk Overlap:</span>{' '}
            <span className="font-medium">{status?.chunk_overlap || 200} chars</span>
          </div>
          <div>
            <span className="text-gray-500">Top-K Results:</span>{' '}
            <span className="font-medium">{status?.top_k || 5}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// Main Component
// ============================================================================

const TABS = [
  { id: 'documents', label: 'Documents', icon: FileText },
  { id: 'sources', label: 'Market Intelligence', icon: Link },
  { id: 'search', label: 'Search', icon: Search },
  { id: 'settings', label: 'Settings', icon: Settings },
];

export default function KnowledgeBase() {
  const { user } = useAuth();
  const [currentTab, setCurrentTab] = useState('documents');
  const [documents, setDocuments] = useState([]);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [statusLoading, setStatusLoading] = useState(true);

  const loadDocuments = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get('/knowledge-base/documents');
      setDocuments(response.data.documents || []);
    } catch (err) {
      console.error('Failed to load documents:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadStatus = useCallback(async () => {
    setStatusLoading(true);
    try {
      const response = await api.get('/knowledge-base/status');
      setStatus(response.data);
    } catch (err) {
      console.error('Failed to load status:', err);
    } finally {
      setStatusLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDocuments();
    loadStatus();
  }, [loadDocuments, loadStatus]);

  const handleDelete = async (docId) => {
    if (!window.confirm('Delete this document and all its chunks? This cannot be undone.')) return;
    try {
      await api.delete(`/knowledge-base/documents/${docId}`);
      loadDocuments();
      loadStatus();
    } catch (err) {
      alert(`Delete failed: ${err.response?.data?.detail || err.message}`);
    }
  };

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center gap-3">
        <BookOpen className="w-8 h-8 text-blue-600" />
        <div>
          <h1 className="text-2xl font-bold">Knowledge Base</h1>
          <p className="text-gray-500 text-sm">
            Upload documents for AI agent context (RAG). Supports PDF, DOCX, TXT, and Markdown.
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b">
        <div className="flex gap-1">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setCurrentTab(tab.id)}
                className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                  currentTab === tab.id
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                <Icon className="w-4 h-4" />
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Tab Content */}
      {currentTab === 'documents' && (
        <DocumentsTab
          documents={documents}
          loading={loading}
          onDelete={handleDelete}
          onRefresh={() => { loadDocuments(); loadStatus(); }}
        />
      )}
      {currentTab === 'sources' && (
        <SourcesTab onRefresh={() => { loadDocuments(); loadStatus(); }} />
      )}
      {currentTab === 'search' && <SearchTab />}
      {currentTab === 'settings' && <SettingsTab status={status} loading={statusLoading} />}
    </div>
  );
}
