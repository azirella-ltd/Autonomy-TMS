/**
 * Supply Chain Insights Dashboard
 *
 * AI-powered insights and recommendations for supply chain optimization.
 */

import React, { useState } from 'react';
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Badge,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '../components/common';
import {
  Lightbulb,
  TrendingUp,
  AlertTriangle,
  CheckCircle,
  BarChart3,
  Brain,
} from 'lucide-react';

const Insights = () => {
  const [currentTab, setCurrentTab] = useState('overview');

  const mockInsights = [
    {
      severity: 'warning',
      title: 'High Inventory at Wholesaler',
      description: 'Inventory levels exceed safety stock by 45%. Consider reducing order quantities.',
      impact: 'High holding costs',
    },
    {
      severity: 'info',
      title: 'Demand Pattern Detected',
      description: 'Seasonal demand spike predicted in 4 weeks based on historical patterns.',
      impact: 'Opportunity for proactive planning',
    },
    {
      severity: 'success',
      title: 'Improved Service Level',
      description: 'Retailer service level improved to 98.5%, exceeding target of 95%.',
      impact: 'Customer satisfaction improvement',
    },
  ];

  const recommendations = [
    'Reduce wholesaler orders by 20% to optimize inventory levels',
    'Increase safety stock at retailer by 15% ahead of seasonal demand',
    'Implement dynamic order policies based on ML forecasts',
    'Review lead time variability with factory to reduce uncertainty',
  ];

  const getAlertVariant = (severity) => {
    switch (severity) {
      case 'warning': return 'warning';
      case 'success': return 'success';
      default: return 'info';
    }
  };

  return (
    <div className="container mx-auto py-8 px-4 max-w-7xl">
      <div className="mb-8 flex items-center gap-3">
        <Lightbulb className="h-10 w-10 text-primary" />
        <h1 className="text-3xl font-bold">Supply Chain Insights</h1>
      </div>

      <Tabs value={currentTab} onValueChange={setCurrentTab} className="w-full">
        <TabsList className="mb-6">
          <TabsTrigger value="overview" className="flex items-center gap-2">
            <Lightbulb className="h-4 w-4" />
            Overview
          </TabsTrigger>
          <TabsTrigger value="performance" className="flex items-center gap-2">
            <BarChart3 className="h-4 w-4" />
            Performance
          </TabsTrigger>
          <TabsTrigger value="risk" className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            Risk Analysis
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle>AI-Powered Insights</CardTitle>
                  <p className="text-sm text-muted-foreground">
                    Intelligent recommendations based on supply chain performance analysis
                  </p>
                </CardHeader>
                <CardContent className="space-y-4">
                  {mockInsights.map((insight, index) => (
                    <Alert key={index} variant={getAlertVariant(insight.severity)}>
                      <Lightbulb className="h-4 w-4" />
                      <AlertTitle>{insight.title}</AlertTitle>
                      <AlertDescription>
                        <p>{insight.description}</p>
                        <p className="text-xs text-muted-foreground mt-1">Impact: {insight.impact}</p>
                      </AlertDescription>
                    </Alert>
                  ))}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Recommended Actions</CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="space-y-3">
                    {recommendations.map((rec, index) => (
                      <li key={index} className="flex items-start gap-3">
                        <CheckCircle className="h-5 w-5 text-primary mt-0.5" />
                        <span>{rec}</span>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            </div>

            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle>Key Metrics</CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div>
                    <p className="text-xs text-muted-foreground">Overall SC Health</p>
                    <div className="flex items-center gap-2">
                      <span className="text-4xl font-bold">82</span>
                      <Badge variant="success">+5%</Badge>
                    </div>
                  </div>

                  <div>
                    <p className="text-xs text-muted-foreground">Risk Score</p>
                    <div className="flex items-center gap-2">
                      <span className="text-4xl font-bold">23</span>
                      <Badge variant="success">-8%</Badge>
                    </div>
                  </div>

                  <div>
                    <p className="text-xs text-muted-foreground">Optimization Opportunities</p>
                    <span className="text-4xl font-bold">12</span>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Insights Powered By</CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="space-y-4">
                    <li className="flex items-start gap-3">
                      <TrendingUp className="h-5 w-5 text-primary mt-0.5" />
                      <div>
                        <p className="font-medium">AI Agent (7M params)</p>
                        <p className="text-sm text-muted-foreground">Fast forecasting</p>
                      </div>
                    </li>
                    <li className="flex items-start gap-3">
                      <BarChart3 className="h-5 w-5 text-primary mt-0.5" />
                      <div>
                        <p className="font-medium">Network Agent (128M+ params)</p>
                        <p className="text-sm text-muted-foreground">Graph analysis</p>
                      </div>
                    </li>
                    <li className="flex items-start gap-3">
                      <Brain className="h-5 w-5 text-primary mt-0.5" />
                      <div>
                        <p className="font-medium">Claude AI</p>
                        <p className="text-sm text-muted-foreground">Natural language insights</p>
                      </div>
                    </li>
                  </ul>
                </CardContent>
              </Card>
            </div>
          </div>
        </TabsContent>

        <TabsContent value="performance">
          <Card>
            <CardContent className="py-12 text-center">
              <h2 className="text-xl font-semibold text-primary mb-2">Performance Metrics Coming Soon</h2>
              <p className="text-muted-foreground">
                Detailed performance analytics with historical trends, benchmarking, and KPI tracking.
              </p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="risk">
          <Card>
            <CardContent className="py-12 text-center">
              <h2 className="text-xl font-semibold text-primary mb-2">Risk Analysis Coming Soon</h2>
              <p className="text-muted-foreground">
                Comprehensive risk assessment including supply disruption, demand volatility, and capacity constraints.
              </p>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default Insights;
