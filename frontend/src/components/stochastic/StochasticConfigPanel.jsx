import React, { useState } from 'react';
import {
  ChevronDown,
  ChevronUp,
  Save,
  RefreshCw
} from 'lucide-react';
import { Card } from '../common/Card';
import { Button } from '../common/Button';
import { Badge } from '../common/Badge';
import { Alert } from '../common/Alert';
import { Tabs, TabsList, Tab, TabPanel } from '../common/Tabs';
import DistributionBuilder from './DistributionBuilder';
import DistributionPreview from './DistributionPreview';
import DistributionTemplates from './DistributionTemplates';

/**
 * Stochastic Configuration Panel
 *
 * Complete panel for configuring stochastic distributions for supply chain variables.
 * Integrates DistributionBuilder, DistributionPreview, and DistributionTemplates.
 *
 * Features:
 * - Configure distributions for 11 operational variables
 * - Tabbed interface (Builder / Templates / Preview)
 * - Save/load configurations
 * - Visual preview of distributions
 * - Apply templates to variables
 *
 * Props:
 * - config: Current configuration object (with distribution fields)
 * - onChange: Callback when configuration changes
 * - onSave: Optional callback to save configuration
 * - variableGroups: Group variables by category for organization
 */

// Variable definitions with metadata
const VARIABLE_DEFINITIONS = {
  // Lead Time Variables
  sourcing_lead_time: {
    label: 'Sourcing Lead Time',
    description: 'Time from order placement to material arrival',
    field: 'sourcing_lead_time_dist',
    category: 'Lead Times',
    defaultValue: 7,
    unit: 'days',
    variableType: 'lead_time'
  },
  vendor_lead_time: {
    label: 'Vendor Lead Time',
    description: 'Vendor-specific lead time',
    field: 'lead_time_dist',
    category: 'Lead Times',
    defaultValue: 7,
    unit: 'days',
    variableType: 'lead_time'
  },
  mfg_lead_time: {
    label: 'Manufacturing Lead Time',
    description: 'Time to produce finished goods',
    field: 'mfg_lead_time_dist',
    category: 'Lead Times',
    defaultValue: 14,
    unit: 'time units',
    variableType: 'lead_time'
  },
  cycle_time: {
    label: 'Cycle Time',
    description: 'Time per production cycle',
    field: 'cycle_time_dist',
    category: 'Production Times',
    defaultValue: 1,
    unit: 'time units',
    variableType: 'lead_time'
  },
  setup_time: {
    label: 'Setup Time',
    description: 'Time to set up production',
    field: 'setup_time_dist',
    category: 'Production Times',
    defaultValue: 2,
    unit: 'time units',
    variableType: 'lead_time'
  },
  changeover_time: {
    label: 'Changeover Time',
    description: 'Time to change between products',
    field: 'changeover_time_dist',
    category: 'Production Times',
    defaultValue: 1,
    unit: 'time units',
    variableType: 'lead_time'
  },

  // Capacity Variables
  capacity: {
    label: 'Production Capacity',
    description: 'Maximum production capacity per period',
    field: 'capacity_dist',
    category: 'Capacity',
    defaultValue: 100,
    unit: 'units',
    variableType: 'capacity'
  },

  // Yield Variables
  yield: {
    label: 'Manufacturing Yield',
    description: 'Percentage of good units produced',
    field: 'yield_dist',
    category: 'Yields',
    defaultValue: 100,
    unit: '%',
    variableType: 'yield'
  },
  scrap_rate: {
    label: 'Scrap Rate',
    description: 'Percentage of material scrapped',
    field: 'scrap_rate_dist',
    category: 'Yields',
    defaultValue: 0,
    unit: '%',
    variableType: 'yield'
  },

  // Demand Variables
  demand: {
    label: 'Market Demand',
    description: 'Customer demand quantity',
    field: 'demand_dist',
    category: 'Demand',
    defaultValue: 100,
    unit: 'units',
    variableType: 'demand'
  },
  forecast_error: {
    label: 'Forecast Error',
    description: 'Error in demand forecast',
    field: 'forecast_error_dist',
    category: 'Demand',
    defaultValue: 0,
    unit: 'units',
    variableType: 'demand'
  }
};

// Group variables by category
const VARIABLE_GROUPS = {
  'Lead Times': ['sourcing_lead_time', 'vendor_lead_time', 'mfg_lead_time'],
  'Production Times': ['cycle_time', 'setup_time', 'changeover_time'],
  'Capacity': ['capacity'],
  'Yields': ['yield', 'scrap_rate'],
  'Demand': ['demand', 'forecast_error']
};

/**
 * Collapsible Accordion Component
 */
const Accordion = ({ title, expanded, onToggle, badge, children }) => {
  return (
    <div className="border border-border rounded-lg mb-2 overflow-hidden">
      <button
        type="button"
        className="w-full flex items-center justify-between p-4 bg-muted/30 hover:bg-muted/50 transition-colors"
        onClick={onToggle}
      >
        <div className="flex items-center gap-3">
          <h3 className="text-base font-semibold">{title}</h3>
          {badge}
        </div>
        {expanded ? (
          <ChevronUp className="h-5 w-5 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-5 w-5 text-muted-foreground" />
        )}
      </button>
      {expanded && (
        <div className="p-4 border-t border-border">
          {children}
        </div>
      )}
    </div>
  );
};

const StochasticConfigPanel = ({
  config = {},
  onChange,
  onSave = null,
  variableGroups = VARIABLE_GROUPS,
  disabled = false
}) => {
  const [expandedGroups, setExpandedGroups] = useState({});
  const [activeTab, setActiveTab] = useState('builder');
  const [previewData, setPreviewData] = useState({});
  const [previewLoading, setPreviewLoading] = useState({});
  const [previewErrors, setPreviewErrors] = useState({});
  const [selectedVariable, setSelectedVariable] = useState(null);

  // Handle distribution change for a variable
  const handleDistributionChange = (variableKey, newConfig) => {
    const variable = VARIABLE_DEFINITIONS[variableKey];
    if (!variable || !onChange) return;

    const updatedConfig = {
      ...config,
      [variable.field]: newConfig
    };

    onChange(updatedConfig);
  };

  // Handle template selection
  const handleTemplateSelect = (variableKey, templateConfig) => {
    handleDistributionChange(variableKey, templateConfig);
    setActiveTab('builder'); // Switch back to builder to see applied config
  };

  // Handle preview generation
  const handlePreview = async (variableKey, distConfig) => {
    setPreviewLoading({ ...previewLoading, [variableKey]: true });
    setPreviewErrors({ ...previewErrors, [variableKey]: null });

    try {
      // Call backend API to generate samples
      const response = await fetch('/api/v1/stochastic/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          config: distConfig,
          num_samples: 1000
        })
      });

      if (!response.ok) {
        throw new Error('Failed to generate preview');
      }

      const data = await response.json();
      setPreviewData({ ...previewData, [variableKey]: data.samples });
    } catch (error) {
      setPreviewErrors({ ...previewErrors, [variableKey]: error.message });
    } finally {
      setPreviewLoading({ ...previewLoading, [variableKey]: false });
    }
  };

  // Handle accordion expansion
  const handleAccordionChange = (category) => {
    setExpandedGroups({
      ...expandedGroups,
      [category]: !expandedGroups[category]
    });
  };

  // Check if variable has stochastic config
  const isStochastic = (variableKey) => {
    const variable = VARIABLE_DEFINITIONS[variableKey];
    const distConfig = config[variable.field];
    return distConfig && distConfig.type !== 'deterministic';
  };

  // Get current config for variable
  const getVariableConfig = (variableKey) => {
    const variable = VARIABLE_DEFINITIONS[variableKey];
    return config[variable.field] || null;
  };

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <h2 className="text-xl font-semibold mb-2">
          Stochastic Distribution Configuration
        </h2>
        <Alert variant="info">
          Configure probability distributions for operational variables to model supply chain uncertainty.
          Leave as deterministic (default) for fixed values.
        </Alert>
      </div>

      {/* Save Button */}
      {onSave && (
        <div className="mb-4 flex justify-end">
          <Button
            leftIcon={<Save className="h-4 w-4" />}
            onClick={onSave}
            disabled={disabled}
          >
            Save Configuration
          </Button>
        </div>
      )}

      {/* Variable Groups */}
      {Object.entries(variableGroups).map(([category, variables]) => (
        <Accordion
          key={category}
          title={category}
          expanded={expandedGroups[category] || false}
          onToggle={() => handleAccordionChange(category)}
          badge={
            <Badge
              variant={variables.some(isStochastic) ? 'default' : 'secondary'}
              size="sm"
            >
              {variables.filter(isStochastic).length}/{variables.length} stochastic
            </Badge>
          }
        >
          {variables.map(variableKey => {
            const variable = VARIABLE_DEFINITIONS[variableKey];
            const currentConfig = getVariableConfig(variableKey);

            return (
              <Card key={variableKey} className="p-4 mb-4 last:mb-0">
                {/* Variable Header */}
                <div className="mb-4">
                  <div className="flex items-center justify-between mb-1">
                    <h4 className="text-base font-semibold">
                      {variable.label}
                    </h4>
                    {isStochastic(variableKey) && (
                      <Badge variant="default" size="sm">Stochastic</Badge>
                    )}
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {variable.description} (Default: {variable.defaultValue} {variable.unit})
                  </p>
                </div>

                {/* Tabs */}
                <Tabs value={activeTab} onChange={(e, v) => setActiveTab(v)}>
                  <TabsList className="mb-4">
                    <Tab value="builder" label="Builder" />
                    <Tab value="templates" label="Templates" />
                    <Tab value="preview" label="Preview" />
                  </TabsList>

                  {/* Builder Tab */}
                  <TabPanel value="builder">
                    <DistributionBuilder
                      value={currentConfig}
                      onChange={(newConfig) => handleDistributionChange(variableKey, newConfig)}
                      variable={variable.label}
                      disabled={disabled}
                      onPreview={(config) => handlePreview(variableKey, config)}
                      showPreview={true}
                    />
                  </TabPanel>

                  {/* Templates Tab */}
                  <TabPanel value="templates">
                    <DistributionTemplates
                      onSelect={(templateConfig) => handleTemplateSelect(variableKey, templateConfig)}
                      variableType={variable.variableType}
                    />
                  </TabPanel>

                  {/* Preview Tab */}
                  <TabPanel value="preview">
                    <DistributionPreview
                      data={previewData[variableKey]}
                      config={currentConfig}
                      loading={previewLoading[variableKey]}
                      error={previewErrors[variableKey]}
                    />
                  </TabPanel>
                </Tabs>
              </Card>
            );
          })}
        </Accordion>
      ))}

      {/* Summary */}
      <Card className="p-4 mt-4">
        <h3 className="text-base font-semibold mb-2">
          Configuration Summary
        </h3>
        <div className="space-y-1 text-sm">
          <p>
            Total Variables: {Object.keys(VARIABLE_DEFINITIONS).length}
          </p>
          <p>
            Stochastic: {Object.keys(VARIABLE_DEFINITIONS).filter(isStochastic).length}
          </p>
          <p>
            Deterministic: {Object.keys(VARIABLE_DEFINITIONS).filter(k => !isStochastic(k)).length}
          </p>
        </div>
      </Card>
    </div>
  );
};

export default StochasticConfigPanel;
