/**
 * Workforce Planning — Shift planning, labor availability, skill matrix, and overtime tracking.
 *
 * Sub-processes:
 *   - Shift calendar management (1/2/3 shifts per work center)
 *   - Labor availability by skill and work center
 *   - Overtime tracking and cost analysis
 *   - Skill matrix (worker × capability)
 *   - Headcount planning vs capacity demand
 */

import React, { useState, useEffect, useMemo } from 'react';
import {
  Card, CardContent, CardHeader, CardTitle, Button, Badge, Alert,
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell, Spinner,
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from '../../components/common';
import {
  Users, RefreshCw, Clock, Calendar, AlertTriangle,
  TrendingUp, DollarSign, UserCheck,
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  LineChart, Line, Legend, AreaChart, Area,
} from 'recharts';
import { useActiveConfig } from '../../contexts/ActiveConfigContext';

const SHIFT_PATTERNS = [
  { id: '1x8', label: '1 × 8h', hours: 8, color: '#10b981' },
  { id: '2x8', label: '2 × 8h', hours: 16, color: '#3b82f6' },
  { id: '3x8', label: '3 × 8h', hours: 24, color: '#8b5cf6' },
  { id: '2x12', label: '2 × 12h', hours: 24, color: '#f59e0b' },
];

const SKILLS = ['Assembly', 'Welding', 'CNC', 'Painting', 'Testing', 'Packaging', 'Maintenance', 'Forklift'];

export default function WorkforcePlanning() {
  const { effectiveConfigId } = useActiveConfig();
  const [loading, setLoading] = useState(false);
  const [view, setView] = useState('overview'); // overview | shifts | skills | overtime

  // Generate synthetic workforce data
  const [workCenters] = useState(() =>
    Array.from({ length: 8 }, (_, i) => {
      const shiftPattern = SHIFT_PATTERNS[i % 4];
      const headcount = 5 + Math.floor(Math.random() * 25);
      const required = Math.floor(headcount * (0.7 + Math.random() * 0.5));
      return {
        id: `WC-${String(i + 1).padStart(2, '0')}`,
        name: ['Assembly Line A', 'CNC Shop', 'Paint Booth', 'Packaging',
          'Weld Station', 'Test Lab', 'Surface Treat', 'Final Assembly'][i],
        site: `Plant ${1 + (i % 3)}`,
        shift_pattern: shiftPattern,
        headcount,
        required_headcount: required,
        available_hours: headcount * shiftPattern.hours * 5,
        overtime_hours: Math.round(Math.random() * headcount * 4),
        overtime_cost: 0,
        absenteeism: Math.round(2 + Math.random() * 8),
        skills: SKILLS.slice(0, 3 + Math.floor(Math.random() * 5)),
      };
    }).map(wc => ({
      ...wc,
      overtime_cost: wc.overtime_hours * (45 + Math.random() * 30),
      gap: wc.required_headcount - wc.headcount,
    }))
  );

  // Skill matrix data
  const skillMatrix = useMemo(() => {
    const workers = [];
    workCenters.forEach(wc => {
      for (let w = 0; w < Math.min(wc.headcount, 5); w++) {
        const skills = {};
        SKILLS.forEach(s => {
          skills[s] = wc.skills.includes(s) ? (Math.random() > 0.3 ? (Math.random() > 0.5 ? 3 : 2) : 1) : 0;
        });
        workers.push({
          id: `${wc.id}-W${w + 1}`,
          name: `Worker ${wc.id.slice(-2)}-${w + 1}`,
          work_center: wc.name,
          ...skills,
        });
      }
    });
    return workers;
  }, [workCenters]);

  // Weekly overtime trend
  const overtimeTrend = useMemo(() =>
    Array.from({ length: 12 }, (_, w) => ({
      week: `W${w + 1}`,
      overtime_hours: Math.round(workCenters.reduce((s, wc) => s + wc.overtime_hours, 0) * (0.7 + Math.random() * 0.6)),
      regular_hours: Math.round(workCenters.reduce((s, wc) => s + wc.available_hours, 0) * (0.85 + Math.random() * 0.15)),
      overtime_cost: Math.round(workCenters.reduce((s, wc) => s + wc.overtime_cost, 0) * (0.7 + Math.random() * 0.6)),
    })),
  [workCenters]);

  const summary = useMemo(() => ({
    total_headcount: workCenters.reduce((s, wc) => s + wc.headcount, 0),
    total_required: workCenters.reduce((s, wc) => s + wc.required_headcount, 0),
    total_overtime: Math.round(workCenters.reduce((s, wc) => s + wc.overtime_hours, 0)),
    total_overtime_cost: Math.round(workCenters.reduce((s, wc) => s + wc.overtime_cost, 0)),
    avg_absenteeism: Math.round(workCenters.reduce((s, wc) => s + wc.absenteeism, 0) / workCenters.length),
    understaffed: workCenters.filter(wc => wc.gap > 0).length,
  }), [workCenters]);

  return (
    <div className="space-y-6">
      {/* Summary */}
      <div className="grid grid-cols-6 gap-3">
        <Card>
          <CardContent className="pt-3 text-center">
            <Users className="h-4 w-4 mx-auto mb-1 text-blue-500" />
            <div className="text-lg font-bold">{summary.total_headcount}</div>
            <div className="text-[10px] text-muted-foreground">Total HC</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-3 text-center">
            <UserCheck className="h-4 w-4 mx-auto mb-1 text-green-500" />
            <div className="text-lg font-bold">{summary.total_required}</div>
            <div className="text-[10px] text-muted-foreground">Required HC</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-3 text-center">
            <Clock className="h-4 w-4 mx-auto mb-1 text-amber-500" />
            <div className="text-lg font-bold">{summary.total_overtime}h</div>
            <div className="text-[10px] text-muted-foreground">OT Hours/Wk</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-3 text-center">
            <DollarSign className="h-4 w-4 mx-auto mb-1 text-red-500" />
            <div className="text-lg font-bold">${(summary.total_overtime_cost / 1000).toFixed(1)}K</div>
            <div className="text-[10px] text-muted-foreground">OT Cost/Wk</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-3 text-center">
            <AlertTriangle className="h-4 w-4 mx-auto mb-1 text-amber-500" />
            <div className="text-lg font-bold">{summary.avg_absenteeism}%</div>
            <div className="text-[10px] text-muted-foreground">Absenteeism</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-3 text-center">
            <Users className="h-4 w-4 mx-auto mb-1 text-red-500" />
            <div className="text-lg font-bold">{summary.understaffed}</div>
            <div className="text-[10px] text-muted-foreground">Understaffed</div>
          </CardContent>
        </Card>
      </div>

      {/* View selector */}
      <div className="flex items-center gap-2">
        <Select value={view} onValueChange={setView}>
          <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="overview">Headcount Overview</SelectItem>
            <SelectItem value="shifts">Shift Patterns</SelectItem>
            <SelectItem value="skills">Skill Matrix</SelectItem>
            <SelectItem value="overtime">Overtime Analysis</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Headcount Overview */}
      {view === 'overview' && (
        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle className="text-sm">Headcount: Available vs Required</CardTitle></CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={workCenters}>
                  <XAxis dataKey="name" tick={{ fontSize: 9 }} angle={-30} textAnchor="end" height={60} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="headcount" name="Available" fill="#3b82f6" fillOpacity={0.7} radius={[2, 2, 0, 0]} />
                  <Bar dataKey="required_headcount" name="Required" fill="#ef4444" fillOpacity={0.5} radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Work Center</TableHead>
                    <TableHead>Site</TableHead>
                    <TableHead>Shift</TableHead>
                    <TableHead className="text-right">Available</TableHead>
                    <TableHead className="text-right">Required</TableHead>
                    <TableHead className="text-right">Gap</TableHead>
                    <TableHead className="text-right">Absent %</TableHead>
                    <TableHead>Skills</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {workCenters.map(wc => (
                    <TableRow key={wc.id}>
                      <TableCell className="font-medium">{wc.name}</TableCell>
                      <TableCell>{wc.site}</TableCell>
                      <TableCell><Badge variant="outline" className="text-[10px]">{wc.shift_pattern.label}</Badge></TableCell>
                      <TableCell className="text-right tabular-nums">{wc.headcount}</TableCell>
                      <TableCell className="text-right tabular-nums">{wc.required_headcount}</TableCell>
                      <TableCell className="text-right">
                        <Badge variant={wc.gap > 0 ? 'destructive' : wc.gap === 0 ? 'secondary' : 'success'}>
                          {wc.gap > 0 ? `−${wc.gap}` : wc.gap === 0 ? '0' : `+${Math.abs(wc.gap)}`}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{wc.absenteeism}%</TableCell>
                      <TableCell>
                        <div className="flex gap-0.5 flex-wrap">
                          {wc.skills.slice(0, 4).map(s => (
                            <Badge key={s} variant="outline" className="text-[9px] px-1">{s}</Badge>
                          ))}
                          {wc.skills.length > 4 && <Badge variant="outline" className="text-[9px] px-1">+{wc.skills.length - 4}</Badge>}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Shift Patterns */}
      {view === 'shifts' && (
        <Card>
          <CardHeader><CardTitle className="text-sm">Shift Pattern Distribution</CardTitle></CardHeader>
          <CardContent>
            <div className="grid grid-cols-4 gap-4 mb-6">
              {SHIFT_PATTERNS.map(sp => {
                const count = workCenters.filter(wc => wc.shift_pattern.id === sp.id).length;
                return (
                  <Card key={sp.id} className="text-center">
                    <CardContent className="pt-4">
                      <div className="w-4 h-4 rounded-full mx-auto mb-2" style={{ backgroundColor: sp.color }} />
                      <div className="text-xl font-bold">{count}</div>
                      <div className="text-sm font-medium">{sp.label}</div>
                      <div className="text-xs text-muted-foreground">{sp.hours}h/day capacity</div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>

            {/* Weekly hours by shift */}
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={workCenters}>
                <XAxis dataKey="name" tick={{ fontSize: 9 }} angle={-20} textAnchor="end" height={50} />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip />
                <Bar dataKey="available_hours" name="Available Hrs/Wk" radius={[3, 3, 0, 0]}>
                  {workCenters.map((wc, i) => (
                    <Cell key={i} fill={wc.shift_pattern.color} fillOpacity={0.7} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* Skill Matrix */}
      {view === 'skills' && (
        <Card>
          <CardHeader><CardTitle className="text-sm">Skill Matrix (0=None, 1=Basic, 2=Proficient, 3=Expert)</CardTitle></CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Worker</TableHead>
                    <TableHead>Center</TableHead>
                    {SKILLS.map(s => <TableHead key={s} className="text-center text-[10px]">{s}</TableHead>)}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {skillMatrix.slice(0, 30).map(w => (
                    <TableRow key={w.id}>
                      <TableCell className="font-medium text-xs">{w.name}</TableCell>
                      <TableCell className="text-xs">{w.work_center}</TableCell>
                      {SKILLS.map(s => {
                        const level = w[s];
                        const bg = level === 3 ? 'bg-green-100 text-green-800' :
                                   level === 2 ? 'bg-blue-100 text-blue-800' :
                                   level === 1 ? 'bg-amber-100 text-amber-800' : 'bg-gray-50 text-gray-300';
                        return (
                          <TableCell key={s} className="text-center">
                            <span className={`inline-block w-6 h-5 text-[10px] font-bold rounded ${bg} leading-5`}>
                              {level || '—'}
                            </span>
                          </TableCell>
                        );
                      })}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Overtime Analysis */}
      {view === 'overtime' && (
        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle className="text-sm">Weekly Overtime Trend</CardTitle></CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={250}>
                <AreaChart data={overtimeTrend}>
                  <XAxis dataKey="week" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip />
                  <Legend />
                  <Area type="monotone" dataKey="regular_hours" name="Regular Hours" fill="#3b82f6" fillOpacity={0.15} stroke="#3b82f6" />
                  <Area type="monotone" dataKey="overtime_hours" name="OT Hours" fill="#ef4444" fillOpacity={0.3} stroke="#ef4444" />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="text-sm">Overtime by Work Center</CardTitle></CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={workCenters.sort((a, b) => b.overtime_hours - a.overtime_hours)}>
                  <XAxis dataKey="name" tick={{ fontSize: 9 }} angle={-20} textAnchor="end" height={50} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip formatter={(v, name) => [name === 'overtime_cost' ? `$${v.toFixed(0)}` : `${v}h`, name === 'overtime_cost' ? 'Cost' : 'Hours']} />
                  <Bar dataKey="overtime_hours" name="OT Hours" fill="#ef4444" fillOpacity={0.7} radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
