import React, { useState } from 'react';
import {
  Copy,
  Pencil
} from 'lucide-react';
import { Card, CardContent, CardFooter, Button, Badge, Textarea, FormField } from '../common';
import { Modal, ModalHeader, ModalTitle, ModalBody, ModalFooter } from '../common/Modal';
import { Select, SelectOption } from '../common/Select';

/**
 * Distribution Templates Component
 *
 * Pre-configured distribution templates for common supply chain scenarios.
 * Users can select and apply templates to quickly configure stochastic variables.
 *
 * Features:
 * - Pre-built templates for common variability levels
 * - Templates for different variable types (lead time, capacity, yield, demand)
 * - Quick apply functionality
 * - Visual variability indicators
 *
 * Props:
 * - onSelect: Callback when template is selected (config)
 * - variableType: Type of variable (lead_time, capacity, yield, demand) for filtering
 */

// Template library
const TEMPLATE_LIBRARY = {
  // Lead Time Templates
  lead_time_low_variability: {
    name: 'Lead Time - Low Variability (CV=10%)',
    description: 'Stable lead times with minimal variation. Typical for local suppliers.',
    variability: 'low',
    category: 'Lead Time',
    config: {
      type: 'normal',
      mean: 7.0,
      stddev: 0.7,
      min: 5.0,
      max: 9.0
    },
    useCase: 'Local suppliers, reliable transportation'
  },
  lead_time_medium_variability: {
    name: 'Lead Time - Medium Variability (CV=25%)',
    description: 'Moderate lead time variation. Typical for domestic shipping.',
    variability: 'medium',
    category: 'Lead Time',
    config: {
      type: 'normal',
      mean: 7.0,
      stddev: 1.75,
      min: 3.0,
      max: 12.0
    },
    useCase: 'Domestic shipping, moderate reliability'
  },
  lead_time_high_variability: {
    name: 'Lead Time - High Variability (CV=50%)',
    description: 'High lead time uncertainty. Typical for international or unreliable routes.',
    variability: 'high',
    category: 'Lead Time',
    config: {
      type: 'lognormal',
      mean_log: 1.8,
      stddev_log: 0.4,
      min: 3.0,
      max: 20.0
    },
    useCase: 'International shipping, unreliable suppliers'
  },
  lead_time_disruption: {
    name: 'Lead Time - With Disruptions',
    description: 'Normal operations with occasional severe disruptions (5% chance).',
    variability: 'very high',
    category: 'Lead Time',
    config: {
      type: 'mixture',
      components: [
        {
          weight: 0.95,
          distribution: { type: 'normal', mean: 7.0, stddev: 1.0 }
        },
        {
          weight: 0.05,
          distribution: { type: 'uniform', min: 20.0, max: 30.0 }
        }
      ]
    },
    useCase: 'Supply chains with disruption risk'
  },

  // Capacity Templates
  capacity_low_variability: {
    name: 'Capacity - Low Variability (CV=10%)',
    description: 'Stable production capacity. Well-maintained equipment.',
    variability: 'low',
    category: 'Capacity',
    config: {
      type: 'truncated_normal',
      mean: 100.0,
      stddev: 10.0,
      min: 80.0,
      max: 120.0
    },
    useCase: 'Modern facilities, preventive maintenance'
  },
  capacity_medium_variability: {
    name: 'Capacity - Medium Variability (CV=20%)',
    description: 'Moderate capacity fluctuations. Some equipment variability.',
    variability: 'medium',
    category: 'Capacity',
    config: {
      type: 'truncated_normal',
      mean: 100.0,
      stddev: 20.0,
      min: 60.0,
      max: 140.0
    },
    useCase: 'Typical manufacturing, aging equipment'
  },
  capacity_high_variability: {
    name: 'Capacity - High Variability (CV=30%)',
    description: 'Significant capacity uncertainty. Unreliable equipment or labor.',
    variability: 'high',
    category: 'Capacity',
    config: {
      type: 'gamma',
      shape: 11.0,
      scale: 9.0,
      min: 40.0
    },
    useCase: 'Unreliable equipment, variable labor availability'
  },

  // Yield Templates
  yield_excellent: {
    name: 'Yield - Excellent (98-100%)',
    description: 'Very high yield with minimal defects. Well-controlled process.',
    variability: 'low',
    category: 'Yield',
    config: {
      type: 'beta',
      alpha: 98.0,
      beta: 2.0,
      min: 96.0,
      max: 100.0
    },
    useCase: 'Automated processes, quality control'
  },
  yield_good: {
    name: 'Yield - Good (93-98%)',
    description: 'Good yield with occasional defects. Typical manufacturing.',
    variability: 'low',
    category: 'Yield',
    config: {
      type: 'beta',
      alpha: 90.0,
      beta: 10.0,
      min: 85.0,
      max: 100.0
    },
    useCase: 'Typical manufacturing processes'
  },
  yield_variable: {
    name: 'Yield - Variable (85-95%)',
    description: 'Higher yield variability. Complex or sensitive process.',
    variability: 'medium',
    category: 'Yield',
    config: {
      type: 'beta',
      alpha: 30.0,
      beta: 5.0,
      min: 80.0,
      max: 100.0
    },
    useCase: 'Complex processes, high sensitivity'
  },

  // Demand Templates
  demand_stable: {
    name: 'Demand - Stable (CV=20%)',
    description: 'Relatively stable demand. Mature product.',
    variability: 'low',
    category: 'Demand',
    config: {
      type: 'poisson',
      lambda: 100.0
    },
    useCase: 'Mature products, stable market'
  },
  demand_moderate: {
    name: 'Demand - Moderate Variability (CV=40%)',
    description: 'Moderate demand fluctuations. Typical consumer goods.',
    variability: 'medium',
    category: 'Demand',
    config: {
      type: 'negative_binomial',
      r: 10,
      p: 0.1
    },
    useCase: 'Consumer goods, seasonal products'
  },
  demand_volatile: {
    name: 'Demand - Volatile (CV=70%)',
    description: 'Highly variable demand. Fashion, tech, or promotional items.',
    variability: 'high',
    category: 'Demand',
    config: {
      type: 'negative_binomial',
      r: 5,
      p: 0.05
    },
    useCase: 'Fashion, technology, promotional items'
  }
};

// Variability colors
const VARIABILITY_VARIANTS = {
  low: 'success',
  medium: 'warning',
  high: 'destructive',
  'very high': 'destructive'
};

const DistributionTemplates = ({ onSelect, variableType = null }) => {
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [filterCategory, setFilterCategory] = useState('All');

  // Get unique categories
  const categories = ['All', ...new Set(Object.values(TEMPLATE_LIBRARY).map(t => t.category))];

  // Filter templates
  const filteredTemplates = Object.entries(TEMPLATE_LIBRARY).filter(([key, template]) => {
    if (filterCategory !== 'All' && template.category !== filterCategory) {
      return false;
    }
    if (variableType) {
      const typeMap = {
        lead_time: 'Lead Time',
        capacity: 'Capacity',
        yield: 'Yield',
        demand: 'Demand'
      };
      return template.category === typeMap[variableType];
    }
    return true;
  });

  // Handle template selection
  const handleSelect = (template) => {
    if (onSelect) {
      onSelect(template.config);
    }
  };

  // Handle view details
  const handleViewDetails = (template) => {
    setSelectedTemplate(template);
    setDialogOpen(true);
  };

  // Handle apply from dialog
  const handleApply = () => {
    if (selectedTemplate && onSelect) {
      onSelect(selectedTemplate.config);
    }
    setDialogOpen(false);
  };

  return (
    <div>
      {/* Category Filter */}
      <div className="mb-4">
        <FormField label="Category">
          <Select
            value={filterCategory}
            onChange={(e) => setFilterCategory(e.target.value)}
            className="w-[200px]"
          >
            {categories.map(cat => (
              <SelectOption key={cat} value={cat}>{cat}</SelectOption>
            ))}
          </Select>
        </FormField>
      </div>

      {/* Template Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
        {filteredTemplates.map(([key, template]) => (
          <Card key={key} className="flex flex-col h-full">
            <CardContent className="flex-grow">
              {/* Template Name */}
              <h3 className="text-base font-semibold mb-2 truncate">
                {template.name}
              </h3>

              {/* Category & Variability */}
              <div className="flex flex-wrap gap-1 mb-2">
                <Badge variant="secondary" size="sm">
                  {template.category}
                </Badge>
                <Badge variant={VARIABILITY_VARIANTS[template.variability]} size="sm">
                  {template.variability.toUpperCase()}
                </Badge>
              </div>

              {/* Description */}
              <p className="text-sm text-muted-foreground mb-2">
                {template.description}
              </p>

              {/* Use Case */}
              <p className="text-xs text-muted-foreground italic">
                Use case: {template.useCase}
              </p>

              {/* Distribution Type */}
              <div className="mt-2">
                <span className="text-xs text-muted-foreground">
                  Type: <strong>{template.config.type}</strong>
                </span>
              </div>
            </CardContent>

            <CardFooter className="pt-2">
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  leftIcon={<Copy className="h-4 w-4" />}
                  onClick={() => handleSelect(template)}
                >
                  Apply
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  leftIcon={<Pencil className="h-4 w-4" />}
                  onClick={() => handleViewDetails(template)}
                >
                  Details
                </Button>
              </div>
            </CardFooter>
          </Card>
        ))}
      </div>

      {/* Empty State */}
      {filteredTemplates.length === 0 && (
        <div className="text-center py-8">
          <p className="text-muted-foreground">
            No templates found for this category.
          </p>
        </div>
      )}

      {/* Template Details Dialog */}
      <Modal isOpen={dialogOpen} onClose={() => setDialogOpen(false)} size="md">
        <ModalHeader>
          <ModalTitle>Template Details</ModalTitle>
        </ModalHeader>
        <ModalBody>
          {selectedTemplate && (
            <div>
              <h3 className="text-lg font-semibold mb-2">
                {selectedTemplate.name}
              </h3>

              <div className="flex flex-wrap gap-1 mb-4">
                <Badge variant="secondary" size="sm">
                  {selectedTemplate.category}
                </Badge>
                <Badge variant={VARIABILITY_VARIANTS[selectedTemplate.variability]} size="sm">
                  {selectedTemplate.variability.toUpperCase()}
                </Badge>
              </div>

              <p className="text-sm mb-4">
                {selectedTemplate.description}
              </p>

              <p className="text-sm text-muted-foreground italic mb-4">
                <strong>Use Case:</strong> {selectedTemplate.useCase}
              </p>

              <FormField label="Configuration:">
                <Textarea
                  value={JSON.stringify(selectedTemplate.config, null, 2)}
                  readOnly
                  rows={8}
                  className="font-mono text-xs"
                />
              </FormField>
            </div>
          )}
        </ModalBody>
        <ModalFooter>
          <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleApply}>
            Apply Template
          </Button>
        </ModalFooter>
      </Modal>
    </div>
  );
};

export default DistributionTemplates;
