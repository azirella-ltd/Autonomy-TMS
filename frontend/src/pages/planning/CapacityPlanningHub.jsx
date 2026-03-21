/**
 * Capacity Planning Hub — Unified tabbed interface for capacity planners.
 *
 * Tabs:
 *   Utilization   — Resource utilization rates and trending
 *   Bottleneck    — Constraint identification and what-if analysis
 *   Rough-Cut     — RCCP from MPS
 *   Processes     — Work center and process configuration
 *   Workforce     — Shift planning, labor availability
 *   Maintenance   — PM scheduling, deferral decisions
 */

import React, { useState, useEffect, lazy, Suspense } from 'react';
import { useSearchParams, useLocation } from 'react-router-dom';
import {
  Tabs, TabsList, TabsTrigger, TabsContent,
  Card, CardContent,
} from '../../components/common';
import RoleTimeSeries from '../../components/charts/RoleTimeSeries';
import { useActiveConfig } from '../../contexts/ActiveConfigContext';
import {
  Gauge, AlertTriangle, Target, Factory,
  Users, Wrench,
} from 'lucide-react';

const ResourceCapacity = lazy(() => import('./ResourceCapacity'));
const CapacityCheck = lazy(() => import('./CapacityCheck'));
const ProductionProcesses = lazy(() => import('./ProductionProcesses'));
const MaintenanceWorklistPage = lazy(() => import('./MaintenanceWorklistPage'));

const TABS = [
  { key: 'utilization', label: 'Utilization', icon: Gauge },
  { key: 'bottleneck', label: 'Bottleneck', icon: AlertTriangle },
  { key: 'roughcut', label: 'Rough-Cut', icon: Target },
  { key: 'processes', label: 'Processes', icon: Factory },
  { key: 'workforce', label: 'Workforce', icon: Users },
  { key: 'maintenance', label: 'Maintenance', icon: Wrench },
];

const TabLoading = () => (
  <div className="flex items-center justify-center h-64 text-muted-foreground">Loading...</div>
);

const ComingSoonTab = ({ title, description }) => (
  <Card>
    <CardContent className="flex flex-col items-center justify-center py-16 text-center">
      <h3 className="text-lg font-semibold mb-2">{title}</h3>
      <p className="text-muted-foreground max-w-md">{description}</p>
    </CardContent>
  </Card>
);

export default function CapacityPlanningHub() {
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  const { effectiveConfigId } = useActiveConfig();
  const initialTab = searchParams.get('tab') || location.state?.tab || 'utilization';
  const [activeTab, setActiveTab] = useState(initialTab);

  useEffect(() => {
    if (searchParams.get('tab') !== activeTab) {
      setSearchParams({ tab: activeTab }, { replace: true });
    }
  }, [activeTab]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-4">
      <RoleTimeSeries roleKey="capacity_planner" configId={effectiveConfigId} compact />

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
          <TabsContent value="utilization" className="mt-0 pt-4"><ResourceCapacity /></TabsContent>
          <TabsContent value="bottleneck" className="mt-0 pt-4">
            <ComingSoonTab
              title="Bottleneck Analysis"
              description="Identify binding constraints, evaluate relaxation options (overtime, outsourcing, shift extension), and model capacity-constrained production scenarios."
            />
          </TabsContent>
          <TabsContent value="roughcut" className="mt-0 pt-4"><CapacityCheck /></TabsContent>
          <TabsContent value="processes" className="mt-0 pt-4"><ProductionProcesses /></TabsContent>
          <TabsContent value="workforce" className="mt-0 pt-4">
            <ComingSoonTab
              title="Workforce Planning"
              description="Shift planning, labor availability calendars, skill matrix, overtime tracking, and labor cost modeling by work center."
            />
          </TabsContent>
          <TabsContent value="maintenance" className="mt-0 pt-4"><MaintenanceWorklistPage /></TabsContent>
        </Suspense>
      </Tabs>
    </div>
  );
}
