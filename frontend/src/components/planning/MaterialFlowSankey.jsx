/**
 * Material Flow Sankey — Visualizes material flowing through the distribution network.
 *
 * Layout: Suppliers (Vendors) → DCs (CDC / RDC) → Customers
 * Flow widths proportional to order/shipment quantities.
 *
 * Data sources:
 *   - Supply chain config: sites (with dag_type) and transportation_lanes
 *   - /demand-plan/aggregated: flow volumes per site
 */

import React, { useEffect, useMemo, useState } from 'react';
import {
  Card,
  CardContent,
  Spinner,
} from '../common';
import { GitBranch } from 'lucide-react';
import SankeyDiagram from '../charts/SankeyDiagram';
import {
  getSites,
  getTransportationLanes,
} from '../../services/supplyChainConfigService';
import { api } from '../../services/api';
import { useActiveConfig } from '../../contexts/ActiveConfigContext';

// Colors per site role
const ROLE_COLORS = {
  vendor: '#8b5cf6',        // purple
  cdc: '#3b82f6',           // blue
  rdc: '#06b6d4',           // cyan
  dc: '#0ea5e9',            // sky
  manufacturer: '#f97316',  // orange
  customer: '#10b981',      // emerald
};

const classifySite = (site) => {
  const dagType = (site.dag_type || site.type || site.master_type || '').toLowerCase();
  const name = (site.name || '').toLowerCase();

  if (dagType.includes('vendor') || dagType === 'supplier') return 'vendor';
  if (dagType.includes('customer')) return 'customer';
  if (dagType.includes('manufacturer')) return 'manufacturer';

  // DC sub-classification
  if (dagType.includes('cdc') || name.includes('cdc') || name.includes('central')) return 'cdc';
  if (dagType.includes('rdc') || name.includes('rdc') || name.includes('regional')) return 'rdc';
  if (dagType.includes('distribution') || dagType.includes('inventory') || dagType.includes('warehouse') || dagType.includes('dc')) return 'dc';

  return 'dc'; // default for unknown internal sites
};

const roleLabel = (role) => {
  const labels = {
    vendor: 'Vendor',
    cdc: 'CDC',
    rdc: 'RDC',
    dc: 'DC',
    manufacturer: 'Manufacturer',
    customer: 'Customer',
  };
  return labels[role] || role;
};

// Column ordering: vendors left, DCs center, customers right
const COLUMN_ORDER = ['vendor', 'manufacturer', 'cdc', 'dc', 'rdc', 'customer'];

const MaterialFlowSankey = () => {
  const { effectiveConfigId } = useActiveConfig();
  const [sites, setSites] = useState([]);
  const [lanes, setLanes] = useState([]);
  const [demandData, setDemandData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!effectiveConfigId) return;
    setLoading(true);
    setError(null);

    Promise.all([
      getSites(effectiveConfigId),
      getTransportationLanes(effectiveConfigId),
      api.get('/demand-plan/aggregated', {
        params: { config_id: effectiveConfigId, time_bucket: 'month' },
      }).then(res => res.data).catch(() => null),
    ])
      .then(([sitesData, lanesData, demand]) => {
        setSites(Array.isArray(sitesData) ? sitesData : []);
        setLanes(Array.isArray(lanesData) ? lanesData : []);
        setDemandData(demand);
      })
      .catch(err => {
        setError(err.response?.data?.detail || 'Failed to load network topology');
      })
      .finally(() => setLoading(false));
  }, [effectiveConfigId]);

  const { nodes, links, legend } = useMemo(() => {
    if (!sites.length || !lanes.length) {
      return { nodes: [], links: [], legend: [] };
    }

    // Build site map with classifications
    const siteMap = new Map();
    for (const site of sites) {
      const id = String(site.id);
      const role = classifySite(site);
      siteMap.set(id, {
        id,
        name: site.name || `Site ${id}`,
        role,
        type: role,
        color: ROLE_COLORS[role] || ROLE_COLORS.dc,
      });
    }

    // Build demand volume lookup by site (sum across all periods)
    const siteVolume = new Map();
    const series = demandData?.series || [];
    for (const pt of series) {
      const siteId = String(pt.site_id || '');
      if (!siteId) continue;
      const vol = pt.p50 || pt.quantity || pt.value || 0;
      siteVolume.set(siteId, (siteVolume.get(siteId) || 0) + vol);
    }

    // Per-site volumes from demand breakdown
    const siteDemandBreakdown = demandData?.site_breakdown || [];
    for (const entry of siteDemandBreakdown) {
      const siteId = String(entry.site_id || '');
      if (!siteId) continue;
      const vol = entry.total || entry.quantity || entry.p50 || 0;
      if (vol > 0 && !siteVolume.has(siteId)) {
        siteVolume.set(siteId, vol);
      }
    }

    // Build links from transportation lanes
    const linkList = [];
    const connectedNodeIds = new Set();

    for (const lane of lanes) {
      const sourceId = String(lane.source_site_id ?? lane.source_id ?? lane.from_site_id ?? '');
      const targetId = String(lane.destination_site_id ?? lane.target_site_id ?? lane.target_id ?? lane.to_site_id ?? '');

      if (!sourceId || !targetId || !siteMap.has(sourceId) || !siteMap.has(targetId)) continue;

      // Flow value: use lane throughput, or demand at target, or a baseline
      const laneVolume = lane.throughput || lane.capacity || lane.volume || 0;
      const targetVol = siteVolume.get(targetId) || 0;
      const sourceVol = siteVolume.get(sourceId) || 0;
      const flowValue = laneVolume > 0 ? laneVolume : (targetVol > 0 ? targetVol : (sourceVol > 0 ? sourceVol : 100));

      const sourceRole = siteMap.get(sourceId)?.role;
      const targetRole = siteMap.get(targetId)?.role;

      linkList.push({
        source: sourceId,
        target: targetId,
        value: flowValue,
        color: ROLE_COLORS[sourceRole] || ROLE_COLORS[targetRole] || '#94a3b8',
      });

      connectedNodeIds.add(sourceId);
      connectedNodeIds.add(targetId);
    }

    // Only include connected nodes
    const nodeList = [];
    const roleCounts = {};
    for (const [id, site] of siteMap) {
      if (!connectedNodeIds.has(id)) continue;
      nodeList.push(site);
      roleCounts[site.role] = (roleCounts[site.role] || 0) + 1;
    }

    // Build legend
    const legendItems = Object.entries(roleCounts)
      .sort(([a], [b]) => COLUMN_ORDER.indexOf(a) - COLUMN_ORDER.indexOf(b))
      .map(([role, count]) => ({
        label: `${roleLabel(role)} (${count})`,
        color: ROLE_COLORS[role] || '#94a3b8',
      }));

    return { nodes: nodeList, links: linkList, legend: legendItems };
  }, [sites, lanes, demandData]);

  if (!effectiveConfigId) return null;

  return (
    <Card>
      <CardContent className="pt-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold flex items-center gap-2">
            <GitBranch className="h-4 w-4" />
            Material Flow Through Distribution Network
          </h3>
          {legend.length > 0 && (
            <div className="flex items-center gap-3">
              {legend.map(item => (
                <div key={item.label} className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <span
                    className="inline-block w-3 h-3 rounded-sm"
                    style={{ backgroundColor: item.color }}
                  />
                  {item.label}
                </div>
              ))}
            </div>
          )}
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-64">
            <Spinner className="h-8 w-8" />
            <span className="ml-3 text-muted-foreground">Loading network topology...</span>
          </div>
        ) : error ? (
          <div className="flex items-center justify-center h-64 text-muted-foreground">
            <p>{error}</p>
          </div>
        ) : nodes.length === 0 || links.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 text-muted-foreground">
            <GitBranch className="h-10 w-10 mb-2 opacity-40" />
            <p className="text-sm">No network flow data available.</p>
            <p className="text-xs mt-1">Ensure sites and transportation lanes are configured.</p>
          </div>
        ) : (
          <SankeyDiagram
            nodes={nodes}
            links={links}
            height={420}
            margin={{ top: 16, right: 140, bottom: 16, left: 140 }}
            nodeWidth={16}
            nodePadding={24}
            columnOrder={COLUMN_ORDER}
            defaultLinkOpacity={0.45}
            nodeCornerRadius={3}
            renderNodeTopLabel={(node) => node.name}
            renderNodeBottomLabel={(node) => roleLabel(node.role)}
            linkTooltip={(link) => {
              const sourceName = typeof link.source === 'object' ? link.source.name : link.sourceId;
              const targetName = typeof link.target === 'object' ? link.target.name : link.targetId;
              const val = Math.round(link.value || 0);
              return `${sourceName} → ${targetName}: ${val.toLocaleString()} units`;
            }}
            nodeTooltip={(node) => {
              const totalIn = (node.targetLinks || []).reduce((s, l) => s + (l.value || 0), 0);
              const totalOut = (node.sourceLinks || []).reduce((s, l) => s + (l.value || 0), 0);
              return (
                <span>
                  <strong>{node.name}</strong> ({roleLabel(node.role)})<br />
                  In: {Math.round(totalIn).toLocaleString()} · Out: {Math.round(totalOut).toLocaleString()}
                </span>
              );
            }}
            emptyState={
              <div className="flex items-center justify-center h-48 text-muted-foreground text-sm">
                No flow data to display
              </div>
            }
          />
        )}
      </CardContent>
    </Card>
  );
};

export default MaterialFlowSankey;
