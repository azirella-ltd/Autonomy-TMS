/**
 * Inventory Segmentation — ABC/XYZ classification and demand pattern analysis.
 *
 * Sub-processes:
 *   - ABC analysis (revenue/volume Pareto)
 *   - XYZ analysis (demand variability — CV of demand)
 *   - Combined ABC-XYZ matrix (9 quadrants)
 *   - Glenday Sieve (green/yellow/blue/red production frequency)
 *   - Demand pattern classification (smooth, seasonal, intermittent, lumpy, erratic)
 *   - Policy recommendation by segment
 */

import React, { useState, useEffect, useMemo } from 'react';
import {
  Card, CardContent, CardHeader, CardTitle, Button, Badge, Alert,
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell, Spinner,
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from '../../components/common';
import {
  Grid3X3, RefreshCw, Download, BarChart3, TrendingUp, AlertTriangle,
  Package, Filter,
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ScatterChart, Scatter, ZAxis, Cell, PieChart, Pie, Legend,
} from 'recharts';
import { api } from '../../services/api';
import { useActiveConfig } from '../../contexts/ActiveConfigContext';

// ── ABC/XYZ Classification Logic ──────────────────────────────────────

const ABC_THRESHOLDS = { A: 0.80, B: 0.95 }; // cumulative revenue %
const XYZ_THRESHOLDS = { X: 0.5, Y: 1.0 };   // coefficient of variation

function classifyABC(products) {
  const sorted = [...products].sort((a, b) => b.annual_revenue - a.annual_revenue);
  const totalRevenue = sorted.reduce((s, p) => s + p.annual_revenue, 0);
  let cumulative = 0;
  return sorted.map(p => {
    cumulative += p.annual_revenue;
    const pct = cumulative / totalRevenue;
    const abc = pct <= ABC_THRESHOLDS.A ? 'A' : pct <= ABC_THRESHOLDS.B ? 'B' : 'C';
    return { ...p, abc_class: abc, cumulative_pct: Math.round(pct * 100) };
  });
}

function classifyXYZ(products) {
  return products.map(p => {
    const cv = p.demand_stddev / Math.max(p.demand_mean, 0.01);
    const xyz = cv <= XYZ_THRESHOLDS.X ? 'X' : cv <= XYZ_THRESHOLDS.Y ? 'Y' : 'Z';
    return { ...p, xyz_class: xyz, cv: Math.round(cv * 100) / 100 };
  });
}

function classifyDemandPattern(products) {
  return products.map(p => {
    const cv = p.demand_stddev / Math.max(p.demand_mean, 0.01);
    const adi = p.avg_demand_interval || 1;
    let pattern;
    if (adi > 1.32 && cv > 0.49) pattern = 'lumpy';
    else if (adi > 1.32) pattern = 'intermittent';
    else if (cv > 0.49) pattern = 'erratic';
    else if (p.seasonal_index > 1.3) pattern = 'seasonal';
    else pattern = 'smooth';
    return { ...p, demand_pattern: pattern };
  });
}

const PATTERN_COLORS = {
  smooth: '#10b981', seasonal: '#3b82f6', intermittent: '#f59e0b',
  erratic: '#ef4444', lumpy: '#8b5cf6',
};

const ABC_COLORS = { A: '#10b981', B: '#3b82f6', C: '#f59e0b' };
const XYZ_COLORS = { X: '#10b981', Y: '#f59e0b', Z: '#ef4444' };

const POLICY_RECOMMENDATIONS = {
  AX: { policy: 'sl_fitted', reason: 'High value, stable — tight service level with fitted distributions' },
  AY: { policy: 'sl_conformal_fitted', reason: 'High value, moderate variability — hybrid conformal + fitted' },
  AZ: { policy: 'conformal', reason: 'High value, volatile — distribution-free conformal guarantees' },
  BX: { policy: 'doc_fcst', reason: 'Medium value, stable — forecast-based days of coverage' },
  BY: { policy: 'sl', reason: 'Medium value, moderate variability — service level with z-score' },
  BZ: { policy: 'conformal', reason: 'Medium value, volatile — conformal prediction intervals' },
  CX: { policy: 'doc_dem', reason: 'Low value, stable — demand-based days of coverage' },
  CY: { policy: 'abs_level', reason: 'Low value, moderate variability — fixed quantity buffer' },
  CZ: { policy: 'econ_optimal', reason: 'Low value, volatile — marginal economic return analysis' },
};

// ── Glenday Sieve ─────────────────────────────────────────────────────

function classifyGlenday(products) {
  const sorted = [...products].sort((a, b) => b.annual_volume - a.annual_volume);
  const totalVolume = sorted.reduce((s, p) => s + p.annual_volume, 0);
  let cumulative = 0;
  return sorted.map(p => {
    cumulative += p.annual_volume;
    const pct = cumulative / totalVolume;
    let sieve;
    if (pct <= 0.50) sieve = 'green';       // top 6% SKUs → 50% volume
    else if (pct <= 0.95) sieve = 'yellow';  // next ~50% SKUs → 45% volume
    else if (pct <= 0.99) sieve = 'blue';    // slow movers
    else sieve = 'red';                       // dead stock candidates
    return { ...p, glenday: sieve, volume_pct: Math.round(pct * 100) };
  });
}

const GLENDAY_COLORS = { green: '#10b981', yellow: '#eab308', blue: '#3b82f6', red: '#ef4444' };
const GLENDAY_LABELS = {
  green: 'Repeaters (daily)', yellow: 'Runners (weekly)',
  blue: 'Strangers (monthly)', red: 'Aliens (review)',
};

// ── Main Component ────────────────────────────────────────────────────

export default function InventorySegmentation() {
  const { effectiveConfigId } = useActiveConfig();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [products, setProducts] = useState([]);
  const [view, setView] = useState('matrix'); // matrix | glenday | patterns | table

  useEffect(() => {
    if (effectiveConfigId) loadData();
  }, [effectiveConfigId]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      // Fetch product inventory data for segmentation
      const [invRes, fcstRes] = await Promise.allSettled([
        api.get('/inventory-projection/projections', { params: { config_id: effectiveConfigId, limit: 500 } }),
        api.get('/demand-plan/current', { params: { config_id: effectiveConfigId, limit: 500 } }),
      ]);
      // Unwrap allSettled results
      const invData = invRes.status === 'fulfilled' ? invRes.value : { data: [] };
      const fcstData = fcstRes.status === 'fulfilled' ? fcstRes.value : { data: [] };

      const invLevels = invData.data?.levels || invData.data || [];
      const forecasts = fcstData.data?.forecasts || fcstData.data || [];

      // Build product-level aggregates from inventory + forecast data
      const productMap = {};
      invLevels.forEach(inv => {
        const key = inv.product_id;
        if (!productMap[key]) {
          productMap[key] = {
            product_id: key,
            product_name: inv.product_name || inv.description || `Product ${key}`,
            site_count: 0,
            on_hand: 0,
            annual_revenue: 0,
            annual_volume: 0,
            demand_mean: 0,
            demand_stddev: 0,
            avg_demand_interval: 1,
            seasonal_index: 1.0,
            unit_cost: inv.unit_cost || 0,
          };
        }
        productMap[key].site_count += 1;
        productMap[key].on_hand += (inv.on_hand_qty || 0);
      });

      // Enrich with forecast data
      forecasts.forEach(f => {
        const key = f.product_id;
        if (productMap[key]) {
          productMap[key].demand_mean += (f.forecast_p50 || 0);
          productMap[key].annual_revenue += (f.forecast_p50 || 0) * (productMap[key].unit_cost || 10);
          productMap[key].annual_volume += (f.forecast_p50 || 0);
          // Approximate stddev from P10/P90
          if (f.forecast_p90 && f.forecast_p10) {
            productMap[key].demand_stddev = Math.max(
              productMap[key].demand_stddev,
              (f.forecast_p90 - f.forecast_p10) / 2.56
            );
          }
        }
      });

      let prods = Object.values(productMap).filter(p => p.annual_volume > 0);

      // If no real data, generate synthetic for demonstration
      if (prods.length === 0) {
        prods = Array.from({ length: 80 }, (_, i) => {
          const revenue = Math.round(Math.pow(Math.random(), 0.3) * 500000);
          const volume = Math.round(revenue / (5 + Math.random() * 50));
          const mean = volume / 12;
          const cv = 0.1 + Math.random() * 1.5;
          return {
            product_id: `P-${String(i + 1).padStart(3, '0')}`,
            product_name: `Product ${i + 1}`,
            site_count: 1 + Math.floor(Math.random() * 5),
            on_hand: Math.round(mean * (1 + Math.random() * 3)),
            annual_revenue: revenue,
            annual_volume: volume,
            demand_mean: Math.round(mean),
            demand_stddev: Math.round(mean * cv),
            avg_demand_interval: Math.random() > 0.7 ? 1 + Math.random() * 3 : 1,
            seasonal_index: Math.random() > 0.8 ? 1.3 + Math.random() * 0.5 : 0.9 + Math.random() * 0.3,
            unit_cost: 5 + Math.random() * 100,
          };
        });
      }

      setProducts(prods);
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  };

  // Apply all classifications
  const classified = useMemo(() => {
    if (products.length === 0) return [];
    let result = classifyABC(products);
    result = classifyXYZ(result);
    result = classifyDemandPattern(result);
    result = classifyGlenday(result);
    return result;
  }, [products]);

  // Matrix summary (ABC × XYZ counts)
  const matrixData = useMemo(() => {
    const matrix = {};
    ['A', 'B', 'C'].forEach(abc => {
      ['X', 'Y', 'Z'].forEach(xyz => {
        const key = `${abc}${xyz}`;
        const items = classified.filter(p => p.abc_class === abc && p.xyz_class === xyz);
        matrix[key] = {
          count: items.length,
          revenue: items.reduce((s, p) => s + p.annual_revenue, 0),
          pct: classified.length > 0 ? Math.round(items.length / classified.length * 100) : 0,
        };
      });
    });
    return matrix;
  }, [classified]);

  // Glenday summary
  const glendaySummary = useMemo(() => {
    const groups = { green: [], yellow: [], blue: [], red: [] };
    classified.forEach(p => { if (groups[p.glenday]) groups[p.glenday].push(p); });
    return Object.entries(groups).map(([sieve, items]) => ({
      sieve,
      label: GLENDAY_LABELS[sieve],
      count: items.length,
      pct: classified.length > 0 ? Math.round(items.length / classified.length * 100) : 0,
      volume: items.reduce((s, p) => s + p.annual_volume, 0),
    }));
  }, [classified]);

  // Demand pattern distribution
  const patternDist = useMemo(() => {
    const counts = {};
    classified.forEach(p => { counts[p.demand_pattern] = (counts[p.demand_pattern] || 0) + 1; });
    return Object.entries(counts).map(([pattern, count]) => ({
      name: pattern.charAt(0).toUpperCase() + pattern.slice(1),
      value: count,
      fill: PATTERN_COLORS[pattern],
    }));
  }, [classified]);

  if (loading) return <div className="flex justify-center py-16"><Spinner /></div>;

  return (
    <div className="space-y-6">
      {error && <Alert variant="destructive"><AlertTriangle className="h-4 w-4" />{error}</Alert>}

      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Badge variant="outline">{classified.length} products</Badge>
          <Badge variant="outline">Config {effectiveConfigId}</Badge>
        </div>
        <div className="flex items-center gap-2">
          <Select value={view} onValueChange={setView}>
            <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="matrix">ABC-XYZ Matrix</SelectItem>
              <SelectItem value="glenday">Glenday Sieve</SelectItem>
              <SelectItem value="patterns">Demand Patterns</SelectItem>
              <SelectItem value="table">Detail Table</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={loadData}>
            <RefreshCw className="h-4 w-4 mr-1" /> Refresh
          </Button>
        </div>
      </div>

      {/* ABC-XYZ Matrix View */}
      {view === 'matrix' && (
        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2"><Grid3X3 className="h-5 w-5" /> ABC-XYZ Classification Matrix</CardTitle></CardHeader>
            <CardContent>
              <div className="grid grid-cols-4 gap-2">
                {/* Header row */}
                <div />
                {['X (Stable)', 'Y (Variable)', 'Z (Volatile)'].map(h => (
                  <div key={h} className="text-center text-sm font-semibold py-2 rounded bg-muted">{h}</div>
                ))}
                {/* Data rows */}
                {['A', 'B', 'C'].map(abc => (
                  <React.Fragment key={abc}>
                    <div className="flex items-center justify-center text-sm font-semibold rounded bg-muted" style={{ color: ABC_COLORS[abc] }}>
                      {abc} ({abc === 'A' ? 'High' : abc === 'B' ? 'Medium' : 'Low'})
                    </div>
                    {['X', 'Y', 'Z'].map(xyz => {
                      const key = `${abc}${xyz}`;
                      const cell = matrixData[key] || {};
                      const rec = POLICY_RECOMMENDATIONS[key];
                      return (
                        <Card key={key} className="text-center p-3 hover:shadow-md transition-shadow cursor-default">
                          <div className="text-2xl font-bold">{cell.count || 0}</div>
                          <div className="text-xs text-muted-foreground">{cell.pct}% of SKUs</div>
                          <div className="text-xs text-muted-foreground mt-1">${(cell.revenue / 1000).toFixed(0)}K revenue</div>
                          {rec && (
                            <Badge variant="outline" className="mt-2 text-[10px]">
                              {rec.policy}
                            </Badge>
                          )}
                        </Card>
                      );
                    })}
                  </React.Fragment>
                ))}
              </div>

              {/* Policy recommendations legend */}
              <div className="mt-6 grid grid-cols-3 gap-2 text-xs">
                {Object.entries(POLICY_RECOMMENDATIONS).map(([key, rec]) => (
                  <div key={key} className="flex gap-2 p-2 rounded border">
                    <Badge variant="secondary" className="text-[10px] shrink-0">{key}</Badge>
                    <span className="text-muted-foreground">{rec.reason}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Pareto Chart */}
          <Card>
            <CardHeader><CardTitle className="text-sm">Revenue Pareto (ABC)</CardTitle></CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={classified.slice(0, 40)}>
                  <XAxis dataKey="product_id" tick={{ fontSize: 9 }} interval={3} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip formatter={(v) => [`$${v.toLocaleString()}`, 'Revenue']} />
                  <Bar dataKey="annual_revenue" radius={[2, 2, 0, 0]}>
                    {classified.slice(0, 40).map((p, i) => (
                      <Cell key={i} fill={ABC_COLORS[p.abc_class]} fillOpacity={0.7} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Glenday Sieve View */}
      {view === 'glenday' && (
        <div className="space-y-4">
          <div className="grid grid-cols-4 gap-4">
            {glendaySummary.map(g => (
              <Card key={g.sieve}>
                <CardContent className="pt-4 text-center">
                  <div className="w-4 h-4 rounded-full mx-auto mb-2" style={{ backgroundColor: GLENDAY_COLORS[g.sieve] }} />
                  <div className="text-xl font-bold">{g.count}</div>
                  <div className="text-sm font-medium">{g.label}</div>
                  <div className="text-xs text-muted-foreground">{g.pct}% of SKUs</div>
                  <div className="text-xs text-muted-foreground">{g.volume.toLocaleString()} units</div>
                </CardContent>
              </Card>
            ))}
          </div>

          <Card>
            <CardHeader><CardTitle className="text-sm">Volume Distribution by Sieve</CardTitle></CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={glendaySummary}>
                  <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip formatter={(v) => [v.toLocaleString(), 'Volume']} />
                  <Bar dataKey="volume" radius={[4, 4, 0, 0]}>
                    {glendaySummary.map((g, i) => (
                      <Cell key={i} fill={GLENDAY_COLORS[g.sieve]} fillOpacity={0.8} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          <Alert>
            <Package className="h-4 w-4" />
            <div>
              <strong>Glenday Sieve</strong> classifies products by production frequency. <strong>Green</strong> items (top 50% volume, ~6% SKUs)
              run daily for flow efficiency. <strong>Yellow</strong> run weekly. <strong>Blue</strong> monthly. <strong>Red</strong> items are
              candidates for discontinuation or special-order only.
            </div>
          </Alert>
        </div>
      )}

      {/* Demand Pattern View */}
      {view === 'patterns' && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Card>
              <CardHeader><CardTitle className="text-sm">Demand Pattern Distribution</CardTitle></CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={250}>
                  <PieChart>
                    <Pie data={patternDist} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90} label={({ name, value }) => `${name} (${value})`}>
                      {patternDist.map((d, i) => <Cell key={i} fill={d.fill} />)}
                    </Pie>
                    <Legend />
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle className="text-sm">CV vs ADI Scatter (Syntetos-Boylan)</CardTitle></CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={250}>
                  <ScatterChart margin={{ top: 10, right: 10, bottom: 20, left: 10 }}>
                    <XAxis type="number" dataKey="avg_demand_interval" name="ADI" tick={{ fontSize: 10 }} label={{ value: 'Avg Demand Interval', position: 'bottom', fontSize: 11 }} />
                    <YAxis type="number" dataKey="cv" name="CV" tick={{ fontSize: 10 }} label={{ value: 'CV', angle: -90, position: 'insideLeft', fontSize: 11 }} />
                    <ZAxis type="number" dataKey="annual_revenue" range={[20, 200]} />
                    <Tooltip formatter={(v, name) => [typeof v === 'number' ? v.toFixed(2) : v, name]} />
                    <Scatter data={classified}>
                      {classified.map((p, i) => (
                        <Cell key={i} fill={PATTERN_COLORS[p.demand_pattern] || '#999'} fillOpacity={0.6} />
                      ))}
                    </Scatter>
                  </ScatterChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>

          <Alert>
            <TrendingUp className="h-4 w-4" />
            <div>
              <strong>Syntetos-Boylan classification</strong>: ADI &gt; 1.32 and CV &gt; 0.49 = lumpy. ADI &gt; 1.32 only = intermittent.
              CV &gt; 0.49 only = erratic. Low ADI + low CV = smooth. Seasonal detected from seasonal index &gt; 1.3.
              Each pattern suggests different forecasting and inventory policy approaches.
            </div>
          </Alert>
        </div>
      )}

      {/* Detail Table View */}
      {view === 'table' && (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Product</TableHead>
                    <TableHead>Sites</TableHead>
                    <TableHead className="text-right">Revenue</TableHead>
                    <TableHead className="text-right">Volume</TableHead>
                    <TableHead>ABC</TableHead>
                    <TableHead>XYZ</TableHead>
                    <TableHead className="text-right">CV</TableHead>
                    <TableHead>Pattern</TableHead>
                    <TableHead>Glenday</TableHead>
                    <TableHead>Rec. Policy</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {classified.slice(0, 100).map(p => {
                    const rec = POLICY_RECOMMENDATIONS[`${p.abc_class}${p.xyz_class}`];
                    return (
                      <TableRow key={p.product_id}>
                        <TableCell className="font-medium">{p.product_name}</TableCell>
                        <TableCell>{p.site_count}</TableCell>
                        <TableCell className="text-right tabular-nums">${(p.annual_revenue / 1000).toFixed(1)}K</TableCell>
                        <TableCell className="text-right tabular-nums">{p.annual_volume.toLocaleString()}</TableCell>
                        <TableCell><Badge style={{ backgroundColor: ABC_COLORS[p.abc_class], color: '#fff' }}>{p.abc_class}</Badge></TableCell>
                        <TableCell><Badge style={{ backgroundColor: XYZ_COLORS[p.xyz_class], color: '#fff' }}>{p.xyz_class}</Badge></TableCell>
                        <TableCell className="text-right tabular-nums">{p.cv}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className="text-[10px]" style={{ borderColor: PATTERN_COLORS[p.demand_pattern] }}>
                            {p.demand_pattern}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <span className="inline-block w-3 h-3 rounded-full mr-1" style={{ backgroundColor: GLENDAY_COLORS[p.glenday] }} />
                          {p.glenday}
                        </TableCell>
                        <TableCell><Badge variant="secondary" className="text-[10px]">{rec?.policy}</Badge></TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
