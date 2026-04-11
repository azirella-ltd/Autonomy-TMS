/**
 * SupplyChainVSM — Supply Chain Value Stream Map
 *
 * Horizontal timeline visualization showing material flow through the supply chain
 * network with inventory buffers, lead times, and decision points at each step.
 *
 * Unlike the Sankey (which shows flow volume), the VSM emphasizes TIME:
 * - Horizontal axis = cumulative lead time from supplier to customer
 * - Inventory triangles at each node = buffer stock
 * - Lead time ladder at bottom = value-add vs wait time breakdown
 * - Information flow arrows (top) = demand signals flowing upstream
 * - Material flow arrows (bottom) = goods flowing downstream
 *
 * Props:
 *   sites: Array of site objects with metrics
 *   lanes: Array of transportation lane objects with lead times
 *   configId: Supply chain config ID
 */

import React, { useMemo } from 'react';
import { cn } from '@azirella-ltd/autonomy-frontend';

// Color palette
const SITE_COLORS = {
  VENDOR: '#1d4ed8',
  MANUFACTURER: '#0891b2',
  INVENTORY: '#0ea5e9',
  CUSTOMER: '#be123c',
};

const DOS_COLOR = (dos) => {
  if (dos == null) return '#94a3b8';
  if (dos < 7) return '#ef4444';   // critical
  if (dos < 14) return '#f59e0b';  // warning
  if (dos < 30) return '#22c55e';  // healthy
  return '#16a34a';                // excess
};

/**
 * Build the VSM data from sites and lanes.
 * Finds the critical path (longest lead time path) through the DAG.
 */
const buildVSMData = (sites, lanes) => {
  if (!sites?.length || !lanes?.length) return null;

  // Build adjacency and site maps
  const siteMap = {};
  sites.forEach(s => {
    const id = String(s.id);
    siteMap[id] = {
      ...s,
      masterType: (s.master_type || '').toUpperCase(),
      metrics: s.metrics || {},
    };
  });

  // Add virtual partner nodes from partner-endpoint lanes
  lanes.forEach(lane => {
    if (lane.from_partner_id && !lane.from_site_id) {
      const pid = `partner_${lane.from_partner_id}`;
      if (!siteMap[pid]) {
        siteMap[pid] = {
          id: pid, name: lane.from_partner_name || `Vendor ${lane.from_partner_id}`,
          masterType: 'VENDOR', metrics: {},
        };
      }
    }
    if (lane.to_partner_id && !lane.to_site_id) {
      const pid = `partner_${lane.to_partner_id}`;
      if (!siteMap[pid]) {
        siteMap[pid] = {
          id: pid, name: lane.to_partner_name || `Customer ${lane.to_partner_id}`,
          masterType: 'CUSTOMER', metrics: {},
        };
      }
    }
  });

  // Build directed edges with lead times
  const edges = lanes.map(lane => {
    const fromId = String(lane.from_site_id ?? (lane.from_partner_id ? `partner_${lane.from_partner_id}` : null));
    const toId = String(lane.to_site_id ?? (lane.to_partner_id ? `partner_${lane.to_partner_id}` : null));
    const lt = lane.supply_lead_time?.value ?? lane.lead_time_days?.value ??
               lane.lead_time_days?.avg ?? lane.lead_time ?? 0;
    return { from: fromId, to: toId, leadTime: lt, capacity: lane.capacity ?? 0 };
  }).filter(e => e.from && e.to && siteMap[e.from] && siteMap[e.to]);

  // Find the critical path (longest path) using BFS/topological approach
  // Simple approach: find all vendor→customer paths and pick longest
  const adjacency = {};
  edges.forEach(e => {
    if (!adjacency[e.from]) adjacency[e.from] = [];
    adjacency[e.from].push(e);
  });

  // Find source nodes (no incoming edges) and sink nodes (no outgoing edges)
  const hasIncoming = new Set(edges.map(e => e.to));
  const hasOutgoing = new Set(edges.map(e => e.from));
  const sources = Object.keys(siteMap).filter(id => !hasIncoming.has(id) && hasOutgoing.has(id));
  const sinks = Object.keys(siteMap).filter(id => !hasOutgoing.has(id) && hasIncoming.has(id));

  // BFS to find longest path
  let longestPath = [];
  let longestTime = 0;

  const dfs = (nodeId, path, totalTime) => {
    path.push(nodeId);
    const outEdges = adjacency[nodeId] || [];
    if (outEdges.length === 0 || sinks.includes(nodeId)) {
      if (totalTime > longestTime) {
        longestTime = totalTime;
        longestPath = [...path];
      }
    }
    for (const edge of outEdges) {
      if (!path.includes(edge.to)) {
        dfs(edge.to, path, totalTime + edge.leadTime);
      }
    }
    path.pop();
  };

  sources.forEach(src => dfs(src, [], 0));

  // If no path found, just use all sites in master_type order
  if (longestPath.length === 0) {
    const typeOrder = ['VENDOR', 'MANUFACTURER', 'INVENTORY', 'CUSTOMER'];
    longestPath = Object.keys(siteMap).sort((a, b) => {
      const aOrder = typeOrder.indexOf(siteMap[a].masterType);
      const bOrder = typeOrder.indexOf(siteMap[b].masterType);
      return aOrder - bOrder;
    });
  }

  // Build VSM steps from the critical path
  const steps = longestPath.map((nodeId, idx) => {
    const site = siteMap[nodeId];
    const outEdge = edges.find(e => e.from === nodeId && longestPath.includes(e.to));
    const inEdge = edges.find(e => e.to === nodeId && longestPath.includes(e.from));

    return {
      id: nodeId,
      name: site.name,
      masterType: site.masterType,
      color: SITE_COLORS[site.masterType] || '#6b7280',
      // Inventory metrics
      onHand: site.metrics.on_hand_qty ?? 0,
      safetyStock: site.metrics.safety_stock ?? 0,
      daysOfSupply: site.metrics.days_of_supply,
      inventoryRatio: site.metrics.inventory_ratio,
      // Lead time to next step
      leadTimeToNext: outEdge?.leadTime ?? 0,
      leadTimeFromPrev: inEdge?.leadTime ?? 0,
      // Position
      index: idx,
      isFirst: idx === 0,
      isLast: idx === longestPath.length - 1,
    };
  });

  // Compute totals for the lead time ladder
  const totalLeadTime = steps.reduce((sum, s) => sum + s.leadTimeToNext, 0);
  const totalInventoryDays = steps.reduce((sum, s) => sum + (s.daysOfSupply ?? 0), 0);

  return {
    steps,
    totalLeadTime,
    totalInventoryDays,
    totalTime: totalLeadTime + totalInventoryDays,
    pathLength: steps.length,
  };
};

const SupplyChainVSM = ({ sites, lanes, className, height = 280 }) => {
  const vsmData = useMemo(() => buildVSMData(sites, lanes), [sites, lanes]);

  if (!vsmData || vsmData.steps.length === 0) {
    return (
      <div className={cn('flex items-center justify-center text-muted-foreground text-sm', className)}
           style={{ height }}>
        No supply chain data available for VSM
      </div>
    );
  }

  const { steps, totalLeadTime, totalInventoryDays } = vsmData;
  const stepWidth = Math.max(120, Math.min(200, (800 / steps.length)));
  const gapWidth = 60;
  const totalWidth = steps.length * stepWidth + (steps.length - 1) * gapWidth;
  const valueAddPct = totalLeadTime > 0 ? Math.round((totalLeadTime / (totalLeadTime + totalInventoryDays)) * 100) : 0;

  return (
    <div className={cn('overflow-x-auto', className)}>
      <div style={{ minWidth: totalWidth + 40, padding: '16px 20px' }}>

        {/* ── Information Flow (top — demand signals flowing right to left) ── */}
        <div className="flex items-center mb-1">
          <div className="flex-1 flex items-center justify-center">
            <span className="text-[10px] text-muted-foreground mr-1">Demand Signal</span>
            <svg width={totalWidth - 80} height={12}>
              <defs>
                <marker id="arrowLeft" markerWidth="6" markerHeight="4" refX="0" refY="2" orient="auto">
                  <polygon points="6,0 6,4 0,2" fill="#94a3b8" />
                </marker>
              </defs>
              <line x1={totalWidth - 100} y1={6} x2={20} y2={6}
                    stroke="#94a3b8" strokeWidth={1} strokeDasharray="4,3"
                    markerEnd="url(#arrowLeft)" />
            </svg>
          </div>
        </div>

        {/* ── Process Steps ── */}
        <div className="flex items-end" style={{ gap: gapWidth }}>
          {steps.map((step, idx) => (
            <div key={step.id} style={{ width: stepWidth }} className="flex flex-col items-center">

              {/* Inventory triangle */}
              {step.onHand > 0 && (
                <div className="relative mb-1 flex flex-col items-center">
                  <svg width={40} height={30} className="mb-0.5">
                    <polygon points="20,0 40,30 0,30"
                             fill={DOS_COLOR(step.daysOfSupply)}
                             fillOpacity={0.2}
                             stroke={DOS_COLOR(step.daysOfSupply)}
                             strokeWidth={1.5} />
                  </svg>
                  <span className="text-[9px] font-mono text-muted-foreground">
                    {step.onHand.toLocaleString()}
                  </span>
                  {step.daysOfSupply != null && (
                    <span className="text-[9px] font-medium" style={{ color: DOS_COLOR(step.daysOfSupply) }}>
                      {step.daysOfSupply}d
                    </span>
                  )}
                </div>
              )}

              {/* Process box */}
              <div
                className="rounded-md border-2 px-2 py-2 text-center w-full"
                style={{ borderColor: step.color, backgroundColor: `${step.color}10` }}
              >
                <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                  {step.masterType}
                </div>
                <div className="text-xs font-semibold mt-0.5 truncate" title={step.name}>
                  {step.name}
                </div>
              </div>

              {/* Lead time arrow to next step */}
              {!step.isLast && step.leadTimeToNext > 0 && (
                <div className="absolute" style={{
                  left: `${(idx + 1) * (stepWidth + gapWidth) - gapWidth / 2 - 10}px`,
                  top: '50%',
                }}>
                  <span className="text-[9px] font-mono text-amber-600 bg-background px-1">
                    {step.leadTimeToNext}d
                  </span>
                </div>
              )}
            </div>
          ))}
        </div>

        {/* ── Lead Time Arrows Between Steps ── */}
        <div className="flex items-center mt-2" style={{ gap: 0 }}>
          {steps.map((step, idx) => (
            <React.Fragment key={step.id}>
              <div style={{ width: stepWidth }} className="flex justify-center">
                <div className="w-0.5 h-3 bg-border" />
              </div>
              {!step.isLast && (
                <div style={{ width: gapWidth }} className="flex flex-col items-center">
                  <div className="text-[10px] font-mono font-medium text-amber-600">
                    {step.leadTimeToNext}d
                  </div>
                  <svg width={gapWidth} height={8}>
                    <defs>
                      <marker id="arrowRight" markerWidth="6" markerHeight="4" refX="6" refY="2" orient="auto">
                        <polygon points="0,0 6,2 0,4" fill="#d97706" />
                      </marker>
                    </defs>
                    <line x1={4} y1={4} x2={gapWidth - 4} y2={4}
                          stroke="#d97706" strokeWidth={1.5}
                          markerEnd="url(#arrowRight)" />
                  </svg>
                </div>
              )}
            </React.Fragment>
          ))}
        </div>

        {/* ── Lead Time Ladder (bottom summary) ── */}
        <div className="mt-4 pt-3 border-t border-border">
          <div className="flex items-center gap-4 text-xs">
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-sm bg-amber-500/20 border border-amber-500" />
              <span className="text-muted-foreground">Transit: <span className="font-medium text-foreground">{totalLeadTime}d</span></span>
            </div>
            <div className="flex items-center gap-1.5">
              <svg width={12} height={12}>
                <polygon points="6,0 12,12 0,12" fill="#22c55e" fillOpacity={0.3} stroke="#22c55e" strokeWidth={1} />
              </svg>
              <span className="text-muted-foreground">Buffer: <span className="font-medium text-foreground">{totalInventoryDays}d</span></span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-muted-foreground">Total: <span className="font-medium text-foreground">{totalLeadTime + totalInventoryDays}d</span></span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-muted-foreground">Value-add: <span className="font-medium text-foreground">{valueAddPct}%</span></span>
            </div>
          </div>

          {/* Visual lead time bar */}
          <div className="mt-2 h-2 rounded-full bg-muted overflow-hidden flex">
            {steps.map((step, idx) => (
              <React.Fragment key={step.id}>
                {/* Buffer time (inventory) */}
                {(step.daysOfSupply ?? 0) > 0 && (
                  <div
                    className="h-full"
                    style={{
                      width: `${((step.daysOfSupply ?? 0) / (totalLeadTime + totalInventoryDays)) * 100}%`,
                      backgroundColor: DOS_COLOR(step.daysOfSupply),
                      opacity: 0.4,
                    }}
                    title={`${step.name}: ${step.daysOfSupply}d buffer`}
                  />
                )}
                {/* Transit time */}
                {step.leadTimeToNext > 0 && (
                  <div
                    className="h-full bg-amber-500"
                    style={{
                      width: `${(step.leadTimeToNext / (totalLeadTime + totalInventoryDays)) * 100}%`,
                    }}
                    title={`Transit to next: ${step.leadTimeToNext}d`}
                  />
                )}
              </React.Fragment>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default SupplyChainVSM;
