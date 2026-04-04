/**
 * Forecast Analytics Hub — Unified tabbed interface for forecast analysts / data scientists.
 *
 * Tabs:
 *   Pipeline      — LightGBM/Holt-Winters model training and configuration
 *   Accuracy      — WAPE/RMSE/MAE/CRPS metrics by hierarchy
 *   Drift         — Pattern shift and feature drift detection
 *   Distributions — Fitted distribution analysis (Normal, Lognormal, Weibull, etc.)
 *   Backtesting   — Holdout validation, model comparison
 */

import React, { useState, useEffect, lazy, Suspense } from 'react';
import { useSearchParams, useLocation } from 'react-router-dom';
import {
  Tabs, TabsList, TabsTrigger, TabsContent,
} from '../../components/common';
import TabErrorBoundary from '../../components/TabErrorBoundary';
import RoleTimeSeries from '../../components/charts/RoleTimeSeries';
import { useActiveConfig } from '../../contexts/ActiveConfigContext';
import {
  Cpu, Target, Activity, BarChart3, FlaskConical,
} from 'lucide-react';

const Forecasting = lazy(() => import('./Forecasting'));
const KPIMonitoring = lazy(() => import('./KPIMonitoring'));
const ForecastExceptions = lazy(() => import('./ForecastExceptions'));
const DistributionAnalysis = lazy(() => import('./DistributionAnalysis'));
const ForecastBacktesting = lazy(() => import('./ForecastBacktesting'));

const TABS = [
  { key: 'pipeline', label: 'Pipeline', icon: Cpu },
  { key: 'accuracy', label: 'Accuracy', icon: Target },
  { key: 'drift', label: 'Drift', icon: Activity },
  { key: 'distributions', label: 'Distributions', icon: BarChart3 },
  { key: 'backtesting', label: 'Backtesting', icon: FlaskConical },
];

const TabLoading = () => (
  <div className="flex items-center justify-center h-64 text-muted-foreground">Loading...</div>
);

export default function ForecastAnalyticsHub() {
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  const { effectiveConfigId } = useActiveConfig();
  const initialTab = searchParams.get('tab') || location.state?.tab || 'pipeline';
  const [activeTab, setActiveTab] = useState(initialTab);

  useEffect(() => {
    if (searchParams.get('tab') !== activeTab) {
      setSearchParams({ tab: activeTab }, { replace: true });
    }
  }, [activeTab]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-4">
      <RoleTimeSeries roleKey="forecast_analyst" configId={effectiveConfigId} compact />

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

        <TabErrorBoundary>
        <Suspense fallback={<TabLoading />}>
          <TabsContent value="pipeline" className="mt-0 pt-4"><Forecasting /></TabsContent>
          <TabsContent value="accuracy" className="mt-0 pt-4"><KPIMonitoring /></TabsContent>
          <TabsContent value="drift" className="mt-0 pt-4"><ForecastExceptions /></TabsContent>
          <TabsContent value="distributions" className="mt-0 pt-4"><DistributionAnalysis /></TabsContent>
          <TabsContent value="backtesting" className="mt-0 pt-4"><ForecastBacktesting /></TabsContent>
        </Suspense>
        </TabErrorBoundary>
      </Tabs>
    </div>
  );
}
