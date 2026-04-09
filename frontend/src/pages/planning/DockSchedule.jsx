import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { api } from '../../services/api';
import { cn } from '../../lib/utils/cn';
import {
  Card, CardContent, CardHeader, CardTitle,
  Badge, Button, Spinner, Alert, AlertDescription,
} from '../../components/common';
import {
  Calendar, ChevronLeft, ChevronRight, Clock, Truck,
  AlertTriangle, RefreshCw, Building,
} from 'lucide-react';

const HOURS = Array.from({ length: 24 }, (_, i) => i);

const APPT_COLORS = {
  PICKUP: 'bg-blue-400 border-blue-600 text-white',
  DELIVERY: 'bg-emerald-400 border-emerald-600 text-white',
  EMPTY: 'bg-gray-300 border-gray-400 text-gray-700',
};

const formatDateISO = (date) => date.toISOString().split('T')[0];

const formatDisplayDate = (date) =>
  date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });

const DockSchedule = () => {
  const [appointments, setAppointments] = useState([]);
  const [facilities, setFacilities] = useState([]);
  const [selectedFacility, setSelectedFacility] = useState('');
  const [selectedDate, setSelectedDate] = useState(new Date());
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
      const response = await api.get('/dock/schedule', {
        params: {
          facility_id: selectedFacility,
          date: formatDateISO(selectedDate),
        },
      });
      setAppointments(response.data?.appointments || response.data || []);
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

    // Door utilization: hours used / total hours across all doors
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
      const totalAvailableMinutes = doors.length * 24 * 60;
      utilization = totalAvailableMinutes > 0
        ? ((totalUsedMinutes / totalAvailableMinutes) * 100)
        : null;
    }

    return { totalAppts, utilization, avgDwell, detentionRisk };
  }, [appointments, doors]);

  const getApptPosition = (appt) => {
    const start = appt.start_hour ?? 0;
    const end = appt.end_hour ?? (start + (appt.duration_hours ?? 1));
    const left = `${(start / 24) * 100}%`;
    const width = `${((end - start) / 24) * 100}%`;
    return { left, width };
  };

  const navigateDate = (offset) => {
    setSelectedDate((prev) => {
      const next = new Date(prev);
      next.setDate(next.getDate() + offset);
      return next;
    });
  };

  const goToToday = () => setSelectedDate(new Date());

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
          {/* Timeline - Left 2/3 */}
          <div className="flex-[2] min-w-0">
            {appointments.length === 0 && !error ? (
              <Alert>
                <AlertDescription>
                  No dock appointments for {formatDisplayDate(selectedDate)} at the selected facility. Verify appointment data is available.
                </AlertDescription>
              </Alert>
            ) : doors.length > 0 ? (
              <Card>
                <CardContent className="p-3 overflow-x-auto">
                  {/* Hour headers */}
                  <div className="flex mb-1">
                    <div className="w-20 flex-shrink-0" />
                    <div className="flex-1 flex">
                      {HOURS.map((h) => (
                        <div
                          key={h}
                          className="flex-1 text-center text-[10px] text-gray-400 border-l border-gray-100"
                        >
                          {String(h).padStart(2, '0')}
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
                          {/* Hour grid lines */}
                          {HOURS.map((h) => (
                            <div
                              key={h}
                              className="absolute top-0 bottom-0 border-l border-gray-100"
                              style={{ left: `${(h / 24) * 100}%` }}
                            />
                          ))}
                          {/* Appointment bars */}
                          {doorAppts.map((appt, idx) => {
                            const pos = getApptPosition(appt);
                            const type = appt.type || 'EMPTY';
                            return (
                              <div
                                key={appt.id || idx}
                                className={cn(
                                  'absolute top-1 bottom-1 rounded border text-[10px] px-1 truncate flex items-center',
                                  APPT_COLORS[type] || APPT_COLORS.EMPTY
                                )}
                                style={{ left: pos.left, width: pos.width }}
                                title={`${appt.carrier || ''} ${appt.shipment_id || ''} (${type})`}
                              >
                                {appt.carrier || ''} {appt.shipment_id || ''}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}
                  {/* Legend */}
                  <div className="flex items-center gap-4 mt-3 pt-2 border-t border-gray-100">
                    <div className="flex items-center gap-1 text-[10px]">
                      <div className="w-3 h-3 rounded bg-blue-400 border border-blue-600" />
                      <span>Pickup</span>
                    </div>
                    <div className="flex items-center gap-1 text-[10px]">
                      <div className="w-3 h-3 rounded bg-emerald-400 border border-emerald-600" />
                      <span>Delivery</span>
                    </div>
                    <div className="flex items-center gap-1 text-[10px]">
                      <div className="w-3 h-3 rounded bg-gray-300 border border-gray-400" />
                      <span>Empty</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ) : null}
          </div>

          {/* Summary - Right 1/3 */}
          <div className="flex-1 space-y-3">
            {summary ? (
              <>
                <Card>
                  <CardContent className="p-4">
                    <div className="flex items-center gap-2 mb-1">
                      <Truck className="h-4 w-4 text-indigo-500" />
                      <span className="text-xs text-gray-500">Appointments Today</span>
                    </div>
                    <div className="text-2xl font-bold">{summary.totalAppts}</div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-4">
                    <div className="flex items-center gap-2 mb-1">
                      <Clock className="h-4 w-4 text-green-500" />
                      <span className="text-xs text-gray-500">Door Utilization %</span>
                    </div>
                    <div className="text-2xl font-bold">
                      {summary.utilization != null ? `${summary.utilization.toFixed(1)}%` : '\u2014'}
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-4">
                    <div className="flex items-center gap-2 mb-1">
                      <Clock className="h-4 w-4 text-amber-500" />
                      <span className="text-xs text-gray-500">Avg Dwell Time</span>
                    </div>
                    <div className="text-2xl font-bold">
                      {summary.avgDwell != null ? `${summary.avgDwell} min` : '\u2014'}
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-4">
                    <div className="flex items-center gap-2 mb-1">
                      <AlertTriangle className="h-4 w-4 text-red-500" />
                      <span className="text-xs text-gray-500">Detention Risk</span>
                    </div>
                    <div className="text-2xl font-bold">{summary.detentionRisk}</div>
                  </CardContent>
                </Card>
              </>
            ) : (
              <Alert>
                <AlertDescription>
                  No appointment data available to calculate summary metrics.
                </AlertDescription>
              </Alert>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default DockSchedule;
