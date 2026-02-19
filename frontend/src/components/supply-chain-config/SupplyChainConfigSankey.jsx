import React, { useCallback, useEffect, useMemo, useState } from 'react';
import PropTypes from 'prop-types';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Spinner,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
  ToggleGroup,
  ToggleGroupItem,
} from '../common';
import {
  getSupplyChainConfigById,
  getSupplyChainConfigs,
  DEFAULT_SITE_TYPE_DEFINITIONS,
  sortSiteTypeDefinitions,
  buildSiteTypeLabelMap,
  getProducts, // AWS SC DM compliant (was getItems)
  getSites,
  getLanes,
  getProductSiteConfigs, // AWS SC terminology (was getItemNodeConfigs)
} from '../../services/supplyChainConfigService';
import SankeyDiagram from '../charts/SankeyDiagram';
import SankeyMetricLegend from '../charts/SankeyMetricLegend';
import GeospatialSupplyChain from '../visualization/GeospatialSupplyChain';

const MARKET_DEMAND_TYPE = 'MARKET_DEMAND';
const MARKET_SUPPLY_TYPE = 'MARKET_SUPPLY';

const canonicalizeTypeKey = (value) => {
  if (value === undefined || value === null) {
    return '';
  }
  return String(value)
    .trim()
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '');
};

const normalizeTypeToken = (value) => {
  const canonical = canonicalizeTypeKey(value);
  return canonical ? canonical.toUpperCase() : '';
};

const MIN_LINK_VALUE = 1e-4;

const LEAD_COLOR_MIN = '#16a34a';
const LEAD_COLOR_MEDIAN = '#f97316';
const LEAD_COLOR_MAX = '#dc2626';

const hexToRgbChannels = (hex) => {
  if (typeof hex !== 'string') return null;
  let normalized = hex.trim();
  if (!normalized.startsWith('#')) return null;
  normalized = normalized.slice(1);
  if (normalized.length === 3) {
    normalized = normalized
      .split('')
      .map((char) => `${char}${char}`)
      .join('');
  }
  if (normalized.length !== 6) {
    return null;
  }
  const value = Number.parseInt(normalized, 16);
  if (Number.isNaN(value)) {
    return null;
  }
  return {
    r: (value >> 16) & 255,
    g: (value >> 8) & 255,
    b: value & 255,
  };
};

const interpolateChannel = (start, end, t) => Math.round(start + (end - start) * t);

const interpolateHex = (startColor, endColor, t) => {
  const start = hexToRgbChannels(startColor);
  const end = hexToRgbChannels(endColor);
  if (!start || !end) {
    return startColor;
  }
  const clamped = Math.max(0, Math.min(1, t));
  const r = interpolateChannel(start.r, end.r, clamped);
  const g = interpolateChannel(start.g, end.g, clamped);
  const b = interpolateChannel(start.b, end.b, clamped);
  return `rgb(${r}, ${g}, ${b})`;
};

const computeMedian = (values) => {
  if (!Array.isArray(values) || values.length === 0) {
    return 0;
  }
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 0) {
    return (sorted[mid - 1] + sorted[mid]) / 2;
  }
  return sorted[mid];
};

const extractLeadTime = (lane) => {
  if (!lane || typeof lane !== 'object') {
    return null;
  }

  const candidates = [
    lane.demand_lead_time,
    lane.supply_lead_time,
    lane.lead_time,
    lane.leadTime,
    lane.transit_time,
  ];

  const legacy = lane.lead_time_days;
  if (legacy && typeof legacy === 'object') {
    candidates.push(legacy.avg);
    candidates.push(legacy.mean);
    candidates.push(legacy.median);
    candidates.push(legacy.min);
    candidates.push(legacy.max);
  }

  for (const candidate of candidates) {
    if (candidate === undefined || candidate === null) {
      continue;
    }
    if (typeof candidate === 'number') {
      if (Number.isFinite(candidate)) {
        return candidate;
      }
      continue;
    }
    if (typeof candidate === 'object') {
      const deterministic = candidate?.value ?? candidate?.deterministic ?? null;
      if (Number.isFinite(Number(deterministic))) {
        return Number(deterministic);
      }
    }
    const numeric = Number(candidate);
    if (Number.isFinite(numeric)) {
      return numeric;
    }
  }

  return null;
};

const resolveLeadTimeColor = (leadTime, stats) => {
  if (!stats || !Number.isFinite(leadTime)) {
    return LEAD_COLOR_MIN;
  }
  const { min, median, max } = stats;
  if (!Number.isFinite(min) || !Number.isFinite(median) || !Number.isFinite(max)) {
    return LEAD_COLOR_MIN;
  }
  if (max - min <= 0) {
    return LEAD_COLOR_MIN;
  }
  if (leadTime <= median) {
    const range = Math.max(median - min, 1e-9);
    const t = (leadTime - min) / range;
    return interpolateHex(LEAD_COLOR_MIN, LEAD_COLOR_MEDIAN, t);
  }
  const upperRange = Math.max(max - median, 1e-9);
  const t = (leadTime - median) / upperRange;
  return interpolateHex(LEAD_COLOR_MEDIAN, LEAD_COLOR_MAX, Math.min(Math.max(t, 0), 1));
};

const formatSiteTypeLabel = (type) =>
  String(type || '')
    .replace(/_/g, ' ')
    .replace(/\b([a-z])/gi, (match) => match.toUpperCase());

const DEFAULT_SANKEY_HEIGHT = 420;

const isAggregatedInputNode = (node) =>
  node?.isAggregated === true ||
  node?.is_aggregated === true ||
  node?.aggregated === true ||
  node?.is_summary === true ||
  node?.summary === true;

// Tailwind color palette for D3 visualization (replacing MUI theme)
const SANKEY_COLORS = {
  primary: { light: '#93c5fd', main: '#3b82f6', dark: '#1d4ed8' },
  secondary: { main: '#8b5cf6', dark: '#6d28d9' },
  success: { main: '#22c55e', dark: '#15803d' },
  warning: { main: '#f59e0b', dark: '#b45309' },
  info: { main: '#06b6d4', dark: '#0e7490' },
  error: { main: '#ef4444', dark: '#b91c1c' },
  grey: { 500: '#6b7280', 700: '#374151' },
  text: { secondary: '#6b7280' },
};

const SupplyChainConfigSankey = ({ restrictToGroupId = null }) => {
  const [configOptions, setConfigOptions] = useState([]);
  const [selectedConfigId, setSelectedConfigId] = useState(null);
  const [configsLoading, setConfigsLoading] = useState(true);
  const [configsError, setConfigsError] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(null);
  const [configDetail, setConfigDetail] = useState(null);
  const [products, setProducts] = useState([]); // AWS SC DM: Product (not Item)
  const [sites, setSites] = useState([]); // AWS SC DM: Site (not Node)
  const [lanes, setLanes] = useState([]);
  const [productSiteConfigs, setProductSiteConfigs] = useState([]); // AWS SC DM: ProductSiteConfig
  const [activeTab, setActiveTab] = useState('diagram');
  const [sankeyScaleMode, setSankeyScaleMode] = useState('flow');
  const [viewMode, setViewMode] = useState('sankey'); // 'sankey' or 'map'
  const forwardStroke = SANKEY_COLORS.text.secondary;
  const returnStroke = SANKEY_COLORS.grey[500];

  const siteTypeDefinitions = useMemo(
    () =>
      sortSiteTypeDefinitions(
        configDetail?.site_type_definitions || DEFAULT_SITE_TYPE_DEFINITIONS
      ),
    [configDetail?.site_type_definitions]
  );

  const siteTypeLabelMap = useMemo(
    () => buildSiteTypeLabelMap(siteTypeDefinitions),
    [siteTypeDefinitions]
  );

  const { dagDefinitionOrderMap, descendingDefinitionTokens } = useMemo(() => {
    const map = new Map();
    const orderedTokens = [];
    sortSiteTypeDefinitions(siteTypeDefinitions).forEach((definition, index) => {
      const orderValue = Number.isFinite(definition?.order) ? definition.order : index;
      const candidateTokens = new Set([
        definition?.type,
        definition?.label,
        definition?.group_type,
        definition?.groupType,
      ]);
      candidateTokens.forEach((token) => {
        const normalized = normalizeTypeToken(token);
        if (!normalized || map.has(normalized)) {
          return;
        }
        map.set(normalized, orderValue);
        orderedTokens.push(normalized);
      });
    });

    const sortedTokens = [...orderedTokens].sort((a, b) => {
      const orderA = Number.isFinite(map.get(a)) ? map.get(a) : -Infinity;
      const orderB = Number.isFinite(map.get(b)) ? map.get(b) : -Infinity;
      if (orderA !== orderB) {
        return orderB - orderA;
      }
      return a.localeCompare(b);
    });

    return {
      dagDefinitionOrderMap: map,
      descendingDefinitionTokens: sortedTokens,
    };
  }, [siteTypeDefinitions]);

  const applyDescendingDagDisplayOrder = useCallback(
    (tokens = []) => {
      if (!Array.isArray(tokens)) {
        return descendingDefinitionTokens;
      }
      const seen = new Set();
      const enriched = [];
      tokens.forEach((token, index) => {
        const normalized = normalizeTypeToken(token);
        if (!normalized || seen.has(normalized)) {
          return;
        }
        seen.add(normalized);
        const orderValue = dagDefinitionOrderMap.has(normalized)
          ? dagDefinitionOrderMap.get(normalized)
          : null;
        enriched.push({
          token: normalized,
          order: Number.isFinite(orderValue) ? orderValue : null,
          fallbackIndex: index,
        });
      });

      if (!enriched.length) {
        return descendingDefinitionTokens;
      }

      enriched.sort((a, b) => {
        if (Number.isFinite(a.order) && Number.isFinite(b.order) && a.order !== b.order) {
          return b.order - a.order;
        }
        if (Number.isFinite(a.order)) return -1;
        if (Number.isFinite(b.order)) return 1;
        return a.fallbackIndex - b.fallbackIndex;
      });

      return enriched.map((entry) => entry.token);
    },
    [dagDefinitionOrderMap, descendingDefinitionTokens]
  );

  const resolveSiteTypeToken = useCallback((site) => {
    if (!site) return '';
    const dagType = normalizeTypeToken(site.dag_type || site.dagType);
    if (dagType) return dagType;
    const explicitType = normalizeTypeToken(site.type || site.site_type || site.node_type);
    if (explicitType) return explicitType;
    const masterType = normalizeTypeToken(site.master_type || site.masterType);
    if (masterType) return masterType;
    return '';
  }, []);

  const typeOrder = useMemo(() => {
    const siteLookup = new Map();
    (Array.isArray(sites) ? sites : []).forEach((site) => {
      siteLookup.set(String(site.id ?? site.site_id ?? site.node_id), site);
    });

    const edges = [];
    const tokenSet = new Set();
    (Array.isArray(lanes) ? lanes : []).forEach((lane) => {
      const upstreamId = lane.from_site_id;
      const downstreamId = lane.to_site_id;
      const upstreamSite = siteLookup.get(String(upstreamId));
      const downstreamSite = siteLookup.get(String(downstreamId));
      const upstreamType = resolveSiteTypeToken(upstreamSite);
      const downstreamType = resolveSiteTypeToken(downstreamSite);
      if (!upstreamType || !downstreamType) {
        return;
      }
      const normalizedUpstream = normalizeTypeToken(upstreamType);
      const normalizedDownstream = normalizeTypeToken(downstreamType);
      if (!normalizedUpstream || !normalizedDownstream) {
        return;
      }
      tokenSet.add(normalizedUpstream);
      tokenSet.add(normalizedDownstream);
      if (normalizedUpstream !== normalizedDownstream) {
        edges.push([normalizedUpstream, normalizedDownstream]);
      }
    });

    if (tokenSet.size && descendingDefinitionTokens.length) {
      const missing = [...tokenSet].filter((token) => !dagDefinitionOrderMap.has(token));
      if (missing.length === 0) {
        const subset = descendingDefinitionTokens.filter((token) => tokenSet.has(token));
        if (subset.length) {
          return subset;
        }
      }
    }

    if (edges.length) {
      const adjacency = new Map();
      const inDegree = new Map();
      tokenSet.forEach((token) => {
        adjacency.set(token, new Set());
        inDegree.set(token, 0);
      });

      edges.forEach(([source, target]) => {
        const targets = adjacency.get(source);
        if (!targets.has(target)) {
          targets.add(target);
          inDegree.set(target, (inDegree.get(target) ?? 0) + 1);
        }
      });

      const queue = [];
      const enqueueIfRoot = (token) => {
        if ((inDegree.get(token) ?? 0) === 0) {
          queue.push(token);
        }
      };
      tokenSet.forEach(enqueueIfRoot);

      const sortQueue = () => {
        if (queue.length <= 1) return;
        queue.sort((a, b) => {
          const defA = dagDefinitionOrderMap.has(a) ? dagDefinitionOrderMap.get(a) : Infinity;
          const defB = dagDefinitionOrderMap.has(b) ? dagDefinitionOrderMap.get(b) : Infinity;
          if (defA !== defB) {
            return defA - defB;
          }
          return a.localeCompare(b);
        });
      };
      sortQueue();

      const topoOrder = [];
      while (queue.length) {
        const current = queue.shift();
        topoOrder.push(current);
        adjacency.get(current)?.forEach((neighbor) => {
          const updated = (inDegree.get(neighbor) ?? 0) - 1;
          inDegree.set(neighbor, updated);
          if (updated === 0) {
            queue.push(neighbor);
            sortQueue();
          }
        });
      }

      if (topoOrder.length === tokenSet.size) {
        return applyDescendingDagDisplayOrder(topoOrder);
      }
    }

    const fallbackTokens = [
      ...descendingDefinitionTokens,
      ...Array.from(tokenSet.values()),
    ];
    return applyDescendingDagDisplayOrder(fallbackTokens);
  }, [
    applyDescendingDagDisplayOrder,
    dagDefinitionOrderMap,
    descendingDefinitionTokens,
    lanes,
    sites,
    resolveSiteTypeToken,
  ]);

  const siteTypeOrderMap = useMemo(() => {
    const map = {};
    typeOrder.forEach((token, index) => {
      const key = normalizeTypeToken(token);
      if (key) {
        map[key] = index;
      }
    });
    return map;
  }, [typeOrder]);

  const getTypeOrderIndex = useCallback(
    (type) => {
      const normalizedDefinitionOrder = dagDefinitionOrderMap.get(normalizeTypeToken(type));
      if (Number.isFinite(normalizedDefinitionOrder)) {
        return normalizedDefinitionOrder;
      }
      const normalized = normalizeTypeToken(type);
      if (Object.prototype.hasOwnProperty.call(siteTypeOrderMap, normalized)) {
        return siteTypeOrderMap[normalized];
      }
      return typeOrder.length;
    },
    [dagDefinitionOrderMap, siteTypeOrderMap, typeOrder]
  );

  const getTypeLabel = useCallback(
    (type) => {
      const canonical = canonicalizeTypeKey(type);
      if (canonical && siteTypeLabelMap[canonical]) {
        return siteTypeLabelMap[canonical];
      }
      if (typeof type === 'string' && type.trim()) {
        return formatSiteTypeLabel(type);
      }
      return 'Unspecified';
    },
    [siteTypeLabelMap]
  );

  const fetchConfigs = useCallback(async () => {
    try {
      setConfigsLoading(true);
      const data = await getSupplyChainConfigs();
      const targetGroupId =
        restrictToGroupId !== null && restrictToGroupId !== undefined
          ? String(restrictToGroupId)
          : null;

      const filtered = Array.isArray(data)
        ? data.filter((cfg) => {
            if (targetGroupId === null) return true;
            if (cfg?.group_id === undefined || cfg?.group_id === null) {
              return false;
            }
            return String(cfg.group_id) === targetGroupId;
          })
        : [];

      setConfigOptions(filtered);
      setConfigsError(null);
      if (filtered.length > 0) {
        setSelectedConfigId((current) => current ?? filtered[0]?.id ?? null);
      } else {
        setSelectedConfigId(null);
      }
    } catch (error) {
      console.error('Failed to load supply chain configs for Sankey diagram', error);
      setConfigOptions([]);
      setConfigsError('Unable to load supply chain configurations.');
      setSelectedConfigId(null);
    } finally {
      setConfigsLoading(false);
    }
  }, [restrictToGroupId]);

  useEffect(() => {
    fetchConfigs();
  }, [fetchConfigs]);

  useEffect(() => {
    if (!selectedConfigId) {
      setConfigDetail(null);
      return;
    }

    let ignore = false;
    const loadDetails = async () => {
      try {
        setDetailLoading(true);
        const [detail, productsData, sitesData, lanesData, pscData] = await Promise.all([
          getSupplyChainConfigById(selectedConfigId),
          getProducts(selectedConfigId), // AWS SC DM: Product
          getSites(selectedConfigId), // AWS SC DM: Site (was getNodes)
          getLanes(selectedConfigId),
          getProductSiteConfigs(selectedConfigId),
        ]);
        if (!ignore) {
          setConfigDetail(detail);
          setProducts(Array.isArray(productsData) ? productsData : []);
          setSites(Array.isArray(sitesData) ? sitesData : []);
          setLanes(Array.isArray(lanesData) ? lanesData : []);
          setProductSiteConfigs(Array.isArray(pscData) ? pscData : []);
          setDetailError(null);
          setActiveTab('diagram');
        }
      } catch (error) {
        console.error('Failed to load supply chain config detail for Sankey diagram', error);
        if (!ignore) {
          setConfigDetail(null);
          setProducts([]);
          setSites([]);
          setLanes([]);
          setProductSiteConfigs([]);
          setDetailError('Unable to load the configuration details right now.');
        }
      } finally {
        if (!ignore) {
          setDetailLoading(false);
        }
      }
    };

    loadDetails();

    return () => {
      ignore = true;
    };
  }, [selectedConfigId]);

  const quantityFormatter = useMemo(
    () => new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }),
    []
  );

  const typeStyles = useMemo(
    () => ({
      SUPPLIER: {
        fill: SANKEY_COLORS.primary.light,
        stroke: SANKEY_COLORS.primary.main,
        renderer: 'roundedRect',
      },
      MARKET_SUPPLY: {
        fill: SANKEY_COLORS.primary.main,
        stroke: SANKEY_COLORS.primary.dark,
        renderer: 'roundedRect',
      },
      MANUFACTURER: {
        fill: SANKEY_COLORS.success.main,
        stroke: SANKEY_COLORS.success.dark,
        renderer: 'rect',
      },
      DISTRIBUTOR: {
        fill: SANKEY_COLORS.warning.main,
        stroke: SANKEY_COLORS.warning.dark,
        renderer: 'parallelogram',
      },
      WHOLESALER: {
        fill: SANKEY_COLORS.info.main,
        stroke: SANKEY_COLORS.info.dark,
        renderer: 'ellipse',
      },
      RETAILER: {
        fill: SANKEY_COLORS.secondary.main,
        stroke: SANKEY_COLORS.secondary.dark,
        renderer: 'pill',
      },
      MARKET_DEMAND: {
        fill: SANKEY_COLORS.error.main,
        stroke: SANKEY_COLORS.error.dark,
        renderer: 'diamond',
      },
      DEFAULT: {
        fill: SANKEY_COLORS.grey[500],
        stroke: SANKEY_COLORS.grey[700],
        renderer: 'rect',
      },
    }),
    []
  );

  const extractArray = useCallback((value) => {
    if (!value) return [];
    if (Array.isArray(value)) return value;
    return [];
  }, []);

  const extractSites = useCallback(
    (config) => {
      if (!config) return [];

      const candidateCollections = [];

      const collectFrom = (candidate) => {
        if (!candidate || typeof candidate !== 'object') return;

        // AWS SC DM: sites is canonical
        candidateCollections.push(
          candidate.sites,
          candidate.structure?.sites,
          candidate.structure?.graph?.sites,
          candidate.graph?.sites
        );

        if (candidate.structure?.layers) {
          candidateCollections.push(
            candidate.structure.layers.flatMap((layer) => extractArray(layer?.sites))
          );
        }

        if (candidate.structure?.sites_by_type && typeof candidate.structure.sites_by_type === 'object') {
          candidateCollections.push(
            Object.values(candidate.structure.sites_by_type).flatMap((collection) =>
              extractArray(collection)
            )
          );
        }
        if (candidate.structure && typeof candidate.structure === 'object') {
          Object.entries(candidate.structure).forEach(([key, value]) => {
            if (key && key.toLowerCase().endsWith('_sites')) {
              candidateCollections.push(extractArray(value));
            }
          });
        }

        if (Array.isArray(candidate.structure?.site_templates)) {
          candidateCollections.push(candidate.structure.site_templates);
        }
        if (Array.isArray(candidate.structure?.node_templates)) {
          candidateCollections.push(candidate.structure.node_templates);
        }
      };

      collectFrom(config);
      if (config?.config && config.config !== config) {
        collectFrom(config.config);
      }

      const flattened = candidateCollections
        .flatMap((collection) => extractArray(collection))
        .filter(Boolean);

      const byId = new Map();

      flattened.forEach((site) => {
        if (!site) return;
        const id = site.id ?? site.site_id ?? site.node_id ?? site.key ?? site.name;
        if (id === undefined || id === null) {
          return;
        }
        const normalizedId = String(id);
        if (!byId.has(normalizedId)) {
          byId.set(normalizedId, { id, ...site });
        }
      });

      return Array.from(byId.values());
    },
    [extractArray]
  );

  const extractLanes = useCallback(
    (config) => {
      if (!config) return [];

      const candidateCollections = [];

      const collectFrom = (candidate) => {
        if (!candidate || typeof candidate !== 'object') return;

        candidateCollections.push(
          candidate.lanes,
          candidate.structure?.lanes,
          candidate.structure?.links,
          candidate.structure?.graph?.lanes,
          candidate.structure?.graph?.links,
          candidate.graph?.lanes,
          candidate.graph?.links
        );

        if (candidate.structure?.layers) {
          candidateCollections.push(
            candidate.structure.layers.flatMap((layer) =>
              extractArray(layer?.lanes || layer?.links)
            )
          );
        }

        if (candidate.structure?.lane_groups && typeof candidate.structure.lane_groups === 'object') {
          candidateCollections.push(
            Object.values(candidate.structure.lane_groups).flatMap((collection) =>
              extractArray(collection)
            )
          );
        }

        if (candidate.structure && typeof candidate.structure === 'object') {
          Object.entries(candidate.structure).forEach(([key, value]) => {
            if (
              key &&
              (key.toLowerCase().endsWith('_lanes') || key.toLowerCase().endsWith('_links'))
            ) {
              candidateCollections.push(extractArray(value));
            }
          });
        }

        if (Array.isArray(candidate.structure?.edges)) {
          candidateCollections.push(candidate.structure.edges);
        }
      };

      collectFrom(config);
      if (config?.config && config.config !== config) {
        collectFrom(config.config);
      }

      return candidateCollections.flatMap((collection) => extractArray(collection));
    },
    [extractArray]
  );

  const normalizeLaneDirection = useCallback(
    (fromNode, toNode) => {
      if (!fromNode || !toNode) {
        return {
          sourceNode: fromNode,
          targetNode: toNode,
          sourceType: null,
          targetType: null,
          sourceDagOrder: null,
          destinationDagOrder: null,
          swapped: false,
        };
      }
      const sourceType = normalizeTypeToken(
        resolveSiteTypeToken(fromNode) || fromNode?.type || fromNode?.node_type || fromNode?.dag_type
      );
      const destinationType = normalizeTypeToken(
        resolveSiteTypeToken(toNode) || toNode?.type || toNode?.node_type || toNode?.dag_type
      );
      const sourceDagOrder = getTypeOrderIndex(sourceType);
      const destinationDagOrder = getTypeOrderIndex(destinationType);

      if (
        Number.isFinite(sourceDagOrder) &&
        Number.isFinite(destinationDagOrder) &&
        sourceDagOrder > destinationDagOrder
      ) {
        return {
          sourceNode: toNode,
          targetNode: fromNode,
          sourceType: destinationType,
          targetType: sourceType,
          sourceDagOrder: destinationDagOrder,
          destinationDagOrder: sourceDagOrder,
          swapped: true,
        };
      }

      return {
        sourceNode: fromNode,
        targetNode: toNode,
        sourceType,
        targetType: destinationType,
        sourceDagOrder: Number.isFinite(sourceDagOrder) ? sourceDagOrder : null,
        destinationDagOrder: Number.isFinite(destinationDagOrder) ? destinationDagOrder : null,
        swapped: false,
      };
    },
    [getTypeOrderIndex, resolveSiteTypeToken]
  );

  const sankeyComputation = useMemo(() => {
    if (!configDetail && !sites?.length && !lanes?.length) {
      return { data: null, error: null };
    }

    const combinedSites = [
      ...extractSites(configDetail),
      ...extractArray(sites),
    ];
    const combinedLanes = [
      ...extractLanes(configDetail),
      ...extractArray(lanes),
    ];

    const rawSites = Array.from(
      new Map(
        combinedSites
          .filter(Boolean)
          .map((site, index) => {
            const identifier =
              site?.id ?? site?.site_id ?? site?.node_id ?? site?.key ?? site?.name ?? `site-${index}`;
            return [String(identifier), { id: identifier, ...site }];
          })
      ).values()
    );
    const rawLanes = combinedLanes.filter(Boolean);

    // Provide informative error messages when data is missing
    if (!rawSites.length && !rawLanes.length) {
      return { data: null, error: 'No sites or transportation lanes defined. Add sites and connect them with lanes to see the Sankey diagram.' };
    }
    if (!rawSites.length) {
      return { data: null, error: 'No sites defined. Add sites to your supply chain configuration to visualize the network.' };
    }
    if (!rawLanes.length) {
      return { data: null, error: 'No transportation lanes defined. Connect your sites with lanes to see material flow in the Sankey diagram.' };
    }

    const filteredSites = rawSites.filter((site) => !isAggregatedInputNode(site));

    const baseSites = filteredSites.map((site) => {
      const rawTypeForLabel =
        site.dag_type ||
        site.dagType ||
        site.type ||
        site.site_type ||
        site.node_type ||
        site.master_type ||
        site.masterType ||
        '';
      const normalizedType =
        resolveSiteTypeToken(site) ||
        normalizeTypeToken(site.type || site.site_type || site.node_type || site.master_type || site.masterType);
      const finalType = normalizedType || normalizeTypeToken(rawTypeForLabel) || 'UNSPECIFIED';
      const fallbackStyleKey = normalizeTypeToken(
        site.master_type || site.masterType || site.type || site.site_type || site.node_type
      );
      const style =
        typeStyles[finalType] ??
        (fallbackStyleKey ? typeStyles[fallbackStyleKey] : null) ??
        typeStyles.DEFAULT;
      const attributes =
        (typeof site.attributes === 'object' && site.attributes !== null ? site.attributes : {}) || {};
      const attrCapacity =
        attributes.inventory_capacity ??
        attributes.capacity ??
        attributes.inventory_capacity_max ??
        attributes.max_inventory ??
        attributes.capacity_max ??
        null;
      const attrCapacityMin =
        attributes.inventory_capacity_min ??
        attributes.min_inventory ??
        attributes.capacity_min ??
        null;
      const capacityMax =
        Number.isFinite(Number(site.inventory_capacity))
          ? Number(site.inventory_capacity)
          : Number.isFinite(Number(site.inventory_capacity_max))
            ? Number(site.inventory_capacity_max)
            : Number.isFinite(Number(site.inventory_capacity_min))
              ? Number(site.inventory_capacity_min)
              : Number.isFinite(Number(attrCapacity))
                ? Number(attrCapacity)
                : 0;
      const capacityMinRaw = Number.isFinite(Number(site.inventory_capacity_min))
        ? Number(site.inventory_capacity_min)
        : Number.isFinite(Number(attrCapacityMin))
          ? Number(attrCapacityMin)
          : null;
      const capacityLabelParts = [];
      if (capacityMinRaw !== null && Number.isFinite(capacityMax) && capacityMinRaw !== capacityMax) {
        capacityLabelParts.push(
          `${quantityFormatter.format(capacityMinRaw)} – ${quantityFormatter.format(capacityMax)} units`
        );
      } else if (Number.isFinite(capacityMax)) {
        capacityLabelParts.push(`${quantityFormatter.format(capacityMax)} units`);
      }
      const inventoryLabel = capacityLabelParts.join('');
      const resolvedCapacity =
        Number.isFinite(capacityMax) && capacityMax > 0 ? Number(capacityMax) : 0;
      return {
        id: site.id,
        name: site.name,
        type: finalType,
        dagType: site.dag_type || site.dagType || null,
        masterType: site.master_type || site.masterType || null,
        sourceType: finalType || null,
        typeLabel: getTypeLabel(rawTypeForLabel || finalType),
        capacityValue: resolvedCapacity,
        inventoryCapacityMin: capacityMinRaw,
        inventoryCapacityMax: Number.isFinite(capacityMax) ? capacityMax : null,
        inventoryLabel,
        color: style.fill,
        strokeColor: style.stroke,
      };
    });

    let sortedSites = [...baseSites].sort((a, b) => {
      const orderDiff = getTypeOrderIndex(a.type) - getTypeOrderIndex(b.type);
      if (orderDiff !== 0) {
        return orderDiff;
      }
      return String(a.name || '').localeCompare(String(b.name || ''));
    });

    const siteIndexMap = new Map(
      sortedSites.map((site, index) => [String(site.id), { ...site, index }])
    );
    const siteNameLookup = new Map(
      sortedSites
        .filter((site) => site?.name)
        .map((site) => [String(site.name).trim().toLowerCase(), site])
    );

    const resolveSite = (reference) => {
      if (!reference && reference !== 0) {
        return null;
      }
      if (typeof reference === 'object') {
        const candidateId = reference.id ?? reference.site_id ?? reference.node_id ?? reference.key;
        if (candidateId !== undefined && candidateId !== null) {
          const match = siteIndexMap.get(String(candidateId));
          if (match) {
            return match;
          }
        }
        const candidateName = reference.name ?? reference.label;
        if (candidateName) {
          return siteNameLookup.get(String(candidateName).trim().toLowerCase()) ?? null;
        }
        return null;
      }
      const match = siteIndexMap.get(String(reference));
      if (match) {
        return match;
      }
      if (typeof reference === 'string') {
        return siteNameLookup.get(reference.trim().toLowerCase()) ?? null;
      }
      return null;
    };

    const findSiteForLaneEnd = (lane, direction) => {
      // AWS SC DM uses from_site_id/to_site_id
      const siteId = direction === 'upstream' ? lane.from_site_id : lane.to_site_id;
      return resolveSite(siteId);
    };

    const forwardLinks = rawLanes
      .map((lane) => {
        const upstreamSite = findSiteForLaneEnd(lane, 'upstream');
        const downstreamSite = findSiteForLaneEnd(lane, 'downstream');

        if (!upstreamSite || !downstreamSite) {
          return null;
        }

        const {
          sourceNode: sourceSite,
          targetNode: targetSite,
          sourceType,
          targetType,
        } = normalizeLaneDirection(upstreamSite, downstreamSite);

        const valueRaw = lane.capacity ?? lane.capacity_int ?? lane.value ?? lane.volume ?? 0;
        const numeric = Number.isFinite(Number(valueRaw)) ? Number(valueRaw) : 0;
        const sanitizedValue = numeric > 0 ? numeric : 1e-4;

        const leadTime = extractLeadTime(lane);
        return {
          id:
            lane.id ??
            `${sourceSite?.id ?? sourceSite?.name}-${targetSite?.id ?? targetSite?.name}`,
          source: sourceSite?.id,
          target: targetSite?.id,
          value: sanitizedValue,
          capacity: numeric,
          direction: 'forward',
          color: sourceSite?.color,
          sourceType: sourceType ? sourceType.toUpperCase() : undefined,
          targetType: targetType ? targetType.toUpperCase() : undefined,
          leadTime: Number.isFinite(leadTime) ? leadTime : null,
        };
      })
      .filter(Boolean);

    const resolveMetricValue = (capacityMetric, flowMetric) => {
      if (sankeyScaleMode === 'capacity') {
        return capacityMetric > 0 ? capacityMetric : flowMetric;
      }
      return flowMetric > 0 ? flowMetric : capacityMetric;
    };

    const siteFlowMetricMap = new Map();
    forwardLinks.forEach((link) => {
      const capacityMetric = Math.max(Number(link.capacity ?? 0) || 0, 0);
      const flowMetric = Math.max(Number(link.value ?? 0) || 0, MIN_LINK_VALUE);
      const metricValue = resolveMetricValue(capacityMetric, flowMetric);
      const sourceId = link.source ? String(link.source) : null;
      const targetId = link.target ? String(link.target) : null;
      if (sourceId) {
        siteFlowMetricMap.set(
          sourceId,
          (siteFlowMetricMap.get(sourceId) ?? 0) + metricValue
        );
      }
      if (targetId) {
        siteFlowMetricMap.set(
          targetId,
          (siteFlowMetricMap.get(targetId) ?? 0) + metricValue
        );
      }
    });

    sortedSites = sortedSites.map((site) => {
      const flowMetric = siteFlowMetricMap.get(String(site.id)) ?? 0;
      const baseMetric = Math.max(Number(site.capacityValue ?? 0), 0);
      let metricValue = flowMetric;
      let metricSource = 'flow';
      if (sankeyScaleMode === 'capacity' && baseMetric > 0) {
        metricValue = baseMetric;
        metricSource = 'capacity';
      } else if (flowMetric > 0) {
        metricValue = flowMetric;
        metricSource = 'flow';
      } else {
        metricValue = baseMetric;
        metricSource = baseMetric > 0 ? 'capacity' : null;
      }
      return {
        ...site,
        metricValue,
        metricSource,
      };
    });

    const collapseSitesByType = (siteList, linkList) => {
      const siteLookup = new Map(
        (Array.isArray(siteList) ? siteList : []).map((site) => [String(site.id), site])
      );
      const groupedByType = new Map();

      siteList.forEach((site) => {
        const typeKey = String(site.type || '').toUpperCase();
        if (!groupedByType.has(typeKey)) {
          groupedByType.set(typeKey, []);
        }
        const isPreAggregated =
          site?.isAggregated === true ||
          site?.aggregated === true ||
          site?.is_aggregated === true ||
          site?.is_summary === true ||
          site?.summary === true;
        if (isPreAggregated) {
          return;
        }
        groupedByType.get(typeKey).push(site);
      });

      const collapseMap = new Map();
      const resultSites = [];

      groupedByType.forEach((sitesOfType, typeKey) => {
        const sortedByMetric = [...sitesOfType].sort((a, b) => {
          const aMetric = Math.max(Number(a.metricValue ?? a.capacityValue ?? 0), 0);
          const bMetric = Math.max(Number(b.metricValue ?? b.capacityValue ?? 0), 0);
          if (bMetric !== aMetric) {
            return bMetric - aMetric;
          }
          return String(a.name || '').localeCompare(String(b.name || ''));
        });
        sortedByMetric.forEach((site) => {
          collapseMap.set(String(site.id), String(site.id));
        });

        const maxVisible = Math.min(sortedByMetric.length, 10);
        const visible = sortedByMetric.slice(0, maxVisible);
        visible.forEach((site) => {
          resultSites.push(site);
          collapseMap.set(String(site.id), String(site.id));
        });

        const hidden = sortedByMetric.slice(maxVisible);
        if (hidden.length) {
          const aggregateCapacity = hidden.reduce(
            (sum, site) => sum + Math.max(Number(site.capacityValue ?? 0) || 0, 0),
            0
          );
          const aggregateMetric = hidden.reduce(
            (sum, site) => sum + Math.max(Number(site.metricValue ?? 0) || 0, 0),
            0
          );
          const baseId = `${typeKey}-OTHER`;
          let aggregatedId = baseId;
          let counter = 1;
          const existingIds = new Set([
            ...siteList.map((site) => String(site.id)),
            ...resultSites.map((site) => String(site.id)),
          ]);
          while (existingIds.has(aggregatedId)) {
            aggregatedId = `${baseId}-${counter++}`;
          }

          const sampleSite = visible[0] ?? hidden[0];
          const typeLabel = getTypeLabel(typeKey);
          const aggregatedSite = {
            id: aggregatedId,
            name: `${typeLabel} – Other`,
            type: typeKey,
            typeLabel,
            inventoryLabel:
              aggregateCapacity > 0
                ? `${quantityFormatter.format(Math.max(aggregateCapacity, 0))} units total`
                : `${quantityFormatter.format(Math.max(aggregateMetric, 0))} units total`,
            inventoryCapacityMin: null,
            inventoryCapacityMax: null,
            capacityValue: aggregateCapacity,
            metricValue: aggregateMetric,
            color:
              sampleSite?.color ||
              typeStyles?.[typeKey]?.fill ||
              typeStyles.DEFAULT.fill,
            strokeColor:
              sampleSite?.strokeColor ||
              typeStyles?.[typeKey]?.stroke ||
              typeStyles.DEFAULT.stroke,
            isAggregated: true,
            aggregatedSites: hidden.map((site) => site.id),
          };
          resultSites.push(aggregatedSite);
          hidden.forEach((site) => {
            collapseMap.set(String(site.id), aggregatedId);
          });
        }
      });

      siteList.forEach((site) => {
        const key = String(site.id);
        if (!collapseMap.has(key)) {
          collapseMap.set(key, key);
        }
      });

      const resultSiteLookup = new Map(
        resultSites.map((site) => [String(site.id), site])
      );

      const aggregatedLinksMap = new Map();
      linkList.forEach((link) => {
        const sourceId = collapseMap.get(String(link.source)) || String(link.source);
        const targetId = collapseMap.get(String(link.target)) || String(link.target);
        if (!sourceId || !targetId || sourceId === targetId) {
          return;
        }
        const mapKey = `${sourceId}→${targetId}`;
        const existing = aggregatedLinksMap.get(mapKey);
        const sourceSite = resultSiteLookup.get(sourceId) || siteLookup.get(String(link.source));
        const targetSite = resultSiteLookup.get(targetId) || siteLookup.get(String(link.target));
        const sourceType = String(sourceSite?.type || '').toUpperCase();
        const targetType = String(targetSite?.type || '').toUpperCase();
        const linkCapacity = Number(link.capacity ?? 0);
        const weight = Number.isFinite(linkCapacity) && linkCapacity > 0 ? linkCapacity : 0;
        if (existing) {
          existing.value += Number(link.value ?? 0);
          existing.capacity += linkCapacity || 0;
          if (Number.isFinite(link.leadTime)) {
            existing.leadTimes.push({ value: link.leadTime, weight: weight || Number(link.value ?? 0) || 0 });
          }
        } else {
          aggregatedLinksMap.set(mapKey, {
            id: link.id ?? mapKey,
            source: sourceId,
            target: targetId,
            value: Number(link.value ?? 0),
            capacity: linkCapacity || 0,
            color: link.color,
            direction: link.direction,
            sourceType,
            targetType,
            leadTimes:
              Number.isFinite(link.leadTime)
                ? [{ value: link.leadTime, weight: weight || Number(link.value ?? 0) || 0 }]
                : [],
          });
        }
      });

      const aggregatedLinks = Array.from(aggregatedLinksMap.values());
      return { sites: resultSites, links: aggregatedLinks, collapseMap };
    };

    const { sites: effectiveSites, links: effectiveLinks } = collapseSitesByType(
      sortedSites,
      forwardLinks
    );

    const enrichedLinks = effectiveLinks.map((link) => {
      const leadSamples = Array.isArray(link.leadTimes) ? link.leadTimes : [];
      let weightedLead = null;
      if (leadSamples.length > 0) {
        const weightSum = leadSamples.reduce((sum, sample) => {
          const weight = Number(sample.weight);
          return Number.isFinite(weight) && weight > 0 ? sum + weight : sum;
        }, 0);
        if (weightSum > 0) {
          const aggregate = leadSamples.reduce((sum, sample) => {
            const weight = Number(sample.weight);
            const lead = Number(sample.value);
            if (!Number.isFinite(weight) || weight <= 0 || !Number.isFinite(lead)) {
              return sum;
            }
            return sum + lead * weight;
          }, 0);
          weightedLead = aggregate / weightSum;
        } else {
          const candidate = leadSamples.find((sample) => Number.isFinite(Number(sample.value)));
          if (candidate) {
            weightedLead = Number(candidate.value);
          }
        }
      } else if (Number.isFinite(link.leadTime)) {
        weightedLead = Number(link.leadTime);
      }

      return {
        ...link,
        sourceType: String(link.sourceType || '').toUpperCase(),
        targetType: String(link.targetType || '').toUpperCase(),
        capacity: Number.isFinite(Number(link.capacity)) ? Number(link.capacity) : 0,
        flowValue: Number.isFinite(Number(link.value))
          ? Math.max(Number(link.value), 0)
          : 0,
        leadTimeValue: Number.isFinite(weightedLead) ? weightedLead : null,
      };
    });

    const typeMetricStats = new Map();
    effectiveSites.forEach((node) => {
      const metric = Number(node.metricValue ?? node.capacityValue ?? 0);
      if (!Number.isFinite(metric)) {
        return;
      }
      const safeMetric = Math.max(metric, 0);
      const typeKey = String(node.type || "").toUpperCase();
      const record = typeMetricStats.get(typeKey) || {
        totalMetric: 0,
        count: 0,
      };
      record.totalMetric += safeMetric;
      record.count += 1;
      typeMetricStats.set(typeKey, record);
    });

    const normalizedEffectiveNodes = effectiveSites.map((node, index) => {
      const metric = Number(node.metricValue ?? node.capacityValue ?? 0);
      const safeMetric = Number.isFinite(metric) ? Math.max(metric, 0) : 0;
      const typeKey = String(node.type || "").toUpperCase();
      const stats = typeMetricStats.get(typeKey);
      let normalized = 0;
      if (stats) {
        if (stats.totalMetric > 0) {
          normalized = safeMetric > 0 ? safeMetric / stats.totalMetric : 0;
        } else if (stats.count > 0) {
          normalized = 1 / stats.count;
        }
      }
      const shipmentsValue =
        safeMetric > 0
          ? safeMetric
          : normalized > 0
            ? normalized
            : MIN_LINK_VALUE;
      return {
        ...node,
        id: String(node.id ?? `node-${index}`),
        normalizedCapacity: normalized,
        shipments: Math.max(shipmentsValue, MIN_LINK_VALUE),
        metricValue: safeMetric,
        capacityValue: Math.max(Number(node.capacityValue ?? 0), 0),
      };
    });

    const normalizedTypeSet = new Set();
    const typePredecessors = new Map();
    const typeSuccessors = new Map();

    const registerType = (typeToken) => {
      const normalized = normalizeTypeToken(typeToken);
      if (normalized) {
        normalizedTypeSet.add(normalized);
      }
      return normalized;
    };

    const registerEdge = (sourceType, targetType) => {
      const sourceKey = registerType(sourceType);
      const targetKey = registerType(targetType);
      if (!sourceKey || !targetKey || sourceKey === targetKey) {
        return;
      }
      if (!typeSuccessors.has(sourceKey)) {
        typeSuccessors.set(sourceKey, new Set());
      }
      if (!typePredecessors.has(targetKey)) {
        typePredecessors.set(targetKey, new Set());
      }
      typeSuccessors.get(sourceKey).add(targetKey);
      typePredecessors.get(targetKey).add(sourceKey);
    };

    normalizedEffectiveNodes.forEach((node) => registerType(node.type));
    enrichedLinks.forEach((link) => {
      registerEdge(link.sourceType, link.targetType);
    });

    // Only register MARKET_DEMAND / MARKET_SUPPLY if sites with those types actually exist
    const demandKey = normalizeTypeToken(MARKET_DEMAND_TYPE);
    const supplyKey = normalizeTypeToken(MARKET_SUPPLY_TYPE);
    if (normalizedTypeSet.has(demandKey)) registerType(MARKET_DEMAND_TYPE);
    if (normalizedTypeSet.has(supplyKey)) registerType(MARKET_SUPPLY_TYPE);

    const distanceByType = new Map();
    const queue = [];
    if (normalizedTypeSet.has(demandKey)) {
      queue.push([demandKey, 0]);
    }

    while (queue.length > 0) {
      const [typeKey, distance] = queue.shift();
      const previous = distanceByType.get(typeKey);
      if (previous !== undefined && previous >= distance) {
        continue;
      }
      distanceByType.set(typeKey, distance);
      const predecessors = typePredecessors.get(typeKey);
      if (predecessors) {
        predecessors.forEach((neighbor) => {
          queue.push([neighbor, distance + 1]);
        });
      }
    }

    const typeList = Array.from(normalizedTypeSet.values());

    for (let pass = 0; pass < typeList.length; pass += 1) {
      let updated = false;
      typeList.forEach((typeKey) => {
        if (distanceByType.has(typeKey)) {
          return;
        }
        const successors = typeSuccessors.get(typeKey);
        if (!successors || successors.size === 0) {
          return;
        }
        let maxSuccessor = -Infinity;
        successors.forEach((succ) => {
          const dist = distanceByType.get(succ);
          if (dist !== undefined) {
            maxSuccessor = Math.max(maxSuccessor, dist);
          }
        });
        if (Number.isFinite(maxSuccessor) && maxSuccessor > -Infinity) {
          distanceByType.set(typeKey, maxSuccessor + 1);
          updated = true;
        }
      });
      if (!updated) {
        break;
      }
    }

    const assignedDistances = Array.from(distanceByType.values());
    const maxDistance = assignedDistances.length ? Math.max(...assignedDistances) : 0;
    if (normalizedTypeSet.has(supplyKey) && !distanceByType.has(supplyKey)) {
      distanceByType.set(supplyKey, maxDistance + 1);
    }

    const unresolvedTypes = typeList.filter((typeKey) => !distanceByType.has(typeKey));
    if (unresolvedTypes.length > 0) {
      const fallbackOrder = typeOrder.filter((token) => normalizedTypeSet.has(token));
      if (fallbackOrder.length) {
        fallbackOrder.forEach((typeKey, idx) => {
          distanceByType.set(typeKey, idx);
        });
      }
      const stillUnresolved = typeList.filter((typeKey) => !distanceByType.has(typeKey));
      if (stillUnresolved.length > 0) {
        const unresolvedLabels = stillUnresolved.map((typeKey) => getTypeLabel(typeKey));
        const unresolvedList = unresolvedLabels.join(', ');
        const noun = unresolvedLabels.length === 1 ? 'site type' : 'site types';
        return {
          data: null,
          error: `Unable to derive a lane-based order for ${noun} ${unresolvedList}. Ensure every type participates in a forward lane path that eventually reaches Market Demand.`,
        };
      }
    }

    let layeredTypes = typeList.sort((a, b) => {
      const distA = distanceByType.get(a);
      const distB = distanceByType.get(b);
      if (distA !== distB) {
        return (distA ?? Infinity) - (distB ?? Infinity);
      }
      return a.localeCompare(b);
    });

    layeredTypes = applyDescendingDagDisplayOrder(layeredTypes);

    const deriveLayering = () => {
      const typeTokens = new Set();
      normalizedEffectiveNodes.forEach((node) => {
        const token = normalizeTypeToken(node.type);
        if (token) {
          typeTokens.add(token);
        }
      });

      const edges = [];
      let loopType = null;
      enrichedLinks.forEach((link) => {
        const sourceKey = normalizeTypeToken(link.sourceType);
        const targetKey = normalizeTypeToken(link.targetType);
        if (!sourceKey || !targetKey) {
          return;
        }
        typeTokens.add(sourceKey);
        typeTokens.add(targetKey);
        if (sourceKey === targetKey) {
          loopType = loopType ?? sourceKey;
          return;
        }
        edges.push([sourceKey, targetKey]);
      });

      if (loopType) {
        return {
          layeredTypes: [],
          columnOrder: [],
          error: `We found a lane that loops from ${getTypeLabel(loopType)} back to itself. Remove or correct that lane to build the diagram.`,
        };
      }

      if (typeTokens.size <= 1) {
        const soleType = Array.from(typeTokens)[0];
        if (!soleType) {
          return {
            layeredTypes: [],
            columnOrder: [],
            error: 'We could not identify any site types in this configuration.',
          };
        }
        return {
          layeredTypes: [soleType],
          columnOrder: [soleType.toLowerCase()],
          error: null,
        };
      }

      if (!edges.length) {
        return {
          layeredTypes: [],
          columnOrder: [],
          error:
            'We could not derive a site type ordering from the lanes because no connections were found between types.',
        };
      }

      const adjacency = new Map();
      const inDegree = new Map();
      typeTokens.forEach((token) => {
        adjacency.set(token, new Set());
        inDegree.set(token, 0);
      });

      edges.forEach(([source, target]) => {
        const targets = adjacency.get(source);
        if (!targets.has(target)) {
          targets.add(target);
          inDegree.set(target, inDegree.get(target) + 1);
        }
      });

      const queue = [];
      const enqueueIfRoot = (token) => {
        if (inDegree.get(token) === 0) {
          queue.push(token);
        }
      };
      typeTokens.forEach(enqueueIfRoot);

      const sortQueue = () => {
        if (queue.length <= 1) {
          return;
        }
        queue.sort((a, b) => {
          const orderDiff = getTypeOrderIndex(a) - getTypeOrderIndex(b);
          if (orderDiff !== 0) {
            return orderDiff;
          }
          return String(a || '').localeCompare(String(b || ''));
        });
      };
      sortQueue();

      const topoOrder = [];
      const visited = new Set();

      while (queue.length > 0) {
        const current = queue.shift();
        topoOrder.push(current);
        visited.add(current);
        adjacency.get(current).forEach((neighbor) => {
          const updated = inDegree.get(neighbor) - 1;
          inDegree.set(neighbor, updated);
          if (updated === 0) {
            queue.push(neighbor);
            sortQueue();
          }
        });

        if (!queue.length) {
          typeTokens.forEach((token) => {
            if (!visited.has(token) && inDegree.get(token) === 0) {
              queue.push(token);
            }
          });
          sortQueue();
        }
      }

      if (visited.size !== typeTokens.size) {
        const remaining = [];
        typeTokens.forEach((token) => {
          if (!visited.has(token)) {
            remaining.push(getTypeLabel(token));
          }
        });
        remaining.sort();
        return {
          layeredTypes: [],
          columnOrder: [],
          error: `We detected a loop or missing path among site types: ${remaining.join(', ')}.`,
        };
      }

      const reversedTopo = [...topoOrder].reverse();
      let layeredTypes = applyDescendingDagDisplayOrder(reversedTopo);
      if (!layeredTypes.length && reversedTopo.length) {
        layeredTypes = applyDescendingDagDisplayOrder([...reversedTopo]);
      }

      return {
        layeredTypes,
        columnOrder: layeredTypes.map((token) => token.toLowerCase()),
        error: null,
      };
    };

    const layering = deriveLayering();
    if (layering.error) {
      return { data: null, error: layering.error };
    }

    // Use the deriveLayering result (which only includes actual site types)
    // instead of the outer columnOrder (which may include phantom types)
    if (layering.layeredTypes?.length) {
      layeredTypes = layering.layeredTypes;
    }
    const columnOrder = layering.columnOrder?.length
      ? layering.columnOrder
      : layeredTypes.map((token) => token.toLowerCase());

    const nodeLookupForLinks = new Map(
      normalizedEffectiveNodes.map((node) => [String(node.id), node])
    );

    const leadTimeValues = [];
    const sourceTypeTotals = new Map();
    const sourceTypeCounts = new Map();
    enrichedLinks.forEach((link) => {
      const sourceNode = nodeLookupForLinks.get(String(link.source)) || null;
      const targetNode = nodeLookupForLinks.get(String(link.target)) || null;
      const sourceType = String(link.sourceType || sourceNode?.type || '').toUpperCase();
      const targetType = String(link.targetType || targetNode?.type || '').toUpperCase();
      const capacityValue = Math.max(link.capacity ?? 0, 0);
      const flowValue = Math.max(link.flowValue ?? link.value ?? 0, 0);
      const metricValue =
        sankeyScaleMode === 'capacity'
          ? capacityValue > 0
            ? capacityValue
            : flowValue
          : flowValue > 0
            ? flowValue
            : capacityValue;
      link.metricValue = metricValue;
      link.sourceType = sourceType;
      link.targetType = targetType;
      if (metricValue > 0) {
        sourceTypeTotals.set(sourceType, (sourceTypeTotals.get(sourceType) ?? 0) + metricValue);
      }
      sourceTypeCounts.set(sourceType, (sourceTypeCounts.get(sourceType) ?? 0) + 1);
      if (Number.isFinite(link.leadTimeValue)) {
        leadTimeValues.push(link.leadTimeValue);
      }
    });

    const leadTimeStats = leadTimeValues.length
      ? {
          min: Math.min(...leadTimeValues),
          median: computeMedian(leadTimeValues),
          max: Math.max(...leadTimeValues),
        }
      : null;

    const supplyNode = normalizedEffectiveNodes.find(
      (node) => String(node.type || '').toUpperCase() === 'MARKET_SUPPLY'
    );

    const returnLinks = [];
    if (supplyNode) {
      normalizedEffectiveNodes
        .filter((node) => String(node.type || '').toUpperCase() === 'MARKET_DEMAND')
        .forEach((marketNode) => {
          const inboundTotal = effectiveLinks
            .filter((link) => String(link.target) === String(marketNode.id))
            .reduce((sum, link) => sum + (Number(link.value) || 0), 0);

          const outboundTotal = effectiveLinks
            .filter((link) => String(link.source) === String(marketNode.id))
            .reduce((sum, link) => sum + (Number(link.value) || 0), 0);

          const feedbackMagnitude = Math.max(inboundTotal, outboundTotal);
          const value = feedbackMagnitude > 0 ? feedbackMagnitude : MIN_LINK_VALUE;
          returnLinks.push({
            id: `return-${marketNode.id}-${supplyNode.id}`,
            sourceId: String(marketNode.id),
            targetId: String(supplyNode.id),
            value,
          });
        });
    }

    const nodeFlowTotals = new Map();

    const sankeyNodes = normalizedEffectiveNodes.map((node) => ({
      id: String(node.id),
      key: String(node.id),
      name: node.name,
      type: node.type,
      typeLabel: node.typeLabel || getTypeLabel(node.type),
      inventoryLabel: node.inventoryLabel,
      inventoryCapacityMin: node.inventoryCapacityMin,
      inventoryCapacityMax: node.inventoryCapacityMax,
      capacityValue: node.capacityValue,
      metricValue: node.metricValue,
      normalizedCapacity: node.normalizedCapacity,
      shipments: Math.max(node.shipments ?? MIN_LINK_VALUE, MIN_LINK_VALUE),
      color: node.color,
      strokeColor: node.strokeColor,
      isAggregated: Boolean(node.isAggregated),
    }));

    const sankeyLinks = enrichedLinks.map((link, index) => {
      const sourceNode = nodeLookupForLinks.get(String(link.source));
      const sourceType = String(link.sourceType || sourceNode?.type || '').toUpperCase();
      const capacityValue = Math.max(link.capacity ?? 0, 0);
      const metricValue = Number.isFinite(link.metricValue)
        ? Math.max(link.metricValue, 0)
        : Math.max(link.value ?? 0, MIN_LINK_VALUE);
      const totalSourceMetric = sourceTypeTotals.get(sourceType) ?? 0;
      const sourceCount = sourceTypeCounts.get(sourceType) ?? 0;
      let share = 0;
      if (totalSourceMetric > 0) {
        share = metricValue / totalSourceMetric;
      } else if (sourceCount > 0) {
        share = 1 / sourceCount;
      }
      const magnitude = Math.max(metricValue, MIN_LINK_VALUE);
      const color = resolveLeadTimeColor(link.leadTimeValue, leadTimeStats);

      nodeFlowTotals.set(
        String(link.source),
        (nodeFlowTotals.get(String(link.source)) ?? 0) + magnitude
      );
      nodeFlowTotals.set(
        String(link.target),
        (nodeFlowTotals.get(String(link.target)) ?? 0) + magnitude
      );

      return {
        id: link.id ?? `link-${index}`,
        source: String(link.source),
        target: String(link.target),
        value: magnitude,
        capacity: capacityValue,
        metricValue,
        relativeCapacity: share,
        leadTime: link.leadTimeValue,
        color,
        direction: link.direction,
      };
    });

    const adjustedNodes = sankeyNodes.map((node) => {
      const flow = nodeFlowTotals.get(String(node.id)) ?? node.shipments ?? MIN_LINK_VALUE;
      return {
        ...node,
        shipments: Math.max(node.shipments ?? MIN_LINK_VALUE, MIN_LINK_VALUE),
        flowShare: Math.max(flow, MIN_LINK_VALUE),
      };
    });

    return {
      data: {
        nodes: adjustedNodes,
        links: sankeyLinks,
        returnLinks,
        leadTimeStats,
        columnOrder,
        typeOrder: layeredTypes,
      },
      error: null,
    };
  }, [
    applyDescendingDagDisplayOrder,
    configDetail,
    extractArray,
    extractLanes,
    extractSites,
    getTypeLabel,
    getTypeOrderIndex,
    lanes,
    sites,
    normalizeLaneDirection,
    quantityFormatter,
    resolveSiteTypeToken,
    typeOrder,
    typeStyles,
    sankeyScaleMode,
  ]);

  const {
    data: sankeyData,
    error: sankeyError,
  } = sankeyComputation || { data: null, error: null };
  const leadTimeStats = sankeyData?.leadTimeStats;
  const sankeyHeight = DEFAULT_SANKEY_HEIGHT;

  const sankeyNodePadding = useMemo(() => {
    if (!sankeyData?.nodes?.length) {
      return 32;
    }
    const countsByType = new Map();
    sankeyData.nodes.forEach((node) => {
      const typeKey = normalizeTypeToken(node.type);
      if (!typeKey) return;
      countsByType.set(typeKey, (countsByType.get(typeKey) ?? 0) + 1);
    });
    const maxNodesInColumn = countsByType.size ? Math.max(...countsByType.values()) : 1;
    const innerHeight = Math.max(sankeyHeight - 72, 180);
    const minPadding = 12;
    const maxPadding = 36;
    const spacingPerNode = innerHeight / Math.max(maxNodesInColumn, 1);
    const dynamicPadding = Math.max(minPadding, Math.min(maxPadding, Math.floor(spacingPerNode * 0.6)));
    return dynamicPadding;
  }, [sankeyData?.nodes, sankeyHeight]);

  const handleTabChange = useCallback((value) => {
    setActiveTab(value);
  }, []);

  const handleScaleModeChange = useCallback((value) => {
    if (value) {
      setSankeyScaleMode(value);
    }
  }, []);

  const siteTypeLookup = useMemo(() => {
    return new Map((sites || []).map((site) => [String(site.id ?? site.site_id ?? site.node_id), site]));
  }, [sites]);

  const productLookup = useMemo(() => {
    // AWS SC DM: Product terminology
    return new Map((products || []).map((product) => [String(product.id ?? product.product_id ?? product.item_id), product]));
  }, [products]);

  const laneTableRows = useMemo(() => {
    if (!lanes?.length) return [];

    const det = (dist, legacy = null) => {
      if (dist === null || dist === undefined) return legacy ?? 1;
      if (typeof dist === 'number') return Number.isFinite(dist) ? dist : (legacy ?? 1);
      if (typeof dist === 'object') {
        const val = dist.value ?? dist.deterministic ?? dist.mean ?? dist.minimum ?? dist.maximum;
        const num = Number(val);
        if (Number.isFinite(num)) return num;
      }
      const num = Number(dist);
      return Number.isFinite(num) ? num : (legacy ?? 1);
    };

    const rows = lanes.map((lane) => {
      const displayFromId = lane.from_site_id;
      const displayToId = lane.to_site_id;
      const fromNode = siteTypeLookup.get(String(displayFromId));
      const toNode = siteTypeLookup.get(String(displayToId));
      const {
        sourceNode,
        targetNode,
        sourceType,
        targetType,
        sourceDagOrder,
        destinationDagOrder,
      } = normalizeLaneDirection(fromNode, toNode);
      const legacyLead =
        (lane.lead_time_days && typeof lane.lead_time_days === 'object'
          ? lane.lead_time_days.min ?? lane.lead_time_days.max
          : lane.lead_time) ?? null;
      const canonicalFromId = sourceNode?.id ?? displayFromId;
      const canonicalToId = targetNode?.id ?? displayToId;

      return {
        id: lane.id ?? `${canonicalFromId}-${canonicalToId}`,
        fromId: canonicalFromId,
        toId: canonicalToId,
        fromType: sourceType,
        toType: targetType,
        sourceType,
        destinationType: targetType,
        sourceDagOrder: Number.isFinite(sourceDagOrder) ? sourceDagOrder : null,
        destinationDagOrder: Number.isFinite(destinationDagOrder) ? destinationDagOrder : null,
        sourceName: sourceNode?.name || sourceNode?.label || fromNode?.name || fromNode?.label || 'Unknown',
        destinationName: targetNode?.name || targetNode?.label || toNode?.name || toNode?.label || 'Unknown',
        // Demand/order lead time should default to the standard one-week delay when
        // it isn't explicitly set, not the material/shipping lead time.
        demandLead: det(lane.demand_lead_time, 1),
        supplyLead: det(lane.supply_lead_time, legacyLead),
        capacity: lane.capacity ?? lane.capacity_int ?? lane.value ?? null,
      };
    });

    return rows
      .map((row) => ({
        ...row,
        sourceDagOrder: Number.isFinite(row.sourceDagOrder) ? row.sourceDagOrder : null,
        destinationDagOrder: Number.isFinite(row.destinationDagOrder)
          ? row.destinationDagOrder
          : null,
      }))
      .sort((a, b) => {
        const aIdx = a.sourceDagOrder ?? Number.MAX_SAFE_INTEGER;
        const bIdx = b.sourceDagOrder ?? Number.MAX_SAFE_INTEGER;
        if (aIdx !== bIdx) return aIdx - bIdx;
        return String(a.sourceName).localeCompare(String(b.sourceName));
      });
  }, [lanes, siteTypeLookup, normalizeLaneDirection]);

  // Get product hierarchy breadcrumb from AWS SC DM product_hierarchy table
  // API returns computed hierarchy_path field (e.g., "Frozen > Proteins > Poultry")
  const getProductBreadcrumb = (product) => {
    // Use hierarchy_path computed from product_hierarchy table by backend
    return product.hierarchy_path || null;
  };

  const renderItemsTable = () => (
    <div className="border rounded-md">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Hierarchy</TableHead>
            <TableHead>Description</TableHead>
            <TableHead>Unit Cost Range</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {products?.length ? (
            products.map((product) => {
              const breadcrumb = getProductBreadcrumb(product);
              return (
                <TableRow key={product.id}>
                  <TableCell className="font-medium">{product.name || product.id}</TableCell>
                  <TableCell>
                    {breadcrumb ? (
                      <span className="text-sm text-muted-foreground">{breadcrumb}</span>
                    ) : (
                      <span className="text-sm text-muted-foreground italic">—</span>
                    )}
                  </TableCell>
                  <TableCell>
                    {product.description || (
                      <span className="text-sm text-muted-foreground">
                        No description provided
                      </span>
                    )}
                  </TableCell>
                  <TableCell>
                    {product.unit_cost_range
                      ? `$${Number(product.unit_cost_range.min ?? 0).toFixed(2)} – $${Number(
                          product.unit_cost_range.max ?? product.unit_cost_range.min ?? 0
                        ).toFixed(2)}`
                      : '—'}
                  </TableCell>
                </TableRow>
              );
            })
          ) : (
            <TableRow>
              <TableCell colSpan={4} className="text-center">
                <span className="text-sm text-muted-foreground">
                  No products are defined for this configuration yet.
                </span>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );

  const renderSitesTable = () => (
    <div className="border rounded-md">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead className="text-right">DAG Order</TableHead>
            <TableHead>Type</TableHead>
            <TableHead>Inventory Capacity</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sites?.length ? (
            [...sites]
              .sort(
                (a, b) =>
                  getTypeOrderIndex(
                    resolveSiteTypeToken(a) ||
                      normalizeTypeToken(a.dag_type || a.type || a.site_type || a.node_type)
                  ) -
                  getTypeOrderIndex(
                    resolveSiteTypeToken(b) ||
                      normalizeTypeToken(b.dag_type || b.type || b.site_type || b.node_type)
                  )
              )
              .map((site) => {
                const typeToken =
                  resolveSiteTypeToken(site) ||
                  normalizeTypeToken(site.dag_type || site.dagType || site.type || site.site_type || site.node_type);
                const typeLabel = getTypeLabel(typeToken);
                const dagOrder = getTypeOrderIndex(typeToken);
                const attrs =
                  typeof site.attributes === 'object' && site.attributes !== null
                    ? site.attributes
                    : {};
              const capacityMin =
                site.inventory_capacity_min ??
                attrs.inventory_capacity_min ??
                attrs.min_inventory ??
                null;
              const capacityMax =
                site.inventory_capacity_max ??
                site.inventory_capacity ??
                attrs.inventory_capacity ??
                attrs.inventory_capacity_max ??
                attrs.capacity ??
                null;
              let capacityLabel = 'Unknown';
              if (capacityMin !== null && capacityMax !== null && capacityMin !== capacityMax) {
                capacityLabel = `${quantityFormatter.format(Number(capacityMin))} – ${quantityFormatter.format(
                  Number(capacityMax)
                )} units`;
              } else if (capacityMax !== null) {
                capacityLabel = `${quantityFormatter.format(Number(capacityMax))} units`;
              } else if (capacityMin !== null) {
                capacityLabel = `${quantityFormatter.format(Number(capacityMin))} units`;
              }

              return (
                <TableRow key={site.id}>
                  <TableCell>{site.name}</TableCell>
                  <TableCell className="text-right">
                    {Number.isFinite(dagOrder) ? dagOrder : '—'}
                  </TableCell>
                  <TableCell>{typeLabel}</TableCell>
                  <TableCell>{capacityLabel}</TableCell>
                </TableRow>
              );
            })
          ) : (
            <TableRow>
              <TableCell colSpan={4} className="text-center">
                <span className="text-sm text-muted-foreground">
                  No sites are defined for this configuration yet.
                </span>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );

  const renderLanesTable = () => (
    <div className="border rounded-md">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Source / DAG Order</TableHead>
            <TableHead>Destination / DAG Order</TableHead>
            <TableHead className="text-right">Demand Lead Time</TableHead>
            <TableHead className="text-right">Supply Lead Time</TableHead>
            <TableHead className="text-right">Capacity</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {laneTableRows.length ? (
            laneTableRows.map((row) => (
              <TableRow key={row.id}>
                <TableCell>
                  <div className="flex flex-col">
                    <span className="text-sm">
                      {row.sourceName}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      DAG Order {Number.isFinite(row.sourceDagOrder) ? row.sourceDagOrder : '—'}
                    </span>
                  </div>
                </TableCell>
                <TableCell>
                  <div className="flex flex-col">
                    <span className="text-sm">
                      {row.destinationName}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      DAG Order {Number.isFinite(row.destinationDagOrder) ? row.destinationDagOrder : '—'}
                    </span>
                  </div>
                </TableCell>
                <TableCell className="text-right">
                  {row.demandLead !== null && row.demandLead !== undefined ? row.demandLead : '—'}
                </TableCell>
                <TableCell className="text-right">
                  {row.supplyLead !== null && row.supplyLead !== undefined ? row.supplyLead : '—'}
                </TableCell>
                <TableCell className="text-right">
                  {row.capacity !== null && row.capacity !== undefined
                    ? `${quantityFormatter.format(Number(row.capacity))} units`
                    : '—'}
                </TableCell>
              </TableRow>
            ))
          ) : (
            <TableRow>
              <TableCell colSpan={5} className="text-center">
                <span className="text-sm text-muted-foreground">
                  No lanes are defined for this configuration yet.
                </span>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );

  const renderProductSiteTable = () => (
    <div className="border rounded-md">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Product</TableHead>
            <TableHead>Site</TableHead>
            <TableHead>Inventory Target</TableHead>
            <TableHead>Initial Inventory</TableHead>
            <TableHead>Holding Cost</TableHead>
            <TableHead>Backlog Cost</TableHead>
            <TableHead>Selling Price</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {productSiteConfigs?.length ? (
            productSiteConfigs.map((cfg) => {
              const product = productLookup.get(String(cfg.product_id || cfg.item_id)) || {};
              const site = siteTypeLookup.get(String(cfg.site_id || cfg.node_id)) || {};
              const fmtRange = (range) =>
                range && range.min !== undefined && range.max !== undefined
                  ? `${range.min} – ${range.max}`
                  : '—';
              return (
                <TableRow key={cfg.id}>
                  <TableCell>{product.name || cfg.product_id || cfg.item_id}</TableCell>
                  <TableCell>{site.name || cfg.site_id || cfg.node_id}</TableCell>
                  <TableCell>{fmtRange(cfg.inventory_target_range)}</TableCell>
                  <TableCell>{fmtRange(cfg.initial_inventory_range)}</TableCell>
                  <TableCell>{fmtRange(cfg.holding_cost_range)}</TableCell>
                  <TableCell>{fmtRange(cfg.backlog_cost_range)}</TableCell>
                  <TableCell>{fmtRange(cfg.selling_price_range)}</TableCell>
                </TableRow>
              );
            })
          ) : (
            <TableRow>
              <TableCell colSpan={7} className="text-center">
                <span className="text-sm text-muted-foreground">
                  No product-site configurations are defined for this configuration yet.
                </span>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );

  const nodeTooltipContent = useCallback(
    (node) => {
      if (!node) {
        return null;
      }
      const capacityLabel = node.inventoryLabel
        ? `Inventory capacity: ${node.inventoryLabel}`
        : 'Inventory capacity: Unknown';
      const sharePercent = Number.isFinite(Number(node.normalizedCapacity))
        ? (Number(node.normalizedCapacity) * 100).toFixed(1)
        : null;
      const metricLabel = Number.isFinite(Number(node.metricValue))
        ? `${quantityFormatter.format(Math.max(Number(node.metricValue), 0))} units`
        : null;
      return (
        <div className="flex flex-col gap-1 p-1">
          <span className="text-sm font-semibold">
            {`${node.name} • ${node.typeLabel || getTypeLabel(node.type)}`}
          </span>
          <span className="text-sm text-muted-foreground">
            {capacityLabel}
          </span>
          {metricLabel && (
            <span className="text-sm text-muted-foreground">
              Flow metric: {metricLabel}
            </span>
          )}
          {sharePercent && (
            <span className="text-sm text-muted-foreground">
              Share of column capacity: {sharePercent}%
            </span>
          )}
          <span className="text-xs text-muted-foreground">
            Suggested context: overlay reorder point, safety stock, or throughput constraints for
            richer comparisons.
          </span>
        </div>
      );
    },
    [getTypeLabel, quantityFormatter]
  );

  const linkTooltipContent = useCallback(
    (link) => {
      if (!link) {
        return null;
      }
      const capacityValue = Number.isFinite(Number(link.capacity))
        ? Number(link.capacity)
        : Number.isFinite(Number(link.value))
          ? Number(link.value)
          : 0;
      const metricValue = Number.isFinite(Number(link.metricValue))
        ? Number(link.metricValue)
        : capacityValue;
      const linkLabel = `${link.source?.name ?? 'Source'} → ${link.target?.name ?? 'Target'}`;
      const sharePercent = Number.isFinite(Number(link.relativeCapacity))
        ? (Number(link.relativeCapacity) * 100).toFixed(1)
        : null;
      const leadTimeLabel = Number.isFinite(Number(link.leadTime))
        ? `${Number(link.leadTime).toFixed(2)} periods`
        : 'Unknown';
      const rangeNote = leadTimeStats
        ? `Lead time scale — min: ${leadTimeStats.min?.toFixed?.(2) ?? leadTimeStats.min}, median: ${
            leadTimeStats.median?.toFixed?.(2) ?? leadTimeStats.median
          }, max: ${leadTimeStats.max?.toFixed?.(2) ?? leadTimeStats.max}`
        : null;
      return (
        <div className="flex flex-col gap-1 p-1">
          <span className="text-sm font-semibold">
            {linkLabel}
          </span>
          <span className="text-sm text-muted-foreground">
            Lane metric: {quantityFormatter.format(Math.max(metricValue, 0))} units
          </span>
          {sharePercent && (
            <span className="text-sm text-muted-foreground">
              Share within lane group: {sharePercent}%
            </span>
          )}
          <span className="text-sm text-muted-foreground">
            Lead time: {leadTimeLabel}
          </span>
          {rangeNote && (
            <span className="text-xs text-muted-foreground">
              {rangeNote}
            </span>
          )}
        </div>
      );
    },
    [
      quantityFormatter,
      leadTimeStats,
    ]
  );

  const returnLinkTooltipContent = useCallback(
    (link) => {
      if (!link) {
        return null;
      }
      const magnitude = Number.isFinite(Number(link.value)) ? Number(link.value) : 0;
      const returnLabel = `${link.source?.name ?? 'Market Demand'} → ${link.target?.name ?? 'Market Supply'}`;
      return (
        <div className="flex flex-col gap-1 p-1">
          <span className="text-sm font-semibold">
            Demand feedback signal
          </span>
          <span className="text-sm text-muted-foreground">
            {returnLabel}
          </span>
          <span className="text-sm text-muted-foreground">
            Signal magnitude: {quantityFormatter.format(Math.max(magnitude, 0))} units
          </span>
        </div>
      );
    },
    [quantityFormatter]
  );

  const linkColorAccessor = useCallback(
    (link) => link.color ?? link.source?.color ?? forwardStroke,
    [forwardStroke]
  );

  const renderReturnDecorators = useCallback(
    (layout) => {
      if (!sankeyData?.returnLinks?.length) {
        return null;
      }
      const nodeMap = new Map(layout.nodes.map((node) => [String(node.id), node]));
      return (
        <g key="return-links">
          {sankeyData.returnLinks.map((link) => {
            const sourceNode = nodeMap.get(String(link.sourceId));
            const targetNode = nodeMap.get(String(link.targetId));
            if (!sourceNode || !targetNode) {
              return null;
            }
            const startX = sourceNode.x1;
            const startY = (sourceNode.y0 + sourceNode.y1) / 2;
            const endX = targetNode.x0;
            const endY = (targetNode.y0 + targetNode.y1) / 2;
            const horizontalGap = Math.max(Math.abs(endX - startX), 1);
            const direction = startX <= endX ? 1 : -1;
            const curveHeight = Math.max(layout.innerHeight * 0.25, 60);
            const controlX1 = startX + horizontalGap * 0.25 * direction;
            const controlY1 = startY - curveHeight;
            const controlX2 = endX - horizontalGap * 0.25 * direction;
            const controlY2 = endY - curveHeight;
            const pathD = `M${startX},${startY} C${controlX1},${controlY1} ${controlX2},${controlY2} ${endX},${endY}`;
            const payload = {
              ...link,
              source: sourceNode,
              target: targetNode,
            };
            const pathElement = (
              <path
                key={link.id}
                d={pathD}
                fill="none"
                stroke={returnStroke}
                strokeWidth={2}
                strokeOpacity={0.6}
                strokeDasharray="8 4"
              />
            );
            return (
              <TooltipProvider key={link.id}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    {pathElement}
                  </TooltipTrigger>
                  <TooltipContent side="top">
                    {returnLinkTooltipContent(payload)}
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            );
          })}
        </g>
      );
    },
    [returnLinkTooltipContent, returnStroke, sankeyData?.returnLinks]
  );

  const hasData = Boolean(!sankeyError && sankeyData?.nodes?.length && sankeyData?.links?.length);

  return (
    <Card variant="outline">
      <CardHeader>
        <CardTitle>Supply Chain Flow</CardTitle>
        <p className="text-sm text-muted-foreground mt-1">
          Visualize the forward flow to demand and the feedback signal returning to the supply side.
        </p>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-6">
          <div>
            <Label htmlFor="supply-chain-config-select">
              Supply Chain Configuration
            </Label>
            <Select
              value={selectedConfigId ? String(selectedConfigId) : ''}
              onValueChange={(value) => setSelectedConfigId(value ? Number(value) : null)}
              disabled={configsLoading || !configOptions.length}
            >
              <SelectTrigger id="supply-chain-config-select" className="mt-1">
                <SelectValue placeholder="Select a configuration" />
              </SelectTrigger>
              <SelectContent>
                {configOptions.map((cfg) => (
                  <SelectItem key={cfg.id} value={String(cfg.id)}>
                    {cfg.name || `Configuration ${cfg.id}`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {configsLoading && (
            <div className="flex justify-center py-8">
              <Spinner size="md" />
            </div>
          )}

          {!configsLoading && configsError && (
            <p className="text-sm text-destructive">
              {configsError}
            </p>
          )}

          {!configsLoading && !configsError && !configOptions.length && (
            <p className="text-sm text-muted-foreground">
              There are no supply chain configurations available for your group
              yet.
            </p>
          )}

          {detailLoading && (
            <div className="flex justify-center py-8">
              <Spinner size="md" />
            </div>
          )}

          {!detailLoading && detailError && (
            <p className="text-sm text-destructive">
              {detailError}
            </p>
          )}

          {!detailLoading && !detailError && selectedConfigId && (
            <Tabs value={activeTab} onValueChange={handleTabChange}>
              <TabsList className="flex-wrap">
                <TabsTrigger value="diagram">Flow Diagram</TabsTrigger>
                <TabsTrigger value="items">Products ({products.length})</TabsTrigger>
                <TabsTrigger value="sites">Sites ({sites.length})</TabsTrigger>
                <TabsTrigger value="lanes">Lanes ({lanes.length})</TabsTrigger>
                <TabsTrigger value="productsites">Product-Site ({productSiteConfigs.length})</TabsTrigger>
              </TabsList>

              <TabsContent value="diagram" className="mt-4">
                <div className="flex flex-col gap-2">
                  <div className="flex justify-between items-center">
                    {/* View mode toggle: Sankey vs Map */}
                    <ToggleGroup
                      type="single"
                      size="sm"
                      value={viewMode}
                      onValueChange={(val) => val && setViewMode(val)}
                    >
                      <ToggleGroupItem value="sankey">Sankey Flow</ToggleGroupItem>
                      <ToggleGroupItem value="map">Map View</ToggleGroupItem>
                    </ToggleGroup>
                    {/* Scale mode toggle (only shown for Sankey view) */}
                    {viewMode === 'sankey' && (
                      <ToggleGroup
                        type="single"
                        size="sm"
                        value={sankeyScaleMode}
                        onValueChange={handleScaleModeChange}
                      >
                        <ToggleGroupItem value="flow">Flow ratio</ToggleGroupItem>
                        <ToggleGroupItem value="capacity">Capacity ratio</ToggleGroupItem>
                      </ToggleGroup>
                    )}
                  </div>
                  <div style={{ height: sankeyHeight }} className="w-full">
                    {viewMode === 'sankey' ? (
                      // Sankey diagram view
                      hasData ? (
                        <SankeyDiagram
                          nodes={sankeyData.nodes}
                          links={sankeyData.links}
                          height={sankeyHeight}
                          nodeWidth={20}
                          nodePadding={sankeyNodePadding}
                          linkTooltip={linkTooltipContent}
                          nodeTooltip={nodeTooltipContent}
                          linkColorAccessor={linkColorAccessor}
                          defaultLinkOpacity={0.65}
                          renderDecorators={renderReturnDecorators}
                          columnOrder={sankeyData?.columnOrder}
                        />
                      ) : (
                        <div className="h-full flex items-center justify-center">
                          <p className={`text-sm text-center ${sankeyError ? 'text-destructive' : 'text-muted-foreground'}`}>
                            {sankeyError ??
                              "We couldn't find enough site and lane information to build the Sankey diagram for this configuration yet."}
                          </p>
                        </div>
                      )
                    ) : (
                      // Map view
                      (() => {
                        // Check if any sites have geographic coordinates
                        const sitesWithCoords = sites.filter(
                          (site) => site.geography?.latitude && site.geography?.longitude
                        );
                        // Transform sites for map component
                        const mapSites = sites.map((site) => ({
                          id: site.id,
                          name: site.name,
                          role: site.type || site.dag_type,
                          latitude: site.geography?.latitude,
                          longitude: site.geography?.longitude,
                          location: site.geography
                            ? [site.geography.city, site.geography.state_prov, site.geography.country]
                                .filter(Boolean)
                                .join(', ')
                            : null,
                        }));
                        // Transform lanes to edges for map component
                        const mapEdges = lanes.map((lane) => ({
                          from: lane.from_site_id,
                          to: lane.to_site_id,
                        }));

                        if (sitesWithCoords.length === 0) {
                          return (
                            <div className="h-full flex items-center justify-center">
                              <p className="text-sm text-center text-muted-foreground">
                                No geographic coordinates available. Add latitude/longitude data to your sites
                                via the Geography table to enable the map view.
                              </p>
                            </div>
                          );
                        }

                        // Build dynamic site type color map from typeStyles
                        const siteTypeColorMap = {};
                        sites.forEach((site) => {
                          const role = site.type || site.dag_type;
                          if (!role) return;
                          const key = role.toLowerCase().replace(/[\s-]+/g, '_');
                          if (siteTypeColorMap[key]) return;
                          const upperKey = key.toUpperCase();
                          const style = typeStyles[upperKey] ?? typeStyles.DEFAULT;
                          siteTypeColorMap[key] = style.fill;
                        });

                        return (
                          <GeospatialSupplyChain
                            sites={mapSites}
                            edges={mapEdges}
                            inventoryData={{}}
                            activeFlows={[]}
                            siteTypeColors={siteTypeColorMap}
                          />
                        );
                      })()
                    )}
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="items" className="mt-4">
                {renderItemsTable()}
              </TabsContent>
              <TabsContent value="sites" className="mt-4">
                {renderSitesTable()}
              </TabsContent>
              <TabsContent value="lanes" className="mt-4">
                {renderLanesTable()}
              </TabsContent>
              <TabsContent value="productsites" className="mt-4">
                {renderProductSiteTable()}
              </TabsContent>
            </Tabs>
          )}

          {hasData && viewMode === 'sankey' && (
            <SankeyMetricLegend orientation="row" justify="center" mode={sankeyScaleMode} />
          )}
        </div>
      </CardContent>
    </Card>
  );
};

SupplyChainConfigSankey.propTypes = {
  restrictToGroupId: PropTypes.number,
};

export default SupplyChainConfigSankey;
