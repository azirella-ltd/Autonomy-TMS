import React from 'react';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Badge,
} from '../../components/common';
import { BarChart3, Plus, RefreshCw, AlertTriangle } from 'lucide-react';

const ResourceCapacity = () => {
  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold">Resource Capacity</h1>
          <p className="text-sm text-muted-foreground">Capacity tracking and bottleneck analysis</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" leftIcon={<RefreshCw className="h-4 w-4" />}>Refresh</Button>
          <Button leftIcon={<Plus className="h-4 w-4" />}>Add Capacity</Button>
        </div>
      </div>

      <Alert variant="warning" className="mb-6">
        <AlertTriangle className="h-4 w-4" />
        <strong className="ml-2">Bottleneck Detection:</strong> Identifies resources with high utilization (&gt;95%)
      </Alert>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Total Resources</p>
            <p className="text-3xl font-bold">0</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Avg Utilization</p>
            <p className="text-3xl font-bold">0%</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Bottlenecks</p>
            <p className="text-3xl font-bold text-red-600">0</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Available Capacity</p>
            <p className="text-3xl font-bold">0 hrs</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="pt-4 text-center min-h-[400px] flex flex-col items-center justify-center">
          <BarChart3 className="h-20 w-20 text-muted-foreground/50 mb-4" />
          <h2 className="text-xl font-semibold mb-2">Resource Capacity Dashboard</h2>
          <p className="text-muted-foreground mb-4">Utilization heatmap and bottleneck detection coming soon.</p>
          <p className="text-sm text-muted-foreground mb-4"><strong>API:</strong> /api/v1/resource-capacity/*</p>
          <div className="flex gap-2">
            <Badge>9 Endpoints</Badge>
            <Badge variant="secondary">Utilization Analysis</Badge>
            <Badge variant="secondary">Bottleneck Detection</Badge>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default ResourceCapacity;
