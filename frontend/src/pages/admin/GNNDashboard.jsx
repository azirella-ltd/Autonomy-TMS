/**
 * GNN Dashboard Page
 *
 * Main dashboard for GNN (Graph Neural Network) management.
 * Combines training, model management, and testing functionality.
 *
 * IMPORTANT: Models are config-specific. A model trained on one SC config
 * should only be used for that config. The config selector filters all tabs.
 */

import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  Card,
  CardContent,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
  NativeSelect,
  SelectOption,
  Alert,
  Spinner,
  FormField,
} from '../../components/common';
import { GraduationCap, Database, FlaskConical, ChevronRight, Settings2, ClipboardCheck } from 'lucide-react';
import GNNTrainingPanel from '../../components/admin/GNNTrainingPanel';
import GNNModelManager from '../../components/admin/GNNModelManager';
import GNNTestPanel from '../../components/admin/GNNTestPanel';
import GNNDirectiveReview from '../../components/admin/GNNDirectiveReview';
import { getSupplyChainConfigs } from '../../services/supplyChainConfigService';

const GNNDashboard = () => {
  const [currentTab, setCurrentTab] = useState('training');

  // Supply chain config selection (shared across all tabs)
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
        <span className="text-foreground">Network Agent Training</span>
      </nav>

      <div className="mb-6">
        <h1 className="text-3xl font-bold mb-2">Tactical Agent</h1>
        <p className="text-muted-foreground">
          Tactical / Network — daily priority allocations and execution directives across sites.
        </p>
      </div>

      {/* Supply Chain Config Selector - applies to all tabs */}
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
            Models are trained for a specific supply chain configuration. Training, checkpoints, and testing are filtered by the selected config.
          </p>
        </CardContent>
      </Card>

      <Card className="mb-6">
        <Tabs value={currentTab} onValueChange={setCurrentTab}>
          <TabsList className="w-full justify-start border-b rounded-none h-auto p-0">
            <TabsTrigger
              value="training"
              className="flex items-center gap-2 rounded-none border-b-2 border-transparent data-[state=active]:border-primary"
            >
              <GraduationCap className="h-4 w-4" />
              Training
            </TabsTrigger>
            <TabsTrigger
              value="models"
              className="flex items-center gap-2 rounded-none border-b-2 border-transparent data-[state=active]:border-primary"
            >
              <Database className="h-4 w-4" />
              Model Manager
            </TabsTrigger>
            <TabsTrigger
              value="testing"
              className="flex items-center gap-2 rounded-none border-b-2 border-transparent data-[state=active]:border-primary"
            >
              <FlaskConical className="h-4 w-4" />
              Testing
            </TabsTrigger>
            <TabsTrigger
              value="directive-review"
              className="flex items-center gap-2 rounded-none border-b-2 border-transparent data-[state=active]:border-primary"
            >
              <ClipboardCheck className="h-4 w-4" />
              Directive Review
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </Card>

      {currentTab === 'training' && <GNNTrainingPanel selectedConfig={selectedConfig} />}
      {currentTab === 'models' && <GNNModelManager selectedConfig={selectedConfig} />}
      {currentTab === 'testing' && <GNNTestPanel selectedConfig={selectedConfig} />}
      {currentTab === 'directive-review' && <GNNDirectiveReview />}
    </div>
  );
};

export default GNNDashboard;
