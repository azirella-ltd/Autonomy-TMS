import React, { useState, useEffect } from 'react';
import { Save, Trash2 } from 'lucide-react';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Input,
  Label,
  FormField,
  Select,
  SelectOption,
  Spinner,
  H6,
  Text,
  SmallText,
} from '../common';
import { cn } from '../../lib/utils/cn';
import { useFormik } from '../../hooks/useFormik';
import { api } from '../../services/api';

const agentTypes = [
  { value: 'base', label: 'Base Agent' },
  { value: 'rule_based', label: 'Rule Based' },
  { value: 'reinforcement_learning', label: 'Reinforcement Learning' },
  { value: 'trm', label: 'TRM (Tiny Recursive Model)' },
];

const validate = (values) => {
  const errors = {};

  if (!values.role) {
    errors.role = 'Required';
  }

  if (!values.agent_type) {
    errors.agent_type = 'Required';
  }

  return errors;
};

const AgentConfigForm = ({ gameId, configId, onSuccess }) => {
  const [loading, setLoading] = useState(!!configId);
  const [error, setError] = useState(null);
  const [availableRoles, setAvailableRoles] = useState([]);

  const formik = useFormik({
    initialValues: {
      role: '',
      agent_type: 'base',
      config: {}
    },
    validate,
    onSubmit: async (values) => {
      try {
        setError(null);
        const data = {
          ...values,
          game_id: gameId
        };

        if (configId) {
          await api.put(`/agent-configs/${configId}`, data);
        } else {
          await api.post('/agent-configs', data);
        }

        if (onSuccess) onSuccess();
      } catch (err) {
        setError(err.response?.data?.detail || 'Failed to save configuration');
        console.error(err);
      }
    },
  });

  useEffect(() => {
    const fetchData = async () => {
      try {
        // Fetch available roles
        const rolesRes = await api.get(`/scenarios/${scenarioId}/available-roles`);
        setAvailableRoles(rolesRes.data);

        // If editing, load the config
        if (configId) {
          const configRes = await api.get(`/agent-configs/${configId}`);
          formik.setValues(configRes.data);
        }
      } catch (err) {
        setError('Failed to load data');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [gameId, configId, formik]);

  const renderConfigFields = () => {
    const { agent_type } = formik.values;

    switch (agent_type) {
      case 'rule_based':
        return (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <FormField label="Aggressiveness (0-1)">
              <Input
                type="number"
                min={0}
                max={1}
                step={0.1}
                value={formik.values.config?.aggressiveness || 0.5}
                onChange={(e) =>
                  formik.setFieldValue('config', {
                    ...formik.values.config,
                    aggressiveness: parseFloat(e.target.value)
                  })
                }
              />
            </FormField>
            <FormField label="Smoothing Factor (0-1)">
              <Input
                type="number"
                min={0}
                max={1}
                step={0.1}
                value={formik.values.config?.smoothing_factor || 0.7}
                onChange={(e) =>
                  formik.setFieldValue('config', {
                    ...formik.values.config,
                    smoothing_factor: parseFloat(e.target.value)
                  })
                }
              />
            </FormField>
          </div>
        );

      case 'reinforcement_learning':
        return (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <FormField label="Learning Rate (0-1)">
              <Input
                type="number"
                min={0}
                max={1}
                step={0.01}
                value={formik.values.config?.learning_rate || 0.01}
                onChange={(e) =>
                  formik.setFieldValue('config', {
                    ...formik.values.config,
                    learning_rate: parseFloat(e.target.value)
                  })
                }
              />
            </FormField>
            <FormField label="Discount Factor (0-1)">
              <Input
                type="number"
                min={0}
                max={1}
                step={0.1}
                value={formik.values.config?.discount_factor || 0.9}
                onChange={(e) =>
                  formik.setFieldValue('config', {
                    ...formik.values.config,
                    discount_factor: parseFloat(e.target.value)
                  })
                }
              />
            </FormField>
          </div>
        );

      default:
        return (
          <Text className="text-muted-foreground">
            No additional configuration required for this agent type.
          </Text>
        );
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center p-8">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <Card>
      <CardContent className="p-6">
        <H6 className="mb-4">
          {configId ? 'Edit' : 'Create'} Agent Configuration
        </H6>

        {error && (
          <Alert variant="error" className="mb-4">
            {error}
          </Alert>
        )}

        <form onSubmit={formik.handleSubmit}>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Role Select */}
            <FormField
              label="Role"
              error={formik.touched.role && formik.errors.role}
            >
              <Select
                name="role"
                value={formik.values.role}
                onChange={formik.handleChange}
                disabled={!!configId}
                error={formik.touched.role && Boolean(formik.errors.role)}
              >
                <SelectOption value="" disabled>
                  Select a role
                </SelectOption>
                {availableRoles.map((role) => (
                  <SelectOption key={role} value={role}>
                    {role.charAt(0).toUpperCase() + role.slice(1)}
                  </SelectOption>
                ))}
              </Select>
            </FormField>

            {/* Agent Type Select */}
            <FormField
              label="Agent Type"
              error={formik.touched.agent_type && formik.errors.agent_type}
            >
              <Select
                name="agent_type"
                value={formik.values.agent_type}
                onChange={formik.handleChange}
                error={formik.touched.agent_type && Boolean(formik.errors.agent_type)}
              >
                {agentTypes.map((type) => (
                  <SelectOption key={type.value} value={type.value}>
                    {type.label}
                  </SelectOption>
                ))}
              </Select>
            </FormField>

            {/* Configuration Section */}
            <div className="col-span-1 md:col-span-2">
              <SmallText className="font-medium mb-2 block">
                Configuration
              </SmallText>
              <hr className="border-border mb-4" />
              {renderConfigFields()}
            </div>

            {/* Action Buttons */}
            <div className="col-span-1 md:col-span-2 flex justify-between">
              <div>
                {configId && (
                  <Button
                    type="button"
                    variant="destructive"
                    leftIcon={<Trash2 className="h-4 w-4" />}
                    onClick={async () => {
                      if (window.confirm('Are you sure you want to delete this configuration?')) {
                        try {
                          await api.delete(`/agent-configs/${configId}`);
                          if (onSuccess) onSuccess();
                        } catch (err) {
                          setError('Failed to delete configuration');
                          console.error(err);
                        }
                      }
                    }}
                  >
                    Delete
                  </Button>
                )}
              </div>
              <Button
                type="submit"
                variant="default"
                leftIcon={<Save className="h-4 w-4" />}
                loading={formik.isSubmitting}
              >
                {formik.isSubmitting ? 'Saving...' : 'Save Configuration'}
              </Button>
            </div>
          </div>
        </form>
      </CardContent>
    </Card>
  );
};

export default AgentConfigForm;
