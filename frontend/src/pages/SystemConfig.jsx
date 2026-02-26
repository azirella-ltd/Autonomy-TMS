import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  AlertDescription,
  Button,
  Card,
  CardContent,
  Input,
  Label,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/common';
import PageLayout from '../components/PageLayout';
import simulationApi from '../services/api';
import { getSupplyChainConfigs, getProducts, getSites, getLanes } from '../services/supplyChainConfigService';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { isTenantAdmin as isTenantAdminUser } from '../utils/authUtils';

const DEFAULTS = {
  supply_leadtime: { min: 0, max: 8 },
  order_leadtime: { min: 0, max: 8 },
  init_inventory: { min: 0, max: 1000 },
  holding_cost: { min: 0, max: 100 },
  backlog_cost: { min: 0, max: 200 },
  max_inbound_per_link: { min: 10, max: 2000 },
  max_order: { min: 10, max: 2000 },
  price: { min: 0, max: 10000 },
  standard_cost: { min: 0, max: 10000 },
  min_order_qty: { min: 0, max: 1000 },
};

const LABELS = {
  order_leadtime: 'Order Leadtime',
  supply_leadtime: 'Supply Leadtime',
  max_inbound_per_link: 'Inbound Lane Capacity',
  min_order_qty: 'MOQ',
};

const SystemConfig = () => {
  const [ranges, setRanges] = useState(DEFAULTS);
  const [saved, setSaved] = useState(false);
  const [name, setName] = useState('Undefined');
  const [configs, setConfigs] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [counts, setCounts] = useState({ products: 0, sites: 0, lanes: 0 });
  const [loadingConfigs, setLoadingConfigs] = useState(true);
  const navigate = useNavigate();
  const { user } = useAuth();
  const isTenantAdmin = isTenantAdminUser(user);
  const scConfigBasePath = isTenantAdmin ? '/admin/tenant/supply-chain-configs' : '/supply-chain-config';

  useEffect(() => {
    let active = true;
    const init = async () => {
      let configuredName;
      try {
        const data = await simulationApi.getSystemConfig();
        const { name: cfgName, variable_cost, ...rest } = data || {};
        configuredName = cfgName;
        if (!active) return;
        setName(cfgName || 'Undefined');
        setRanges({ ...DEFAULTS, ...rest });
      } catch (error) {
        const fallback = localStorage.getItem('systemConfigRanges');
        if (fallback) {
          try {
            const parsed = JSON.parse(fallback);
            const { name: cfgName, variable_cost, ...rest } = parsed || {};
            configuredName = cfgName;
            if (!active) return;
            setName(cfgName || 'Undefined');
            setRanges({ ...DEFAULTS, ...rest });
          } catch (_) {
            // ignore invalid cache
          }
        }
      }

      try {
        const configs = await getSupplyChainConfigs();
        if (!active) return;
        const list = Array.isArray(configs) ? configs : [];
        setConfigs(list);
        const matching = list.find((cfg) => cfg.name === configuredName);
        if (matching) {
          setSelectedId(String(matching.id));
        }
      } catch (error) {
        if (active) {
          setConfigs([]);
        }
      } finally {
        if (active) setLoadingConfigs(false);
      }
    };

    init();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setCounts({ products: 0, sites: 0, lanes: 0 });
      return;
    }

    const fetchCounts = async (configId) => {
      try {
        const [products, sites, lanes] = await Promise.all([
          getProducts(configId),
          getSites(configId),
          getLanes(configId),
        ]);
        setCounts({
          products: products.length,
          sites: sites.length,
          lanes: lanes.length,
        });
      } catch (error) {
        setCounts({ products: 0, sites: 0, lanes: 0 });
      }
    };

    fetchCounts(Number(selectedId));
  }, [selectedId]);

  const handleRangeChange = (key, field, value) => {
    setRanges((prev) => ({
      ...prev,
      [key]: {
        ...prev[key],
        [field]: Number(value),
      },
    }));
  };

  const handleSelectChange = (event) => {
    const id = event.target.value;
    setSelectedId(id);
    const cfg = configs.find((config) => String(config.id) === String(id));
    setName(cfg?.name || 'Undefined');
  };

  const handleSave = async () => {
    try {
      await simulationApi.saveSystemConfig({ name, ...ranges });
      showSaved();
    } catch (error) {
      showSaved();
    }
  };

  const showSaved = () => {
    setSaved(true);
    localStorage.setItem('systemConfigRanges', JSON.stringify({ name, ...ranges }));
    setTimeout(() => setSaved(false), 1500);
  };

  const navigateToConfig = () => {
    if (!selectedId) return;
    navigate(`${scConfigBasePath}/edit/${selectedId}`);
  };

  const systemSummary = useMemo(() => (
    <p className="text-sm text-muted-foreground mb-4">
      Define allowable ranges for configuration variables. These ranges seed the Mixed Game definition workflow.
    </p>
  ), []);

  return (
    <PageLayout title="System Configuration">
      <Card>
        <CardContent className="pt-6">
          <h2 className="text-xl font-bold mb-2">System Configuration</h2>
          {systemSummary}

          <div className="flex gap-4 items-end flex-wrap mb-6">
            <div className="min-w-[260px]">
              <Label htmlFor="config-select">Configuration Name ({configs.length})</Label>
              <select
                id="config-select"
                value={selectedId}
                onChange={handleSelectChange}
                className="w-full mt-1 h-10 px-3 rounded-md border border-input bg-background"
              >
                <option value="">Select configuration</option>
                {configs.map((config) => (
                  <option key={config.id} value={String(config.id)}>
                    {config.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="min-w-[220px]">
              <Label htmlFor="active-name">Active Name</Label>
              <Input
                id="active-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="mt-1"
              />
            </div>
            <Button onClick={() => navigate(`${scConfigBasePath}/new`)}>
              New Configuration
            </Button>
          </div>

          {loadingConfigs && (
            <Alert className="mb-6">
              <AlertDescription>Loading configurations…</AlertDescription>
            </Alert>
          )}

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Parameter</TableHead>
                <TableHead className="text-right">Min Value</TableHead>
                <TableHead className="text-right">Max Value</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {Object.entries(ranges)
                .filter(([key]) => key !== 'name' && key !== 'variable_cost')
                .map(([key, value]) => (
                  <TableRow key={key}>
                    <TableCell className="capitalize">
                      {LABELS[key] || key.replaceAll('_', ' ')}
                    </TableCell>
                    <TableCell className="text-right">
                      <Input
                        type="number"
                        value={value.min}
                        onChange={(e) => handleRangeChange(key, 'min', e.target.value)}
                        className="w-24 ml-auto"
                      />
                    </TableCell>
                    <TableCell className="text-right">
                      <Input
                        type="number"
                        value={value.max}
                        onChange={(e) => handleRangeChange(key, 'max', e.target.value)}
                        className="w-24 ml-auto"
                      />
                    </TableCell>
                  </TableRow>
                ))}
            </TableBody>
          </Table>

          <div className="mt-8">
            <h3 className="font-bold mb-2">Definitions</h3>
            <p className="text-sm">Products: {counts.products}</p>
            <p className="text-sm">Sites: {counts.sites}</p>
            <p className="text-sm mb-4">Lanes: {counts.lanes}</p>
            <Button
              variant="outline"
              onClick={navigateToConfig}
              disabled={!selectedId || name === 'Undefined'}
            >
              Define Products, Sites, Lanes
            </Button>
          </div>

          <div className="text-right mt-8">
            <Button onClick={handleSave}>
              Save Ranges
            </Button>
            {saved && (
              <span className="ml-4 text-green-600">Saved</span>
            )}
          </div>
        </CardContent>
      </Card>
    </PageLayout>
  );
};

export default SystemConfig;
