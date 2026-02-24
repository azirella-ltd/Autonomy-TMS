// Utility functions to transform game data for visualization components

/**
 * Transform scenarioUsers data to sites format for 3D/geospatial visualizations
 * @param {Array} scenarioUsers - Array of scenarioUser objects from game state
 * @param {Object} supplyChainConfig - Supply chain configuration with site metadata
 * @returns {Array} Array of site objects with id, role, name, location
 */
export function transformPlayersToSites(scenarioUsers, supplyChainConfig = null) {
  if (!scenarioUsers || !Array.isArray(scenarioUsers)) return [];

  return users.map((scenarioUser) => {
    const site = {
      id: user.scenario_user_id || user.id,
      name: user.scenario_user_name || user.name || `ScenarioUser ${user.scenario_user_id}`,
      role: user.role || user.sc_site_type || user.sc_node_type || 'unknown',
    };

    // Add location data if available from supply chain config
    if (supplyChainConfig?.sites) {
      const configSite = supplyChainConfig.sites.find(
        (n) => n.id === user.site_id || n.name === user.site_name
      );
      if (configSite && configSite.location) {
        site.latitude = configSite.location.latitude;
        site.longitude = configSite.location.longitude;
        site.location = configSite.location.name;
      }
    }

    // Fallback: Generate approximate locations based on role
    if (!site.latitude || !site.longitude) {
      const generatedLocation = generateLocationByRole(site.role, user.scenario_user_id);
      site.latitude = generatedLocation.latitude;
      site.longitude = generatedLocation.longitude;
      site.location = generatedLocation.name;
    }

    return site;
  });
}

// Backward compatibility alias
export const transformPlayersToNodes = transformPlayersToSites;

/**
 * Generate approximate geographic locations based on supply chain role
 * @param {string} role - ScenarioUser role (retailer, wholesaler, distributor, factory, supplier)
 * @param {number} scenarioUserId - ScenarioUser ID for variation
 * @returns {Object} Location with latitude, longitude, name
 */
function generateLocationByRole(role, scenarioUserId = 0) {
  const roleNormalized = (role || '').toLowerCase();
  const variation = (scenarioUserId % 5) * 2; // Add variation for multiple sites of same role

  // Approximate US locations by supply chain tier
  const locations = {
    retailer: [
      { latitude: 40.7128 + variation, longitude: -74.006, name: 'New York' },
      { latitude: 34.0522 + variation, longitude: -118.2437, name: 'Los Angeles' },
      { latitude: 41.8781 + variation, longitude: -87.6298, name: 'Chicago' },
      { latitude: 29.7604 + variation, longitude: -95.3698, name: 'Houston' },
      { latitude: 33.4484 + variation, longitude: -112.074, name: 'Phoenix' },
    ],
    wholesaler: [
      { latitude: 39.7392 + variation, longitude: -104.9903, name: 'Denver' },
      { latitude: 33.749 + variation, longitude: -84.388, name: 'Atlanta' },
      { latitude: 32.7767 + variation, longitude: -96.797, name: 'Dallas' },
      { latitude: 37.7749 + variation, longitude: -122.4194, name: 'San Francisco' },
      { latitude: 47.6062 + variation, longitude: -122.3321, name: 'Seattle' },
    ],
    distributor: [
      { latitude: 39.0997 + variation, longitude: -94.5786, name: 'Kansas City' },
      { latitude: 36.1627 + variation, longitude: -86.7816, name: 'Nashville' },
      { latitude: 35.2271 + variation, longitude: -80.8431, name: 'Charlotte' },
      { latitude: 38.9072 + variation, longitude: -77.0369, name: 'Washington DC' },
      { latitude: 42.3601 + variation, longitude: -71.0589, name: 'Boston' },
    ],
    factory: [
      { latitude: 42.3314 + variation, longitude: -83.0458, name: 'Detroit' },
      { latitude: 39.9612 + variation, longitude: -82.9988, name: 'Columbus' },
      { latitude: 35.0456 + variation, longitude: -85.3097, name: 'Chattanooga' },
      { latitude: 43.0389 + variation, longitude: -87.9065, name: 'Milwaukee' },
      { latitude: 41.2565 + variation, longitude: -95.9345, name: 'Omaha' },
    ],
    supplier: [
      { latitude: 30.2672 + variation, longitude: -97.7431, name: 'Austin' },
      { latitude: 45.5152 + variation, longitude: -122.6784, name: 'Portland' },
      { latitude: 44.9778 + variation, longitude: -93.265, name: 'Minneapolis' },
      { latitude: 39.7684 + variation, longitude: -86.1581, name: 'Indianapolis' },
      { latitude: 38.5816 + variation, longitude: -121.4944, name: 'Sacramento' },
    ],
  };

  const roleLocations = locations[roleNormalized] || locations.retailer;
  return roleLocations[scenarioUserId % roleLocations.length];
}

/**
 * Transform connections/lanes to edges format for visualizations
 * @param {Array} scenarioUsers - Array of scenarioUser objects
 * @param {Object} supplyChainConfig - Supply chain configuration with lanes
 * @returns {Array} Array of edge objects with from, to, flowSpeed
 */
export function transformConnectionsToEdges(scenarioUsers, supplyChainConfig = null) {
  if (!scenarioUsers || !Array.isArray(scenarioUsers)) return [];

  const edges = [];

  // Method 1: Extract from scenarioUser upstream/downstream relationships
  users.forEach((scenarioUser) => {
    if (user.upstream_scenario_user_id) {
      edges.push({
        from: user.scenario_user_id || user.id,
        to: user.upstream_scenario_user_id,
        flowSpeed: 1,
      });
    }
    if (user.downstream_scenario_user_id) {
      edges.push({
        from: user.downstream_scenario_user_id,
        to: user.scenario_user_id || user.id,
        flowSpeed: 1,
      });
    }
  });

  // Method 2: Extract from supply chain config lanes
  if (supplyChainConfig && supplyChainConfig.lanes) {
    supplyChainConfig.lanes.forEach((lane) => {
      // Find scenarioUser IDs that correspond to these sites
      const fromPlayer = users.find((p) => p.site_id === lane.from_site_id);
      const toPlayer = users.find((p) => p.site_id === lane.to_site_id);

      if (fromPlayer && toPlayer) {
        edges.push({
          from: fromPlayer.scenario_user_id || fromPlayer.id,
          to: toPlayer.scenario_user_id || toPlayer.id,
          flowSpeed: 1,
        });
      }
    });
  }

  // Remove duplicates
  const uniqueEdges = edges.filter(
    (edge, index, self) =>
      index === self.findIndex((e) => e.from === edge.from && e.to === edge.to)
  );

  return uniqueEdges;
}

/**
 * Build inventory data object for current game state
 * @param {Array} scenarioUsers - Array of scenarioUser objects with current state
 * @returns {Object} Inventory data keyed by scenarioUser ID
 */
export function buildInventoryData(scenarioUsers) {
  if (!scenarioUsers || !Array.isArray(scenarioUsers)) return {};

  const inventoryData = {};

  users.forEach((scenarioUser) => {
    const scenarioUserId = user.scenario_user_id || user.id;
    inventoryData[scenarioUserId] = {
      inventory: user.inventory_end ?? user.inventory ?? 0,
      backlog: user.backlog ?? 0,
      cost: user.total_cost ?? user.cost ?? 0,
      order_placed: user.order_placed ?? user.last_order ?? 0,
      incoming_order: user.incoming_order ?? user.demand ?? 0,
    };
  });

  return inventoryData;
}

/**
 * Identify active flows based on recent order activity
 * @param {Array} scenarioUsers - Array of scenarioUser objects with order data
 * @param {number} threshold - Minimum order quantity to consider flow active
 * @returns {Array} Array of edge IDs (e.g., ["1-2", "2-3"]) with active flows
 */
export function identifyActiveFlows(scenarioUsers, threshold = 1) {
  if (!scenarioUsers || !Array.isArray(scenarioUsers)) return [];

  const activeFlows = [];

  users.forEach((scenarioUser) => {
    const scenarioUserId = user.scenario_user_id || user.id;
    const orderPlaced = user.order_placed ?? user.last_order ?? 0;

    if (orderPlaced >= threshold && user.upstream_scenario_user_id) {
      activeFlows.push(`${scenarioUserId}-${user.upstream_scenario_user_id}`);
    }
  });

  return activeFlows;
}

/**
 * Transform game history (rounds) for TimelineVisualization
 * @param {Array} rounds - Array of round objects from game history
 * @returns {Array} Formatted game history with scenarioUser data per round
 */
export function transformGameHistory(rounds) {
  if (!rounds || !Array.isArray(rounds)) return [];

  return rounds.map((round) => ({
    round_number: round.round_number,
    scenarioUsers: round.scenarioUsers || round.player_rounds || [],
    timestamp: round.created_at || round.timestamp,
  }));
}

/**
 * Extract supply chain structure from game state
 * @param {Object} gameState - Full game state object
 * @returns {Object} Object with sites, edges, inventoryData, activeFlows
 */
export function extractVisualizationData(gameState) {
  if (!gameState) {
    return {
      sites: [],
      edges: [],
      inventoryData: {},
      activeFlows: [],
    };
  }

  const scenarioUsers = gameState.scenarioUsers || [];
  const supplyChainConfig = gameState.supply_chain_config || null;

  const sites = transformPlayersToSites(scenarioUsers, supplyChainConfig);
  const edges = transformConnectionsToEdges(scenarioUsers, supplyChainConfig);
  const inventoryData = buildInventoryData(scenarioUsers);
  const activeFlows = identifyActiveFlows(scenarioUsers);

  return {
    sites,
    edges,
    inventoryData,
    activeFlows,
  };
}

/**
 * Check if a site has valid geospatial coordinates
 * @param {Object} site - Site object
 * @returns {boolean} True if site has valid lat/lon
 */
export function hasValidCoordinates(site) {
  return (
    site &&
    typeof site.latitude === 'number' &&
    typeof site.longitude === 'number' &&
    !isNaN(site.latitude) &&
    !isNaN(site.longitude) &&
    site.latitude >= -90 &&
    site.latitude <= 90 &&
    site.longitude >= -180 &&
    site.longitude <= 180
  );
}
