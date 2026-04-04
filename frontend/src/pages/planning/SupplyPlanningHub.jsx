/**
 * Supply Planning Hub — Unified tabbed interface for supply planners.
 *
 * Tabs:
 *   Plan Generation   — AWS SC 3-step planner with probabilistic BSC
 *   Directives        — Supply Agent proposals, accept/override
 *   Sourcing          — Buy/transfer/manufacture rules with priorities
 *   Net Requirements  — MRP BOM explosion, component requirements
 *   Lot Sizing        — EOQ, LFL, POQ algorithm comparison
 *   Capacity Check    — Rough-cut capacity validation
 *   Lead Times        — Supplier lead time management
 */

import React, { useState, useEffect, useMemo, lazy, Suspense } from 'react';
import { useSearchParams, useLocation } from 'react-router-dom';
import {
  Tabs, TabsList, TabsTrigger, TabsContent,
} from '../../components/common';
import TabErrorBoundary from '../../components/TabErrorBoundary';
import RoleTimeSeries from '../../components/charts/RoleTimeSeries';
import { useActiveConfig } from '../../contexts/ActiveConfigContext';
import { api } from '../../services/api';
import {
  Play, ListChecks, Store, Calculator, Layers,
  Gauge, Clock,
} from 'lucide-react';

const SupplyPlanGeneration = lazy(() => import('./SupplyPlanGeneration'));
const SupplyWorklistPage = lazy(() => import('./SupplyWorklistPage'));
const SourcingAllocation = lazy(() => import('./SourcingAllocation'));
const MRPRun = lazy(() => import('./MRPRun'));
const LotSizingAnalysis = lazy(() => import('./LotSizingAnalysis'));
const CapacityCheck = lazy(() => import('./CapacityCheck'));
const VendorLeadTimes = lazy(() => import('./VendorLeadTimes'));

const ALL_TABS = [
  { key: 'generation', label: 'Plan Generation', icon: Play },
  { key: 'directives', label: 'Directives', icon: ListChecks },
  { key: 'sourcing', label: 'Sourcing', icon: Store },
  { key: 'netting', label: 'Net Requirements', icon: Calculator, manufacturerOnly: true },
  { key: 'lot_sizing', label: 'Lot Sizing', icon: Layers, manufacturerOnly: true },
  { key: 'capacity', label: 'Capacity Check', icon: Gauge, manufacturerOnly: true },
  { key: 'lead_times', label: 'Lead Times', icon: Clock },
];

/** Tabs that require at least one manufacturer site in the config */
const MANUFACTURER_ONLY_KEYS = new Set(['netting', 'lot_sizing', 'capacity']);

const TabLoading = () => (
  <div className="flex items-center justify-center h-64 text-muted-foreground">Loading...</div>
);

export default function SupplyPlanningHub() {
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  const { effectiveConfigId } = useActiveConfig();
  const [hasManufacturer, setHasManufacturer] = useState(true); // default true to avoid flash
  const initialTab = searchParams.get('tab') || location.state?.tab || 'generation';
  const [activeTab, setActiveTab] = useState(initialTab);

  // Fetch config to check for manufacturer sites
  useEffect(() => {
    if (!effectiveConfigId) return;
    let cancelled = false;
    api.get(`/supply-chain-config/${effectiveConfigId}`)
      .then(res => {
        if (cancelled) return;
        const defs = res.data?.site_type_definitions || [];
        const hasMfg = defs.some(d =>
          (d.master_type || '').toLowerCase() === 'manufacturer'
        );
        setHasManufacturer(hasMfg);
      })
      .catch(() => { /* keep default */ });
    return () => { cancelled = true; };
  }, [effectiveConfigId]);

  const visibleTabs = useMemo(
    () => hasManufacturer ? ALL_TABS : ALL_TABS.filter(t => !MANUFACTURER_ONLY_KEYS.has(t.key)),
    [hasManufacturer]
  );

  // If active tab got hidden, reset to first visible tab
  useEffect(() => {
    if (!visibleTabs.some(t => t.key === activeTab)) {
      setActiveTab(visibleTabs[0]?.key || 'generation');
    }
  }, [visibleTabs, activeTab]);

  useEffect(() => {
    if (searchParams.get('tab') !== activeTab) {
      setSearchParams({ tab: activeTab }, { replace: true });
    }
  }, [activeTab]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-4">
      <RoleTimeSeries roleKey="supply_planner" configId={effectiveConfigId} compact />

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="w-full justify-start border-b rounded-none h-auto p-0 bg-transparent flex-wrap">
          {visibleTabs.map(tab => (
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

        <TabErrorBoundary>
        <Suspense fallback={<TabLoading />}>
          <TabsContent value="generation" className="mt-0 pt-4"><SupplyPlanGeneration /></TabsContent>
          <TabsContent value="directives" className="mt-0 pt-4"><SupplyWorklistPage /></TabsContent>
          <TabsContent value="sourcing" className="mt-0 pt-4"><SourcingAllocation /></TabsContent>
          <TabsContent value="netting" className="mt-0 pt-4"><MRPRun /></TabsContent>
          <TabsContent value="lot_sizing" className="mt-0 pt-4"><LotSizingAnalysis /></TabsContent>
          <TabsContent value="capacity" className="mt-0 pt-4"><CapacityCheck /></TabsContent>
          <TabsContent value="lead_times" className="mt-0 pt-4"><VendorLeadTimes /></TabsContent>
        </Suspense>
        </TabErrorBoundary>
      </Tabs>
    </div>
  );
}
