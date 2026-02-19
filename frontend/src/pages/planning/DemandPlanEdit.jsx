/**
 * Demand Plan Edit Page
 *
 * Full-featured demand planning page with:
 * - Editable forecast table
 * - Version management
 * - Adjustment history
 * - Bulk tools
 */

import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Badge,
  Label,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
  Spinner,
} from '../../components/common';
import {
  Pencil,
  History,
  ArrowLeftRight,
  Upload,
  Download,
} from 'lucide-react';
import { ForecastEditor, ForecastPipelineManager } from '../../components/demand-planning';
import { getSupplyChainConfigs } from '../../services/supplyChainConfigService';

const DemandPlanEdit = () => {
  const [activeTab, setActiveTab] = useState('edit');
  const [selectedConfig, setSelectedConfig] = useState('');
  const [timeGranularity, setTimeGranularity] = useState('week');

  // Supply chain configs loaded from API (filtered by user's group)
  const [supplyChainConfigs, setSupplyChainConfigs] = useState([]);
  const [configsLoading, setConfigsLoading] = useState(true);
  const [configsError, setConfigsError] = useState(null);

  // Load supply chain configs for user's group on mount
  useEffect(() => {
    const loadConfigs = async () => {
      setConfigsLoading(true);
      setConfigsError(null);
      try {
        const configs = await getSupplyChainConfigs();
        setSupplyChainConfigs(configs);
      } catch (err) {
        console.error('Failed to load supply chain configs:', err);
        setConfigsError('Failed to load supply chain configurations');
      } finally {
        setConfigsLoading(false);
      }
    };
    loadConfigs();
  }, []);

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">
            Demand Plan Editor
          </h1>
          <p className="text-sm text-muted-foreground">
            Adjust statistical forecasts with full audit trail and version control
          </p>
        </div>
        <div className="flex gap-2">
          <Badge variant="default" className="flex items-center gap-1">
            <Pencil className="h-3 w-3" />
            Editable Forecasts
          </Badge>
        </div>
      </div>

      {/* Info Alert */}
      <Alert variant="info" className="mb-6">
        <strong>How to use:</strong> Click any cell to edit the forecast value. Use bulk tools
        to apply percentage or delta adjustments to multiple cells. All changes are tracked with
        full audit history.
      </Alert>

      {/* Filters and Actions */}
      <Card className="mb-6">
        <CardContent className="pt-4">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
            <div>
              <Label>Supply Chain Config</Label>
              {configsLoading ? (
                <div className="flex items-center gap-2 py-2 mt-1">
                  <Spinner size="sm" />
                  <span className="text-sm text-muted-foreground">Loading...</span>
                </div>
              ) : configsError ? (
                <Alert variant="error" className="mt-1">{configsError}</Alert>
              ) : (
                <Select value={selectedConfig} onValueChange={setSelectedConfig}>
                  <SelectTrigger className="mt-1">
                    <SelectValue placeholder="All Configs" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">All Configs</SelectItem>
                    {supplyChainConfigs.map(config => (
                      <SelectItem key={config.id} value={config.id.toString()}>
                        {config.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
            <div>
              <Label>Time Granularity</Label>
              <Select value={timeGranularity} onValueChange={setTimeGranularity}>
                <SelectTrigger className="mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="day">Daily</SelectItem>
                  <SelectItem value="week">Weekly</SelectItem>
                  <SelectItem value="month">Monthly</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>{/* Spacer */}</div>
            <div className="flex gap-2">
              <Button variant="outline" className="flex-1" leftIcon={<Upload className="h-4 w-4" />}>
                Import
              </Button>
              <Button variant="outline" className="flex-1" leftIcon={<Download className="h-4 w-4" />}>
                Export
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList className="w-full grid grid-cols-4">
          <TabsTrigger value="edit" className="flex items-center gap-2">
            <Pencil className="h-4 w-4" />
            Edit Forecasts
          </TabsTrigger>
          <TabsTrigger value="pipeline" className="flex items-center gap-2">
            <Upload className="h-4 w-4" />
            ML Forecast Pipeline
          </TabsTrigger>
          <TabsTrigger value="history" className="flex items-center gap-2">
            <History className="h-4 w-4" />
            Adjustment History
          </TabsTrigger>
          <TabsTrigger value="compare" className="flex items-center gap-2">
            <ArrowLeftRight className="h-4 w-4" />
            Version Comparison
          </TabsTrigger>
        </TabsList>

        {/* Tab Content */}
        <TabsContent value="edit">
          <Card>
            <CardContent className="pt-4">
              <ForecastEditor
                configId={selectedConfig ? parseInt(selectedConfig) : undefined}
                onSave={() => console.log('Forecasts saved')}
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="pipeline">
          <ForecastPipelineManager configId={selectedConfig ? parseInt(selectedConfig) : undefined} />
        </TabsContent>

        <TabsContent value="history">
          <Card>
            <CardContent className="p-6">
              <h3 className="text-lg font-medium mb-2">Adjustment History</h3>
              <p className="text-sm text-muted-foreground mb-4">
                View all forecast adjustments made across the planning horizon.
                Filter by date, user, product, or reason code.
              </p>
              <Alert variant="info">
                History view coming soon. For now, use the cell-level history in the Edit tab.
              </Alert>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="compare">
          <Card>
            <CardContent className="p-6">
              <h3 className="text-lg font-medium mb-2">Version Comparison</h3>
              <p className="text-sm text-muted-foreground mb-4">
                Compare different forecast versions side-by-side.
                Track changes between baseline, consensus, and published versions.
              </p>
              <Alert variant="info">
                Version comparison coming soon. Create snapshots from the Edit tab to enable comparison.
              </Alert>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default DemandPlanEdit;
