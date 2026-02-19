import React from 'react';
import { Alert, AlertDescription, Badge, Card, CardContent } from '../../components/common';
import { Settings } from 'lucide-react';

const KPIConfigurationAnalytics = () => {
  return (
    <div className="container mx-auto px-4 py-8 max-w-7xl">
      <h1 className="text-2xl font-bold mb-4 flex items-center gap-2">
        <Settings className="h-8 w-8" />
        KPI Configuration
      </h1>
      <Alert className="mb-6">
        <AlertDescription>
          <strong>Define & Track KPIs:</strong> Configure supply chain performance metrics with targets and thresholds.
        </AlertDescription>
      </Alert>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-6">
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">Total KPIs</p>
            <p className="text-3xl font-bold">0</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">Financial</p>
            <p className="text-3xl font-bold">0</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">Customer</p>
            <p className="text-3xl font-bold">0</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">Operational</p>
            <p className="text-3xl font-bold">0</p>
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardContent className="pt-6 text-center min-h-[400px] flex flex-col items-center justify-center">
          <Settings className="h-20 w-20 text-muted-foreground/50 mb-4" />
          <h2 className="text-xl font-semibold">KPI Configuration</h2>
          <p className="text-muted-foreground mb-4">Full interface coming soon.</p>
          <p className="text-sm text-muted-foreground"><strong>API:</strong> /api/v1/analytics-optimization/kpi-configuration</p>
          <div className="mt-6 flex gap-2">
            <Badge variant="secondary">Service Level</Badge>
            <Badge variant="secondary">Inventory Turns</Badge>
            <Badge variant="secondary">Custom KPIs</Badge>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
export default KPIConfigurationAnalytics;
