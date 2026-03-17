/**
 * Network Analytics — DAG topology analysis and risk scoring
 *
 * Computes graph theory metrics directly from the supply chain config DAG:
 * - Betweenness centrality (critical bridge sites)
 * - In/out degree (supplier/customer concentration)
 * - Echelon depth (stages from demand to supply)
 * - Lead time propagation (cumulative path lead times)
 * - Single-source risk (sites with only one upstream supplier)
 * - Network density and connectivity
 *
 * Also surfaces S&OP GraphSAGE risk scores when available.
 */
import React, { useState, useEffect, useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle, Badge, Progress } from '../../components/common';
import {
  Network, MapPin, ArrowRight, Truck, AlertTriangle, Shield,
  Zap, BarChart3, Target, Layers, GitBranch,
} from 'lucide-react';
import api from '../../services/api';
import Sparkline from '../../components/metrics/Sparkline';

// ---------------------------------------------------------------------------
// Graph analytics computed client-side from site/lane data
// ---------------------------------------------------------------------------

function computeGraphMetrics(siteList, laneList) {
  const siteMap = {};
  for (const s of siteList) siteMap[s.id] = s;

  // Adjacency lists
  const outEdges = {};   // site_id → [{to, leadTime, capacity}]
  const inEdges = {};    // site_id → [{from, leadTime, capacity}]
  for (const s of siteList) { outEdges[s.id] = []; inEdges[s.id] = []; }

  for (const l of laneList) {
    const lt = l.lead_time_min ?? l.supply_lead_time?.value ?? l.supply_lead_time?.mean ?? l.lead_time ?? 0;
    const cap = l.capacity_int ?? l.capacity ?? 0;
    if (outEdges[l.from_site_id]) outEdges[l.from_site_id].push({ to: l.to_site_id, leadTime: lt, capacity: cap });
    if (inEdges[l.to_site_id]) inEdges[l.to_site_id].push({ from: l.from_site_id, leadTime: lt, capacity: cap });
  }

  // --- Degree ---
  const degree = {};
  for (const s of siteList) {
    degree[s.id] = {
      in: (inEdges[s.id] || []).length,
      out: (outEdges[s.id] || []).length,
      total: (inEdges[s.id] || []).length + (outEdges[s.id] || []).length,
    };
  }

  // --- Echelon depth (BFS from demand sinks) ---
  const echelon = {};
  const demandSites = siteList.filter(s =>
    s.master_type === 'MARKET_DEMAND' || (degree[s.id]?.out === 0 && s.master_type !== 'MARKET_SUPPLY')
  );
  // BFS backward from demand
  const queue = [];
  for (const d of demandSites) { echelon[d.id] = 0; queue.push(d.id); }
  while (queue.length) {
    const current = queue.shift();
    for (const e of (inEdges[current] || [])) {
      if (echelon[e.from] === undefined) {
        echelon[e.from] = echelon[current] + 1;
        queue.push(e.from);
      }
    }
  }

  // --- Cumulative lead time (longest path from each site to nearest demand) ---
  const cumulativeLT = {};
  const visited = new Set();
  function dfs(siteId) {
    if (cumulativeLT[siteId] !== undefined) return cumulativeLT[siteId];
    if (visited.has(siteId)) return 0;
    visited.add(siteId);
    const downstream = outEdges[siteId] || [];
    if (downstream.length === 0) { cumulativeLT[siteId] = 0; return 0; }
    let maxPath = 0;
    for (const e of downstream) {
      maxPath = Math.max(maxPath, e.leadTime + dfs(e.to));
    }
    cumulativeLT[siteId] = maxPath;
    return maxPath;
  }
  for (const s of siteList) dfs(s.id);

  // --- Betweenness centrality (simplified: count shortest paths through each node) ---
  const betweenness = {};
  for (const s of siteList) betweenness[s.id] = 0;
  // BFS from each source to each sink, count intermediaries
  const sources = siteList.filter(s => s.master_type === 'MARKET_SUPPLY' || (degree[s.id]?.in === 0 && s.master_type !== 'MARKET_DEMAND'));
  const sinks = siteList.filter(s => s.master_type === 'MARKET_DEMAND' || (degree[s.id]?.out === 0 && s.master_type !== 'MARKET_SUPPLY'));
  for (const src of sources) {
    // BFS to find all reachable paths
    const parent = {};
    const bfsQ = [src.id];
    parent[src.id] = null;
    while (bfsQ.length) {
      const curr = bfsQ.shift();
      for (const e of (outEdges[curr] || [])) {
        if (parent[e.to] === undefined) {
          parent[e.to] = curr;
          bfsQ.push(e.to);
        }
      }
    }
    // Trace paths to sinks and count intermediaries
    for (const sink of sinks) {
      if (parent[sink.id] === undefined) continue;
      let node = parent[sink.id];
      while (node !== null && node !== src.id) {
        betweenness[node] = (betweenness[node] || 0) + 1;
        node = parent[node];
      }
    }
  }
  // Normalize
  const maxBetween = Math.max(...Object.values(betweenness), 1);
  for (const k of Object.keys(betweenness)) betweenness[k] /= maxBetween;

  // --- Single-source risk (internal sites with exactly 1 upstream supplier) ---
  const singleSource = {};
  for (const s of siteList) {
    if (s.master_type === 'MARKET_SUPPLY' || s.master_type === 'MARKET_DEMAND') continue;
    singleSource[s.id] = (inEdges[s.id] || []).length <= 1;
  }

  // --- Network metrics ---
  const internal = siteList.filter(s => s.master_type !== 'MARKET_SUPPLY' && s.master_type !== 'MARKET_DEMAND');
  const maxEchelon = Math.max(...Object.values(echelon), 0);
  const density = siteList.length > 1 ? laneList.length / (siteList.length * (siteList.length - 1)) : 0;
  const avgDegree = siteList.length > 0 ? Object.values(degree).reduce((s, d) => s + d.total, 0) / siteList.length : 0;
  const allLTs = laneList.map(l => l.lead_time_min ?? l.supply_lead_time?.value ?? l.supply_lead_time?.mean ?? l.lead_time ?? 0);
  const avgLT = allLTs.length > 0 ? allLTs.reduce((a, b) => a + b, 0) / allLTs.length : 0;
  const maxCumulativeLT = Math.max(...Object.values(cumulativeLT), 0);

  return {
    degree,
    echelon,
    cumulativeLT,
    betweenness,
    singleSource,
    networkMetrics: {
      totalSites: siteList.length,
      internalSites: internal.length,
      totalLanes: laneList.length,
      echelonDepth: maxEchelon,
      density: density,
      avgDegree: avgDegree,
      avgLeadTime: avgLT,
      maxCumulativeLT: maxCumulativeLT,
      singleSourceCount: Object.values(singleSource).filter(Boolean).length,
    },
  };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const TYPE_COLORS = {
  MANUFACTURER: { bg: 'bg-purple-100 text-purple-700', border: 'border-l-purple-500' },
  INVENTORY: { bg: 'bg-blue-100 text-blue-700', border: 'border-l-blue-500' },
  MARKET_SUPPLY: { bg: 'bg-green-100 text-green-700', border: 'border-l-green-500' },
  MARKET_DEMAND: { bg: 'bg-amber-100 text-amber-700', border: 'border-l-amber-500' },
};

const RiskBadge = ({ value, label }) => {
  if (value == null) return null;
  const v = typeof value === 'number' ? value : 0;
  const color = v > 0.7 ? 'bg-red-100 text-red-700' : v > 0.4 ? 'bg-amber-100 text-amber-700' : 'bg-green-100 text-green-700';
  return (
    <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${color}`} title={label}>
      {(v * 100).toFixed(0)}%
    </span>
  );
};

const NetworkOptimizationAnalytics = () => {
  const [sites, setSites] = useState([]);
  const [lanes, setLanes] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const { data: configs } = await api.get('/supply-chain-config/');
        const cfg = Array.isArray(configs) ? configs.find(c => c.is_active) || configs[0] : null;
        if (!cfg) { setLoading(false); return; }

        const [sitesRes, lanesRes] = await Promise.all([
          api.get(`/supply-chain-config/${cfg.id}/sites`),
          api.get(`/supply-chain-config/${cfg.id}/lanes`),
        ]);

        setSites(Array.isArray(sitesRes.data) ? sitesRes.data : []);
        setLanes(Array.isArray(lanesRes.data) ? lanesRes.data : []);
      } catch (err) {
        console.error('Network analytics error:', err);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const graph = useMemo(() => computeGraphMetrics(sites, lanes), [sites, lanes]);
  const nm = graph.networkMetrics;

  // Build enriched site list with all metrics
  const enrichedSites = useMemo(() => {
    return sites
      .filter(s => s.master_type !== 'MARKET_SUPPLY' && s.master_type !== 'MARKET_DEMAND')
      .map(s => ({
        ...s,
        inDegree: graph.degree[s.id]?.in || 0,
        outDegree: graph.degree[s.id]?.out || 0,
        echelon: graph.echelon[s.id] ?? '-',
        cumulativeLT: graph.cumulativeLT[s.id] || 0,
        betweenness: graph.betweenness[s.id] || 0,
        singleSource: graph.singleSource[s.id] || false,
      }))
      .sort((a, b) => b.betweenness - a.betweenness);
  }, [sites, graph]);

  // Site composition by type
  const sitesByType = {};
  for (const s of sites) {
    const t = s.master_type || 'OTHER';
    sitesByType[t] = (sitesByType[t] || 0) + 1;
  }

  // Top lanes by lead time
  const siteMap = {};
  for (const s of sites) siteMap[s.id] = s;
  const enrichedLanes = useMemo(() =>
    lanes.map(l => ({
      ...l,
      fromName: siteMap[l.from_site_id]?.name || l.from_site_id,
      toName: siteMap[l.to_site_id]?.name || l.to_site_id,
      leadTime: l.lead_time_min ?? l.supply_lead_time?.value ?? l.supply_lead_time?.mean ?? l.lead_time ?? 0,
      cap: l.capacity_int ?? l.capacity ?? 0,
    })).sort((a, b) => b.leadTime - a.leadTime),
  [lanes, siteMap]);

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-12 text-center text-muted-foreground">
        Loading network topology...
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-6 max-w-7xl">
      <div className="flex items-center gap-2 mb-1">
        <Network className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-bold">Network Analytics</h1>
      </div>
      <p className="text-sm text-muted-foreground mb-6">
        DAG topology analysis, centrality scoring, risk detection, and lead time propagation
      </p>

      {/* ── Network-level metrics ── */}
      <div className="grid grid-cols-3 md:grid-cols-6 gap-3 mb-6">
        {[
          { label: 'Sites', value: nm.totalSites, icon: MapPin },
          { label: 'Lanes', value: nm.totalLanes, icon: GitBranch },
          { label: 'Echelon Depth', value: nm.echelonDepth, icon: Layers },
          { label: 'Avg Lead Time', value: `${nm.avgLeadTime.toFixed(1)}d`, icon: Truck },
          { label: 'Max Cumulative LT', value: `${nm.maxCumulativeLT.toFixed(0)}d`, icon: Zap },
          { label: 'Single-Source Risk', value: nm.singleSourceCount, icon: AlertTriangle,
            color: nm.singleSourceCount > 0 ? 'text-red-600' : 'text-green-600' },
        ].map(({ label, value, icon: Icon, color }) => (
          <Card key={label}>
            <CardContent className="pt-4 pb-3">
              <div className="flex items-center gap-1.5 mb-1">
                <Icon className="h-3.5 w-3.5 text-muted-foreground" />
                <p className="text-[10px] text-muted-foreground">{label}</p>
              </div>
              <p className={`text-xl font-bold ${color || ''}`}>{value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* ── Additional network stats ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Card><CardContent className="pt-4 pb-3">
          <p className="text-[10px] text-muted-foreground">Network Density</p>
          <p className="text-lg font-bold">{(nm.density * 100).toFixed(1)}%</p>
          <p className="text-[10px] text-muted-foreground mt-0.5">
            {nm.density < 0.1 ? 'Sparse (typical for supply chains)' : nm.density < 0.3 ? 'Moderate' : 'Dense'}
          </p>
        </CardContent></Card>
        <Card><CardContent className="pt-4 pb-3">
          <p className="text-[10px] text-muted-foreground">Avg Connectivity</p>
          <p className="text-lg font-bold">{nm.avgDegree.toFixed(1)}</p>
          <p className="text-[10px] text-muted-foreground mt-0.5">edges per site</p>
        </CardContent></Card>
        <Card><CardContent className="pt-4 pb-3">
          <p className="text-[10px] text-muted-foreground">Internal Sites</p>
          <p className="text-lg font-bold">{nm.internalSites}</p>
          <p className="text-[10px] text-muted-foreground mt-0.5">company-controlled nodes</p>
        </CardContent></Card>
        <Card><CardContent className="pt-4 pb-3">
          <p className="text-[10px] text-muted-foreground">Supplier/Customer Sites</p>
          <p className="text-lg font-bold">{nm.totalSites - nm.internalSites}</p>
          <p className="text-[10px] text-muted-foreground mt-0.5">external trading partners</p>
        </CardContent></Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        {/* ── Site composition ── */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <MapPin className="h-4 w-4" /> Site Composition
            </CardTitle>
          </CardHeader>
          <CardContent>
            {Object.entries(sitesByType).sort((a, b) => b[1] - a[1]).map(([type, count]) => (
              <div key={type} className="flex items-center justify-between py-2 border-b last:border-0">
                <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${TYPE_COLORS[type]?.bg || 'bg-gray-100 text-gray-700'}`}>
                  {type}
                </span>
                <div className="flex items-center gap-3">
                  <Progress value={(count / Math.max(sites.length, 1)) * 100} className="w-20 h-1.5" />
                  <span className="text-sm font-mono w-8 text-right">{count}</span>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* ── Longest lanes ── */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Truck className="h-4 w-4" /> Longest Lanes
            </CardTitle>
          </CardHeader>
          <CardContent>
            {enrichedLanes.slice(0, 8).map((l) => (
              <div key={l.id} className="flex items-center gap-1.5 py-1.5 border-b last:border-0 text-xs">
                <span className="truncate w-20">{l.fromName}</span>
                <ArrowRight className="h-2.5 w-2.5 text-muted-foreground flex-shrink-0" />
                <span className="truncate flex-1">{l.toName}</span>
                <Badge variant="outline" className="text-[9px] flex-shrink-0">{l.leadTime}d</Badge>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* ── Single-source risks ── */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-red-500" /> Single-Source Risk
            </CardTitle>
          </CardHeader>
          <CardContent>
            {enrichedSites.filter(s => s.singleSource).length === 0 ? (
              <div className="text-center py-6 text-sm text-green-600 flex items-center justify-center gap-2">
                <Shield className="h-4 w-4" /> No single-source sites detected
              </div>
            ) : (
              enrichedSites.filter(s => s.singleSource).map((s) => (
                <div key={s.id} className="flex items-center justify-between py-1.5 border-b last:border-0 text-xs">
                  <span className="font-medium">{s.name}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-muted-foreground">1 supplier</span>
                    <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-red-100 text-red-700">
                      AT RISK
                    </span>
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>

      {/* ── Site-level metrics table ── */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <BarChart3 className="h-4 w-4" /> Site Criticality Analysis
            <span className="text-[10px] text-muted-foreground font-normal ml-2">
              Sorted by betweenness centrality (most critical first)
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-[10px] text-muted-foreground border-b uppercase tracking-wide">
                  <th className="text-left py-2 pr-3">Site</th>
                  <th className="text-left py-2 pr-2">Type</th>
                  <th className="text-center py-2 pr-2">Echelon</th>
                  <th className="text-center py-2 pr-2" title="Upstream connections">In</th>
                  <th className="text-center py-2 pr-2" title="Downstream connections">Out</th>
                  <th className="text-right py-2 pr-3" title="Cumulative lead time to demand">Cum. LT</th>
                  <th className="py-2 pr-2" title="Betweenness centrality — higher = more critical bridge">Centrality</th>
                  <th className="text-left py-2">Risk</th>
                </tr>
              </thead>
              <tbody>
                {enrichedSites.map((s) => (
                  <tr key={s.id} className="border-b last:border-0 hover:bg-muted/50">
                    <td className="py-2 pr-3 font-medium">{s.name}</td>
                    <td className="py-2 pr-2">
                      <span className={`text-[9px] font-semibold px-1 py-0.5 rounded ${TYPE_COLORS[s.master_type]?.bg || 'bg-gray-100 text-gray-700'}`}>
                        {s.master_type}
                      </span>
                    </td>
                    <td className="py-2 pr-2 text-center font-mono">{s.echelon}</td>
                    <td className="py-2 pr-2 text-center font-mono">{s.inDegree}</td>
                    <td className="py-2 pr-2 text-center font-mono">{s.outDegree}</td>
                    <td className="py-2 pr-3 text-right font-mono">{s.cumulativeLT.toFixed(0)}d</td>
                    <td className="py-2 pr-2">
                      <div className="flex items-center gap-2">
                        <Progress
                          value={s.betweenness * 100}
                          className={`w-16 h-1.5 ${s.betweenness > 0.7 ? '[&>div]:bg-red-500' : s.betweenness > 0.3 ? '[&>div]:bg-amber-500' : '[&>div]:bg-green-500'}`}
                        />
                        <RiskBadge value={s.betweenness} label="Betweenness centrality" />
                      </div>
                    </td>
                    <td className="py-2">
                      {s.singleSource && (
                        <span className="text-[9px] font-semibold px-1 py-0.5 rounded bg-red-100 text-red-700">
                          SINGLE SRC
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
export default NetworkOptimizationAnalytics;
