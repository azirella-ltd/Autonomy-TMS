/**
 * TMS Scenario Templates
 *
 * Pre-configured scenario templates for transportation simulations.
 * Each template maps to the existing CreateScenario wizard, providing
 * default roles, parameters, and objectives for TMS-specific use cases.
 */

export const TMS_SCENARIO_TEMPLATES = [
  {
    id: 'freight_tender',
    name: 'Freight Tender Scenario',
    description:
      'Carrier bidding simulation. Shipper agents publish loads, carrier agents bid with rates. ' +
      'Multiple rounds of tender/counter-tender. Tests procurement strategy under market dynamics.',
    category: 'procurement',
    difficulty: 'intermediate',
    estimatedDuration: '45 min',
    roles: [
      { name: 'Shipper Planner', type: 'human', description: 'Publishes loads and evaluates carrier bids' },
      { name: 'Carrier Sales Rep', type: 'human', description: 'Bids on loads and negotiates rates' },
      { name: 'Shipper Agent', type: 'ai', description: 'FreightProcurement TRM — automated tender strategy' },
      { name: 'Carrier Agent', type: 'ai', description: 'Capacity and pricing optimization' },
      { name: 'Market Maker', type: 'ai', description: 'Generates demand and rate signals' },
    ],
    parameters: {
      lanes: 5,
      carriers_per_lane: 3,
      rounds: 8,
      initial_contract_rate: 2.50,
      spot_volatility: 0.15,
      demand_pattern: 'seasonal',
      tender_timeout_seconds: 120,
    },
    objectives: [
      'Understand the carrier waterfall tendering process',
      'Balance cost optimization against service reliability',
      'Recognize when to go spot market or route through a broker',
    ],
    phases: 8,
  },
  {
    id: 'network_disruption',
    name: 'Network Disruption Scenario',
    description:
      'Port strike, weather event, or capacity crunch response. Players manage exception resolution, ' +
      'rerouting, and carrier reallocation under cascading disruptions. Tests crisis response across the network.',
    category: 'disruption',
    difficulty: 'advanced',
    estimatedDuration: '60 min',
    roles: [
      { name: 'Network Planner', type: 'human', description: 'Coordinates rerouting and carrier reallocation' },
      { name: 'Exception Manager', type: 'human', description: 'Triages and resolves shipment exceptions' },
      { name: 'ShipmentTracking Agent', type: 'ai', description: 'In-transit visibility and ETA prediction' },
      { name: 'ExceptionManagement Agent', type: 'ai', description: 'Automated exception detection and resolution' },
      { name: 'FreightProcurement Agent', type: 'ai', description: 'Emergency carrier sourcing' },
      { name: 'Disruption Generator', type: 'ai', description: 'Injects cascading disruption events' },
    ],
    parameters: {
      network_facilities: 8,
      active_shipments: 50,
      disruption_type: 'port_closure',
      cascade_probability: 0.3,
      rounds: 6,
      recovery_target_hours: 48,
    },
    objectives: [
      'Coordinate exception response across multiple facilities',
      'Prioritize critical shipments under constrained capacity',
      'Manage cascading failures without over-reacting',
      'Learn rerouting trade-offs between cost, time, and reliability',
    ],
    phases: 6,
  },
  {
    id: 'mode_selection',
    name: 'Mode Selection Scenario',
    description:
      'Intermodal vs direct routing optimization. Players decide which shipments to route via ' +
      'rail/intermodal vs direct truck given cost, time, and reliability constraints. Tests mode optimization judgment.',
    category: 'optimization',
    difficulty: 'beginner',
    estimatedDuration: '30 min',
    roles: [
      { name: 'Mode Planner', type: 'human', description: 'Assigns shipments to transportation modes' },
      { name: 'IntermodalTransfer Agent', type: 'ai', description: 'Cross-mode transfer coordination' },
      { name: 'LoadBuild Agent', type: 'ai', description: 'Load consolidation and optimization' },
      { name: 'Cost Optimizer', type: 'ai', description: 'Generates cost scenarios for mode comparison' },
    ],
    parameters: {
      shipments: 20,
      lanes_with_rail: 5,
      truck_rate_per_mile: 2.80,
      intermodal_rate_per_mile: 1.60,
      transit_time_penalty_days: 1.5,
      reliability_threshold: 0.90,
      rounds: 5,
    },
    objectives: [
      'Balance cost savings against transit time penalties',
      'Learn when intermodal routing is advantageous',
      'Understand reliability trade-offs between modes',
    ],
    phases: 5,
  },
];

export const getTemplateById = (id) =>
  TMS_SCENARIO_TEMPLATES.find((t) => t.id === id);
