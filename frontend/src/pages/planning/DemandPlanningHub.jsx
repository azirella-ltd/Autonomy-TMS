/**
 * Demand Planning Hub — Unified tabbed interface for demand planners.
 *
 * Tabs:
 *   Forecast     — Baseline forecast view (P10/P50/P90)
 *   Editor       — Version-controlled manual adjustments
 *   Sensing      — Signal-driven adjustments (email, market intel, voice)
 *   Shaping      — Promotional/event demand impact modeling
 *   Consensus    — Multi-stakeholder alignment & voting
 *   Life Cycle   — NPI ramp, EOL phaseout, stage tracking
 *   Exceptions   — Anomaly detection & root cause
 */

import React, { useState, useEffect, lazy, Suspense } from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';
import {
  Tabs, TabsList, TabsTrigger, TabsContent,
  Card, Badge,
} from '../../components/common';
import RoleTimeSeries from '../../components/charts/RoleTimeSeries';
import ScenarioPanel from '../../components/planning/ScenarioPanel';
import { useActiveConfig } from '../../contexts/ActiveConfigContext';
import {
  TrendingUp, Pencil, Radio, Megaphone, Users,
  Recycle, AlertTriangle, BarChart3, Workflow,
} from 'lucide-react';

// Lazy-load existing page components as tab content
const DemandPlanView = lazy(() => import('./DemandPlanView'));
const DemandPlanEdit = lazy(() => import('./DemandPlanEdit'));
const ForecastAdjWorklistPage = lazy(() => import('./ForecastAdjWorklistPage'));
const PromotionalPlanning = lazy(() => import('./PromotionalPlanning'));
const ConsensusPlanning = lazy(() => import('./ConsensusPlanning'));
const ProductLifecycle = lazy(() => import('./ProductLifecycle'));
const ForecastExceptions = lazy(() => import('./ForecastExceptions'));
const ForecastAnalytics = lazy(() => import('./ForecastAnalytics'));
const ForecastPipeline = lazy(() => import('./ForecastPipeline'));

const TABS = [
  { key: 'forecast', label: 'Forecast', icon: TrendingUp },
  { key: 'pipeline', label: 'Pipeline', icon: Workflow },
  { key: 'analytics', label: 'Analytics', icon: BarChart3 },
  { key: 'editor', label: 'Editor', icon: Pencil },
  { key: 'sensing', label: 'Sensing', icon: Radio },
  { key: 'shaping', label: 'Shaping', icon: Megaphone },
  { key: 'consensus', label: 'Consensus', icon: Users },
  { key: 'lifecycle', label: 'Life Cycle', icon: Recycle },
  { key: 'exceptions', label: 'Exceptions', icon: AlertTriangle },
];

const TabLoading = () => (
  <div className="flex items-center justify-center h-64 text-muted-foreground">
    Loading...
  </div>
);

export default function DemandPlanningHub() {
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  const { effectiveConfigId } = useActiveConfig();
  const initialTab = searchParams.get('tab') || location.state?.tab || 'forecast';
  const [activeTab, setActiveTab] = useState(initialTab);

  // Sync tab to URL
  useEffect(() => {
    if (searchParams.get('tab') !== activeTab) {
      setSearchParams({ tab: activeTab }, { replace: true });
    }
  }, [activeTab]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-4">
      {/* Role time series header */}
      <RoleTimeSeries roleKey="demand_planner" configId={effectiveConfigId} compact />

      {/* Scenario panel — available across all planning tabs */}
      <ScenarioPanel />

      {/* Tab navigation */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="w-full justify-start border-b rounded-none h-auto p-0 bg-transparent flex-wrap">
          {TABS.map(tab => (
            <TabsTrigger
              key={tab.key}
              value={tab.key}
              className="flex items-center gap-1.5 rounded-none border-b-2 border-transparent data-[state=active]:border-primary px-4 py-2.5"
            >
              <tab.icon className="h-3.5 w-3.5" />
              {tab.label}
            </TabsTrigger>
          ))}
        </TabsList>

        <Suspense fallback={<TabLoading />}>
          <TabsContent value="forecast" className="mt-0 pt-4">
            <DemandPlanView />
          </TabsContent>
          <TabsContent value="pipeline" className="mt-0 pt-4">
            <ForecastPipeline />
          </TabsContent>
          <TabsContent value="analytics" className="mt-0 pt-4">
            <ForecastAnalytics />
          </TabsContent>
          <TabsContent value="editor" className="mt-0 pt-4">
            <DemandPlanEdit />
          </TabsContent>
          <TabsContent value="sensing" className="mt-0 pt-4">
            <ForecastAdjWorklistPage />
          </TabsContent>
          <TabsContent value="shaping" className="mt-0 pt-4">
            <PromotionalPlanning />
          </TabsContent>
          <TabsContent value="consensus" className="mt-0 pt-4">
            <ConsensusPlanning />
          </TabsContent>
          <TabsContent value="lifecycle" className="mt-0 pt-4">
            <ProductLifecycle />
          </TabsContent>
          <TabsContent value="exceptions" className="mt-0 pt-4">
            <ForecastExceptions />
          </TabsContent>
        </Suspense>
      </Tabs>
    </div>
  );
}
