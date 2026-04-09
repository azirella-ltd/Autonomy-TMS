import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { api } from '../../services/api';
import { cn } from '../../lib/utils/cn';
import {
  Card, CardContent, CardHeader, CardTitle,
  Badge, Button, Spinner, Alert, AlertDescription,
} from '../../components/common';
import {
  Calendar, ChevronLeft, ChevronRight, Clock, Truck,
  AlertTriangle, RefreshCw, Building, GaugeCircle,
} from 'lucide-react';

/**
 * Gantt-style dock schedule with 6am-6pm focus window, live ETA feed,
 * and appointment compliance tracking.
 * Pattern reference: FourKites Dynamic Yard.
 */

// 6:00 AM to 6:00 PM in 30-min ticks (24 ticks)
const GANTT_START_HOUR = 6;
const GANTT_END_HOUR = 18;
const GANTT_TOTAL_HOURS = GANTT_END_HOUR - GANTT_START_HOUR;
const TICK_COUNT = GANTT_TOTAL_HOURS * 2; // 30-min ticks

const TICKS = Array.from({ length: TICK_COUNT + 1 }, (_, i) => {
  const totalMinutes = GANTT_START_HOUR * 60 + i * 30;
  const h = Math.floor(totalMinutes / 60);
  const m = totalMinutes % 60;
  return {
    label: i % 2 === 0 ? `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}` : '',
    offset: i / TICK_COUNT,
    isHour: m === 0,
  };
});

const APPT_STATUS_COLORS = {
  SCHEDULED: 'bg-blue-400 border-blue-600 text-white',
  CHECKED_IN: 'bg-green-400 border-green-600 text-white',
  LOADING: 'bg-amber-400 border-amber-600 text-white',
  UNLOADING: 'bg-amber-400 border-amber-600 text-white',
  COMPLETED: 'bg-gray-300 border-gray-400 text-gray-700',
  NO_SHOW: 'bg-red-500 border-red-700 text-white',
  DETENTION: 'bg-red-400 border-red-600 text-white bg-stripes',
};

const formatDateISO = (date) => date.toISOString().split('T')[0];

const formatDisplayDate = (date) =>
  date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });

const formatTime = (dateStr) => {
  if (!dateStr) return '\u2014';
  try {
    const d = new Date(dateStr);
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
  } catch {
    return '\u2014';
  }
};

const DockSchedule = () => {
  const [appointments, setAppointments] = useState([]);
  const [facilities, setFacilities] = useState([]);
  const [selectedFacility, setSelectedFacility] = useState('');
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [inboundEtas, setInboundEtas] = useState([]);
  const [gateQueue, setGateQueue] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchFacilities = useCallback(async () => {
    try {
      const response = await api.get('/dock/facilities');
      const data = response.data?.facilities || response.data || [];
      setFacilities(data);
      if (data.length > 0 && !selectedFacility) {
        setSelectedFacility(data[0].id || data[0].facility_id);
      }
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to fetch facilities');
    }
  }, [selectedFacility]);

  const fetchAppointments = useCallback(async () => {
    if (!selectedFacility) return;
    setLoading(true);
    setError(null);
    try {
      const params = {
        facility_id: selectedFacility,
        date: formatDateISO(selectedDate),
      };
      const [apptRes, etaRes, gateRes] = await Promise.all([
        api.get('/dock/schedule', { params }),
        api.get('/dock/inbound-etas', { params }).catch(() => ({ data: [] })),
        api.get('/dock/gate-queue', { params }).catch(() => ({ data: null })),
      ]);
      setAppointments(apptRes.data?.appointments || apptRes.data || []);
      setInboundEtas(etaRes.data?.shipments || etaRes.data || []);
      setGateQueue(gateRes.data || null);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to fetch dock schedule');
      setAppointments([]);
    } finally {
      setLoading(false);
    }
  }, [selectedFacility, selectedDate]);

  useEffect(() => {
    fetchFacilities();
  }, [fetchFacilities]);

  useEffect(() => {
    if (selectedFacility) {
      fetchAppointments();
    }
  }, [fetchAppointments, selectedFacility]);

  const doors = useMemo(() => {
    const doorSet = new Set();
    appointments.forEach((appt) => {
      if (appt.door) doorSet.add(appt.door);
    });
    return Array.from(doorSet).sort((a, b) => {
      const numA = parseInt(String(a).replace(/\D/g, ''), 10);
      const numB = parseInt(String(b).replace(/\D/g, ''), 10);
      if (!isNaN(numA) && !isNaN(numB)) return numA - numB;
      return String(a).localeCompare(String(b));
    });
  }, [appointments]);

  const summary = useMemo(() => {
    if (appointments.length === 0) return null;
    const totalAppts = appointments.length;
    const dwellTimes = appointments.map((a) => a.dwell_minutes).filter((v) => v != null);
    const avgDwell = dwellTimes.length > 0
      ? Math.round(dwellTimes.reduce((s, v) => s + v, 0) / dwellTimes.length)
      : null;
    const detentionRisk = appointments.filter(
      (a) => a.dwell_minutes != null && a.free_time != null && a.dwell_minutes > a.free_time
    ).length;

    // Door utilization: hours used / total gantt hours across all doors
    let utilization = null;
    if (doors.length > 0) {
      let totalUsedMinutes = 0;
      appointments.forEach((appt) => {
        if (appt.start_hour != null && appt.end_hour != null) {
          totalUsedMinutes += (appt.end_hour - appt.start_hour) * 60;
        } else if (appt.duration_hours != null) {
          totalUsedMinutes += appt.duration_hours * 60;
        }
      });
      const totalAvailableMinutes = doors.length * GANTT_TOTAL_HOURS * 60;
      utilization = totalAvailableMinutes > 0
        ? ((totalUsedMinutes / totalAvailableMinutes) * 100)
        : null;
    }

    // Appointment compliance: on-time arrivals / total scheduled
    const scheduledCount = appointments.filter((a) => a.scheduled_arrival).length;
    const onTimeCount = appointments.filter((a) => a.arrived_on_time === true).length;
    const complianceRate = scheduledCount > 0 ? ((onTimeCount / scheduledCount) * 100) : null;

    return { totalAppts, utilization, avgDwell, detentionRisk, complianceRate };
  }, [appointments, doors]);

  /**
   * Position an appointment bar within the Gantt 6am-6pm window.
   */
  const getApptPosition = (appt) => {
    const start = appt.start_hour ?? GANTT_START_HOUR;
    const end = appt.end_hour ?? (start + (appt.duration_hours ?? 1));
    // Clamp to gantt range
    const clampedStart = Math.max(start, GANTT_START_HOUR);
    const clampedEnd = Math.min(end, GANTT_END_HOUR);
    if (clampedEnd <= clampedStart) return { left: '0%', width: '0%', visible: false };
    const left = `${((clampedStart - GANTT_START_HOUR) / GANTT_TOTAL_HOURS) * 100}%`;
    const width = `${((clampedEnd - clampedStart) / GANTT_TOTAL_HOURS) * 100}%`;
    return { left, width, visible: true };
  };

  const navigateDate = (offset) => {
    setSelectedDate((prev) => {
      const next = new Date(prev);
      next.setDate(next.getDate() + offset);
      return next;
    });
  };

  const goToToday = () => setSelectedDate(new Date());

  const getApptStatusColor = (appt) => {
    const status = appt.appt_status || appt.status || 'SCHEDULED';
    return APPT_STATUS_COLORS[status] || APPT_STATUS_COLORS.SCHEDULED;
  };

  const getApptLabel = (appt) => {
    const scac = appt.carrier_scac || appt.carrier || '';
    const shipmentCount = appt.shipment_count != null ? appt.shipment_count : '';
    if (scac && shipmentCount) return `${scac} | ${shipmentCount} items`;
    if (scac) return scac;
    return appt.shipment_id || '';
  };

  return (
    <div className="p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Calendar className="h-5 w-5 text-gray-700" />
          <h1 className="text-xl font-semibold text-gray-900">Dock Schedule</h1>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => navigateDate(-1)}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button variant="outline" size="sm" onClick={goToToday}>Today</Button>
          <Button variant="outline" size="sm" onClick={() => navigateDate(1)}>
            <ChevronRight className="h-4 w-4" />
          </Button>
          <span className="text-sm font-medium text-gray-700 min-w-[180px] text-center">
            {formatDisplayDate(selectedDate)}
          </span>
          <Button variant="outline" size="sm" onClick={fetchAppointments}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Facility Selector */}
      <div className="flex items-center gap-3">
        <Building className="h-4 w-4 text-gray-500" />
        <select
          value={selectedFacility}
          onChange={(e) => setSelectedFacility(e.target.value)}
          className="text-sm border rounded px-3 py-1.5"
        >
          {facilities.length === 0 && (
            <option value="">No facilities available</option>
          )}
          {facilities.map((f) => (
            <option key={f.id || f.facility_id} value={f.id || f.facility_id}>
              {f.name || f.facility_name || f.id || f.facility_id}
            </option>
          ))}
        </select>
      </div>

      {/* Error */}
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {loading ? (
        <div className="flex items-center justify-center h-64">
          <Spinner className="h-8 w-8" />
          <span className="ml-3 text-sm text-gray-500">Loading schedule...</span>
        </div>
      ) : (
        <div className="flex gap-4">
          {/* Gantt Timeline - Left 2/3 */}
          <div className="flex-[2] min-w-0 space-y-3">
            {/* KPI cards row */}
            <div className="grid grid-cols-5 gap-2">
              <Card>
                <CardContent className="p-3">
                  <div className="flex items-center gap-1 mb-1">
                    <Truck className="h-3 w-3 text-indigo-500" />
                    <span className="text-[10px] text-gray-500">Appointments</span>
                  </div>
                  <div className="text-lg font-bold">{summary ? summary.totalAppts : '\u2014'}</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-3">
                  <div className="flex items-center gap-1 mb-1">
                    <Clock className="h-3 w-3 text-green-500" />
                    <span className="text-[10px] text-gray-500">Door Util %</span>
                  </div>
                  <div className="text-lg font-bold">
                    {summary?.utilization != null ? `${summary.utilization.toFixed(1)}%` : '\u2014'}
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-3">
                  <div className="flex items-center gap-1 mb-1">
                    <Clock className="h-3 w-3 text-amber-500" />
                    <span className="text-[10px] text-gray-500">Avg Dwell</span>
                  </div>
                  <div className="text-lg font-bold">
                    {summary?.avgDwell != null ? `${summary.avgDwell} min` : '\u2014'}
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-3">
                  <div className="flex items-center gap-1 mb-1">
                    <GaugeCircle className="h-3 w-3 text-blue-500" />
                    <span className="text-[10px] text-gray-500">Compliance</span>
                  </div>
                  <div className="text-lg font-bold">
                    {summary?.complianceRate != null ? `${summary.complianceRate.toFixed(1)}%` : '\u2014'}
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-3">
                  <div className="flex items-center gap-1 mb-1">
                    <AlertTriangle className="h-3 w-3 text-red-500" />
                    <span className="text-[10px] text-gray-500">Detention Risk</span>
                  </div>
                  <div className="text-lg font-bold">{summary ? summary.detentionRisk : '\u2014'}</div>
                </CardContent>
              </Card>
            </div>

            {/* Gate Queue Indicator */}
            {gateQueue && gateQueue.trucks_waiting != null && (
              <div className={cn(
                'flex items-center gap-2 p-2 rounded-lg border text-xs',
                gateQueue.trucks_waiting > 5 ? 'bg-red-50 border-red-200 text-red-700'
                  : gateQueue.trucks_waiting > 2 ? 'bg-amber-50 border-amber-200 text-amber-700'
                  : 'bg-green-50 border-green-200 text-green-700'
              )}>
                <Truck className="h-3 w-3" />
                <span className="font-medium">Gate Queue:</span>
                <span>{gateQueue.trucks_waiting} trucks waiting</span>
                {gateQueue.avg_wait_minutes != null && (
                  <span className="ml-2">| Avg wait: {gateQueue.avg_wait_minutes} min</span>
                )}
              </div>
            )}

            {/* Gantt Chart */}
            {appointments.length === 0 && !error ? (
              <Alert>
                <AlertDescription>
                  No dock appointments for {formatDisplayDate(selectedDate)} at the selected facility. Verify appointment data is available.
                </AlertDescription>
              </Alert>
            ) : doors.length > 0 ? (
              <Card>
                <CardContent className="p-3 overflow-x-auto">
                  {/* Time scale header */}
                  <div className="flex mb-1">
                    <div className="w-20 flex-shrink-0" />
                    <div className="flex-1 relative h-5">
                      {TICKS.map((tick, idx) => (
                        <div
                          key={idx}
                          className="absolute top-0 text-center"
                          style={{ left: `${tick.offset * 100}%`, transform: 'translateX(-50%)' }}
                        >
                          {tick.label && (
                            <span className={cn(
                              'text-[9px]',
                              tick.isHour ? 'text-gray-600 font-medium' : 'text-gray-400'
                            )}>
                              {tick.label}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Door rows */}
                  {doors.map((door) => {
                    const doorAppts = appointments.filter((a) => a.door === door);
                    return (
                      <div key={door} className="flex items-center h-10 border-t border-gray-100">
                        <div className="w-20 flex-shrink-0 text-xs font-medium text-gray-600 pr-2 truncate">
                          {door}
                        </div>
                        <div className="flex-1 relative h-full bg-gray-50 rounded">
                          {/* 30-min grid lines */}
                          {TICKS.map((tick, idx) => (
                            <div
                              key={idx}
                              className={cn(
                                'absolute top-0 bottom-0',
                                tick.isHour ? 'border-l border-gray-200' : 'border-l border-gray-100'
                              )}
                              style={{ left: `${tick.offset * 100}%` }}
                            />
                          ))}
                          {/* Appointment bars */}
                          {doorAppts.map((appt, idx) => {
                            const pos = getApptPosition(appt);
                            if (!pos.visible) return null;
                            return (
                              <div
                                key={appt.id || idx}
                                className={cn(
                                  'absolute top-1 bottom-1 rounded border text-[10px] px-1 truncate flex items-center',
                                  getApptStatusColor(appt)
                                )}
                                style={{ left: pos.left, width: pos.width }}
                                title={`${getApptLabel(appt)} (${appt.appt_status || appt.status || 'SCHEDULED'})`}
                              >
                                {getApptLabel(appt)}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}

                  {/* Legend */}
                  <div className="flex flex-wrap items-center gap-3 mt-3 pt-2 border-t border-gray-100">
                    {Object.entries(APPT_STATUS_COLORS).map(([status, colorCls]) => (
                      <div key={status} className="flex items-center gap-1 text-[10px]">
                        <div className={cn('w-3 h-3 rounded border', colorCls.split(' ').slice(0, 2).join(' '))} />
                        <span>{status.replace('_', ' ')}</span>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ) : null}
          </div>

          {/* Live ETA Feed Panel - Right 1/3 */}
          <div className="flex-1 space-y-3">
            <Card>
              <CardHeader className="pb-2 pt-3 px-4">
                <CardTitle className="text-sm font-semibold">Inbound ETA Feed</CardTitle>
              </CardHeader>
              <CardContent className="p-3 pt-0">
                {inboundEtas.length === 0 ? (
                  <div className="text-xs text-gray-400 py-4 text-center">
                    No inbound shipments with ETA data available.
                  </div>
                ) : (
                  <div className="space-y-2 max-h-[400px] overflow-y-auto">
                    {inboundEtas.map((shipment, idx) => {
                      const isLate = shipment.predicted_arrival && shipment.scheduled_arrival
                        && new Date(shipment.predicted_arrival) > new Date(shipment.scheduled_arrival);
                      return (
                        <div
                          key={shipment.shipment_id || idx}
                          className={cn(
                            'p-2 rounded border text-xs space-y-1',
                            isLate ? 'bg-red-50 border-red-200' : 'bg-white border-gray-200'
                          )}
                        >
                          <div className="flex justify-between items-center">
                            <span className="font-medium truncate">
                              {shipment.shipment_id || '\u2014'}
                            </span>
                            <span className="text-gray-400">
                              {shipment.carrier_scac || shipment.carrier || '\u2014'}
                            </span>
                          </div>
                          <div className="flex justify-between text-[10px]">
                            <span className="text-gray-500">
                              Sched: {formatTime(shipment.scheduled_arrival)}
                            </span>
                            <span className={cn(isLate ? 'text-red-600 font-medium' : 'text-green-600')}>
                              Pred: {formatTime(shipment.predicted_arrival)}
                            </span>
                          </div>
                          {shipment.variance_minutes != null && (
                            <div className={cn(
                              'text-[10px]',
                              shipment.variance_minutes > 0 ? 'text-red-500' : 'text-green-500'
                            )}>
                              {shipment.variance_minutes > 0 ? '+' : ''}{shipment.variance_minutes} min
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
};

export default DockSchedule;
