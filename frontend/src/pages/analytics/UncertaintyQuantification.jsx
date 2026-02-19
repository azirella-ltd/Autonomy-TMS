/**
 * Uncertainty Quantification Page
 *
 * Central page for advanced uncertainty modeling:
 * 1. Conformal Prediction - Distribution-free prediction intervals
 * 2. Planning Method Comparison - Stochastic vs Deterministic
 *
 * This page helps planners understand and manage uncertainty in supply chain planning.
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
} from '../../components/common';
import { FlaskConical, ArrowLeftRight } from 'lucide-react';
import { ConformalPrediction, PlanningMethodComparison } from '../../components/advanced-analytics';

const UncertaintyQuantification = () => {
  const [activeTab, setActiveTab] = useState('conformal');

  return (
    <div className="container mx-auto px-4 py-8 max-w-7xl">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold">
            Uncertainty Quantification
          </h1>
          <p className="text-sm text-muted-foreground">
            Advanced tools for planning under uncertainty with formal guarantees
          </p>
        </div>
        <div className="flex gap-2">
          <Badge variant="default" className="flex items-center gap-1">
            <FlaskConical className="h-3 w-3" />
            Advanced Analytics
          </Badge>
        </div>
      </div>

      <Alert className="mb-6">
        <AlertDescription>
          <p className="mb-2">
            <strong>Why Uncertainty Matters:</strong> Real supply chains face variability in demand, lead times, yields, and costs.
            Traditional planning uses point estimates and ignores uncertainty. These tools help you:
          </p>
          <ul className="list-disc list-inside space-y-1 text-sm">
            <li><strong>Conformal Prediction:</strong> Get prediction intervals with guaranteed coverage (no distribution assumptions)</li>
            <li><strong>Planning Comparison:</strong> Understand when to use stochastic vs deterministic planning</li>
          </ul>
        </AlertDescription>
      </Alert>

      <Card className="mb-6">
        <CardContent className="p-0">
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="w-full grid grid-cols-2">
              <TabsTrigger value="conformal" className="flex items-center gap-2">
                <FlaskConical className="h-4 w-4" />
                Conformal Prediction
              </TabsTrigger>
              <TabsTrigger value="comparison" className="flex items-center gap-2">
                <ArrowLeftRight className="h-4 w-4" />
                Stochastic vs Deterministic
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </CardContent>
      </Card>

      <div className="mt-6">
        {activeTab === 'conformal' && <ConformalPrediction />}
        {activeTab === 'comparison' && <PlanningMethodComparison />}
      </div>
    </div>
  );
};

export default UncertaintyQuantification;
