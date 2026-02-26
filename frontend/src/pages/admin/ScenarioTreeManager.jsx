/**
 * Scenario Tree Manager Page
 *
 * Manage git-like scenario branching for supply chain configurations.
 * Shows tree visualization with branch/commit/rollback operations.
 */

import { useState, useEffect } from 'react';
import { useParams, useNavigate, Navigate, useLocation } from 'react-router-dom';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Spinner,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from '../../components/common';
import { ArrowLeft, Pencil, Eye, ChevronRight } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { isTenantAdmin as isTenantAdminUser } from '../../utils/authUtils';
import ScenarioTreeViewer from '../../components/supply-chain-config/ScenarioTreeViewer';
import DecisionProposalManager from '../../components/supply-chain-config/DecisionProposalManager';
import { api } from '../../services/api';

const ScenarioTreeManager = () => {
  const { configId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const { user, loading: authLoading } = useAuth();

  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [currentTab, setCurrentTab] = useState('tree');

  useEffect(() => {
    if (configId) {
      loadConfig();
    }
  }, [configId]);

  const loadConfig = async () => {
    try {
      setLoading(true);
      const response = await api.get(`/supply-chain-config/${configId}`);
      setConfig(response.data);
    } catch (error) {
      console.error('Failed to load configuration:', error);
      setError('Failed to load configuration');
    } finally {
      setLoading(false);
    }
  };

  const handleConfigChange = (updatedConfig) => {
    if (updatedConfig?.id && updatedConfig.id !== parseInt(configId)) {
      navigate(`/admin/tenant/supply-chain-configs/${updatedConfig.id}/scenarios`);
    } else {
      loadConfig();
    }
  };

  const handleBack = () => {
    navigate('/admin/tenant/supply-chain-configs');
  };

  const handleEdit = () => {
    navigate(`/admin/tenant/supply-chain-configs/edit/${configId}`);
  };

  const handleViewEffective = async () => {
    try {
      const response = await api.get(`/supply-chain-config/${configId}/effective`);
      console.log('Effective configuration:', response.data);
      alert('Effective configuration loaded. Check browser console for details.');
    } catch (error) {
      console.error('Failed to load effective config:', error);
      alert('Failed to load effective configuration');
    }
  };

  if (authLoading) {
    return (
      <div className="flex justify-center items-center min-h-[50vh]">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!user) {
    return (
      <Navigate
        to="/login"
        replace
        state={{
          from: location.pathname + location.search,
        }}
      />
    );
  }

  const canAccess = user?.is_superuser || isTenantAdminUser(user);
  if (!canAccess) {
    return <Navigate to="/unauthorized" replace />;
  }

  if (loading) {
    return (
      <div className="flex justify-center items-center min-h-[50vh]">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <div>
        <Alert variant="destructive">{error}</Alert>
        <Button onClick={handleBack} className="mt-4" leftIcon={<ArrowLeft className="h-4 w-4" />}>
          Back to Configurations
        </Button>
      </div>
    );
  }

  if (!config) {
    return (
      <div>
        <Alert variant="warning">Configuration not found</Alert>
        <Button onClick={handleBack} className="mt-4" leftIcon={<ArrowLeft className="h-4 w-4" />}>
          Back to Configurations
        </Button>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="mb-6">
        {/* Breadcrumbs */}
        <nav className="flex items-center gap-2 text-sm text-muted-foreground mb-4">
          <button onClick={handleBack} className="hover:text-foreground">
            Supply Chain Configurations
          </button>
          <ChevronRight className="h-4 w-4" />
          <span className="text-foreground">{config.name}</span>
          <ChevronRight className="h-4 w-4" />
          <span className="text-foreground">Scenarios</span>
        </nav>

        <div className="flex items-center justify-between">
          <div className="flex-1">
            <h1 className="text-2xl font-bold">{config.name}</h1>
            {config.description && (
              <p className="text-sm text-muted-foreground">{config.description}</p>
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={handleBack} leftIcon={<ArrowLeft className="h-4 w-4" />}>
              Back
            </Button>
            <Button variant="outline" onClick={handleEdit} leftIcon={<Pencil className="h-4 w-4" />}>
              Edit Config
            </Button>
            <Button variant="outline" onClick={handleViewEffective} leftIcon={<Eye className="h-4 w-4" />}>
              View Effective
            </Button>
          </div>
        </div>
      </div>

      {/* Info Card */}
      <Card className="mb-6 bg-blue-50 dark:bg-blue-950 border-blue-200 dark:border-blue-800">
        <CardContent className="pt-4">
          <h2 className="text-lg font-semibold mb-2">Scenario Management & Decision Simulation</h2>
          <p className="text-sm text-muted-foreground">
            Create scenario branches to experiment with configuration variants. Use decision proposals
            to simulate business impact of changes and present approval-ready business cases with
            probabilistic metrics (cost, service level, inventory) across all planning levels.
          </p>
        </CardContent>
      </Card>

      {/* Tabs */}
      <Card>
        <Tabs value={currentTab} onValueChange={setCurrentTab}>
          <div className="border-b">
            <TabsList className="w-full justify-start p-0 h-auto bg-transparent">
              <TabsTrigger
                value="tree"
                className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary"
              >
                Scenario Tree
              </TabsTrigger>
              <TabsTrigger
                value="proposals"
                className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary"
              >
                Decision Proposals
              </TabsTrigger>
            </TabsList>
          </div>

          <TabsContent value="tree" className="p-4">
            <ScenarioTreeViewer configId={parseInt(configId)} onConfigChange={handleConfigChange} />
          </TabsContent>

          <TabsContent value="proposals" className="p-4">
            <DecisionProposalManager
              configId={parseInt(configId)}
              scenarioName={config.name}
              onProposalChange={handleConfigChange}
            />
          </TabsContent>
        </Tabs>
      </Card>
    </div>
  );
};

export default ScenarioTreeManager;
