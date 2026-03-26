/**
 * ResourceHeatmap — Sites x Weeks capacity utilization grid.
 *
 * Rows = sites (MANUFACTURER first, then INVENTORY, then others).
 * Columns = weeks across the planning horizon.
 * Cell color intensity reflects utilization severity.
 *
 * Props:
 *   configId       — supply chain config ID
 *   horizonWeeks   — number of weeks to project (default 12)
 *   siteTypeFilter — optional master_type filter (e.g. "MANUFACTURER")
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Card,
  CardContent,
  Spinner,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../common';
import {
  AlertTriangle,
  RefreshCw,
  X,
  Package,
  Factory,
  Warehouse,
} from 'lucide-react';
import { api } from '../../services/api';


// ── Color thresholds ────────────────────────────────────────────
function getCellStyle(utilization) {
  if (utilization > 0.90) {
    return { backgroundColor: '#B71C1C', color: '#ffffff', fontWeight: 600 };
  }
  if (utilization > 0.70) {
    return { backgroundColor: '#FFEBEE', color: '#D32F2F', fontWeight: 600 };
  }
  if (utilization > 0.50) {
    return { backgroundColor: '#FFF8E1', color: '#F57C00', fontWeight: 500 };
  }
  return { backgroundColor: '#E8F5E9', color: '#388E3C', fontWeight: 400 };
}

function formatPct(val) {
  return `${Math.round(val * 100)}%`;
}

function masterTypeIcon(masterType) {
  if (masterType === 'MANUFACTURER') return <Factory className="h-3.5 w-3.5 inline mr-1" />;
  if (masterType === 'INVENTORY') return <Warehouse className="h-3.5 w-3.5 inline mr-1" />;
  return <Package className="h-3.5 w-3.5 inline mr-1" />;
}


// ── Cell Detail Panel ───────────────────────────────────────────
function CellDetailPanel({ detail, onClose }) {
  if (!detail) return null;

  return (
    <Card className="mt-4 border-l-4 border-l-blue-500">
      <CardContent className="py-3 px-4">
        <div className="flex items-center justify-between mb-3">
          <h4 className="text-sm font-semibold">
            Capacity Detail — Site {detail.site_id}, Week of {detail.week_start}
          </h4>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        {detail.supply_plan_items?.length > 0 && (
          <div className="mb-3">
            <h5 className="text-xs font-medium text-muted-foreground mb-1">Planned MO Requests</h5>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs py-1">Product</TableHead>
                  <TableHead className="text-xs py-1 text-right">Quantity</TableHead>
                  <TableHead className="text-xs py-1">Date</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {detail.supply_plan_items.map((item, idx) => (
                  <TableRow key={idx}>
                    <TableCell className="text-xs py-1">{item.product_name}</TableCell>
                    <TableCell className="text-xs py-1 text-right">{item.quantity.toLocaleString()}</TableCell>
                    <TableCell className="text-xs py-1">{item.date || '—'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        {detail.production_orders?.length > 0 && (
          <div>
            <h5 className="text-xs font-medium text-muted-foreground mb-1">Production Orders</h5>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs py-1">Order #</TableHead>
                  <TableHead className="text-xs py-1">Product</TableHead>
                  <TableHead className="text-xs py-1 text-right">Qty</TableHead>
                  <TableHead className="text-xs py-1 text-right">Hours</TableHead>
                  <TableHead className="text-xs py-1">Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {detail.production_orders.map((po, idx) => (
                  <TableRow key={idx}>
                    <TableCell className="text-xs py-1 font-mono">{po.order_number}</TableCell>
                    <TableCell className="text-xs py-1">{po.product_id}</TableCell>
                    <TableCell className="text-xs py-1 text-right">{po.planned_quantity.toLocaleString()}</TableCell>
                    <TableCell className="text-xs py-1 text-right">{po.resource_hours.toFixed(1)}</TableCell>
                    <TableCell className="text-xs py-1">
                      <Badge variant="outline" className="text-[10px]">{po.status}</Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        {(!detail.supply_plan_items?.length && !detail.production_orders?.length) && (
          <p className="text-xs text-muted-foreground">No orders found for this cell.</p>
        )}
      </CardContent>
    </Card>
  );
}


// ── Main Component ──────────────────────────────────────────────
export default function ResourceHeatmap({ configId, horizonWeeks = 12, siteTypeFilter }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [cellDetail, setCellDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const fetchHeatmap = useCallback(async () => {
    if (!configId) return;
    setLoading(true);
    setError(null);
    try {
      const params = { horizon_weeks: horizonWeeks };
      if (siteTypeFilter) params.site_type = siteTypeFilter;
      const res = await api.get(`/resource-heatmap/${configId}`, { params });
      setData(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to load heatmap data');
    } finally {
      setLoading(false);
    }
  }, [configId, horizonWeeks, siteTypeFilter]);

  useEffect(() => {
    fetchHeatmap();
  }, [fetchHeatmap]);

  const handleCellClick = async (siteId, weekIso) => {
    setDetailLoading(true);
    try {
      const res = await api.get(`/resource-heatmap/${configId}/cell-detail`, {
        params: { site_id: siteId, week_start: weekIso },
      });
      setCellDetail(res.data);
    } catch (err) {
      setCellDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  // --- Render states ---
  if (loading) {
    return (
      <div className="flex items-center justify-center h-48">
        <Spinner className="h-6 w-6 mr-2" />
        <span className="text-muted-foreground">Loading heatmap...</span>
      </div>
    );
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTriangle className="h-4 w-4" />
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }

  if (!data || !data.sites?.length) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <Factory className="h-10 w-10 mx-auto mb-2 opacity-50" />
        <p>No sites found for this configuration.</p>
        <p className="text-xs mt-1">Resource heatmap requires internal sites with capacity data.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Bottleneck Alerts Banner */}
      {data.bottleneck_alerts?.length > 0 && (
        <Alert variant="destructive" className="border-red-300 bg-red-50">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>
            <span className="font-medium">Bottleneck Alerts:</span>{' '}
            {data.bottleneck_alerts.slice(0, 3).map((alert, idx) => (
              <span key={idx}>
                {idx > 0 && ' | '}
                <strong>{alert.site_name}</strong> overallocated {alert.week} ({formatPct(alert.utilization)})
                {alert.competing_products?.length > 0 &&
                  ` — ${alert.competing_products.slice(0, 3).join(', ')} compete`
                }
              </span>
            ))}
            {data.bottleneck_alerts.length > 3 && (
              <span className="ml-1 text-xs">+{data.bottleneck_alerts.length - 3} more</span>
            )}
          </AlertDescription>
        </Alert>
      )}

      {/* Legend + Refresh */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3 text-xs">
          <span className="font-medium text-muted-foreground">Utilization:</span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-4 h-3 rounded-sm" style={{ backgroundColor: '#E8F5E9' }} />
            &le;50%
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-4 h-3 rounded-sm" style={{ backgroundColor: '#FFF8E1' }} />
            50-70%
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-4 h-3 rounded-sm" style={{ backgroundColor: '#FFEBEE' }} />
            70-90%
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-4 h-3 rounded-sm" style={{ backgroundColor: '#B71C1C' }} />
            &gt;90%
          </span>
        </div>
        <Button variant="outline" size="sm" onClick={fetchHeatmap}>
          <RefreshCw className="h-3.5 w-3.5 mr-1" /> Refresh
        </Button>
      </div>

      {/* Heatmap Grid */}
      <div className="overflow-x-auto border rounded-lg">
        <TooltipProvider delayDuration={200}>
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/30">
                <TableHead className="text-xs font-semibold py-2 px-3 sticky left-0 bg-muted/30 z-10 min-w-[180px]">
                  Site
                </TableHead>
                {data.week_labels.map((label, idx) => (
                  <TableHead
                    key={idx}
                    className="text-xs font-medium py-2 px-2 text-center whitespace-nowrap min-w-[72px]"
                  >
                    {label}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.sites.map((site) => (
                <TableRow key={site.site_id} className="hover:bg-muted/10">
                  <TableCell className="text-xs py-1.5 px-3 sticky left-0 bg-background z-10 border-r">
                    <div className="flex items-center">
                      {masterTypeIcon(site.master_type)}
                      <span className="font-medium truncate max-w-[140px]" title={site.site_name}>
                        {site.site_name}
                      </span>
                    </div>
                    <span className="text-[10px] text-muted-foreground">
                      {site.master_type || 'OTHER'}
                    </span>
                  </TableCell>
                  {site.weeks.map((week, wIdx) => {
                    const cellStyle = getCellStyle(week.utilization);
                    const tooltipText =
                      `${site.site_name} — ${data.week_labels[wIdx]}: ` +
                      `${week.planned_orders} planned orders, ` +
                      `${formatPct(week.utilization)} utilized ` +
                      `(${week.available_capacity}h available)`;

                    return (
                      <Tooltip key={wIdx}>
                        <TooltipTrigger asChild>
                          <TableCell
                            className="text-xs text-center py-1.5 px-1 cursor-pointer transition-opacity hover:opacity-80"
                            style={cellStyle}
                            onClick={() => handleCellClick(site.site_id, week.week)}
                          >
                            {formatPct(week.utilization)}
                          </TableCell>
                        </TooltipTrigger>
                        <TooltipContent side="top" className="max-w-xs text-xs">
                          {tooltipText}
                        </TooltipContent>
                      </Tooltip>
                    );
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TooltipProvider>
      </div>

      {/* Cell Detail Panel */}
      {detailLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Spinner className="h-4 w-4" /> Loading detail...
        </div>
      )}
      <CellDetailPanel detail={cellDetail} onClose={() => setCellDetail(null)} />
    </div>
  );
}
