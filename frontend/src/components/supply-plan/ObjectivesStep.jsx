/**
 * Objectives Step
 *
 * Configure supply chain configuration, planning horizon, and business objectives.
 */

import React, { useState, useEffect } from 'react';
import { Button } from '../common/Button';
import { Alert } from '../common/Alert';
import { Input, Label, FormField } from '../common/Input';
import { Select, SelectOption } from '../common/Select';
import { getSupplyChainConfigs } from '../../services/supplyChainConfigService';

export default function ObjectivesStep({ config, onUpdate, onNext }) {
  const [configs, setConfigs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadConfigurations();
  }, []);

  const loadConfigurations = async () => {
    try {
      const configs = await getSupplyChainConfigs();
      setConfigs(configs || []);
    } catch (err) {
      setError('Failed to load supply chain configurations');
    } finally {
      setLoading(false);
    }
  };

  const handleConfigChange = (event) => {
    const selectedConfig = configs.find((c) => c.id === parseInt(event.target.value));
    if (selectedConfig) {
      onUpdate({
        configId: selectedConfig.id,
        configName: selectedConfig.name,
      });
    }
  };

  const handleObjectiveChange = (field, value) => {
    onUpdate({
      objectives: {
        ...config.objectives,
        [field]: value,
      },
    });
  };

  const canProceed = config.configId !== null;

  return (
    <div>
      <h2 className="text-lg font-semibold mb-4">Configuration & Business Objectives</h2>

      {error && (
        <Alert variant="error" className="mb-4">
          {error}
        </Alert>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Configuration Selection */}
        <div className="col-span-full">
          <FormField label="Supply Chain Configuration">
            <Select
              value={config.configId || ''}
              onChange={handleConfigChange}
              placeholder="Select a configuration"
            >
              {configs.map((cfg) => (
                <SelectOption key={cfg.id} value={cfg.id}>
                  {cfg.name} ({cfg.sites?.length || 0} sites)
                </SelectOption>
              ))}
            </Select>
          </FormField>
        </div>

        {/* Planning Horizon */}
        <FormField
          label="Planning Horizon"
          helperText="Typical: 52 weeks (1 year) for tactical planning"
        >
          <div className="relative">
            <Input
              type="number"
              value={config.objectives.planningHorizon}
              onChange={(e) =>
                handleObjectiveChange('planningHorizon', parseInt(e.target.value))
              }
              className="pr-16"
            />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm">
              weeks
            </span>
          </div>
        </FormField>

        {/* Primary Objective */}
        <FormField label="Primary Objective">
          <Select
            value={config.objectives.primaryObjective}
            onChange={(e) => handleObjectiveChange('primaryObjective', e.target.value)}
          >
            <SelectOption value="minimize_cost">Minimize Total Cost</SelectOption>
            <SelectOption value="maximize_service">Maximize Service Level</SelectOption>
            <SelectOption value="balance">Balance Cost & Service</SelectOption>
          </Select>
        </FormField>

        {/* Service Level Target */}
        <FormField
          label="Service Level Target (OTIF)"
          helperText="Target on-time-in-full delivery rate"
        >
          <div className="relative">
            <Input
              type="number"
              value={config.objectives.serviceLevelTarget}
              onChange={(e) =>
                handleObjectiveChange('serviceLevelTarget', parseFloat(e.target.value))
              }
              min={0}
              max={100}
              step={1}
              className="pr-8"
            />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm">
              %
            </span>
          </div>
        </FormField>

        {/* Service Level Confidence */}
        <FormField
          label="Service Level Confidence"
          helperText="P(OTIF > target) must be >= this value"
        >
          <div className="relative">
            <Input
              type="number"
              value={config.objectives.serviceLevelConfidence}
              onChange={(e) =>
                handleObjectiveChange('serviceLevelConfidence', parseFloat(e.target.value))
              }
              min={0}
              max={100}
              step={1}
              className="pr-8"
            />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm">
              %
            </span>
          </div>
        </FormField>

        {/* Budget Limit */}
        <FormField
          label="Budget Limit (Optional)"
          helperText="Maximum total cost constraint"
        >
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm">
              $
            </span>
            <Input
              type="number"
              value={config.objectives.budgetLimit || ''}
              onChange={(e) =>
                handleObjectiveChange(
                  'budgetLimit',
                  e.target.value ? parseFloat(e.target.value) : null
                )
              }
              className="pl-7"
            />
          </div>
        </FormField>

        {/* Days of Supply Range */}
        <FormField label="Min Days of Supply">
          <div className="relative">
            <Input
              type="number"
              value={config.objectives.inventoryDosMin || ''}
              onChange={(e) =>
                handleObjectiveChange(
                  'inventoryDosMin',
                  e.target.value ? parseInt(e.target.value) : null
                )
              }
              className="pr-14"
            />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm">
              days
            </span>
          </div>
        </FormField>

        <FormField label="Max Days of Supply">
          <div className="relative">
            <Input
              type="number"
              value={config.objectives.inventoryDosMax || ''}
              onChange={(e) =>
                handleObjectiveChange(
                  'inventoryDosMax',
                  e.target.value ? parseInt(e.target.value) : null
                )
              }
              className="pr-14"
            />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm">
              days
            </span>
          </div>
        </FormField>
      </div>

      {/* Navigation */}
      <div className="flex justify-end mt-8">
        <Button onClick={onNext} disabled={!canProceed}>
          Next: Select Planning Method
        </Button>
      </div>
    </div>
  );
}
