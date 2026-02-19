import React from 'react';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Badge,
} from '../../components/common';
import {
  Factory,
  Plus,
  RefreshCw,
} from 'lucide-react';

const ProductionProcesses = () => {
  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold">Production Processes</h1>
          <p className="text-sm text-muted-foreground">
            Manufacturing process definitions for MPS/MRP planning
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" leftIcon={<RefreshCw className="h-4 w-4" />}>
            Refresh
          </Button>
          <Button leftIcon={<Plus className="h-4 w-4" />}>
            Add Process
          </Button>
        </div>
      </div>

      <Alert variant="info" className="mb-6">
        <strong>Key Parameters:</strong> Operation time, setup time, lot size, yield %, lead time, capacity
      </Alert>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Total Processes</p>
            <p className="text-3xl font-bold">0</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Avg Operation Time</p>
            <p className="text-3xl font-bold">2.5 hrs</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Avg Yield</p>
            <p className="text-3xl font-bold">98.5%</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Total Capacity</p>
            <p className="text-3xl font-bold">840 hrs</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="py-12 text-center">
          <Factory className="h-20 w-20 text-muted-foreground mx-auto mb-4" />
          <h2 className="text-xl font-medium mb-2">Production Processes Management</h2>
          <p className="text-muted-foreground mb-4">Full CRUD interface coming soon.</p>
          <p className="text-sm text-muted-foreground mb-4">
            <strong>API:</strong> /api/v1/production-process/*
          </p>
          <div className="flex justify-center gap-2">
            <Badge variant="secondary">8 Endpoints</Badge>
            <Badge variant="secondary">MPS/MRP Integration</Badge>
            <Badge variant="secondary">Capacity Planning</Badge>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default ProductionProcesses;
