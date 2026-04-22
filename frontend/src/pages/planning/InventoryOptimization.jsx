import React, { useState, useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Card,
  CardContent,
  Button,
  Alert,
  AlertDescription,
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
} from '../../components/common';
import {
  Package,
  Settings2,
  Calculator,
  RefreshCw,
  Play,
  CheckCircle,
  AlertTriangle,
  TrendingUp,
  Shield,
  Target,
  Layers,
  Sparkles,
  BarChart3,
  Info,
} from 'lucide-react';
import { api } from '../../services/api';
import { useActiveConfig } from '../../contexts/ActiveConfigContext';
import { useDisplayPreferences } from '../../contexts/DisplayPreferencesContext';
import BranchPicker from '../../components/planning/BranchPicker';

/**
 * Tactical Inventory Optimization
 *
 * Optimizes safety stock and reorder points across the supply chain network.
 *
 * Supports 5 safety stock policy types:
 * 1. abs_level - Absolute level (fixed safety stock quantity)
 * 2. doc_dem - Days of coverage based on historical demand
 * 3. doc_fcst - Days of coverage based on forecast
 * 4. sl - Service level using King Formula (accounts for demand AND lead time variability)
 * 5. conformal - Conformal prediction-based (distribution-free guarantees)
 *
 * Features:
 * - Multi-echelon inventory optimization
 * - Policy comparison and what-if analysis
 * - Hierarchical override management
 * - Safety stock recommendations
 * - Conformal prediction integration with formal coverage guarantees
 *
 * Planning Horizon: Typically 3-12 months (tactical)
 */
const InventoryOptimization = () => {
  const location = useLocation();
  const filtersApplied = useRef(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [activeTab, setActiveTab] = useState('policies');

  // Hydrate tab from Talk To Me query routing
  useEffect(() => {
    const filters = location.state?.filters;
    if (filters?.tab && !filtersApplied.current) {
      filtersApplied.current = true;
      setActiveTab(filters.tab);
      window.history.replaceState({}, '');
    }
  }, [location.state]);

  const { effectiveConfigId } = useActiveConfig();
  const { formatProduct, formatSite, loadLookupsForConfig } = useDisplayPreferences();

  useEffect(() => { if (effectiveConfigId) loadLookupsForConfig(effectiveConfigId); }, [effectiveConfigId, loadLookupsForConfig]);

  // Data states
  const [policies, setPolicies] = useState([]);
  const [optimizations, setOptimizations] = useState([]);

  // Optimization dialog
  const [runOptDialogOpen, setRunOptDialogOpen] = useState(false);
  const [optRequest, setOptRequest] = useState({
    product_id: '',
    site_id: '',
    optimization_method: 'newsvendor',
    target_service_level: 95,
    holding_cost_pct: 25,
    stockout_cost_factor: 10,
  });

  // Policy editor dialog
  const [policyDialogOpen, setPolicyDialogOpen] = useState(false);
  const [policyForm, setPolicyForm] = useState({
    product_id: '',
    site_id: '',
    ss_policy: 'sl',
    ss_quantity: '',
    ss_days: '',
    service_level: 95,
    review_period: 7,
    min_qty: '',
    max_qty: '',
    // Conformal prediction fields
    conformal_demand_coverage: 90,
    conformal_lead_time_coverage: 90,
  });

  // Conformal suite status
  const [conformalStatus, setConformalStatus] = useState(null);

  useEffect(() => {
    loadConformalStatus();
  }, []);

  const loadConformalStatus = async () => {
    try {
      const response = await api.get('/conformal-prediction/suite/status');
      setConformalStatus(response.data);
    } catch (err) {
      // API might not be available
      setConformalStatus(null);
    }
  };

  useEffect(() => {
    if (effectiveConfigId) {
      loadPolicies();
      loadOptimizations();
    }
  }, [effectiveConfigId]);

  const loadPolicies = async () => {
    setLoading(true);
    try {
      const response = await api.get('/inv-policy', {
        params: { config_id: effectiveConfigId, limit: 100 },
      });
      setPolicies(response.data.items || response.data || []);
    } catch (err) {
      // API might not exist yet - use empty array
      setPolicies([]);
    } finally {
      setLoading(false);
    }
  };

  const loadOptimizations = async () => {
    try {
      const response = await api.get('/analytics-optimization/inventory-optimization', {
        params: { limit: 50 },
      });
      setOptimizations(response.data || []);
    } catch (err) {
      // API might return error if no data
      setOptimizations([]);
    }
  };

  const handleRunOptimization = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.post('/analytics-optimization/inventory-optimization', {
        ...optRequest,
        optimization_date: new Date().toISOString().split('T')[0],
        current_safety_stock: 0,
        recommended_safety_stock: 0, // Will be calculated
        expected_service_level: optRequest.target_service_level,
      });
      setSuccess('Optimization run submitted successfully');
      setRunOptDialogOpen(false);
      loadOptimizations();
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSavePolicy = async () => {
    setLoading(true);
    setError(null);
    try {
      await api.post('/inv-policy', {
        config_id: effectiveConfigId,
        ...policyForm,
        ss_quantity: policyForm.ss_quantity ? parseFloat(policyForm.ss_quantity) : null,
        ss_days: policyForm.ss_days ? parseInt(policyForm.ss_days) : null,
        service_level: policyForm.service_level / 100,
        min_qty: policyForm.min_qty ? parseFloat(policyForm.min_qty) : null,
        max_qty: policyForm.max_qty ? parseFloat(policyForm.max_qty) : null,
        // Conformal prediction fields (stored as decimals)
        conformal_demand_coverage: policyForm.conformal_demand_coverage / 100,
        conformal_lead_time_coverage: policyForm.conformal_lead_time_coverage / 100,
      });
      setSuccess('Policy saved successfully');
      setPolicyDialogOpen(false);
      loadPolicies();
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  };

  const getPolicyTypeLabel = (type) => {
    const labels = {
      abs_level: 'Absolute Level',
      doc_dem: 'Days of Coverage (Demand)',
      doc_fcst: 'Days of Coverage (Forecast)',
      sl: 'Service Level (King)',
      conformal: 'Conformal Prediction',
    };
    return labels[type] || type;
  };

  const getPolicyTypeBadgeVariant = (type) => {
    const variants = {
      abs_level: 'secondary',
      doc_dem: 'default',
      doc_fcst: 'outline',
      sl: 'success',
      conformal: 'warning',
    };
    return variants[type] || 'secondary';
  };

  const getStatusBadgeVariant = (status) => {
    const variants = {
      pending: 'secondary',
      approved: 'success',
      applied: 'default',
      rejected: 'destructive',
    };
    return variants[status] || 'secondary';
  };

  const renderPoliciesTab = () => (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-semibold">Inventory Policies</h3>
        <Button onClick={() => setPolicyDialogOpen(true)} leftIcon={<Settings2 className="h-4 w-4" />}>
          Add Policy
        </Button>
      </div>

      <Card>
        <CardContent className="pt-4">
          {policies.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <Layers className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>No inventory policies configured</p>
              <p className="text-sm mt-2">Add policies to define safety stock calculation rules</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Product</TableHead>
                  <TableHead>Site</TableHead>
                  <TableHead>Policy Type</TableHead>
                  <TableHead className="text-right">SS Qty / Days</TableHead>
                  <TableHead className="text-right">Service Level</TableHead>
                  <TableHead className="text-right">Review Period</TableHead>
                  <TableHead className="text-right">Min/Max</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {policies.map((policy) => (
                  <TableRow key={policy.id}>
                    <TableCell>{policy.product_id ? formatProduct(policy.product_id) : 'All'}</TableCell>
                    <TableCell>{policy.site_id ? formatSite(policy.site_id) : 'All'}</TableCell>
                    <TableCell>
                      <Badge variant={getPolicyTypeBadgeVariant(policy.ss_policy)}>
                        {getPolicyTypeLabel(policy.ss_policy)}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      {policy.ss_policy === 'abs_level'
                        ? policy.ss_quantity?.toFixed(0) || '-'
                        : policy.ss_days
                          ? `${policy.ss_days} days`
                          : '-'}
                    </TableCell>
                    <TableCell className="text-right">
                      {policy.service_level ? `${(policy.service_level * 100).toFixed(0)}%` : '-'}
                    </TableCell>
                    <TableCell className="text-right">{policy.review_period ? `${policy.review_period} days` : '-'}</TableCell>
                    <TableCell className="text-right">
                      {policy.min_qty || policy.max_qty
                        ? `${policy.min_qty?.toFixed(0) || '-'} / ${policy.max_qty?.toFixed(0) || '-'}`
                        : '-'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );

  const renderOptimizationsTab = () => (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-semibold">Optimization Runs</h3>
        <Button onClick={() => setRunOptDialogOpen(true)} leftIcon={<Play className="h-4 w-4" />}>
          Run Optimization
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Total Runs</p>
                <p className="text-2xl font-bold">{optimizations.length}</p>
              </div>
              <Calculator className="h-8 w-8 text-muted-foreground/30" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Pending Approval</p>
                <p className="text-2xl font-bold text-amber-600">
                  {optimizations.filter((o) => o.status === 'pending').length}
                </p>
              </div>
              <AlertTriangle className="h-8 w-8 text-amber-600/30" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Approved</p>
                <p className="text-2xl font-bold text-green-600">
                  {optimizations.filter((o) => o.status === 'approved').length}
                </p>
              </div>
              <CheckCircle className="h-8 w-8 text-green-600/30" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Applied</p>
                <p className="text-2xl font-bold text-blue-600">
                  {optimizations.filter((o) => o.status === 'applied').length}
                </p>
              </div>
              <Target className="h-8 w-8 text-blue-600/30" />
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="pt-4">
          {optimizations.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <Calculator className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>No optimization runs yet</p>
              <p className="text-sm mt-2">Run an optimization to calculate recommended safety stock levels</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Product</TableHead>
                  <TableHead>Site</TableHead>
                  <TableHead>Method</TableHead>
                  <TableHead className="text-right">Current SS</TableHead>
                  <TableHead className="text-right">Recommended SS</TableHead>
                  <TableHead className="text-right">Service Level</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {optimizations.map((opt) => (
                  <TableRow key={opt.id}>
                    <TableCell>{opt.optimization_date}</TableCell>
                    <TableCell>{opt.product_id ? formatProduct(opt.product_id) : '-'}</TableCell>
                    <TableCell>{opt.site_id ? formatSite(opt.site_id) : '-'}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{opt.optimization_method}</Badge>
                    </TableCell>
                    <TableCell className="text-right">{opt.current_safety_stock?.toFixed(0) || '-'}</TableCell>
                    <TableCell className="text-right font-medium">{opt.recommended_safety_stock?.toFixed(0)}</TableCell>
                    <TableCell className="text-right">{opt.expected_service_level?.toFixed(0)}%</TableCell>
                    <TableCell>
                      <Badge variant={getStatusBadgeVariant(opt.status)}>{opt.status}</Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );

  const renderMethodologyTab = () => (
    <div className="space-y-6">
      <Card>
        <CardContent className="pt-6">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Safety Stock Policy Types
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[
              {
                type: 'abs_level',
                name: 'Absolute Level',
                desc: 'Fixed safety stock quantity. Use when demand is stable and predictable.',
                formula: 'SS = Fixed Quantity',
                badge: 'secondary',
                icon: Target,
              },
              {
                type: 'doc_dem',
                name: 'Days of Coverage (Demand)',
                desc: 'Safety stock based on historical demand. Adapts to actual consumption patterns.',
                formula: 'SS = Days × Avg Daily Demand',
                badge: 'default',
                icon: BarChart3,
              },
              {
                type: 'doc_fcst',
                name: 'Days of Coverage (Forecast)',
                desc: 'Safety stock based on forecast. Good for seasonal or promotional items.',
                formula: 'SS = Days × Avg Daily Forecast',
                badge: 'outline',
                icon: TrendingUp,
              },
              {
                type: 'sl',
                name: 'Service Level (King Formula)',
                desc: 'Probabilistic calculation accounting for BOTH demand AND lead time variability.',
                formula: 'SS = z × √(LT×σ_d² + d²×σ_LT²)',
                badge: 'success',
                icon: Shield,
              },
              {
                type: 'conformal',
                name: 'Conformal Prediction',
                desc: 'Distribution-free method with formal coverage guarantees. No normality assumption required.',
                formula: 'SS = Worst_Case_LT - Expected_LT',
                badge: 'warning',
                icon: Sparkles,
                highlight: true,
              },
            ].map((policy) => (
              <div
                key={policy.type}
                className={`border rounded-lg p-4 ${policy.highlight ? 'border-amber-500 bg-amber-50/50 dark:bg-amber-900/10' : ''}`}
              >
                <div className="flex items-center gap-2 mb-2">
                  {policy.icon && <policy.icon className="h-4 w-4 text-muted-foreground" />}
                  <Badge variant={policy.badge}>{policy.name}</Badge>
                  {policy.highlight && (
                    <Badge variant="outline" className="text-xs">AI-Powered</Badge>
                  )}
                </div>
                <p className="text-sm text-muted-foreground mb-2">{policy.desc}</p>
                <code className="text-xs bg-muted px-2 py-1 rounded">{policy.formula}</code>
                {policy.type === 'conformal' && (
                  <div className="mt-3 p-2 bg-muted/50 rounded text-xs">
                    <div className="flex items-center gap-1 text-amber-700 dark:text-amber-400">
                      <Info className="h-3 w-3" />
                      <span>Joint coverage = demand_coverage × lead_time_coverage</span>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Layers className="h-5 w-5" />
            Hierarchical Override Logic
          </h3>
          <p className="text-muted-foreground mb-4">
            Policies are applied with hierarchical overrides. More specific policies take precedence over general ones.
          </p>
          <div className="space-y-2">
            {[
              { level: 1, name: 'Product + Site', desc: 'Most specific - individual SKU at specific site' },
              { level: 2, name: 'Product Group + Site', desc: 'Category-level policy at specific site' },
              { level: 3, name: 'Product + Geography', desc: 'SKU-level policy for a region' },
              { level: 4, name: 'Product Group + Geography', desc: 'Category policy for a region' },
              { level: 5, name: 'Segment', desc: 'Market segment default' },
              { level: 6, name: 'Company', desc: 'Company-wide default - lowest priority' },
            ].map((item) => (
              <div key={item.level} className="flex items-center gap-4 py-2 border-b last:border-0">
                <div className="w-8 h-8 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold text-sm">
                  {item.level}
                </div>
                <div>
                  <p className="font-medium">{item.name}</p>
                  <p className="text-xs text-muted-foreground">{item.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="flex justify-between items-center mb-6">
        <div className="flex items-center gap-2">
          <Package className="h-8 w-8 text-primary" />
          <div>
            <h1 className="text-2xl font-bold">Inventory Optimization</h1>
            <p className="text-sm text-muted-foreground">Tactical safety stock and reorder point optimization</p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <BranchPicker />
          </div>
          <Button variant="outline" onClick={() => { loadPolicies(); loadOptimizations(); }} leftIcon={<RefreshCw className="h-4 w-4" />}>
            Refresh
          </Button>
        </div>
      </div>

      {error && (
        <Alert variant="destructive" className="mb-4" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {success && (
        <Alert variant="success" className="mb-4" onClose={() => setSuccess(null)}>
          {success}
        </Alert>
      )}

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="mb-4">
          <TabsTrigger value="policies" className="flex items-center gap-2">
            <Settings2 className="h-4 w-4" />
            Policies
          </TabsTrigger>
          <TabsTrigger value="optimizations" className="flex items-center gap-2">
            <Calculator className="h-4 w-4" />
            Optimization Runs
          </TabsTrigger>
          <TabsTrigger value="methodology" className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4" />
            Methodology
          </TabsTrigger>
        </TabsList>

        {loading && !policies.length ? (
          <div className="flex justify-center p-8">
            <Spinner size="lg" />
          </div>
        ) : (
          <>
            <TabsContent value="policies">{renderPoliciesTab()}</TabsContent>
            <TabsContent value="optimizations">{renderOptimizationsTab()}</TabsContent>
            <TabsContent value="methodology">{renderMethodologyTab()}</TabsContent>
          </>
        )}
      </Tabs>

      {/* Run Optimization Dialog */}
      <Modal isOpen={runOptDialogOpen} onClose={() => setRunOptDialogOpen(false)} title="Run Inventory Optimization">
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="optProductId">Product ID (optional)</Label>
              <Input
                id="optProductId"
                value={optRequest.product_id}
                onChange={(e) => setOptRequest({ ...optRequest, product_id: e.target.value })}
                placeholder="Leave empty for all"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="optSiteId">Site ID (optional)</Label>
              <Input
                id="optSiteId"
                value={optRequest.site_id}
                onChange={(e) => setOptRequest({ ...optRequest, site_id: e.target.value })}
                placeholder="Leave empty for all"
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label>Optimization Method</Label>
            <Select
              value={optRequest.optimization_method}
              onValueChange={(value) => setOptRequest({ ...optRequest, optimization_method: value })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="newsvendor">Newsvendor Model</SelectItem>
                <SelectItem value="base_stock">Base Stock Policy</SelectItem>
                <SelectItem value="ss_rop">Safety Stock + ROP</SelectItem>
                <SelectItem value="monte_carlo">Monte Carlo Simulation</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div className="space-y-2">
              <Label htmlFor="targetSL">Target Service Level (%)</Label>
              <Input
                id="targetSL"
                type="number"
                min={50}
                max={99.9}
                step={0.1}
                value={optRequest.target_service_level}
                onChange={(e) => setOptRequest({ ...optRequest, target_service_level: parseFloat(e.target.value) })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="holdingCost">Holding Cost (%/yr)</Label>
              <Input
                id="holdingCost"
                type="number"
                min={0}
                max={100}
                value={optRequest.holding_cost_pct}
                onChange={(e) => setOptRequest({ ...optRequest, holding_cost_pct: parseFloat(e.target.value) })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="stockoutCost">Stockout Cost Factor</Label>
              <Input
                id="stockoutCost"
                type="number"
                min={1}
                max={100}
                value={optRequest.stockout_cost_factor}
                onChange={(e) => setOptRequest({ ...optRequest, stockout_cost_factor: parseFloat(e.target.value) })}
              />
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <Button variant="outline" onClick={() => setRunOptDialogOpen(false)}>
            Cancel
          </Button>
          <Button onClick={handleRunOptimization} disabled={loading}>
            {loading ? <Spinner size="sm" className="mr-2" /> : <Play className="h-4 w-4 mr-2" />}
            Run Optimization
          </Button>
        </div>
      </Modal>

      {/* Add Policy Dialog */}
      <Modal isOpen={policyDialogOpen} onClose={() => setPolicyDialogOpen(false)} title="Add Inventory Policy">
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="policyProductId">Product ID (optional)</Label>
              <Input
                id="policyProductId"
                value={policyForm.product_id}
                onChange={(e) => setPolicyForm({ ...policyForm, product_id: e.target.value })}
                placeholder="Leave empty for all"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="policySiteId">Site ID (optional)</Label>
              <Input
                id="policySiteId"
                value={policyForm.site_id}
                onChange={(e) => setPolicyForm({ ...policyForm, site_id: e.target.value })}
                placeholder="Leave empty for all"
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label>Policy Type</Label>
            <Select
              value={policyForm.ss_policy}
              onValueChange={(value) => setPolicyForm({ ...policyForm, ss_policy: value })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="abs_level">Absolute Level (fixed quantity)</SelectItem>
                <SelectItem value="doc_dem">Days of Coverage (demand-based)</SelectItem>
                <SelectItem value="doc_fcst">Days of Coverage (forecast-based)</SelectItem>
                <SelectItem value="sl">Service Level - King Formula (probabilistic)</SelectItem>
                <SelectItem value="conformal">Conformal Prediction (distribution-free)</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {policyForm.ss_policy === 'abs_level' && (
            <div className="space-y-2">
              <Label htmlFor="ssQty">Safety Stock Quantity</Label>
              <Input
                id="ssQty"
                type="number"
                min={0}
                value={policyForm.ss_quantity}
                onChange={(e) => setPolicyForm({ ...policyForm, ss_quantity: e.target.value })}
              />
            </div>
          )}

          {(policyForm.ss_policy === 'doc_dem' || policyForm.ss_policy === 'doc_fcst') && (
            <div className="space-y-2">
              <Label htmlFor="ssDays">Days of Coverage</Label>
              <Input
                id="ssDays"
                type="number"
                min={1}
                max={90}
                value={policyForm.ss_days}
                onChange={(e) => setPolicyForm({ ...policyForm, ss_days: e.target.value })}
              />
            </div>
          )}

          {policyForm.ss_policy === 'sl' && (
            <div className="space-y-2">
              <Label htmlFor="serviceLevel">Service Level (%)</Label>
              <Input
                id="serviceLevel"
                type="number"
                min={50}
                max={99.9}
                step={0.1}
                value={policyForm.service_level}
                onChange={(e) => setPolicyForm({ ...policyForm, service_level: parseFloat(e.target.value) })}
              />
              <p className="text-xs text-muted-foreground">
                Uses King Formula: SS = z × √(LT × σ_d² + d² × σ_LT²)
              </p>
            </div>
          )}

          {policyForm.ss_policy === 'conformal' && (
            <div className="space-y-4 p-4 border rounded-lg bg-amber-50/50 dark:bg-amber-900/10">
              <div className="flex items-center gap-2 mb-2">
                <Sparkles className="h-4 w-4 text-amber-600" />
                <span className="font-medium text-sm">Conformal Prediction Settings</span>
              </div>

              <Alert className="mb-4">
                <AlertDescription className="text-xs">
                  Conformal prediction provides <strong>distribution-free coverage guarantees</strong>.
                  Joint coverage = demand_coverage × lead_time_coverage
                  (e.g., 90% × 90% = 81% joint coverage)
                </AlertDescription>
              </Alert>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="demandCoverage">Demand Coverage (%)</Label>
                  <Input
                    id="demandCoverage"
                    type="number"
                    min={50}
                    max={99}
                    step={1}
                    value={policyForm.conformal_demand_coverage}
                    onChange={(e) => setPolicyForm({ ...policyForm, conformal_demand_coverage: parseFloat(e.target.value) })}
                  />
                  <p className="text-xs text-muted-foreground">
                    {policyForm.conformal_demand_coverage}% of actual demand falls within interval
                  </p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="leadTimeCoverage">Lead Time Coverage (%)</Label>
                  <Input
                    id="leadTimeCoverage"
                    type="number"
                    min={50}
                    max={99}
                    step={1}
                    value={policyForm.conformal_lead_time_coverage}
                    onChange={(e) => setPolicyForm({ ...policyForm, conformal_lead_time_coverage: parseFloat(e.target.value) })}
                  />
                  <p className="text-xs text-muted-foreground">
                    {policyForm.conformal_lead_time_coverage}% of actual lead times fall within interval
                  </p>
                </div>
              </div>

              <div className="p-3 bg-muted rounded-lg">
                <div className="flex justify-between items-center">
                  <span className="text-sm font-medium">Joint Coverage Guarantee:</span>
                  <Badge variant="warning" className="text-lg">
                    {((policyForm.conformal_demand_coverage / 100) * (policyForm.conformal_lead_time_coverage / 100) * 100).toFixed(0)}%
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  This is the probability that BOTH demand AND lead time fall within their respective intervals
                </p>
              </div>

              {conformalStatus && (
                <div className="text-xs text-muted-foreground border-t pt-2 mt-2">
                  <strong>Suite Status:</strong>{' '}
                  {conformalStatus.summary?.demand_predictors || 0} demand predictors,{' '}
                  {conformalStatus.summary?.lead_time_predictors || 0} lead time predictors calibrated
                </div>
              )}
            </div>
          )}

          <div className="grid grid-cols-3 gap-4">
            <div className="space-y-2">
              <Label htmlFor="reviewPeriod">Review Period (days)</Label>
              <Input
                id="reviewPeriod"
                type="number"
                min={1}
                max={30}
                value={policyForm.review_period}
                onChange={(e) => setPolicyForm({ ...policyForm, review_period: parseInt(e.target.value) })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="minQty">Min Qty</Label>
              <Input
                id="minQty"
                type="number"
                min={0}
                value={policyForm.min_qty}
                onChange={(e) => setPolicyForm({ ...policyForm, min_qty: e.target.value })}
                placeholder="Optional"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="maxQty">Max Qty</Label>
              <Input
                id="maxQty"
                type="number"
                min={0}
                value={policyForm.max_qty}
                onChange={(e) => setPolicyForm({ ...policyForm, max_qty: e.target.value })}
                placeholder="Optional"
              />
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <Button variant="outline" onClick={() => setPolicyDialogOpen(false)}>
            Cancel
          </Button>
          <Button onClick={handleSavePolicy} disabled={loading}>
            {loading ? <Spinner size="sm" className="mr-2" /> : <CheckCircle className="h-4 w-4 mr-2" />}
            Save Policy
          </Button>
        </div>
      </Modal>
    </div>
  );
};

export default InventoryOptimization;
