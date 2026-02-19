import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Card,
  CardContent,
  Button,
  Input,
  Label,
  Modal,
  Spinner,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  Checkbox,
} from '../../components/common';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../../components/ui/tooltip';
import { Trash2, Plus, Wand2, CheckCircle, AlertCircle } from 'lucide-react';
import PageLayout from '../../components/PageLayout';
import simulationApi from '../../services/api';
import { useSystemConfig } from '../../contexts/SystemConfigContext.jsx';
import { getAdminDashboardPath } from '../../utils/adminDashboardState';

const siteTypes = ['manufacturer', 'distributor', 'wholesaler', 'retailer'];

const classicPreset = () => ({
  version: 1,
  products: [{ id: 'product_1', name: 'Product 1' }],
  // Backward compatibility alias
  get items() { return this.products; },
  sites: [
    { id: 'manufacturer_1', type: 'manufacturer', name: 'Manufacturer 1', products_sold: ['product_1'] },
    { id: 'distributor_1', type: 'distributor', name: 'Distributor 1', products_sold: ['product_1'] },
    { id: 'wholesaler_1', type: 'wholesaler', name: 'Wholesaler 1', products_sold: ['product_1'] },
    { id: 'retailer_1', type: 'retailer', name: 'Retailer 1', products_sold: ['product_1'] },
  ],
  site_product_settings: {
    manufacturer_1: { product_1: { inventory_target: 20, holding_cost: 0.5, backorder_cost: 1.0, avg_selling_price: 7.0, standard_cost: 5.0, moq: 0 } },
    distributor_1: { product_1: { inventory_target: 20, holding_cost: 0.5, backorder_cost: 1.0, avg_selling_price: 7.0, standard_cost: 5.0, moq: 0 } },
    wholesaler_1: { product_1: { inventory_target: 20, holding_cost: 0.5, backorder_cost: 1.0, avg_selling_price: 7.0, standard_cost: 5.0, moq: 0 } },
    retailer_1: { product_1: { inventory_target: 20, holding_cost: 0.5, backorder_cost: 1.0, avg_selling_price: 7.0, standard_cost: 5.0, moq: 0 } },
  },
  // Backward compatibility alias
  get site_item_settings() { return this.site_product_settings; },
  lanes: [
    {
      from_site_id: 'manufacturer_1',
      to_site_id: 'distributor_1',
      product_id: 'product_1',
      demand_lead_time: { type: 'deterministic', value: 0 },
      supply_lead_time: { type: 'deterministic', value: 2 },
      lead_time: 2,
      capacity: null,
      otif_target: 0.95,
    },
    {
      from_site_id: 'distributor_1',
      to_site_id: 'wholesaler_1',
      product_id: 'product_1',
      demand_lead_time: { type: 'deterministic', value: 0 },
      supply_lead_time: { type: 'deterministic', value: 2 },
      lead_time: 2,
      capacity: null,
      otif_target: 0.95,
    },
    {
      from_site_id: 'wholesaler_1',
      to_site_id: 'retailer_1',
      product_id: 'product_1',
      demand_lead_time: { type: 'deterministic', value: 0 },
      supply_lead_time: { type: 'deterministic', value: 2 },
      lead_time: 2,
      capacity: null,
      otif_target: 0.95,
    },
  ],
  retailer_demand: { distribution: 'profile', params: { week1_4: 4, week5_plus: 8 }, expected_delivery_offset: 1 },
  manufacturer_lead_times: { product_1: 2 },
});

function numberIn(range, v) {
  if (!range) return true;
  if (typeof v !== 'number' || Number.isNaN(v)) return false;
  return v >= range.min && v <= range.max;
}

const parseNumeric = (value) => {
  if (value === null || value === undefined) return null;
  const numeric = Number(value);
  return Number.isNaN(numeric) ? null : numeric;
};

const getDistributionValue = (distribution) => {
  if (distribution === null || distribution === undefined) return null;
  if (typeof distribution === 'number') {
    return Number.isFinite(distribution) ? distribution : null;
  }
  if (typeof distribution !== 'object') {
    return null;
  }

  if (distribution?.type === 'deterministic' && distribution.value !== undefined) {
    const numeric = parseNumeric(distribution.value);
    if (numeric !== null) {
      return numeric;
    }
  }

  if (distribution?.value !== undefined) {
    const numeric = parseNumeric(distribution.value);
    if (numeric !== null) {
      return numeric;
    }
  }

  if (distribution?.mean !== undefined) {
    const numeric = parseNumeric(distribution.mean);
    if (numeric !== null) {
      return numeric;
    }
  }

  const min = parseNumeric(distribution?.minimum);
  const max = parseNumeric(distribution?.maximum);
  if (min !== null && max !== null) {
    return (min + max) / 2;
  }
  if (min !== null) {
    return min;
  }
  if (max !== null) {
    return max;
  }

  return null;
};

const getLegacyLeadTimeValue = (lane) => {
  if (!lane) return null;
  const range = lane.lead_time_days;
  if (range && typeof range === 'object') {
    const min = parseNumeric(range.min);
    const max = parseNumeric(range.max);
    if (min !== null && max !== null) {
      return min === max ? min : (min + max) / 2;
    }
    if (min !== null) return min;
    if (max !== null) return max;
  }

  const legacy = parseNumeric(lane.lead_time);
  if (legacy !== null) {
    return legacy;
  }

  return null;
};

const getLaneOrderLeadValue = (lane) => {
  const value = getDistributionValue(lane?.demand_lead_time);
  return value !== null ? value : null;
};

const getLaneSupplyLeadValue = (lane) => {
  const value = getDistributionValue(lane?.supply_lead_time);
  if (value !== null) return value;
  return getLegacyLeadTimeValue(lane);
};

export default function ModelSetup() {
  const navigate = useNavigate();
  const { ranges } = useSystemConfig();
  const [cfg, setCfg] = useState(classicPreset());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [processDialogOpen, setProcessDialogOpen] = useState(false);
  const [processSteps, setProcessSteps] = useState([]);
  const autoCloseRef = useRef(null);

  useEffect(() => {
    (async () => {
      try {
        const data = await simulationApi.getModelConfig();
        if (data) setCfg(data);
      } catch (e) {
        // keep preset
      } finally { setLoading(false); }
    })();
  }, []);

  // AWS SC DM: products (with backward compat for items)
  const products = useMemo(() => cfg.products || cfg.items || [], [cfg.products, cfg.items]);
  const sites = useMemo(() => cfg.sites || [], [cfg.sites]);

  const setSiteProduct = (siteId, productId, field, value) => {
    setCfg((prev) => {
      const settings = prev.site_product_settings || prev.site_item_settings || {};
      return {
        ...prev,
        site_product_settings: {
          ...settings,
          [siteId]: {
            ...(settings[siteId] || {}),
            [productId]: { ...(settings[siteId]?.[productId] || {}), [field]: value }
          }
        }
      };
    });
  };

  const setLane = (idx, field, value) => {
    setCfg((prev) => {
      const lanes = [...(prev.lanes || [])];
      const current = { ...lanes[idx] };
      if (field === 'demand_lead_time') {
        if (value === null || Number.isNaN(value)) {
          current.demand_lead_time = null;
        } else {
          current.demand_lead_time = { type: 'deterministic', value: Number(value) };
        }
      } else if (field === 'supply_lead_time') {
        if (value === null || Number.isNaN(value)) {
          current.supply_lead_time = null;
          delete current.lead_time;
        } else {
          const numeric = Number(value);
          current.supply_lead_time = { type: 'deterministic', value: numeric };
          current.lead_time = numeric;
        }
      } else {
        current[field] = value;
      }
      lanes[idx] = current;
      return { ...prev, lanes };
    });
  };

  const addProduct = () => {
    const n = (products?.length || 0) + 1;
    const newProduct = { id: `product_${n}`, name: `Product ${n}` };
    setCfg((prev) => ({ ...prev, products: [...(prev.products || prev.items || []), newProduct] }));
  };

  const removeProduct = (productId) => {
    setCfg((prev) => {
      const products = (prev.products || prev.items || []).filter((p) => p.id !== productId);
      const sites = (prev.sites || []).map((s) => ({
        ...s,
        products_sold: (s.products_sold || s.items_sold || []).filter((id) => id !== productId)
      }));
      const settings = prev.site_product_settings || prev.site_item_settings || {};
      const sps = Object.fromEntries(
        Object.entries(settings).map(([sid, m]) => [sid, Object.fromEntries(Object.entries(m).filter(([pid]) => pid !== productId))])
      );
      const lanes = (prev.lanes || []).filter((ln) => (ln.product_id || ln.item_id) !== productId);
      return { ...prev, products, sites, site_product_settings: sps, lanes };
    });
  };

  const addSite = (type) => {
    const idx = (sites.filter((s) => s.type === type).length || 0) + 1;
    const id = `${type}_${idx}`;
    const name = `${type.charAt(0).toUpperCase() + type.slice(1)} ${idx}`;
    const productIds = (prev) => (prev.products || prev.items || []).map((p) => p.id);
    setCfg((prev) => ({ ...prev, sites: [...(prev.sites || []), { id, type, name, products_sold: productIds(prev) }] }));
  };

  const removeSite = (siteId) => {
    setCfg((prev) => {
      const sites = (prev.sites || []).filter((s) => s.id !== siteId);
      const settings = prev.site_product_settings || prev.site_item_settings || {};
      const sps = Object.fromEntries(Object.entries(settings).filter(([sid]) => sid !== siteId));
      const lanes = (prev.lanes || []).filter((ln) => ln.from_site_id !== siteId && ln.to_site_id !== siteId);
      return { ...prev, sites, site_product_settings: sps, lanes };
    });
  };

  const setProductsSold = (siteId, productIds) => {
    setCfg((prev) => ({
      ...prev,
      sites: (prev.sites || []).map((s) => (s.id === siteId ? { ...s, products_sold: productIds } : s)),
    }));
  };

  const addLane = () => {
    const firstProduct = products[0]?.id || 'product_1';
    const manufacturer = sites.find((s) => s.type === 'manufacturer')?.id || '';
    const retailer = sites.find((s) => s.type === 'retailer')?.id || '';
    const defaultLane = {
      from_site_id: manufacturer,
      to_site_id: retailer,
      product_id: firstProduct,
      demand_lead_time: { type: 'deterministic', value: 0 },
      supply_lead_time: { type: 'deterministic', value: 1 },
      lead_time: 1,
      capacity: null,
      otif_target: 0.95,
    };
    setCfg((prev) => ({ ...prev, lanes: [...(prev.lanes || []), defaultLane] }));
  };

  const generateChainLanesAllToAll = () => {
    const typesOrder = ['manufacturer', 'distributor', 'wholesaler', 'retailer'];
    const byType = Object.fromEntries(typesOrder.map((t) => [t, sites.filter((s) => s.type === t)]));
    const newLanes = [];
    for (let i = 0; i < typesOrder.length - 1; i++) {
      const froms = byType[typesOrder[i]];
      const tos = byType[typesOrder[i + 1]];
      for (const prod of products) {
        for (const f of froms) {
          for (const t of tos) {
            const supplyLead = 2;
            newLanes.push({
              from_site_id: f.id,
              to_site_id: t.id,
              product_id: prod.id,
              demand_lead_time: { type: 'deterministic', value: 0 },
              supply_lead_time: { type: 'deterministic', value: supplyLead },
              lead_time: supplyLead,
              capacity: null,
              otif_target: 0.95,
            });
          }
        }
      }
    }
    setCfg((prev) => ({ ...prev, lanes: newLanes }));
  };

  const violations = useMemo(() => {
    const errs = [];
    const settings = cfg.site_product_settings || cfg.site_item_settings || {};
    for (const site of sites) {
      for (const product of products) {
        const s = settings[site.id]?.[product.id];
        if (!s) continue;
        if (!numberIn(ranges?.init_inventory, s.inventory_target)) errs.push(`${site.name}/${product.name}: inventory_target`);
        if (!numberIn(ranges?.holding_cost, s.holding_cost)) errs.push(`${site.name}/${product.name}: holding_cost`);
        if (!numberIn(ranges?.backlog_cost, s.backorder_cost)) errs.push(`${site.name}/${product.name}: backorder_cost`);
        if (!numberIn(ranges?.price, s.avg_selling_price)) errs.push(`${site.name}/${product.name}: avg_selling_price`);
        if (!numberIn(ranges?.standard_cost, s.standard_cost)) errs.push(`${site.name}/${product.name}: standard_cost`);
        if (!numberIn(ranges?.min_order_qty, s.moq)) errs.push(`${site.name}/${product.name}: moq`);
      }
    }
    for (const [i, lane] of (cfg.lanes || []).entries()) {
      const orderLeadValue = getLaneOrderLeadValue(lane);
      const supplyLeadValue = getLaneSupplyLeadValue(lane);
      const orderLeadForCheck = orderLeadValue ?? 0;
      const supplyLeadForCheck = supplyLeadValue ?? 0;
      if (!numberIn(ranges?.order_leadtime, orderLeadForCheck)) errs.push(`Lane ${i+1}: demand_lead_time`);
      if (!numberIn(ranges?.ship_order_leadtimedelay, supplyLeadForCheck)) errs.push(`Lane ${i+1}: supply_lead_time`);
      if (lane.capacity != null && !numberIn(ranges?.max_inbound_per_link, Number(lane.capacity))) errs.push(`Lane ${i+1}: capacity`);
    }
    return errs;
  }, [cfg, ranges, products, sites]);

  const closeProcessDialog = () => {
    if (autoCloseRef.current) {
      clearTimeout(autoCloseRef.current);
      autoCloseRef.current = null;
    }
    setProcessDialogOpen(false);
    setProcessSteps([]);
  };

  useEffect(() => () => {
    if (autoCloseRef.current) {
      clearTimeout(autoCloseRef.current);
    }
  }, []);

  const save = async () => {
    setSaving(true);
    setError(null);
    setProcessSteps([
      {
        id: 'save-model-config',
        label: 'Saving model configuration',
        status: 'running',
        message: 'Submitting your latest changes to the server.',
      },
    ]);
    setProcessDialogOpen(true);
    try {
      const saved = await simulationApi.saveModelConfig(cfg);
      setCfg(saved);
      setProcessSteps((prev) =>
        prev.map((step) =>
          step.id === 'save-model-config'
            ? { ...step, status: 'success', message: 'Configuration saved successfully.' }
            : step
        )
      );
      if (autoCloseRef.current) {
        clearTimeout(autoCloseRef.current);
      }
      autoCloseRef.current = setTimeout(() => {
        closeProcessDialog();
      }, 1200);
    } catch (e) {
      const detail = e?.response?.data?.detail;
      const message = typeof detail === 'string' ? detail : detail?.message || 'Failed to save configuration.';
      setError(message);
      setProcessSteps((prev) =>
        prev.map((step) =>
          step.id === 'save-model-config'
            ? { ...step, status: 'error', message }
            : step
        )
      );
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <PageLayout title="Model Setup"><div className="p-6">Loading...</div></PageLayout>;

  const hasActiveProcess = processSteps.some((step) => step.status === 'running');
  const canCloseProcessDialog = processSteps.length > 0 && !hasActiveProcess;

  const toggleProductSold = (siteId, productId) => {
    const site = sites.find(s => s.id === siteId);
    if (!site) return;
    const current = site.products_sold || site.items_sold || [];
    if (current.includes(productId)) {
      setProductsSold(siteId, current.filter(id => id !== productId));
    } else {
      setProductsSold(siteId, [...current, productId]);
    }
  };

  return (
    <PageLayout title="Model Setup">
      <Card>
        <CardContent className="p-6 space-y-6">
          <div className="flex gap-2">
            <Button onClick={() => setCfg(classicPreset())}>Classic Supply Chain Preset</Button>
            <Button variant="outline" onClick={() => navigate(getAdminDashboardPath())}>Back to Admin Dashboard</Button>
          </div>

          {error && <div className="bg-red-50 text-red-700 p-3 rounded">{error}</div>}

          {/* Products (AWS SC DM compliant - was Items) */}
          <div>
            <h3 className="text-lg font-semibold mb-2">Products</h3>
            <div className="mb-2">
              <Button size="sm" variant="outline" onClick={addProduct} leftIcon={<Plus className="h-4 w-4" />}>
                Add Product
              </Button>
            </div>
            {products.map((prod, idx) => (
              <div key={prod.id} className="flex gap-2 mb-2 items-center">
                <div className="w-40">
                  <Label className="text-xs">Product ID</Label>
                  <Input
                    value={prod.id}
                    onChange={(e) => {
                      const products2 = [...products];
                      products2[idx] = { ...prod, id: e.target.value };
                      setCfg({ ...cfg, products: products2 });
                    }}
                  />
                </div>
                <div className="w-40">
                  <Label className="text-xs">Name</Label>
                  <Input
                    value={prod.name}
                    onChange={(e) => {
                      const products2 = [...products];
                      products2[idx] = { ...prod, name: e.target.value };
                      setCfg({ ...cfg, products: products2 });
                    }}
                  />
                </div>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button variant="ghost" size="sm" onClick={() => removeProduct(prod.id)}>
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Remove Product</TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </div>
            ))}
          </div>

          {/* Sites */}
          <div>
            <h3 className="text-lg font-semibold mb-2">Sites</h3>
            <div className="flex gap-2 mb-2">
              {siteTypes.map((t) => (
                <Button key={t} size="sm" variant="outline" onClick={() => addSite(t)} leftIcon={<Plus className="h-4 w-4" />}>
                  Add {t}
                </Button>
              ))}
            </div>
            {sites.map((s, idx) => (
              <div key={s.id} className="flex gap-2 mb-2 items-center flex-wrap">
                <div className="w-36">
                  <Label className="text-xs">Site ID</Label>
                  <Input
                    value={s.id}
                    onChange={(e) => {
                      const sites2 = [...sites];
                      sites2[idx] = { ...s, id: e.target.value };
                      setCfg({ ...cfg, sites: sites2 });
                    }}
                  />
                </div>
                <div className="w-32">
                  <Label className="text-xs">Type</Label>
                  <Select
                    value={s.type}
                    onValueChange={(value) => {
                      const sites2 = [...sites];
                      sites2[idx] = { ...s, type: value };
                      setCfg({ ...cfg, sites: sites2 });
                    }}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {siteTypes.map((t) => (
                        <SelectItem key={t} value={t}>{t}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="w-40">
                  <Label className="text-xs">Name</Label>
                  <Input
                    value={s.name}
                    onChange={(e) => {
                      const sites2 = [...sites];
                      sites2[idx] = { ...s, name: e.target.value };
                      setCfg({ ...cfg, sites: sites2 });
                    }}
                  />
                </div>
                <div className="min-w-[200px]">
                  <Label className="text-xs">Products Sold</Label>
                  <div className="flex flex-wrap gap-2 mt-1">
                    {products.map((prod) => (
                      <label key={prod.id} className="flex items-center gap-1 text-sm">
                        <Checkbox
                          checked={(s.products_sold || s.items_sold || []).includes(prod.id)}
                          onCheckedChange={() => toggleProductSold(s.id, prod.id)}
                        />
                        {prod.name}
                      </label>
                    ))}
                  </div>
                </div>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button variant="ghost" size="sm" onClick={() => removeSite(s.id)}>
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Remove Site</TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </div>
            ))}
          </div>

          {/* Site-Product Settings (AWS SC DM compliant) */}
          <div>
            <h3 className="text-lg font-semibold mb-2">Site-Product Settings</h3>
            {sites.map((s) => {
              const settings = cfg.site_product_settings || cfg.site_item_settings || {};
              return (
                <div key={s.id} className="rounded border p-3 mb-2">
                  <div className="font-medium mb-2">{s.name}</div>
                  {products.map((prod) => {
                    const st = settings[s.id]?.[prod.id] || {};
                    const field = (name, label, range, step = 1) => (
                      <div key={name} className="inline-block mr-2 mb-2">
                        <Label className="text-xs">{label}{range ? ` [${range.min}-${range.max}]` : ''}</Label>
                        <Input
                          type="number"
                          className={`w-40 ${range && !numberIn(range, Number(st[name])) ? 'border-red-500' : ''}`}
                          value={st[name] ?? ''}
                          onChange={(e) => setSiteProduct(s.id, prod.id, name, e.target.valueAsNumber)}
                          step={step}
                        />
                      </div>
                    );
                    return (
                      <div key={prod.id}>
                        <div className="text-sm text-muted-foreground mb-1">{prod.name}</div>
                        {field('inventory_target', 'Inventory Target', ranges?.init_inventory)}
                        {field('holding_cost', 'Holding Cost', ranges?.holding_cost, 0.1)}
                        {field('backorder_cost', 'Backorder Cost', ranges?.backlog_cost, 0.1)}
                        {field('avg_selling_price', 'Avg Selling Price', ranges?.price, 0.1)}
                        {field('standard_cost', 'Standard Cost', ranges?.standard_cost, 0.1)}
                        {field('moq', 'MOQ', ranges?.min_order_qty)}
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>

          {/* Lanes */}
          <div>
            <h3 className="text-lg font-semibold mb-2">Lanes</h3>
            <div className="flex gap-2 mb-2">
              <Button size="sm" variant="outline" onClick={addLane} leftIcon={<Plus className="h-4 w-4" />}>
                Add Lane
              </Button>
              <Button size="sm" variant="outline" onClick={generateChainLanesAllToAll} leftIcon={<Wand2 className="h-4 w-4" />}>
                Generate Chain Lanes (all-to-all)
              </Button>
            </div>
            {(cfg.lanes || []).map((ln, i) => {
              const orderLeadValue = getLaneOrderLeadValue(ln);
              const supplyLeadValue = getLaneSupplyLeadValue(ln);
              const orderLeadForCheck = orderLeadValue ?? 0;
              const supplyLeadForCheck = supplyLeadValue ?? 0;
              return (
                <div key={i} className="flex gap-2 mb-2 items-end flex-wrap">
                  <div className="w-32">
                    <Label className="text-xs">From</Label>
                    <Input value={ln.from_site_id} onChange={(e) => setLane(i, 'from_site_id', e.target.value)} />
                  </div>
                  <div className="w-32">
                    <Label className="text-xs">To</Label>
                    <Input value={ln.to_site_id} onChange={(e) => setLane(i, 'to_site_id', e.target.value)} />
                  </div>
                  <div className="w-28">
                    <Label className="text-xs">Product</Label>
                    <Input value={ln.product_id || ln.item_id} onChange={(e) => setLane(i, 'product_id', e.target.value)} />
                  </div>
                  <div className="w-36">
                    <Label className="text-xs">Demand Lead {ranges?.order_leadtime ? `[${ranges.order_leadtime.min}-${ranges.order_leadtime.max}]` : ''}</Label>
                    <Input
                      type="number"
                      className={ranges?.order_leadtime && !numberIn(ranges.order_leadtime, orderLeadForCheck) ? 'border-red-500' : ''}
                      value={orderLeadValue ?? ''}
                      onChange={(e) => setLane(i, 'demand_lead_time', e.target.value === '' ? null : e.target.valueAsNumber)}
                    />
                  </div>
                  <div className="w-36">
                    <Label className="text-xs">Supply Lead {ranges?.ship_order_leadtimedelay ? `[${ranges.ship_order_leadtimedelay.min}-${ranges.ship_order_leadtimedelay.max}]` : ''}</Label>
                    <Input
                      type="number"
                      className={ranges?.ship_order_leadtimedelay && !numberIn(ranges.ship_order_leadtimedelay, supplyLeadForCheck) ? 'border-red-500' : ''}
                      value={supplyLeadValue ?? ''}
                      onChange={(e) => setLane(i, 'supply_lead_time', e.target.value === '' ? null : e.target.valueAsNumber)}
                    />
                  </div>
                  <div className="w-28">
                    <Label className="text-xs">Capacity {ranges?.max_inbound_per_link ? `[${ranges.max_inbound_per_link.min}-${ranges.max_inbound_per_link.max}]` : ''}</Label>
                    <Input
                      type="number"
                      className={ln.capacity != null && ranges?.max_inbound_per_link && !numberIn(ranges.max_inbound_per_link, Number(ln.capacity)) ? 'border-red-500' : ''}
                      value={ln.capacity ?? ''}
                      onChange={(e) => setLane(i, 'capacity', e.target.value === '' ? null : e.target.valueAsNumber)}
                    />
                  </div>
                  <div className="w-28">
                    <Label className="text-xs">OTIF Target (0-1 or %)</Label>
                    <Input
                      type="number"
                      value={ln.otif_target ?? ''}
                      onChange={(e) => setLane(i, 'otif_target', e.target.value === '' ? null : e.target.valueAsNumber)}
                    />
                  </div>
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button variant="ghost" size="sm" onClick={() => setCfg((prev) => ({ ...prev, lanes: (prev.lanes || []).filter((_, j) => j !== i) }))}>
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>Remove Lane</TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </div>
              );
            })}
          </div>

          {/* Save */}
          <div className="flex gap-2 items-center">
            <Button disabled={saving || violations.length > 0} onClick={save}>Save</Button>
            {violations.length > 0 && (
              <span className="text-sm text-red-600">Out of range: {violations.join(', ')}</span>
            )}
          </div>
        </CardContent>
      </Card>

      <Modal
        isOpen={processDialogOpen}
        onClose={canCloseProcessDialog ? closeProcessDialog : undefined}
        title="Processing updates"
        size="sm"
        footer={canCloseProcessDialog ? (
          <div className="flex justify-end">
            <Button onClick={closeProcessDialog}>Close</Button>
          </div>
        ) : null}
      >
        <p className="text-sm text-muted-foreground mb-4">
          We'll keep this window open while we finish saving your model configuration.
        </p>
        <div className="space-y-3">
          {processSteps.map((step) => (
            <div key={step.id} className="flex items-start gap-3">
              <div className="mt-0.5">
                {step.status === 'success' ? (
                  <CheckCircle className="h-5 w-5 text-green-500" />
                ) : step.status === 'error' ? (
                  <AlertCircle className="h-5 w-5 text-red-500" />
                ) : (
                  <Spinner size="sm" />
                )}
              </div>
              <div>
                <p className="font-medium">{step.label}</p>
                <p className="text-sm text-muted-foreground">{step.message}</p>
              </div>
            </div>
          ))}
        </div>
      </Modal>
    </PageLayout>
  );
}
