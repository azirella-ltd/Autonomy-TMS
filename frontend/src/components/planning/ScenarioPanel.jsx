/**
 * Scenario Panel — Reusable component for scenario management.
 *
 * Embeds in any planning page (MPS, Supply, Inventory, Demand).
 * Provides: create scenario, list scenarios, compare, promote.
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, CardContent, Button, Badge, Input, Modal,
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '../common';
import { GitBranch, Plus, BarChart3, ArrowUp, RefreshCw, ChevronDown, ChevronUp } from 'lucide-react';
import { api } from '../../services/api';
import { useActiveConfig } from '../../contexts/ActiveConfigContext';
import { cn } from '../../lib/utils/cn';

const TYPE_COLORS = {
  BASELINE: 'bg-green-100 text-green-700',
  WHAT_IF: 'bg-blue-100 text-blue-700',
  OPTIMIZATION: 'bg-purple-100 text-purple-700',
  RISK_ANALYSIS: 'bg-amber-100 text-amber-700',
};

export default function ScenarioPanel({ className }) {
  const { effectiveConfigId } = useActiveConfig();
  const [scenarios, setScenarios] = useState(null);
  const [baseline, setBaseline] = useState(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [compareResult, setCompareResult] = useState(null);
  const [form, setForm] = useState({ name: '', description: '', scenario_type: 'WHAT_IF' });

  const cfgId = effectiveConfigId;

  const load = useCallback(async () => {
    if (!cfgId) return;
    setLoading(true);
    try {
      const res = await api.get('/scenario-planning/', { params: { config_id: cfgId } });
      setBaseline(res.data.baseline);
      setScenarios(res.data.scenarios || []);
    } catch (err) {
      console.error('Scenario load failed:', err);
    } finally {
      setLoading(false);
    }
  }, [cfgId]);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    try {
      await api.post('/scenario-planning/', form, { params: { config_id: cfgId } });
      setCreateOpen(false);
      setForm({ name: '', description: '', scenario_type: 'WHAT_IF' });
      load();
    } catch (err) {
      alert(`Failed: ${err.response?.data?.detail || err.message}`);
    }
  };

  const handleCompare = async (scenarioId) => {
    try {
      const res = await api.get('/scenario-planning/compare', {
        params: { baseline_id: cfgId, scenario_id: scenarioId },
      });
      setCompareResult(res.data);
    } catch (err) {
      console.error('Compare failed:', err);
    }
  };

  const handlePromote = async (scenarioId) => {
    if (!window.confirm('Promote this scenario to baseline? The current baseline will be archived.')) return;
    try {
      await api.post(`/scenario-planning/${scenarioId}/promote`);
      load();
    } catch (err) {
      alert(`Failed: ${err.response?.data?.detail || err.message}`);
    }
  };

  return (
    <Card className={cn("border-dashed", className)}>
      <CardContent className="pt-3 pb-3">
        {/* Header — always visible */}
        <div className="flex items-center justify-between cursor-pointer" onClick={() => setExpanded(!expanded)}>
          <div className="flex items-center gap-2">
            <GitBranch className="h-4 w-4 text-primary" />
            <span className="font-medium text-sm">Scenarios</span>
            {scenarios && (
              <Badge variant="secondary" className="text-xs">{scenarios.length}</Badge>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" className="h-7 text-xs"
              onClick={(e) => { e.stopPropagation(); setCreateOpen(true); }}>
              <Plus className="h-3 w-3 mr-1" /> New Scenario
            </Button>
            {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </div>
        </div>

        {/* Expanded scenario list */}
        {expanded && (
          <div className="mt-3 pt-3 border-t space-y-2">
            {/* Baseline */}
            {baseline && (
              <div className="flex items-center justify-between py-1 px-2 bg-green-50 rounded">
                <div className="flex items-center gap-2">
                  <Badge className={TYPE_COLORS.BASELINE}>Baseline</Badge>
                  <span className="text-sm font-medium">{baseline.name}</span>
                </div>
                <span className="text-xs text-muted-foreground">Active</span>
              </div>
            )}

            {/* Scenarios */}
            {scenarios?.map(s => (
              <div key={s.id} className="flex items-center justify-between py-1 px-2 border rounded">
                <div className="flex items-center gap-2">
                  <Badge className={TYPE_COLORS[s.scenario_type] || TYPE_COLORS.WHAT_IF}>
                    {s.scenario_type}
                  </Badge>
                  <span className="text-sm">{s.name}</span>
                </div>
                <div className="flex gap-1">
                  <Button variant="ghost" size="sm" className="h-6 text-xs"
                    onClick={() => handleCompare(s.id)} title="Compare with baseline">
                    <BarChart3 className="h-3 w-3" />
                  </Button>
                  <Button variant="ghost" size="sm" className="h-6 text-xs"
                    onClick={() => handlePromote(s.id)} title="Promote to baseline">
                    <ArrowUp className="h-3 w-3" />
                  </Button>
                </div>
              </div>
            ))}

            {scenarios?.length === 0 && (
              <p className="text-xs text-muted-foreground text-center py-2">
                No scenarios yet. Create one to test different planning parameters.
              </p>
            )}

            {/* Comparison results */}
            {compareResult && (
              <Card className="mt-2 bg-blue-50 border-blue-200">
                <CardContent className="pt-3 pb-3">
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-sm font-semibold">Scenario Comparison</span>
                    <Button variant="ghost" size="sm" className="h-6" onClick={() => setCompareResult(null)}>
                      Close
                    </Button>
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-xs">
                    <div className="font-medium">Metric</div>
                    <div className="font-medium">Baseline</div>
                    <div className="font-medium">Scenario (Δ)</div>
                    {Object.entries(compareResult.deltas || {}).map(([key, d]) => (
                      <React.Fragment key={key}>
                        <div className="capitalize">{key.replace(/_/g, ' ')}</div>
                        <div>{typeof d.baseline === 'number' ? d.baseline.toLocaleString() : d.baseline}</div>
                        <div>
                          {typeof d.scenario === 'number' ? d.scenario.toLocaleString() : d.scenario}
                          {d.delta_pct !== 0 && (
                            <span className={cn("ml-1", d.delta_pct > 0 ? "text-green-600" : "text-red-600")}>
                              ({d.delta_pct > 0 ? '+' : ''}{d.delta_pct}%)
                            </span>
                          )}
                        </div>
                      </React.Fragment>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        )}
      </CardContent>

      {/* Create Modal */}
      <Modal isOpen={createOpen} onClose={() => setCreateOpen(false)} title="Create Scenario" size="md"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button onClick={handleCreate} disabled={!form.name}>Create</Button>
          </div>
        }>
        <div className="space-y-3">
          <div>
            <label className="text-sm font-medium block mb-1">Scenario Name</label>
            <Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
              placeholder="e.g., Q3 Demand Uplift + New Supplier" />
          </div>
          <div>
            <label className="text-sm font-medium block mb-1">Description</label>
            <Input value={form.description} onChange={e => setForm({ ...form, description: e.target.value })}
              placeholder="What are you testing?" />
          </div>
          <div>
            <label className="text-sm font-medium block mb-1">Type</label>
            <select className="w-full border rounded px-3 py-2 text-sm" value={form.scenario_type}
              onChange={e => setForm({ ...form, scenario_type: e.target.value })}>
              <option value="WHAT_IF">What-If Analysis</option>
              <option value="OPTIMIZATION">Optimization</option>
              <option value="RISK_ANALYSIS">Risk Analysis</option>
            </select>
          </div>
        </div>
      </Modal>
    </Card>
  );
}
