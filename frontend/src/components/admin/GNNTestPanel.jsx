import React, { useState, useEffect } from 'react';
import {
  Play as TestIcon,
  CheckCircle as SuccessIcon,
  AlertCircle as ErrorIcon,
  AlertTriangle as WarningIcon,
} from 'lucide-react';
import {
  Card,
  CardContent,
  Alert,
  AlertDescription,
  Badge,
  Chip,
  Input,
  FormField,
  Textarea,
  Button,
  Table,
  TableBody,
  TableCell,
  TableRow,
  TableContainer,
  H5,
  H6,
  Text,
  SmallText,
  Caption,
} from '../common';
import { cn } from '@azirella-ltd/autonomy-frontend';
import { testGNNModel, getGNNModelInfo } from '../../services/gnnApi';

const GNNTestPanel = ({ selectedConfig }) => {
  const [testInput, setTestInput] = useState({
    inventory: 50,
    backlog: 0,
    pipeline: 20,
    incoming_order: 10,
    demand_history: [8, 9, 10, 11, 10, 9, 8, 10],
    node_type: 'retailer',
  });

  const [testResult, setTestResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [modelInfo, setModelInfo] = useState(null);

  // Check if a model is loaded and get its config
  useEffect(() => {
    const fetchModelInfo = async () => {
      try {
        const info = await getGNNModelInfo();
        setModelInfo(info);
      } catch (err) {
        // Model not loaded is fine
        setModelInfo(null);
      }
    };
    fetchModelInfo();
  }, []);

  // Check if loaded model matches selected config
  const configMatches = () => {
    if (!modelInfo || !selectedConfig || !modelInfo.config_name) return true;
    const normalizeConfig = (s) => s.toLowerCase().replace(/[\s_-]+/g, '_');
    return normalizeConfig(modelInfo.config_name) === normalizeConfig(selectedConfig);
  };

  const handleInputChange = (field, value) => {
    setTestInput(prev => ({
      ...prev,
      [field]: value
    }));
  };

  const handleDemandHistoryChange = (value) => {
    try {
      const history = value.split(',').map(v => parseFloat(v.trim())).filter(v => !isNaN(v));
      setTestInput(prev => ({
        ...prev,
        demand_history: history
      }));
    } catch (err) {
      console.error('Invalid demand history format');
    }
  };

  const handleRunTest = async () => {
    setError(null);
    setLoading(true);

    try {
      const result = await testGNNModel(testInput);
      setTestResult(result);
    } catch (err) {
      setError(err.response?.data?.detail || 'Test failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <H5 className="mb-2">Network Agent Testing</H5>
      <Text className="text-muted-foreground mb-4">
        Test the loaded network model with custom supply chain state inputs.
      </Text>

      {/* Config and Model Status */}
      <div className="flex flex-wrap gap-2 mb-4">
        {selectedConfig && (
          <Badge variant="outline">
            Testing Config: {selectedConfig}
          </Badge>
        )}
        {modelInfo ? (
          <Badge variant="success" className="gap-1">
            <SuccessIcon className="h-3 w-3" />
            Model Loaded: {modelInfo.config_name || 'Unknown Config'}
          </Badge>
        ) : (
          <Badge variant="secondary" className="gap-1">
            <ErrorIcon className="h-3 w-3" />
            No Model Loaded
          </Badge>
        )}
      </div>

      {/* Config Mismatch Warning */}
      {modelInfo && selectedConfig && !configMatches() && (
        <Alert variant="warning" className="mb-4">
          <WarningIcon className="h-4 w-4 mr-2 inline" />
          <strong>Config Mismatch:</strong> The loaded model was trained on "{modelInfo.config_name}"
          but you have "{selectedConfig}" selected. Test results may be inaccurate.
          Load a model trained for "{selectedConfig}" from the Model Manager tab.
        </Alert>
      )}

      {error && (
        <Alert variant="destructive" className="mb-4" onClose={() => setError(null)}>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Test Input */}
        <Card>
          <CardContent className="pt-6">
            <H6 className="mb-4">Test Input</H6>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <FormField label="Inventory">
                <Input
                  type="number"
                  value={testInput.inventory}
                  onChange={(e) => handleInputChange('inventory', parseFloat(e.target.value))}
                  min={0}
                  step={1}
                />
              </FormField>

              <FormField label="Backlog">
                <Input
                  type="number"
                  value={testInput.backlog}
                  onChange={(e) => handleInputChange('backlog', parseFloat(e.target.value))}
                  min={0}
                  step={1}
                />
              </FormField>

              <FormField label="Pipeline">
                <Input
                  type="number"
                  value={testInput.pipeline}
                  onChange={(e) => handleInputChange('pipeline', parseFloat(e.target.value))}
                  min={0}
                  step={1}
                />
              </FormField>

              <FormField label="Incoming Order">
                <Input
                  type="number"
                  value={testInput.incoming_order}
                  onChange={(e) => handleInputChange('incoming_order', parseFloat(e.target.value))}
                  min={0}
                  step={1}
                />
              </FormField>

              <div className="sm:col-span-2">
                <FormField
                  label="Node Type"
                  helperText="e.g., retailer, wholesaler, distributor, factory"
                >
                  <Input
                    value={testInput.node_type}
                    onChange={(e) => handleInputChange('node_type', e.target.value)}
                  />
                </FormField>
              </div>

              <div className="sm:col-span-2">
                <FormField
                  label="Demand History (comma-separated)"
                  helperText="Recent demand values, e.g., 8, 9, 10, 11, 10"
                >
                  <Textarea
                    value={testInput.demand_history.join(', ')}
                    onChange={(e) => handleDemandHistoryChange(e.target.value)}
                    rows={2}
                  />
                </FormField>
              </div>
            </div>

            <div className="mt-6">
              <Button
                onClick={handleRunTest}
                disabled={loading}
                className="w-full"
              >
                <TestIcon className="h-4 w-4 mr-2" />
                {loading ? 'Testing...' : 'Run Test'}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Test Result */}
        <Card>
          <CardContent className="pt-6">
            <H6 className="mb-4">Test Result</H6>

            {testResult ? (
              <div>
                <div className="flex items-center mb-4">
                  <Chip
                    icon={<SuccessIcon className="h-3 w-3" />}
                    variant="success"
                    size="sm"
                  >
                    Test Completed
                  </Chip>
                </div>

                <TableContainer className="border rounded-md">
                  <Table>
                    <TableBody>
                      <TableRow>
                        <TableCell className="font-semibold">Predicted Order Quantity</TableCell>
                        <TableCell className="text-right">
                          <H6 className="text-primary">
                            {testResult.order_quantity?.toFixed(2) || 'N/A'}
                          </H6>
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell className="font-semibold">Model Used</TableCell>
                        <TableCell className="text-right">
                          {testResult.model_used ? (
                            <Chip variant="default" size="sm">Network Agent</Chip>
                          ) : (
                            <Chip variant="warning" size="sm">Fallback Heuristic</Chip>
                          )}
                        </TableCell>
                      </TableRow>
                      {testResult.confidence !== undefined && (
                        <TableRow>
                          <TableCell className="font-semibold">Confidence</TableCell>
                          <TableCell className="text-right">{(testResult.confidence * 100).toFixed(1)}%</TableCell>
                        </TableRow>
                      )}
                      {testResult.explanation && (
                        <TableRow>
                          <TableCell colSpan={2}>
                            <SmallText className="text-muted-foreground">
                              <span className="font-semibold">Explanation:</span> {testResult.explanation}
                            </SmallText>
                          </TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                </TableContainer>

                {testResult.graph_features && (
                  <div className="mt-4">
                    <SmallText className="text-muted-foreground mb-2 block">
                      <span className="font-semibold">Graph Features Used:</span>
                    </SmallText>
                    <div className="border rounded-md p-2">
                      <pre className="text-xs whitespace-pre-wrap">
                        {JSON.stringify(testResult.graph_features, null, 2)}
                      </pre>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <Alert variant="info">
                <AlertDescription>
                  Run a test to see results here. Make sure a network model is loaded first.
                </AlertDescription>
              </Alert>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default GNNTestPanel;
