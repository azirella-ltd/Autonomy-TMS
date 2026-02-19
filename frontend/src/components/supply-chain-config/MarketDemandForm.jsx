import React, { useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Label,
  Modal,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../common';
import { Plus, Trash2, Pencil } from 'lucide-react';
import DemandPatternInput from './DemandPatternInput';

const DEFAULT_PATTERN = {
  demand_type: 'constant',
  variability: { type: 'flat', value: 4 },
  seasonality: { type: 'none', amplitude: 0, period: 12, phase: 0 },
  trend: { type: 'none', slope: 0, intercept: 0 },
  parameters: { value: 4 },
  params: { value: 4 },
};

const MarketDemandForm = ({
  navigationButtons = null,
  demands = [],
  products = [],
  markets = [],
  onAdd,
  onUpdate,
  onDelete,
  loading = false,
  // Backward compatibility alias (deprecated)
  items = null,
}) => {
  // Use products if provided, fall back to items for backward compat
  const productList = products.length > 0 ? products : (items || []);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingDemand, setEditingDemand] = useState(null);

  const buildPattern = (incoming = {}) => ({
    demand_type: incoming.demand_type || incoming.type || DEFAULT_PATTERN.demand_type,
    variability: {
      ...DEFAULT_PATTERN.variability,
      ...(incoming.variability || {}),
    },
    seasonality: {
      ...DEFAULT_PATTERN.seasonality,
      ...(incoming.seasonality || {}),
    },
    trend: {
      ...DEFAULT_PATTERN.trend,
      ...(incoming.trend || {}),
    },
    parameters: {
      ...DEFAULT_PATTERN.parameters,
      ...(incoming.parameters || incoming.params || {}),
    },
    params: {
      ...DEFAULT_PATTERN.params,
      ...(incoming.parameters || incoming.params || {}),
    },
  });

  const [formValues, setFormValues] = useState({
    product_id: '',
    market_id: '',
    demand_pattern: buildPattern(),
  });
  const [errors, setErrors] = useState({});
  const [marketFilter, setMarketFilter] = useState('all');

  const productMap = useMemo(() => new Map(productList.map((product) => [product.id, product])), [productList]);
  const marketMap = useMemo(() => new Map(markets.map((market) => [market.id, market])), [markets]);

  const filteredDemands = useMemo(() => {
    if (marketFilter === 'all') {
      return demands;
    }
    return demands.filter((demand) => String(demand.market_id) === String(marketFilter));
  }, [demands, marketFilter]);

  const openDialog = (demand = null) => {
    if (demand) {
      setEditingDemand(demand);
      setFormValues({
        product_id: String(demand.product_id),
        market_id: String(demand.market_id),
        demand_pattern: buildPattern(demand.demand_pattern || demand.pattern || {}),
      });
    } else {
      setEditingDemand(null);
      setFormValues({
        product_id: '',
        market_id: '',
        demand_pattern: buildPattern(),
      });
    }
    setErrors({});
    setDialogOpen(true);
  };

  const closeDialog = () => {
    setDialogOpen(false);
    setEditingDemand(null);
  };

  const handlePatternChange = (pattern) => {
    setFormValues((prev) => ({ ...prev, demand_pattern: pattern }));
  };

  const validate = () => {
    const nextErrors = {};
    if (!formValues.market_id) {
      nextErrors.market_id = 'Market is required';
    }
    if (!formValues.product_id) {
      nextErrors.product_id = 'Product is required';
    }

    const duplicate = demands.some(
      (demand) =>
        demand.market_id === Number(formValues.market_id) &&
        demand.product_id === Number(formValues.product_id) &&
        (!editingDemand || demand.id !== editingDemand.id)
    );
    if (duplicate) {
      nextErrors.duplicate = 'A demand already exists for this market and product.';
    }

    if (!formValues.demand_pattern || !formValues.demand_pattern.demand_type) {
      nextErrors.demand_pattern = 'Demand pattern is required';
    }

    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!validate()) {
      return;
    }

    const payload = {
      product_id: Number(formValues.product_id),
      market_id: Number(formValues.market_id),
      demand_pattern: {
        ...formValues.demand_pattern,
        params: formValues.demand_pattern.params || formValues.demand_pattern.parameters || {},
      },
    };

    if (editingDemand) {
      await onUpdate?.(editingDemand.id, payload);
    } else {
      await onAdd?.(payload);
    }

    closeDialog();
  };

  const handleDelete = async (demandId) => {
    if (
      window.confirm(
        'Are you sure you want to delete this demand pattern? This action cannot be undone.'
      )
    ) {
      await onDelete?.(demandId);
    }
  };

  const renderPatternSummary = (pattern) => {
    if (!pattern) return '—';
    const variability = pattern.variability ? `${pattern.variability.type}` : 'n/a';
    const seasonality = pattern.seasonality?.type || 'n/a';
    const trend = pattern.trend?.type || 'n/a';
    return `Type: ${pattern.demand_type || pattern.type || 'n/a'} • Variability: ${variability} • Seasonality: ${seasonality} • Trend: ${trend}`;
  };

  const hasMarkets = markets.length > 0;

  return (
    <Card variant="outline">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Market Demands</CardTitle>
            <p className="text-sm text-muted-foreground mt-1">
              Specify demand behaviour for each market and product combination.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              onClick={() => openDialog()}
              disabled={loading || !hasMarkets || productList.length === 0}
              leftIcon={<Plus className="h-4 w-4" />}
            >
              Add Demand
            </Button>
            {navigationButtons}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {!hasMarkets ? (
          <Alert variant="info">Define at least one market before configuring demand.</Alert>
        ) : productList.length === 0 ? (
          <Alert variant="info">Add products to the configuration before defining demand.</Alert>
        ) : (
          <>
            <div className="flex gap-4 mb-4 items-center">
              <div className="w-48">
                <Label htmlFor="market-filter">Filter by Market</Label>
                <Select value={marketFilter} onValueChange={setMarketFilter}>
                  <SelectTrigger id="market-filter">
                    <SelectValue placeholder="All Markets" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Markets</SelectItem>
                    {markets.map((market) => (
                      <SelectItem key={market.id} value={String(market.id)}>
                        {market.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="border rounded-md">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Market</TableHead>
                    <TableHead>Product</TableHead>
                    <TableHead>Pattern Summary</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredDemands.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={4} className="text-center">
                        No demand patterns defined yet.
                      </TableCell>
                    </TableRow>
                  ) : (
                    filteredDemands.map((demand) => (
                      <TableRow
                        key={demand.id || `${demand.market_id}-${demand.product_id}`}
                      >
                        <TableCell>
                          {marketMap.get(demand.market_id)?.name || 'Unknown'}
                        </TableCell>
                        <TableCell>
                          {productMap.get(demand.product_id)?.name || 'Unknown'}
                        </TableCell>
                        <TableCell>
                          {renderPatternSummary(demand.demand_pattern || demand.pattern)}
                        </TableCell>
                        <TableCell className="text-right">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              openDialog({
                                ...demand,
                                demand_pattern: demand.demand_pattern || demand.pattern,
                              })
                            }
                            disabled={loading}
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-destructive"
                            onClick={() => handleDelete(demand.id)}
                            disabled={loading}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          </>
        )}
      </CardContent>

      <Modal
        isOpen={dialogOpen}
        onClose={closeDialog}
        title={editingDemand ? 'Edit Demand Pattern' : 'Add Demand Pattern'}
        size="lg"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={closeDialog}>
              Cancel
            </Button>
            <Button onClick={handleSubmit} disabled={loading}>
              {editingDemand ? 'Save Changes' : 'Add Demand'}
            </Button>
          </div>
        }
      >
        <form onSubmit={handleSubmit} className="space-y-4">
          {errors.duplicate && (
            <Alert
              variant="warning"
              onClose={() => setErrors((prev) => ({ ...prev, duplicate: undefined }))}
            >
              {errors.duplicate}
            </Alert>
          )}

          <div>
            <Label htmlFor="demand-market">Market</Label>
            <Select
              value={formValues.market_id}
              onValueChange={(value) => setFormValues((prev) => ({ ...prev, market_id: value }))}
            >
              <SelectTrigger id="demand-market" className={errors.market_id ? 'border-destructive' : ''}>
                <SelectValue placeholder="Select market" />
              </SelectTrigger>
              <SelectContent>
                {markets.map((market) => (
                  <SelectItem key={market.id} value={String(market.id)}>
                    {market.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {errors.market_id && <p className="text-sm text-destructive mt-1">{errors.market_id}</p>}
          </div>

          <div>
            <Label htmlFor="demand-product">Product</Label>
            <Select
              value={formValues.product_id}
              onValueChange={(value) => setFormValues((prev) => ({ ...prev, product_id: value }))}
            >
              <SelectTrigger id="demand-product" className={errors.product_id ? 'border-destructive' : ''}>
                <SelectValue placeholder="Select product" />
              </SelectTrigger>
              <SelectContent>
                {productList.map((product) => (
                  <SelectItem key={product.id} value={String(product.id)}>
                    {product.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {errors.product_id && <p className="text-sm text-destructive mt-1">{errors.product_id}</p>}
          </div>

          <DemandPatternInput value={formValues.demand_pattern} onChange={handlePatternChange} />
          {errors.demand_pattern && (
            <p className="text-sm text-destructive">{errors.demand_pattern}</p>
          )}
        </form>
      </Modal>
    </Card>
  );
};

export default MarketDemandForm;
