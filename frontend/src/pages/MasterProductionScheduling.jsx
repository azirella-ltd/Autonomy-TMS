/**
 * Master Production Scheduling — Kinaxis-style time-phased grid.
 *
 * Rows: Product × Site
 * Columns: Weeks (W01, W02, W03...)
 * Cells: Planned quantity from Plan of Record
 *
 * Agent-generated — no manual creation. Users inspect and override via Decision Stream.
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, CardContent, Badge, Button, Alert,
  Tabs, TabsList, TabsTrigger, TabsContent,
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '../components/common';
import { Calendar, RefreshCw, ChevronDown, ChevronUp } from 'lucide-react';
import { api } from '../services/api';
import { useActiveConfig } from '../contexts/ActiveConfigContext';
import ScenarioPanel from '../components/planning/ScenarioPanel';
import { cn } from '../lib/utils/cn';

export default function MasterProductionScheduling() {
  const { effectiveConfigId } = useActiveConfig();
  const [gridData, setGridData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [weeks, setWeeks] = useState(12);
  const [expandedCategories, setExpandedCategories] = useState(new Set());
  const [tab, setTab] = useState('grid');
  const cfgId = effectiveConfigId || 129;

  const loadGrid = useCallback(async () => {
    if (!cfgId) return;
    setLoading(true);
    try {
      const res = await api.get('/demand-plan/grid', {
        params: { config_id: cfgId, weeks },
      });
      setGridData(res.data);
      // Auto-expand all categories
      const cats = new Set(res.data?.rows?.map(r => r.category).filter(Boolean));
      setExpandedCategories(cats);
    } catch (err) {
      console.error('Grid load failed:', err);
    } finally {
      setLoading(false);
    }
  }, [cfgId, weeks]);

  useEffect(() => { loadGrid(); }, [loadGrid]);

  const columns = gridData?.columns || [];
  const rows = gridData?.rows || [];

  // Group rows by category
  const byCategory = {};
  rows.forEach(r => {
    const cat = r.category || 'Uncategorized';
    if (!byCategory[cat]) byCategory[cat] = [];
    byCategory[cat].push(r);
  });

  const toggleCategory = (cat) => {
    setExpandedCategories(prev => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat); else next.add(cat);
      return next;
    });
  };

  return (
    <div className="max-w-full mx-auto px-4 py-6">
      <div className="flex justify-between items-center mb-4">
        <div className="flex items-center gap-2">
          <Calendar className="h-7 w-7 text-primary" />
          <div>
            <h1 className="text-2xl font-bold">Production & Supply Schedule</h1>
            <p className="text-sm text-muted-foreground">
              Plan of Record — {rows.length} product×site combinations × {columns.length} weeks
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <select className="border rounded px-2 py-1.5 text-sm" value={weeks}
            onChange={e => setWeeks(parseInt(e.target.value))}>
            <option value={8}>8 weeks</option>
            <option value={12}>12 weeks</option>
            <option value={26}>26 weeks</option>
            <option value={52}>52 weeks</option>
          </select>
          <Button variant="outline" onClick={loadGrid} disabled={loading}
            leftIcon={<RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />}>
            Refresh
          </Button>
        </div>
      </div>

      <ScenarioPanel className="mb-4" />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="grid">Plan Grid</TabsTrigger>
          <TabsTrigger value="capacity">Capacity</TabsTrigger>
          <TabsTrigger value="metrics">Performance</TabsTrigger>
        </TabsList>

        <TabsContent value="grid">
          {rows.length > 0 ? (
            <Card>
              <CardContent className="pt-4 pb-2">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm border-collapse">
                    <thead>
                      <tr className="border-b-2">
                        <th className="sticky left-0 bg-white z-20 text-left py-2 px-3 min-w-[240px] border-r">
                          Product / Site
                        </th>
                        {columns.map(col => (
                          <th key={col.date} className="text-center py-1 px-1 min-w-[70px] text-xs">
                            <div className="font-bold">{col.label}</div>
                            <div className="text-muted-foreground font-normal">{col.month}</div>
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(byCategory).map(([cat, catRows]) => (
                        <React.Fragment key={cat}>
                          {/* Category header row */}
                          <tr className="bg-muted/50 cursor-pointer hover:bg-muted"
                            onClick={() => toggleCategory(cat)}>
                            <td className="sticky left-0 bg-muted/50 z-10 py-1.5 px-3 font-semibold border-r flex items-center gap-1" colSpan={1}>
                              {expandedCategories.has(cat)
                                ? <ChevronDown className="h-3 w-3" />
                                : <ChevronUp className="h-3 w-3" />}
                              {cat}
                              <Badge variant="secondary" className="text-[10px] ml-1">{catRows.length}</Badge>
                            </td>
                            {/* Category totals */}
                            {columns.map(col => {
                              const total = catRows.reduce((sum, r) => sum + (r.weeks?.[col.date] || 0), 0);
                              return (
                                <td key={col.date} className="text-center py-1.5 px-1 font-semibold text-xs bg-muted/50">
                                  {total > 0 ? Math.round(total).toLocaleString() : ''}
                                </td>
                              );
                            })}
                          </tr>
                          {/* Product×site rows */}
                          {expandedCategories.has(cat) && catRows.map(row => (
                            <tr key={`${row.product_id}|${row.site_id}`} className="border-b hover:bg-blue-50/30">
                              <td className="sticky left-0 bg-white z-10 py-1 px-3 border-r">
                                <div className="text-xs font-medium truncate max-w-[220px]">{row.product_name}</div>
                                <div className="text-[10px] text-muted-foreground">{row.site_name}</div>
                              </td>
                              {columns.map(col => {
                                const qty = row.weeks?.[col.date];
                                return (
                                  <td key={col.date} className={cn(
                                    "text-center py-1 px-1 text-xs tabular-nums",
                                    qty > 0 ? "text-foreground" : "text-muted-foreground/30"
                                  )}>
                                    {qty > 0 ? Math.round(qty).toLocaleString() : '—'}
                                  </td>
                                );
                              })}
                            </tr>
                          ))}
                        </React.Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          ) : (
            <Alert className="mt-4">
              {loading ? 'Loading plan grid...' : 'No plan data. Run provisioning to generate the Plan of Record.'}
            </Alert>
          )}
        </TabsContent>

        <TabsContent value="capacity">
          <Alert className="mt-4">
            Capacity view — resource utilization against the production schedule.
          </Alert>
        </TabsContent>

        <TabsContent value="metrics">
          <Alert className="mt-4">
            Performance — plan adherence, schedule stability, on-time delivery.
          </Alert>
        </TabsContent>
      </Tabs>
    </div>
  );
}
