/**
 * TRM Test Panel Component
 *
 * Provides UI for testing TRM model with custom inputs.
 */

import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Chip,
  Input,
  Label,
  FormField,
  Textarea,
  Select,
  SelectOption,
  NativeSelect,
  Typography,
  H4,
  H6,
  Text,
  SmallText,
  Spinner,
} from '../common';
import { cn } from '../../lib/utils/cn';
import { Play, FlaskConical } from 'lucide-react';
import { testModel } from '../../services/trmApi';
import { api } from '../../services/api';

const TRMTestPanel = () => {
  // Site selection for per-site model testing
  const [sites, setSites] = useState([]);
  const [sitesLoading, setSitesLoading] = useState(true);
  const [selectedSiteId, setSelectedSiteId] = useState('');

  const [testInputs, setTestInputs] = useState({
    inventory: 100,
    backlog: 10,
    pipeline: 50,
    demand_history: [45, 50, 48, 52, 49, 47, 51, 50, 48, 46],
    node_type: 'retailer',
    node_position: 0
  });

  const [testResult, setTestResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const nodeTypes = ['retailer', 'wholesaler', 'distributor', 'factory', 'supplier', 'market'];

  // Load sites on mount
  useEffect(() => {
    const loadSites = async () => {
      setSitesLoading(true);
      try {
        const response = await api.get('/sites');
        const siteList = response.data || [];
        setSites(siteList.filter(s =>
          ['INVENTORY', 'MANUFACTURER'].includes(s.master_type?.toUpperCase?.() || s.master_type)
        ));
      } catch (err) {
        console.error('Failed to load sites:', err);
      } finally {
        setSitesLoading(false);
      }
    };
    loadSites();
  }, []);

  const handleInputChange = (field, value) => {
    setTestInputs(prev => ({
      ...prev,
      [field]: value
    }));
  };

  const handleDemandHistoryChange = (value) => {
    // Parse comma-separated values
    const values = value.split(',').map(v => parseFloat(v.trim())).filter(v => !isNaN(v));
    setTestInputs(prev => ({
      ...prev,
      demand_history: values
    }));
  };

  const handleRunTest = async () => {
    setError(null);
    setTestResult(null);
    setLoading(true);

    try {
      const payload = { ...testInputs };
      if (selectedSiteId) {
        payload.site_id = parseInt(selectedSiteId);
      }
      const result = await testModel(payload);
      setTestResult(result);
    } catch (err) {
      setError(`Test failed: ${err.response?.data?.detail || err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const generateRandomScenario = () => {
    const randomDemand = Array.from({ length: 10 }, () =>
      Math.round(30 + Math.random() * 40)
    );

    setTestInputs({
      inventory: Math.round(Math.random() * 200),
      backlog: Math.round(Math.random() * 30),
      pipeline: Math.round(Math.random() * 100),
      demand_history: randomDemand,
      node_type: nodeTypes[Math.floor(Math.random() * nodeTypes.length)],
      node_position: Math.floor(Math.random() * 4)
    });

    setTestResult(null);
    setError(null);
  };

  return (
    <div className="p-6">
      <H4 gutterBottom>
        AI Agent Testing
      </H4>
      <SmallText color="textSecondary" className="mb-4">
        Test the AI agent with custom supply chain scenarios to validate predictions.
      </SmallText>

      {error && (
        <Alert variant="error" onClose={() => setError(null)} className="mb-4">
          {error}
        </Alert>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Test Inputs */}
        <Card>
          <CardContent>
            <div className="flex justify-between items-center mb-4">
              <H6>
                Test Inputs
              </H6>
              <Button
                size="sm"
                variant="ghost"
                leftIcon={<FlaskConical className="h-4 w-4" />}
                onClick={generateRandomScenario}
              >
                Random Scenario
              </Button>
            </div>

            {/* Site Selector */}
            <FormField label="Site (optional)" className="mb-4">
              {sitesLoading ? (
                <div className="flex items-center gap-2 py-1">
                  <Spinner size="sm" />
                  <SmallText color="textSecondary">Loading sites...</SmallText>
                </div>
              ) : (
                <NativeSelect
                  value={selectedSiteId}
                  onChange={(e) => setSelectedSiteId(e.target.value)}
                >
                  <option value="">Global (no site filter)</option>
                  {sites.map(site => (
                    <option key={site.id} value={site.id}>
                      {site.name} ({site.master_type})
                    </option>
                  ))}
                </NativeSelect>
              )}
              <SmallText color="textSecondary" className="mt-1">
                Select a site to test with its per-site trained model checkpoint.
              </SmallText>
            </FormField>

            <div className="grid grid-cols-12 gap-4">
              {/* Inventory State */}
              <div className="col-span-12">
                <Typography variant="subtitle2" className="mb-2">
                  Inventory State
                </Typography>
              </div>

              <div className="col-span-4">
                <FormField label="Inventory">
                  <Input
                    type="number"
                    value={testInputs.inventory}
                    onChange={(e) => handleInputChange('inventory', parseFloat(e.target.value))}
                    min={0}
                  />
                </FormField>
              </div>

              <div className="col-span-4">
                <FormField label="Backlog">
                  <Input
                    type="number"
                    value={testInputs.backlog}
                    onChange={(e) => handleInputChange('backlog', parseFloat(e.target.value))}
                    min={0}
                  />
                </FormField>
              </div>

              <div className="col-span-4">
                <FormField label="Pipeline">
                  <Input
                    type="number"
                    value={testInputs.pipeline}
                    onChange={(e) => handleInputChange('pipeline', parseFloat(e.target.value))}
                    min={0}
                  />
                </FormField>
              </div>

              {/* Node Configuration */}
              <div className="col-span-12">
                <Typography variant="subtitle2" className="mt-2 mb-2">
                  Node Configuration
                </Typography>
              </div>

              <div className="col-span-8">
                <FormField label="Node Type">
                  <Select
                    value={testInputs.node_type}
                    onChange={(e) => handleInputChange('node_type', e.target.value)}
                  >
                    {nodeTypes.map(type => (
                      <SelectOption key={type} value={type}>
                        {type.charAt(0).toUpperCase() + type.slice(1)}
                      </SelectOption>
                    ))}
                  </Select>
                </FormField>
              </div>

              <div className="col-span-4">
                <FormField label="Position">
                  <Input
                    type="number"
                    value={testInputs.node_position}
                    onChange={(e) => handleInputChange('node_position', parseInt(e.target.value))}
                    min={0}
                    max={9}
                  />
                </FormField>
              </div>

              {/* Demand History */}
              <div className="col-span-12">
                <Typography variant="subtitle2" className="mt-2 mb-2">
                  Demand History
                </Typography>
              </div>

              <div className="col-span-12">
                <FormField
                  label="Demand History (comma-separated)"
                  helperText="Enter recent demand observations (e.g., 45, 50, 48, 52)"
                >
                  <Textarea
                    value={testInputs.demand_history.join(', ')}
                    onChange={(e) => handleDemandHistoryChange(e.target.value)}
                    rows={2}
                  />
                </FormField>
              </div>

              <div className="col-span-12">
                <div className="flex gap-1 flex-wrap">
                  {testInputs.demand_history.map((value, index) => (
                    <Chip
                      key={index}
                      variant="outline"
                      size="sm"
                    >
                      {value}
                    </Chip>
                  ))}
                </div>
              </div>
            </div>

            {/* Run Test Button */}
            <Button
              variant="default"
              fullWidth
              size="lg"
              leftIcon={<Play className="h-4 w-4" />}
              onClick={handleRunTest}
              disabled={loading}
              loading={loading}
              className="mt-6"
            >
              {loading ? 'Running Test...' : 'Run Test'}
            </Button>
          </CardContent>
        </Card>

        {/* Test Results */}
        <div className="space-y-4">
          <Card>
            <CardContent>
              <H6 gutterBottom>
                Test Results
              </H6>

              {testResult ? (
                <div>
                  <div className="p-6 bg-primary text-primary-foreground rounded-lg mb-4">
                    <div className="text-4xl font-bold text-center">
                      {testResult.order_quantity.toFixed(2)}
                    </div>
                    <SmallText className="text-center text-primary-foreground/80 block">
                      Recommended Order Quantity
                    </SmallText>
                  </div>

                  <hr className="border-border my-4" />

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <SmallText color="textSecondary">
                        Model Used
                      </SmallText>
                      <div className="mt-1">
                        <Chip
                          variant={testResult.model_used ? 'success' : 'warning'}
                          size="sm"
                        >
                          {testResult.model_used ? 'AI Agent' : 'Heuristic'}
                        </Chip>
                      </div>
                    </div>

                    <div>
                      <SmallText color="textSecondary">
                        Fallback Used
                      </SmallText>
                      <div className="mt-1">
                        <Chip
                          variant={testResult.fallback_used ? 'warning' : 'secondary'}
                          size="sm"
                        >
                          {testResult.fallback_used ? 'Yes' : 'No'}
                        </Chip>
                      </div>
                    </div>
                  </div>

                  <div className="mt-4">
                    <SmallText color="textSecondary" className="mb-2 block">
                      Explanation
                    </SmallText>
                    <div className="p-3 border border-border rounded-md bg-muted/30">
                      <SmallText>
                        {testResult.explanation}
                      </SmallText>
                    </div>
                  </div>

                  {/* Analysis */}
                  <div className="mt-6">
                    <Typography variant="subtitle2" className="mb-2">
                      Input Summary
                    </Typography>
                    <div className="space-y-2">
                      <SmallText>
                        <strong>Inventory Position:</strong>{' '}
                        {testInputs.inventory + testInputs.pipeline - testInputs.backlog}
                        {' '}(Inv: {testInputs.inventory} + Pipeline: {testInputs.pipeline} - Backlog: {testInputs.backlog})
                      </SmallText>
                      <SmallText>
                        <strong>Average Recent Demand:</strong>{' '}
                        {(testInputs.demand_history.reduce((a, b) => a + b, 0) / testInputs.demand_history.length).toFixed(2)}
                      </SmallText>
                      <SmallText>
                        <strong>Demand Volatility:</strong>{' '}
                        {(() => {
                          const avg = testInputs.demand_history.reduce((a, b) => a + b, 0) / testInputs.demand_history.length;
                          const variance = testInputs.demand_history.reduce((sum, val) => sum + Math.pow(val - avg, 2), 0) / testInputs.demand_history.length;
                          return Math.sqrt(variance).toFixed(2);
                        })()}
                      </SmallText>
                    </div>
                  </div>
                </div>
              ) : (
                <Alert variant="info">
                  Configure test inputs and click "Run Test" to see predictions.
                </Alert>
              )}
            </CardContent>
          </Card>

          {/* Predefined Test Scenarios */}
          <Card>
            <CardContent>
              <H6 gutterBottom>
                Predefined Scenarios
              </H6>
              <SmallText color="textSecondary" className="mb-4 block">
                Quick test scenarios for validation
              </SmallText>

              <div className="grid grid-cols-2 gap-2">
                <Button
                  fullWidth
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setTestInputs({
                      inventory: 50,
                      backlog: 0,
                      pipeline: 0,
                      demand_history: [50, 50, 50, 50, 50],
                      node_type: 'retailer',
                      node_position: 0
                    });
                    setTestResult(null);
                  }}
                >
                  Stable Demand
                </Button>

                <Button
                  fullWidth
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setTestInputs({
                      inventory: 0,
                      backlog: 50,
                      pipeline: 100,
                      demand_history: [30, 40, 50, 60, 70, 80, 90],
                      node_type: 'wholesaler',
                      node_position: 1
                    });
                    setTestResult(null);
                  }}
                >
                  Demand Spike
                </Button>

                <Button
                  fullWidth
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setTestInputs({
                      inventory: 200,
                      backlog: 0,
                      pipeline: 50,
                      demand_history: [80, 70, 60, 50, 40, 30, 20],
                      node_type: 'distributor',
                      node_position: 2
                    });
                    setTestResult(null);
                  }}
                >
                  Demand Drop
                </Button>

                <Button
                  fullWidth
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setTestInputs({
                      inventory: 10,
                      backlog: 100,
                      pipeline: 20,
                      demand_history: [60, 55, 65, 50, 70, 45, 75],
                      node_type: 'factory',
                      node_position: 3
                    });
                    setTestResult(null);
                  }}
                >
                  High Backlog
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default TRMTestPanel;
