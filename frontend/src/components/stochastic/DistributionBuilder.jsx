import React, { useState, useEffect, useMemo } from 'react';
import { Trash2 } from 'lucide-react';
import { Button, Alert, Input, Label, Textarea, FormField } from '../common';
import { Select, SelectOption } from '../common/Select';

/**
 * Distribution Builder Component
 *
 * Visual editor for creating and configuring stochastic distributions.
 * Supports 18 distribution types with dynamic parameter forms and real-time validation.
 *
 * Features:
 * - Dynamic parameter forms based on distribution type
 * - Real-time validation of parameters
 * - Tooltips with distribution descriptions
 * - Template loading
 * - Preview integration (via parent component)
 *
 * Props:
 * - value: Current distribution configuration (JSON object)
 * - onChange: Callback when distribution changes
 * - variable: Variable name (for context)
 * - disabled: Disable editing
 * - onPreview: Optional callback to trigger preview
 * - showPreview: Show/hide preview section
 */

// Distribution type definitions with parameters and descriptions
const DISTRIBUTION_TYPES = {
  deterministic: {
    label: 'Deterministic (Fixed Value)',
    description: 'Always returns the same value. Use for backward compatibility or no uncertainty.',
    params: [
      { name: 'value', label: 'Value', type: 'number', required: true }
    ],
    category: 'Basic'
  },
  uniform: {
    label: 'Uniform',
    description: 'All values between min and max are equally likely. Simple uniform distribution.',
    params: [
      { name: 'min', label: 'Minimum', type: 'number', required: true },
      { name: 'max', label: 'Maximum', type: 'number', required: true }
    ],
    category: 'Basic'
  },
  discrete_uniform: {
    label: 'Discrete Uniform',
    description: 'Integer values between min and max are equally likely.',
    params: [
      { name: 'min', label: 'Minimum (Integer)', type: 'number', required: true, step: 1 },
      { name: 'max', label: 'Maximum (Integer)', type: 'number', required: true, step: 1 }
    ],
    category: 'Basic'
  },
  normal: {
    label: 'Normal (Gaussian)',
    description: 'Bell-shaped distribution. Most common for natural variations (lead times, demand).',
    params: [
      { name: 'mean', label: 'Mean (mu)', type: 'number', required: true },
      { name: 'stddev', label: 'Std Dev (sigma)', type: 'number', required: true, min: 0 },
      { name: 'min', label: 'Min (optional)', type: 'number', required: false },
      { name: 'max', label: 'Max (optional)', type: 'number', required: false }
    ],
    category: 'Symmetric'
  },
  truncated_normal: {
    label: 'Truncated Normal',
    description: 'Normal distribution with hard bounds. Use when values must stay within limits.',
    params: [
      { name: 'mean', label: 'Mean (mu)', type: 'number', required: true },
      { name: 'stddev', label: 'Std Dev (sigma)', type: 'number', required: true, min: 0 },
      { name: 'min', label: 'Minimum', type: 'number', required: true },
      { name: 'max', label: 'Maximum', type: 'number', required: true }
    ],
    category: 'Symmetric'
  },
  triangular: {
    label: 'Triangular',
    description: 'Three-point estimate (min, most likely, max). Common for expert estimates.',
    params: [
      { name: 'min', label: 'Minimum', type: 'number', required: true },
      { name: 'mode', label: 'Mode (Most Likely)', type: 'number', required: true },
      { name: 'max', label: 'Maximum', type: 'number', required: true }
    ],
    category: 'Symmetric'
  },
  lognormal: {
    label: 'Lognormal',
    description: 'Right-skewed, non-negative. Good for lead times, repair times, demand spikes.',
    params: [
      { name: 'mean_log', label: 'Mean (log scale)', type: 'number', required: true },
      { name: 'stddev_log', label: 'Std Dev (log scale)', type: 'number', required: true, min: 0 },
      { name: 'min', label: 'Min (optional)', type: 'number', required: false, min: 0 },
      { name: 'max', label: 'Max (optional)', type: 'number', required: false }
    ],
    category: 'Right-Skewed'
  },
  gamma: {
    label: 'Gamma',
    description: 'Flexible right-skewed distribution. Good for waiting times, capacities.',
    params: [
      { name: 'shape', label: 'Shape (alpha)', type: 'number', required: true, min: 0 },
      { name: 'scale', label: 'Scale (theta)', type: 'number', required: true, min: 0 },
      { name: 'min', label: 'Min (optional)', type: 'number', required: false, min: 0 }
    ],
    category: 'Right-Skewed'
  },
  weibull: {
    label: 'Weibull',
    description: 'Time-to-failure distribution. Use for reliability analysis.',
    params: [
      { name: 'shape', label: 'Shape (k)', type: 'number', required: true, min: 0 },
      { name: 'scale', label: 'Scale (lambda)', type: 'number', required: true, min: 0 }
    ],
    category: 'Right-Skewed'
  },
  exponential: {
    label: 'Exponential',
    description: 'Memoryless distribution. Good for rare events, time between failures.',
    params: [
      { name: 'rate', label: 'Rate (lambda)', type: 'number', required: true, min: 0 }
    ],
    category: 'Right-Skewed'
  },
  beta: {
    label: 'Beta',
    description: 'Bounded [0,1] distribution. Perfect for yields, percentages, probabilities.',
    params: [
      { name: 'alpha', label: 'Alpha (alpha)', type: 'number', required: true, min: 0 },
      { name: 'beta', label: 'Beta (beta)', type: 'number', required: true, min: 0 },
      { name: 'min', label: 'Min (rescale)', type: 'number', required: false },
      { name: 'max', label: 'Max (rescale)', type: 'number', required: false }
    ],
    category: 'Bounded'
  },
  poisson: {
    label: 'Poisson',
    description: 'Discrete count distribution. Good for demand, defects, arrivals.',
    params: [
      { name: 'lambda', label: 'Lambda (lambda) - Mean', type: 'number', required: true, min: 0 }
    ],
    category: 'Discrete'
  },
  binomial: {
    label: 'Binomial',
    description: 'Number of successes in n trials. Good for pass/fail scenarios.',
    params: [
      { name: 'n', label: 'Trials (n)', type: 'number', required: true, min: 1, step: 1 },
      { name: 'p', label: 'Success Probability (p)', type: 'number', required: true, min: 0, max: 1, step: 0.01 }
    ],
    category: 'Discrete'
  },
  negative_binomial: {
    label: 'Negative Binomial',
    description: 'Overdispersed Poisson. Good for demand with high variability.',
    params: [
      { name: 'r', label: 'Successes (r)', type: 'number', required: true, min: 1 },
      { name: 'p', label: 'Success Probability (p)', type: 'number', required: true, min: 0, max: 1, step: 0.01 }
    ],
    category: 'Discrete'
  },
  empirical_discrete: {
    label: 'Empirical Discrete',
    description: 'User-defined values and probabilities. Specify custom PMF.',
    params: [
      { name: 'values', label: 'Values (comma-separated)', type: 'array', required: true },
      { name: 'probabilities', label: 'Probabilities (comma-separated)', type: 'array', required: true }
    ],
    category: 'Data-Driven'
  },
  empirical_continuous: {
    label: 'Empirical Continuous',
    description: 'Learn distribution from sample data. Uses kernel density estimation.',
    params: [
      { name: 'samples', label: 'Sample Data (comma-separated)', type: 'array', required: true }
    ],
    category: 'Data-Driven'
  },
  mixture: {
    label: 'Mixture',
    description: 'Combination of distributions. Use for normal operations + disruptions.',
    params: [
      { name: 'components', label: 'Components (JSON)', type: 'json', required: true }
    ],
    category: 'Advanced'
  },
  categorical: {
    label: 'Categorical',
    description: 'Named categories with probabilities. Map categories to numeric values.',
    params: [
      { name: 'categories', label: 'Categories (comma-separated)', type: 'array', required: true },
      { name: 'probabilities', label: 'Probabilities (comma-separated)', type: 'array', required: true },
      { name: 'mappings', label: 'Value Mappings (JSON)', type: 'json', required: true }
    ],
    category: 'Advanced'
  }
};

// Group distributions by category
const DISTRIBUTION_CATEGORIES = {
  'Basic': ['deterministic', 'uniform', 'discrete_uniform'],
  'Symmetric': ['normal', 'truncated_normal', 'triangular'],
  'Right-Skewed': ['lognormal', 'gamma', 'weibull', 'exponential'],
  'Bounded': ['beta'],
  'Discrete': ['poisson', 'binomial', 'negative_binomial'],
  'Data-Driven': ['empirical_discrete', 'empirical_continuous'],
  'Advanced': ['mixture', 'categorical']
};

const DistributionBuilder = ({
  value = null,
  onChange,
  variable = 'variable',
  disabled = false,
  onPreview = null,
  showPreview = true
}) => {
  const [distType, setDistType] = useState(value?.type || 'deterministic');
  const [params, setParams] = useState(value || { type: 'deterministic', value: 0 });
  const [errors, setErrors] = useState({});
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Update local state when value prop changes
  useEffect(() => {
    if (value && value.type !== distType) {
      setDistType(value.type);
      setParams(value);
    }
  }, [value]);

  // Get distribution definition
  const distDef = useMemo(() => DISTRIBUTION_TYPES[distType] || DISTRIBUTION_TYPES.deterministic, [distType]);

  // Validate parameters
  const validateParams = (newParams) => {
    const newErrors = {};
    const def = DISTRIBUTION_TYPES[newParams.type];

    if (!def) return newErrors;

    def.params.forEach(param => {
      const val = newParams[param.name];

      // Check required
      if (param.required && (val === undefined || val === null || val === '')) {
        newErrors[param.name] = 'Required';
      }

      // Check min/max for numbers
      if (param.type === 'number' && val !== undefined && val !== null && val !== '') {
        const numVal = Number(val);
        if (isNaN(numVal)) {
          newErrors[param.name] = 'Must be a number';
        } else {
          if (param.min !== undefined && numVal < param.min) {
            newErrors[param.name] = `Must be >= ${param.min}`;
          }
          if (param.max !== undefined && numVal > param.max) {
            newErrors[param.name] = `Must be <= ${param.max}`;
          }
        }
      }

      // Check arrays
      if (param.type === 'array' && val) {
        const arr = typeof val === 'string' ? val.split(',').map(v => v.trim()) : val;
        if (arr.length === 0) {
          newErrors[param.name] = 'Must have at least one value';
        }
      }

      // Check JSON
      if (param.type === 'json' && val) {
        try {
          if (typeof val === 'string') {
            JSON.parse(val);
          }
        } catch (e) {
          newErrors[param.name] = 'Invalid JSON';
        }
      }
    });

    return newErrors;
  };

  // Handle distribution type change
  const handleTypeChange = (newType) => {
    setDistType(newType);

    // Reset to default params for new type
    const def = DISTRIBUTION_TYPES[newType];
    const newParams = { type: newType };

    // Set default values
    def.params.forEach(param => {
      if (param.name === 'value') newParams.value = 0;
      else if (param.name === 'mean') newParams.mean = 0;
      else if (param.name === 'stddev') newParams.stddev = 1;
      else if (param.name === 'min') newParams.min = 0;
      else if (param.name === 'max') newParams.max = 10;
      else if (param.name === 'rate') newParams.rate = 1;
      else if (param.name === 'lambda') newParams.lambda = 5;
      else if (param.name === 'shape') newParams.shape = 2;
      else if (param.name === 'scale') newParams.scale = 1;
      else if (param.name === 'alpha') newParams.alpha = 2;
      else if (param.name === 'beta') newParams.beta = 5;
      else if (param.name === 'mode') newParams.mode = 5;
      else if (param.name === 'n') newParams.n = 10;
      else if (param.name === 'p') newParams.p = 0.5;
      else if (param.name === 'r') newParams.r = 5;
    });

    setParams(newParams);
    setErrors({});

    if (onChange) {
      onChange(newParams);
    }
  };

  // Handle parameter change
  const handleParamChange = (paramName, value) => {
    const newParams = { ...params, [paramName]: value };
    setParams(newParams);

    // Validate
    const newErrors = validateParams(newParams);
    setErrors(newErrors);

    // Only call onChange if valid
    if (Object.keys(newErrors).length === 0 && onChange) {
      onChange(newParams);
    }
  };

  // Render parameter input
  const renderParamInput = (param) => {
    const value = params[param.name];
    const error = errors[param.name];

    if (param.type === 'number') {
      return (
        <FormField
          label={param.label}
          required={param.required}
          error={error}
        >
          <Input
            type="number"
            value={value ?? ''}
            onChange={(e) => handleParamChange(param.name, e.target.value ? Number(e.target.value) : '')}
            disabled={disabled}
            step={param.step || 'any'}
            min={param.min}
            max={param.max}
            error={!!error}
          />
        </FormField>
      );
    } else if (param.type === 'array') {
      return (
        <FormField
          label={param.label}
          required={param.required}
          error={error}
          helperText={!error ? 'Comma-separated values' : undefined}
        >
          <Textarea
            value={Array.isArray(value) ? value.join(', ') : value || ''}
            onChange={(e) => handleParamChange(param.name, e.target.value)}
            disabled={disabled}
            error={!!error}
            rows={2}
          />
        </FormField>
      );
    } else if (param.type === 'json') {
      return (
        <FormField
          label={param.label}
          required={param.required}
          error={error}
          helperText={!error ? 'Valid JSON object' : undefined}
        >
          <Textarea
            value={typeof value === 'object' ? JSON.stringify(value, null, 2) : value || ''}
            onChange={(e) => handleParamChange(param.name, e.target.value)}
            disabled={disabled}
            error={!!error}
            rows={4}
            className="font-mono text-xs"
          />
        </FormField>
      );
    }

    return null;
  };

  return (
    <div>
      {/* Distribution Type Selection */}
      <FormField label="Distribution Type" className="mb-4">
        <Select
          value={distType}
          onChange={(e) => handleTypeChange(e.target.value)}
          disabled={disabled}
        >
          {Object.entries(DISTRIBUTION_CATEGORIES).map(([category, types]) => (
            <React.Fragment key={category}>
              <SelectOption value="" disabled className="font-bold bg-muted">
                {category}
              </SelectOption>
              {types.map(type => (
                <SelectOption key={type} value={type}>
                  {DISTRIBUTION_TYPES[type].label}
                </SelectOption>
              ))}
            </React.Fragment>
          ))}
        </Select>
      </FormField>

      {/* Distribution Description */}
      <Alert variant="info" className="mb-4">
        <p className="text-sm">
          {distDef.description}
        </p>
      </Alert>

      {/* Parameter Inputs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {distDef.params.map(param => (
          <div key={param.name}>
            {renderParamInput(param)}
          </div>
        ))}
      </div>

      {/* Preview Button */}
      {onPreview && showPreview && (
        <div className="mt-4 flex justify-end">
          <Button
            variant="outline"
            onClick={() => onPreview(params)}
            disabled={disabled || Object.keys(errors).length > 0}
          >
            Generate Preview
          </Button>
        </div>
      )}

      {/* Clear/Reset Button */}
      {!disabled && distType !== 'deterministic' && (
        <div className="mt-4 flex justify-start">
          <Button
            variant="ghost"
            className="text-destructive hover:text-destructive"
            leftIcon={<Trash2 className="h-4 w-4" />}
            onClick={() => handleTypeChange('deterministic')}
          >
            Clear Distribution
          </Button>
        </div>
      )}
    </div>
  );
};

export default DistributionBuilder;
