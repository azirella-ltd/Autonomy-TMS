/**
 * User Role & Capability Management
 *
 * Allows customer admins to assign roles and customize capabilities for users in their customer organization.
 */

import { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Badge,
  Modal,
  Checkbox,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from '../../components/common';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../../components/ui/tooltip';
import {
  Users,
  Pencil,
  Save,
  X,
  ChevronDown,
  Shield,
  User,
  ShieldCheck,
  Info,
  BookOpen,
} from 'lucide-react';
import { api } from '../../services/api';

const UserRoleManagement = () => {
  const [currentTab, setCurrentTab] = useState('roles');
  const [users, setUsers] = useState([]);
  const [selectedUser, setSelectedUser] = useState(null);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Config assignment state
  const [tenantConfigs, setTenantConfigs] = useState([]);
  const [configDialogOpen, setConfigDialogOpen] = useState(false);
  const [configAssignUser, setConfigAssignUser] = useState(null);
  const [selectedConfigId, setSelectedConfigId] = useState(null);
  const [savingConfig, setSavingConfig] = useState(false);

  const capabilityCategories = {
    overview: {
      label: 'Overview & Dashboard',
      capabilities: [
        { id: 'view_dashboard', label: 'View Dashboard', description: 'Access main dashboard' },
        { id: 'view_analytics', label: 'View Analytics', description: 'Access analytics page' },
        { id: 'view_sc_analytics', label: 'View SC Analytics', description: 'Access supply chain analytics' },
      ],
    },
    insights: {
      label: 'Insights',
      capabilities: [
        { id: 'view_insights', label: 'View Insights', description: 'Access insights dashboard' },
        { id: 'manage_insights', label: 'Manage Insights', description: 'Configure insights' },
      ],
    },
    gamification: {
      label: 'Simulation',
      capabilities: [
        { id: 'view_simulations', label: 'View Scenarios', description: 'View simulation list' },
        { id: 'create_simulation', label: 'Create Scenarios', description: 'Create new simulations' },
        { id: 'play_simulation', label: 'Run Scenarios', description: 'Participate in simulations' },
        { id: 'delete_simulation', label: 'Delete Scenarios', description: 'Delete simulations' },
        { id: 'manage_simulations', label: 'Manage Scenarios', description: 'Full simulation management' },
      ],
    },
    supply_chain: {
      label: 'Supply Chain Design',
      capabilities: [
        { id: 'view_sc_configs', label: 'View SC Configs', description: 'View supply chain configurations' },
        { id: 'create_sc_config', label: 'Create SC Config', description: 'Create new configurations' },
        { id: 'edit_sc_config', label: 'Edit SC Config', description: 'Edit configurations' },
        { id: 'delete_sc_config', label: 'Delete SC Config', description: 'Delete configurations' },
        { id: 'view_inventory_models', label: 'View Inventory Models', description: 'View inventory models' },
        { id: 'manage_inventory_models', label: 'Manage Inventory Models', description: 'Manage inventory models' },
        { id: 'view_tenant_configs', label: 'View Organization Configs', description: 'View organization configurations' },
        { id: 'manage_tenant_configs', label: 'Manage Organization Configs', description: 'Manage organization configurations' },
        { id: 'view_ntier_visibility', label: 'View N-Tier Visibility', description: 'Access N-tier visibility' },
      ],
    },
    planning: {
      label: 'Planning & Optimization',
      capabilities: [
        { id: 'view_order_planning', label: 'View Order Planning', description: 'View order planning' },
        { id: 'manage_order_planning', label: 'Manage Order Planning', description: 'Manage order planning' },
        { id: 'view_demand_planning', label: 'View Demand Planning', description: 'View demand planning' },
        { id: 'manage_demand_planning', label: 'Manage Demand Planning', description: 'Manage demand planning' },
        { id: 'view_supply_planning', label: 'View Supply Planning', description: 'View supply planning' },
        { id: 'manage_supply_planning', label: 'Manage Supply Planning', description: 'Manage supply planning' },
        { id: 'view_optimization', label: 'View Optimization', description: 'View optimization results' },
        { id: 'run_optimization', label: 'Run Optimization', description: 'Execute optimization' },
      ],
    },
    ai_ml: {
      label: 'AI & ML Models',
      capabilities: [
        { id: 'use_ai_assistant', label: 'Use AI Assistant', description: 'Access Claude AI assistant' },
        { id: 'view_trm_training', label: 'View TRM Training', description: 'View TRM training dashboard' },
        { id: 'start_trm_training', label: 'Start TRM Training', description: 'Start TRM training' },
        { id: 'manage_trm_models', label: 'Manage TRM Models', description: 'Manage TRM models' },
        { id: 'view_gnn_training', label: 'View GNN Training', description: 'View GNN training dashboard' },
        { id: 'start_gnn_training', label: 'Start GNN Training', description: 'Start GNN training' },
        { id: 'manage_gnn_models', label: 'Manage GNN Models', description: 'Manage GNN models' },
        { id: 'view_model_setup', label: 'View Model Setup', description: 'View model setup' },
        { id: 'manage_model_setup', label: 'Manage Model Setup', description: 'Manage model configuration' },
      ],
    },
    collaboration: {
      label: 'Collaboration',
      capabilities: [
        { id: 'view_tenants', label: 'View Organizations', description: 'View organizations' },
        { id: 'create_tenant', label: 'Create Organizations', description: 'Create new organizations' },
        { id: 'manage_tenants', label: 'Manage Organizations', description: 'Full organization management' },
        { id: 'view_scenario_users', label: 'View ScenarioUsers', description: 'View users' },
        { id: 'manage_scenario_users', label: 'Manage ScenarioUsers', description: 'Manage users' },
        { id: 'view_users', label: 'View Users', description: 'View users' },
        { id: 'create_user', label: 'Create Users', description: 'Create new users' },
        { id: 'edit_user', label: 'Edit Users', description: 'Edit user information' },
        { id: 'delete_user', label: 'Delete Users', description: 'Delete users' },
      ],
    },
  };

  const roleTemplates = {
    TENANT_ADMIN: {
      label: 'Organization Admin',
      description: 'Full access to organization management and scenario creation',
      capabilities: [
        'view_dashboard', 'view_analytics', 'view_sc_analytics',
        'view_insights',
        'view_simulations', 'create_simulation', 'play_simulation', 'delete_simulation', 'manage_simulations',
        'view_sc_configs', 'view_inventory_models', 'view_tenant_configs', 'manage_tenant_configs', 'view_ntier_visibility',
        'view_order_planning', 'view_demand_planning', 'view_supply_planning', 'view_optimization',
        'use_ai_assistant', 'view_trm_training', 'view_gnn_training', 'view_model_setup',
        'view_tenants', 'manage_tenants', 'view_scenario_users', 'manage_scenario_users', 'view_users', 'create_user', 'edit_user',
      ],
    },
    USER: {
      label: 'User',
      description: 'Basic access to run scenarios and view information',
      capabilities: [
        'view_dashboard', 'view_analytics',
        'view_insights',
        'view_simulations', 'play_simulation',
        'view_sc_configs', 'view_ntier_visibility',
        'view_order_planning',
        'view_tenants', 'view_scenario_users',
      ],
    },
    GAME_MANAGER: {
      label: 'Scenario Manager',
      description: 'Create and manage scenarios without admin access',
      capabilities: [
        'view_dashboard', 'view_analytics', 'view_sc_analytics',
        'view_insights',
        'view_simulations', 'create_simulation', 'play_simulation', 'manage_simulations',
        'view_sc_configs', 'view_ntier_visibility',
        'view_order_planning', 'view_demand_planning', 'view_supply_planning',
        'view_tenants', 'view_scenario_users',
      ],
    },
    ANALYST: {
      label: 'Analyst',
      description: 'View-only access with analytics and insights',
      capabilities: [
        'view_dashboard', 'view_analytics', 'view_sc_analytics',
        'view_insights',
        'view_simulations',
        'view_sc_configs', 'view_ntier_visibility',
        'view_order_planning', 'view_demand_planning', 'view_supply_planning', 'view_optimization',
        'view_trm_training', 'view_gnn_training', 'view_model_setup',
        'view_tenants', 'view_scenario_users',
      ],
    },
  };

  useEffect(() => {
    fetchUsers();
    fetchTenantConfigs();
  }, []);

  const fetchTenantConfigs = async () => {
    try {
      const response = await api.get('/supply-chain-config/');
      const configs = Array.isArray(response.data) ? response.data : (response.data.configs || []);
      setTenantConfigs(configs);
    } catch (err) {
      console.error('Failed to fetch tenant configs:', err);
    }
  };

  const fetchUsers = async () => {
    try {
      setLoading(true);
      const response = await api.get('/users');
      // API returns array directly, or object with users key
      const userData = Array.isArray(response.data) ? response.data : (response.data.users || []);
      setUsers(userData);
      setError(null);
    } catch (err) {
      console.error('Failed to fetch users:', err);
      setError('Failed to load users');
    } finally {
      setLoading(false);
    }
  };

  const handleEditUser = (user) => {
    setSelectedUser({
      ...user,
      capabilities: user.capabilities || [],
      user_type: user.user_type || 'USER',
    });
    setEditDialogOpen(true);
  };

  const handleApplyRoleTemplate = (templateKey) => {
    if (selectedUser) {
      setSelectedUser({
        ...selectedUser,
        user_type: templateKey,
        capabilities: [...roleTemplates[templateKey].capabilities],
      });
    }
  };

  const handleToggleCapability = (capabilityId) => {
    if (selectedUser) {
      const currentCaps = selectedUser.capabilities || [];
      const newCaps = currentCaps.includes(capabilityId)
        ? currentCaps.filter(c => c !== capabilityId)
        : [...currentCaps, capabilityId];

      setSelectedUser({
        ...selectedUser,
        capabilities: newCaps,
      });
    }
  };

  const handleSaveUser = async () => {
    try {
      setLoading(true);
      await api.put(`/users/${selectedUser.id}/capabilities`, {
        user_type: selectedUser.user_type,
        capabilities: selectedUser.capabilities,
      });

      setSuccess('User roles and capabilities updated successfully');
      setEditDialogOpen(false);
      fetchUsers();
    } catch (err) {
      console.error('Failed to update user:', err);
      setError('Failed to update user roles and capabilities');
    } finally {
      setLoading(false);
    }
  };

  const handleOpenConfigDialog = (user) => {
    setConfigAssignUser(user);
    setSelectedConfigId(user.default_config_id || null);
    setConfigDialogOpen(true);
  };

  const handleSaveConfig = async () => {
    if (!configAssignUser || !selectedConfigId) return;
    try {
      setSavingConfig(true);
      await api.put(`/admin/users/${configAssignUser.id}/default-config`, { config_id: selectedConfigId });
      setSuccess(`Config updated for ${configAssignUser.full_name || configAssignUser.email}`);
      setConfigDialogOpen(false);
      fetchUsers();
    } catch (err) {
      console.error('Failed to assign config:', err);
      setError(err?.response?.data?.detail || 'Failed to assign config');
    } finally {
      setSavingConfig(false);
    }
  };

  const getConfigForUser = (user) => {
    if (!user.default_config_id) return null;
    return tenantConfigs.find((c) => c.id === user.default_config_id) || null;
  };

  const getUserRoleLabel = (userType) => {
    return roleTemplates[userType]?.label || userType;
  };

  const getCapabilityCount = (user) => {
    return user.capabilities?.length || 0;
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="flex items-center gap-3 mb-6">
        <Users className="h-8 w-8 text-primary" />
        <div>
          <h1 className="text-2xl font-bold">User Role & Capability Management</h1>
          <p className="text-sm text-muted-foreground">
            Assign roles and customize capabilities for users in your organization
          </p>
        </div>
      </div>

      {error && (
        <Alert variant="destructive" className="mb-4" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {success && (
        <Alert variant="success" className="mb-4" onClose={() => setSuccess(null)}>
          {success}
        </Alert>
      )}

      <Card className="mb-6">
        <Tabs value={currentTab} onValueChange={setCurrentTab}>
          <TabsList className="w-full justify-start border-b rounded-none h-auto p-0">
            <TabsTrigger
              value="roles"
              className="flex items-center gap-2 rounded-none border-b-2 border-transparent data-[state=active]:border-primary"
            >
              <User className="h-4 w-4" />
              User Roles
            </TabsTrigger>
            <TabsTrigger
              value="templates"
              className="flex items-center gap-2 rounded-none border-b-2 border-transparent data-[state=active]:border-primary"
            >
              <Shield className="h-4 w-4" />
              Role Templates
            </TabsTrigger>
            <TabsTrigger
              value="reference"
              className="flex items-center gap-2 rounded-none border-b-2 border-transparent data-[state=active]:border-primary"
            >
              <Info className="h-4 w-4" />
              Capability Reference
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </Card>

      {currentTab === 'roles' && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <Card>
              <CardContent className="pt-4">
                <p className="text-sm text-muted-foreground">Total Users</p>
                <p className="text-3xl font-bold">{users.length}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4">
                <p className="text-sm text-muted-foreground">Organization Admins</p>
                <p className="text-3xl font-bold text-primary">
                  {users.filter(u => u.user_type === 'TENANT_ADMIN').length}
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4">
                <p className="text-sm text-muted-foreground">Users</p>
                <p className="text-3xl font-bold text-green-600">
                  {users.filter(u => u.user_type === 'USER').length}
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4">
                <p className="text-sm text-muted-foreground">Custom Roles</p>
                <p className="text-3xl font-bold text-blue-600">
                  {users.filter(u => !['TENANT_ADMIN', 'USER', 'SYSTEM_ADMIN'].includes(u.user_type)).length}
                </p>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardContent className="p-6">
              <h2 className="text-lg font-semibold mb-4">Users in Your Organization</h2>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Email</TableHead>
                    <TableHead>Role</TableHead>
                    <TableHead className="text-center">Capabilities</TableHead>
                    <TableHead>Active Config</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {users.map((user) => (
                    <TableRow key={user.id}>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          {user.user_type === 'SYSTEM_ADMIN' && <ShieldCheck className="h-4 w-4 text-destructive" />}
                          <span className="font-medium">{user.full_name || user.email}</span>
                        </div>
                      </TableCell>
                      <TableCell>{user.email}</TableCell>
                      <TableCell>
                        <Badge variant={user.user_type === 'TENANT_ADMIN' ? 'default' : 'secondary'}>
                          {getUserRoleLabel(user.user_type)}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-center">
                        <Badge variant="outline">{getCapabilityCount(user)}</Badge>
                      </TableCell>
                      <TableCell>
                        {(() => {
                          const cfg = getConfigForUser(user);
                          if (!cfg) return <span className="text-xs text-muted-foreground">Default</span>;
                          return (
                            <div className="flex items-center gap-1.5">
                              <Badge
                                variant={cfg.mode === 'learning' ? 'warning' : 'default'}
                                className="text-xs"
                              >
                                {cfg.mode === 'learning' ? 'Learning' : 'Production'}
                              </Badge>
                              <span className="text-xs text-muted-foreground truncate max-w-[120px]" title={cfg.name}>
                                {cfg.name}
                              </span>
                            </div>
                          );
                        })()}
                      </TableCell>
                      <TableCell>
                        <Badge variant={user.is_active ? 'success' : 'secondary'}>
                          {user.is_active ? 'Active' : 'Inactive'}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-1">
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleOpenConfigDialog(user)}
                                  disabled={user.user_type === 'SYSTEM_ADMIN'}
                                >
                                  <BookOpen className="h-4 w-4" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>Assign Config</TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleEditUser(user)}
                                  disabled={user.user_type === 'SYSTEM_ADMIN'}
                                >
                                  <Pencil className="h-4 w-4" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>Edit Roles & Capabilities</TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}

      {currentTab === 'templates' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {Object.entries(roleTemplates).map(([key, template]) => (
            <Card key={key}>
              <CardContent className="pt-6">
                <h3 className="text-lg font-semibold mb-1">{template.label}</h3>
                <p className="text-sm text-muted-foreground mb-4">{template.description}</p>
                <div>
                  <p className="text-sm font-medium mb-2">
                    Included Capabilities ({template.capabilities.length})
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {template.capabilities.slice(0, 10).map((cap) => (
                      <Badge key={cap} variant="outline">{cap}</Badge>
                    ))}
                    {template.capabilities.length > 10 && (
                      <Badge variant="secondary">+{template.capabilities.length - 10} more</Badge>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {currentTab === 'reference' && (
        <Card>
          <CardContent className="pt-6">
            <h2 className="text-lg font-semibold mb-2">Available Capabilities by Category</h2>
            <p className="text-sm text-muted-foreground mb-4">
              Complete list of all capabilities that can be assigned to users
            </p>

            <Accordion type="multiple">
              {Object.entries(capabilityCategories).map(([key, category]) => (
                <AccordionItem key={key} value={key}>
                  <AccordionTrigger>
                    <span className="font-semibold">{category.label} ({category.capabilities.length})</span>
                  </AccordionTrigger>
                  <AccordionContent>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
                      {category.capabilities.map((cap) => (
                        <div key={cap.id} className="p-3 border rounded">
                          <p className="font-medium text-sm">{cap.label}</p>
                          <p className="text-xs text-muted-foreground">{cap.description}</p>
                          <Badge variant="outline" className="mt-2">{cap.id}</Badge>
                        </div>
                      ))}
                    </div>
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </CardContent>
        </Card>
      )}

      {/* Config Assignment Dialog */}
      <Modal
        isOpen={configDialogOpen}
        onClose={() => setConfigDialogOpen(false)}
        title={
          <div className="flex items-center gap-2">
            <BookOpen className="h-5 w-5 text-primary" />
            <div>
              <p>Assign Active Config</p>
              <p className="text-sm text-muted-foreground font-normal">{configAssignUser?.email}</p>
            </div>
          </div>
        }
        size="md"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setConfigDialogOpen(false)} leftIcon={<X className="h-4 w-4" />}>
              Cancel
            </Button>
            <Button onClick={handleSaveConfig} disabled={savingConfig || !selectedConfigId} leftIcon={<Save className="h-4 w-4" />}>
              {savingConfig ? 'Saving…' : 'Save'}
            </Button>
          </div>
        }
      >
        {configAssignUser && (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Select the supply chain configuration this user will see when they log in.
            </p>

            {/* Production configs */}
            {tenantConfigs.filter((c) => c.mode !== 'learning').length > 0 && (
              <div>
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Production</p>
                <div className="space-y-1">
                  {tenantConfigs.filter((c) => c.mode !== 'learning').map((cfg) => (
                    <label
                      key={cfg.id}
                      className={`flex items-center gap-3 p-3 rounded border cursor-pointer transition-colors ${
                        selectedConfigId === cfg.id ? 'border-primary bg-primary/5' : 'hover:bg-muted/50'
                      }`}
                    >
                      <input
                        type="radio"
                        name="config"
                        value={cfg.id}
                        checked={selectedConfigId === cfg.id}
                        onChange={() => setSelectedConfigId(cfg.id)}
                        className="accent-primary"
                      />
                      <div>
                        <p className="text-sm font-medium">{cfg.name}</p>
                        {cfg.description && <p className="text-xs text-muted-foreground">{cfg.description}</p>}
                      </div>
                    </label>
                  ))}
                </div>
              </div>
            )}

            {/* Learning configs */}
            {tenantConfigs.filter((c) => c.mode === 'learning').length > 0 && (
              <div>
                <p className="text-xs font-semibold text-amber-600 uppercase tracking-wide mb-2">Learning</p>
                <div className="space-y-1">
                  {tenantConfigs.filter((c) => c.mode === 'learning').map((cfg) => (
                    <label
                      key={cfg.id}
                      className={`flex items-center gap-3 p-3 rounded border cursor-pointer transition-colors ${
                        selectedConfigId === cfg.id ? 'border-amber-500 bg-amber-50' : 'hover:bg-muted/50'
                      }`}
                    >
                      <input
                        type="radio"
                        name="config"
                        value={cfg.id}
                        checked={selectedConfigId === cfg.id}
                        onChange={() => setSelectedConfigId(cfg.id)}
                        className="accent-amber-500"
                      />
                      <div>
                        <p className="text-sm font-medium">{cfg.name}</p>
                        {cfg.description && <p className="text-xs text-muted-foreground">{cfg.description}</p>}
                      </div>
                    </label>
                  ))}
                </div>
              </div>
            )}

            {tenantConfigs.length === 0 && (
              <p className="text-sm text-muted-foreground italic">No supply chain configs available for this tenant.</p>
            )}
          </div>
        )}
      </Modal>

      {/* Edit User Dialog */}
      <Modal
        isOpen={editDialogOpen}
        onClose={() => setEditDialogOpen(false)}
        title={
          <div className="flex items-center gap-2">
            <Users className="h-5 w-5 text-primary" />
            <div>
              <p>Edit User Roles & Capabilities</p>
              <p className="text-sm text-muted-foreground font-normal">{selectedUser?.email}</p>
            </div>
          </div>
        }
        size="lg"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setEditDialogOpen(false)} leftIcon={<X className="h-4 w-4" />}>
              Cancel
            </Button>
            <Button onClick={handleSaveUser} disabled={loading} leftIcon={<Save className="h-4 w-4" />}>
              Save Changes
            </Button>
          </div>
        }
      >
        {selectedUser && (
          <div className="space-y-6">
            {/* Role Template Selection */}
            <div>
              <h4 className="font-semibold mb-3">Quick Apply Role Template</h4>
              <div className="grid grid-cols-2 gap-2">
                {Object.entries(roleTemplates).map(([key, template]) => (
                  <Button
                    key={key}
                    variant={selectedUser.user_type === key ? 'default' : 'outline'}
                    className="justify-start h-auto py-3"
                    onClick={() => handleApplyRoleTemplate(key)}
                  >
                    <div className="text-left">
                      <p className="font-medium">{template.label}</p>
                      <p className="text-xs opacity-70">{template.capabilities.length} capabilities</p>
                    </div>
                  </Button>
                ))}
              </div>
            </div>

            {/* Custom Capabilities */}
            <div>
              <div className="flex items-center gap-2 mb-3">
                <h4 className="font-semibold">Custom Capability Selection</h4>
                <Badge>{selectedUser.capabilities?.length || 0} selected</Badge>
              </div>

              <Accordion type="multiple">
                {Object.entries(capabilityCategories).map(([key, category]) => (
                  <AccordionItem key={key} value={key}>
                    <AccordionTrigger>
                      <div className="flex items-center gap-2">
                        <span>{category.label}</span>
                        <Badge variant="outline">
                          {category.capabilities.filter(c => selectedUser.capabilities?.includes(c.id)).length}/{category.capabilities.length}
                        </Badge>
                      </div>
                    </AccordionTrigger>
                    <AccordionContent>
                      <div className="space-y-2 pt-2">
                        {category.capabilities.map((cap) => (
                          <label key={cap.id} className="flex items-start gap-3 p-2 hover:bg-muted/50 rounded cursor-pointer">
                            <Checkbox
                              checked={selectedUser.capabilities?.includes(cap.id) || false}
                              onCheckedChange={() => handleToggleCapability(cap.id)}
                            />
                            <div>
                              <p className="text-sm font-medium">{cap.label}</p>
                              <p className="text-xs text-muted-foreground">{cap.description}</p>
                            </div>
                          </label>
                        ))}
                      </div>
                    </AccordionContent>
                  </AccordionItem>
                ))}
              </Accordion>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default UserRoleManagement;
