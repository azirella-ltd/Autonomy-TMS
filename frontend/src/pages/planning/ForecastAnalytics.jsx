/**
 * Forecast Analytics — EDA, demand drivers, model comparison, accuracy.
 *
 * Data pipeline workbench for demand planners to understand forecast quality,
 * identify demand drivers, and compare forecasting methods.
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, CardContent, Badge, Button, Alert,
  Tabs, TabsList, TabsTrigger, TabsContent,
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '../../components/common';
import {
  BarChart3, TrendingUp, TrendingDown, Activity, Zap, Target, RefreshCw,
} from 'lucide-react';
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, RadarChart, PolarGrid,
  PolarAngleAxis, PolarRadiusAxis, Radar, Cell,
} from 'recharts';
import { api } from '../../services/api';
import { useActiveConfig } from '../../contexts/ActiveConfigContext';

const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const DOW_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

export default function ForecastAnalytics() {
  const { effectiveConfigId } = useActiveConfig();
  const [tab, setTab] = useState('eda');
  const [eda, setEda] = useState(null);
  const [accuracy, setAccuracy] = useState(null);
  const [methods, setMethods] = useState(null);
  const [drivers, setDrivers] = useState(null);
  const [loading, setLoading] = useState(false);

  const loadData = useCallback(async () => {
    if (!effectiveConfigId) return;
    setLoading(true);
    try {
      const [edaRes, accRes, methRes, drvRes] = await Promise.all([
        api.get('/v1/forecast-analytics/eda', { params: { config_id: effectiveConfigId } }),
        api.get('/v1/forecast-analytics/accuracy', { params: { config_id: effectiveConfigId } }),
        api.get('/v1/forecast-analytics/methods', { params: { config_id: effectiveConfigId } }),
        api.get('/v1/forecast-analytics/drivers', { params: { config_id: effectiveConfigId } }),
      ]);
      setEda(edaRes.data);
      setAccuracy(accRes.data);
      setMethods(methRes.data);
      setDrivers(drvRes.data);
    } catch (err) {
      console.error('Failed to load analytics:', err);
    } finally {
      setLoading(false);
    }
  }, [effectiveConfigId]);

  useEffect(() => { loadData(); }, [loadData]);

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-xl font-bold">Forecast Analytics</h2>
          <p className="text-sm text-muted-foreground">
            Demand distribution, seasonality, accuracy, drivers, and model comparison
          </p>
        </div>
        <Button variant="outline" onClick={loadData} disabled={loading}
          leftIcon={<RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />}>
          Refresh
        </Button>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="eda">EDA</TabsTrigger>
          <TabsTrigger value="accuracy">Accuracy</TabsTrigger>
          <TabsTrigger value="drivers">Drivers</TabsTrigger>
          <TabsTrigger value="methods">Methods</TabsTrigger>
        </TabsList>

        {/* ── EDA Tab ─────────────────────────────── */}
        <TabsContent value="eda">
          {eda && (
            <div className="space-y-4">
              {/* Distribution summary */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                {[
                  { label: 'Mean Demand', value: eda.distribution?.mean, icon: Target },
                  { label: 'Std Dev', value: eda.distribution?.stddev, icon: Activity },
                  { label: 'CV %', value: `${eda.distribution?.cv_pct}%`, icon: Zap },
                  { label: 'Records', value: eda.distribution?.count?.toLocaleString(), icon: BarChart3 },
                ].map((m, i) => (
                  <Card key={i}>
                    <CardContent className="pt-3 pb-3">
                      <div className="flex items-center gap-2 mb-1">
                        <m.icon className="h-4 w-4 text-muted-foreground" />
                        <span className="text-xs text-muted-foreground">{m.label}</span>
                      </div>
                      <p className="text-xl font-bold">{m.value}</p>
                    </CardContent>
                  </Card>
                ))}
              </div>

              {/* Distribution box: Q1, Median, Q3, IQR */}
              <Card>
                <CardContent className="pt-4">
                  <h3 className="text-sm font-semibold mb-2">Distribution</h3>
                  <div className="grid grid-cols-6 gap-3 text-center text-sm">
                    {['min', 'q1', 'median', 'q3', 'max', 'iqr'].map(k => (
                      <div key={k}>
                        <p className="text-xs text-muted-foreground uppercase">{k}</p>
                        <p className="font-bold">{eda.distribution?.[k]?.toLocaleString()}</p>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>

              {/* Seasonality chart */}
              {eda.seasonality?.length > 0 && (
                <Card>
                  <CardContent className="pt-4">
                    <h3 className="text-sm font-semibold mb-2">Monthly Seasonality</h3>
                    <ResponsiveContainer width="100%" height={250}>
                      <BarChart data={eda.seasonality.map(s => ({ ...s, name: MONTH_NAMES[s.month - 1] }))}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                        <YAxis tick={{ fontSize: 10 }} />
                        <Tooltip />
                        <Bar dataKey="avg_demand" fill="#6366f1" name="Avg Demand" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              )}

              {/* Trend */}
              {eda.trend && (
                <Card>
                  <CardContent className="pt-4">
                    <h3 className="text-sm font-semibold mb-2">Trend Analysis</h3>
                    <div className="flex items-center gap-4">
                      <div>
                        <p className="text-xs text-muted-foreground">First Half Avg</p>
                        <p className="text-lg font-bold">{eda.trend.first_half_avg?.toLocaleString()}</p>
                      </div>
                      <div className="flex items-center gap-1">
                        {eda.trend.trend_pct > 0
                          ? <TrendingUp className="h-5 w-5 text-green-600" />
                          : <TrendingDown className="h-5 w-5 text-red-600" />}
                        <span className={`text-lg font-bold ${eda.trend.trend_pct > 0 ? 'text-green-600' : 'text-red-600'}`}>
                          {eda.trend.trend_pct > 0 ? '+' : ''}{eda.trend.trend_pct}%
                        </span>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Second Half Avg</p>
                        <p className="text-lg font-bold">{eda.trend.second_half_avg?.toLocaleString()}</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          )}
        </TabsContent>

        {/* ── Accuracy Tab ────────────────────────── */}
        <TabsContent value="accuracy">
          {accuracy && (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-3">
                <Card>
                  <CardContent className="pt-3">
                    <p className="text-xs text-muted-foreground">Products Analyzed</p>
                    <p className="text-2xl font-bold">{accuracy.aggregate?.total_products}</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-3">
                    <p className="text-xs text-muted-foreground">Avg CV %</p>
                    <p className="text-2xl font-bold">{accuracy.aggregate?.avg_cv_pct}%</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-3">
                    <p className="text-xs text-muted-foreground">Avg MAPE (approx)</p>
                    <p className="text-2xl font-bold">{accuracy.aggregate?.avg_mape_pct}%</p>
                  </CardContent>
                </Card>
              </div>

              <Card>
                <CardContent className="pt-4">
                  <h3 className="text-sm font-semibold mb-2">Accuracy by Product</h3>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Product</TableHead>
                        <TableHead>Category</TableHead>
                        <TableHead>Periods</TableHead>
                        <TableHead>Avg Forecast</TableHead>
                        <TableHead>CV %</TableHead>
                        <TableHead>Interval Width</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {accuracy.products?.map((p) => (
                        <TableRow key={p.product_id}>
                          <TableCell className="text-xs font-medium">{p.product_name}</TableCell>
                          <TableCell className="text-xs">{p.category}</TableCell>
                          <TableCell>{p.periods}</TableCell>
                          <TableCell>{p.avg_forecast?.toLocaleString()}</TableCell>
                          <TableCell>
                            <Badge variant={p.forecast_cv_pct > 30 ? 'destructive' : p.forecast_cv_pct > 20 ? 'warning' : 'success'}>
                              {p.forecast_cv_pct}%
                            </Badge>
                          </TableCell>
                          <TableCell>{p.avg_interval_width?.toLocaleString()}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            </div>
          )}
        </TabsContent>

        {/* ── Drivers Tab ─────────────────────────── */}
        <TabsContent value="drivers">
          {drivers && (
            <div className="space-y-4">
              <Card>
                <CardContent className="pt-4">
                  <h3 className="text-sm font-semibold mb-3">Demand Driver Correlations</h3>
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={drivers.drivers?.sort((a, b) => Math.abs(b.correlation) - Math.abs(a.correlation))}
                      layout="vertical" margin={{ left: 120 }}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis type="number" domain={[-1, 1]} tick={{ fontSize: 10 }} />
                      <YAxis type="category" dataKey="driver" tick={{ fontSize: 10 }} width={120} />
                      <Tooltip />
                      <Bar dataKey="correlation" name="Correlation" radius={[0, 4, 4, 0]}>
                        {drivers.drivers?.map((d, i) => (
                          <Cell key={i} fill={d.correlation > 0 ? '#22c55e' : '#ef4444'} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>

              <Card>
                <CardContent className="pt-4">
                  <h3 className="text-sm font-semibold mb-2">Driver Details</h3>
                  <div className="space-y-2">
                    {drivers.drivers?.map((d, i) => (
                      <div key={i} className="flex items-center justify-between py-2 border-b last:border-0">
                        <div>
                          <p className="text-sm font-medium">{d.driver}</p>
                          <p className="text-xs text-muted-foreground">{d.description}</p>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge variant="outline">{d.type}</Badge>
                          <span className={`text-sm font-bold ${d.correlation > 0 ? 'text-green-600' : 'text-red-600'}`}>
                            {d.correlation > 0 ? '+' : ''}{d.correlation.toFixed(2)}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </TabsContent>

        {/* ── Methods Tab ─────────────────────────── */}
        <TabsContent value="methods">
          {methods && (
            <div className="space-y-4">
              <Card>
                <CardContent className="pt-4">
                  <h3 className="text-sm font-semibold mb-2">Active Forecast Methods</h3>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Method</TableHead>
                        <TableHead>Records</TableHead>
                        <TableHead>Products</TableHead>
                        <TableHead>Avg Forecast</TableHead>
                        <TableHead>Avg Interval Width</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {methods.methods?.map((m) => (
                        <TableRow key={m.method}>
                          <TableCell className="font-medium">{m.method}</TableCell>
                          <TableCell>{m.records?.toLocaleString()}</TableCell>
                          <TableCell>{m.products}</TableCell>
                          <TableCell>{m.avg_forecast?.toLocaleString()}</TableCell>
                          <TableCell>{m.avg_interval_width?.toLocaleString()}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>

              <Card>
                <CardContent className="pt-4">
                  <h3 className="text-sm font-semibold mb-2">Available Methods</h3>
                  <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
                    {methods.available_methods?.map((m) => (
                      <div key={m.key} className="border rounded-lg p-3">
                        <p className="font-medium text-sm">{m.name}</p>
                        <Badge variant="outline" className="text-xs mt-1">{m.type}</Badge>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
