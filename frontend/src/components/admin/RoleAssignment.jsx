/**
 * Role Assignment Component
 *
 * Manages role assignments for games, allowing switching between
 * human and AI-controlled users.
 */

import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Spinner,
  Label,
  Select,
  SelectOption,
} from '../common';
import { api } from '../../services/api';
import { cn } from '../../lib/utils/cn';

const RoleAssignment = ({ gameId }) => {
  const [roles, setRoles] = useState([]);
  const [assignments, setAssignments] = useState({});
  const [agentConfigs, setAgentConfigs] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        // Fetch available roles
        const rolesRes = await api.get(`/scenarios/${scenarioId}/available-roles`);
        setRoles(rolesRes.data);

        // Fetch current assignments
        const assignmentsRes = await api.get(`/scenarios/${scenarioId}/roles`);
        setAssignments(assignmentsRes.data);

        // Fetch agent configs
        const configsRes = await api.get(`/scenarios/${scenarioId}/agent-configs`);
        setAgentConfigs(configsRes.data);

        // Fetch users (you'll need to implement this endpoint)
        const usersRes = await api.get(`/scenarios/${scenarioId}/users`);
        setUsers(usersRes.data);

        setLoading(false);
      } catch (err) {
        setError('Failed to load role assignments');
        console.error(err);
        setLoading(false);
      }
    };

    fetchData();
  }, [gameId]);

  const handleRoleChange = (role, field, value) => {
    setAssignments(prev => ({
      ...prev,
      [role]: {
        ...(prev[role] || {}),
        [field]: value
      }
    }));
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      const updates = [];

      // Update each role assignment
      for (const [role, assignment] of Object.entries(assignments)) {
        updates.push(
          api.put(`/scenarios/${scenarioId}/roles/${role}`, assignment)
        );
      }

      await Promise.all(updates);
      // Show success message or update UI
    } catch (err) {
      setError('Failed to save role assignments');
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center p-8">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <Alert variant="error" className="m-4">
        {error}
      </Alert>
    );
  }

  return (
    <div>
      <h2 className="text-lg font-semibold mb-4">
        Role Assignments
      </h2>

      <Card>
        <CardContent className="p-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {roles.map((role) => (
              <div key={role} className="space-y-3">
                <h3 className="font-medium">
                  {role.charAt(0).toUpperCase() + role.slice(1)}
                </h3>

                {/* AI/Human Toggle */}
                <label className="flex items-center gap-3 cursor-pointer">
                  <div className="relative">
                    <input
                      type="checkbox"
                      checked={assignments[role]?.is_ai || false}
                      onChange={(e) =>
                        handleRoleChange(role, 'is_ai', e.target.checked)
                      }
                      className="sr-only peer"
                    />
                    <div className={cn(
                      'w-11 h-6 rounded-full transition-colors',
                      assignments[role]?.is_ai ? 'bg-primary' : 'bg-muted'
                    )}>
                      <div className={cn(
                        'absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform',
                        assignments[role]?.is_ai && 'translate-x-5'
                      )} />
                    </div>
                  </div>
                  <span className="text-sm">
                    {assignments[role]?.is_ai ? 'AI Controlled' : 'Human Controlled'}
                  </span>
                </label>

                {/* Agent Config or User Selection */}
                {assignments[role]?.is_ai ? (
                  <div className="space-y-1">
                    <Label>Agent Configuration</Label>
                    <Select
                      value={assignments[role]?.agent_config_id || ''}
                      onChange={(e) =>
                        handleRoleChange(role, 'agent_config_id', e.target.value)
                      }
                      size="sm"
                    >
                      <SelectOption value="">Select agent...</SelectOption>
                      {agentConfigs.map((config) => (
                        <SelectOption key={config.id} value={config.id}>
                          {config.agent_type} - {config.role}
                        </SelectOption>
                      ))}
                    </Select>
                  </div>
                ) : (
                  <div className="space-y-1">
                    <Label>Assign User</Label>
                    <Select
                      value={assignments[role]?.user_id || ''}
                      onChange={(e) =>
                        handleRoleChange(role, 'user_id', e.target.value)
                      }
                      size="sm"
                    >
                      <SelectOption value="">Select user...</SelectOption>
                      {users.map((user) => (
                        <SelectOption key={user.id} value={user.id}>
                          {user.name || user.email}
                        </SelectOption>
                      ))}
                    </Select>
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="flex justify-end mt-6">
            <Button
              onClick={handleSave}
              disabled={saving}
              loading={saving}
            >
              {saving ? 'Saving...' : 'Save Changes'}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default RoleAssignment;
