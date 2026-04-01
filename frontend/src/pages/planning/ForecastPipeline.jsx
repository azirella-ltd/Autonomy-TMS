/**
 * Forecast Pipeline — 10-stage demand forecasting pipeline visualization.
 *
 * Shows the full pipeline flow from data prep to publish, with stage
 * status, metrics, and ability to re-run individual stages.
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, CardContent, Badge, Button, Alert,
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '../../components/common';
import {
  Database, BarChart3, Cpu, Brain, Target, TrendingUp,
  GitBranch, Users, AlertTriangle, Megaphone,
  CheckCircle, Clock, XCircle, Play, RefreshCw, ChevronDown, ChevronUp,
} from 'lucide-react';
import { api } from '../../services/api';
import { useActiveConfig } from '../../contexts/ActiveConfigContext';
import { cn } from '../../lib/utils/cn';

const STAGE_ICONS = {
  data_prep: Database,
  eda: BarChart3,
  feature_eng: Cpu,
  model_train: Brain,
  model_select: Target,
  forecast_gen: TrendingUp,
  reconcile: GitBranch,
  consensus: Users,
  exception_mgmt: AlertTriangle,
  publish: Megaphone,
};

const STATUS_STYLES = {
  completed: { icon: CheckCircle, color: 'text-green-600', bg: 'bg-green-50 border-green-200' },
  running: { icon: Clock, color: 'text-blue-600', bg: 'bg-blue-50 border-blue-200' },
  failed: { icon: XCircle, color: 'text-red-600', bg: 'bg-red-50 border-red-200' },
  pending: { icon: Clock, color: 'text-gray-400', bg: 'bg-gray-50 border-gray-200' },
  unknown: { icon: Clock, color: 'text-amber-500', bg: 'bg-amber-50 border-amber-200' },
};

export default function ForecastPipeline() {
  const { effectiveConfigId } = useActiveConfig();
  const [pipeline, setPipeline] = useState(null);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [expandedStage, setExpandedStage] = useState(null);

  const loadStatus = useCallback(async () => {
    const cfgId = effectiveConfigId || 129;
    if (!cfgId) return;
    setLoading(true);
    try {
      const res = await api.get('/forecast-analytics/pipeline/status', { params: { config_id: cfgId } });
      setPipeline(res.data);
    } catch (err) {
      console.error('Pipeline status load failed:', err);
    } finally {
      setLoading(false);
    }
  }, [effectiveConfigId]);

  useEffect(() => { loadStatus(); }, [loadStatus]);

  const runFullPipeline = async () => {
    const cfgId = effectiveConfigId || 129;
    setRunning(true);
    try {
      const res = await api.post('/forecast-analytics/pipeline/run', null, { params: { config_id: cfgId } });
      setPipeline(res.data);
    } catch (err) {
      console.error('Pipeline run failed:', err);
    } finally {
      setRunning(false);
    }
  };

  const runStage = async (stage) => {
    const cfgId = effectiveConfigId || 129;
    try {
      await api.post(`/forecast-analytics/pipeline/run/${stage}`, null, { params: { config_id: cfgId } });
      loadStatus();
    } catch (err) {
      console.error(`Stage ${stage} run failed:`, err);
    }
  };

  const stages = pipeline?.stages || {};
  const stageList = Object.values(stages);
  const completedCount = stageList.filter(s => s.status === 'completed').length;

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-xl font-bold">Forecasting Pipeline</h2>
          <p className="text-sm text-muted-foreground">
            10-stage pipeline from data preparation to published demand plan
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={loadStatus} disabled={loading}
            leftIcon={<RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />}>
            Refresh
          </Button>
          <Button onClick={runFullPipeline} disabled={running}
            leftIcon={<Play className="h-4 w-4" />}>
            {running ? 'Running...' : 'Run Full Pipeline'}
          </Button>
        </div>
      </div>

      {/* Progress bar */}
      <Card>
        <CardContent className="pt-4 pb-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium">
              Pipeline Progress: {completedCount}/{stageList.length} stages
            </span>
            <Badge variant={completedCount === stageList.length ? 'success' : 'secondary'}>
              {pipeline?.status || 'unknown'}
            </Badge>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-primary rounded-full h-2 transition-all"
              style={{ width: `${stageList.length > 0 ? (completedCount / stageList.length) * 100 : 0}%` }}
            />
          </div>
        </CardContent>
      </Card>

      {/* Stage cards */}
      <div className="space-y-2">
        {Object.entries(stages).map(([key, stage], index) => {
          const Icon = STAGE_ICONS[key] || Database;
          const statusStyle = STATUS_STYLES[stage.status] || STATUS_STYLES.pending;
          const StatusIcon = statusStyle.icon;
          const isExpanded = expandedStage === key;

          return (
            <Card key={key} className={cn("border", statusStyle.bg)}>
              <CardContent className="pt-3 pb-3">
                {/* Stage header */}
                <div className="flex items-center justify-between cursor-pointer"
                  onClick={() => setExpandedStage(isExpanded ? null : key)}>
                  <div className="flex items-center gap-3">
                    <div className="flex items-center gap-2 w-8 text-center">
                      <span className="text-xs text-muted-foreground font-mono">{index + 1}</span>
                    </div>
                    <Icon className={cn("h-5 w-5", statusStyle.color)} />
                    <div>
                      <span className="font-medium text-sm">{stage.label}</span>
                      {stage.records_processed > 0 && (
                        <span className="text-xs text-muted-foreground ml-2">
                          ({stage.records_processed.toLocaleString()} records)
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusIcon className={cn("h-4 w-4", statusStyle.color)} />
                    <Badge variant="outline" className="text-xs">{stage.status}</Badge>
                    {stage.duration_seconds > 0 && (
                      <span className="text-xs text-muted-foreground">{stage.duration_seconds}s</span>
                    )}
                    <Button variant="ghost" size="sm" className="h-6 w-6 p-0"
                      onClick={(e) => { e.stopPropagation(); runStage(key); }}>
                      <Play className="h-3 w-3" />
                    </Button>
                    {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                  </div>
                </div>

                {/* Expanded metrics */}
                {isExpanded && stage.metrics && (
                  <div className="mt-3 pt-3 border-t">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                      {Object.entries(stage.metrics).filter(([k, v]) =>
                        typeof v !== 'object' || v === null
                      ).map(([k, v]) => (
                        <div key={k} className="text-sm">
                          <span className="text-muted-foreground capitalize">{k.replace(/_/g, ' ')}:</span>{' '}
                          <span className="font-medium">
                            {typeof v === 'number' ? v.toLocaleString() : String(v)}
                          </span>
                        </div>
                      ))}
                    </div>
                    {stage.metrics.feature_list && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {stage.metrics.feature_list.map(f => (
                          <Badge key={f} variant="secondary" className="text-xs">{f}</Badge>
                        ))}
                      </div>
                    )}
                    {stage.metrics.methods && (
                      <div className="mt-2">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Method</TableHead>
                              <TableHead>Records</TableHead>
                              <TableHead>Products</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {stage.metrics.methods.map(m => (
                              <TableRow key={m.method}>
                                <TableCell className="text-sm">{m.method}</TableCell>
                                <TableCell>{m.records?.toLocaleString()}</TableCell>
                                <TableCell>{m.products}</TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </div>
                    )}
                    {stage.warnings?.length > 0 && (
                      <div className="mt-2">
                        {stage.warnings.map((w, i) => (
                          <Alert key={i} variant="warning" className="text-xs py-1 px-2 mb-1">
                            {w}
                          </Alert>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
