/**
 * Carrier Management — Onboarding, Scorecards, Lane Coverage, Contracts
 *
 * Data-driven page for managing carrier relationships. All data fetched
 * from backend APIs; no hardcoded fallback values.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../../services/api';
import { cn } from '@azirella-ltd/autonomy-frontend';
import {
  Card, CardContent, CardHeader, CardTitle,
  Badge, Button, Spinner, Alert, AlertDescription,
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
  Tooltip, TooltipTrigger, TooltipContent, TooltipProvider,
  useToast,
} from '../../components/common';
import {
  Truck, Star, MapPin, FileText, ChevronDown, ChevronUp,
  Plus, RefreshCw, AlertTriangle,
} from 'lucide-react';

const TABS = [
  { key: 'overview', label: 'Overview', icon: Truck },
  { key: 'scorecards', label: 'Scorecards', icon: Star },
  { key: 'coverage', label: 'Lane Coverage', icon: MapPin },
  { key: 'contracts', label: 'Contracts', icon: FileText },
];

const SCORE_THRESHOLDS = { good: 85, warning: 70 };

function scoreBadgeClass(score) {
  if (score == null) return 'bg-gray-100 text-gray-600';
  if (score >= SCORE_THRESHOLDS.good) return 'bg-green-100 text-green-700';
  if (score >= SCORE_THRESHOLDS.warning) return 'bg-yellow-100 text-yellow-700';
  return 'bg-red-100 text-red-700';
}

function statusBadgeClass(status) {
  if (status === 'active') return 'bg-green-100 text-green-700';
  if (status === 'suspended') return 'bg-red-100 text-red-700';
  return 'bg-gray-100 text-gray-600';
}

const CarrierManagementPage = () => {
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState('overview');
  const [carriers, setCarriers] = useState([]);
  const [scorecards, setScorecards] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expandedId, setExpandedId] = useState(null);

  const fetchCarriers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get('/carriers');
      setCarriers(Array.isArray(res.data) ? res.data : res.data?.items ?? []);
    } catch (err) {
      const msg = err.response?.status === 404
        ? 'Carrier endpoints not yet configured for this tenant.'
        : `Failed to load carriers: ${err.message}`;
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchScorecards = useCallback(async () => {
    if (activeTab !== 'scorecards') return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.get('/carriers');
      const list = Array.isArray(res.data) ? res.data : res.data?.items ?? [];
      const cards = await Promise.all(
        list.map(async (c) => {
          try {
            const sc = await api.get(`/carriers/${c.id}/scorecard`);
            return { ...c, scorecard: sc.data };
          } catch {
            return { ...c, scorecard: null };
          }
        })
      );
      setScorecards(cards);
    } catch (err) {
      setError(`Failed to load scorecards: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }, [activeTab]);

  useEffect(() => {
    if (activeTab === 'scorecards') {
      fetchScorecards();
    } else {
      fetchCarriers();
    }
  }, [activeTab, fetchCarriers, fetchScorecards]);

  const cell = (val) => (val != null ? val : '\u2014');
  const pct = (val) => (val != null ? `${val}%` : '\u2014');

  // ---- Tab content renderers ----

  const renderOverview = () => {
    if (loading) return <div className="flex justify-center py-12"><Spinner /></div>;
    if (error) return <Alert variant="destructive"><AlertTriangle className="h-4 w-4" /><AlertDescription>{error}</AlertDescription></Alert>;
    if (carriers.length === 0) return <Alert><AlertDescription>No carriers found. Carrier data is synced from your TMS/ERP system.</AlertDescription></Alert>;

    return (
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>SCAC</TableHead>
            <TableHead>Mode(s)</TableHead>
            <TableHead className="text-right">Active Lanes</TableHead>
            <TableHead className="text-right">OTD %</TableHead>
            <TableHead className="text-right">Acceptance Rate</TableHead>
            <TableHead className="text-right">Score</TableHead>
            <TableHead>Status</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {carriers.map((c) => (
            <React.Fragment key={c.id}>
              <TableRow
                className="cursor-pointer hover:bg-muted/50"
                onClick={() => setExpandedId(expandedId === c.id ? null : c.id)}
              >
                <TableCell className="font-medium">{cell(c.name)}</TableCell>
                <TableCell>{cell(c.scac)}</TableCell>
                <TableCell>{Array.isArray(c.modes) ? c.modes.join(', ') : cell(c.mode)}</TableCell>
                <TableCell className="text-right">{cell(c.active_lanes)}</TableCell>
                <TableCell className="text-right">{pct(c.otd_pct)}</TableCell>
                <TableCell className="text-right">{pct(c.acceptance_rate)}</TableCell>
                <TableCell className="text-right">
                  <Badge className={scoreBadgeClass(c.score)}>{cell(c.score)}</Badge>
                </TableCell>
                <TableCell>
                  <Badge className={statusBadgeClass(c.status)}>{cell(c.status)}</Badge>
                </TableCell>
                <TableCell>
                  {expandedId === c.id ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                </TableCell>
              </TableRow>
              {expandedId === c.id && (
                <TableRow>
                  <TableCell colSpan={9} className="bg-muted/30 px-6 py-4">
                    <div className="grid grid-cols-3 gap-4 text-sm">
                      <div><span className="text-muted-foreground">MC Number:</span> {cell(c.mc_number)}</div>
                      <div><span className="text-muted-foreground">DOT Number:</span> {cell(c.dot_number)}</div>
                      <div><span className="text-muted-foreground">Equipment Types:</span> {Array.isArray(c.equipment_types) ? c.equipment_types.join(', ') : '\u2014'}</div>
                      <div><span className="text-muted-foreground">Insurance Expires:</span> {cell(c.insurance_expiry)}</div>
                      <div><span className="text-muted-foreground">Primary Contact:</span> {cell(c.primary_contact)}</div>
                      <div><span className="text-muted-foreground">Email:</span> {cell(c.email)}</div>
                    </div>
                  </TableCell>
                </TableRow>
              )}
            </React.Fragment>
          ))}
        </TableBody>
      </Table>
    );
  };

  const renderScorecards = () => {
    if (loading) return <div className="flex justify-center py-12"><Spinner /></div>;
    if (error) return <Alert variant="destructive"><AlertTriangle className="h-4 w-4" /><AlertDescription>{error}</AlertDescription></Alert>;
    if (scorecards.length === 0) return <Alert><AlertDescription>No scorecard data available. Scorecards are generated from shipment execution history.</AlertDescription></Alert>;

    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {scorecards.map((c) => {
          const sc = c.scorecard;
          return (
            <Card key={c.id} className={cn('border-l-4', sc ? (sc.overall_score >= SCORE_THRESHOLDS.good ? 'border-l-green-500' : sc.overall_score >= SCORE_THRESHOLDS.warning ? 'border-l-yellow-500' : 'border-l-red-500') : 'border-l-gray-300')}>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">{cell(c.name)}</CardTitle>
              </CardHeader>
              <CardContent>
                {sc ? (
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between"><span className="text-muted-foreground">Overall Score</span><Badge className={scoreBadgeClass(sc.overall_score)}>{sc.overall_score}</Badge></div>
                    <div className="flex justify-between"><span className="text-muted-foreground">On-Time Delivery</span><span>{pct(sc.otd)}</span></div>
                    <div className="flex justify-between"><span className="text-muted-foreground">Damage-Free Rate</span><span>{pct(sc.damage_free_rate)}</span></div>
                    <div className="flex justify-between"><span className="text-muted-foreground">Billing Accuracy</span><span>{pct(sc.billing_accuracy)}</span></div>
                    <div className="flex justify-between"><span className="text-muted-foreground">Responsiveness</span><span>{pct(sc.responsiveness)}</span></div>
                  </div>
                ) : (
                  <Alert><AlertDescription>Scorecard not available for this carrier.</AlertDescription></Alert>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    );
  };

  const renderCoverage = () => {
    if (loading) return <div className="flex justify-center py-12"><Spinner /></div>;
    if (error) return <Alert variant="destructive"><AlertTriangle className="h-4 w-4" /><AlertDescription>{error}</AlertDescription></Alert>;
    if (carriers.length === 0) return <Alert><AlertDescription>No lane coverage data available. Coverage is derived from carrier lane assignments.</AlertDescription></Alert>;

    return (
      <Alert><AlertDescription>Lane coverage visualization will be available once carrier lane data is populated from TMS/ERP extraction.</AlertDescription></Alert>
    );
  };

  const renderContracts = () => {
    if (loading) return <div className="flex justify-center py-12"><Spinner /></div>;
    if (error) return <Alert variant="destructive"><AlertTriangle className="h-4 w-4" /><AlertDescription>{error}</AlertDescription></Alert>;

    return (
      <Alert><AlertDescription>Contract management will be available once rate and contract data is synced from your TMS/ERP system.</AlertDescription></Alert>
    );
  };

  const TAB_CONTENT = { overview: renderOverview, scorecards: renderScorecards, coverage: renderCoverage, contracts: renderContracts };

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Carrier Management</h1>
          <p className="text-sm text-muted-foreground mt-1">Onboarding, scorecards, lane coverage, and contract management</p>
        </div>
        <div className="flex gap-2">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <span>
                  <Button variant="outline" disabled><Plus className="h-4 w-4 mr-1" />Add Carrier</Button>
                </span>
              </TooltipTrigger>
              <TooltipContent>Carriers are synced from TMS/ERP</TooltipContent>
            </Tooltip>
          </TooltipProvider>
          <Button variant="outline" onClick={activeTab === 'scorecards' ? fetchScorecards : fetchCarriers}>
            <RefreshCw className="h-4 w-4 mr-1" />Refresh
          </Button>
        </div>
      </div>

      <div className="flex gap-1 border-b">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setActiveTab(t.key)}
            className={cn(
              'flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 transition-colors',
              activeTab === t.key
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            )}
          >
            <t.icon className="h-4 w-4" />{t.label}
          </button>
        ))}
      </div>

      {TAB_CONTENT[activeTab]?.()}
    </div>
  );
};

export default CarrierManagementPage;
