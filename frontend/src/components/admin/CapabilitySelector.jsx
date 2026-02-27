import React, { useState, useMemo } from 'react';
import { cn } from '../../lib/utils/cn';
import { Card, Button, Alert, Badge } from '../common';
import { ChevronDown, Square, CheckSquare, MinusSquare } from 'lucide-react';

/**
 * Capability definitions organized by functional area
 * Based on UI_UX_REQUIREMENTS.md - 59 granular capabilities
 */
const CAPABILITY_TREE = [
  {
    category: 'Strategic Planning',
    capabilities: [
      { id: 'view_network_design', label: 'View Network Design', description: 'View supply chain network configurations' },
      { id: 'manage_network_design', label: 'Manage Network Design', description: 'Create and edit network topologies' },
      { id: 'view_demand_forecasting', label: 'View Demand Forecasting', description: 'View demand forecasts and predictions' },
      { id: 'manage_demand_forecasting', label: 'Manage Demand Forecasting', description: 'Create and edit demand forecasts' },
      { id: 'view_inventory_optimization', label: 'View Inventory Optimization', description: 'View inventory policies and targets' },
      { id: 'manage_inventory_optimization', label: 'Manage Inventory Optimization', description: 'Configure inventory policies' },
      { id: 'view_stochastic_planning', label: 'View Stochastic Planning', description: 'View probabilistic planning scenarios' },
      { id: 'manage_stochastic_planning', label: 'Manage Stochastic Planning', description: 'Configure stochastic parameters' },
    ],
  },
  {
    category: 'Tactical Planning',
    capabilities: [
      { id: 'view_mps', label: 'View MPS', description: 'View Master Production Schedule' },
      { id: 'manage_mps', label: 'Manage MPS', description: 'Create and edit MPS plans' },
      { id: 'approve_mps', label: 'Approve MPS', description: 'Approve MPS plans for execution' },
      { id: 'view_lot_sizing', label: 'View Lot Sizing', description: 'View lot sizing analysis' },
      { id: 'manage_lot_sizing', label: 'Manage Lot Sizing', description: 'Configure lot sizing parameters' },
      { id: 'view_capacity_check', label: 'View Capacity Check', description: 'View capacity utilization and constraints' },
      { id: 'manage_capacity_check', label: 'Manage Capacity Check', description: 'Configure capacity parameters' },
      { id: 'view_mrp', label: 'View MRP', description: 'View Material Requirements Planning' },
      { id: 'manage_mrp', label: 'Manage MRP', description: 'Run MRP and manage exceptions' },
    ],
  },
  {
    category: 'Operational Planning',
    capabilities: [
      { id: 'view_supply_plan', label: 'View Supply Plan', description: 'View generated supply plans' },
      { id: 'manage_supply_plan', label: 'Manage Supply Plan', description: 'Generate and edit supply plans' },
      { id: 'approve_supply_plan', label: 'Approve Supply Plan', description: 'Approve supply plans for execution' },
      { id: 'view_atp_ctp', label: 'View ATP/CTP', description: 'View Available-to-Promise and Capable-to-Promise' },
      { id: 'manage_atp_ctp', label: 'Manage ATP/CTP', description: 'Configure ATP/CTP parameters' },
      { id: 'view_sourcing_allocation', label: 'View Sourcing & Allocation', description: 'View sourcing rules and allocations' },
      { id: 'manage_sourcing_allocation', label: 'Manage Sourcing & Allocation', description: 'Configure sourcing rules' },
      { id: 'view_order_planning', label: 'View Order Planning', description: 'View planned orders' },
      { id: 'manage_order_planning', label: 'Manage Order Planning', description: 'Create and edit planned orders' },
    ],
  },
  {
    category: 'Execution & Monitoring',
    capabilities: [
      { id: 'view_order_management', label: 'View Order Management', description: 'View purchase and transfer orders' },
      { id: 'manage_order_management', label: 'Manage Order Management', description: 'Create and edit orders' },
      { id: 'approve_orders', label: 'Approve Orders', description: 'Approve orders for release' },
      { id: 'view_shipment_tracking', label: 'View Shipment Tracking', description: 'Track shipments and deliveries' },
      { id: 'manage_shipment_tracking', label: 'Manage Shipment Tracking', description: 'Update shipment status' },
      { id: 'view_inventory_visibility', label: 'View Inventory Visibility', description: 'View inventory levels across network' },
      { id: 'manage_inventory_visibility', label: 'Manage Inventory Visibility', description: 'Adjust inventory levels' },
      { id: 'view_ntier_visibility', label: 'View N-Tier Visibility', description: 'View multi-tier supply chain visibility' },
    ],
  },
  {
    category: 'Analytics & Insights',
    capabilities: [
      { id: 'view_analytics', label: 'View Analytics', description: 'View supply chain analytics dashboards' },
      { id: 'view_kpi_monitoring', label: 'View KPI Monitoring', description: 'View KPI dashboards and alerts' },
      { id: 'manage_kpi_monitoring', label: 'Manage KPI Monitoring', description: 'Configure KPI thresholds and alerts' },
      { id: 'view_scenario_comparison', label: 'View Scenario Comparison', description: 'View scenario analysis' },
      { id: 'manage_scenario_comparison', label: 'Manage Scenario Comparison', description: 'Create and run scenarios' },
      { id: 'view_risk_analysis', label: 'View Risk Analysis', description: 'View supply chain risk analysis' },
      { id: 'manage_risk_analysis', label: 'Manage Risk Analysis', description: 'Configure risk parameters' },
    ],
  },
  {
    category: 'AI & Agents',
    capabilities: [
      { id: 'view_ai_agents', label: 'View AI Agents', description: 'View AI agent configurations' },
      { id: 'manage_ai_agents', label: 'Manage AI Agents', description: 'Configure and deploy AI agents' },
      { id: 'view_trm_training', label: 'View TRM Training', description: 'View TRM training status' },
      { id: 'manage_trm_training', label: 'Manage TRM Training', description: 'Train and manage TRM models' },
      { id: 'view_gnn_training', label: 'View GNN Training', description: 'View GNN training status' },
      { id: 'manage_gnn_training', label: 'Manage GNN Training', description: 'Train and manage GNN models' },
      { id: 'view_llm_agents', label: 'View LLM Agents', description: 'View LLM agent performance' },
      { id: 'manage_llm_agents', label: 'Manage LLM Agents', description: 'Configure LLM agents' },
    ],
  },
  {
    category: 'Simulation',
    capabilities: [
      { id: 'view_simulations', label: 'View Scenarios', description: 'View simulation sessions' },
      { id: 'create_simulation', label: 'Create Scenarios', description: 'Create new simulation sessions' },
      { id: 'play_simulation', label: 'Run Scenarios', description: 'Participate in scenarios' },
      { id: 'manage_simulations', label: 'Manage Scenarios', description: 'Administer simulation sessions' },
      { id: 'view_scenario_analytics', label: 'View Game Analytics', description: 'View game performance metrics' },
    ],
  },
  {
    category: 'Administration',
    capabilities: [
      { id: 'view_users', label: 'View Users', description: 'View user list' },
      { id: 'create_user', label: 'Create Users', description: 'Create new users' },
      { id: 'edit_user', label: 'Edit Users', description: 'Edit user details' },
      { id: 'manage_permissions', label: 'Manage Permissions', description: 'Assign user capabilities' },
      { id: 'view_tenants', label: 'View Organizations', description: 'View organization information' },
      { id: 'manage_tenants', label: 'Manage Organizations', description: 'Configure organization settings' },
    ],
  },
];

/**
 * Custom Checkbox component for Autonomy UI Kit
 */
const Checkbox = ({
  checked = false,
  indeterminate = false,
  onChange,
  disabled = false,
  className,
  size = 'default',
}) => {
  const handleClick = (e) => {
    e.stopPropagation();
    if (!disabled && onChange) {
      onChange(!checked);
    }
  };

  const sizeClasses = {
    small: 'h-4 w-4',
    default: 'h-5 w-5',
  };

  const iconSize = size === 'small' ? 16 : 20;

  const Icon = indeterminate ? MinusSquare : checked ? CheckSquare : Square;

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={disabled}
      className={cn(
        'inline-flex items-center justify-center rounded transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
        disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:text-primary',
        checked || indeterminate ? 'text-primary' : 'text-muted-foreground',
        sizeClasses[size],
        className
      )}
    >
      <Icon size={iconSize} />
    </button>
  );
};

/**
 * Accordion component for Autonomy UI Kit
 */
const Accordion = ({ children, expanded, onChange, disabled = false }) => {
  return (
    <div className={cn('border-b border-border', disabled && 'opacity-50')}>
      {children}
    </div>
  );
};

const AccordionSummary = ({ children, expanded, onToggle, expandIcon, disabled = false }) => {
  return (
    <button
      type="button"
      onClick={!disabled ? onToggle : undefined}
      disabled={disabled}
      className={cn(
        'flex w-full items-center justify-between py-4 px-4 text-left',
        'hover:bg-muted/50 transition-colors',
        disabled && 'cursor-not-allowed'
      )}
    >
      <div className="flex-1">{children}</div>
      <div
        className={cn(
          'transition-transform duration-200',
          expanded && 'rotate-180'
        )}
      >
        {expandIcon}
      </div>
    </button>
  );
};

const AccordionDetails = ({ children, expanded }) => {
  if (!expanded) return null;
  return (
    <div className="pb-4 px-4">
      {children}
    </div>
  );
};

/**
 * CapabilitySelector Component
 *
 * Hierarchical checkbox tree for selecting user capabilities.
 * Supports Select All, Deselect All, and category-level selection.
 *
 * @param {Object} props
 * @param {string[]} props.selectedCapabilities - Array of selected capability IDs
 * @param {Function} props.onChange - Callback when selection changes
 * @param {boolean} props.disabled - Disable all interactions
 * @param {string[]} props.disabledCapabilities - Array of capability IDs to disable
 */
const CapabilitySelector = ({
  selectedCapabilities = [],
  onChange,
  disabled = false,
  disabledCapabilities = [],
}) => {
  const [expandedCategories, setExpandedCategories] = useState([]);

  /**
   * Calculate selection state for each category
   */
  const categoryStates = useMemo(() => {
    const states = {};
    CAPABILITY_TREE.forEach(category => {
      const categoryCapIds = category.capabilities.map(c => c.id);
      const selectedCount = categoryCapIds.filter(id => selectedCapabilities.includes(id)).length;
      const totalCount = categoryCapIds.length;

      states[category.category] = {
        checked: selectedCount === totalCount,
        indeterminate: selectedCount > 0 && selectedCount < totalCount,
        selectedCount,
        totalCount,
      };
    });
    return states;
  }, [selectedCapabilities]);

  /**
   * Handle individual capability toggle
   */
  const handleCapabilityToggle = (capabilityId) => {
    if (disabled || disabledCapabilities.includes(capabilityId)) return;

    const newSelected = selectedCapabilities.includes(capabilityId)
      ? selectedCapabilities.filter(id => id !== capabilityId)
      : [...selectedCapabilities, capabilityId];

    onChange(newSelected);
  };

  /**
   * Handle category-level toggle (select/deselect all in category)
   */
  const handleCategoryToggle = (category) => {
    if (disabled) return;

    const categoryCapIds = category.capabilities
      .filter(c => !disabledCapabilities.includes(c.id))
      .map(c => c.id);

    const state = categoryStates[category.category];

    if (state.checked) {
      // Deselect all in category
      const newSelected = selectedCapabilities.filter(id => !categoryCapIds.includes(id));
      onChange(newSelected);
    } else {
      // Select all in category
      const newSelected = [...new Set([...selectedCapabilities, ...categoryCapIds])];
      onChange(newSelected);
    }
  };

  /**
   * Handle Select All button
   */
  const handleSelectAll = () => {
    if (disabled) return;

    const allCapIds = CAPABILITY_TREE.flatMap(cat =>
      cat.capabilities
        .filter(c => !disabledCapabilities.includes(c.id))
        .map(c => c.id)
    );
    onChange(allCapIds);
  };

  /**
   * Handle Deselect All button
   */
  const handleDeselectAll = () => {
    if (disabled) return;
    onChange([]);
  };

  /**
   * Handle Expand All / Collapse All
   */
  const handleExpandAll = () => {
    setExpandedCategories(CAPABILITY_TREE.map(cat => cat.category));
  };

  const handleCollapseAll = () => {
    setExpandedCategories([]);
  };

  return (
    <div>
      {/* Header with action buttons */}
      <div className="flex justify-between items-center mb-4">
        <h6 className="text-lg font-semibold text-foreground">Capabilities</h6>
        <div className="flex gap-2">
          <Button size="sm" variant="ghost" onClick={handleExpandAll} disabled={disabled}>
            Expand All
          </Button>
          <Button size="sm" variant="ghost" onClick={handleCollapseAll} disabled={disabled}>
            Collapse All
          </Button>
          <Button size="sm" variant="ghost" onClick={handleSelectAll} disabled={disabled}>
            Select All
          </Button>
          <Button size="sm" variant="ghost" onClick={handleDeselectAll} disabled={disabled}>
            Deselect All
          </Button>
        </div>
      </div>

      {/* Selection summary */}
      <Alert variant="info" className="mb-4">
        <span className="text-sm">
          <strong>{selectedCapabilities.length}</strong> of{' '}
          <strong>
            {CAPABILITY_TREE.reduce((sum, cat) => sum + cat.capabilities.length, 0)}
          </strong>{' '}
          capabilities selected
        </span>
      </Alert>

      {/* Capability tree */}
      <Card variant="outlined" padding="none">
        {CAPABILITY_TREE.map((category, index) => {
          const isExpanded = expandedCategories.includes(category.category);
          const state = categoryStates[category.category];

          return (
            <Accordion
              key={category.category}
              expanded={isExpanded}
              disabled={disabled}
            >
              <AccordionSummary
                expanded={isExpanded}
                onToggle={() => {
                  setExpandedCategories(prev =>
                    isExpanded
                      ? prev.filter(c => c !== category.category)
                      : [...prev, category.category]
                  );
                }}
                expandIcon={<ChevronDown className="h-5 w-5 text-muted-foreground" />}
                disabled={disabled}
              >
                <div className="flex items-center w-full">
                  <Checkbox
                    checked={state.checked}
                    indeterminate={state.indeterminate}
                    onChange={() => handleCategoryToggle(category)}
                    disabled={disabled}
                    className="mr-3"
                  />
                  <span className="text-base font-semibold text-foreground">
                    {category.category}
                  </span>
                  <Badge
                    variant={state.checked ? 'default' : 'secondary'}
                    size="sm"
                    className="ml-3"
                  >
                    {state.selectedCount}/{state.totalCount}
                  </Badge>
                </div>
              </AccordionSummary>
              <AccordionDetails expanded={isExpanded}>
                <div className="space-y-2">
                  {category.capabilities.map((capability) => {
                    const isDisabled = disabled || disabledCapabilities.includes(capability.id);
                    const isSelected = selectedCapabilities.includes(capability.id);

                    return (
                      <div key={capability.id} className="pl-8">
                        <label
                          className={cn(
                            'flex items-start gap-3 cursor-pointer',
                            isDisabled && 'cursor-not-allowed opacity-50'
                          )}
                        >
                          <Checkbox
                            checked={isSelected}
                            onChange={() => handleCapabilityToggle(capability.id)}
                            disabled={isDisabled}
                            size="small"
                            className="mt-0.5"
                          />
                          <div className="flex-1">
                            <span
                              className={cn(
                                'text-sm block',
                                isSelected ? 'font-semibold' : 'font-normal'
                              )}
                            >
                              {capability.label}
                            </span>
                            <span className="text-xs text-muted-foreground">
                              {capability.description}
                            </span>
                          </div>
                        </label>
                      </div>
                    );
                  })}
                </div>
              </AccordionDetails>
            </Accordion>
          );
        })}
      </Card>
    </div>
  );
};

export default CapabilitySelector;
