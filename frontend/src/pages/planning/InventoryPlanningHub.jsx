/**
 * Inventory Planning Hub — Unified tabbed interface for inventory planners.
 *
 * Tabs:
 *   Policies      — 8 safety stock policy types with hierarchical overrides
 *   Projections   — Forward inventory simulation and what-if
 *   Segmentation  — ABC/XYZ classification, demand pattern analysis
 *   Allocations   — Priority-based allocation commits
 *   ATP/CTP       — Available/Capable to Promise analysis
 *   Rebalancing   — Cross-location transfer optimization
 *   Excess & Obs. — E&O identification and write-off tracking
 */

import React, { useState, useEffect, lazy, Suspense } from 'react';
import { useSearchParams, useLocation } from 'react-router-dom';
import {
  Tabs, TabsList, TabsTrigger, TabsContent,
} from '../../components/common';
import RoleTimeSeries from '../../components/charts/RoleTimeSeries';
import ScenarioPanel from '../../components/planning/ScenarioPanel';
import { useActiveConfig } from '../../contexts/ActiveConfigContext';
import {
  Shield, LineChart, BarChart3, Crosshair,
  ArrowLeftRight, AlertTriangle, Grid3X3,
} from 'lucide-react';

const InventoryOptimization = lazy(() => import('./InventoryOptimization'));
const InventoryProjection = lazy(() => import('./InventoryProjection'));
const InventorySegmentation = lazy(() => import('./InventorySegmentation'));
const AllocationWorklistPage = lazy(() => import('./AllocationWorklistPage'));
const ATPCTPView = lazy(() => import('./ATPCTPView'));
const RebalancingWorklistPage = lazy(() => import('./RebalancingWorklistPage'));
const ExcessObsolete = lazy(() => import('./ExcessObsolete'));

const TABS = [
  { key: 'policies', label: 'Policies', icon: Shield },
  { key: 'projections', label: 'Projections', icon: LineChart },
  { key: 'segmentation', label: 'Segmentation', icon: Grid3X3 },
  { key: 'allocations', label: 'Allocations', icon: Crosshair },
  { key: 'atp_ctp', label: 'ATP/CTP', icon: BarChart3 },
  { key: 'rebalancing', label: 'Rebalancing', icon: ArrowLeftRight },
  { key: 'excess', label: 'Excess & Obs.', icon: AlertTriangle },
];

const TabLoading = () => (
  <div className="flex items-center justify-center h-64 text-muted-foreground">Loading...</div>
);


export default function InventoryPlanningHub() {
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  const { effectiveConfigId } = useActiveConfig();
  const initialTab = searchParams.get('tab') || location.state?.tab || 'policies';
  const [activeTab, setActiveTab] = useState(initialTab);

  useEffect(() => {
    if (searchParams.get('tab') !== activeTab) {
      setSearchParams({ tab: activeTab }, { replace: true });
    }
  }, [activeTab]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-4">
      <RoleTimeSeries roleKey="inventory_planner" configId={effectiveConfigId} compact />
      <ScenarioPanel />

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
          <TabsContent value="policies" className="mt-0 pt-4"><InventoryOptimization /></TabsContent>
          <TabsContent value="projections" className="mt-0 pt-4"><InventoryProjection /></TabsContent>
          <TabsContent value="segmentation" className="mt-0 pt-4"><InventorySegmentation /></TabsContent>
          <TabsContent value="allocations" className="mt-0 pt-4"><AllocationWorklistPage /></TabsContent>
          <TabsContent value="atp_ctp" className="mt-0 pt-4"><ATPCTPView /></TabsContent>
          <TabsContent value="rebalancing" className="mt-0 pt-4"><RebalancingWorklistPage /></TabsContent>
          <TabsContent value="excess" className="mt-0 pt-4"><ExcessObsolete /></TabsContent>
        </Suspense>
      </Tabs>
    </div>
  );
}
