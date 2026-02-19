import React from 'react';
import { Alert, AlertDescription, Badge, Button, Card, CardContent } from '../../components/common';
import { Wrench, Plus, RefreshCw } from 'lucide-react';

const ServiceOrders = () => {
  return (
    <div className="container mx-auto py-8 px-4 max-w-7xl">
      <div className="flex justify-between items-start mb-6 flex-wrap gap-4">
        <div>
          <h1 className="text-3xl font-bold">Service Orders</h1>
          <p className="text-muted-foreground">Corrective maintenance and repair orders</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline">
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
          <Button>
            <Plus className="h-4 w-4 mr-2" />
            Create Service Order
          </Button>
        </div>
      </div>

      <Alert className="mb-6">
        <AlertDescription>
          <strong>Service Orders</strong> track corrective maintenance (breakdowns, repairs, warranty work). Different from preventive maintenance orders.
        </AlertDescription>
      </Alert>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">Open Orders</p>
            <p className="text-4xl font-bold">0</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">In Progress</p>
            <p className="text-4xl font-bold">0</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">Overdue</p>
            <p className="text-4xl font-bold text-destructive">0</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">Critical</p>
            <p className="text-4xl font-bold text-amber-500">0</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="py-16 text-center">
          <Wrench className="h-20 w-20 mx-auto text-muted-foreground mb-4" />
          <h2 className="text-2xl font-semibold mb-2">Service Order Management</h2>
          <p className="text-muted-foreground mb-2">Full interface coming soon.</p>
          <p className="text-sm text-muted-foreground mb-6"><strong>API:</strong> /api/v1/service-order/*</p>
          <div className="flex justify-center gap-2 flex-wrap">
            <Badge variant="secondary">11 Endpoints</Badge>
            <Badge variant="secondary">Priority Scheduling</Badge>
            <Badge variant="secondary">Downtime Tracking</Badge>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default ServiceOrders;
