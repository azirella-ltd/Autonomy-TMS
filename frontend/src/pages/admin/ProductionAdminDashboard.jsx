/**
 * Production Customer Administrator Dashboard
 *
 * Tailored for production customer admins - focused on configuration and operations
 * rather than game-centric learning mode features.
 *
 * Tabs:
 * 1. Supply Chains - Network configurations and management
 * 2. Scenarios - Git-like scenario tree for what-if planning
 * 3. Users - User management and capability assignment
 * 4. Settings - Hierarchy levels, data sources, CDC thresholds
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { isSystemAdmin as isSystemAdminUser } from '../../utils/authUtils';
import { saveAdminDashboardPath } from '../../utils/adminDashboardState';
import TenantSupplyChainConfigList from './TenantSupplyChainConfigList';
import TenantAdminUserManagement from './UserManagement';
import TenantSettingsPanel from './TenantSettingsPanel';
import { getSupplyChainConfigs } from '../../services/supplyChainConfigService';
import {
  Card,
  CardContent,
  Button,
  Spinner,
  NativeSelect,
  Tabs,
  TabsList,
  Tab,
  Alert,
  AlertDescription,
} from '../../components/common';
import {
  Network,
  GitBranch,
  Users,
  Settings,
  Database,
  ArrowRight,
  ChevronRight,
  FolderTree,
} from 'lucide-react';
import { cn } from '../../lib/utils/cn';
import ScenarioTreeViewer from '../../components/supply-chain-config/ScenarioTreeViewer';
import { api } from '../../services/api';

// Production-focused tab configuration
const tabItems = [
  { value: 'sc', label: 'Supply Chains', icon: <Network className="h-4 w-4" /> },
  { value: 'scenarios', label: 'Scenarios', icon: <GitBranch className="h-4 w-4" /> },
  { value: 'users', label: 'Users', icon: <Users className="h-4 w-4" /> },
  { value: 'settings', label: 'Settings', icon: <Settings className="h-4 w-4" /> },
];

const ProductionAdminDashboard = () => {
  const { user, loading, isTenantAdmin } = useAuth();
  const isSystemAdmin = isSystemAdminUser(user);
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const initialTab = searchParams.get('section') || 'sc';
  const initialScParam = searchParams.get('sc') || 'all';
  const [activeTab, setActiveTab] = useState(
    tabItems.some((tab) => tab.value === initialTab) ? initialTab : 'sc'
  );
  const [selectedSupplyChainId, setSelectedSupplyChainId] = useState(initialScParam);

  const tenantId = useMemo(() => {
    const rawTenant = user?.tenant_id;
    if (rawTenant == null) return null;
    const parsed = Number(rawTenant);
    return Number.isFinite(parsed) ? parsed : null;
  }, [user]);

  // Supply chain configs state
  const [supplyChainConfigs, setSupplyChainConfigs] = useState([]);
  const [supplyChainsLoading, setSupplyChainsLoading] = useState(true);
  const [selectedConfig, setSelectedConfig] = useState(null);

  // Customer info state
  const [tenantInfo, setCustomerInfo] = useState(null);

  useEffect(() => {
    const section = searchParams.get('section') || 'sc';
    if (tabItems.some((tab) => tab.value === section) && section !== activeTab) {
      setActiveTab(section);
    }
    const scParam = searchParams.get('sc') || 'all';
    if (scParam !== selectedSupplyChainId) {
      setSelectedSupplyChainId(scParam);
    }
  }, [searchParams, activeTab, selectedSupplyChainId]);

  const updateSearchParams = useCallback(
    (updates) => {
      const params = new URLSearchParams(searchParams);
      Object.entries(updates).forEach(([key, value]) => {
        if (value === undefined || value === null || value === '') {
          params.delete(key);
        } else {
          params.set(key, value);
        }
      });
      setSearchParams(params);
    },
    [searchParams, setSearchParams]
  );

  const handleTabChange = (newValue) => {
    setActiveTab(newValue);
    updateSearchParams({ section: newValue, sc: selectedSupplyChainId || 'all' });
  };

  // Persist path for back navigation
  useEffect(() => {
    const path = `/admin/production?section=${activeTab}&sc=${selectedSupplyChainId || 'all'}`;
    saveAdminDashboardPath(path);
  }, [activeTab, selectedSupplyChainId]);

  // Load supply chain configs
  const refreshSupplyChains = useCallback(async () => {
    setSupplyChainsLoading(true);
    try {
      const configs = await getSupplyChainConfigs();
      const data = Array.isArray(configs) ? configs : [];
      setSupplyChainConfigs(data);

      // Select first config if none selected.
      // Prefer production (non-TBG/non-Learning) configs over simulation configs.
      if (data.length > 0 && (selectedSupplyChainId === 'all' || !selectedSupplyChainId)) {
        const isTbgOrLearning = (c) => /tbg|learning/i.test(c.name || '');
        const productionConfigs = data.filter((c) => !isTbgOrLearning(c));
        const pool = productionConfigs.length > 0 ? productionConfigs : data;
        const activeConfig = pool.find((c) => c.is_active) || pool[0];
        setSelectedConfig(activeConfig);
      } else if (selectedSupplyChainId && selectedSupplyChainId !== 'all') {
        const found = data.find((c) => String(c.id) === String(selectedSupplyChainId));
        setSelectedConfig(found || null);
      }

      // Cache names locally
      try {
        if (typeof window !== 'undefined' && window.localStorage) {
          const cache = data.reduce((acc, config) => {
            if (!config || config.id == null) return acc;
            const key = String(config.id);
            acc[key] = config.name || `Config ${key}`;
            return acc;
          }, {});
          window.localStorage.setItem('scConfigNameMap', JSON.stringify(cache));
        }
      } catch (storageErr) {
        console.warn('Failed to cache supply chain config names locally', storageErr);
      }
    } catch (err) {
      console.warn('Unable to load supply chain configurations', err);
      setSupplyChainConfigs([]);
    } finally {
      setSupplyChainsLoading(false);
    }
  }, [selectedSupplyChainId]);

  useEffect(() => {
    refreshSupplyChains();
  }, [refreshSupplyChains]);

  // Load organization info
  useEffect(() => {
    const loadTenantInfo = async () => {
      if (!tenantId) return;
      try {
        const response = await api.get(`/tenants/${tenantId}`);
        setCustomerInfo(response.data);
      } catch (err) {
        console.warn('Failed to load organization info', err);
      }
    };
    loadTenantInfo();
  }, [tenantId]);

  // Supply chain options for dropdown
  const supplyChainOptions = useMemo(() => {
    const entries = supplyChainConfigs.map((c) => ({
      id: String(c.id),
      name: c.name || `Config ${c.id}`,
    }));
    entries.sort((a, b) => a.name.localeCompare(b.name));
    return [{ id: 'all', name: 'All Configurations' }, ...entries];
  }, [supplyChainConfigs]);

  const handleSupplyChainChange = useCallback(
    (e) => {
      const value = e.target.value;
      const normalized = value === 'all' || value == null ? 'all' : String(value);
      setSelectedSupplyChainId(normalized);
      updateSearchParams({ section: activeTab, sc: normalized });

      // Update selected config
      if (normalized !== 'all') {
        const found = supplyChainConfigs.find((c) => String(c.id) === normalized);
        setSelectedConfig(found || null);
      } else {
        setSelectedConfig(supplyChainConfigs.find((c) => c.is_active) || supplyChainConfigs[0] || null);
      }
    },
    [activeTab, updateSearchParams, supplyChainConfigs]
  );

  // Handle config selection from tree
  const handleConfigSelect = useCallback((config) => {
    if (config?.id) {
      setSelectedConfig(config);
      setSelectedSupplyChainId(String(config.id));
      updateSearchParams({ section: activeTab, sc: String(config.id) });
    }
  }, [activeTab, updateSearchParams]);

  if (loading) {
    return (
      <div className="flex justify-center items-center min-h-[60vh]">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/unauthorized" replace />;
  }

  if (isSystemAdmin && !isTenantAdmin) {
    return <Navigate to="/system/users" replace />;
  }

  if (!isTenantAdmin) {
    return <Navigate to="/unauthorized" replace />;
  }

  return (
    <div className="max-w-7xl mx-auto py-6 px-4 md:px-6">
      <Card className="mb-6">
        <CardContent className="p-4 md:p-6">
          <div className="flex flex-col gap-4 mb-4">
            <div>
              <h1 className="text-2xl font-bold mb-1">
                {tenantInfo?.name || 'Organization'} Administration
              </h1>
              <p className="text-sm text-muted-foreground">
                Configure supply chain networks, manage scenarios and users, and adjust planning settings for your organization.
              </p>
            </div>
          </div>

          <div className="flex justify-start mb-4">
            <div className="w-full md:w-80">
              <label htmlFor="sc-filter" className="block text-sm font-medium mb-1">
                Supply Chain Configuration
              </label>
              <NativeSelect
                id="sc-filter"
                value={String(selectedSupplyChainId ?? 'all')}
                onChange={handleSupplyChainChange}
              >
                {supplyChainOptions.map((option) => (
                  <option key={option.id} value={String(option.id)}>
                    {option.name}
                  </option>
                ))}
              </NativeSelect>
            </div>
          </div>

          <Tabs value={activeTab} onValueChange={handleTabChange} className="mt-4">
            <TabsList className="bg-transparent border-b border-border rounded-none p-0 gap-0">
              {tabItems.map((tab) => (
                <Tab
                  key={tab.value}
                  value={tab.value}
                  className={cn(
                    'rounded-none border-b-2 border-transparent px-4 py-2 flex items-center gap-2',
                    activeTab === tab.value && 'border-primary bg-transparent text-foreground'
                  )}
                >
                  {tab.icon}
                  {tab.label}
                </Tab>
              ))}
            </TabsList>
          </Tabs>
        </CardContent>
      </Card>

      <div>
        {/* Supply Chains Tab */}
        {activeTab === 'sc' && <TenantSupplyChainConfigList />}

        {/* Scenarios Tab - Git-like tree view */}
        {activeTab === 'scenarios' && (
          <Card>
            <CardContent className="p-6">
              <div className="mb-6">
                <h2 className="text-xl font-bold mb-1 flex items-center gap-2">
                  <GitBranch className="h-5 w-5" />
                  Scenario Management
                </h2>
                <p className="text-muted-foreground">
                  Create and manage what-if scenarios with git-like branching. Each branch represents a different planning scenario.
                </p>
              </div>

              {selectedConfig ? (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <FolderTree className="h-4 w-4 text-muted-foreground" />
                      <span className="font-medium">{selectedConfig.name}</span>
                      {selectedConfig.is_active && (
                        <span className="text-xs bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200 px-2 py-0.5 rounded">
                          Active
                        </span>
                      )}
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => navigate(`/admin/tenant/supply-chain-configs/${selectedConfig.id}/scenarios`)}
                    >
                      Open Full Tree Manager
                      <ChevronRight className="h-4 w-4 ml-1" />
                    </Button>
                  </div>

                  <ScenarioTreeViewer
                    configId={selectedConfig.id}
                    onConfigChange={handleConfigSelect}
                  />
                </div>
              ) : (
                <Alert>
                  <AlertDescription>
                    Select a supply chain configuration above to view its scenario tree.
                  </AlertDescription>
                </Alert>
              )}
            </CardContent>
          </Card>
        )}

        {/* Users Tab */}
        {activeTab === 'users' && <TenantAdminUserManagement />}

        {/* Settings Tab */}
        {activeTab === 'settings' && (
          <TenantSettingsPanel
            groupId={tenantId}
            groupInfo={tenantInfo}
            selectedConfigId={selectedConfig?.id}
            onGroupInfoChange={setCustomerInfo}
          />
        )}
      </div>
    </div>
  );
};

export default ProductionAdminDashboard;
