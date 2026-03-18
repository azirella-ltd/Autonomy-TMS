/**
 * Supply Chain Sankey – Executive Dashboard (S&OP Aggregation Level)
 *
 * Shows the supply chain network with hierarchy navigation:
 *   - Geography: Country / Region / State / Site drill-down
 *   - Product: All / Category filter
 *   - Time: Daily / Weekly / Monthly / Quarterly / Annual scaling
 *
 * Nodes = sites grouped by geography level × master type
 * Links = material flow between groups (sized by volume × time multiplier)
 *
 * Features:
 *   - Three hierarchy navigation dropdowns
 *   - Sankey Flow / Map View toggle
 *   - Auto-loads first available SC config when no configId prop
 *   - SankeyMetricLegend shown in Sankey mode
 *   - All data sourced from DB (no hardcoded defaults)
 */
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Spinner,
  ToggleGroup,
  ToggleGroupItem,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '../common';
import { Network } from 'lucide-react';
import SankeyDiagram from '../charts/SankeyDiagram';
import SankeyMetricLegend from '../charts/SankeyMetricLegend';
import GeospatialSupplyChain from '../visualization/GeospatialSupplyChain';
import HierarchyAggregationBar, { DEFAULT_HIERARCHY_VALUE } from '../metrics/HierarchyAggregationBar';
import {
  getSupplyChainConfigs,
  getSites,
  getLanes,
  getProducts,
} from '../../services/supplyChainConfigService';

// Column order: upstream (vendor source) → downstream (customer sink)
// AWS SC DM: VENDOR = external supplier (TradingPartner), CUSTOMER = external demand
const COLUMN_ORDER = [
  'VENDOR',
  'INVENTORY',
  'MANUFACTURER',
  'DISTRIBUTOR',
  'WHOLESALER',
  'RETAILER',
  'CUSTOMER',
];

// Site type colors (consistent with SupplyChainConfigSankey)
const TYPE_COLORS = {
  VENDOR: '#1d4ed8',          // blue (external supplier diamond)
  INVENTORY: '#0ea5e9',       // sky blue
  MANUFACTURER: '#0891b2',    // cyan
  DISTRIBUTOR: '#f59e0b',     // amber
  WHOLESALER: '#f97316',      // orange
  RETAILER: '#3b82f6',        // blue
  CUSTOMER: '#be123c',        // rose (external customer diamond)
};

// Geography hierarchy levels
const GEO_LEVELS = [
  { value: 'country', label: 'Country' },
  { value: 'region', label: 'Region' },
  { value: 'state', label: 'State' },
  { value: 'site', label: 'Site' },
];

// Time bucket options with multiplier relative to daily capacity
const TIME_BUCKETS = [
  { value: 'daily', label: 'Daily', multiplier: 1 },
  { value: 'weekly', label: 'Weekly', multiplier: 7 },
  { value: 'monthly', label: 'Monthly', multiplier: 30 },
  { value: 'quarterly', label: 'Quarterly', multiplier: 91 },
  { value: 'annual', label: 'Annual', multiplier: 365 },
];

/**
 * Extract the geography label for a site at the given hierarchy level.
 */
const getGeoLabel = (site, geoLevel) => {
  const geo = site.geography;
  switch (geoLevel) {
    case 'country':
      return geo?.country || 'Unknown';
    case 'region':
      return geo?.region || geo?.state_prov || 'Unknown';
    case 'state':
      return geo?.state_prov || 'Unknown';
    case 'site':
      return site.name || `Site ${site.id}`;
    default:
      return geo?.state_prov || site.name || `Site ${site.id}`;
  }
};

/**
 * Build S&OP aggregated Sankey data from sites + lanes.
 *
 * @param {Array} sites - Site objects with geography
 * @param {Array} lanes - Transportation lane objects
 * @param {string} geoLevel - Geography hierarchy level (country|region|state|site)
 * @param {number} timeMultiplier - Multiplier for flow values (e.g. 30 for monthly)
 */
const buildAggregatedSankeyData = (sites, lanes, geoLevel = 'state', timeMultiplier = 30) => {
  if (!sites?.length || !lanes?.length) return { nodes: [], links: [] };

  // ── 1. Build site ID → metadata map ──────────────────────────────
  const siteMap = {};
  // Normalize AWS SC master_type to display tokens used in COLUMN_ORDER/TYPE_COLORS
  const normalizeMasterType = (raw) => {
    const t = (raw || '').toUpperCase();
    if (t === 'MARKET_SUPPLY') return 'VENDOR';
    if (t === 'MARKET_DEMAND') return 'CUSTOMER';
    return t;
  };

  sites.forEach(s => {
    const masterType = normalizeMasterType(s.master_type || s.type);
    const geoLabel = getGeoLabel(s, geoLevel);
    siteMap[s.id] = { masterType, geoLabel, name: s.name };
  });

  // ── 2. Build aggregation groups (geoLabel × masterType) ──────────
  const groupKey = (masterType, geoLabel) => `${masterType}::${geoLabel}`;
  const groups = {};

  sites.forEach(s => {
    const meta = siteMap[s.id];
    if (!meta) return;
    const key = groupKey(meta.masterType, meta.geoLabel);
    if (!groups[key]) {
      groups[key] = {
        id: key,
        name: meta.geoLabel,
        type: meta.masterType,
        siteCount: 0,
        totalCapacity: 0,
      };
    }
    groups[key].siteCount += 1;
    groups[key].totalCapacity += (
      s.max_inventory ?? s.capacity ?? s.attributes?.max_inventory ?? 0
    );
  });

  // ── 3. Build aggregated links ────────────────────────────────────
  const linkMap = {};

  lanes.forEach(lane => {
    const fromId = lane.from_site_id ?? lane.source;
    const toId = lane.to_site_id ?? lane.target;
    const fromMeta = siteMap[fromId];
    const toMeta = siteMap[toId];
    if (!fromMeta || !toMeta) return;

    const fromKey = groupKey(fromMeta.masterType, fromMeta.geoLabel);
    const toKey = groupKey(toMeta.masterType, toMeta.geoLabel);
    if (fromKey === toKey) return; // skip self-loops

    const lk = `${fromKey}→${toKey}`;
    if (!linkMap[lk]) {
      linkMap[lk] = {
        source: fromKey,
        target: toKey,
        value: 0,
        laneCount: 0,
        sourceType: fromMeta.masterType,
      };
    }
    linkMap[lk].value += lane.capacity ?? lane.volume ?? lane.flow ?? 1;
    linkMap[lk].laneCount += 1;
  });

  // ── 4. Convert to arrays with time scaling ─────────────────────
  const nodes = Object.values(groups).map(g => ({
    id: g.id,
    name: g.name,
    type: g.type,
    color: TYPE_COLORS[g.type] || '#6b7280',
    siteCount: g.siteCount,
    totalCapacity: g.totalCapacity,
  }));

  const links = Object.values(linkMap).map(l => ({
    source: l.source,
    target: l.target,
    value: Math.max(l.value * timeMultiplier, 0.01),
    laneCount: l.laneCount,
    color: TYPE_COLORS[l.sourceType] || '#6b7280',
  }));

  // Build columnOrder from types actually present in the data
  const presentTypes = new Set(nodes.map(n => n.type));
  const columnOrder = COLUMN_ORDER.filter(t => presentTypes.has(t));

  return { nodes, links, columnOrder };
};

const PlanningCascadeSankey = ({ configId: configIdProp, height = 380, className }) => {
  const [sankeyData, setSankeyData] = useState(null);
  const [rawSites, setRawSites] = useState([]);
  const [rawLanes, setRawLanes] = useState([]);
  const [rawProducts, setRawProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [viewMode, setViewMode] = useState('sankey');
  const [resolvedConfigId, setResolvedConfigId] = useState(configIdProp || null);

  // Hierarchy navigation state (unified via HierarchyAggregationBar)
  const [hierarchy, setHierarchy] = useState(DEFAULT_HIERARCHY_VALUE);
  // Backward-compat aliases used by existing Sankey builder logic
  const geoLevel = hierarchy?.geo?.level === 'all' ? 'state' : hierarchy?.geo?.level || 'state';
  const productCategory = hierarchy?.product?.categoryKey || 'all';
  const timeBucket = 'monthly';

  // Auto-resolve configId: if none passed, pick the first available config
  useEffect(() => {
    if (configIdProp) {
      setResolvedConfigId(configIdProp);
      return;
    }
    let cancelled = false;
    const resolveConfig = async () => {
      try {
        const configs = await getSupplyChainConfigs();
        if (!cancelled && Array.isArray(configs) && configs.length > 0) {
          setResolvedConfigId(configs[0].id);
        } else if (!cancelled) {
          setLoading(false);
          setError('no_config');
        }
      } catch {
        if (!cancelled) {
          setLoading(false);
          setError('no_config');
        }
      }
    };
    resolveConfig();
    return () => { cancelled = true; };
  }, [configIdProp]);

  // Load SC config data from DB
  useEffect(() => {
    if (!resolvedConfigId) return;

    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [sitesData, lanesData, productsData] = await Promise.all([
          getSites(resolvedConfigId),
          getLanes(resolvedConfigId),
          getProducts(resolvedConfigId),
        ]);
        if (cancelled) return;
        const sitesArr = Array.isArray(sitesData) ? sitesData : [];
        const lanesArr = Array.isArray(lanesData) ? lanesData : [];
        const productsArr = Array.isArray(productsData) ? productsData : [];
        setRawSites(sitesArr);
        setRawLanes(lanesArr);
        setRawProducts(productsArr);
      } catch {
        if (!cancelled) {
          setError('load_error');
          setRawSites([]);
          setRawLanes([]);
          setRawProducts([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [resolvedConfigId]);

  // Extract unique product categories from loaded products
  const productCategories = useMemo(() => {
    const cats = new Set();
    rawProducts.forEach(p => {
      if (p.category) cats.add(p.category);
    });
    return Array.from(cats).sort();
  }, [rawProducts]);

  // Compute time multiplier
  const timeMultiplier = useMemo(() => {
    const bucket = TIME_BUCKETS.find(b => b.value === timeBucket);
    return bucket ? bucket.multiplier : 30;
  }, [timeBucket]);

  // Recompute Sankey data whenever hierarchy selections or raw data change
  useEffect(() => {
    if (rawSites.length === 0 || rawLanes.length === 0) {
      if (!loading && !error) {
        setError('no_data');
      }
      return;
    }

    // Product category filtering: if a category is selected and products have
    // category data, we could filter sites. For now, product filter acts as
    // a display label since lanes don't carry product-level data.
    // Future: filter lanes by product when product-lane mapping exists.

    const aggregated = buildAggregatedSankeyData(rawSites, rawLanes, geoLevel, timeMultiplier);
    if (aggregated.nodes.length > 0 && aggregated.links.length > 0) {
      setSankeyData(aggregated);
      setError(null);
    } else {
      setSankeyData(null);
      setError('no_data');
    }
  }, [rawSites, rawLanes, geoLevel, timeMultiplier, loading, error]);

  // Subtitle updates with current hierarchy context
  const subtitle = useMemo(() => {
    const geoLabel = GEO_LEVELS.find(g => g.value === geoLevel)?.label || 'State';
    const timeLabel = TIME_BUCKETS.find(t => t.value === timeBucket)?.label || 'Monthly';
    const productLabel = productCategory === 'all' ? 'All Products' : productCategory;
    return `${timeLabel} flow by ${geoLabel.toLowerCase()} × site type · ${productLabel}`;
  }, [geoLevel, timeBucket, productCategory]);

  const nodeTooltipFn = useCallback((node) => (
    <span>{node.name} ({node.siteCount ?? '?'} sites)</span>
  ), []);

  const linkTooltipFn = useCallback((link) => {
    const timeLabel = TIME_BUCKETS.find(t => t.value === timeBucket)?.label || 'Monthly';
    return (
      <span>
        {link.source?.name || '?'} → {link.target?.name || '?'}
        : {link.value?.toLocaleString()} units/{timeLabel.toLowerCase()} ({link.laneCount ?? '?'} lanes)
      </span>
    );
  }, [timeBucket]);

  // Build map data from raw sites/lanes
  const mapData = useMemo(() => {
    const sitesWithCoords = rawSites.filter(
      (s) => s.geography?.latitude && s.geography?.longitude
    );
    if (sitesWithCoords.length === 0) return null;

    const mapSites = rawSites.map((site) => {
      const attrs = typeof site.attributes === 'object' && site.attributes ? site.attributes : {};
      return {
        id: site.id,
        name: site.name,
        role: site.type || site.dag_type || site.master_type,
        master_type: site.master_type || site.dag_type,
        latitude: site.geography?.latitude,
        longitude: site.geography?.longitude,
        location: site.geography
          ? [site.geography.city, site.geography.state_prov, site.geography.country]
              .filter(Boolean)
              .join(', ')
          : null,
        attributes: attrs,
      };
    });

    const mapEdges = rawLanes.map((lane) => ({
      from: lane.from_site_id,
      to: lane.to_site_id,
    }));

    // Build color map from TYPE_COLORS
    const siteTypeColorMap = {};
    rawSites.forEach((site) => {
      const role = site.type || site.dag_type || site.master_type;
      if (!role) return;
      const key = role.toLowerCase().replace(/[\s-]+/g, '_');
      if (!siteTypeColorMap[key]) {
        const upperKey = key.toUpperCase();
        siteTypeColorMap[key] = TYPE_COLORS[upperKey] || '#6b7280';
      }
    });

    return { sites: mapSites, edges: mapEdges, siteTypeColors: siteTypeColorMap };
  }, [rawSites, rawLanes]);

  const renderContent = () => {
    if (loading) {
      return (
        <div className="flex items-center justify-center" style={{ height }}>
          <Spinner size="md" />
        </div>
      );
    }

    if (error) {
      const message = error === 'no_config'
        ? 'No supply chain configuration available. Create one in Administration > Supply Chain Configs.'
        : error === 'no_data'
        ? 'No sites or lanes found in the supply chain configuration.'
        : 'Unable to load supply chain data.';
      return (
        <div className="flex items-center justify-center" style={{ height }}>
          <p className="text-sm text-center text-muted-foreground">{message}</p>
        </div>
      );
    }

    if (viewMode === 'sankey' && sankeyData) {
      return (
        <>
          <SankeyDiagram
            nodes={sankeyData.nodes}
            links={sankeyData.links}
            height={height}
            nodeWidth={14}
            nodePadding={16}
            align="justify"
            columnOrder={sankeyData.columnOrder || COLUMN_ORDER}
            nodeTooltip={nodeTooltipFn}
            linkTooltip={linkTooltipFn}
            defaultLinkOpacity={0.45}
            nodeCornerRadius={4}
          />
          <SankeyMetricLegend orientation="row" justify="center" className="mt-2" />
        </>
      );
    }

    if (viewMode === 'map') {
      return (
        <div style={{ height }} className="w-full">
          {mapData ? (
            <GeospatialSupplyChain
              sites={mapData.sites}
              edges={mapData.edges}
              inventoryData={{}}
              activeFlows={[]}
              siteTypeColors={mapData.siteTypeColors}
            />
          ) : (
            <div className="h-full flex items-center justify-center">
              <p className="text-sm text-center text-muted-foreground">
                No geographic coordinates available. Add latitude/longitude data to your sites
                via the Geography table to enable the map view.
              </p>
            </div>
          )}
        </div>
      );
    }

    return null;
  };

  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <CardTitle className="text-lg flex items-center gap-2">
              <Network className="h-5 w-5 shrink-0" />
              Supply Chain Flow
            </CardTitle>
            <p className="text-sm text-muted-foreground truncate">
              {subtitle}
            </p>
          </div>
          {!error && (
            <div className="flex items-center gap-2 shrink-0">
              <ToggleGroup
                type="single"
                size="sm"
                value={viewMode}
                onValueChange={(val) => val && setViewMode(val)}
              >
                <ToggleGroupItem value="sankey">Sankey</ToggleGroupItem>
                <ToggleGroupItem value="map">Map</ToggleGroupItem>
              </ToggleGroup>
            </div>
          )}
        </div>
      </CardHeader>
      <CardContent className="px-2 pb-2">
        <HierarchyAggregationBar
          sites={rawSites}
          products={rawProducts}
          value={hierarchy}
          onChange={setHierarchy}
        />
        {renderContent()}
      </CardContent>
    </Card>
  );
};

export default PlanningCascadeSankey;
