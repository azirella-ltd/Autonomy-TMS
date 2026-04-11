import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { toast } from 'react-toastify';
import {
  Card,
  CardHeader,
  CardContent,
  CardTitle,
  Button,
  Input,
  Label,
  FormField,
  Spinner,
  Select,
  SelectOption,
} from '../components/common';
import { Plus, ArrowLeft, User, Bot } from 'lucide-react';
import { cn } from '@azirella-ltd/autonomy-frontend';
import PageLayout from '../components/PageLayout';
import simulationApi, { api } from '../services/api';
import { getAllConfigs as getAllSupplyConfigs } from '../services/supplyChainConfigService';

const roleOptions = [
  { value: 'retailer', label: 'Retailer' },
  { value: 'wholesaler', label: 'Wholesaler' },
  { value: 'distributor', label: 'Distributor' },
  { value: 'manufacturer', label: 'Manufacturer' },
];

const agentStrategyLabels = {
  AUTONOMY_DTCE: 'Autonomy - Roles',
  AUTONOMY_DTCE_CENTRAL: 'Autonomy - Roles + Supervisor',
  AUTONOMY_DTCE_GLOBAL: 'Autonomy - SC Orchestrator',
  LLM_SUPERVISED: 'Autonomy LLM - Roles + Supervisor',
  LLM_GLOBAL: 'Autonomy LLM - SC Orchestrator',
  LLM_BALANCED: 'Autonomy LLM - Balanced',
  LLM_CONSERVATIVE: 'Autonomy LLM - Conservative',
  LLM_AGGRESSIVE: 'Autonomy LLM - Aggressive',
  LLM_ADAPTIVE: 'Autonomy LLM - Adaptive',
  NAIVE: 'Heuristic - Naive',
  BULLWHIP: 'Heuristic - Bullwhip',
  CONSERVATIVE: 'Heuristic - Conservative',
  RANDOM: 'Heuristic - Random',
  PID_HEURISTIC: 'Heuristic - PID',
};

const resolveStrategyLabel = (scenarioUser) => {
  const raw = scenarioUser?.agent_type ?? scenarioUser?.ai_strategy ?? scenarioUser?.strategy;
  if (!raw) {
    return '';
  }
  const key =
    typeof raw === 'string'
      ? raw.toUpperCase()
      : String(raw?.value ?? raw?.name ?? '').toUpperCase();
  return agentStrategyLabels[key] ? ` - ${agentStrategyLabels[key]}` : '';
};

const ScenarioUsersPage = () => {
  const [games, setGames] = useState([]);
  const [coreConfigs, setCoreConfigs] = useState([]);
  const [selectedCoreConfigId, setSelectedCoreConfigId] = useState('');
  const [users, setUsers] = useState([]);
  const [selectedGameId, setSelectedGameId] = useState('');
  const [loading, setLoading] = useState(true);
  const [scenarioUsers, setScenarioUsers] = useState([]);

  const [form, setForm] = useState({
    name: '',
    role: 'retailer',
    type: 'agent',
    agent_type: 'LLM_BALANCED',
    user_id: '',
  });

  const fetchScenarioUsers = useCallback(async (gameId) => {
    if (!gameId) return;
    try {
      const data = await simulationApi.getScenarioUsers(gameId);
      setScenarioUsers(data);
    } catch (e) {
      console.error(e);
      toast.error('Failed to load users');
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const [gamesData, usersRes, cfgs] = await Promise.all([
          simulationApi.getScenarios(),
          api.get('/auth/users/'),
          (async () => {
            try {
              const list = await getAllSupplyConfigs();
              return Array.isArray(list) ? list : [];
            } catch {
              return [];
            }
          })()
        ]);
        setGames(gamesData);
        setUsers(usersRes.data || []);
        setCoreConfigs(cfgs);
        if (cfgs?.length) setSelectedCoreConfigId(String(cfgs[0].id));
        if (Array.isArray(gamesData) && gamesData.length) {
          setSelectedGameId(String(gamesData[0].id));
        }
      } catch (e) {
        console.error(e);
        toast.error('Failed to load initial data');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  useEffect(() => {
    fetchScenarioUsers(selectedGameId);
  }, [fetchScenarioUsers, selectedGameId]);

  const handleAdd = async () => {
    if (!selectedGameId) return;
    try {
      const payload = {
        name: form.name || `${form.role} (${form.type === 'human' ? 'Human' : 'Agent'})`,
        role: form.role,
        is_ai: form.type !== 'human',
        scenario_user_type: form.type === 'human' ? 'human' : 'agent',
        agent_type: form.type !== 'human' ? form.agent_type : undefined,
        user_id: form.type === 'human' ? Number(form.user_id) || null : null,
      };
      if (payload.agent_type === 'AUTONOMY_DTCE_CENTRAL' || payload.agent_type === 'LLM_SUPERVISED') {
        payload.autonomy_override_pct = 0.05;
      }
      await simulationApi.addScenarioUser(Number(selectedGameId), payload);
      toast.success('User added');
      setForm(prev => ({ ...prev, name: '' }));
      fetchScenarioUsers(selectedGameId);
    } catch (e) {
      console.error(e);
      const msg = e?.response?.data?.detail || 'Failed to add user';
      toast.error(msg);
    }
  };

  // Quick create a minimal game if none exist
  const quickCreateGame = async () => {
    try {
      const payload = {
        name: `Quick Game ${new Date().toLocaleString()}`,
        max_periods: 20,
        demand_pattern: { type: 'classic', params: { initial_demand: 4, change_week: 6, final_demand: 8 } },
      };
      const newGame = await simulationApi.createScenario(payload);
      toast.success('Alternative created');
      setGames((prev) => (Array.isArray(prev) ? [...prev, newGame] : [newGame]));
      const id = String(newGame.id);
      setSelectedGameId(id);
      fetchScenarioUsers(id);
    } catch (e) {
      console.error('Quick create failed', e);
      toast.error(e?.response?.data?.detail || e.message || 'Failed to create alternative');
    }
  };

  if (loading) {
    return (
      <PageLayout title="Users">
        <div className="flex items-center justify-center p-8">
          <Spinner size="lg" />
        </div>
      </PageLayout>
    );
  }

  return (
    <PageLayout title="Users">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-foreground">Users</h1>
        <Button
          as={Link}
          to="/scenarios"
          variant="outline"
          leftIcon={<ArrowLeft className="h-4 w-4" />}
        >
          Back to Games
        </Button>
      </div>

      <Card className="mb-6">
        <CardHeader>
          <div className="flex flex-wrap items-end gap-4">
            <FormField label="Core Configuration" className="w-full max-w-xs">
              <Select
                value={selectedCoreConfigId}
                onChange={(e) => setSelectedCoreConfigId(e.target.value)}
              >
                {coreConfigs.length === 0 && (
                  <SelectOption value="">System Defaults</SelectOption>
                )}
                {coreConfigs.map(c => (
                  <SelectOption key={c.id} value={c.id}>{c.name}</SelectOption>
                ))}
              </Select>
            </FormField>
            <FormField label="Alternative" className="w-full max-w-xs">
              {games.length > 0 ? (
                <Select
                  value={selectedGameId}
                  onChange={(e) => setSelectedGameId(e.target.value)}
                >
                  {games.map(g => (
                    <SelectOption key={g.id} value={g.id}>{g.name}</SelectOption>
                  ))}
                </Select>
              ) : (
                <div className="flex items-center gap-3">
                  <span className="text-sm text-muted-foreground">No scenarios found.</span>
                  <Button
                    variant="outline"
                    size="sm"
                    leftIcon={<Plus className="h-4 w-4" />}
                    onClick={quickCreateGame}
                  >
                    Create Scenario
                  </Button>
                </div>
              )}
            </FormField>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Add ScenarioUser Form */}
            <div>
              <h3 className="text-lg font-semibold text-foreground mb-4">Add User</h3>
              <div className="space-y-4">
                <FormField label="Role">
                  <Select
                    value={form.role}
                    onChange={(e) => setForm({ ...form, role: e.target.value })}
                  >
                    {roleOptions.map(o => (
                      <SelectOption key={o.value} value={o.value}>{o.label}</SelectOption>
                    ))}
                  </Select>
                </FormField>

                <FormField label="Type">
                  <Select
                    value={form.type}
                    onChange={(e) => setForm({ ...form, type: e.target.value })}
                  >
                    <SelectOption value="agent">Agent</SelectOption>
                    <SelectOption value="human">Human</SelectOption>
                  </Select>
                </FormField>

                {form.type === 'agent' && (
                  <FormField label="Agent Type">
                    <Select
                      value={form.agent_type}
                      onChange={(e) => setForm({ ...form, agent_type: e.target.value })}
                    >
                      <SelectOption value="AUTONOMY_DTCE">Autonomy - Roles</SelectOption>
                      <SelectOption value="AUTONOMY_DTCE_CENTRAL">Autonomy - Roles + Supervisor</SelectOption>
                      <SelectOption value="AUTONOMY_DTCE_GLOBAL">Autonomy - SC Orchestrator</SelectOption>
                      <SelectOption value="LLM_BALANCED">Autonomy LLM - Balanced</SelectOption>
                      <SelectOption value="LLM_CONSERVATIVE">Autonomy LLM - Conservative</SelectOption>
                      <SelectOption value="LLM_AGGRESSIVE">Autonomy LLM - Aggressive</SelectOption>
                      <SelectOption value="LLM_SUPERVISED">Autonomy LLM - Roles + Supervisor</SelectOption>
                      <SelectOption value="LLM_GLOBAL">Autonomy LLM - SC Orchestrator</SelectOption>
                      <SelectOption value="NAIVE">Heuristic - Naive</SelectOption>
                      <SelectOption value="BULLWHIP">Heuristic - Bullwhip</SelectOption>
                      <SelectOption value="CONSERVATIVE">Heuristic - Conservative</SelectOption>
                      <SelectOption value="RANDOM">Heuristic - Random</SelectOption>
                      <SelectOption value="PID_HEURISTIC">Heuristic - PID</SelectOption>
                    </Select>
                  </FormField>
                )}

                {form.type === 'human' && (
                  <FormField label="User">
                    <Select
                      placeholder="Select user"
                      value={form.user_id}
                      onChange={(e) => setForm({ ...form, user_id: e.target.value })}
                    >
                      {users.map(u => (
                        <SelectOption key={u.id} value={u.id}>{u.email || u.username}</SelectOption>
                      ))}
                    </Select>
                  </FormField>
                )}

                <FormField label="Display Name (optional)">
                  <Input
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    placeholder="e.g., Retailer (Trevor)"
                  />
                </FormField>

                <Button onClick={handleAdd} className="w-full">
                  Add User
                </Button>
              </div>
            </div>

            {/* Current ScenarioUsers */}
            <div>
              <h3 className="text-lg font-semibold text-foreground mb-4">Current Users</h3>
              {users.length === 0 ? (
                <p className="text-sm text-muted-foreground">No users yet for this game.</p>
              ) : (
                <div className="space-y-3">
                  {users.map(p => (
                    <div
                      key={p.id}
                      className="border border-border rounded-lg p-4 bg-card"
                    >
                      <div className="flex items-center justify-between flex-wrap gap-2">
                        <div className="flex items-center gap-2">
                          {p.scenario_user_type === 'agent' || p.is_ai ? (
                            <Bot className="h-5 w-5 text-primary" />
                          ) : (
                            <User className="h-5 w-5 text-muted-foreground" />
                          )}
                          <span className="font-semibold text-foreground">{p.name}</span>
                        </div>
                        <span className="text-sm text-muted-foreground capitalize">
                          {p.role.toLowerCase()}
                        </span>
                        <span className="text-sm text-muted-foreground">
                          {p.scenario_user_type === 'agent' || p.is_ai
                            ? `AI${resolveStrategyLabel(p)}`
                            : 'Human'}
                        </span>
                        {p.user_id && (
                          <span className="text-xs text-muted-foreground">
                            User #{p.user_id}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    </PageLayout>
  );
};

export default ScenarioUsersPage;
