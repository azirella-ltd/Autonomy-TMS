import React, { useMemo, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
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
  Textarea,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../common';
import { Plus, Trash2, Pencil, ChevronDown, ChevronRight, Users } from 'lucide-react';
import DemandPatternInput from './DemandPatternInput';

/**
 * CustomerManager — AWS SC DM compliant step for managing external demand parties.
 *
 * Customers are TradingPartner records (tpartner_type='customer') representing
 * external demand sources. Each customer has one or more demand patterns per product.
 *
 * This component combines what were previously separate "Markets" and "Market Demands"
 * wizard steps into a single unified customer view, where:
 *   - A Customer (previously "Market") is a named demand pool
 *   - Demand Patterns (previously "Market Demands") are per-customer per-product
 *
 * The backend persists these in the existing Market + MarketDemand tables during the
 * Phase 1–4 migration period. Full migration to TradingPartner records is Phase 4.
 */

const DEFAULT_PATTERN = {
  demand_type: 'constant',
  variability: { type: 'flat', value: 4 },
  seasonality: { type: 'none', amplitude: 0, period: 12, phase: 0 },
  trend: { type: 'none', slope: 0, intercept: 0 },
  parameters: { value: 4 },
  params: { value: 4 },
};

const buildPattern = (incoming = {}) => ({
  demand_type: incoming.demand_type || incoming.type || DEFAULT_PATTERN.demand_type,
  variability: { ...DEFAULT_PATTERN.variability, ...(incoming.variability || {}) },
  seasonality: { ...DEFAULT_PATTERN.seasonality, ...(incoming.seasonality || {}) },
  trend: { ...DEFAULT_PATTERN.trend, ...(incoming.trend || {}) },
  parameters: { ...DEFAULT_PATTERN.parameters, ...(incoming.parameters || incoming.params || {}) },
  params: { ...DEFAULT_PATTERN.params, ...(incoming.parameters || incoming.params || {}) },
});

const PatternSummary = ({ pattern }) => {
  if (!pattern) return <span className="text-muted-foreground">—</span>;
  const type = pattern.demand_type || pattern.type || 'n/a';
  const variability = pattern.variability?.type || 'n/a';
  const seasonality = pattern.seasonality?.type || 'n/a';
  return (
    <span className="text-sm">
      <span className="font-medium capitalize">{type}</span>
      {' · '}{variability}
      {seasonality !== 'none' && <> · seasonal</>}
    </span>
  );
};

const CustomerManager = ({
  navigationButtons = null,
  customers = [],       // Market records (name, id, description)
  demands = [],         // MarketDemand records (market_id, product_id, demand_pattern)
  products = [],
  loading = false,
  onAddCustomer,
  onUpdateCustomer,
  onDeleteCustomer,
  onAddDemand,
  onUpdateDemand,
  onDeleteDemand,
}) => {
  // --- Customer (Market) dialog state ---
  const [customerDialogOpen, setCustomerDialogOpen] = useState(false);
  const [editingCustomer, setEditingCustomer] = useState(null);
  const [customerForm, setCustomerForm] = useState({ name: '', description: '' });
  const [customerErrors, setCustomerErrors] = useState({});

  // --- Demand dialog state ---
  const [demandDialogOpen, setDemandDialogOpen] = useState(false);
  const [editingDemand, setEditingDemand] = useState(null);
  const [demandCustomerId, setDemandCustomerId] = useState(null);
  const [demandForm, setDemandForm] = useState({
    product_id: '',
    demand_pattern: buildPattern(),
  });
  const [demandErrors, setDemandErrors] = useState({});

  // --- Expand/collapse per customer ---
  const [expanded, setExpanded] = useState({});

  const sortedCustomers = useMemo(
    () => [...customers].sort((a, b) => a.name.localeCompare(b.name)),
    [customers]
  );

  const productMap = useMemo(
    () => new Map(products.map((p) => [p.id, p])),
    [products]
  );

  const demandsByCustomer = useMemo(() => {
    const map = new Map();
    demands.forEach((d) => {
      const key = d.market_id;
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(d);
    });
    return map;
  }, [demands]);

  // ---- Customer CRUD ----
  const openCustomerDialog = (customer = null) => {
    setEditingCustomer(customer);
    setCustomerForm({ name: customer?.name || '', description: customer?.description || '' });
    setCustomerErrors({});
    setCustomerDialogOpen(true);
  };

  const closeCustomerDialog = () => {
    setCustomerDialogOpen(false);
    setEditingCustomer(null);
  };

  const validateCustomer = () => {
    const errs = {};
    if (!customerForm.name.trim()) errs.name = 'Customer name is required';
    if (
      !editingCustomer &&
      sortedCustomers.some(
        (c) => c.name.toLowerCase() === customerForm.name.trim().toLowerCase()
      )
    ) {
      errs.name = 'A customer with this name already exists';
    }
    setCustomerErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmitCustomer = async () => {
    if (!validateCustomer()) return;
    const payload = {
      name: customerForm.name.trim(),
      description: customerForm.description.trim() || null,
    };
    if (editingCustomer) {
      await onUpdateCustomer?.(editingCustomer.id, payload);
    } else {
      await onAddCustomer?.(payload);
    }
    closeCustomerDialog();
  };

  const handleDeleteCustomer = async (customerId) => {
    if (
      window.confirm(
        'Delete this customer? All associated demand patterns will also be removed.'
      )
    ) {
      await onDeleteCustomer?.(customerId);
    }
  };

  // ---- Demand CRUD ----
  const openDemandDialog = (customerId, demand = null) => {
    setDemandCustomerId(customerId);
    setEditingDemand(demand);
    setDemandForm({
      product_id: demand ? String(demand.product_id) : '',
      demand_pattern: buildPattern(demand?.demand_pattern || demand?.pattern || {}),
    });
    setDemandErrors({});
    setDemandDialogOpen(true);
  };

  const closeDemandDialog = () => {
    setDemandDialogOpen(false);
    setEditingDemand(null);
    setDemandCustomerId(null);
  };

  const validateDemand = () => {
    const errs = {};
    if (!demandForm.product_id) errs.product_id = 'Product is required';
    const customerDemands = demandsByCustomer.get(demandCustomerId) || [];
    const duplicate = customerDemands.some(
      (d) =>
        d.product_id === Number(demandForm.product_id) &&
        (!editingDemand || d.id !== editingDemand.id)
    );
    if (duplicate) errs.duplicate = 'A demand pattern for this product already exists for this customer.';
    if (!demandForm.demand_pattern?.demand_type) errs.demand_pattern = 'Demand pattern is required';
    setDemandErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmitDemand = async () => {
    if (!validateDemand()) return;
    const payload = {
      product_id: Number(demandForm.product_id),
      market_id: demandCustomerId,
      demand_pattern: {
        ...demandForm.demand_pattern,
        params: demandForm.demand_pattern.params || demandForm.demand_pattern.parameters || {},
      },
    };
    if (editingDemand) {
      await onUpdateDemand?.(editingDemand.id, payload);
    } else {
      await onAddDemand?.(payload);
    }
    closeDemandDialog();
  };

  const handleDeleteDemand = async (demandId) => {
    if (window.confirm('Delete this demand pattern?')) {
      await onDeleteDemand?.(demandId);
    }
  };

  const toggleExpand = (customerId) => {
    setExpanded((prev) => ({ ...prev, [customerId]: !prev[customerId] }));
  };

  return (
    <Card variant="outline">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Customers (External Demand)</CardTitle>
            <p className="text-sm text-muted-foreground mt-1">
              Add the external customers that consume products from your supply chain.
              Each customer has demand patterns per product (AWS SC: TradingPartner with tpartner_type=customer).
            </p>
          </div>
          <div className="flex items-center gap-2">
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => openCustomerDialog()}
                    disabled={loading}
                    leftIcon={<Plus className="h-4 w-4" />}
                  >
                    Add Customer
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Add an external customer</TooltipContent>
              </Tooltip>
            </TooltipProvider>
            {navigationButtons}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {products.length === 0 && (
          <Alert variant="warning" className="mb-4">
            Add products in the Products step before configuring customer demand patterns.
          </Alert>
        )}

        {sortedCustomers.length === 0 ? (
          <Alert variant="info">
            No customers defined yet. Click "Add Customer" to add an external demand source.
            Customers represent the downstream boundary of your supply network — where finished
            goods flow out.
          </Alert>
        ) : (
          <div className="space-y-3">
            {sortedCustomers.map((customer) => {
              const customerDemands = demandsByCustomer.get(customer.id) || [];
              const isExpanded = Boolean(expanded[customer.id]);
              return (
                <div key={customer.id} className="border rounded-lg overflow-hidden">
                  {/* Customer row header */}
                  <div
                    className="flex items-center justify-between px-4 py-3 bg-muted/30 cursor-pointer hover:bg-muted/50 transition-colors"
                    onClick={() => toggleExpand(customer.id)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => e.key === 'Enter' && toggleExpand(customer.id)}
                  >
                    <div className="flex items-center gap-3">
                      {isExpanded ? (
                        <ChevronDown className="h-4 w-4 text-muted-foreground" />
                      ) : (
                        <ChevronRight className="h-4 w-4 text-muted-foreground" />
                      )}
                      <Users className="h-4 w-4 text-rose-600" />
                      <span className="font-medium">{customer.name}</span>
                      {customer.description && (
                        <span className="text-xs text-muted-foreground hidden sm:inline">
                          {customer.description}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                      <Badge variant="secondary">
                        {customerDemands.length} demand pattern{customerDemands.length !== 1 ? 's' : ''}
                      </Badge>
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => openDemandDialog(customer.id)}
                              disabled={loading || products.length === 0}
                            >
                              <Plus className="h-4 w-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Add demand pattern</TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => openCustomerDialog(customer)}
                              disabled={loading}
                            >
                              <Pencil className="h-4 w-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Edit customer</TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleDeleteCustomer(customer.id)}
                              disabled={loading}
                              className="text-destructive"
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Delete customer</TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </div>
                  </div>

                  {/* Expandable demand patterns table */}
                  {isExpanded && (
                    <div className="border-t">
                      {customerDemands.length === 0 ? (
                        <div className="px-6 py-4 text-sm text-muted-foreground">
                          No demand patterns yet.{' '}
                          <button
                            className="text-primary underline"
                            onClick={() => openDemandDialog(customer.id)}
                            disabled={loading || products.length === 0}
                          >
                            Add one
                          </button>
                          .
                        </div>
                      ) : (
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Product</TableHead>
                              <TableHead>Demand Pattern</TableHead>
                              <TableHead className="text-right">Actions</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {customerDemands.map((demand) => (
                              <TableRow key={demand.id || `${demand.market_id}-${demand.product_id}`}>
                                <TableCell>
                                  {productMap.get(demand.product_id)?.name || 'Unknown'}
                                </TableCell>
                                <TableCell>
                                  <PatternSummary
                                    pattern={demand.demand_pattern || demand.pattern}
                                  />
                                </TableCell>
                                <TableCell className="text-right">
                                  <TooltipProvider>
                                    <Tooltip>
                                      <TooltipTrigger asChild>
                                        <Button
                                          variant="ghost"
                                          size="sm"
                                          onClick={() =>
                                            openDemandDialog(customer.id, {
                                              ...demand,
                                              demand_pattern:
                                                demand.demand_pattern || demand.pattern,
                                            })
                                          }
                                          disabled={loading}
                                        >
                                          <Pencil className="h-4 w-4" />
                                        </Button>
                                      </TooltipTrigger>
                                      <TooltipContent>Edit</TooltipContent>
                                    </Tooltip>
                                  </TooltipProvider>
                                  <TooltipProvider>
                                    <Tooltip>
                                      <TooltipTrigger asChild>
                                        <Button
                                          variant="ghost"
                                          size="sm"
                                          onClick={() => handleDeleteDemand(demand.id)}
                                          disabled={loading}
                                          className="text-destructive"
                                        >
                                          <Trash2 className="h-4 w-4" />
                                        </Button>
                                      </TooltipTrigger>
                                      <TooltipContent>Delete</TooltipContent>
                                    </Tooltip>
                                  </TooltipProvider>
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </CardContent>

      {/* Customer dialog */}
      <Modal
        isOpen={customerDialogOpen}
        onClose={closeCustomerDialog}
        title={editingCustomer ? 'Edit Customer' : 'Add Customer'}
        size="sm"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={closeCustomerDialog}>
              Cancel
            </Button>
            <Button onClick={handleSubmitCustomer} disabled={loading}>
              {editingCustomer ? 'Save Changes' : 'Add Customer'}
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <div>
            <Label htmlFor="customer-name">Customer Name</Label>
            <Input
              id="customer-name"
              value={customerForm.name}
              onChange={(e) =>
                setCustomerForm((prev) => ({ ...prev, name: e.target.value }))
              }
              className={customerErrors.name ? 'border-destructive' : ''}
              placeholder="e.g., Retail Chain A"
            />
            {customerErrors.name && (
              <p className="text-sm text-destructive mt-1">{customerErrors.name}</p>
            )}
          </div>
          <div>
            <Label htmlFor="customer-description">Description</Label>
            <Textarea
              id="customer-description"
              value={customerForm.description}
              onChange={(e) =>
                setCustomerForm((prev) => ({ ...prev, description: e.target.value }))
              }
              rows={2}
              placeholder="e.g., National grocery chain, weekly deliveries"
            />
          </div>
        </div>
      </Modal>

      {/* Demand pattern dialog */}
      <Modal
        isOpen={demandDialogOpen}
        onClose={closeDemandDialog}
        title={editingDemand ? 'Edit Demand Pattern' : 'Add Demand Pattern'}
        size="lg"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={closeDemandDialog}>
              Cancel
            </Button>
            <Button onClick={handleSubmitDemand} disabled={loading}>
              {editingDemand ? 'Save Changes' : 'Add Demand'}
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          {demandErrors.duplicate && (
            <Alert
              variant="warning"
              onClose={() => setDemandErrors((prev) => ({ ...prev, duplicate: undefined }))}
            >
              {demandErrors.duplicate}
            </Alert>
          )}

          <div>
            <Label htmlFor="demand-product">Product</Label>
            <Select
              value={demandForm.product_id}
              onValueChange={(value) =>
                setDemandForm((prev) => ({ ...prev, product_id: value }))
              }
            >
              <SelectTrigger
                id="demand-product"
                className={demandErrors.product_id ? 'border-destructive' : ''}
              >
                <SelectValue placeholder="Select product" />
              </SelectTrigger>
              <SelectContent>
                {products.map((product) => (
                  <SelectItem key={product.id} value={String(product.id)}>
                    {product.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {demandErrors.product_id && (
              <p className="text-sm text-destructive mt-1">{demandErrors.product_id}</p>
            )}
          </div>

          <DemandPatternInput
            value={demandForm.demand_pattern}
            onChange={(pattern) =>
              setDemandForm((prev) => ({ ...prev, demand_pattern: pattern }))
            }
          />
          {demandErrors.demand_pattern && (
            <p className="text-sm text-destructive">{demandErrors.demand_pattern}</p>
          )}
        </div>
      </Modal>
    </Card>
  );
};

export default CustomerManager;
