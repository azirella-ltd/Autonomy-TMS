import { useState, useEffect } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
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
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../common';
import { Plus, Pencil, Trash2, Save, X, ChevronLeft, ChevronRight } from 'lucide-react';

const SITE_TYPE_LABELS = {
  retailer: 'Retailer',
  wholesaler: 'Wholesaler',
  distributor: 'Distributor',
  manufacturer: 'Manufacturer',
  factory: 'Factory',
  market_supply: 'Market Supply',
  market_demand: 'Market Demand',
};

const SITE_TYPE_VARIANTS = {
  retailer: 'success',
  wholesaler: 'destructive',
  distributor: 'info',
  manufacturer: 'warning',
  factory: 'warning',
  market_supply: 'default',
  market_demand: 'secondary',
};

const ProductSiteConfigForm = ({
  configs = [],
  products = [],
  sites = [],
  onAdd,
  onUpdate,
  onDelete,
  loading = false,
  navigationButtons = null,
  // Backward compatibility alias (deprecated)
  items = null,
}) => {
  // Use products if provided, fall back to items for backward compat
  const productList = products.length > 0 ? products : (items || []);
  const [openDialog, setOpenDialog] = useState(false);
  const [editingConfig, setEditingConfig] = useState(null);
  const [formData, setFormData] = useState({
    product_id: '',
    site_id: '',
    initial_inventory: 0,
    holding_cost: 0.1,
    backorder_cost: 1.0,
    service_level: 0.95,
  });
  const [errors, setErrors] = useState({});
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);
  const [filteredSites, setFilteredSites] = useState([]);

  useEffect(() => {
    if (openDialog) {
      if (editingConfig) {
        setFormData({
          product_id: editingConfig.product_id,
          site_id: editingConfig.site_id,
          initial_inventory:
            editingConfig.initial_inventory_min !== undefined
              ? editingConfig.initial_inventory_min
              : editingConfig.initial_inventory || 0,
          holding_cost:
            editingConfig.holding_cost_min !== undefined
              ? editingConfig.holding_cost_min
              : editingConfig.holding_cost || 0.1,
          backorder_cost:
            editingConfig.backlog_cost_min !== undefined
              ? editingConfig.backlog_cost_min
              : editingConfig.backorder_cost || 1.0,
          service_level: editingConfig.service_level || 0.95,
        });
      } else {
        setFormData({
          product_id: '',
          site_id: '',
          initial_inventory: 0,
          holding_cost: 0.1,
          backorder_cost: 1.0,
          service_level: 0.95,
        });
      }
      setErrors({});
    }
  }, [openDialog, editingConfig]);

  useEffect(() => {
    if (formData.product_id) {
      const configuredSiteIds = configs
        .filter((c) => c.product_id === formData.product_id)
        .map((c) => c.site_id);

      const availableSites = sites.filter(
        (site) =>
          !configuredSiteIds.includes(site.id) ||
          (editingConfig && site.id === editingConfig.site_id)
      );

      setFilteredSites(availableSites);

      if (formData.site_id && !availableSites.some((s) => s.id === formData.site_id)) {
        setFormData((prev) => ({ ...prev, site_id: '' }));
      }
    } else {
      setFilteredSites([]);
    }
  }, [formData.product_id, formData.site_id, sites, configs, editingConfig]);

  const handleOpenDialog = (config = null) => {
    setEditingConfig(config);
    setOpenDialog(true);
  };

  const handleCloseDialog = () => {
    setOpenDialog(false);
    setEditingConfig(null);
  };

  const validateForm = () => {
    const newErrors = {};

    if (!formData.product_id) {
      newErrors.product_id = 'Product is required';
    }

    if (!formData.site_id) {
      newErrors.site_id = 'Site is required';
    }

    if (formData.initial_inventory < 0) {
      newErrors.initial_inventory = 'Cannot be negative';
    }

    if (formData.holding_cost < 0) {
      newErrors.holding_cost = 'Cannot be negative';
    }

    if (formData.backorder_cost < 0) {
      newErrors.backorder_cost = 'Cannot be negative';
    }

    if (formData.service_level < 0 || formData.service_level > 1) {
      newErrors.service_level = 'Must be between 0 and 1';
    }

    const isDuplicate = configs.some(
      (config) =>
        config.product_id === formData.product_id &&
        config.site_id === formData.site_id &&
        (!editingConfig || config.id !== editingConfig.id)
    );

    if (isDuplicate) {
      newErrors.duplicate = 'A configuration for this product and site already exists';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = (e) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    const configData = {
      product_id: formData.product_id,
      site_id: formData.site_id,
      initial_inventory: parseInt(formData.initial_inventory, 10) || 0,
      holding_cost: parseFloat(formData.holding_cost) || 0.1,
      backorder_cost: parseFloat(formData.backorder_cost) || 1.0,
      service_level: parseFloat(formData.service_level) || 0.95,
    };

    if (editingConfig) {
      onUpdate(editingConfig.id, configData);
    } else {
      onAdd(configData);
    }

    handleCloseDialog();
  };

  const handleDelete = (configId) => {
    if (
      window.confirm(
        'Are you sure you want to delete this configuration? This action cannot be undone.'
      )
    ) {
      onDelete(configId);
    }
  };

  const handleChange = (name, value) => {
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const getProductName = (productId) => {
    const product = productList.find((p) => p.id === productId);
    return product ? product.name : 'Unknown';
  };

  const getSiteInfo = (siteId) => {
    const site = sites.find((s) => s.id === siteId);
    if (!site) return { name: 'Unknown', type: 'unknown', master_type: '', display: 'Unknown' };

    const name = site.name || 'Unknown';
    const dagType = site.type || 'unknown';
    const masterType = site.master_type || '';

    const display = masterType ? `${name} / ${dagType} / ${masterType}` : `${name} / ${dagType}`;

    return { name, type: dagType, master_type: masterType, display };
  };

  const startIndex = page * rowsPerPage;
  const endIndex = startIndex + rowsPerPage;
  const paginatedConfigs = configs.slice(startIndex, endIndex);
  const totalPages = Math.ceil(configs.length / rowsPerPage);

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-lg font-semibold">Product by Site</h2>
        <div className="flex gap-2">
          <Button
            onClick={() => handleOpenDialog()}
            disabled={loading || productList.length === 0 || sites.length === 0}
            leftIcon={<Plus className="h-4 w-4" />}
          >
            Add Configuration
          </Button>
          {navigationButtons}
        </div>
      </div>

      {productList.length === 0 || sites.length === 0 ? (
        <Card variant="outline" className="p-6 text-center">
          <p className="text-muted-foreground">
            {productList.length === 0 && sites.length === 0
              ? 'Add products and sites first to create configurations.'
              : productList.length === 0
              ? 'Add products first to create configurations.'
              : 'Add sites first to create configurations.'}
          </p>
        </Card>
      ) : (
        <Card variant="outline">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Product</TableHead>
                <TableHead>Site</TableHead>
                <TableHead className="text-right">Initial Inventory</TableHead>
                <TableHead className="text-right">Holding Cost</TableHead>
                <TableHead className="text-right">Backorder Cost</TableHead>
                <TableHead className="text-right">Service Level</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {paginatedConfigs.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center">
                    No configurations added yet. Click "Add Configuration" to get started.
                  </TableCell>
                </TableRow>
              ) : (
                paginatedConfigs.map((config) => (
                  <TableRow key={`${config.product_id}-${config.site_id}`}>
                    <TableCell>{getProductName(config.product_id)}</TableCell>
                    <TableCell>{getSiteInfo(config.site_id).display}</TableCell>
                    <TableCell className="text-right">
                      {config.initial_inventory_min !== undefined &&
                      config.initial_inventory_max !== undefined
                        ? `${config.initial_inventory_min} - ${config.initial_inventory_max}`
                        : config.initial_inventory || 0}
                    </TableCell>
                    <TableCell className="text-right">
                      {config.holding_cost_min !== undefined && config.holding_cost_max !== undefined
                        ? `$${config.holding_cost_min.toFixed(2)} - $${config.holding_cost_max.toFixed(2)}`
                        : config.holding_cost
                        ? `$${config.holding_cost.toFixed(2)}`
                        : '$0.00'}
                    </TableCell>
                    <TableCell className="text-right">
                      {config.backlog_cost_min !== undefined && config.backlog_cost_max !== undefined
                        ? `$${config.backlog_cost_min.toFixed(2)} - $${config.backlog_cost_max.toFixed(2)}`
                        : config.backorder_cost
                        ? `$${config.backorder_cost.toFixed(2)}`
                        : '$0.00'}
                    </TableCell>
                    <TableCell className="text-right">
                      {config.service_level !== undefined
                        ? `${(config.service_level * 100).toFixed(1)}%`
                        : 'N/A'}
                    </TableCell>
                    <TableCell className="text-right">
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleOpenDialog(config)}
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
                              className="text-destructive"
                              onClick={() => handleDelete(config.id)}
                              disabled={loading}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Delete</TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>

          {configs.length > rowsPerPage && (
            <div className="flex items-center justify-between px-4 py-3 border-t">
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">Rows per page:</span>
                <Select
                  value={String(rowsPerPage)}
                  onValueChange={(value) => {
                    setRowsPerPage(parseInt(value, 10));
                    setPage(0);
                  }}
                >
                  <SelectTrigger className="w-[70px] h-8">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="5">5</SelectItem>
                    <SelectItem value="10">10</SelectItem>
                    <SelectItem value="25">25</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-center gap-4">
                <span className="text-sm text-muted-foreground">
                  {startIndex + 1}-{Math.min(endIndex, configs.length)} of {configs.length}
                </span>
                <div className="flex gap-1">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    disabled={page === 0}
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                    disabled={page >= totalPages - 1}
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </div>
          )}
        </Card>
      )}

      <Modal
        isOpen={openDialog}
        onClose={handleCloseDialog}
        title={editingConfig ? 'Edit Configuration' : 'Add New Configuration'}
        size="md"
        footer={
          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              onClick={handleCloseDialog}
              disabled={loading}
              leftIcon={<X className="h-4 w-4" />}
            >
              Cancel
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={loading || !formData.product_id || !formData.site_id}
              leftIcon={editingConfig ? <Save className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
            >
              {editingConfig ? 'Update' : 'Add'} Configuration
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <div>
            <Label htmlFor="product">Product</Label>
            <Select
              value={formData.product_id ? String(formData.product_id) : ''}
              onValueChange={(value) => handleChange('product_id', Number(value))}
              disabled={loading || !!editingConfig}
            >
              <SelectTrigger
                id="product"
                className={errors.product_id ? 'border-destructive' : ''}
              >
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
            {errors.product_id && (
              <p className="text-xs text-destructive mt-1">{errors.product_id}</p>
            )}
          </div>

          <div>
            <Label htmlFor="site">Site</Label>
            <Select
              value={formData.site_id ? String(formData.site_id) : ''}
              onValueChange={(value) => handleChange('site_id', Number(value))}
              disabled={loading || !formData.product_id || !!editingConfig}
            >
              <SelectTrigger id="site" className={errors.site_id ? 'border-destructive' : ''}>
                <SelectValue placeholder="Select site" />
              </SelectTrigger>
              <SelectContent>
                {filteredSites.map((site) => (
                  <SelectItem key={site.id} value={String(site.id)}>
                    <div className="flex items-center gap-2">
                      <Badge variant={SITE_TYPE_VARIANTS[site.type]} className="text-xs">
                        {SITE_TYPE_LABELS[site.type] || site.type}
                      </Badge>
                      {site.name}
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {errors.site_id ? (
              <p className="text-xs text-destructive mt-1">{errors.site_id}</p>
            ) : !formData.product_id ? (
              <p className="text-xs text-muted-foreground mt-1">Select a product first</p>
            ) : filteredSites.length === 0 ? (
              <p className="text-xs text-muted-foreground mt-1">
                No available sites for the selected product
              </p>
            ) : null}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label htmlFor="initial-inventory">Initial Inventory</Label>
              <Input
                id="initial-inventory"
                type="number"
                value={formData.initial_inventory}
                onChange={(e) => handleChange('initial_inventory', e.target.value)}
                disabled={loading}
                min={0}
                step={1}
                className={errors.initial_inventory ? 'border-destructive' : ''}
              />
              {errors.initial_inventory && (
                <p className="text-xs text-destructive mt-1">{errors.initial_inventory}</p>
              )}
            </div>

            <div>
              <Label htmlFor="holding-cost">Holding Cost ($/unit/period)</Label>
              <Input
                id="holding-cost"
                type="number"
                value={formData.holding_cost}
                onChange={(e) => handleChange('holding_cost', e.target.value)}
                disabled={loading}
                min={0}
                step={0.01}
                className={errors.holding_cost ? 'border-destructive' : ''}
              />
              {errors.holding_cost && (
                <p className="text-xs text-destructive mt-1">{errors.holding_cost}</p>
              )}
            </div>

            <div>
              <Label htmlFor="backorder-cost">Backorder Cost ($/unit/period)</Label>
              <Input
                id="backorder-cost"
                type="number"
                value={formData.backorder_cost}
                onChange={(e) => handleChange('backorder_cost', e.target.value)}
                disabled={loading}
                min={0}
                step={0.01}
                className={errors.backorder_cost ? 'border-destructive' : ''}
              />
              {errors.backorder_cost && (
                <p className="text-xs text-destructive mt-1">{errors.backorder_cost}</p>
              )}
            </div>

            <div>
              <Label htmlFor="service-level">Service Level (0-1)</Label>
              <Input
                id="service-level"
                type="number"
                value={formData.service_level}
                onChange={(e) => handleChange('service_level', e.target.value)}
                disabled={loading}
                min={0}
                max={1}
                step={0.01}
                className={errors.service_level ? 'border-destructive' : ''}
              />
              {errors.service_level ? (
                <p className="text-xs text-destructive mt-1">{errors.service_level}</p>
              ) : (
                <p className="text-xs text-muted-foreground mt-1">Probability of meeting demand</p>
              )}
            </div>
          </div>

          {errors.duplicate && <Alert variant="destructive">{errors.duplicate}</Alert>}
        </div>
      </Modal>
    </div>
  );
};

export default ProductSiteConfigForm;
