import { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
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
import { Plus, Pencil, Trash2, Save, X, ArrowRight } from 'lucide-react';
import {
  DEFAULT_SITE_TYPE_DEFINITIONS,
  canonicalizeSiteTypeKey,
  sortSiteTypeDefinitions,
} from '../../services/supplyChainConfigService';

const getDeterministicValue = (distribution, fallback) => {
  if (distribution === null || distribution === undefined) {
    return fallback;
  }
  if (typeof distribution === 'number') {
    return Number.isFinite(distribution) ? distribution : fallback;
  }
  const value = distribution?.value ?? distribution?.mean ?? distribution?.minimum;
  if (value !== undefined && value !== null) {
    const numeric = Number(value);
    return Number.isNaN(numeric) ? fallback : numeric;
  }
  if (
    distribution?.minimum !== undefined &&
    distribution?.maximum !== undefined &&
    distribution.minimum !== null &&
    distribution.maximum !== null
  ) {
    const min = Number(distribution.minimum);
    const max = Number(distribution.maximum);
    if (!Number.isNaN(min) && !Number.isNaN(max)) {
      return (min + max) / 2;
    }
  }
  return fallback;
};

const SITE_TYPE_LABELS = {
  // AWS SC DM types
  customer: 'Customer',
  distribution_center: 'Distribution Center',
  warehouse: 'Warehouse',
  manufacturing_plant: 'Manufacturing Plant',
  vendor: 'Vendor',
  market_supply: 'Market Supply',
  market_demand: 'Market Demand',
  // Legacy TBG types
  retailer: 'Retailer',
  wholesaler: 'Wholesaler',
  distributor: 'Distributor',
  manufacturer: 'Manufacturer',
};

const SITE_TYPE_VARIANTS = {
  // AWS SC DM types
  customer: 'success',
  distribution_center: 'info',
  warehouse: 'info',
  manufacturing_plant: 'warning',
  vendor: 'default',
  market_supply: 'default',
  market_demand: 'secondary',
  // Legacy TBG types
  retailer: 'success',
  wholesaler: 'destructive',
  distributor: 'info',
  manufacturer: 'warning',
};

/**
 * TransportationLaneForm - AWS SC DM compliant component for managing transportation lanes
 * Props:
 *   - lanes: Array of transportation lane objects (AWS SC DM: transportation_lane)
 *   - sites: Array of site objects (AWS SC DM: site)
 *   - onAdd, onUpdate, onDelete: CRUD callbacks
 */
const TransportationLaneForm = ({
  lanes = [],
  sites = [],
  siteTypeDefinitions = DEFAULT_SITE_TYPE_DEFINITIONS,
  onAdd,
  onUpdate,
  onDelete,
  loading = false,
  navigationButtons = null,
}) => {
  const normalizeTypeToken = (value) => (value ? value.toString().trim().toLowerCase() : '');

  const normalisedSites = useMemo(
    () =>
      sites.map((s) => {
        const dagType = normalizeTypeToken(s?.dag_type || s?.dagType || s?.type || s?.site_type || s?.node_type);
        const masterType = normalizeTypeToken(s?.master_type || s?.masterType);
        const fallbackType = normalizeTypeToken(s?.type || s?.site_type || s?.node_type);
        const resolvedType = dagType || fallbackType || masterType;

        return {
          ...s,
          id: Number(s.id),
          dag_type: dagType,
          master_type: masterType,
          type: resolvedType,
        };
      }),
    [sites]
  );

  const normalisedLanes = useMemo(
    () =>
      lanes.map((lane) => ({
        ...lane,
        // Normalize to from_site_id/to_site_id (AWS SC DM standard)
        from_site_id: Number(lane.from_site_id),
        to_site_id: Number(lane.to_site_id),
      })),
    [lanes]
  );

  const [openDialog, setOpenDialog] = useState(false);
  const [editingLane, setEditingLane] = useState(null);
  const [formData, setFormData] = useState({
    from_site_id: '',
    to_site_id: '',
    supply_lead_time: 1,
    demand_lead_time: 0,
    capacity: 100,
    cost_per_unit: 1.0,
  });
  const [errors, setErrors] = useState({});
  const [filteredToSites, setFilteredToSites] = useState([]);

  const dagOrderMap = useMemo(() => {
    const map = new Map();
    sortSiteTypeDefinitions(siteTypeDefinitions).forEach((definition, index) => {
      const orderValue = Number.isFinite(definition?.order) ? definition.order : index;
      const typeKey = canonicalizeSiteTypeKey(definition?.type);
      const masterKey = canonicalizeSiteTypeKey(definition?.master_type);

      if (typeKey && !map.has(typeKey)) {
        map.set(typeKey, orderValue);
      }
      if (masterKey && !map.has(masterKey)) {
        map.set(masterKey, orderValue);
      }
    });
    return map;
  }, [siteTypeDefinitions]);

  const getDagIndex = useCallback(
    (site) => {
      if (!site) return Number.MAX_SAFE_INTEGER;

      const candidates = [
        site?.dag_type,
        site?.dagType,
        site?.type,
        site?.site_type,
        site?.master_type,
        site?.masterType,
      ]
        .map((entry) => canonicalizeSiteTypeKey(entry))
        .filter(Boolean);

      for (const key of candidates) {
        if (dagOrderMap.has(key)) {
          return dagOrderMap.get(key);
        }
      }

      if (Number.isFinite(site?.order)) {
        return site.order;
      }

      return Number.MAX_SAFE_INTEGER;
    },
    [dagOrderMap]
  );

  useEffect(() => {
    if (formData.from_site_id) {
      const fromSite = normalisedSites.find((n) => n.id === formData.from_site_id);
      const fromIndex = getDagIndex(fromSite);

      const availableSites = normalisedSites.filter((site) => {
        if (site.id === formData.from_site_id) return false;
        const toIndex = getDagIndex(site);
        return toIndex > fromIndex;
      });

      setFilteredToSites(availableSites);

      if (!editingLane && fromSite?.type === 'market_supply' && formData.demand_lead_time !== 0) {
        setFormData((prev) => ({ ...prev, demand_lead_time: 0 }));
      }

      if (formData.to_site_id && !availableSites.some((n) => n.id === formData.to_site_id)) {
        setFormData((prev) => ({ ...prev, to_site_id: '' }));
      }
    } else {
      setFilteredToSites([]);
    }
  }, [
    formData.from_site_id,
    formData.to_site_id,
    sites,
    editingLane,
    formData.demand_lead_time,
    normalisedSites,
    getDagIndex,
  ]);

  const handleOpenDialog = (lane = null) => {
    if (lane) {
      setEditingLane(lane);
      const legacyLead =
        lane.lead_time_days && typeof lane.lead_time_days === 'object'
          ? lane.lead_time_days.min ?? lane.lead_time_days.max ?? 1
          : lane.lead_time ?? 1;
      const supplyValue = getDeterministicValue(lane.supply_lead_time, legacyLead ?? 1);
      const orderValue = getDeterministicValue(lane.demand_lead_time, 0);
      setFormData({
        from_site_id: lane.from_site_id,
        to_site_id: lane.to_site_id,
        supply_lead_time: supplyValue,
        demand_lead_time: orderValue,
        capacity: lane.capacity ?? 100,
        cost_per_unit: lane.cost_per_unit ?? 1.0,
      });
    } else {
      setEditingLane(null);
      setFormData({
        from_site_id: '',
        to_site_id: '',
        supply_lead_time: 1,
        demand_lead_time: 0,
        capacity: 100,
        cost_per_unit: 1.0,
      });
    }
    setErrors({});
    setOpenDialog(true);
  };

  const handleCloseDialog = () => {
    setOpenDialog(false);
    setEditingLane(null);
    setFormData({
      from_site_id: '',
      to_site_id: '',
      supply_lead_time: 1,
      demand_lead_time: 0,
      capacity: 100,
      cost_per_unit: 1.0,
    });
    setErrors({});
  };

  const validateForm = () => {
    const newErrors = {};

    if (!formData.from_site_id) {
      newErrors.from_site_id = 'Source site is required';
    }

    if (!formData.to_site_id) {
      newErrors.to_site_id = 'Destination site is required';
    } else if (formData.from_site_id === formData.to_site_id) {
      newErrors.to_site_id = 'Source and destination cannot be the same';
    }

    if (Number(formData.supply_lead_time) < 0) {
      newErrors.supply_lead_time = 'Supply lead time cannot be negative';
    }

    if (Number(formData.demand_lead_time) < 0) {
      newErrors.demand_lead_time = 'Demand lead time cannot be negative';
    }

    if (formData.capacity <= 0) {
      newErrors.capacity = 'Capacity must be greater than 0';
    }

    if (formData.cost_per_unit < 0) {
      newErrors.cost_per_unit = 'Cost cannot be negative';
    }

    const isDuplicate = normalisedLanes.some(
      (lane) =>
        lane.from_site_id === formData.from_site_id &&
        lane.to_site_id === formData.to_site_id &&
        (!editingLane || lane.id !== editingLane.id)
    );

    if (isDuplicate) {
      newErrors.duplicate = 'A lane between these sites already exists';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = (e) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    const supplyLead = Number(formData.supply_lead_time);
    const demandLead = Number(formData.demand_lead_time);

    // API payload uses AWS SC DM from_site_id/to_site_id
    const laneData = {
      from_site_id: formData.from_site_id,
      to_site_id: formData.to_site_id,
      capacity: parseInt(formData.capacity, 10),
      lead_time_days: {
        min: supplyLead,
        max: supplyLead,
      },
      demand_lead_time: {
        type: 'deterministic',
        value: Number.isNaN(demandLead) ? 0 : demandLead,
      },
      supply_lead_time: {
        type: 'deterministic',
        value: Number.isNaN(supplyLead) ? 1 : supplyLead,
      },
      cost_per_unit: parseFloat(formData.cost_per_unit),
    };

    if (editingLane) {
      onUpdate(editingLane.id, laneData);
    } else {
      onAdd(laneData);
    }

    handleCloseDialog();
  };

  const handleDelete = (laneId) => {
    if (window.confirm('Are you sure you want to delete this lane? This action cannot be undone.')) {
      onDelete(laneId);
    }
  };

  const handleChange = (name, value) => {
    const numericValue = typeof value === 'string' && value !== '' && name !== 'cost_per_unit' ? Number(value) : value;
    setFormData((prev) => {
      const next = {
        ...prev,
        [name]: numericValue,
      };

      if (name === 'from_site_id') {
        const fromSite = normalisedSites.find((n) => n.id === numericValue);
        if (fromSite?.type === 'market_supply') {
          next.demand_lead_time = 0;
        }
      }

      if (name === 'to_site_id') {
        const toSite = normalisedSites.find((n) => n.id === numericValue);
        if (toSite?.type === 'market_demand') {
          next.supply_lead_time = 0;
        }
      }

      return next;
    });
  };

  const getSiteName = (siteId) => {
    const site = normalisedSites.find((n) => n.id === siteId);
    return site ? site.name : 'Unknown';
  };

  const getSiteType = (siteId) => {
    const site = normalisedSites.find((n) => n.id === siteId);
    if (!site) return 'unknown';
    return site.dag_type || site.type || site.site_type || site.master_type || 'unknown';
  };

  const toTitle = (value) =>
    value
      ? value
          .split('_')
          .join(' ')
          .replace(/\b\w/g, (char) => char.toUpperCase())
      : 'Unknown';

  const getSiteTypeLabel = (type) => SITE_TYPE_LABELS[type] || toTitle(type);
  const getSiteTypeVariant = (type) => SITE_TYPE_VARIANTS[type] || 'secondary';

  const getDagOrderForSite = (siteId) => {
    const site = normalisedSites.find((n) => n.id === siteId);
    return getDagIndex(site);
  };

  const getDagOrderDisplay = (siteId) => {
    const order = getDagOrderForSite(siteId);
    if (!Number.isFinite(order) || order === Number.MAX_SAFE_INTEGER) {
      return '—';
    }
    return order;
  };

  const getDemandLead = (lane) => {
    const legacyLead =
      lane.lead_time_days && typeof lane.lead_time_days === 'object'
        ? lane.lead_time_days.min ?? lane.lead_time_days.max ?? 0
        : lane.lead_time ?? 0;
    return getDeterministicValue(lane.demand_lead_time, legacyLead ?? 0);
  };

  const getSupplyLead = (lane) => {
    const legacyLead =
      lane.lead_time_days && typeof lane.lead_time_days === 'object'
        ? lane.lead_time_days.min ?? lane.lead_time_days.max ?? 0
        : lane.lead_time ?? 0;
    return getDeterministicValue(lane.supply_lead_time, legacyLead);
  };

  const getCapacityDisplay = (lane) => {
    const value = lane.capacity;
    if (value === undefined || value === null) return '—';
    return Number(value).toLocaleString();
  };

  const getCostDisplay = (lane) => {
    if (lane.cost_per_unit === undefined || lane.cost_per_unit === null) {
      return '—';
    }
    const numeric = Number(lane.cost_per_unit);
    return `$${numeric.toFixed(2)}`;
  };

  const sourceSites = normalisedSites.filter((site) => site.type !== 'market_supply');

  const sortedLanes = useMemo(() => {
    return [...normalisedLanes]
      .map((lane) => {
        // Use normalised from_site_id/to_site_id
        return {
          ...lane,
          display_from_id: lane.from_site_id,
          display_to_id: lane.to_site_id,
        };
      })
      .sort((a, b) => {
        const aDag = getDagOrderForSite(a.display_from_id);
        const bDag = getDagOrderForSite(b.display_from_id);
        if (aDag !== bDag) return aDag - bDag;
        const aName = getSiteName(a.display_from_id);
        const bName = getSiteName(b.display_from_id);
        return String(aName).localeCompare(String(bName));
      });
  }, [normalisedLanes, getDagOrderForSite, getSiteName]);

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-lg font-semibold">Lanes</h2>
        <div className="flex gap-2">
          <Button
            onClick={() => handleOpenDialog()}
            disabled={loading || sites.length < 2 || sourceSites.length === 0}
            leftIcon={<Plus className="h-4 w-4" />}
          >
            Add Lane
          </Button>
          {navigationButtons}
        </div>
      </div>

      {sites.length < 2 ? (
        <Card variant="outline" className="p-6 text-center">
          <p className="text-muted-foreground">Add at least 2 sites to create lanes between them.</p>
        </Card>
      ) : sourceSites.length === 0 ? (
        <Card variant="outline" className="p-6 text-center">
          <p className="text-muted-foreground">
            Add at least one upstream site (e.g., Market Supply or Manufacturer) to originate lanes.
          </p>
        </Card>
      ) : (
        <Card variant="outline">
          <div className="px-4 py-3 border-b">
            <p className="text-sm text-muted-foreground">
              Products flow from the source site to the destination site. Orders travel in the opposite direction.
            </p>
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>From Site</TableHead>
                <TableHead className="text-center">DAG Order (From → To)</TableHead>
                <TableHead className="text-center w-12">
                  <ArrowRight className="h-4 w-4 mx-auto text-muted-foreground" />
                </TableHead>
                <TableHead>To Site</TableHead>
                <TableHead className="text-right">Demand Lead Time</TableHead>
                <TableHead className="text-right">Supply Lead Time</TableHead>
                <TableHead className="text-right">Capacity</TableHead>
                <TableHead className="text-right">Cost/Unit</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sortedLanes.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={9} className="text-center">
                    No lanes added yet. Click "Add Lane" to connect sites.
                  </TableCell>
                </TableRow>
              ) : (
                sortedLanes.map((lane) => {
                  const fromDagOrder = getDagOrderDisplay(lane.display_from_id);
                  const toDagOrder = getDagOrderDisplay(lane.display_to_id);

                  return (
                    <TableRow key={lane.id}>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Badge variant={getSiteTypeVariant(getSiteType(lane.display_from_id))}>
                            {getSiteTypeLabel(getSiteType(lane.display_from_id))}
                          </Badge>
                          {getSiteName(lane.display_from_id)}
                        </div>
                      </TableCell>
                      <TableCell className="text-center">
                        <div className="flex items-center justify-center gap-1">
                          <span className="text-sm">{fromDagOrder}</span>
                          <ArrowRight className="h-4 w-4 text-muted-foreground" />
                          <span className="text-sm">{toDagOrder}</span>
                        </div>
                      </TableCell>
                      <TableCell className="text-center">
                        <ArrowRight className="h-4 w-4 mx-auto text-muted-foreground" />
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Badge variant={getSiteTypeVariant(getSiteType(lane.display_to_id))}>
                            {getSiteTypeLabel(getSiteType(lane.display_to_id))}
                          </Badge>
                          {getSiteName(lane.display_to_id)}
                        </div>
                      </TableCell>
                      <TableCell className="text-right">{getDemandLead(lane)}</TableCell>
                      <TableCell className="text-right">{getSupplyLead(lane)}</TableCell>
                      <TableCell className="text-right">{getCapacityDisplay(lane)}</TableCell>
                      <TableCell className="text-right">{getCostDisplay(lane)}</TableCell>
                      <TableCell className="text-right">
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleOpenDialog(lane)}
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
                                onClick={() => handleDelete(lane.id)}
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
        </Card>
      )}

      <Modal
        isOpen={openDialog}
        onClose={handleCloseDialog}
        title={editingLane ? 'Edit Lane' : 'Add New Lane'}
        size="md"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={handleCloseDialog} disabled={loading} leftIcon={<X className="h-4 w-4" />}>
              Cancel
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={loading || !formData.from_site_id || !formData.to_site_id}
              leftIcon={editingLane ? <Save className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
            >
              {editingLane ? 'Update' : 'Add'} Lane
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <div>
            <Label htmlFor="from-site">From Site</Label>
            <Select
              value={formData.from_site_id ? String(formData.from_site_id) : ''}
              onValueChange={(value) => handleChange('from_site_id', Number(value))}
              disabled={loading || !!editingLane}
            >
              <SelectTrigger id="from-site" className={errors.from_site_id ? 'border-destructive' : ''}>
                <SelectValue placeholder="Select source site" />
              </SelectTrigger>
              <SelectContent>
                {sourceSites.map((site) => (
                  <SelectItem key={site.id} value={String(site.id)}>
                    <div className="flex items-center gap-2">
                      <Badge variant={getSiteTypeVariant(site.type)} className="text-xs">
                        {getSiteTypeLabel(site.type)}
                      </Badge>
                      {site.name}
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {errors.from_site_id && <p className="text-xs text-destructive mt-1">{errors.from_site_id}</p>}
          </div>

          <div>
            <Label htmlFor="to-site">To Site</Label>
            <Select
              value={formData.to_site_id ? String(formData.to_site_id) : ''}
              onValueChange={(value) => handleChange('to_site_id', Number(value))}
              disabled={loading || !formData.from_site_id || !!editingLane}
            >
              <SelectTrigger id="to-site" className={errors.to_site_id ? 'border-destructive' : ''}>
                <SelectValue placeholder="Select destination site" />
              </SelectTrigger>
              <SelectContent>
                {filteredToSites.map((site) => (
                  <SelectItem key={site.id} value={String(site.id)}>
                    <div className="flex items-center gap-2">
                      <Badge variant={getSiteTypeVariant(site.type)} className="text-xs">
                        {getSiteTypeLabel(site.type)}
                      </Badge>
                      {site.name}
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {errors.to_site_id ? (
              <p className="text-xs text-destructive mt-1">{errors.to_site_id}</p>
            ) : !formData.from_site_id ? (
              <p className="text-xs text-muted-foreground mt-1">Select a source site first</p>
            ) : filteredToSites.length === 0 ? (
              <p className="text-xs text-muted-foreground mt-1">No valid destination sites available for the selected source</p>
            ) : null}
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div>
              <Label htmlFor="demand-lead-time">Demand Lead Time</Label>
              <Input
                id="demand-lead-time"
                type="number"
                value={formData.demand_lead_time}
                onChange={(e) => handleChange('demand_lead_time', e.target.value)}
                disabled={loading}
                min={0}
                step={0.5}
                className={errors.demand_lead_time ? 'border-destructive' : ''}
              />
              {errors.demand_lead_time ? (
                <p className="text-xs text-destructive mt-1">{errors.demand_lead_time}</p>
              ) : (
                <p className="text-xs text-muted-foreground mt-1">Delay for orders to reach the source site</p>
              )}
            </div>

            <div>
              <Label htmlFor="supply-lead-time">Supply Lead Time</Label>
              <Input
                id="supply-lead-time"
                type="number"
                value={formData.supply_lead_time}
                onChange={(e) => handleChange('supply_lead_time', e.target.value)}
                disabled={loading}
                min={0}
                step={0.5}
                className={errors.supply_lead_time ? 'border-destructive' : ''}
              />
              {errors.supply_lead_time ? (
                <p className="text-xs text-destructive mt-1">{errors.supply_lead_time}</p>
              ) : (
                <p className="text-xs text-muted-foreground mt-1">Transit time for shipments to arrive</p>
              )}
            </div>

            <div>
              <Label htmlFor="capacity">Capacity (units)</Label>
              <Input
                id="capacity"
                type="number"
                value={formData.capacity}
                onChange={(e) => handleChange('capacity', e.target.value)}
                disabled={loading}
                min={1}
                step={1}
                className={errors.capacity ? 'border-destructive' : ''}
              />
              {errors.capacity && <p className="text-xs text-destructive mt-1">{errors.capacity}</p>}
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div>
              <Label htmlFor="cost-per-unit">Cost per Unit ($)</Label>
              <Input
                id="cost-per-unit"
                type="number"
                value={formData.cost_per_unit}
                onChange={(e) => handleChange('cost_per_unit', e.target.value)}
                disabled={loading}
                min={0}
                step={0.01}
                className={errors.cost_per_unit ? 'border-destructive' : ''}
              />
              {errors.cost_per_unit && <p className="text-xs text-destructive mt-1">{errors.cost_per_unit}</p>}
            </div>
          </div>

          {errors.duplicate && (
            <Alert variant="destructive">
              {errors.duplicate}
            </Alert>
          )}
        </div>
      </Modal>
    </div>
  );
};

// DEPRECATED: Use TransportationLaneForm
const LaneForm = TransportationLaneForm;

export default TransportationLaneForm;
export { LaneForm };
