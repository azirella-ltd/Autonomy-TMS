/**
 * N-Tier Visibility Dashboard
 *
 * AWS SC-inspired multi-tier supply chain visibility interface.
 */

import React, { useState } from 'react';
import {
  Alert,
  AlertDescription,
  Badge,
  Card,
  CardContent,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '../components/common';
import { Eye, Factory, Truck, Store, Package } from 'lucide-react';

const NTierVisibility = () => {
  const [currentTab, setCurrentTab] = useState('overview');

  const tiers = [
    {
      name: 'Tier 1 - Factory',
      icon: <Factory className="h-5 w-5" />,
      status: 'operational',
      inventory: 450,
      capacity: '85%',
      leadTime: '4 weeks',
    },
    {
      name: 'Tier 2 - Distributor',
      icon: <Truck className="h-5 w-5" />,
      status: 'operational',
      inventory: 320,
      capacity: '72%',
      leadTime: '2 weeks',
    },
    {
      name: 'Tier 3 - Wholesaler',
      icon: <Package className="h-5 w-5" />,
      status: 'warning',
      inventory: 180,
      capacity: '91%',
      leadTime: '1 week',
    },
    {
      name: 'Tier 4 - Retailer',
      icon: <Store className="h-5 w-5" />,
      status: 'operational',
      inventory: 85,
      capacity: '68%',
      leadTime: '2 days',
    },
  ];

  const getStatusVariant = (status) => {
    const variants = {
      operational: 'success',
      warning: 'warning',
      critical: 'destructive',
    };
    return variants[status] || 'secondary';
  };

  return (
    <div className="container mx-auto py-8 px-4 max-w-7xl">
      <div className="mb-8 flex items-center gap-3">
        <Eye className="h-10 w-10 text-primary" />
        <h1 className="text-3xl font-bold">N-Tier Visibility</h1>
      </div>

      <Card className="mb-6">
        <CardContent className="pt-6">
          <p className="text-muted-foreground">
            Gain end-to-end visibility across all tiers of your supply chain network.
            Monitor inventory levels, capacity utilization, and operational status at each tier.
          </p>
        </CardContent>
      </Card>

      <Alert className="mb-6">
        <AlertDescription>
          <strong>Real-time visibility</strong> powered by supply chain simulation data.
          Track inventory flow and identify bottlenecks across the supply chain network.
        </AlertDescription>
      </Alert>

      <Tabs value={currentTab} onValueChange={setCurrentTab}>
        <TabsList className="mb-6">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="inventory-flow">Inventory Flow</TabsTrigger>
          <TabsTrigger value="capacity">Capacity Analysis</TabsTrigger>
          <TabsTrigger value="risk">Risk Assessment</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {tiers.map((tier, index) => (
              <Card key={index}>
                <CardContent className="pt-6">
                  <div className="flex items-center gap-3 mb-4">
                    {tier.icon}
                    <h3 className="text-lg font-semibold">{tier.name}</h3>
                    <Badge variant={getStatusVariant(tier.status)} className="ml-auto">
                      {tier.status.toUpperCase()}
                    </Badge>
                  </div>

                  <div className="space-y-3">
                    <div className="flex justify-between py-2 border-b">
                      <span className="text-muted-foreground">Current Inventory</span>
                      <span>{tier.inventory} units</span>
                    </div>
                    <div className="flex justify-between py-2 border-b">
                      <span className="text-muted-foreground">Capacity Utilization</span>
                      <span>{tier.capacity}</span>
                    </div>
                    <div className="flex justify-between py-2">
                      <span className="text-muted-foreground">Average Lead Time</span>
                      <span>{tier.leadTime}</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="mt-8">
            <h2 className="text-xl font-bold mb-4">Supply Chain Health</h2>
            <Card>
              <CardContent className="pt-6">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <div>
                    <p className="text-sm text-muted-foreground mb-1">Overall Health Score</p>
                    <p className="text-4xl font-bold text-green-600">87</p>
                    <p className="text-xs text-muted-foreground">Out of 100</p>
                  </div>

                  <div>
                    <p className="text-sm text-muted-foreground mb-1">Total Network Inventory</p>
                    <p className="text-4xl font-bold">1,035</p>
                    <p className="text-xs text-muted-foreground">Units across all tiers</p>
                  </div>

                  <div>
                    <p className="text-sm text-muted-foreground mb-1">Average Service Level</p>
                    <p className="text-4xl font-bold text-primary">94.2%</p>
                    <p className="text-xs text-muted-foreground">Last 30 days</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="inventory-flow">
          <Card>
            <CardContent className="py-16 text-center">
              <h2 className="text-xl font-semibold text-primary mb-2">
                Inventory Flow Visualization Coming Soon
              </h2>
              <p className="text-muted-foreground">
                Animated flow diagrams showing inventory movement between tiers in real-time.
              </p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="capacity">
          <Card>
            <CardContent className="py-16 text-center">
              <h2 className="text-xl font-semibold text-primary mb-2">
                Capacity Analysis Coming Soon
              </h2>
              <p className="text-muted-foreground">
                Detailed capacity utilization charts and bottleneck identification.
              </p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="risk">
          <Card>
            <CardContent className="py-16 text-center">
              <h2 className="text-xl font-semibold text-primary mb-2">
                Risk Assessment Coming Soon
              </h2>
              <p className="text-muted-foreground">
                AI-powered risk scoring and mitigation recommendations for each tier.
              </p>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default NTierVisibility;
