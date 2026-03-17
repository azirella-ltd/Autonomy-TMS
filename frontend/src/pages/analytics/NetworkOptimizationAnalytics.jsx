import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, Badge, Progress } from '../../components/common';
import { Network, MapPin, ArrowRight, Truck } from 'lucide-react';
import api from '../../services/api';

const NetworkOptimizationAnalytics = () => {
  const [sites, setSites] = useState([]);
  const [lanes, setLanes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState({ sites: 0, lanes: 0, avgLeadTime: 0, longestLane: '', regions: 0 });

  useEffect(() => {
    const load = async () => {
      try {
        const { data: configs } = await api.get('/supply-chain-config/');
        const cfg = Array.isArray(configs) ? configs.find(c => c.is_active) || configs[0] : null;
        if (!cfg) { setLoading(false); return; }

        const [sitesRes, lanesRes] = await Promise.all([
          api.get(`/supply-chain-config/${cfg.id}/sites`),
          api.get(`/supply-chain-config/${cfg.id}/lanes`),
        ]);

        const siteList = Array.isArray(sitesRes.data) ? sitesRes.data : [];
        const laneList = Array.isArray(lanesRes.data) ? lanesRes.data : [];

        const siteMap = {};
        for (const s of siteList) siteMap[s.id] = s;

        const enrichedLanes = laneList.map(l => {
          const from = siteMap[l.from_site_id] || {};
          const to = siteMap[l.to_site_id] || {};
          const lt = l.lead_time_min != null ? l.lead_time_min :
                     l.supply_lead_time?.value || l.supply_lead_time?.mean || l.lead_time || 0;
          return {
            id: l.id,
            fromName: from.name || l.from_site_id,
            toName: to.name || l.to_site_id,
            fromType: from.master_type || '',
            toType: to.master_type || '',
            leadTime: lt,
            capacity: l.capacity_int || l.capacity || l.value || 0,
          };
        });

        const regions = new Set(siteList.map(s => s.geography?.region).filter(Boolean));
        const sorted = [...enrichedLanes].sort((a, b) => b.leadTime - a.leadTime);
        const longest = sorted[0];

        setSites(siteList);
        setLanes(enrichedLanes);
        setSummary({
          sites: siteList.length,
          lanes: enrichedLanes.length,
          avgLeadTime: enrichedLanes.length > 0
            ? (enrichedLanes.reduce((s, l) => s + l.leadTime, 0) / enrichedLanes.length).toFixed(1) : 0,
          longestLane: longest ? `${longest.fromName} \u2192 ${longest.toName} (${longest.leadTime}d)` : '-',
          regions: regions.size || 1,
        });
      } catch (err) {
        console.error('Network analytics error:', err);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const sitesByType = {};
  for (const s of sites) {
    const t = s.master_type || 'OTHER';
    sitesByType[t] = (sitesByType[t] || 0) + 1;
  }

  const TYPE_COLORS = {
    MANUFACTURER: 'bg-purple-100 text-purple-700',
    INVENTORY: 'bg-blue-100 text-blue-700',
    MARKET_SUPPLY: 'bg-green-100 text-green-700',
    MARKET_DEMAND: 'bg-amber-100 text-amber-700',
  };

  return (
    <div className="container mx-auto px-4 py-6 max-w-7xl">
      <div className="flex items-center gap-2 mb-1">
        <Network className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-bold">Network Analytics</h1>
      </div>
      <p className="text-sm text-muted-foreground mb-6">
        Supply chain topology, transportation lane analysis, and network structure
      </p>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
        <Card><CardContent className="pt-5 pb-4">
          <p className="text-xs text-muted-foreground">Total Sites</p>
          <p className="text-2xl font-bold">{summary.sites}</p>
        </CardContent></Card>
        <Card><CardContent className="pt-5 pb-4">
          <p className="text-xs text-muted-foreground">Transport Lanes</p>
          <p className="text-2xl font-bold">{summary.lanes}</p>
        </CardContent></Card>
        <Card><CardContent className="pt-5 pb-4">
          <p className="text-xs text-muted-foreground">Avg Lead Time</p>
          <p className="text-2xl font-bold">{summary.avgLeadTime}d</p>
        </CardContent></Card>
        <Card><CardContent className="pt-5 pb-4">
          <p className="text-xs text-muted-foreground">Regions</p>
          <p className="text-2xl font-bold">{summary.regions}</p>
        </CardContent></Card>
        <Card><CardContent className="pt-5 pb-4">
          <p className="text-xs text-muted-foreground">Longest Lane</p>
          <p className="text-xs font-medium mt-1 truncate">{summary.longestLane}</p>
        </CardContent></Card>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <MapPin className="h-4 w-4" /> Site Composition
            </CardTitle>
          </CardHeader>
          <CardContent>
            {Object.entries(sitesByType).sort((a, b) => b[1] - a[1]).map(([type, count]) => (
              <div key={type} className="flex items-center justify-between py-2 border-b last:border-0">
                <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${TYPE_COLORS[type] || 'bg-gray-100 text-gray-700'}`}>
                  {type}
                </span>
                <div className="flex items-center gap-3">
                  <Progress value={(count / Math.max(sites.length, 1)) * 100} className="w-24 h-1.5" />
                  <span className="text-sm font-mono w-8 text-right">{count}</span>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <Truck className="h-4 w-4" /> Longest Transportation Lanes
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="text-center py-8 text-muted-foreground">Loading...</div>
            ) : lanes.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">No lanes configured</div>
            ) : (
              [...lanes].sort((a, b) => b.leadTime - a.leadTime).slice(0, 10).map((l) => (
                <div key={l.id} className="flex items-center gap-2 py-1.5 border-b last:border-0 text-sm">
                  <span className="truncate w-24">{l.fromName}</span>
                  <ArrowRight className="h-3 w-3 text-muted-foreground flex-shrink-0" />
                  <span className="truncate flex-1">{l.toName}</span>
                  <Badge variant="outline" className="text-[10px] flex-shrink-0">{l.leadTime}d</Badge>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};
export default NetworkOptimizationAnalytics;
