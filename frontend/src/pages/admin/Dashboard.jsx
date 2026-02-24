import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { isSystemAdmin as isSystemAdminUser } from '../../utils/authUtils';
import { saveAdminDashboardPath } from '../../utils/adminDashboardState';
import GroupSupplyChainConfigList from './GroupSupplyChainConfigList';
import GroupPlayerManagement from './UserManagement';
import GroupGameConfigPanel from './GroupGameConfigPanel';
import GroupGameSupervisionPanel from './GroupGameSupervisionPanel';
import GroupGameComparisonPanel from './GroupGameComparisonPanel';
import simulationApi from '../../services/api';
import { api } from '../../services/api';
import { getSupplyChainConfigs } from '../../services/supplyChainConfigService';
import { listCheckpoints as listTRMCheckpoints } from '../../services/trmApi';
import { listGNNCheckpoints } from '../../services/gnnApi';
import { listCheckpoints as listRLCheckpoints } from '../../services/rlApi';
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
  Database,
  Gamepad2,
  Users,
  Eye,
  BarChart3,
  GraduationCap,
  Brain,
  Bot,
  Sparkles,
  ArrowRight,
  CheckCircle,
  Network,
} from 'lucide-react';
import { cn } from '../../lib/utils/cn';

const tabItems = [
  { value: 'game', label: 'Games', icon: <Gamepad2 className="h-4 w-4" /> },
  { value: 'users', label: 'Users', icon: <Users className="h-4 w-4" /> },
  { value: 'sc', label: 'Supply Chains', icon: <Database className="h-4 w-4" /> },
  { value: 'training', label: 'AI Training', icon: <GraduationCap className="h-4 w-4" /> },
  { value: 'supervision', label: 'Supervision', icon: <Eye className="h-4 w-4" /> },
  { value: 'comparison', label: 'Comparison', icon: <BarChart3 className="h-4 w-4" /> },
];

const AdminDashboard = () => {
  const { user, loading, isGroupAdmin } = useAuth();
  const isSystemAdmin = isSystemAdminUser(user);
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const initialTab = searchParams.get('section') || 'game';
  const initialScParam = searchParams.get('sc') || 'all';
  const [activeTab, setActiveTab] = useState(tabItems.some((tab) => tab.value === initialTab) ? initialTab : 'game');
  const [selectedSupplyChainId, setSelectedSupplyChainId] = useState(initialScParam);

  const groupId = useMemo(() => {
    const rawGroup = user?.group_id;
    if (rawGroup == null) return null;
    const parsed = Number(rawGroup);
    return Number.isFinite(parsed) ? parsed : null;
  }, [user]);

  const currentUserId = user?.id ?? null;

  useEffect(() => {
    const section = searchParams.get('section') || 'game';
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
    [searchParams, setSearchParams],
  );

  const handleTabChange = (newValue) => {
    setActiveTab(newValue);
    updateSearchParams({ section: newValue, sc: selectedSupplyChainId || 'all' });
  };

  useEffect(() => {
    const path = `/admin?section=${activeTab}&sc=${selectedSupplyChainId || 'all'}`;
    saveAdminDashboardPath(path);
  }, [activeTab, selectedSupplyChainId]);

  const [games, setGames] = useState([]);
  const [gamesLoading, setGamesLoading] = useState(true);
  const [gamesError, setGamesError] = useState(null);
  const [supplyChainConfigs, setSupplyChainConfigs] = useState([]);
  const [supplyChainsLoading, setSupplyChainsLoading] = useState(true);

  // Training status counts
  const [trainingCounts, setTrainingCounts] = useState({ trm: 0, gnn: 0, rl: 0 });

  // Fetch training checkpoint counts when training tab is active
  useEffect(() => {
    if (activeTab === 'training') {
      const fetchTrainingCounts = async () => {
        try {
          const [trmRes, gnnRes, rlRes] = await Promise.all([
            listTRMCheckpoints('./checkpoints').catch(() => ({ checkpoints: [] })),
            listGNNCheckpoints('./checkpoints').catch(() => ({ checkpoints: [] })),
            listRLCheckpoints('./checkpoints/rl').catch(() => ({ checkpoints: [] })),
          ]);

          // Count unique configs with checkpoints
          const trmConfigs = new Set();
          (trmRes?.checkpoints || []).forEach(cp => {
            const match = cp.name?.match(/^([a-z_]+)_phase/);
            if (match) trmConfigs.add(match[1]);
          });

          const gnnConfigs = new Set();
          (gnnRes?.checkpoints || []).forEach(cp => {
            if (cp.name?.includes('_temporal_gnn') || cp.name?.includes('_gnn')) {
              gnnConfigs.add(cp.name);
            }
          });

          // For RL, count unique configs by checking if checkpoint names contain config IDs
          // or fall back to counting unique algorithm types
          const rlCheckpoints = rlRes?.checkpoints || [];
          const knownConfigs = ['default_demo', 'case_demo', 'six_pack_demo', 'bottle_demo', 'three_fg_demo', 'variable_demo', 'complex_sc'];
          const rlConfigs = new Set();
          const rlAlgorithms = new Set();

          rlCheckpoints.forEach(cp => {
            const name = (cp.name || '').toLowerCase();
            // Check for config names in the checkpoint filename
            for (const configId of knownConfigs) {
              if (name.includes(configId) || name.includes(configId.replace(/_/g, '-'))) {
                rlConfigs.add(configId);
              }
            }
            // Also track unique algorithms (PPO, SAC, A2C)
            if (name.startsWith('ppo')) rlAlgorithms.add('ppo');
            if (name.startsWith('sac')) rlAlgorithms.add('sac');
            if (name.startsWith('a2c')) rlAlgorithms.add('a2c');
          });

          // Use config count if available, otherwise use algorithm count, otherwise checkpoint count
          const rlCount = rlConfigs.size > 0 ? rlConfigs.size :
                         (rlAlgorithms.size > 0 ? rlAlgorithms.size : rlCheckpoints.length);

          setTrainingCounts({
            trm: trmConfigs.size,
            gnn: gnnConfigs.size,
            rl: rlCount,
          });
        } catch (err) {
          console.error('Failed to fetch training counts:', err);
        }
      };
      fetchTrainingCounts();
    }
  }, [activeTab]);

  const refreshGames = useCallback(async () => {
    setGamesLoading(true);
    try {
      const list = await simulationApi.getGames();
      setGames(Array.isArray(list) ? list : []);
      setGamesError(null);
    } catch (error) {
      const detail = error?.response?.data?.detail || error?.message || 'Unable to load games right now.';
      setGames([]);
      setGamesError(detail);
    } finally {
      setGamesLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshGames();
  }, [refreshGames]);

  const refreshSupplyChains = useCallback(async () => {
    setSupplyChainsLoading(true);
    try {
      // Backend already filters by user's group
      const configs = await getSupplyChainConfigs();
      const data = Array.isArray(configs) ? configs : [];
      setSupplyChainConfigs(data);
      try {
        if (typeof window !== 'undefined' && window.localStorage) {
          const cache = data.reduce((acc, config) => {
            if (!config || config.id == null) {
              return acc;
            }
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
      console.warn('Unable to load supply chain configurations for dashboard filter', err);
      setSupplyChainConfigs([]);
    } finally {
      setSupplyChainsLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshSupplyChains();
  }, [refreshSupplyChains]);

  const supplyChainLookup = useMemo(() => {
    const map = {};
    if (Array.isArray(supplyChainConfigs)) {
      supplyChainConfigs.forEach((config) => {
        if (!config) return;
        const key = String(config.id);
        map[key] = {
          id: key,
          name: config.name || `Config ${key}`,
        };
      });
    }

    if (Array.isArray(games)) {
      games.forEach((game) => {
        if (!game) return;
        const rawId = game.supply_chain_config_id ?? game?.config?.supply_chain_config_id;
        if (rawId == null) return;
        const key = String(rawId);
        if (!map[key]) {
          map[key] = {
            id: key,
            name: game.supply_chain_name || game?.config?.supply_chain_name || `Config ${key}`,
          };
        }
      });
    }
    return map;
  }, [games, supplyChainConfigs]);

  const supplyChainOptions = useMemo(() => {
    const entries = Object.values(supplyChainLookup);
    entries.sort((a, b) => a.name.localeCompare(b.name));
    return [
      { id: 'all', name: 'All' },
      ...entries,
    ];
  }, [supplyChainLookup]);

  useEffect(() => {
    const scParam = searchParams.get('sc');
    const normalized = scParam && scParam !== 'all' ? String(scParam) : 'all';

    const shouldForceAll =
      normalized !== 'all' &&
      !supplyChainLookup[normalized] &&
      !gamesLoading &&
      !supplyChainsLoading;

    if (shouldForceAll) {
      if (selectedSupplyChainId !== 'all') {
        setSelectedSupplyChainId('all');
      }
      updateSearchParams({ section: activeTab, sc: 'all' });
      return;
    }

    if (normalized !== selectedSupplyChainId) {
      setSelectedSupplyChainId(normalized);
    }

    if (!scParam) {
      updateSearchParams({ section: activeTab, sc: normalized });
    }
  }, [
    searchParams,
    supplyChainLookup,
    selectedSupplyChainId,
    updateSearchParams,
    activeTab,
    gamesLoading,
    supplyChainsLoading,
  ]);

  const handleSupplyChainChange = useCallback((e) => {
    const value = e.target.value;
    const normalized = value === 'all' || value == null ? 'all' : String(value);
    setSelectedSupplyChainId(normalized);
    updateSearchParams({ section: activeTab, sc: normalized });
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

  if (isSystemAdmin && !isGroupAdmin) {
    return <Navigate to="/system/users" replace />;
  }

  if (!isGroupAdmin) {
    return <Navigate to="/unauthorized" replace />;
  }

  return (
    <div className="max-w-7xl mx-auto py-6 px-4 md:px-6">
      <Card className="mb-6">
        <CardContent className="p-4 md:p-6">
          <div className="flex flex-col gap-4 mb-4">
            <div>
              <h1 className="text-2xl font-bold mb-1">
                Group Administrator Workspace
              </h1>
              <p className="text-sm text-muted-foreground">
                Configure your supply chain templates, manage scenarioUser access, and supervise active games from a single workspace.
              </p>
            </div>
          </div>

          <div className="flex justify-start mb-4">
            <div className="w-full md:w-64">
              <label htmlFor="sc-filter" className="block text-sm font-medium mb-1">
                Supply Chain Configuration
              </label>
              <NativeSelect
                id="sc-filter"
                value={String(selectedSupplyChainId ?? 'all')}
                onChange={handleSupplyChainChange}
              >
                {(supplyChainOptions.length > 0 ? supplyChainOptions : [{ id: 'all', name: 'All' }]).map((option) => (
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
        {activeTab === 'sc' && (
          <GroupSupplyChainConfigList />
        )}

        {activeTab === 'game' && (
          <GroupGameConfigPanel
            games={games}
            loading={gamesLoading}
            error={gamesError}
            onRefresh={refreshGames}
            groupId={groupId}
            currentUserId={currentUserId}
            selectedSupplyChainId={selectedSupplyChainId}
            onSelectSupplyChain={(value) => handleSupplyChainChange({ target: { value } })}
            supplyChainOptions={supplyChainOptions}
            supplyChainMap={supplyChainLookup}
          />
        )}

        {activeTab === 'users' && <GroupPlayerManagement />}

        {activeTab === 'supervision' && (
          <GroupGameSupervisionPanel
            games={games}
            loading={gamesLoading}
            error={gamesError}
            onRefresh={refreshGames}
            groupId={groupId}
            currentUserId={currentUserId}
            selectedSupplyChainId={selectedSupplyChainId}
          />
        )}

        {activeTab === 'comparison' && (
          <GroupGameComparisonPanel
            games={games}
            loading={gamesLoading}
            error={gamesError}
            onRefresh={refreshGames}
            groupId={groupId}
            currentUserId={currentUserId}
            selectedSupplyChainId={selectedSupplyChainId}
          />
        )}

        {activeTab === 'training' && (
          <Card>
            <CardContent className="p-6">
              <div className="mb-6">
                <h2 className="text-2xl font-bold mb-1">
                  AI Model Training
                </h2>
                <p className="text-muted-foreground">
                  Train and manage AI agents for supply chain optimization and decision-making
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                {/* TRM Training Card */}
                <Card className="h-full hover:shadow-lg transition-all hover:-translate-y-1">
                  <CardContent className="p-6">
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center">
                        <Brain className="h-12 w-12 text-primary mr-3" />
                        <h3 className="text-xl font-semibold">TRM Training</h3>
                      </div>
                      {trainingCounts.trm > 0 && (
                        <div className="flex items-center gap-1 text-green-600 text-sm">
                          <CheckCircle className="h-4 w-4" />
                          <span>{trainingCounts.trm} trained</span>
                        </div>
                      )}
                    </div>

                    <p className="text-muted-foreground mb-4">
                      Lightweight 7M-parameter models with &lt;10ms inference for fast ordering decisions.
                    </p>

                    <Button
                      className="w-full"
                      size="lg"
                      onClick={() => navigate('/admin/trm')}
                    >
                      Go to TRM Training
                      <ArrowRight className="h-4 w-4 ml-2" />
                    </Button>
                  </CardContent>
                </Card>

                {/* GNN Training Card */}
                <Card className="h-full hover:shadow-lg transition-all hover:-translate-y-1">
                  <CardContent className="p-6">
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center">
                        <Sparkles className="h-12 w-12 text-purple-500 mr-3" />
                        <h3 className="text-xl font-semibold">GNN Training</h3>
                      </div>
                      {trainingCounts.gnn > 0 && (
                        <div className="flex items-center gap-1 text-green-600 text-sm">
                          <CheckCircle className="h-4 w-4" />
                          <span>{trainingCounts.gnn} trained</span>
                        </div>
                      )}
                    </div>

                    <p className="text-muted-foreground mb-4">
                      Graph Neural Networks for network-wide supply chain optimization.
                    </p>

                    <Button
                      className="w-full bg-purple-600 hover:bg-purple-700"
                      size="lg"
                      onClick={() => navigate('/admin/gnn')}
                    >
                      Go to GNN Training
                      <ArrowRight className="h-4 w-4 ml-2" />
                    </Button>
                  </CardContent>
                </Card>

                {/* RL Training Card */}
                <Card className="h-full hover:shadow-lg transition-all hover:-translate-y-1">
                  <CardContent className="p-6">
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center">
                        <Bot className="h-12 w-12 text-emerald-500 mr-3" />
                        <h3 className="text-xl font-semibold">RL Training</h3>
                      </div>
                      {trainingCounts.rl > 0 && (
                        <div className="flex items-center gap-1 text-green-600 text-sm">
                          <CheckCircle className="h-4 w-4" />
                          <span>{trainingCounts.rl} trained</span>
                        </div>
                      )}
                    </div>

                    <p className="text-muted-foreground mb-4">
                      Reinforcement Learning agents (PPO, SAC, A2C) that learn optimal policies through interaction.
                    </p>

                    <Button
                      className="w-full bg-emerald-600 hover:bg-emerald-700"
                      size="lg"
                      onClick={() => navigate('/admin/rl')}
                    >
                      Go to RL Training
                      <ArrowRight className="h-4 w-4 ml-2" />
                    </Button>
                  </CardContent>
                </Card>

                {/* Powell Framework Card */}
                <Card className="h-full hover:shadow-lg transition-all hover:-translate-y-1 border-2 border-blue-200 dark:border-blue-800">
                  <CardContent className="p-6">
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center">
                        <Network className="h-12 w-12 text-blue-600 mr-3" />
                        <h3 className="text-xl font-semibold">Powell Framework</h3>
                      </div>
                    </div>

                    <p className="text-muted-foreground mb-4">
                      Sequential Decision Analytics (SDAM): State → Policy → Decision → Exogenous pipeline with TRM agents.
                    </p>

                    <Button
                      className="w-full bg-blue-600 hover:bg-blue-700"
                      size="lg"
                      onClick={() => navigate('/admin/powell')}
                    >
                      Go to Powell Dashboard
                      <ArrowRight className="h-4 w-4 ml-2" />
                    </Button>
                  </CardContent>
                </Card>
              </div>

              <Alert variant="info" className="mt-6">
                <AlertDescription>
                  <strong>Note:</strong> AI model training requires GPU resources and may take several minutes to hours depending on configuration.
                  Ensure your supply chain configurations are finalized before starting training sessions.
                </AlertDescription>
              </Alert>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
};

export default AdminDashboard;
