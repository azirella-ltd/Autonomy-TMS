/**
 * Scenario Comparison Tool
 *
 * Allows users to:
 * - Add multiple simulation scenarios
 * - Compare results side-by-side
 * - Rank scenarios by different criteria
 * - Export comparison reports
 *
 * Phase 5 Sprint 5: Analytics & Visualization
 */

import React, { useState, useCallback } from 'react';
import {
  Plus,
  Trash2,
  Play,
  Download,
  GitCompare,
  Pencil
} from 'lucide-react';
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, Legend, ResponsiveContainer, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar } from 'recharts';
import { api } from '../../services/api';
import { Card, CardContent } from '../common/Card';
import { Button, IconButton } from '../common/Button';
import { Input, Label, Textarea, FormField } from '../common/Input';
import { Badge } from '../common/Badge';
import { Alert } from '../common/Alert';
import { Spinner } from '../common/Loading';
import { Modal, ModalHeader, ModalTitle, ModalBody, ModalFooter } from '../common/Modal';
import { Select, SelectOption } from '../common/Select';

/**
 * Scenario Definition Dialog
 * Modal for adding/editing a scenario
 */
const ScenarioDialog = ({ open, onClose, onSave, scenario }) => {
  const [name, setName] = useState(scenario?.name || '');
  const [description, setDescription] = useState(scenario?.description || '');
  const [gameConfig, setGameConfig] = useState(scenario?.gameConfig || {});

  const handleSave = () => {
    onSave({
      name,
      description,
      gameConfig,
      id: scenario?.id || Date.now()
    });
    onClose();
  };

  return (
    <Modal isOpen={open} onClose={onClose} size="lg">
      <ModalHeader>
        <ModalTitle>
          {scenario ? 'Edit Scenario' : 'Add Scenario'}
        </ModalTitle>
      </ModalHeader>
      <ModalBody>
        <div className="pt-2 space-y-4">
          <FormField label="Scenario Name" required>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Enter scenario name"
            />
          </FormField>
          <FormField label="Description">
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder="Enter scenario description"
            />
          </FormField>
          <Alert variant="info">
            Configure the scenario parameters (stochastic distributions, policies, etc.) using the scenario configuration interface.
          </Alert>
        </div>
      </ModalBody>
      <ModalFooter>
        <Button variant="outline" onClick={onClose}>Cancel</Button>
        <Button onClick={handleSave} disabled={!name}>
          Save
        </Button>
      </ModalFooter>
    </Modal>
  );
};

/**
 * Scenario Results Card
 * Displays summary statistics for a scenario
 */
const ScenarioResultCard = ({ scenario, results, onDelete, onEdit }) => {
  const getStatusVariant = () => {
    if (!results) return 'secondary';
    if (results.status === 'running') return 'default';
    if (results.status === 'completed') return 'success';
    if (results.status === 'error') return 'destructive';
    return 'secondary';
  };

  return (
    <Card>
      <CardContent>
        <div className="flex justify-between items-start mb-4">
          <div>
            <h3 className="text-lg font-semibold">{scenario.name}</h3>
            <p className="text-sm text-muted-foreground">
              {scenario.description}
            </p>
          </div>
          <div className="flex items-center gap-1">
            <Badge variant={getStatusVariant()} size="sm">
              {results?.status || 'pending'}
            </Badge>
            <IconButton onClick={() => onEdit(scenario)}>
              <Pencil className="h-4 w-4" />
            </IconButton>
            <IconButton onClick={() => onDelete(scenario.id)}>
              <Trash2 className="h-4 w-4" />
            </IconButton>
          </div>
        </div>

        {results?.status === 'running' && (
          <div className="flex items-center gap-2">
            <Spinner size="sm" />
            <p className="text-sm">Running simulation...</p>
          </div>
        )}

        {results?.status === 'completed' && results.metrics && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div>
              <p className="text-sm text-muted-foreground">Mean Cost</p>
              <p className="text-lg font-semibold">{results.metrics.mean.toFixed(2)}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Std Dev</p>
              <p className="text-lg font-semibold">{results.metrics.std.toFixed(2)}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">CV</p>
              <p className="text-lg font-semibold">{results.metrics.cv.toFixed(1)}%</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">VaR 95%</p>
              <p className="text-lg font-semibold">{results.metrics.var_95?.toFixed(2) || 'N/A'}</p>
            </div>
          </div>
        )}

        {results?.status === 'error' && (
          <Alert variant="error">{results.error}</Alert>
        )}
      </CardContent>
    </Card>
  );
};

/**
 * Comparison Charts Component
 * Side-by-side comparison visualizations
 */
const ComparisonCharts = ({ scenarios, results }) => {
  // Prepare data for charts
  const chartData = scenarios
    .map(scenario => {
      const result = results[scenario.id];
      if (!result?.metrics) return null;
      return {
        name: scenario.name,
        mean: result.metrics.mean,
        std: result.metrics.std,
        cv: result.metrics.cv,
        var_95: result.metrics.var_95 || 0,
        cvar_95: result.metrics.cvar_95 || 0,
        service_level: result.metrics.service_level || 0
      };
    })
    .filter(Boolean);

  if (chartData.length === 0) {
    return (
      <Alert variant="info">
        Run simulations to see comparison charts
      </Alert>
    );
  }

  // Radar chart data (normalized 0-100 scale)
  const radarData = scenarios
    .map(scenario => {
      const result = results[scenario.id];
      if (!result?.metrics) return null;

      // Normalize metrics to 0-100 scale (lower is better for most metrics)
      const maxMean = Math.max(...chartData.map(d => d.mean));
      const maxCV = Math.max(...chartData.map(d => d.cv));

      return {
        subject: scenario.name,
        Cost: 100 - (result.metrics.mean / maxMean * 100),
        Stability: 100 - (result.metrics.cv / maxCV * 100),
        Service: result.metrics.service_level || 90,
        fullMark: 100
      };
    })
    .filter(Boolean);

  return (
    <div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Mean Cost Comparison */}
        <Card className="p-4">
          <h4 className="text-base font-medium mb-4">
            Mean Cost Comparison
          </h4>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis />
              <RechartsTooltip />
              <Legend />
              <Bar dataKey="mean" fill="#8884d8" name="Mean Cost" />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        {/* Variability Comparison */}
        <Card className="p-4">
          <h4 className="text-base font-medium mb-4">
            Variability Comparison (CV)
          </h4>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis />
              <RechartsTooltip />
              <Legend />
              <Bar dataKey="cv" fill="#82ca9d" name="CV (%)" />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        {/* Risk Metrics Comparison */}
        <Card className="p-4">
          <h4 className="text-base font-medium mb-4">
            Risk Metrics Comparison
          </h4>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis />
              <RechartsTooltip />
              <Legend />
              <Bar dataKey="var_95" fill="#ff9800" name="VaR 95%" />
              <Bar dataKey="cvar_95" fill="#f44336" name="CVaR 95%" />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        {/* Overall Performance Radar */}
        <Card className="p-4">
          <h4 className="text-base font-medium mb-4">
            Overall Performance Profile
          </h4>
          <ResponsiveContainer width="100%" height={300}>
            <RadarChart data={radarData}>
              <PolarGrid />
              <PolarAngleAxis dataKey="subject" />
              <PolarRadiusAxis angle={90} domain={[0, 100]} />
              <Radar name="Performance" dataKey="Cost" stroke="#8884d8" fill="#8884d8" fillOpacity={0.6} />
              <Legend />
            </RadarChart>
          </ResponsiveContainer>
        </Card>
      </div>
    </div>
  );
};

/**
 * Main Scenario Comparison Component
 */
const ScenarioComparison = () => {
  const [scenarios, setScenarios] = useState([]);
  const [results, setResults] = useState({});
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingScenario, setEditingScenario] = useState(null);
  const [running, setRunning] = useState(false);
  const [comparisonMetric, setComparisonMetric] = useState('total_cost');

  // Add or edit scenario
  const handleSaveScenario = (scenario) => {
    if (editingScenario) {
      setScenarios(scenarios.map(s => s.id === scenario.id ? scenario : s));
    } else {
      setScenarios([...scenarios, scenario]);
    }
    setEditingScenario(null);
  };

  // Delete scenario
  const handleDeleteScenario = (id) => {
    setScenarios(scenarios.filter(s => s.id !== id));
    const newResults = { ...results };
    delete newResults[id];
    setResults(newResults);
  };

  // Edit scenario
  const handleEditScenario = (scenario) => {
    setEditingScenario(scenario);
    setDialogOpen(true);
  };

  // Run all simulations
  const handleRunAll = async () => {
    setRunning(true);

    for (const scenario of scenarios) {
      // Mark as running
      setResults(prev => ({
        ...prev,
        [scenario.id]: { status: 'running' }
      }));

      try {
        // Call analytics API
        const response = await api.post('/stochastic/analytics/compare-scenarios', {
          scenarios: {
            [scenario.name]: scenario.samples || []
          },
          metric: comparisonMetric
        });

        // Store results
        setResults(prev => ({
          ...prev,
          [scenario.id]: {
            status: 'completed',
            metrics: response.data[scenario.name]
          }
        }));
      } catch (error) {
        console.error(`Error running scenario ${scenario.name}:`, error);
        setResults(prev => ({
          ...prev,
          [scenario.id]: {
            status: 'error',
            error: error.message
          }
        }));
      }
    }

    setRunning(false);
  };

  // Export comparison report
  const handleExport = () => {
    const report = {
      scenarios: scenarios.map(s => ({
        ...s,
        results: results[s.id]
      })),
      generatedAt: new Date().toISOString()
    };

    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `scenario-comparison-${Date.now()}.json`;
    a.click();
  };

  return (
    <div>
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-xl font-semibold">Scenario Comparison</h2>
        <div className="flex gap-2">
          <Button
            variant="outline"
            leftIcon={<Plus className="h-4 w-4" />}
            onClick={() => {
              setEditingScenario(null);
              setDialogOpen(true);
            }}
          >
            Add Scenario
          </Button>
          <Button
            leftIcon={<Play className="h-4 w-4" />}
            onClick={handleRunAll}
            disabled={scenarios.length === 0 || running}
          >
            Run All
          </Button>
          <Button
            variant="outline"
            leftIcon={<Download className="h-4 w-4" />}
            onClick={handleExport}
            disabled={scenarios.length === 0}
          >
            Export
          </Button>
        </div>
      </div>

      {/* Metric Selection */}
      <div className="mb-6">
        <FormField label="Comparison Metric">
          <Select
            value={comparisonMetric}
            onChange={(e) => setComparisonMetric(e.target.value)}
            className="w-[200px]"
          >
            <SelectOption value="total_cost">Total Cost</SelectOption>
            <SelectOption value="holding_cost">Holding Cost</SelectOption>
            <SelectOption value="backlog_cost">Backlog Cost</SelectOption>
            <SelectOption value="service_level">Service Level</SelectOption>
            <SelectOption value="bullwhip_ratio">Bullwhip Ratio</SelectOption>
          </Select>
        </FormField>
      </div>

      {/* Scenarios List */}
      {scenarios.length === 0 ? (
        <Alert variant="info">
          No scenarios defined. Click "Add Scenario" to get started.
        </Alert>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          {scenarios.map(scenario => (
            <ScenarioResultCard
              key={scenario.id}
              scenario={scenario}
              results={results[scenario.id]}
              onDelete={handleDeleteScenario}
              onEdit={handleEditScenario}
            />
          ))}
        </div>
      )}

      {/* Comparison Charts */}
      {scenarios.length > 1 && (
        <div className="mt-8">
          <h3 className="text-lg font-semibold mb-4">
            Comparison Analysis
          </h3>
          <ComparisonCharts scenarios={scenarios} results={results} />
        </div>
      )}

      {/* Scenario Dialog */}
      <ScenarioDialog
        open={dialogOpen}
        onClose={() => {
          setDialogOpen(false);
          setEditingScenario(null);
        }}
        onSave={handleSaveScenario}
        scenario={editingScenario}
      />
    </div>
  );
};

export default ScenarioComparison;
