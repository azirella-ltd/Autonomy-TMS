import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import { api } from '../../services/api';
import { cn } from '../../lib/utils/cn';
import {
  Card, CardContent, Badge, Button, Spinner, Alert, AlertDescription,
} from '../../components/common';
import {
  Search, Filter, ChevronDown, ChevronUp, ExternalLink,
  Truck, AlertTriangle, CheckCircle, Clock, XCircle, RefreshCw,
} from 'lucide-react';

const STATUS_COLORS = {
  NOT_STARTED: '#9ca3af',
  IN_TRANSIT: '#3b82f6',
  AT_RISK: '#f59e0b',
  EXCEPTION: '#ef4444',
  DELIVERED: '#22c55e',
};

const MODES = ['All', 'Road', 'Rail', 'Ocean', 'Air', 'Intermodal'];

const STATUSES = ['NOT_STARTED', 'IN_TRANSIT', 'AT_RISK', 'EXCEPTION', 'DELIVERED'];

const STATUS_LABELS = {
  NOT_STARTED: 'Not Started',
  IN_TRANSIT: 'In Transit',
  AT_RISK: 'At Risk',
  EXCEPTION: 'Exception',
  DELIVERED: 'Delivered',
};

const pulseStyle = `
@keyframes shipment-pulse {
  0% { opacity: 1; }
  50% { opacity: 0.4; }
  100% { opacity: 1; }
}
.shipment-marker-pulse {
  animation: shipment-pulse 1.5s ease-in-out infinite;
}
`;

/** Simple marker clustering by grid proximity */
function clusterMarkers(shipments, zoomLevel) {
  const gridSize = 2 / Math.pow(2, Math.max(zoomLevel - 4, 0));
  const clusters = new Map();
  shipments.forEach((s) => {
    if (s.lat == null || s.lon == null) return;
    const key = `${Math.round(s.lat / gridSize)}_${Math.round(s.lon / gridSize)}`;
    if (!clusters.has(key)) {
      clusters.set(key, { lat: 0, lon: 0, items: [] });
    }
    const c = clusters.get(key);
    c.items.push(s);
    c.lat = (c.lat * (c.items.length - 1) + s.lat) / c.items.length;
    c.lon = (c.lon * (c.items.length - 1) + s.lon) / c.items.length;
  });
  return Array.from(clusters.values());
}

/** Track map zoom for clustering */
function ZoomTracker({ onZoomChange }) {
  const map = useMap();
  useEffect(() => {
    const handler = () => onZoomChange(map.getZoom());
    map.on('zoomend', handler);
    return () => map.off('zoomend', handler);
  }, [map, onZoomChange]);
  return null;
}

const ShipmentMap = () => {
  const [shipments, setShipments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilters, setStatusFilters] = useState(new Set(STATUSES));
  const [modeFilter, setModeFilter] = useState('All');
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedShipment, setSelectedShipment] = useState(null);
  const [listExpanded, setListExpanded] = useState(true);
  const [zoom, setZoom] = useState(4);
  const refreshTimerRef = useRef(null);

  const fetchShipments = useCallback(async () => {
    setError(null);
    try {
      const response = await api.get('/shipments/map');
      setShipments(response.data || []);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to fetch shipment map data');
      setShipments([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchShipments();
    refreshTimerRef.current = setInterval(fetchShipments, 60000);
    return () => clearInterval(refreshTimerRef.current);
  }, [fetchShipments]);

  const toggleStatus = useCallback((status) => {
    setStatusFilters((prev) => {
      const next = new Set(prev);
      if (next.has(status)) next.delete(status);
      else next.add(status);
      return next;
    });
  }, []);

  const setOnlyStatus = useCallback((status) => {
    setStatusFilters(new Set([status]));
  }, []);

  const filtered = useMemo(() => {
    return shipments.filter((s) => {
      if (!statusFilters.has(s.status)) return false;
      if (modeFilter !== 'All' && s.mode !== modeFilter) return false;
      if (searchTerm) {
        const term = searchTerm.toLowerCase();
        if (
          !(s.shipment_id || '').toLowerCase().includes(term) &&
          !(s.carrier || '').toLowerCase().includes(term)
        ) return false;
      }
      return true;
    });
  }, [shipments, statusFilters, modeFilter, searchTerm]);

  const kpis = useMemo(() => {
    const counts = { NOT_STARTED: 0, IN_TRANSIT: 0, AT_RISK: 0, EXCEPTION: 0, DELIVERED: 0 };
    shipments.forEach((s) => {
      if (counts[s.status] !== undefined) counts[s.status]++;
    });
    return counts;
  }, [shipments]);

  const clusters = useMemo(() => clusterMarkers(filtered, zoom), [filtered, zoom]);

  if (loading && shipments.length === 0) {
    return (
      <div className="flex items-center justify-center h-96">
        <Spinner className="w-8 h-8" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <style>{pulseStyle}</style>

      {error && (
        <Alert variant="destructive" className="mx-4 mt-2">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Filter bar + KPI pills */}
      <div className="flex flex-wrap items-center gap-3 px-4 py-2 border-b bg-background">
        {/* Status checkboxes */}
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-muted-foreground" />
          {STATUSES.map((st) => (
            <label key={st} className="flex items-center gap-1 text-xs cursor-pointer">
              <input
                type="checkbox"
                checked={statusFilters.has(st)}
                onChange={() => toggleStatus(st)}
                className="w-3 h-3"
              />
              <span
                className="w-2 h-2 rounded-full inline-block"
                style={{ backgroundColor: STATUS_COLORS[st] }}
              />
              <span className="text-muted-foreground">{STATUS_LABELS[st]}</span>
            </label>
          ))}
        </div>

        {/* Mode filter */}
        <select
          value={modeFilter}
          onChange={(e) => setModeFilter(e.target.value)}
          className="text-xs border rounded px-2 py-1 bg-background"
        >
          {MODES.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search ID or carrier..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="text-xs border rounded pl-6 pr-2 py-1 w-48 bg-background"
          />
        </div>

        <Button variant="ghost" size="sm" onClick={fetchShipments} className="ml-auto">
          <RefreshCw className="w-3 h-3 mr-1" /> Refresh
        </Button>

        {/* KPI pills */}
        <div className="flex items-center gap-2 ml-2">
          {[
            { key: 'IN_TRANSIT', icon: Truck, label: 'In Transit' },
            { key: 'AT_RISK', icon: AlertTriangle, label: 'At Risk' },
            { key: 'EXCEPTION', icon: XCircle, label: 'Exceptions' },
            { key: 'DELIVERED', icon: CheckCircle, label: 'Delivered Today' },
            { key: 'NOT_STARTED', icon: Clock, label: 'Not Started' },
          ].map(({ key, icon: Icon, label }) => (
            <button
              key={key}
              onClick={() => setOnlyStatus(key)}
              className={cn(
                'flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border cursor-pointer transition-colors',
                statusFilters.size === 1 && statusFilters.has(key)
                  ? 'ring-2 ring-offset-1'
                  : 'opacity-80 hover:opacity-100'
              )}
              style={{
                borderColor: STATUS_COLORS[key],
                color: STATUS_COLORS[key],
              }}
            >
              <Icon className="w-3 h-3" />
              {kpis[key] != null ? kpis[key] : '\u2014'}
              <span className="hidden sm:inline ml-0.5">{label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Map + overlays */}
      <div className="relative flex-1" style={{ minHeight: 'calc(100vh - 200px)' }}>
        <MapContainer
          center={[39.8283, -98.5795]}
          zoom={4}
          className="w-full h-full z-0"
          style={{ height: '100%' }}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <ZoomTracker onZoomChange={setZoom} />

          {clusters.map((cluster, idx) => {
            const isCluster = cluster.items.length > 1;
            const primary = cluster.items[0];
            const color = isCluster ? '#6366f1' : (STATUS_COLORS[primary.status] || '#9ca3af');
            const radius = isCluster ? Math.min(8 + cluster.items.length, 24) : 8;
            const isException = !isCluster && primary.status === 'EXCEPTION';

            return (
              <CircleMarker
                key={idx}
                center={[cluster.lat, cluster.lon]}
                radius={radius}
                pathOptions={{
                  color,
                  fillColor: color,
                  fillOpacity: 0.7,
                  weight: 2,
                  className: isException ? 'shipment-marker-pulse' : undefined,
                }}
                eventHandlers={{
                  click: () => {
                    if (!isCluster) setSelectedShipment(primary);
                  },
                }}
              >
                {isCluster && (
                  <Popup>
                    <span className="text-xs font-medium">{cluster.items.length} shipments</span>
                  </Popup>
                )}
              </CircleMarker>
            );
          })}
        </MapContainer>

        {/* Right overlay: shipment detail panel */}
        {selectedShipment && (
          <div className="absolute top-2 right-2 w-[300px] max-h-[calc(100%-220px)] overflow-y-auto bg-background/95 backdrop-blur border rounded-lg shadow-lg z-[1000] p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="font-semibold text-sm">{selectedShipment.shipment_id || '\u2014'}</span>
              <button
                onClick={() => setSelectedShipment(null)}
                className="text-muted-foreground hover:text-foreground text-xs"
              >
                \u2715
              </button>
            </div>

            <div className="space-y-2 text-xs">
              <div>
                <span className="text-muted-foreground">Route: </span>
                {selectedShipment.origin || '\u2014'} \u2192 {selectedShipment.destination || '\u2014'}
              </div>
              <div>
                <span className="text-muted-foreground">Carrier: </span>
                {selectedShipment.carrier || '\u2014'}
              </div>
              <div>
                <span className="text-muted-foreground">Mode: </span>
                {selectedShipment.mode || '\u2014'}
              </div>
              <div>
                <span className="text-muted-foreground">Equipment: </span>
                {selectedShipment.equipment || '\u2014'}
              </div>
              <div>
                <span className="text-muted-foreground">ETA: </span>
                {selectedShipment.current_eta
                  ? new Date(selectedShipment.current_eta).toLocaleString()
                  : '\u2014'}
              </div>
              {(selectedShipment.eta_p10 || selectedShipment.eta_p90) && (
                <div className="text-[11px] text-muted-foreground pl-2">
                  Conformal range: P10{' '}
                  {selectedShipment.eta_p10
                    ? new Date(selectedShipment.eta_p10).toLocaleString()
                    : '\u2014'}{' '}
                  / P90{' '}
                  {selectedShipment.eta_p90
                    ? new Date(selectedShipment.eta_p90).toLocaleString()
                    : '\u2014'}
                </div>
              )}
              <div>
                <span className="text-muted-foreground">Status: </span>
                <Badge
                  variant="outline"
                  style={{
                    borderColor: STATUS_COLORS[selectedShipment.status],
                    color: STATUS_COLORS[selectedShipment.status],
                  }}
                >
                  {STATUS_LABELS[selectedShipment.status] || selectedShipment.status}
                </Badge>
              </div>

              {/* Exceptions with AIIO agent action */}
              {selectedShipment.exceptions && selectedShipment.exceptions.length > 0 && (
                <div className="mt-2 border-t pt-2">
                  <span className="font-medium text-destructive">Active Exceptions</span>
                  {selectedShipment.exceptions.map((exc, i) => (
                    <div key={i} className="mt-1 p-1.5 border rounded bg-destructive/5">
                      <div className="font-medium">{exc.type || exc}</div>
                      {exc.description && (
                        <div className="text-muted-foreground">{exc.description}</div>
                      )}
                    </div>
                  ))}
                  {selectedShipment.agent_action && (
                    <div className="mt-2 p-1.5 border rounded bg-primary/5">
                      <span className="text-muted-foreground">Agent Action (AIIO): </span>
                      <span className="font-medium">{selectedShipment.agent_action}</span>
                    </div>
                  )}
                </div>
              )}

              <Button
                variant="outline"
                size="sm"
                className="w-full mt-2"
                onClick={() => {
                  window.location.hash = '#/planning/shipment-tracking-worklist';
                }}
              >
                <ExternalLink className="w-3 h-3 mr-1" /> View in Worklist
              </Button>
            </div>
          </div>
        )}

        {/* Bottom overlay: collapsible shipment list */}
        <div
          className={cn(
            'absolute bottom-0 left-0 right-0 bg-background/95 backdrop-blur border-t z-[1000] transition-all',
            listExpanded ? 'h-[200px]' : 'h-8'
          )}
        >
          <button
            onClick={() => setListExpanded((v) => !v)}
            className="flex items-center gap-1 px-3 py-1 text-xs font-medium text-muted-foreground hover:text-foreground w-full border-b"
          >
            {listExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronUp className="w-3 h-3" />}
            {filtered.length} shipments
          </button>
          {listExpanded && (
            <div className="overflow-auto h-[calc(100%-32px)]">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-muted">
                  <tr>
                    <th className="text-left px-2 py-1 font-medium">ID</th>
                    <th className="text-left px-2 py-1 font-medium">Status</th>
                    <th className="text-left px-2 py-1 font-medium">Origin</th>
                    <th className="text-left px-2 py-1 font-medium">Destination</th>
                    <th className="text-left px-2 py-1 font-medium">Carrier</th>
                    <th className="text-left px-2 py-1 font-medium">Mode</th>
                    <th className="text-left px-2 py-1 font-medium">ETA</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((s, i) => (
                    <tr
                      key={s.shipment_id || i}
                      className={cn(
                        'cursor-pointer hover:bg-muted/50',
                        selectedShipment?.shipment_id === s.shipment_id && 'bg-muted'
                      )}
                      onClick={() => setSelectedShipment(s)}
                    >
                      <td className="px-2 py-1 font-mono">{s.shipment_id || '\u2014'}</td>
                      <td className="px-2 py-1">
                        <span
                          className="inline-block w-2 h-2 rounded-full mr-1"
                          style={{ backgroundColor: STATUS_COLORS[s.status] || '#9ca3af' }}
                        />
                        {STATUS_LABELS[s.status] || s.status || '\u2014'}
                      </td>
                      <td className="px-2 py-1">{s.origin || '\u2014'}</td>
                      <td className="px-2 py-1">{s.destination || '\u2014'}</td>
                      <td className="px-2 py-1">{s.carrier || '\u2014'}</td>
                      <td className="px-2 py-1">{s.mode || '\u2014'}</td>
                      <td className="px-2 py-1">
                        {s.current_eta ? new Date(s.current_eta).toLocaleDateString() : '\u2014'}
                      </td>
                    </tr>
                  ))}
                  {filtered.length === 0 && (
                    <tr>
                      <td colSpan={7} className="px-2 py-4 text-center text-muted-foreground">
                        No shipments match the current filters
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ShipmentMap;
