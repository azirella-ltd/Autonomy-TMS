import { api } from './api';

const SUPPLY_CHAIN_CONFIG_BASE_URL = '/supply-chain-config';

export const canonicalizeSiteTypeKey = (value = '') => {
  const cleaned = String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '');
  return cleaned;
};

// AWS SC DM compliant site type definitions.
// Internal sites use master_type (inventory | manufacturer).
// External parties (vendors/customers) are TradingPartner records with tpartner_type.
// is_external=true entries appear in the Sankey but are managed via the
// Vendors / Customers wizard steps, not the Sites step.
export const DEFAULT_SITE_TYPE_DEFINITIONS = [
  { type: 'customer',             tpartner_type: 'customer',     label: 'Customer',             is_required: true,  is_external: true },
  { type: 'distribution_center',  master_type: 'inventory',      label: 'Distribution Center',  is_required: false, is_external: false },
  { type: 'warehouse',            master_type: 'inventory',      label: 'Warehouse',            is_required: false, is_external: false },
  { type: 'manufacturing_plant',  master_type: 'manufacturer',   label: 'Manufacturing Plant',  is_required: false, is_external: false },
  { type: 'vendor',               tpartner_type: 'vendor',       label: 'Vendor',               is_required: true,  is_external: true },
];

export const buildSiteTypeLabelMap = (definitions = DEFAULT_SITE_TYPE_DEFINITIONS) => {
  if (!Array.isArray(definitions)) return {};
  return definitions.reduce((acc, def) => {
    const resolvedLabel =
      def?.label ||
      canonicalizeSiteTypeKey(def?.type || '')
        .replace(/_/g, ' ')
        .replace(/\b\w/g, (m) => m.toUpperCase());
    const candidateKeys = new Set([
      canonicalizeSiteTypeKey(def?.type || ''),
      canonicalizeSiteTypeKey(def?.label || ''),
      canonicalizeSiteTypeKey(def?.group_type || def?.groupType || ''),
    ]);
    candidateKeys.forEach((key) => {
      if (!key || acc[key]) {
        return;
      }
      acc[key] = resolvedLabel;
    });
    return acc;
  }, {});
};

export const sortSiteTypeDefinitions = (definitions = DEFAULT_SITE_TYPE_DEFINITIONS) => {
  if (!Array.isArray(definitions)) return [...DEFAULT_SITE_TYPE_DEFINITIONS];
  // Preserve definition array order (no longer sorted by a static `order` field).
  // Configs that supply their own `site_type_definitions` with an `order` property
  // can still be sorted, but the default definitions rely on array position.
  return [...definitions].sort((a, b) => {
    const orderA = Number.isFinite(a?.order) ? a.order : Infinity;
    const orderB = Number.isFinite(b?.order) ? b.order : Infinity;
    if (orderA !== orderB) return orderA - orderB;
    return 0; // preserve original array order when no explicit order
  });
};

// Supply Chain Config CRUD
export const getSupplyChainConfigs = async () => {
  const response = await api.get(`${SUPPLY_CHAIN_CONFIG_BASE_URL}/`);
  return response.data;
};

export const getSupplyChainConfigById = async (id) => {
  const response = await api.get(`${SUPPLY_CHAIN_CONFIG_BASE_URL}/${id}`);
  return response.data;
};

export const createSupplyChainConfig = async (configData) => {
  const response = await api.post(SUPPLY_CHAIN_CONFIG_BASE_URL, configData);
  return response.data;
};

export const updateSupplyChainConfig = async (id, configData) => {
  const response = await api.put(`${SUPPLY_CHAIN_CONFIG_BASE_URL}/${id}`, configData);
  return response.data;
};

export const deleteSupplyChainConfig = async (id) => {
  await api.delete(`${SUPPLY_CHAIN_CONFIG_BASE_URL}/${id}`);
};

export const trainSupplyChainConfig = async (configId, options = {}) => {
  const response = await api.post(`${SUPPLY_CHAIN_CONFIG_BASE_URL}/${configId}/train`, options);
  return response.data;
};

// Products CRUD (AWS SC compliant - was Items)
export const getProducts = async (configId) => {
  const response = await api.get(`${SUPPLY_CHAIN_CONFIG_BASE_URL}/${configId}/products`);
  return response.data;
};

export const createProduct = async (configId, productData) => {
  const response = await api.post(`${SUPPLY_CHAIN_CONFIG_BASE_URL}/${configId}/products`, productData);
  return response.data;
};

export const updateProduct = async (configId, productId, productData) => {
  const response = await api.put(
    `${SUPPLY_CHAIN_CONFIG_BASE_URL}/${configId}/products/${productId}`,
    productData
  );
  return response.data;
};

export const deleteProduct = async (configId, productId) => {
  await api.delete(`${SUPPLY_CHAIN_CONFIG_BASE_URL}/${configId}/products/${productId}`);
};

// Sites CRUD (AWS SC DM: Site replaces Node)
export const getSites = async (configId, siteType = null) => {
  const url = siteType
    ? `${SUPPLY_CHAIN_CONFIG_BASE_URL}/${configId}/sites?site_type=${siteType}`
    : `${SUPPLY_CHAIN_CONFIG_BASE_URL}/${configId}/sites`;

  const response = await api.get(url);
  return response.data;
};

export const createSite = async (configId, siteData) => {
  const response = await api.post(`${SUPPLY_CHAIN_CONFIG_BASE_URL}/${configId}/sites`, siteData);
  return response.data;
};

export const updateSite = async (configId, siteId, siteData) => {
  const response = await api.put(
    `${SUPPLY_CHAIN_CONFIG_BASE_URL}/${configId}/sites/${siteId}`,
    siteData
  );
  return response.data;
};

export const deleteSite = async (configId, siteId) => {
  await api.delete(`${SUPPLY_CHAIN_CONFIG_BASE_URL}/${configId}/sites/${siteId}`);
};

// Transportation Lanes CRUD (AWS SC DM standard)
export const getTransportationLanes = async (configId) => {
  const response = await api.get(`${SUPPLY_CHAIN_CONFIG_BASE_URL}/${configId}/transportation-lanes`);
  return response.data;
};

export const createTransportationLane = async (configId, laneData) => {
  const response = await api.post(`${SUPPLY_CHAIN_CONFIG_BASE_URL}/${configId}/transportation-lanes`, laneData);
  return response.data;
};

export const updateTransportationLane = async (configId, laneId, laneData) => {
  const response = await api.put(
    `${SUPPLY_CHAIN_CONFIG_BASE_URL}/${configId}/transportation-lanes/${laneId}`,
    laneData
  );
  return response.data;
};

export const deleteTransportationLane = async (configId, laneId) => {
  await api.delete(`${SUPPLY_CHAIN_CONFIG_BASE_URL}/${configId}/transportation-lanes/${laneId}`);
};

// DEPRECATED: Use getTransportationLanes, createTransportationLane, etc.
export const getLanes = getTransportationLanes;
export const createLane = createTransportationLane;
export const updateLane = updateTransportationLane;
export const deleteLane = deleteTransportationLane;

// Product-Site Configs CRUD (AWS SC terminology)
export const getProductSiteConfigs = async (configId) => {
  const response = await api.get(`${SUPPLY_CHAIN_CONFIG_BASE_URL}/${configId}/product-site-configs`);
  return response.data;
};

export const createProductSiteConfig = async (configId, productSiteData) => {
  const response = await api.post(
    `${SUPPLY_CHAIN_CONFIG_BASE_URL}/${configId}/product-site-configs`,
    productSiteData
  );
  return response.data;
};

export const updateProductSiteConfig = async (configId, configEntryId, productSiteData) => {
  const response = await api.put(
    `${SUPPLY_CHAIN_CONFIG_BASE_URL}/${configId}/product-site-configs/${configEntryId}`,
    productSiteData
  );
  return response.data;
};

// Markets CRUD
export const getMarkets = async (configId) => {
  const response = await api.get(`${SUPPLY_CHAIN_CONFIG_BASE_URL}/${configId}/markets`);
  return response.data;
};

export const createMarket = async (configId, marketData) => {
  const response = await api.post(`${SUPPLY_CHAIN_CONFIG_BASE_URL}/${configId}/markets`, marketData);
  return response.data;
};

export const updateMarket = async (configId, marketId, marketData) => {
  const response = await api.put(
    `${SUPPLY_CHAIN_CONFIG_BASE_URL}/${configId}/markets/${marketId}`,
    marketData
  );
  return response.data;
};

export const deleteMarket = async (configId, marketId) => {
  await api.delete(`${SUPPLY_CHAIN_CONFIG_BASE_URL}/${configId}/markets/${marketId}`);
};

// Market Demands CRUD
export const getMarketDemands = async (configId) => {
  const response = await api.get(`${SUPPLY_CHAIN_CONFIG_BASE_URL}/${configId}/market-demands`);
  return response.data;
};

export const createMarketDemand = async (configId, demandData) => {
  const response = await api.post(
    `${SUPPLY_CHAIN_CONFIG_BASE_URL}/${configId}/market-demands`, 
    demandData
  );
  return response.data;
};

export const updateMarketDemand = async (configId, demandId, demandData) => {
  const response = await api.put(
    `${SUPPLY_CHAIN_CONFIG_BASE_URL}/${configId}/market-demands/${demandId}`, 
    demandData
  );
  return response.data;
};

export const deleteMarketDemand = async (configId, demandId) => {
  await api.delete(`${SUPPLY_CHAIN_CONFIG_BASE_URL}/${configId}/market-demands/${demandId}`);
};

// Helper functions
export const getSiteTypeDisplayName = (siteType, definitions = DEFAULT_SITE_TYPE_DEFINITIONS) => {
  if (!siteType) return 'Unknown';
  const map = buildSiteTypeLabelMap(definitions);
  const key = siteType.toString().toLowerCase();
  if (map[key]) return map[key];
  return key
    .split('_')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
};

// Backward compatibility alias
export const getNodeTypeDisplayName = getSiteTypeDisplayName;

export const getSiteTypeColor = (siteType) => {
  const colors = {
    // AWS SC DM types
    customer: 'success',
    distribution_center: 'info',
    warehouse: 'info',
    manufacturing_plant: 'warning',
    vendor: 'primary',
    // Legacy TBG types
    supplier: 'primary',
    retailer: 'success',
    wholesaler: 'error',
    distributor: 'info',
    manufacturer: 'warning',
  };
  return colors[siteType] || 'default';
};

// Backward compatibility alias
export const getNodeTypeColor = getSiteTypeColor;

// Game creation from config
export const createScenarioFromConfig = async (configId, gameData) => {
  const response = await api.post(`${SUPPLY_CHAIN_CONFIG_BASE_URL}/${configId}/create-game`, gameData);
  return response.data;
};

// Get all configurations with minimal data
export const getAllConfigs = async () => {
  const response = await api.get(SUPPLY_CHAIN_CONFIG_BASE_URL);
  return response.data;
};

// Default values for new entities
export const DEFAULT_CONFIG = {
  name: '',
  description: '',
  is_active: false,
  tenant_id: null,
  time_bucket: 'week',
  site_type_definitions: DEFAULT_SITE_TYPE_DEFINITIONS,
};

export const DEFAULT_PRODUCT = {
  name: '',
  description: '',
  unit_cost_range: { min: 0, max: 100 },
};

export const DEFAULT_SITE = {
  name: '',
  type: 'retailer',
};

export const DEFAULT_LANE = {
  from_site_id: null,
  to_site_id: null,
  capacity: 100,
  lead_time_days: { min: 1, max: 3 },
  demand_lead_time: { type: 'deterministic', value: 1 },
  supply_lead_time: { type: 'deterministic', value: 1 },
};

export const DEFAULT_PRODUCT_SITE_CONFIG = {
  product_id: null,
  site_id: null,
  inventory_target_range: { min: 10, max: 50 },
  initial_inventory_range: { min: 20, max: 40 },
  holding_cost_range: { min: 0.5, max: 2 },
  backlog_cost_range: { min: 1, max: 5 },
  selling_price_range: { min: 5, max: 50 },
};

export const DEFAULT_MARKET_DEMAND = {
  product_id: null,  // AWS SC DM compliant (was item_id)
  market_id: null,
  demand_pattern: {
    demand_type: 'constant',
    variability: { type: 'flat', value: 4 },
    seasonality: { type: 'none', amplitude: 0, period: 12, phase: 0 },
    trend: { type: 'none', slope: 0, intercept: 0 },
    parameters: { value: 4 },
    params: { value: 4 },
  },
};

// Classic preset used when creating a new configuration
export const CLASSIC_SUPPLY_CHAIN = {
  products: [
    {
      id: 1,
      name: 'Product 1',
      description: '',
      unit_cost_range: { min: 0, max: 100 },
    },
  ],
  sites: [
    { id: 1, name: 'Market Supply', type: 'market_supply', description: '' },
    { id: 2, name: 'Manufacturer 1', type: 'manufacturer', description: '' },
    { id: 3, name: 'Distributor 1', type: 'distributor', description: '' },
    { id: 4, name: 'Wholesaler 1', type: 'wholesaler', description: '' },
    { id: 5, name: 'Retailer 1', type: 'retailer', description: '' },
    { id: 6, name: 'Market Demand', type: 'market_demand', description: '' },
  ],
  lanes: [
    {
      id: 1,
      from_site_id: 1,
      to_site_id: 2,
      lead_time: 2,
      demand_lead_time: { type: 'deterministic', value: 1 },
      supply_lead_time: { type: 'deterministic', value: 2 },
      capacity: 100,
      cost_per_unit: 1.0,
    },
    {
      id: 2,
      from_site_id: 2,
      to_site_id: 3,
      lead_time: 2,
      demand_lead_time: { type: 'deterministic', value: 1 },
      supply_lead_time: { type: 'deterministic', value: 2 },
      capacity: 100,
      cost_per_unit: 1.0,
    },
    {
      id: 3,
      from_site_id: 3,
      to_site_id: 4,
      lead_time: 2,
      demand_lead_time: { type: 'deterministic', value: 1 },
      supply_lead_time: { type: 'deterministic', value: 2 },
      capacity: 100,
      cost_per_unit: 1.0,
    },
    {
      id: 4,
      from_site_id: 4,
      to_site_id: 5,
      lead_time: 2,
      demand_lead_time: { type: 'deterministic', value: 1 },
      supply_lead_time: { type: 'deterministic', value: 2 },
      capacity: 100,
      cost_per_unit: 1.0,
    },
    {
      id: 5,
      from_site_id: 5,
      to_site_id: 6,
      lead_time: 2,
      demand_lead_time: { type: 'deterministic', value: 1 },
      supply_lead_time: { type: 'deterministic', value: 2 },
      capacity: 100,
      cost_per_unit: 1.0,
    },
  ],
  markets: [
    { id: 1, name: 'Default Market', description: 'Primary demand market' },
  ],
};
