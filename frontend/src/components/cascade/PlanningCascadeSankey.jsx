/**
 * Supply Chain Sankey – Executive Dashboard (S&OP Aggregation Level)
 *
 * Shows the supply chain network at one level below the top of the
 * geography and product hierarchies — the same aggregation level used
 * by the GraphSAGE S&OP model.
 *
 * Nodes = sites grouped by region × master type
 * Links = material flow between groups (sized by volume)
 *
 * Features:
 *   - Sankey Flow / Map View toggle
 *   - Auto-loads first available SC config when no configId prop
 *   - SankeyMetricLegend shown in Sankey mode
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
} from '../common';
import { Network } from 'lucide-react';
import SankeyDiagram from '../charts/SankeyDiagram';
import SankeyMetricLegend from '../charts/SankeyMetricLegend';
import GeospatialSupplyChain from '../visualization/GeospatialSupplyChain';
import { getSupplyChainConfigs, getSites, getLanes } from '../../services/supplyChainConfigService';

// Column order: upstream (supply) → downstream (demand)
const COLUMN_ORDER = [
  'MARKET_SUPPLY',
  'INVENTORY',
  'MANUFACTURER',
  'DISTRIBUTOR',
  'WHOLESALER',
  'RETAILER',
  'MARKET_DEMAND',
];

// Site type colors (consistent with SupplyChainConfigSankey)
const TYPE_COLORS = {
  MARKET_SUPPLY: '#8b5cf6',   // violet
  INVENTORY: '#0ea5e9',       // sky blue
  MANUFACTURER: '#0891b2',    // cyan
  DISTRIBUTOR: '#f59e0b',     // amber
  WHOLESALER: '#f97316',      // orange
  RETAILER: '#3b82f6',        // blue
  MARKET_DEMAND: '#ef4444',   // red
};

/**
 * Build S&OP aggregated Sankey data from sites + lanes.
 *
 * Aggregation:
 *   - Geography: Group by region (one level below company root)
 *   - Master type: Group by MARKET_SUPPLY | MANUFACTURER | DISTRIBUTOR | RETAILER | MARKET_DEMAND
 *   - Each (region, master_type) becomes one Sankey node
 *   - Flow between node-groups is summed across individual lanes
 */
const buildAggregatedSankeyData = (sites, lanes) => {
  if (!sites?.length || !lanes?.length) return { nodes: [], links: [] };

  // ── 1. Build site ID → metadata map ──────────────────────────────
  const siteMap = {};
  sites.forEach(s => {
    const masterType = (s.master_type || s.type || '').toUpperCase();
    // Region = first hierarchy tag, or site name as fallback
    const region = s.region
      || s.hierarchy_path?.split('/')?.slice(1, 2)?.[0]
      || s.name
      || `Site ${s.id}`;
    siteMap[s.id] = { masterType, region, name: s.name };
  });

  // ── 2. Build aggregation groups (region × masterType) ────────────
  const groupKey = (masterType, region) => `${masterType}::${region}`;
  const groups = {};

  sites.forEach(s => {
    const meta = siteMap[s.id];
    if (!meta) return;
    const key = groupKey(meta.masterType, meta.region);
    if (!groups[key]) {
      groups[key] = {
        id: key,
        name: meta.region,
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

    const fromKey = groupKey(fromMeta.masterType, fromMeta.region);
    const toKey = groupKey(toMeta.masterType, toMeta.region);
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

  // ── 4. Convert to arrays ─────────────────────────────────────────
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
    value: Math.max(l.value, 0.01),
    laneCount: l.laneCount,
    color: TYPE_COLORS[l.sourceType] || '#6b7280',
  }));

  // Build columnOrder from types actually present in the data
  const presentTypes = new Set(nodes.map(n => n.type));
  const columnOrder = COLUMN_ORDER.filter(t => presentTypes.has(t));

  return { nodes, links, columnOrder };
};

// ── Default demo data (Food Dist network: Suppliers → 1 DC → Customers by region) ──
const DEFAULT_SANKEY_DATA = {
  nodes: [
    { id: 'ms-suppliers', name: 'Suppliers', type: 'MARKET_SUPPLY', color: TYPE_COLORS.MARKET_SUPPLY, siteCount: 10 },
    { id: 'dc-fooddist',  name: 'FoodDist DC', type: 'INVENTORY', color: TYPE_COLORS.INVENTORY, siteCount: 1 },
    { id: 'md-oregon',    name: 'Oregon', type: 'MARKET_DEMAND', color: TYPE_COLORS.MARKET_DEMAND, siteCount: 3 },
    { id: 'md-washington', name: 'Washington', type: 'MARKET_DEMAND', color: TYPE_COLORS.MARKET_DEMAND, siteCount: 3 },
    { id: 'md-california', name: 'California', type: 'MARKET_DEMAND', color: TYPE_COLORS.MARKET_DEMAND, siteCount: 4 },
    { id: 'md-arizona',   name: 'Arizona', type: 'MARKET_DEMAND', color: TYPE_COLORS.MARKET_DEMAND, siteCount: 3 },
  ],
  links: [
    { source: 'ms-suppliers', target: 'dc-fooddist', value: 7000, laneCount: 10, color: TYPE_COLORS.MARKET_SUPPLY },
    { source: 'dc-fooddist',  target: 'md-oregon',     value: 1800, laneCount: 3, color: TYPE_COLORS.INVENTORY },
    { source: 'dc-fooddist',  target: 'md-washington',  value: 1800, laneCount: 3, color: TYPE_COLORS.INVENTORY },
    { source: 'dc-fooddist',  target: 'md-california',  value: 2200, laneCount: 4, color: TYPE_COLORS.INVENTORY },
    { source: 'dc-fooddist',  target: 'md-arizona',     value: 1200, laneCount: 3, color: TYPE_COLORS.INVENTORY },
  ],
  columnOrder: ['MARKET_SUPPLY', 'INVENTORY', 'MARKET_DEMAND'],
};

const PlanningCascadeSankey = ({ configId: configIdProp, height = 280, className }) => {
  const [sankeyData, setSankeyData] = useState(null);
  const [rawSites, setRawSites] = useState([]);
  const [rawLanes, setRawLanes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [viewMode, setViewMode] = useState('sankey');
  const [resolvedConfigId, setResolvedConfigId] = useState(configIdProp || null);

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
        }
      } catch {
        // Silently fall back to defaults
      }
    };
    resolveConfig();
    return () => { cancelled = true; };
  }, [configIdProp]);

  // Load real SC config data; fall back to defaults
  useEffect(() => {
    if (!resolvedConfigId) {
      setSankeyData(DEFAULT_SANKEY_DATA);
      return;
    }

    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        const [sitesData, lanesData] = await Promise.all([
          getSites(resolvedConfigId),
          getLanes(resolvedConfigId),
        ]);
        if (cancelled) return;
        const sitesArr = Array.isArray(sitesData) ? sitesData : [];
        const lanesArr = Array.isArray(lanesData) ? lanesData : [];
        setRawSites(sitesArr);
        setRawLanes(lanesArr);
        const aggregated = buildAggregatedSankeyData(sitesArr, lanesArr);
        setSankeyData(
          aggregated.nodes.length > 0 && aggregated.links.length > 0
            ? aggregated
            : DEFAULT_SANKEY_DATA
        );
      } catch {
        if (!cancelled) {
          setSankeyData(DEFAULT_SANKEY_DATA);
          setRawSites([]);
          setRawLanes([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [resolvedConfigId]);

  const data = sankeyData || DEFAULT_SANKEY_DATA;

  const nodeTooltipFn = useCallback((node) => (
    <span>{node.name} ({node.siteCount ?? '?'} sites)</span>
  ), []);

  const linkTooltipFn = useCallback((link) => (
    <span>
      {link.source?.name || '?'} → {link.target?.name || '?'}
      : {link.value?.toLocaleString()} units ({link.laneCount ?? '?'} lanes)
    </span>
  ), []);

  // Build map data from raw sites/lanes
  const mapData = useMemo(() => {
    const sitesWithCoords = rawSites.filter(
      (s) => s.geography?.latitude && s.geography?.longitude
    );
    if (sitesWithCoords.length === 0) return null;

    const mapSites = rawSites.map((site) => ({
      id: site.id,
      name: site.name,
      role: site.type || site.dag_type || site.master_type,
      latitude: site.geography?.latitude,
      longitude: site.geography?.longitude,
      location: site.geography
        ? [site.geography.city, site.geography.state_prov, site.geography.country]
            .filter(Boolean)
            .join(', ')
        : null,
    }));

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

  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-lg flex items-center gap-2">
              <Network className="h-5 w-5" />
              Supply Chain Flow
            </CardTitle>
            <p className="text-sm text-muted-foreground">
              Material flow at S&OP aggregation level (region × site type)
            </p>
          </div>
          <ToggleGroup
            type="single"
            size="sm"
            value={viewMode}
            onValueChange={(val) => val && setViewMode(val)}
          >
            <ToggleGroupItem value="sankey">Sankey Flow</ToggleGroupItem>
            <ToggleGroupItem value="map">Map View</ToggleGroupItem>
          </ToggleGroup>
        </div>
      </CardHeader>
      <CardContent className="px-2 pb-2">
        {loading ? (
          <div className="flex items-center justify-center" style={{ height }}>
            <Spinner size="md" />
          </div>
        ) : viewMode === 'sankey' ? (
          <>
            <SankeyDiagram
              nodes={data.nodes}
              links={data.links}
              height={height}
              nodeWidth={14}
              nodePadding={28}
              align="justify"
              columnOrder={data.columnOrder || COLUMN_ORDER}
              nodeTooltip={nodeTooltipFn}
              linkTooltip={linkTooltipFn}
              defaultLinkOpacity={0.45}
              nodeCornerRadius={4}
            />
            <SankeyMetricLegend orientation="row" justify="center" className="mt-2" />
          </>
        ) : (
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
        )}
      </CardContent>
    </Card>
  );
};

export default PlanningCascadeSankey;
