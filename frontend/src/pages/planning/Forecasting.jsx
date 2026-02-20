import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Button,
  Alert,
  Badge,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  Progress,
} from '../../components/common';
import {
  RefreshCw,
  TrendingUp,
  Play,
  CheckCircle,
  Clock,
  BarChart3,
} from 'lucide-react';
import ForecastPipelineManager from '../../components/demand-planning/ForecastPipelineManager';
import { api } from '../../services/api';

const Forecasting = () => {
  const [configs, setConfigs] = useState([]);
  const [selectedConfig, setSelectedConfig] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const loadConfigs = useCallback(async () => {
    try {
      const res = await api.get('/supply-chain-configs');
      const items = res.data.items || res.data || [];
      setConfigs(items);
      if (items.length > 0 && !selectedConfig) {
        setSelectedConfig(items[0].id.toString());
      }
    } catch (err) {
      console.error('Failed to load configs:', err);
      setError('Failed to load supply chain configurations.');
    }
  }, [selectedConfig]);

  useEffect(() => { loadConfigs(); }, [loadConfigs]);

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold">Forecasting</h1>
          <p className="text-sm text-muted-foreground mt-1">
            ML-based statistical forecast generation, clustering, and publishing
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Select value={selectedConfig} onValueChange={setSelectedConfig}>
            <SelectTrigger className="w-[220px]">
              <SelectValue placeholder="Select Configuration" />
            </SelectTrigger>
            <SelectContent>
              {configs.map((c) => (
                <SelectItem key={c.id} value={c.id.toString()}>
                  {c.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {error && (
        <Alert variant="error" onClose={() => setError(null)} className="mb-4">
          {error}
        </Alert>
      )}

      {/* Overview cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Pipeline</p>
                <p className="text-lg font-bold">ML Forecast</p>
              </div>
              <TrendingUp className="h-8 w-8 text-primary" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Method</p>
                <p className="text-lg font-bold">Clustered Naive</p>
              </div>
              <BarChart3 className="h-8 w-8 text-blue-500" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Cadence</p>
                <p className="text-lg font-bold">Weekly</p>
              </div>
              <Clock className="h-8 w-8 text-amber-500" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Metric</p>
                <p className="text-lg font-bold">WAPE</p>
              </div>
              <CheckCircle className="h-8 w-8 text-green-500" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Pipeline Manager */}
      {selectedConfig ? (
        <ForecastPipelineManager configId={Number(selectedConfig)} />
      ) : (
        <Card>
          <CardContent className="pt-4 text-center py-8">
            <p className="text-muted-foreground">Select a supply chain configuration to manage forecast pipelines</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default Forecasting;
