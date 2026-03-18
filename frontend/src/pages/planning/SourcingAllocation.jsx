import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Badge,
  Label,
  Input,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  Spinner,
  Modal,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from '../../components/common';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../../components/ui/tooltip';
import {
  Plus,
  Pencil,
  Trash2,
  RefreshCw,
  Save,
  X,
  Truck,
  Factory,
  ShoppingCart,
  ArrowLeftRight,
  Boxes,
} from 'lucide-react';
import { api } from '../../services/api';
import { useActiveConfig } from '../../contexts/ActiveConfigContext';
import { useDisplayPreferences } from '../../contexts/DisplayPreferencesContext';

const SourcingAllocation = () => {
  const { effectiveConfigId } = useActiveConfig();
  const { formatProduct, formatSite, formatSupplier, loadLookupsForConfig } = useDisplayPreferences();

  useEffect(() => { if (effectiveConfigId) loadLookupsForConfig(effectiveConfigId); }, [effectiveConfigId, loadLookupsForConfig]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [sourcingRules, setSourcingRules] = useState([]);
  const [products, setProducts] = useState([]);
  const [sites, setSites] = useState([]);
  const [tradingPartners, setTradingPartners] = useState([]);

  // Filters
  const [filterProductId, setFilterProductId] = useState('');
  const [filterSiteId, setFilterSiteId] = useState('');
  const [filterRuleType, setFilterRuleType] = useState('all');

  // Dialog state
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingRule, setEditingRule] = useState(null);
  const [formData, setFormData] = useState({
    id: '',
    product_id: '',
    from_site_id: '',
    to_site_id: '',
    tpartner_id: '',
    sourcing_rule_type: 'transfer',
    sourcing_priority: 1,
    sourcing_ratio: 1.0,
    min_quantity: 0,
    max_quantity: 999999,
    lot_size: 1,
    is_active: 'Y',
  });

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    loadSourcingRules();
  }, [filterProductId, filterSiteId, filterRuleType]);

  const loadData = async () => {
    try {
      const [productsRes, sitesRes, partnersRes] = await Promise.all([
        api.get('/products').catch(() => ({ data: [] })),
        api.get('/sites').catch(() => ({ data: [] })),
        api.get('/trading-partners').catch(() => ({ data: [] })),
      ]);

      setProducts(productsRes.data || []);
      setSites(sitesRes.data || []);
      setTradingPartners(partnersRes.data || []);

      await loadSourcingRules();
    } catch (err) {
      console.error('Error loading data:', err);
      setError(err.response?.data?.detail || err.message);
    }
  };

  const loadSourcingRules = async () => {
    setLoading(true);
    setError(null);

    try {
      const params = {};
      if (filterProductId) params.product_id = filterProductId;
      if (filterSiteId) params.site_id = filterSiteId;
      if (filterRuleType && filterRuleType !== 'all') params.rule_type = filterRuleType;

      const response = await api.get('/sourcing-rules', { params });
      setSourcingRules(response.data || []);
    } catch (err) {
      console.error('Failed to load sourcing rules:', err);
      setSourcingRules([]);
    } finally {
      setLoading(false);
    }
  };

  const generateMockData = () => {
    return [
      {
        id: '1',
        product_id: 'PROD-001',
        from_site_id: 'FACTORY-1',
        to_site_id: 'DC-1',
        sourcing_rule_type: 'transfer',
        sourcing_priority: 1,
        sourcing_ratio: 1.0,
        min_quantity: 0,
        max_quantity: 10000,
        lot_size: 100,
        is_active: 'Y',
      },
      {
        id: '2',
        product_id: 'PROD-001',
        from_site_id: 'SUPPLIER-A',
        to_site_id: 'FACTORY-1',
        tpartner_id: 'VENDOR-A',
        sourcing_rule_type: 'buy',
        sourcing_priority: 1,
        sourcing_ratio: 0.7,
        min_quantity: 500,
        max_quantity: 5000,
        lot_size: 500,
        is_active: 'Y',
      },
      {
        id: '3',
        product_id: 'PROD-001',
        from_site_id: 'SUPPLIER-B',
        to_site_id: 'FACTORY-1',
        tpartner_id: 'VENDOR-B',
        sourcing_rule_type: 'buy',
        sourcing_priority: 2,
        sourcing_ratio: 0.3,
        min_quantity: 200,
        max_quantity: 2000,
        lot_size: 200,
        is_active: 'Y',
      },
      {
        id: '4',
        product_id: 'COMPONENT-001',
        to_site_id: 'FACTORY-1',
        sourcing_rule_type: 'manufacture',
        sourcing_priority: 1,
        sourcing_ratio: 1.0,
        min_quantity: 0,
        max_quantity: 20000,
        lot_size: 1000,
        is_active: 'Y',
      },
    ];
  };

  const handleOpenDialog = (rule = null) => {
    if (rule) {
      setEditingRule(rule);
      setFormData({ ...rule });
    } else {
      setEditingRule(null);
      setFormData({
        id: '',
        product_id: '',
        from_site_id: '',
        to_site_id: '',
        tpartner_id: '',
        sourcing_rule_type: 'transfer',
        sourcing_priority: 1,
        sourcing_ratio: 1.0,
        min_quantity: 0,
        max_quantity: 999999,
        lot_size: 1,
        is_active: 'Y',
      });
    }
    setDialogOpen(true);
  };

  const handleCloseDialog = () => {
    setDialogOpen(false);
    setEditingRule(null);
  };

  const handleSave = async () => {
    try {
      setLoading(true);
      if (editingRule) {
        await api.put(`/sourcing-rules/${formData.id}`, formData);
        alert('Sourcing rule updated successfully');
      } else {
        await api.post('/sourcing-rules', formData);
        alert('Sourcing rule created successfully');
      }
      handleCloseDialog();
      await loadSourcingRules();
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (ruleId) => {
    if (!window.confirm('Are you sure you want to delete this sourcing rule?')) {
      return;
    }

    try {
      setLoading(true);
      await api.delete(`/sourcing-rules/${ruleId}`);
      alert('Sourcing rule deleted successfully');
      await loadSourcingRules();
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  };

  const getRuleTypeIcon = (type) => {
    switch (type) {
      case 'transfer':
        return <Truck className="h-3 w-3" />;
      case 'buy':
        return <ShoppingCart className="h-3 w-3" />;
      case 'manufacture':
        return <Factory className="h-3 w-3" />;
      default:
        return <ArrowLeftRight className="h-3 w-3" />;
    }
  };

  const getRuleTypeVariant = (type) => {
    switch (type) {
      case 'transfer':
        return 'info';
      case 'buy':
        return 'success';
      case 'manufacture':
        return 'warning';
      default:
        return 'secondary';
    }
  };

  // Summary calculations
  const totalRules = sourcingRules.length;
  const activeRules = sourcingRules.filter((r) => r.is_active === 'Y').length;
  const byType = sourcingRules.reduce((acc, rule) => {
    acc[rule.sourcing_rule_type] = (acc[rule.sourcing_rule_type] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-6">
        <div className="flex items-center gap-2">
          <Boxes className="h-6 w-6" />
          <h1 className="text-2xl font-bold">Sourcing & Allocation</h1>
        </div>
      </div>

      {error && (
        <Alert variant="error" className="mb-4" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Accordion type="single" collapsible defaultValue="overview" className="mb-4">
        <AccordionItem value="overview">
          <AccordionTrigger>Overview</AccordionTrigger>
          <AccordionContent>
            <Alert variant="info" className="mb-4">
              Sourcing rules define how products are sourced across the supply chain network. Configure
              priorities and allocation ratios for transfer, buy, and manufacture operations.
            </Alert>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
              <Card>
                <CardContent className="pt-4">
                  <p className="text-3xl font-bold text-primary">{totalRules}</p>
                  <p className="text-sm text-muted-foreground">Total Sourcing Rules</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4">
                  <p className="text-3xl font-bold text-green-600">{activeRules}</p>
                  <p className="text-sm text-muted-foreground">Active Rules</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4">
                  <div className="flex items-center gap-2">
                    <Truck className="h-5 w-5 text-blue-500" />
                    <span className="text-3xl font-bold">{byType.transfer || 0}</span>
                  </div>
                  <p className="text-sm text-muted-foreground">Transfer</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4">
                  <div className="flex items-center gap-2">
                    <ShoppingCart className="h-5 w-5 text-green-500" />
                    <span className="text-3xl font-bold">{byType.buy || 0}</span>
                  </div>
                  <p className="text-sm text-muted-foreground">Buy</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4">
                  <div className="flex items-center gap-2">
                    <Factory className="h-5 w-5 text-amber-500" />
                    <span className="text-3xl font-bold">{byType.manufacture || 0}</span>
                  </div>
                  <p className="text-sm text-muted-foreground">Manufacture</p>
                </CardContent>
              </Card>
            </div>
          </AccordionContent>
        </AccordionItem>
      </Accordion>

      {/* Filters */}
      <Card className="mb-4">
        <CardContent className="pt-4">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
            <div>
              <Label>Product ID</Label>
              <Input
                value={filterProductId}
                onChange={(e) => setFilterProductId(e.target.value)}
                placeholder="Filter by product..."
                className="mt-1"
              />
            </div>
            <div>
              <Label>Site ID</Label>
              <Input
                value={filterSiteId}
                onChange={(e) => setFilterSiteId(e.target.value)}
                placeholder="Filter by site..."
                className="mt-1"
              />
            </div>
            <div>
              <Label>Rule Type</Label>
              <Select value={filterRuleType} onValueChange={setFilterRuleType}>
                <SelectTrigger className="mt-1">
                  <SelectValue placeholder="All Types" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Types</SelectItem>
                  <SelectItem value="transfer">Transfer</SelectItem>
                  <SelectItem value="buy">Buy</SelectItem>
                  <SelectItem value="manufacture">Manufacture</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex gap-2">
              <Button onClick={() => handleOpenDialog()} leftIcon={<Plus className="h-4 w-4" />}>
                New Rule
              </Button>
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button variant="outline" size="icon" onClick={loadSourcingRules}>
                      <RefreshCw className="h-4 w-4" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Refresh</TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Rules Table */}
      <Card>
        <CardContent className="pt-4">
          <h3 className="text-lg font-medium mb-4">Sourcing Rules</h3>
          {loading && !dialogOpen ? (
            <div className="flex justify-center p-8">
              <Spinner size="lg" />
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Type</TableHead>
                  <TableHead>Product ID</TableHead>
                  <TableHead>From Site</TableHead>
                  <TableHead>To Site</TableHead>
                  <TableHead>Vendor</TableHead>
                  <TableHead className="text-center">Priority</TableHead>
                  <TableHead className="text-right">Ratio</TableHead>
                  <TableHead className="text-right">Min Qty</TableHead>
                  <TableHead className="text-right">Max Qty</TableHead>
                  <TableHead className="text-right">Lot Size</TableHead>
                  <TableHead className="text-center">Status</TableHead>
                  <TableHead className="text-center">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sourcingRules.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={12} className="text-center py-8">
                      <p className="text-muted-foreground">No sourcing rules found</p>
                    </TableCell>
                  </TableRow>
                ) : (
                  sourcingRules.map((rule) => (
                    <TableRow key={rule.id}>
                      <TableCell>
                        <Badge variant={getRuleTypeVariant(rule.sourcing_rule_type)} className="flex items-center gap-1 w-fit">
                          {getRuleTypeIcon(rule.sourcing_rule_type)}
                          {rule.sourcing_rule_type}
                        </Badge>
                      </TableCell>
                      <TableCell>{formatProduct(rule.product_id) || 'N/A'}</TableCell>
                      <TableCell>{formatSite(rule.from_site_id) || '-'}</TableCell>
                      <TableCell>{formatSite(rule.to_site_id) || '-'}</TableCell>
                      <TableCell>{formatSupplier(rule.tpartner_id) || '-'}</TableCell>
                      <TableCell className="text-center">
                        <Badge variant="outline">{rule.sourcing_priority}</Badge>
                      </TableCell>
                      <TableCell className="text-right">{rule.sourcing_ratio?.toFixed(2)}</TableCell>
                      <TableCell className="text-right">{rule.min_quantity}</TableCell>
                      <TableCell className="text-right">{rule.max_quantity}</TableCell>
                      <TableCell className="text-right">{rule.lot_size}</TableCell>
                      <TableCell className="text-center">
                        <Badge variant={rule.is_active === 'Y' ? 'success' : 'secondary'}>
                          {rule.is_active === 'Y' ? 'Active' : 'Inactive'}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="flex justify-center gap-1">
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button variant="ghost" size="sm" onClick={() => handleOpenDialog(rule)}>
                                  <Pencil className="h-4 w-4" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>Edit</TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button variant="ghost" size="sm" onClick={() => handleDelete(rule.id)}>
                                  <Trash2 className="h-4 w-4 text-destructive" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>Delete</TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Edit/Create Dialog */}
      <Modal
        open={dialogOpen}
        onClose={handleCloseDialog}
        title={editingRule ? 'Edit Sourcing Rule' : 'New Sourcing Rule'}
        size="lg"
      >
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <Label>Rule Type</Label>
              <Select
                value={formData.sourcing_rule_type}
                onValueChange={(value) => setFormData({ ...formData, sourcing_rule_type: value })}
              >
                <SelectTrigger className="mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="transfer">Transfer</SelectItem>
                  <SelectItem value="buy">Buy</SelectItem>
                  <SelectItem value="manufacture">Manufacture</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Product ID *</Label>
              <Input
                value={formData.product_id}
                onChange={(e) => setFormData({ ...formData, product_id: e.target.value })}
                className="mt-1"
              />
            </div>
            <div>
              <Label>From Site ID</Label>
              <Input
                value={formData.from_site_id}
                onChange={(e) => setFormData({ ...formData, from_site_id: e.target.value })}
                disabled={formData.sourcing_rule_type === 'manufacture'}
                className="mt-1"
              />
            </div>
            <div>
              <Label>To Site ID *</Label>
              <Input
                value={formData.to_site_id}
                onChange={(e) => setFormData({ ...formData, to_site_id: e.target.value })}
                className="mt-1"
              />
            </div>
          </div>

          {formData.sourcing_rule_type === 'buy' && (
            <div>
              <Label>Trading Partner ID (Vendor)</Label>
              <Input
                value={formData.tpartner_id}
                onChange={(e) => setFormData({ ...formData, tpartner_id: e.target.value })}
                className="mt-1"
              />
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <Label>Priority (1 = highest)</Label>
              <Input
                type="number"
                value={formData.sourcing_priority}
                onChange={(e) => setFormData({ ...formData, sourcing_priority: parseInt(e.target.value) })}
                min={1}
                className="mt-1"
              />
            </div>
            <div>
              <Label>Allocation Ratio</Label>
              <Input
                type="number"
                value={formData.sourcing_ratio}
                onChange={(e) => setFormData({ ...formData, sourcing_ratio: parseFloat(e.target.value) })}
                min={0}
                max={1}
                step={0.01}
                className="mt-1"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <Label>Min Quantity</Label>
              <Input
                type="number"
                value={formData.min_quantity}
                onChange={(e) => setFormData({ ...formData, min_quantity: parseFloat(e.target.value) })}
                min={0}
                className="mt-1"
              />
            </div>
            <div>
              <Label>Max Quantity</Label>
              <Input
                type="number"
                value={formData.max_quantity}
                onChange={(e) => setFormData({ ...formData, max_quantity: parseFloat(e.target.value) })}
                min={0}
                className="mt-1"
              />
            </div>
            <div>
              <Label>Lot Size</Label>
              <Input
                type="number"
                value={formData.lot_size}
                onChange={(e) => setFormData({ ...formData, lot_size: parseFloat(e.target.value) })}
                min={1}
                className="mt-1"
              />
            </div>
          </div>

          <div>
            <Label>Status</Label>
            <Select
              value={formData.is_active}
              onValueChange={(value) => setFormData({ ...formData, is_active: value })}
            >
              <SelectTrigger className="mt-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="Y">Active</SelectItem>
                <SelectItem value="N">Inactive</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="outline" onClick={handleCloseDialog} leftIcon={<X className="h-4 w-4" />}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={loading} leftIcon={<Save className="h-4 w-4" />}>
            {loading ? <Spinner size="sm" /> : 'Save'}
          </Button>
        </div>
      </Modal>
    </div>
  );
};

export default SourcingAllocation;
