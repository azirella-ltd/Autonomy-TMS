import React, { useState, useEffect } from 'react';
import { useDisplayPreferences } from '../../contexts/DisplayPreferencesContext';
import { useActiveConfig } from '../../contexts/ActiveConfigContext';
import LevelPeggingGantt from '../../components/planning/LevelPeggingGantt';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Badge,
  Label,
  Input,
  Spinner,
  Modal,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
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
  Tooltip,
} from '../../components/common';
import {
  Package,
  TrendingUp,
  TrendingDown,
  CheckCircle,
  AlertTriangle,
  XCircle,
  RefreshCw,
  Calculator,
  Search,
  GitBranch,
} from 'lucide-react';
import { Line, Bar } from 'react-chartjs-2';
import { api } from '../../services/api';

const InventoryProjection = () => {
  const { formatProduct, formatSite } = useDisplayPreferences();
  const { effectiveConfigId } = useActiveConfig();
  const [peggingTarget, setPeggingTarget] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('projections');

  // Projection data
  const [projections, setProjections] = useState([]);
  const [summary, setSummary] = useState(null);

  // ATP data
  const [atpProjections, setAtpProjections] = useState([]);
  const [atpAvailability, setAtpAvailability] = useState(null);

  // CTP data
  const [ctpProjections, setCtpProjections] = useState([]);
  const [ctpAvailability, setCtpAvailability] = useState(null);

  // Order promises
  const [promises, setPromises] = useState([]);

  // Hierarchy filters
  const [dimensions, setDimensions] = useState(null);
  const [productNodeId, setProductNodeId] = useState('');
  const [geoFilter, setGeoFilter] = useState('');

  // Filters
  const [productId, setProductId] = useState('');
  const [siteId, setSiteId] = useState('');
  const [startDate, setStartDate] = useState(null);
  const [endDate, setEndDate] = useState(null);
  const [scenarioId, setScenarioId] = useState('');

  // Dialogs
  const [calculateAtpDialogOpen, setCalculateAtpDialogOpen] = useState(false);
  const [calculateCtpDialogOpen, setCalculateCtpDialogOpen] = useState(false);
  const [promiseOrderDialogOpen, setPromiseOrderDialogOpen] = useState(false);

  // Dialog data
  const [atpRequest, setAtpRequest] = useState({
    product_id: '',
    site_id: '',
    start_date: new Date(),
    end_date: new Date(Date.now() + 90 * 24 * 60 * 60 * 1000),
    atp_rule: 'cumulative',
  });

  const [ctpRequest, setCtpRequest] = useState({
    product_id: '',
    site_id: '',
    start_date: new Date(),
    end_date: new Date(Date.now() + 90 * 24 * 60 * 60 * 1000),
    include_production_capacity: true,
    check_component_availability: true,
    check_resource_capacity: true,
  });

  const [promiseRequest, setPromiseRequest] = useState({
    order_id: '',
    order_line_number: 1,
    product_id: '',
    site_id: '',
    customer_id: '',
    requested_quantity: 0,
    requested_date: new Date(),
    allow_partial: true,
    allow_substitute: false,
    allow_backorder: true,
  });

  const [promiseResult, setPromiseResult] = useState(null);

  // Load hierarchy dimensions
  useEffect(() => {
    if (!effectiveConfigId) return;
    api.get('/demand-plan/hierarchy-dimensions', { params: { config_id: effectiveConfigId } })
      .then(res => {
        setDimensions(res.data);
        // Auto-select root product node if not already set
        if (!productNodeId && res.data?.product_tree?.length > 0) {
          const root = res.data.product_tree.find(n => !n.parent_id);
          if (root) setProductNodeId(String(root.id));
        }
        // Auto-select root geography node if not already set
        if (!geoFilter && res.data?.geography?.length > 0) {
          const root = res.data.geography.find(g => !g.parent_id);
          if (root) setGeoFilter(root.id);
        }
      })
      .catch(() => {});
  }, [effectiveConfigId]);

  useEffect(() => {
    loadData();
  }, [activeTab, productId, siteId, startDate, endDate, scenarioId]);

  const loadData = async () => {
    setLoading(true);
    setError(null);

    try {
      if (activeTab === 'projections') {
        await loadProjections();
        await loadSummary();
      } else if (activeTab === 'atp') {
        if (productId && siteId) {
          await loadAtpAvailability();
        }
      } else if (activeTab === 'ctp') {
        if (productId && siteId) {
          await loadCtpAvailability();
        }
      } else if (activeTab === 'promises') {
        await loadPromises();
      }
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  };

  const loadProjections = async () => {
    const params = {};
    if (productId) params.product_id = productId;
    if (siteId) params.site_id = siteId;
    if (startDate) params.start_date = startDate.toISOString().split('T')[0];
    if (endDate) params.end_date = endDate.toISOString().split('T')[0];
    if (scenarioId) params.scenario_id = scenarioId;

    const response = await api.get('/inventory-projection/projections', { params });
    setProjections(response.data.items);
  };

  const loadSummary = async () => {
    const params = {};
    if (productId) params.product_id = productId;
    if (siteId) params.site_id = siteId;
    if (startDate) params.start_date = startDate.toISOString().split('T')[0];
    if (endDate) params.end_date = endDate.toISOString().split('T')[0];

    const response = await api.get('/inventory-projection/projections/summary', { params });
    setSummary(response.data);
  };

  const loadAtpAvailability = async () => {
    const params = { product_id: productId, site_id: siteId };
    if (startDate) params.start_date = startDate.toISOString().split('T')[0];
    if (endDate) params.end_date = endDate.toISOString().split('T')[0];

    const response = await api.get('/inventory-projection/atp/availability', { params });
    setAtpAvailability(response.data);
  };

  const loadCtpAvailability = async () => {
    const params = { product_id: productId, site_id: siteId };
    if (startDate) params.start_date = startDate.toISOString().split('T')[0];
    if (endDate) params.end_date = endDate.toISOString().split('T')[0];

    const response = await api.get('/inventory-projection/ctp/availability', { params });
    setCtpAvailability(response.data);
  };

  const loadPromises = async () => {
    const params = {};
    if (productId) params.product_id = productId;

    const response = await api.get('/inventory-projection/promises', { params });
    setPromises(response.data.items);
  };

  const handleCalculateAtp = async () => {
    try {
      setLoading(true);
      const response = await api.post('/inventory-projection/atp/calculate', atpRequest);
      setAtpProjections(response.data);
      setCalculateAtpDialogOpen(false);
      setError(null);
      alert(`ATP calculated successfully! ${response.data.length} periods generated.`);
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCalculateCtp = async () => {
    try {
      setLoading(true);
      const response = await api.post('/inventory-projection/ctp/calculate', ctpRequest);
      setCtpProjections(response.data);
      setCalculateCtpDialogOpen(false);
      setError(null);
      alert(`CTP calculated successfully! ${response.data.length} periods generated.`);
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  };

  const handlePromiseOrder = async () => {
    try {
      setLoading(true);
      const response = await api.post('/inventory-projection/promise', promiseRequest);
      setPromiseResult(response.data);
      setError(null);
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  };

  const getStockoutRiskVariant = (probability) => {
    if (!probability) return 'secondary';
    if (probability >= 0.5) return 'destructive';
    if (probability >= 0.2) return 'warning';
    return 'success';
  };

  const getDaysOfSupplyColor = (dos) => {
    if (!dos) return 'text-muted-foreground';
    if (dos >= 30) return 'text-green-600';
    if (dos >= 14) return 'text-amber-600';
    return 'text-red-600';
  };

  const renderSummaryDashboard = () => {
    if (!summary) return null;

    return (
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <Card>
          <CardContent className="pt-4">
            <div className="flex justify-between items-start">
              <div>
                <p className="text-3xl font-bold text-primary">{summary.total_projections}</p>
                <p className="text-sm text-muted-foreground">Total Projections</p>
                <p className="text-xs text-muted-foreground">{summary.date_range}</p>
              </div>
              <Package className="h-10 w-10 text-primary opacity-30" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <div className="flex justify-between items-start">
              <div>
                <p className="text-3xl font-bold text-green-600">{summary.total_atp.toFixed(0)}</p>
                <p className="text-sm text-muted-foreground">Total ATP</p>
                <p className="text-xs text-muted-foreground">Available-to-Promise</p>
              </div>
              <CheckCircle className="h-10 w-10 text-green-600 opacity-30" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <div className="flex justify-between items-start">
              <div>
                <p className="text-3xl font-bold text-blue-600">{summary.total_ctp.toFixed(0)}</p>
                <p className="text-sm text-muted-foreground">Total CTP</p>
                <p className="text-xs text-muted-foreground">Capable-to-Promise</p>
              </div>
              <TrendingUp className="h-10 w-10 text-blue-600 opacity-30" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <div className="flex justify-between items-start">
              <div>
                <p className={`text-3xl font-bold ${summary.stockout_count > 0 ? 'text-red-600' : 'text-green-600'}`}>
                  {summary.stockout_count}
                </p>
                <p className="text-sm text-muted-foreground">Stockouts</p>
                <p className="text-xs text-muted-foreground">{summary.high_risk_products} high risk</p>
              </div>
              {summary.stockout_count > 0 ? (
                <AlertTriangle className="h-10 w-10 text-red-600 opacity-30" />
              ) : (
                <CheckCircle className="h-10 w-10 text-green-600 opacity-30" />
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    );
  };

  const renderProjectionsTab = () => (
    <div>
      {renderSummaryDashboard()}

      <Card>
        <CardContent className="pt-4">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Product ID</TableHead>
                <TableHead>Site ID</TableHead>
                <TableHead className="text-right">On Hand</TableHead>
                <TableHead className="text-right">Available</TableHead>
                <TableHead className="text-right">ATP</TableHead>
                <TableHead className="text-right">CTP</TableHead>
                <TableHead className="text-right">Closing Inv</TableHead>
                <TableHead className="text-right">DOS</TableHead>
                <TableHead className="text-center">Stockout Risk</TableHead>
                <TableHead className="text-center">Pegging</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {projections.map((proj) => (
                <TableRow key={proj.id}>
                  <TableCell>{proj.projection_date}</TableCell>
                  <TableCell>{formatProduct(proj.product_id)}</TableCell>
                  <TableCell>{formatSite(proj.site_id)}</TableCell>
                  <TableCell className="text-right">{proj.on_hand_qty.toFixed(0)}</TableCell>
                  <TableCell className="text-right">{proj.available_qty.toFixed(0)}</TableCell>
                  <TableCell className="text-right">{proj.atp_qty.toFixed(0)}</TableCell>
                  <TableCell className="text-right">{proj.ctp_qty.toFixed(0)}</TableCell>
                  <TableCell className={`text-right ${proj.closing_inventory < 0 ? 'text-red-600' : ''}`}>
                    {proj.closing_inventory.toFixed(0)}
                  </TableCell>
                  <TableCell className={`text-right ${getDaysOfSupplyColor(proj.days_of_supply)}`}>
                    {proj.days_of_supply ? proj.days_of_supply.toFixed(1) : 'N/A'}
                  </TableCell>
                  <TableCell className="text-center">
                    {proj.stockout_probability ? (
                      <Badge variant={getStockoutRiskVariant(proj.stockout_probability)}>
                        {(proj.stockout_probability * 100).toFixed(0)}%
                      </Badge>
                    ) : (
                      'N/A'
                    )}
                  </TableCell>
                  <TableCell className="text-center">
                    <Tooltip content="View Pegging">
                      <button
                        className="inline-flex items-center justify-center rounded-md p-1.5 text-muted-foreground hover:text-primary hover:bg-muted transition-colors"
                        onClick={() => setPeggingTarget({
                          productId: proj.product_id,
                          siteId: proj.site_id,
                          demandDate: proj.projection_date,
                          demandType: 'INVENTORY_PROJECTION',
                        })}
                      >
                        <GitBranch className="h-4 w-4" />
                      </button>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );

  const renderAtpTab = () => (
    <div>
      <div className="mb-4">
        <Button onClick={() => setCalculateAtpDialogOpen(true)} leftIcon={<Calculator className="h-4 w-4" />}>
          Calculate ATP
        </Button>
      </div>

      {atpAvailability && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <Card>
              <CardContent className="pt-4">
                <h3 className="text-lg font-semibold">Current ATP</h3>
                <p className="text-3xl font-bold text-green-600">{atpAvailability.current_atp.toFixed(0)}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4">
                <h3 className="text-lg font-semibold">Total Available</h3>
                <p className="text-3xl font-bold text-blue-600">{atpAvailability.total_available.toFixed(0)}</p>
              </CardContent>
            </Card>
          </div>

          {atpAvailability.future_atp && atpAvailability.future_atp.length > 0 && (
            <Card>
              <CardContent className="pt-4">
                <h3 className="text-lg font-semibold mb-4">ATP Trend</h3>
                <Line
                  data={{
                    labels: atpAvailability.future_atp.map((a) => a.date),
                    datasets: [
                      {
                        label: 'Cumulative ATP',
                        data: atpAvailability.future_atp.map((a) => a.cumulative_atp),
                        borderColor: 'rgb(75, 192, 192)',
                        backgroundColor: 'rgba(75, 192, 192, 0.2)',
                      },
                    ],
                  }}
                  options={{
                    responsive: true,
                    plugins: { legend: { position: 'top' } },
                  }}
                />
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );

  const renderCtpTab = () => (
    <div>
      <div className="mb-4">
        <Button onClick={() => setCalculateCtpDialogOpen(true)} leftIcon={<Calculator className="h-4 w-4" />}>
          Calculate CTP
        </Button>
      </div>

      {ctpAvailability && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <Card>
              <CardContent className="pt-4">
                <h3 className="text-lg font-semibold">Current CTP</h3>
                <p className="text-3xl font-bold text-primary">{ctpAvailability.current_ctp.toFixed(0)}</p>
              </CardContent>
            </Card>
            <Card className="md:col-span-2">
              <CardContent className="pt-4">
                <h3 className="text-lg font-semibold mb-2">Constraints</h3>
                {ctpAvailability.constraints && ctpAvailability.constraints.length > 0 ? (
                  <div className="flex gap-2 flex-wrap">
                    {ctpAvailability.constraints.map((c, idx) => (
                      <Badge key={idx} variant="warning" className="flex items-center gap-1">
                        <AlertTriangle className="h-3 w-3" />
                        {c}
                      </Badge>
                    ))}
                  </div>
                ) : (
                  <p className="text-green-600">No constraints</p>
                )}
              </CardContent>
            </Card>
          </div>

          {ctpAvailability.future_ctp && ctpAvailability.future_ctp.length > 0 && (
            <Card>
              <CardContent className="pt-4">
                <h3 className="text-lg font-semibold mb-4">CTP Projection</h3>
                <Bar
                  data={{
                    labels: ctpAvailability.future_ctp.map((c) => c.date),
                    datasets: [
                      {
                        label: 'CTP Quantity',
                        data: ctpAvailability.future_ctp.map((c) => c.ctp_qty),
                        backgroundColor: ctpAvailability.future_ctp.map((c) =>
                          c.constrained ? 'rgba(255, 99, 132, 0.6)' : 'rgba(54, 162, 235, 0.6)'
                        ),
                      },
                    ],
                  }}
                  options={{
                    responsive: true,
                    plugins: { legend: { position: 'top' } },
                  }}
                />
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );

  const renderPromisesTab = () => (
    <div>
      <div className="mb-4">
        <Button onClick={() => setPromiseOrderDialogOpen(true)} leftIcon={<CheckCircle className="h-4 w-4" />}>
          Promise Order
        </Button>
      </div>

      <Card>
        <CardContent className="pt-4">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Order ID</TableHead>
                <TableHead>Product ID</TableHead>
                <TableHead className="text-right">Requested Qty</TableHead>
                <TableHead className="text-right">Promised Qty</TableHead>
                <TableHead>Requested Date</TableHead>
                <TableHead>Promised Date</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Confidence</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {promises.map((promise) => (
                <TableRow key={promise.id}>
                  <TableCell>
                    {promise.order_id}-{promise.order_line_number}
                  </TableCell>
                  <TableCell>{formatProduct(promise.product_id)}</TableCell>
                  <TableCell className="text-right">{promise.requested_quantity}</TableCell>
                  <TableCell className="text-right">{promise.promised_quantity}</TableCell>
                  <TableCell>{promise.requested_date}</TableCell>
                  <TableCell>{promise.promised_date}</TableCell>
                  <TableCell>
                    <Badge variant="secondary">{promise.promise_source}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant={promise.promise_status === 'CONFIRMED' ? 'success' : 'secondary'}>
                      {promise.promise_status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    {promise.promise_confidence ? `${(promise.promise_confidence * 100).toFixed(0)}%` : 'N/A'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="flex justify-between items-center mb-6">
        <div className="flex items-center gap-2">
          <Package className="h-8 w-8 text-primary" />
          <h1 className="text-2xl font-bold">Inventory Projection & ATP/CTP</h1>
        </div>
        <Button variant="outline" onClick={loadData} leftIcon={<RefreshCw className="h-4 w-4" />}>
          Refresh
        </Button>
      </div>

      {error && (
        <Alert variant="destructive" className="mb-4" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Filters */}
      <Card className="mb-6">
        <CardContent className="pt-4">
          <div className="grid grid-cols-1 md:grid-cols-6 gap-4 items-end">
            {/* Product hierarchy dropdown */}
            <div className="space-y-2">
              <Label>Product</Label>
              {dimensions?.product_tree?.length > 0 ? (() => {
                const tree = dimensions.product_tree;
                const findNode = (id) => tree.find(n => n.id === id);
                const childrenOf = (pid) => tree.filter(n => n.parent_id === pid);
                const breadcrumb = [];
                let cur = productNodeId ? findNode(parseInt(productNodeId)) : null;
                while (cur) { breadcrumb.unshift(cur); cur = cur.parent_id ? findNode(cur.parent_id) : null; }
                const children = productNodeId ? childrenOf(parseInt(productNodeId)) : tree.filter(n => !n.parent_id);
                return (
                  <div>
                    {breadcrumb.length > 0 && (
                      <div className="flex items-center gap-1 mb-1 text-xs">
                        <button className="text-primary hover:underline" onClick={() => setProductNodeId('')}>All</button>
                        {breadcrumb.map((n, i) => (
                          <span key={n.id} className="flex items-center gap-1">
                            <span className="text-muted-foreground">/</span>
                            <button className={i === breadcrumb.length - 1 ? 'font-semibold' : 'text-primary hover:underline'}
                              onClick={() => setProductNodeId(String(n.id))}>{n.name}</button>
                          </span>
                        ))}
                      </div>
                    )}
                    {children.length > 0 && (
                      <select className="border rounded px-2 py-1.5 text-sm w-full" value=""
                        onChange={e => { if (e.target.value) setProductNodeId(e.target.value); }}>
                        <option value="">{productNodeId ? 'Drill deeper...' : 'Select product group...'}</option>
                        {children.map(n => <option key={n.id} value={n.id}>{n.name}</option>)}
                      </select>
                    )}
                  </div>
                );
              })() : (
                <Input id="productId" type="number" value={productId} onChange={(e) => setProductId(e.target.value)} placeholder="Product ID" />
              )}
            </div>
            {/* Geography hierarchy dropdown */}
            <div className="space-y-2">
              <Label>Site / Geography</Label>
              {dimensions?.geography?.length > 0 ? (() => {
                const findGeo = (id) => dimensions.geography.find(g => g.id === id);
                const childrenOf = (pid) => dimensions.geography.filter(g => g.parent_id === pid);
                const breadcrumb = [];
                let cur = geoFilter ? findGeo(geoFilter) : null;
                while (cur) { breadcrumb.unshift(cur); cur = cur.parent_id ? findGeo(cur.parent_id) : null; }
                const children = geoFilter ? childrenOf(geoFilter) : dimensions.geography.filter(g => !g.parent_id);
                return (
                  <div>
                    {breadcrumb.length > 0 && (
                      <div className="flex items-center gap-1 mb-1 text-xs">
                        <button className="text-primary hover:underline" onClick={() => setGeoFilter('')}>All</button>
                        {breadcrumb.map((g, i) => (
                          <span key={g.id} className="flex items-center gap-1">
                            <span className="text-muted-foreground">/</span>
                            <button className={i === breadcrumb.length - 1 ? 'font-semibold' : 'text-primary hover:underline'}
                              onClick={() => setGeoFilter(g.id)}>{g.name}</button>
                          </span>
                        ))}
                      </div>
                    )}
                    {children.length > 0 && (
                      <select className="border rounded px-2 py-1.5 text-sm w-full" value=""
                        onChange={e => { if (e.target.value) setGeoFilter(e.target.value); }}>
                        <option value="">{geoFilter ? 'Drill deeper...' : 'Select region...'}</option>
                        {children.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
                      </select>
                    )}
                  </div>
                );
              })() : (
                <Input id="siteId" type="number" value={siteId} onChange={(e) => setSiteId(e.target.value)} placeholder="Site ID" />
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="startDate">Start Date</Label>
              <Input
                id="startDate"
                type="date"
                value={startDate ? startDate.toISOString().split('T')[0] : ''}
                onChange={(e) => setStartDate(e.target.value ? new Date(e.target.value) : null)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="endDate">End Date</Label>
              <Input
                id="endDate"
                type="date"
                value={endDate ? endDate.toISOString().split('T')[0] : ''}
                onChange={(e) => setEndDate(e.target.value ? new Date(e.target.value) : null)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="scenarioId">Scenario ID</Label>
              <Input id="scenarioId" value={scenarioId} onChange={(e) => setScenarioId(e.target.value)} />
            </div>
            <Button onClick={loadData} className="w-full" leftIcon={<Search className="h-4 w-4" />}>
              Search
            </Button>
          </div>
        </CardContent>
      </Card>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="mb-4">
          <TabsTrigger value="projections" className="flex items-center gap-2">
            <Package className="h-4 w-4" />
            Inventory Projections
          </TabsTrigger>
          <TabsTrigger value="atp" className="flex items-center gap-2">
            <CheckCircle className="h-4 w-4" />
            ATP (Available-to-Promise)
          </TabsTrigger>
          <TabsTrigger value="ctp" className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4" />
            CTP (Capable-to-Promise)
          </TabsTrigger>
          <TabsTrigger value="promises" className="flex items-center gap-2">
            <CheckCircle className="h-4 w-4" />
            Order Promises
          </TabsTrigger>
        </TabsList>

        {loading ? (
          <div className="flex justify-center p-8">
            <Spinner size="lg" />
          </div>
        ) : (
          <>
            <TabsContent value="projections">{renderProjectionsTab()}</TabsContent>
            <TabsContent value="atp">{renderAtpTab()}</TabsContent>
            <TabsContent value="ctp">{renderCtpTab()}</TabsContent>
            <TabsContent value="promises">{renderPromisesTab()}</TabsContent>
          </>
        )}
      </Tabs>

      {/* Level Pegging Gantt */}
      {peggingTarget && effectiveConfigId && peggingTarget.productId && peggingTarget.siteId && (
        <LevelPeggingGantt
          configId={effectiveConfigId}
          productId={peggingTarget.productId}
          siteId={peggingTarget.siteId}
          demandDate={peggingTarget.demandDate}
          demandType={peggingTarget.demandType}
          onClose={() => setPeggingTarget(null)}
        />
      )}

      {/* Calculate ATP Dialog */}
      <Modal isOpen={calculateAtpDialogOpen} onClose={() => setCalculateAtpDialogOpen(false)} title="Calculate ATP">
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="atpProductId">Product ID</Label>
            <Input
              id="atpProductId"
              type="number"
              value={atpRequest.product_id}
              onChange={(e) => setAtpRequest({ ...atpRequest, product_id: parseInt(e.target.value) })}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="atpSiteId">Site ID</Label>
            <Input
              id="atpSiteId"
              type="number"
              value={atpRequest.site_id}
              onChange={(e) => setAtpRequest({ ...atpRequest, site_id: parseInt(e.target.value) })}
            />
          </div>
          <div className="space-y-2">
            <Label>ATP Rule</Label>
            <Select
              value={atpRequest.atp_rule}
              onValueChange={(value) => setAtpRequest({ ...atpRequest, atp_rule: value })}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select ATP rule" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="discrete">Discrete</SelectItem>
                <SelectItem value="cumulative">Cumulative</SelectItem>
                <SelectItem value="rolling">Rolling</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="outline" onClick={() => setCalculateAtpDialogOpen(false)}>
            Cancel
          </Button>
          <Button onClick={handleCalculateAtp} disabled={loading}>
            {loading ? <Spinner size="sm" className="mr-2" /> : null}
            Calculate
          </Button>
        </div>
      </Modal>

      {/* Calculate CTP Dialog */}
      <Modal isOpen={calculateCtpDialogOpen} onClose={() => setCalculateCtpDialogOpen(false)} title="Calculate CTP">
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="ctpProductId">Product ID</Label>
            <Input
              id="ctpProductId"
              type="number"
              value={ctpRequest.product_id}
              onChange={(e) => setCtpRequest({ ...ctpRequest, product_id: parseInt(e.target.value) })}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="ctpSiteId">Site ID</Label>
            <Input
              id="ctpSiteId"
              type="number"
              value={ctpRequest.site_id}
              onChange={(e) => setCtpRequest({ ...ctpRequest, site_id: parseInt(e.target.value) })}
            />
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="outline" onClick={() => setCalculateCtpDialogOpen(false)}>
            Cancel
          </Button>
          <Button onClick={handleCalculateCtp} disabled={loading}>
            {loading ? <Spinner size="sm" className="mr-2" /> : null}
            Calculate
          </Button>
        </div>
      </Modal>

      {/* Promise Order Dialog */}
      <Modal
        isOpen={promiseOrderDialogOpen}
        onClose={() => {
          setPromiseOrderDialogOpen(false);
          setPromiseResult(null);
        }}
        title="Promise Order"
        size="lg"
      >
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="orderId">Order ID</Label>
              <Input
                id="orderId"
                value={promiseRequest.order_id}
                onChange={(e) => setPromiseRequest({ ...promiseRequest, order_id: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="promiseProductId">Product ID</Label>
              <Input
                id="promiseProductId"
                type="number"
                value={promiseRequest.product_id}
                onChange={(e) => setPromiseRequest({ ...promiseRequest, product_id: parseInt(e.target.value) })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="promiseSiteId">Site ID</Label>
              <Input
                id="promiseSiteId"
                type="number"
                value={promiseRequest.site_id}
                onChange={(e) => setPromiseRequest({ ...promiseRequest, site_id: parseInt(e.target.value) })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="requestedQuantity">Requested Quantity</Label>
              <Input
                id="requestedQuantity"
                type="number"
                value={promiseRequest.requested_quantity}
                onChange={(e) =>
                  setPromiseRequest({ ...promiseRequest, requested_quantity: parseFloat(e.target.value) })
                }
              />
            </div>
          </div>

          {promiseResult && (
            <Alert variant={promiseResult.can_promise ? 'success' : 'warning'} className="mt-4">
              <div>
                <h4 className="font-semibold text-lg">
                  {promiseResult.can_promise ? 'Order Can Be Promised' : 'Cannot Fully Promise Order'}
                </h4>
                <p className="mt-1">
                  Promised Quantity: {promiseResult.promised_quantity} | Promised Date: {promiseResult.promised_date} |
                  Source: {promiseResult.promise_source}
                </p>
                <p className="text-sm mt-1">Confidence: {(promiseResult.confidence * 100).toFixed(0)}%</p>
                {promiseResult.confidence_factors && promiseResult.confidence_factors.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {promiseResult.confidence_factors.map((factor, idx) => (
                      <Badge key={idx} variant="secondary">
                        {factor}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
            </Alert>
          )}
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <Button
            variant="outline"
            onClick={() => {
              setPromiseOrderDialogOpen(false);
              setPromiseResult(null);
            }}
          >
            Close
          </Button>
          <Button onClick={handlePromiseOrder} disabled={loading}>
            {loading ? <Spinner size="sm" className="mr-2" /> : null}
            Promise
          </Button>
        </div>
      </Modal>
    </div>
  );
};

export default InventoryProjection;
