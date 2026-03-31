import React, { useState, useMemo, useCallback } from 'react';
import {
  Badge,
  Button,
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
import { Plus, Pencil, Trash2, Save, X } from 'lucide-react';

import {
  DEFAULT_SITE_TYPE_DEFINITIONS,
  sortSiteTypeDefinitions,
  buildSiteTypeLabelMap,
  canonicalizeSiteTypeKey,
} from '../../services/supplyChainConfigService';

const SITE_TYPE_VARIANTS = {
  // AWS SC DM types
  customer: 'success',
  distribution_center: 'info',
  warehouse: 'info',
  manufacturing_plant: 'warning',
  vendor: 'default',
  inventory: 'info',
  manufacturer: 'warning',
  market_supply: 'default',
  customer: 'secondary',
  // Legacy TBG types
  supplier: 'default',
  retailer: 'success',
  wholesaler: 'destructive',
  distributor: 'info',
};

const createAttributeState = (source = {}) => ({
  warehouse_capacity_volume: source?.warehouse_capacity_volume ?? '',
  inventory_target_value: source?.inventory_target_value ?? '',
  supply_capacity: source?.supply_capacity ?? '',
});

const SiteForm = ({
  sites = [],
  siteTypeDefinitions = DEFAULT_SITE_TYPE_DEFINITIONS,
  onAdd,
  onUpdate,
  onDelete,
  loading = false,
  navigationButtons = null,
}) => {
  const availableTypes = useMemo(
    () => sortSiteTypeDefinitions(siteTypeDefinitions),
    [siteTypeDefinitions]
  );
  const siteTypeLabelMap = useMemo(
    () => buildSiteTypeLabelMap(siteTypeDefinitions),
    [siteTypeDefinitions]
  );
  const defaultType = useMemo(() => {
    const preferred = availableTypes.find(
      (entry) =>
        !['vendor', 'customer'].includes(
          String(entry.type || '').toLowerCase()
        )
    );
    return preferred?.type || availableTypes[0]?.type || 'inventory';
  }, [availableTypes]);

  const [openDialog, setOpenDialog] = useState(false);
  const [editingSite, setEditingSite] = useState(null);
  const [formData, setFormData] = useState({
    name: '',
    type: defaultType,
    description: '',
    order_aging: 0,
    lost_sale_cost: '',
    attributes: createAttributeState(),
  });
  const [errors, setErrors] = useState({});

  const getDisplayDagType = useCallback(
    (site) =>
      site?.dag_type || site?.dagType || site?.type || site?.master_type || site?.masterType || '',
    []
  );

  const handleOpenDialog = (site = null) => {
    if (site) {
      setEditingSite(site);
      setFormData({
        name: site.name,
        type:
          availableTypes.find((entry) => entry.type === getDisplayDagType(site))?.type ||
          defaultType,
        description: site.description || '',
        order_aging: Number.isFinite(site.order_aging) ? site.order_aging : 0,
        lost_sale_cost: site.lost_sale_cost ?? '',
        attributes: createAttributeState(site.attributes || {}),
      });
    } else {
      setEditingSite(null);
      setFormData({
        name: '',
        type: defaultType,
        description: '',
        order_aging: 0,
        lost_sale_cost: '',
        attributes: createAttributeState(),
      });
    }
    setErrors({});
    setOpenDialog(true);
  };

  const handleCloseDialog = () => {
    setOpenDialog(false);
    setEditingSite(null);
    setFormData({
      name: '',
      type: defaultType,
      description: '',
      order_aging: 0,
      lost_sale_cost: '',
      attributes: createAttributeState(),
    });
    setErrors({});
  };

  const validateForm = () => {
    const newErrors = {};

    if (!formData.name.trim()) {
      newErrors.name = 'Name is required';
    }

    if (!formData.type || !availableTypes.some((entry) => entry.type === formData.type)) {
      newErrors.type = 'Type is required';
    }

    if (formData.order_aging < 0) {
      newErrors.order_aging = 'Order aging must be zero or greater';
    }

    if (formData.lost_sale_cost !== '' && Number(formData.lost_sale_cost) < 0) {
      newErrors.lost_sale_cost = 'Lost sale cost cannot be negative';
    }

    // Check for duplicate site names (case-insensitive)
    const isDuplicate = sites.some(
      (site) =>
        site.name.toLowerCase() === formData.name.trim().toLowerCase() &&
        (!editingSite || site.id !== editingSite.id)
    );

    if (isDuplicate) {
      newErrors.name = 'A site with this name already exists';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = (e) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    const agingValue = Number(formData.order_aging);
    const parsedLostSale = Number(formData.lost_sale_cost);
    const hasLostSaleCost =
      formData.lost_sale_cost !== '' &&
      formData.lost_sale_cost !== null &&
      Number.isFinite(parsedLostSale);

    const siteData = {
      name: formData.name.trim(),
      type: formData.type,
      description: formData.description.trim() || null,
      order_aging: Number.isFinite(agingValue) ? agingValue : 0,
      lost_sale_cost: hasLostSaleCost ? parsedLostSale : null,
    };

    const typeKey = formData.type?.toLowerCase?.() || '';
    const attributeKeyMap = {
      distributor: ['warehouse_capacity_volume', 'inventory_target_value'],
      supplier: ['supply_capacity'],
      market_supply: ['supply_capacity'],
    };
    const relevantAttributes = attributeKeyMap[typeKey] || [];
    const attributesPayload = {};

    relevantAttributes.forEach((field) => {
      const rawValue = formData.attributes?.[field];
      if (rawValue !== '' && rawValue !== null && rawValue !== undefined) {
        const numericValue = Number(rawValue);
        attributesPayload[field] = Number.isNaN(numericValue) ? rawValue : numericValue;
      }
    });

    const hadExistingAttributes = Boolean(
      editingSite?.attributes && Object.keys(editingSite.attributes).length > 0
    );

    if (relevantAttributes.length > 0) {
      siteData.attributes = attributesPayload;
    } else if (hadExistingAttributes) {
      siteData.attributes = {};
    }

    if (editingSite) {
      onUpdate(editingSite.id, siteData);
    } else {
      onAdd(siteData);
    }

    handleCloseDialog();
  };

  const handleDelete = (siteId) => {
    if (
      window.confirm(
        'Are you sure you want to delete this site? This will also remove any associated lanes and configurations.'
      )
    ) {
      onDelete(siteId);
    }
  };

  const handleChange = (name, value) => {
    if (name === 'type') {
      setFormData((prev) => ({
        ...prev,
        type: value,
        attributes: createAttributeState(),
      }));
      return;
    }
    if (name === 'order_aging') {
      const nextValue = value === '' ? '' : Math.max(0, Number(value));
      setFormData((prev) => ({
        ...prev,
        order_aging: nextValue,
      }));
      return;
    }
    if (name === 'lost_sale_cost') {
      setFormData((prev) => ({
        ...prev,
        lost_sale_cost: value,
      }));
      return;
    }
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleAttributeChange = (field, value) => {
    setFormData((prev) => ({
      ...prev,
      attributes: {
        ...prev.attributes,
        [field]: value,
      },
    }));
  };

  const getSiteTypeLabel = (type) => {
    if (!type) return 'Unknown';
    const canonicalKey = canonicalizeSiteTypeKey(type);
    if (canonicalKey && siteTypeLabelMap[canonicalKey]) {
      return siteTypeLabelMap[canonicalKey];
    }
    return canonicalKey
      ? canonicalKey.replace(/_/g, ' ').replace(/\b\w/g, (match) => match.toUpperCase())
      : String(type);
  };

  const formatAttributes = (site) => {
    if (!site || !site.attributes) {
      return null;
    }
    const parts = [];
    const { attributes } = site;
    if (
      attributes?.warehouse_capacity_volume !== undefined &&
      attributes?.warehouse_capacity_volume !== null &&
      attributes?.warehouse_capacity_volume !== ''
    ) {
      parts.push(`Warehouse capacity: ${attributes.warehouse_capacity_volume}`);
    }
    if (
      attributes?.inventory_target_value !== undefined &&
      attributes?.inventory_target_value !== null &&
      attributes?.inventory_target_value !== ''
    ) {
      parts.push(`Inventory target: ${attributes.inventory_target_value}`);
    }
    if (
      attributes?.supply_capacity !== undefined &&
      attributes?.supply_capacity !== null &&
      attributes?.supply_capacity !== ''
    ) {
      parts.push(`Supply capacity: ${attributes.supply_capacity}`);
    }
    return parts.length > 0 ? parts.join(' • ') : null;
  };

  const dagOrderMap = useMemo(() => {
    const map = new Map();
    availableTypes.forEach((definition, index) => {
      const orderValue = Number.isFinite(definition?.order) ? definition.order : index;
      const candidateKeys = new Set([
        canonicalizeSiteTypeKey(definition?.type || ''),
        canonicalizeSiteTypeKey(definition?.label || ''),
        canonicalizeSiteTypeKey(definition?.group_type || definition?.groupType || ''),
      ]);
      candidateKeys.forEach((key) => {
        if (!key || map.has(key)) return;
        map.set(key, orderValue);
      });
    });
    return map;
  }, [availableTypes]);

  const resolveDagOrder = useCallback(
    (site) => {
      const dagKey = canonicalizeSiteTypeKey(getDisplayDagType(site));
      const orderValue = dagOrderMap.get(dagKey);
      if (Number.isFinite(orderValue)) {
        return orderValue;
      }
      if (Number.isFinite(site?.order)) {
        return site.order;
      }
      return Number.MAX_SAFE_INTEGER;
    },
    [dagOrderMap, getDisplayDagType]
  );

  const sortedSites = useMemo(() => {
    if (!Array.isArray(sites)) return [];

    return [...sites].sort((a, b) => {
      const orderA = resolveDagOrder(a);
      const orderB = resolveDagOrder(b);

      if (orderA !== orderB) {
        return orderA - orderB;
      }

      return String(a?.name || '').localeCompare(String(b?.name || ''));
    });
  }, [sites, resolveDagOrder]);

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-semibold">Sites</h3>
        <div className="flex gap-2">
          <Button
            onClick={() => handleOpenDialog()}
            disabled={loading}
            leftIcon={<Plus className="h-4 w-4" />}
          >
            Add Site
          </Button>
          {navigationButtons}
        </div>
      </div>

      <div className="border rounded-md">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead className="text-right">DAG Order</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Description</TableHead>
              <TableHead>Key Attributes</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sites.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center">
                  No sites added yet. Click "Add Site" to get started.
                </TableCell>
              </TableRow>
            ) : (
              sortedSites.map((site) => {
                const dagOrder = resolveDagOrder(site);
                const hasDagOrder = dagOrder !== Number.MAX_SAFE_INTEGER;

                return (
                  <TableRow key={site.id}>
                    <TableCell>{site.name}</TableCell>
                    <TableCell className="text-right">{hasDagOrder ? dagOrder : '—'}</TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          SITE_TYPE_VARIANTS[getDisplayDagType(site)?.toLowerCase?.()] || 'secondary'
                        }
                      >
                        {getSiteTypeLabel(getDisplayDagType(site))}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {site.description || (
                        <span className="text-muted-foreground">No description</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {formatAttributes(site) || (
                        <span className="text-muted-foreground">No attributes</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleOpenDialog(site)}
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
                              onClick={() => handleDelete(site.id)}
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
                );
              })
            )}
          </TableBody>
        </Table>
      </div>

      <Modal
        isOpen={openDialog}
        onClose={handleCloseDialog}
        title={editingSite ? 'Edit Site' : 'Add New Site'}
        size="md"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={handleCloseDialog} disabled={loading} leftIcon={<X className="h-4 w-4" />}>
              Cancel
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={loading}
              leftIcon={editingSite ? <Save className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
            >
              {editingSite ? 'Update' : 'Add'} Site
            </Button>
          </div>
        }
      >
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-12 gap-4">
            <div className="col-span-8">
              <Label htmlFor="site-name">Site Name</Label>
              <Input
                id="site-name"
                value={formData.name}
                onChange={(e) => handleChange('name', e.target.value)}
                disabled={loading}
                className={errors.name ? 'border-destructive' : ''}
              />
              {errors.name && <p className="text-sm text-destructive mt-1">{errors.name}</p>}
            </div>
            <div className="col-span-4">
              <Label htmlFor="site-type">Site Type</Label>
              <Select
                value={formData.type}
                onValueChange={(value) => handleChange('type', value)}
                disabled={loading}
              >
                <SelectTrigger className={errors.type ? 'border-destructive' : ''}>
                  <SelectValue placeholder="Select type" />
                </SelectTrigger>
                <SelectContent>
                  {availableTypes.map((type) => (
                    <SelectItem key={type.type} value={type.type}>
                      {getSiteTypeLabel(type.type)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {errors.type && <p className="text-sm text-destructive mt-1">{errors.type}</p>}
            </div>
          </div>

          <div>
            <Label htmlFor="site-description">Description (Optional)</Label>
            <Textarea
              id="site-description"
              value={formData.description}
              onChange={(e) => handleChange('description', e.target.value)}
              disabled={loading}
              rows={2}
            />
          </div>

          {formData.type?.toLowerCase() === 'customer' && (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="order-aging">Order Aging (periods)</Label>
                <Input
                  id="order-aging"
                  type="number"
                  value={formData.order_aging}
                  onChange={(e) => handleChange('order_aging', e.target.value)}
                  disabled={loading}
                  min={0}
                  className={errors.order_aging ? 'border-destructive' : ''}
                />
                <p className="text-xs text-muted-foreground mt-1">
                  Periods before unmet demand becomes lost sales
                </p>
                {errors.order_aging && (
                  <p className="text-sm text-destructive mt-1">{errors.order_aging}</p>
                )}
              </div>
              <div>
                <Label htmlFor="lost-sale-cost">Lost Sale Cost</Label>
                <Input
                  id="lost-sale-cost"
                  type="number"
                  value={formData.lost_sale_cost}
                  onChange={(e) => handleChange('lost_sale_cost', e.target.value)}
                  disabled={loading}
                  min={0}
                  step="any"
                  className={errors.lost_sale_cost ? 'border-destructive' : ''}
                />
                <p className="text-xs text-muted-foreground mt-1">
                  Cost applied when aging threshold is exceeded
                </p>
                {errors.lost_sale_cost && (
                  <p className="text-sm text-destructive mt-1">{errors.lost_sale_cost}</p>
                )}
              </div>
            </div>
          )}

          {formData.type?.toLowerCase() === 'distributor' && (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="warehouse-capacity">Warehouse Capacity (volume)</Label>
                <Input
                  id="warehouse-capacity"
                  type="number"
                  value={formData.attributes?.warehouse_capacity_volume}
                  onChange={(e) => handleAttributeChange('warehouse_capacity_volume', e.target.value)}
                  disabled={loading}
                  min={0}
                  step="any"
                />
              </div>
              <div>
                <Label htmlFor="inventory-target">Inventory Target (value)</Label>
                <Input
                  id="inventory-target"
                  type="number"
                  value={formData.attributes?.inventory_target_value}
                  onChange={(e) => handleAttributeChange('inventory_target_value', e.target.value)}
                  disabled={loading}
                  min={0}
                  step="any"
                />
              </div>
            </div>
          )}

          {formData.type?.toLowerCase() === 'vendor' && (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="supply-capacity">Supply Capacity</Label>
                <Input
                  id="supply-capacity"
                  type="number"
                  value={formData.attributes?.supply_capacity}
                  onChange={(e) => handleAttributeChange('supply_capacity', e.target.value)}
                  disabled={loading}
                  min={0}
                  step="any"
                />
                <p className="text-xs text-muted-foreground mt-1">
                  0 means unlimited supply per period
                </p>
              </div>
            </div>
          )}
        </form>
      </Modal>
    </div>
  );
};

export default SiteForm;
