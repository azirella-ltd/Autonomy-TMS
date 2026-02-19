import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Badge,
} from '../../components/common';
import {
  Clock,
  Plus,
  RefreshCw,
} from 'lucide-react';

/**
 * Vendor Lead Times Management
 *
 * Manages supplier-specific lead times with hierarchical override logic.
 *
 * Backend API: /api/v1/vendor-lead-time/*
 * - Hierarchical resolution: Product > Product Group > Site > Region > Company
 * - Lead time variability for stochastic planning
 * - Effective date ranges
 */
const VendorLeadTimes = () => {
  const [leadTimes, setLeadTimes] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // TODO: Fetch vendor lead times from API
    // GET /api/v1/vendor-lead-time/
  }, []);

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold">Vendor Lead Times</h1>
          <p className="text-sm text-muted-foreground">
            Manage supplier-specific lead times with hierarchical overrides
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => {/* Refresh */}}
            leftIcon={<RefreshCw className="h-4 w-4" />}
          >
            Refresh
          </Button>
          <Button
            onClick={() => {/* Open create dialog */}}
            leftIcon={<Plus className="h-4 w-4" />}
          >
            Add Lead Time
          </Button>
        </div>
      </div>

      <Alert variant="info" className="mb-6">
        <strong>Hierarchical Resolution:</strong> Most specific lead time wins:
        Product-specific → Product Group → Site → Region → Company
      </Alert>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        {/* Summary Cards */}
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Total Lead Times</p>
            <p className="text-3xl font-bold">{leadTimes.length}</p>
            <Badge variant="default" className="mt-2">Active</Badge>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Avg Lead Time</p>
            <p className="text-3xl font-bold">7.5 days</p>
            <p className="text-xs text-muted-foreground">Across all suppliers</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Product-Specific</p>
            <p className="text-3xl font-bold">12</p>
            <p className="text-xs text-muted-foreground">Most granular overrides</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Stochastic</p>
            <p className="text-3xl font-bold">8</p>
            <p className="text-xs text-muted-foreground">With variability defined</p>
          </CardContent>
        </Card>
      </div>

      {/* Main Content */}
      <Card>
        <CardContent className="py-12 text-center">
          <Clock className="h-20 w-20 text-muted-foreground mx-auto mb-4" />
          <h2 className="text-xl font-medium mb-2">
            Vendor Lead Times Management
          </h2>
          <p className="text-muted-foreground mb-4">
            Full CRUD interface for vendor lead times coming soon.
          </p>
          <p className="text-sm text-muted-foreground mb-4">
            <strong>Backend API Available:</strong> /api/v1/vendor-lead-time/*
          </p>
          <div className="flex justify-center gap-2">
            <Badge variant="secondary">9 Endpoints</Badge>
            <Badge variant="secondary">Hierarchical Resolution</Badge>
            <Badge variant="secondary">Stochastic Support</Badge>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default VendorLeadTimes;
