import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  Card,
  CardContent,
  NativeSelect,
  SelectOption,
  Alert,
  Spinner,
  FormField,
} from '../../components/common';
import { ChevronRight, Settings2 } from 'lucide-react';
import RLTrainingPanel from '../../components/admin/RLTrainingPanel';
import { getSupplyChainConfigs } from '../../services/supplyChainConfigService';

const RLDashboard = () => {
  // Supply chain config selection (shared across panel)
  const [availableConfigs, setAvailableConfigs] = useState([]);
  const [selectedConfig, setSelectedConfig] = useState('');
  const [configsLoading, setConfigsLoading] = useState(true);
  const [configsError, setConfigsError] = useState(null);

  // Load supply chain configs on mount
  useEffect(() => {
    const loadConfigs = async () => {
      setConfigsLoading(true);
      setConfigsError(null);
      try {
        const configs = await getSupplyChainConfigs();
        setAvailableConfigs(configs);
        // Set default selection to first config if available
        if (configs.length > 0) {
          setSelectedConfig(configs[0].name);
        }
      } catch (err) {
        console.error('Failed to load supply chain configs:', err);
        setConfigsError('Failed to load supply chain configurations');
      } finally {
        setConfigsLoading(false);
      }
    };
    loadConfigs();
  }, []);

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      {/* Breadcrumbs */}
      <nav className="flex items-center gap-2 text-sm text-muted-foreground mb-4">
        <Link to="/" className="hover:text-foreground">Home</Link>
        <ChevronRight className="h-4 w-4" />
        <Link to="/admin?section=training" className="hover:text-foreground">AI & Agents</Link>
        <ChevronRight className="h-4 w-4" />
        <span className="text-foreground">RL Training</span>
      </nav>

      {/* Page Header */}
      <Card className="mb-6">
        <CardContent className="pt-6">
          <h1 className="text-2xl font-bold mb-2">Reinforcement Learning Agent Training</h1>
          <p className="text-muted-foreground">
            Train RL agents (PPO, SAC, A2C) for automated supply chain planning using Stable-Baselines3.
            RL agents learn optimal ordering policies through trial-and-error interaction with the environment.
          </p>
        </CardContent>
      </Card>

      {/* Supply Chain Config Selector - applies to training and checkpoints */}
      <Card className="mb-4">
        <CardContent className="py-4">
          <div className="flex items-center gap-4">
            <Settings2 className="h-5 w-5 text-muted-foreground" />
            <FormField label="Supply Chain Configuration" className="flex-1 mb-0">
              {configsLoading ? (
                <div className="flex items-center gap-2">
                  <Spinner size="sm" />
                  <span className="text-sm text-muted-foreground">Loading configurations...</span>
                </div>
              ) : configsError ? (
                <Alert variant="error" className="py-2">{configsError}</Alert>
              ) : (
                <NativeSelect
                  value={selectedConfig}
                  onChange={(e) => setSelectedConfig(e.target.value)}
                  className="max-w-md"
                >
                  {availableConfigs.map((cfg) => (
                    <SelectOption key={cfg.id} value={cfg.name}>
                      {cfg.name}
                    </SelectOption>
                  ))}
                </NativeSelect>
              )}
            </FormField>
          </div>
          <p className="text-xs text-muted-foreground mt-2 ml-9">
            RL models are trained for a specific supply chain configuration. Training and checkpoints are filtered by the selected config.
          </p>
        </CardContent>
      </Card>

      {/* Training Panel */}
      <div className="mt-6">
        <RLTrainingPanel selectedConfig={selectedConfig} />
      </div>

      {/* Help Section */}
      <Card className="mt-6 bg-blue-50 dark:bg-blue-950 border-blue-200 dark:border-blue-800">
        <CardContent className="pt-6">
          <h2 className="text-lg font-semibold mb-2">Quick Start Guide</h2>
          <ol className="list-decimal list-inside space-y-1 text-sm">
            <li><strong>Select Algorithm</strong>: PPO (recommended), SAC (continuous control), or A2C (lightweight)</li>
            <li><strong>Configure Training</strong>: Set total timesteps (1M recommended for good performance)</li>
            <li><strong>Start Training</strong>: Click "Start Training" - progress updates every 2 seconds</li>
            <li><strong>Monitor Progress</strong>: Watch mean reward (should increase), mean cost (should decrease)</li>
            <li><strong>Evaluate</strong>: After training completes, evaluate the model on 20 episodes</li>
            <li><strong>Use in Scenarios</strong>: Load trained agents in supply chain game configurations</li>
          </ol>
          <p className="text-xs text-muted-foreground mt-4">
            <strong>Training Time</strong>: ~90 minutes (CPU) or ~30 minutes (GPU) for 1M timesteps
          </p>
        </CardContent>
      </Card>
    </div>
  );
};

export default RLDashboard;
