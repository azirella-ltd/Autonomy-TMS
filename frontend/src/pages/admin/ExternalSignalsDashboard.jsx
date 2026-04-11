/**
 * ExternalSignalsDashboard — Manage outside-in planning signal sources.
 *
 * Configuration flow:
 * 1. Select a supply chain config (DAG)
 * 2. "Configure from Network" reads site locations, lanes, products
 * 3. Review auto-detected params (weather locations, states, routes, keywords)
 * 4. Activate — creates tenant-scoped sources with DAG-derived params
 * 5. Refresh to start collecting signals
 *
 * Part of the Context Engine — navigated to from the Market Intelligence card.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Globe,
  RefreshCw,
  Plus,
  ToggleLeft,
  ToggleRight,
  TrendingUp,
  TrendingDown,
  Minus,
  Loader2,
  AlertCircle,
  CheckCircle2,
  Clock,
  Filter,
  MapPin,
  Route,
  Settings2,
  ChevronDown,
  ChevronUp,
  Zap,
} from 'lucide-react';
import {
  Badge,
  Button,
  Card,
  CardContent,
  Skeleton,
} from '../../components/common';
import { api } from '../../services/api';
import { cn } from '@azirella-ltd/autonomy-frontend';

// Category colors and labels
const CATEGORY_CONFIG = {
  economic: { label: 'Economic', color: 'bg-blue-100 text-blue-800' },
  weather: { label: 'Weather', color: 'bg-cyan-100 text-cyan-800' },
  energy: { label: 'Energy', color: 'bg-orange-100 text-orange-800' },
  geopolitical: { label: 'Geopolitical', color: 'bg-red-100 text-red-800' },
  sentiment: { label: 'Sentiment', color: 'bg-purple-100 text-purple-800' },
  regulatory: { label: 'Regulatory', color: 'bg-amber-100 text-amber-800' },
  commodity: { label: 'Commodity', color: 'bg-emerald-100 text-emerald-800' },
  trade: { label: 'Trade', color: 'bg-indigo-100 text-indigo-800' },
};

const SOURCE_ICONS = {
  fred: '📊',
  open_meteo: '🌦️',
  eia: '⚡',
  gdelt: '🌍',
  google_trends: '📈',
  openfda: '🏛️',
  nws_alerts: '⛈️',
  dot_disruptions: '🚛',
};

const SOURCE_DESCRIPTIONS = {
  fred: 'Economic indicators: CPI, PPI, unemployment, oil prices, shipping index',
  open_meteo: 'Weather at your warehouse, DC, and delivery locations',
  eia: 'Energy prices: crude oil, natural gas, diesel (affects logistics costs)',
  gdelt: 'Geopolitical events: supply disruptions, port strikes, trade sanctions',
  google_trends: 'Consumer search trends for your product categories',
  openfda: 'FDA recalls and safety alerts relevant to your products',
  nws_alerts: 'NWS severe weather warnings for your operating states',
  dot_disruptions: 'Persistent road closures, bridge restrictions, port congestion on your freight lanes',
};

function DirectionIcon({ direction }) {
  if (direction === 'up') return <TrendingUp className="h-3.5 w-3.5 text-emerald-600" />;
  if (direction === 'down') return <TrendingDown className="h-3.5 w-3.5 text-red-600" />;
  return <Minus className="h-3.5 w-3.5 text-gray-400" />;
}

// ── Param summary for a source ──────────────────────────────────────────────

function ParamSummary({ sourceKey, params }) {
  if (!params || Object.keys(params).length === 0) return null;

  const items = [];
  if (params.locations?.length) {
    items.push({ icon: MapPin, text: `${params.locations.length} weather locations` });
  }
  if (params.states?.length) {
    items.push({ icon: MapPin, text: `States: ${params.states.join(', ')}` });
  }
  if (params.keywords?.length) {
    items.push({ icon: Filter, text: `${params.keywords.length} keywords monitored` });
  }
  if (params.corridors?.length) {
    items.push({ icon: Route, text: `${params.corridors.length} freight corridors` });
  }
  if (params.route_keywords?.length) {
    items.push({ icon: Route, text: `Routes: ${params.route_keywords.slice(0, 4).join(', ')}${params.route_keywords.length > 4 ? '...' : ''}` });
  }
  if (params.series_ids?.length) {
    items.push({ icon: TrendingUp, text: `${params.series_ids.length} data series` });
  }
  if (params.product_types?.length) {
    items.push({ icon: Filter, text: `Product types: ${params.product_types.join(', ')}` });
  }

  if (items.length === 0) return null;

  return (
    <div className="mt-2 space-y-1">
      {items.map((item, i) => (
        <div key={i} className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <item.icon className="h-3 w-3 flex-shrink-0" />
          <span className="truncate">{item.text}</span>
        </div>
      ))}
    </div>
  );
}


export default function ExternalSignalsDashboard() {
  const [sources, setSources] = useState([]);
  const [signals, setSignals] = useState([]);
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(null);
  const [activatingDefaults, setActivatingDefaults] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState(null);
  const [signalTotal, setSignalTotal] = useState(0);

  // Config selection for DAG-aware setup
  const [configs, setConfigs] = useState([]);
  const [selectedConfigId, setSelectedConfigId] = useState(null);
  const [showSetup, setShowSetup] = useState(false);

  // ── Fetch functions ───────────────────────────────────────────────────

  const fetchConfigs = useCallback(async () => {
    try {
      const res = await api.get('/supply-chain-configs');
      const cfgs = Array.isArray(res.data) ? res.data : res.data?.configs || [];
      setConfigs(cfgs);
      // Auto-select the first active config
      const active = cfgs.find(c => c.is_active);
      if (active) setSelectedConfigId(active.id);
    } catch { /* ignore */ }
  }, []);

  const fetchSources = useCallback(async () => {
    try {
      const res = await api.get('/external-signals/sources');
      setSources(res.data?.sources || []);
    } catch { /* ignore */ }
  }, []);

  const fetchSignals = useCallback(async (category) => {
    try {
      const params = { limit: 50 };
      if (category) params.category = category;
      const res = await api.get('/external-signals/signals', { params });
      setSignals(res.data?.signals || []);
      setSignalTotal(res.data?.total || 0);
    } catch { /* ignore */ }
  }, []);

  const fetchDashboard = useCallback(async () => {
    try {
      const res = await api.get('/external-signals/dashboard');
      setDashboard(res.data);
    } catch { /* ignore */ }
  }, []);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    await Promise.allSettled([fetchConfigs(), fetchSources(), fetchSignals(categoryFilter), fetchDashboard()]);
    setLoading(false);
  }, [fetchConfigs, fetchSources, fetchSignals, fetchDashboard, categoryFilter]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  // ── Actions ───────────────────────────────────────────────────────────

  const handleActivateDefaults = async () => {
    setActivatingDefaults(true);
    try {
      const params = selectedConfigId ? `?config_id=${selectedConfigId}` : '';
      await api.post(`/external-signals/sources/activate-defaults${params}`);
      await Promise.allSettled([fetchSources(), fetchDashboard()]);
      setShowSetup(false);
    } catch { /* ignore */ }
    setActivatingDefaults(false);
  };

  const handleToggleSource = async (sourceId, currentActive) => {
    try {
      await api.put(`/external-signals/sources/${sourceId}/toggle?is_active=${!currentActive}`);
      await fetchSources();
    } catch { /* ignore */ }
  };

  const handleRefreshSource = async (sourceId) => {
    setRefreshing(sourceId);
    try {
      await api.post(`/external-signals/refresh/${sourceId}`);
      await Promise.allSettled([fetchSignals(categoryFilter), fetchDashboard(), fetchSources()]);
    } catch { /* ignore */ }
    setRefreshing(null);
  };

  const handleRefreshAll = async () => {
    setRefreshing('all');
    try {
      await api.post('/external-signals/refresh-all');
      await Promise.allSettled([fetchSignals(categoryFilter), fetchDashboard(), fetchSources()]);
    } catch { /* ignore */ }
    setRefreshing(null);
  };

  const handleCategoryFilter = (cat) => {
    const next = cat === categoryFilter ? null : cat;
    setCategoryFilter(next);
    fetchSignals(next);
  };

  const selectedConfig = configs.find(c => c.id === selectedConfigId);

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <div className="flex items-center justify-center h-9 w-9 rounded-lg bg-sky-500/10">
                <Globe className="h-5 w-5 text-sky-600" />
              </div>
              <h1 className="text-2xl font-bold tracking-tight">Market Intelligence</h1>
            </div>
            <p className="text-muted-foreground ml-12">
              Outside-in planning signals from public data — auto-configured from your supply chain network
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => setShowSetup(!showSetup)}>
              <Settings2 className="h-4 w-4 mr-1.5" />
              {showSetup ? 'Hide Setup' : 'Configure'}
            </Button>
            {sources.length > 0 && (
              <Button variant="outline" size="sm" onClick={handleRefreshAll} disabled={refreshing === 'all'}>
                <RefreshCw className={cn('h-4 w-4 mr-1.5', refreshing === 'all' && 'animate-spin')} />
                Refresh All
              </Button>
            )}
          </div>
        </div>

        {/* ── SETUP PANEL ──────────────────────────────────────────────── */}
        {(showSetup || sources.length === 0) && (
          <Card className="mb-6 border-sky-200 bg-sky-50/50">
            <CardContent className="p-6">
              <div className="flex items-start gap-3 mb-4">
                <Zap className="h-5 w-5 text-sky-600 mt-0.5" />
                <div>
                  <h3 className="font-semibold text-base">Configure from Your Network</h3>
                  <p className="text-sm text-muted-foreground mt-0.5">
                    Select a supply chain config and we'll auto-detect weather locations, freight corridors,
                    product keywords, and monitoring states from your DAG topology.
                  </p>
                </div>
              </div>

              {/* Config selector */}
              <div className="mb-4">
                <label className="block text-sm font-medium mb-1.5">Supply Chain Configuration</label>
                <select
                  value={selectedConfigId || ''}
                  onChange={(e) => setSelectedConfigId(e.target.value ? Number(e.target.value) : null)}
                  className="w-full max-w-md border rounded-md px-3 py-2 text-sm bg-background"
                >
                  <option value="">Select a config...</option>
                  {configs.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} {c.is_active ? '(active)' : ''} — {c.num_sites || '?'} sites, {c.num_products || '?'} products
                    </option>
                  ))}
                </select>
              </div>

              {selectedConfig && (
                <div className="bg-background rounded-lg border p-4 mb-4">
                  <h4 className="text-sm font-medium mb-2">What will be configured:</h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                    <div className="flex items-start gap-2">
                      <span className="text-lg">🌦️</span>
                      <div>
                        <span className="font-medium">Weather (Open-Meteo + NWS)</span>
                        <p className="text-xs text-muted-foreground">Temperature, precipitation, and severe weather at your site locations and along freight lanes</p>
                      </div>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="text-lg">🚛</span>
                      <div>
                        <span className="font-medium">Transportation (DOT)</span>
                        <p className="text-xs text-muted-foreground">Road closures, bridge restrictions, construction on your interstate routes</p>
                      </div>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="text-lg">🌍</span>
                      <div>
                        <span className="font-medium">Geopolitical (GDELT)</span>
                        <p className="text-xs text-muted-foreground">Supply disruptions, port strikes, trade sanctions — keywords from your industry</p>
                      </div>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="text-lg">🏛️</span>
                      <div>
                        <span className="font-medium">Regulatory (FDA)</span>
                        <p className="text-xs text-muted-foreground">Product recalls and safety alerts matching your product categories</p>
                      </div>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="text-lg">📈</span>
                      <div>
                        <span className="font-medium">Consumer Trends</span>
                        <p className="text-xs text-muted-foreground">Google search interest for your product keywords (demand sensing)</p>
                      </div>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="text-lg">📊</span>
                      <div>
                        <span className="font-medium">Economic (FRED + EIA)</span>
                        <p className="text-xs text-muted-foreground">CPI, PPI, oil/gas/diesel prices, shipping index, consumer sentiment</p>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              <Button
                variant="default"
                onClick={handleActivateDefaults}
                disabled={activatingDefaults || !selectedConfigId}
              >
                {activatingDefaults
                  ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
                  : <Zap className="h-4 w-4 mr-1.5" />
                }
                {sources.length > 0 ? 'Reconfigure from Network' : 'Activate & Configure from Network'}
              </Button>
              {!selectedConfigId && (
                <p className="text-xs text-amber-600 mt-2">Please select a supply chain config first</p>
              )}
            </CardContent>
          </Card>
        )}

        {/* Summary stats */}
        {dashboard && sources.length > 0 && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <Card>
              <CardContent className="p-4">
                <p className="text-xs text-muted-foreground uppercase tracking-wider">Active Sources</p>
                <p className="text-2xl font-bold">{dashboard.sources?.filter(s => s.is_active).length || 0}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <p className="text-xs text-muted-foreground uppercase tracking-wider">Signals (30d)</p>
                <p className="text-2xl font-bold">{dashboard.total_signals_30d?.toLocaleString() || 0}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <p className="text-xs text-muted-foreground uppercase tracking-wider">High Relevance</p>
                <p className="text-2xl font-bold">{dashboard.high_relevance_signals?.toLocaleString() || 0}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <p className="text-xs text-muted-foreground uppercase tracking-wider">Categories</p>
                <p className="text-2xl font-bold">{Object.keys(dashboard.signals_by_category || {}).length}</p>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Sources */}
        {sources.length > 0 && (
          <>
            <h2 className="text-lg font-semibold mb-3">Configured Sources</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
              {sources.map((src) => (
                <Card key={src.id} className={cn(!src.is_active && 'opacity-60')}>
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xl">{SOURCE_ICONS[src.source_key] || '📡'}</span>
                        <div>
                          <h3 className="text-sm font-semibold">{src.source_name}</h3>
                          <p className="text-[11px] text-muted-foreground leading-tight mt-0.5">
                            {SOURCE_DESCRIPTIONS[src.source_key] || src.source_key}
                          </p>
                        </div>
                      </div>
                      <button
                        onClick={() => handleToggleSource(src.id, src.is_active)}
                        className="text-muted-foreground hover:text-foreground flex-shrink-0"
                        title={src.is_active ? 'Disable' : 'Enable'}
                      >
                        {src.is_active
                          ? <ToggleRight className="h-5 w-5 text-emerald-600" />
                          : <ToggleLeft className="h-5 w-5" />
                        }
                      </button>
                    </div>

                    {/* Show DAG-derived params */}
                    <ParamSummary sourceKey={src.source_key} params={src.source_params} />

                    {/* Tags */}
                    {(src.industry_tags?.length > 0 || src.region_tags?.length > 0) && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {src.industry_tags?.map(t => (
                          <span key={t} className="text-[10px] px-1.5 py-0.5 rounded bg-violet-100 text-violet-700">{t.replace(/_/g, ' ')}</span>
                        ))}
                        {src.region_tags?.slice(0, 3).map(t => (
                          <span key={t} className="text-[10px] px-1.5 py-0.5 rounded bg-sky-100 text-sky-700">{t.replace(/_/g, ' ')}</span>
                        ))}
                      </div>
                    )}

                    <div className="flex items-center justify-between text-xs text-muted-foreground mt-3 mb-2">
                      <span className="flex items-center gap-1">
                        {src.last_refresh_status === 'success'
                          ? <CheckCircle2 className="h-3 w-3 text-emerald-500" />
                          : src.last_refresh_status === 'error'
                            ? <AlertCircle className="h-3 w-3 text-red-500" />
                            : <Clock className="h-3 w-3" />
                        }
                        {src.last_refresh_at
                          ? `Last: ${new Date(src.last_refresh_at).toLocaleDateString()}`
                          : 'Never refreshed'
                        }
                      </span>
                      <span>{src.signals_collected?.toLocaleString() || 0} signals</span>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full"
                      onClick={() => handleRefreshSource(src.id)}
                      disabled={refreshing === src.id}
                    >
                      {refreshing === src.id
                        ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
                        : <RefreshCw className="h-3.5 w-3.5 mr-1" />
                      }
                      Refresh Now
                    </Button>
                  </CardContent>
                </Card>
              ))}
            </div>
          </>
        )}

        {/* Category filter bar */}
        {signals.length > 0 && (
          <div className="flex items-center gap-2 mb-4 flex-wrap">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <button
              onClick={() => handleCategoryFilter(null)}
              className={cn(
                'text-xs px-2.5 py-1 rounded-full border transition-colors',
                !categoryFilter ? 'bg-primary text-primary-foreground border-primary' : 'border-border hover:bg-muted'
              )}
            >
              All ({signalTotal})
            </button>
            {Object.entries(CATEGORY_CONFIG).map(([key, cfg]) => {
              const count = dashboard?.signals_by_category?.[key] || 0;
              if (count === 0 && key !== categoryFilter) return null;
              return (
                <button
                  key={key}
                  onClick={() => handleCategoryFilter(key)}
                  className={cn(
                    'text-xs px-2.5 py-1 rounded-full border transition-colors',
                    categoryFilter === key ? 'bg-primary text-primary-foreground border-primary' : 'border-border hover:bg-muted'
                  )}
                >
                  {cfg.label} ({count})
                </button>
              );
            })}
          </div>
        )}

        {/* Signals list */}
        {sources.length > 0 && (
          <>
            <h2 className="text-lg font-semibold mb-3">Recent Signals</h2>
            {loading ? (
              <div className="space-y-3">
                {[1,2,3,4,5].map(i => (
                  <Card key={i}><CardContent className="p-4"><Skeleton className="h-16 w-full" /></CardContent></Card>
                ))}
              </div>
            ) : signals.length === 0 ? (
              <Card>
                <CardContent className="p-8 text-center text-muted-foreground">
                  No signals collected yet. Click "Refresh All" to start collecting market intelligence.
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-2">
                {signals.map((sig) => {
                  const catCfg = CATEGORY_CONFIG[sig.category] || { label: sig.category, color: 'bg-gray-100 text-gray-800' };
                  return (
                    <Card key={sig.id} className="hover:shadow-sm transition-shadow">
                      <CardContent className="p-4">
                        <div className="flex items-start gap-3">
                          <DirectionIcon direction={sig.change_direction} />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1 flex-wrap">
                              <span className={cn('text-[10px] px-1.5 py-0.5 rounded-full font-medium', catCfg.color)}>
                                {catCfg.label}
                              </span>
                              <span className="text-xs text-muted-foreground">{sig.signal_date}</span>
                              {sig.planning_layer && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                                  {sig.planning_layer}
                                </span>
                              )}
                            </div>
                            <p className="text-sm font-medium leading-snug mb-1">{sig.title}</p>
                            <p className="text-xs text-muted-foreground leading-relaxed">{sig.summary}</p>
                          </div>
                          <div className="flex flex-col items-end gap-1 flex-shrink-0">
                            <span className="text-[10px] text-muted-foreground">Relevance</span>
                            <div className="w-12 h-1.5 bg-muted rounded-full overflow-hidden">
                              <div
                                className={cn(
                                  'h-full rounded-full',
                                  sig.relevance_score >= 0.7 ? 'bg-emerald-500' : sig.relevance_score >= 0.4 ? 'bg-amber-500' : 'bg-gray-400'
                                )}
                                style={{ width: `${(sig.relevance_score || 0) * 100}%` }}
                              />
                            </div>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
