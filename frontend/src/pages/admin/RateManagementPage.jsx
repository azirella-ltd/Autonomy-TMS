/**
 * Rate Management — Contract Rates, Spot Quotes, Rate Cards
 *
 * Data-driven page for freight rate visibility. All data fetched
 * from backend APIs; no hardcoded fallback values.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../../services/api';
import { cn } from '../../lib/utils/cn';
import {
  Card, CardContent, CardHeader, CardTitle,
  Badge, Button, Spinner, Alert, AlertDescription,
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
  Input,
  Accordion, AccordionItem, AccordionTrigger, AccordionContent,
  useToast,
} from '../../components/common';
import {
  DollarSign, TrendingUp, FileText, RefreshCw, Search,
  AlertTriangle, Filter,
} from 'lucide-react';

const TABS = [
  { key: 'contracts', label: 'Contract Rates', icon: FileText },
  { key: 'spots', label: 'Spot Quotes', icon: TrendingUp },
  { key: 'cards', label: 'Rate Cards', icon: DollarSign },
];

function statusBadge(status) {
  if (!status) return 'bg-gray-100 text-gray-600';
  const s = status.toLowerCase();
  if (s === 'active' || s === 'accepted') return 'bg-green-100 text-green-700';
  if (s === 'expired' || s === 'rejected') return 'bg-red-100 text-red-700';
  if (s === 'pending') return 'bg-yellow-100 text-yellow-700';
  return 'bg-gray-100 text-gray-600';
}

const RateManagementPage = () => {
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState('contracts');
  const [rates, setRates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [modeFilter, setModeFilter] = useState('');
  const [carrierFilter, setCarrierFilter] = useState('');

  const endpointMap = { contracts: '/rates/contracts', spots: '/rates/spots', cards: '/rates/cards' };

  const fetchRates = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(endpointMap[activeTab]);
      setRates(Array.isArray(res.data) ? res.data : res.data?.items ?? []);
    } catch (err) {
      const msg = err.response?.status === 404
        ? 'Rate data endpoints not yet configured. Rate management will be available once the backend rate service is deployed.'
        : `Failed to load rates: ${err.message}`;
      setError(msg);
      setRates([]);
    } finally {
      setLoading(false);
    }
  }, [activeTab]);

  useEffect(() => {
    fetchRates();
  }, [fetchRates]);

  const cell = (val) => (val != null ? val : '\u2014');
  const currency = (val) => (val != null ? `$${Number(val).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '\u2014');
  const pct = (val) => (val != null ? `${val}%` : '\u2014');

  const filteredRates = rates.filter((r) => {
    if (searchTerm && !(r.origin?.toLowerCase().includes(searchTerm.toLowerCase()) || r.destination?.toLowerCase().includes(searchTerm.toLowerCase()) || r.lane?.toLowerCase().includes(searchTerm.toLowerCase()))) return false;
    if (modeFilter && r.mode !== modeFilter) return false;
    if (carrierFilter && r.carrier !== carrierFilter) return false;
    return true;
  });

  const uniqueModes = [...new Set(rates.map((r) => r.mode).filter(Boolean))];
  const uniqueCarriers = [...new Set(rates.map((r) => r.carrier).filter(Boolean))];

  // ---- Tab content renderers ----

  const renderContracts = () => {
    if (loading) return <div className="flex justify-center py-12"><Spinner /></div>;
    if (error) return <Alert variant="destructive"><AlertTriangle className="h-4 w-4" /><AlertDescription>{error}</AlertDescription></Alert>;
    if (rates.length === 0) return <Alert><AlertDescription>No rates configured. Contract rates will appear once rate data is synced from your TMS or rate management system.</AlertDescription></Alert>;

    return (
      <div className="space-y-4">
        <div className="flex gap-3 items-center flex-wrap">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search lanes..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-9"
            />
          </div>
          {uniqueModes.length > 0 && (
            <select
              className="border rounded-md px-3 py-2 text-sm bg-background"
              value={modeFilter}
              onChange={(e) => setModeFilter(e.target.value)}
            >
              <option value="">All Modes</option>
              {uniqueModes.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          )}
          {uniqueCarriers.length > 0 && (
            <select
              className="border rounded-md px-3 py-2 text-sm bg-background"
              value={carrierFilter}
              onChange={(e) => setCarrierFilter(e.target.value)}
            >
              <option value="">All Carriers</option>
              {uniqueCarriers.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          )}
        </div>

        {filteredRates.length === 0 ? (
          <Alert><AlertDescription>No rates match the current filters.</AlertDescription></Alert>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Lane</TableHead>
                <TableHead>Mode</TableHead>
                <TableHead>Carrier</TableHead>
                <TableHead className="text-right">Rate ($/load)</TableHead>
                <TableHead>Effective From</TableHead>
                <TableHead>Expires</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredRates.map((r, i) => (
                <TableRow key={r.id ?? i}>
                  <TableCell className="font-medium">{r.lane ?? `${cell(r.origin)} \u2192 ${cell(r.destination)}`}</TableCell>
                  <TableCell>{cell(r.mode)}</TableCell>
                  <TableCell>{cell(r.carrier)}</TableCell>
                  <TableCell className="text-right">{currency(r.rate)}</TableCell>
                  <TableCell>{cell(r.effective_from)}</TableCell>
                  <TableCell>{cell(r.expires)}</TableCell>
                  <TableCell><Badge className={statusBadge(r.status)}>{cell(r.status)}</Badge></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    );
  };

  const renderSpots = () => {
    if (loading) return <div className="flex justify-center py-12"><Spinner /></div>;
    if (error) return <Alert variant="destructive"><AlertTriangle className="h-4 w-4" /><AlertDescription>{error}</AlertDescription></Alert>;
    if (rates.length === 0) return <Alert><AlertDescription>No spot quotes available. Spot quote data will appear once integrated with your spot market sources.</AlertDescription></Alert>;

    return (
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Lane</TableHead>
            <TableHead>Carrier</TableHead>
            <TableHead className="text-right">Quote Rate</TableHead>
            <TableHead className="text-right">Market Rate (DAT)</TableHead>
            <TableHead className="text-right">Premium %</TableHead>
            <TableHead>Quoted At</TableHead>
            <TableHead>Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rates.map((r, i) => (
            <TableRow key={r.id ?? i}>
              <TableCell className="font-medium">{r.lane ?? `${cell(r.origin)} \u2192 ${cell(r.destination)}`}</TableCell>
              <TableCell>{cell(r.carrier)}</TableCell>
              <TableCell className="text-right">{currency(r.quote_rate)}</TableCell>
              <TableCell className="text-right">{currency(r.market_rate)}</TableCell>
              <TableCell className="text-right">{pct(r.premium_pct)}</TableCell>
              <TableCell>{cell(r.quoted_at)}</TableCell>
              <TableCell><Badge className={statusBadge(r.status)}>{cell(r.status)}</Badge></TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    );
  };

  const renderCards = () => {
    if (loading) return <div className="flex justify-center py-12"><Spinner /></div>;
    if (error) return <Alert variant="destructive"><AlertTriangle className="h-4 w-4" /><AlertDescription>{error}</AlertDescription></Alert>;
    if (rates.length === 0) return <Alert><AlertDescription>No rate cards available. Rate card data will appear once carrier rate sheets are imported.</AlertDescription></Alert>;

    const grouped = rates.reduce((acc, r) => {
      const key = r.carrier ?? 'Unknown';
      if (!acc[key]) acc[key] = [];
      acc[key].push(r);
      return acc;
    }, {});

    return (
      <Accordion type="multiple" className="space-y-2">
        {Object.entries(grouped).map(([carrier, items]) => (
          <AccordionItem key={carrier} value={carrier}>
            <AccordionTrigger className="text-sm font-medium">
              {carrier} ({items.length} rate{items.length !== 1 ? 's' : ''})
            </AccordionTrigger>
            <AccordionContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Lane</TableHead>
                    <TableHead>Mode</TableHead>
                    <TableHead className="text-right">Rate</TableHead>
                    <TableHead>Effective</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((r, i) => (
                    <TableRow key={r.id ?? i}>
                      <TableCell>{r.lane ?? `${cell(r.origin)} \u2192 ${cell(r.destination)}`}</TableCell>
                      <TableCell>{cell(r.mode)}</TableCell>
                      <TableCell className="text-right">{currency(r.rate)}</TableCell>
                      <TableCell>{cell(r.effective_from)}</TableCell>
                      <TableCell><Badge className={statusBadge(r.status)}>{cell(r.status)}</Badge></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
    );
  };

  const TAB_CONTENT = { contracts: renderContracts, spots: renderSpots, cards: renderCards };

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Rate Management</h1>
          <p className="text-sm text-muted-foreground mt-1">Contract rates, spot quotes, and rate cards</p>
        </div>
        <Button variant="outline" onClick={fetchRates}>
          <RefreshCw className="h-4 w-4 mr-1" />Refresh
        </Button>
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

export default RateManagementPage;
