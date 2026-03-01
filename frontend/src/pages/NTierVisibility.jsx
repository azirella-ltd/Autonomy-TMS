/**
 * N-Tier Visibility Dashboard
 *
 * AWS SC-inspired multi-tier supply chain visibility interface.
 * Provides inventory flow visualization, capacity analysis, and risk assessment
 * across all tiers of the supply chain network.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Alert,
  AlertDescription,
  Badge,
  Card,
  CardContent,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '../components/common';
import {
  Eye,
  Factory,
  Truck,
  Store,
  Package,
  ArrowRight,
  ArrowDown,
  AlertTriangle,
  CheckCircle,
  TrendingUp,
  TrendingDown,
  Minus,
  Shield,
  Zap,
  Clock,
  BarChart3,
  Activity,
  RefreshCw,
} from 'lucide-react';
import api from '../services/api';

// --- Mock Data Generators ---

const generateTiers = () => [
  {
    id: 'tier-1',
    name: 'Tier 1 - Factory',
    siteType: 'manufacturer',
    icon: 'factory',
    status: 'operational',
    inventory: { current: 450, min: 200, max: 600, target: 400, unit: 'units' },
    capacity: { utilization: 85, planned: 92, available: 100 },
    leadTime: { current: '4 weeks', average: '3.8 weeks', trend: 'stable' },
    throughput: { daily: 120, weekly: 840 },
    qualityRate: 98.2,
    onTimeDelivery: 94.5,
  },
  {
    id: 'tier-2',
    name: 'Tier 2 - Distributor',
    siteType: 'distributor',
    icon: 'truck',
    status: 'operational',
    inventory: { current: 320, min: 150, max: 500, target: 300, unit: 'units' },
    capacity: { utilization: 72, planned: 78, available: 100 },
    leadTime: { current: '2 weeks', average: '1.9 weeks', trend: 'improving' },
    throughput: { daily: 95, weekly: 665 },
    qualityRate: 99.1,
    onTimeDelivery: 96.8,
  },
  {
    id: 'tier-3',
    name: 'Tier 3 - Wholesaler',
    siteType: 'wholesaler',
    icon: 'package',
    status: 'warning',
    inventory: { current: 180, min: 100, max: 350, target: 250, unit: 'units' },
    capacity: { utilization: 91, planned: 88, available: 100 },
    leadTime: { current: '1 week', average: '0.9 weeks', trend: 'degrading' },
    throughput: { daily: 68, weekly: 476 },
    qualityRate: 97.8,
    onTimeDelivery: 89.3,
  },
  {
    id: 'tier-4',
    name: 'Tier 4 - Retailer',
    siteType: 'retailer',
    icon: 'store',
    status: 'operational',
    inventory: { current: 85, min: 30, max: 150, target: 80, unit: 'units' },
    capacity: { utilization: 68, planned: 75, available: 100 },
    leadTime: { current: '2 days', average: '1.8 days', trend: 'stable' },
    throughput: { daily: 42, weekly: 294 },
    qualityRate: 99.5,
    onTimeDelivery: 97.2,
  },
];

const generateFlowData = () => [
  { from: 'Tier 1 - Factory', to: 'Tier 2 - Distributor', volume: 840, inTransit: 120, avgTransitDays: 5, status: 'normal' },
  { from: 'Tier 2 - Distributor', to: 'Tier 3 - Wholesaler', volume: 665, inTransit: 95, avgTransitDays: 3, status: 'constrained' },
  { from: 'Tier 3 - Wholesaler', to: 'Tier 4 - Retailer', volume: 476, inTransit: 68, avgTransitDays: 1, status: 'normal' },
];

const generateRiskData = () => [
  {
    tier: 'Tier 1 - Factory',
    overallRisk: 'low',
    riskScore: 22,
    risks: [
      { category: 'Supply Continuity', level: 'low', score: 15, detail: 'Multiple raw material suppliers with backup contracts' },
      { category: 'Capacity', level: 'medium', score: 35, detail: 'Utilization at 85% — limited headroom for demand spikes' },
      { category: 'Quality', level: 'low', score: 8, detail: 'Quality rate at 98.2%, consistent with historical average' },
      { category: 'Lead Time', level: 'low', score: 12, detail: 'Lead times stable at 4 weeks, within SLA' },
      { category: 'Financial', level: 'low', score: 18, detail: 'Strong financial position, low payment risk' },
    ],
    mitigations: [
      { action: 'Schedule preventive maintenance for Line 3', priority: 'medium', dueDate: '2026-03-15' },
      { action: 'Negotiate capacity buffer with contract manufacturer', priority: 'low', dueDate: '2026-04-01' },
    ],
  },
  {
    tier: 'Tier 2 - Distributor',
    overallRisk: 'low',
    riskScore: 18,
    risks: [
      { category: 'Supply Continuity', level: 'low', score: 12, detail: 'Single-source from Factory tier — moderate concentration' },
      { category: 'Capacity', level: 'low', score: 15, detail: 'Utilization at 72%, adequate headroom' },
      { category: 'Quality', level: 'low', score: 5, detail: 'Quality rate at 99.1%, best in network' },
      { category: 'Lead Time', level: 'low', score: 10, detail: 'Lead times improving, currently below average' },
      { category: 'Financial', level: 'low', score: 20, detail: 'Stable operations, normal payment terms' },
    ],
    mitigations: [
      { action: 'Identify secondary distribution partner for redundancy', priority: 'low', dueDate: '2026-05-01' },
    ],
  },
  {
    tier: 'Tier 3 - Wholesaler',
    overallRisk: 'high',
    riskScore: 62,
    risks: [
      { category: 'Supply Continuity', level: 'medium', score: 45, detail: 'Inventory 28% below target, replenishment rate insufficient' },
      { category: 'Capacity', level: 'high', score: 78, detail: 'Utilization at 91% — near saturation, bottleneck risk' },
      { category: 'Quality', level: 'low', score: 12, detail: 'Quality rate at 97.8%, slightly below target' },
      { category: 'Lead Time', level: 'high', score: 72, detail: 'Lead times degrading, 11% above historical average' },
      { category: 'Financial', level: 'medium', score: 40, detail: 'Cash flow tightening due to increased buffer stock spending' },
    ],
    mitigations: [
      { action: 'Expedite backlog orders from Tier 2', priority: 'high', dueDate: '2026-03-05' },
      { action: 'Activate overflow warehouse capacity', priority: 'high', dueDate: '2026-03-07' },
      { action: 'Review and adjust safety stock parameters', priority: 'medium', dueDate: '2026-03-10' },
      { action: 'Negotiate extended payment terms with suppliers', priority: 'medium', dueDate: '2026-03-15' },
    ],
  },
  {
    tier: 'Tier 4 - Retailer',
    overallRisk: 'medium',
    riskScore: 35,
    risks: [
      { category: 'Supply Continuity', level: 'medium', score: 42, detail: 'Dependent on Tier 3 which is currently constrained' },
      { category: 'Capacity', level: 'low', score: 18, detail: 'Utilization at 68%, well within limits' },
      { category: 'Quality', level: 'low', score: 5, detail: 'Quality rate at 99.5%, excellent' },
      { category: 'Lead Time', level: 'medium', score: 38, detail: 'Risk of lead time increase if Tier 3 bottleneck worsens' },
      { category: 'Financial', level: 'low', score: 15, detail: 'Strong consumer demand, healthy margins' },
    ],
    mitigations: [
      { action: 'Increase safety stock to cover potential Tier 3 delays', priority: 'high', dueDate: '2026-03-08' },
      { action: 'Identify alternate wholesaler for critical SKUs', priority: 'medium', dueDate: '2026-03-20' },
    ],
  },
];

// --- Icon helper ---
const TierIcon = ({ type, className }) => {
  const icons = { factory: Factory, truck: Truck, package: Package, store: Store };
  const Icon = icons[type] || Package;
  return <Icon className={className} />;
};

// --- Sub-components ---

const InventoryFlowTab = ({ tiers, flows }) => {
  const getFlowStatusColor = (status) => {
    if (status === 'constrained') return 'text-amber-600';
    if (status === 'blocked') return 'text-red-600';
    return 'text-green-600';
  };

  return (
    <div className="space-y-6">
      {/* Flow diagram */}
      <Card>
        <CardContent className="pt-6">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Activity className="h-5 w-5 text-primary" />
            Tier-to-Tier Inventory Flow
          </h3>
          <div className="space-y-4">
            {flows.map((flow, idx) => (
              <div key={idx} className="flex items-center gap-4 p-4 bg-muted/30 rounded-lg">
                <div className="flex-1 text-right font-medium">{flow.from}</div>
                <div className="flex flex-col items-center min-w-[180px]">
                  <div className="flex items-center gap-2">
                    <ArrowRight className={`h-5 w-5 ${getFlowStatusColor(flow.status)}`} />
                    <span className="text-sm font-semibold">{flow.volume}/wk</span>
                    <ArrowRight className={`h-5 w-5 ${getFlowStatusColor(flow.status)}`} />
                  </div>
                  <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                    <span>{flow.inTransit} in transit</span>
                    <span>{flow.avgTransitDays}d avg</span>
                    <Badge variant={flow.status === 'constrained' ? 'warning' : 'success'} className="text-xs">
                      {flow.status}
                    </Badge>
                  </div>
                </div>
                <div className="flex-1 font-medium">{flow.to}</div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Inventory levels comparison */}
      <Card>
        <CardContent className="pt-6">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <BarChart3 className="h-5 w-5 text-primary" />
            Inventory Levels by Tier
          </h3>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tier</TableHead>
                <TableHead className="text-right">Current</TableHead>
                <TableHead className="text-right">Target</TableHead>
                <TableHead className="text-right">Min</TableHead>
                <TableHead className="text-right">Max</TableHead>
                <TableHead className="text-right">vs Target</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {tiers.map((tier) => {
                const delta = tier.inventory.current - tier.inventory.target;
                const pct = ((delta / tier.inventory.target) * 100).toFixed(1);
                const isBelow = delta < 0;
                return (
                  <TableRow key={tier.id}>
                    <TableCell className="font-medium flex items-center gap-2">
                      <TierIcon type={tier.icon} className="h-4 w-4" />
                      {tier.name}
                    </TableCell>
                    <TableCell className="text-right font-mono">{tier.inventory.current}</TableCell>
                    <TableCell className="text-right font-mono">{tier.inventory.target}</TableCell>
                    <TableCell className="text-right font-mono text-muted-foreground">{tier.inventory.min}</TableCell>
                    <TableCell className="text-right font-mono text-muted-foreground">{tier.inventory.max}</TableCell>
                    <TableCell className="text-right">
                      <span className={`flex items-center justify-end gap-1 ${isBelow ? 'text-red-600' : 'text-green-600'}`}>
                        {isBelow ? <TrendingDown className="h-3 w-3" /> : <TrendingUp className="h-3 w-3" />}
                        {isBelow ? '' : '+'}{pct}%
                      </span>
                    </TableCell>
                    <TableCell>
                      <Badge variant={isBelow ? 'warning' : 'success'}>
                        {isBelow ? 'Below Target' : 'On Target'}
                      </Badge>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Network summary */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-6 text-center">
            <p className="text-sm text-muted-foreground mb-1">Total Network Inventory</p>
            <p className="text-3xl font-bold">{tiers.reduce((sum, t) => sum + t.inventory.current, 0).toLocaleString()}</p>
            <p className="text-xs text-muted-foreground">units across all tiers</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <p className="text-sm text-muted-foreground mb-1">Total In-Transit</p>
            <p className="text-3xl font-bold">{flows.reduce((sum, f) => sum + f.inTransit, 0).toLocaleString()}</p>
            <p className="text-xs text-muted-foreground">units between tiers</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <p className="text-sm text-muted-foreground mb-1">Weekly Throughput</p>
            <p className="text-3xl font-bold">{tiers.reduce((sum, t) => sum + t.throughput.weekly, 0).toLocaleString()}</p>
            <p className="text-xs text-muted-foreground">units/week total</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <p className="text-sm text-muted-foreground mb-1">Constrained Lanes</p>
            <p className="text-3xl font-bold text-amber-600">{flows.filter((f) => f.status === 'constrained').length}</p>
            <p className="text-xs text-muted-foreground">of {flows.length} active lanes</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

const CapacityAnalysisTab = ({ tiers }) => {
  const getCapacityColor = (util) => {
    if (util >= 90) return 'text-red-600';
    if (util >= 80) return 'text-amber-600';
    return 'text-green-600';
  };

  const getCapacityBg = (util) => {
    if (util >= 90) return 'bg-red-500';
    if (util >= 80) return 'bg-amber-500';
    return 'bg-green-500';
  };

  const bottlenecks = tiers
    .filter((t) => t.capacity.utilization >= 85)
    .sort((a, b) => b.capacity.utilization - a.capacity.utilization);

  return (
    <div className="space-y-6">
      {/* Capacity utilization bars */}
      <Card>
        <CardContent className="pt-6">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <BarChart3 className="h-5 w-5 text-primary" />
            Capacity Utilization by Tier
          </h3>
          <div className="space-y-6">
            {tiers.map((tier) => (
              <div key={tier.id}>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <TierIcon type={tier.icon} className="h-4 w-4" />
                    <span className="font-medium">{tier.name}</span>
                  </div>
                  <span className={`font-bold ${getCapacityColor(tier.capacity.utilization)}`}>
                    {tier.capacity.utilization}%
                  </span>
                </div>
                <div className="w-full bg-muted rounded-full h-4 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${getCapacityBg(tier.capacity.utilization)}`}
                    style={{ width: `${tier.capacity.utilization}%` }}
                  />
                </div>
                <div className="flex justify-between mt-1 text-xs text-muted-foreground">
                  <span>Planned: {tier.capacity.planned}%</span>
                  <span>Available headroom: {tier.capacity.available - tier.capacity.utilization}%</span>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Bottleneck identification */}
      {bottlenecks.length > 0 && (
        <Alert variant="warning" className="mb-2">
          <AlertDescription className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            <strong>{bottlenecks.length} potential bottleneck{bottlenecks.length > 1 ? 's' : ''} detected</strong>
            — tiers operating above 85% capacity utilization.
          </AlertDescription>
        </Alert>
      )}

      {/* Detailed metrics table */}
      <Card>
        <CardContent className="pt-6">
          <h3 className="text-lg font-semibold mb-4">Detailed Capacity Metrics</h3>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tier</TableHead>
                <TableHead className="text-right">Utilization</TableHead>
                <TableHead className="text-right">Daily Throughput</TableHead>
                <TableHead className="text-right">Weekly Throughput</TableHead>
                <TableHead className="text-right">Quality Rate</TableHead>
                <TableHead className="text-right">On-Time Delivery</TableHead>
                <TableHead>Bottleneck</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {tiers.map((tier) => (
                <TableRow key={tier.id}>
                  <TableCell className="font-medium flex items-center gap-2">
                    <TierIcon type={tier.icon} className="h-4 w-4" />
                    {tier.name}
                  </TableCell>
                  <TableCell className={`text-right font-mono ${getCapacityColor(tier.capacity.utilization)}`}>
                    {tier.capacity.utilization}%
                  </TableCell>
                  <TableCell className="text-right font-mono">{tier.throughput.daily}</TableCell>
                  <TableCell className="text-right font-mono">{tier.throughput.weekly}</TableCell>
                  <TableCell className="text-right font-mono">{tier.qualityRate}%</TableCell>
                  <TableCell className="text-right font-mono">{tier.onTimeDelivery}%</TableCell>
                  <TableCell>
                    {tier.capacity.utilization >= 85 ? (
                      <Badge variant="destructive">Yes</Badge>
                    ) : (
                      <Badge variant="success">No</Badge>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Capacity recommendations */}
      <Card>
        <CardContent className="pt-6">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Zap className="h-5 w-5 text-primary" />
            Capacity Optimization Recommendations
          </h3>
          <div className="space-y-3">
            {bottlenecks.map((tier) => (
              <div key={tier.id} className="p-4 bg-muted/30 rounded-lg border-l-4 border-amber-500">
                <div className="flex items-center gap-2 mb-2">
                  <AlertTriangle className="h-4 w-4 text-amber-600" />
                  <span className="font-semibold">{tier.name} — {tier.capacity.utilization}% utilization</span>
                </div>
                <ul className="text-sm text-muted-foreground space-y-1 ml-6 list-disc">
                  {tier.capacity.utilization >= 90 ? (
                    <>
                      <li>Activate overflow capacity or schedule overtime shifts</li>
                      <li>Evaluate subcontracting options for non-critical operations</li>
                      <li>Review and defer non-essential maintenance to off-peak</li>
                    </>
                  ) : (
                    <>
                      <li>Monitor closely — approaching capacity threshold</li>
                      <li>Pre-position buffer inventory downstream to absorb variability</li>
                    </>
                  )}
                </ul>
              </div>
            ))}
            {bottlenecks.length === 0 && (
              <div className="p-4 bg-green-50 rounded-lg flex items-center gap-2">
                <CheckCircle className="h-5 w-5 text-green-600" />
                <span className="text-green-800">All tiers operating within normal capacity limits.</span>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

const RiskAssessmentTab = ({ riskData }) => {
  const getRiskColor = (level) => {
    if (level === 'high') return 'text-red-600';
    if (level === 'medium') return 'text-amber-600';
    return 'text-green-600';
  };

  const getRiskVariant = (level) => {
    if (level === 'high') return 'destructive';
    if (level === 'medium') return 'warning';
    return 'success';
  };

  const getRiskBg = (score) => {
    if (score >= 60) return 'bg-red-500';
    if (score >= 40) return 'bg-amber-500';
    return 'bg-green-500';
  };

  const [expandedTier, setExpandedTier] = useState(null);

  return (
    <div className="space-y-6">
      {/* Risk score overview */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {riskData.map((tier) => (
          <Card
            key={tier.tier}
            className={`cursor-pointer transition-shadow hover:shadow-md ${expandedTier === tier.tier ? 'ring-2 ring-primary' : ''}`}
            onClick={() => setExpandedTier(expandedTier === tier.tier ? null : tier.tier)}
          >
            <CardContent className="pt-6 text-center">
              <p className="text-sm text-muted-foreground mb-2">{tier.tier}</p>
              <div className="relative inline-flex items-center justify-center w-20 h-20 mb-2">
                <svg className="w-20 h-20 transform -rotate-90" viewBox="0 0 36 36">
                  <path
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                    fill="none"
                    stroke="#e5e7eb"
                    strokeWidth="3"
                  />
                  <path
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                    fill="none"
                    stroke={tier.riskScore >= 60 ? '#dc2626' : tier.riskScore >= 40 ? '#d97706' : '#16a34a'}
                    strokeWidth="3"
                    strokeDasharray={`${tier.riskScore}, 100`}
                  />
                </svg>
                <span className={`absolute text-xl font-bold ${getRiskColor(tier.overallRisk)}`}>
                  {tier.riskScore}
                </span>
              </div>
              <Badge variant={getRiskVariant(tier.overallRisk)}>
                {tier.overallRisk.toUpperCase()} RISK
              </Badge>
              <p className="text-xs text-muted-foreground mt-1">{tier.mitigations.length} actions pending</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Expanded tier detail */}
      {expandedTier && (() => {
        const tier = riskData.find((t) => t.tier === expandedTier);
        if (!tier) return null;
        return (
          <Card>
            <CardContent className="pt-6">
              <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <Shield className="h-5 w-5 text-primary" />
                {tier.tier} — Risk Breakdown
              </h3>

              {/* Risk categories */}
              <div className="space-y-4 mb-6">
                {tier.risks.map((risk, idx) => (
                  <div key={idx}>
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-sm">{risk.category}</span>
                        <Badge variant={getRiskVariant(risk.level)} className="text-xs">
                          {risk.level}
                        </Badge>
                      </div>
                      <span className={`text-sm font-mono ${getRiskColor(risk.level)}`}>{risk.score}/100</span>
                    </div>
                    <div className="w-full bg-muted rounded-full h-2 mb-1">
                      <div
                        className={`h-full rounded-full ${getRiskBg(risk.score)}`}
                        style={{ width: `${risk.score}%` }}
                      />
                    </div>
                    <p className="text-xs text-muted-foreground">{risk.detail}</p>
                  </div>
                ))}
              </div>

              {/* Mitigations */}
              <h4 className="font-semibold mb-3 flex items-center gap-2">
                <CheckCircle className="h-4 w-4" />
                Recommended Mitigations
              </h4>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Action</TableHead>
                    <TableHead>Priority</TableHead>
                    <TableHead>Due Date</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {tier.mitigations.map((m, idx) => (
                    <TableRow key={idx}>
                      <TableCell>{m.action}</TableCell>
                      <TableCell>
                        <Badge variant={m.priority === 'high' ? 'destructive' : m.priority === 'medium' ? 'warning' : 'secondary'}>
                          {m.priority}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-mono text-sm">{m.dueDate}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        );
      })()}

      {/* All mitigations summary */}
      <Card>
        <CardContent className="pt-6">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-amber-600" />
            All Pending Mitigations ({riskData.reduce((sum, t) => sum + t.mitigations.length, 0)})
          </h3>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tier</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Priority</TableHead>
                <TableHead>Due Date</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {riskData
                .flatMap((tier) => tier.mitigations.map((m) => ({ ...m, tier: tier.tier })))
                .sort((a, b) => {
                  const pri = { high: 0, medium: 1, low: 2 };
                  return (pri[a.priority] ?? 3) - (pri[b.priority] ?? 3);
                })
                .map((m, idx) => (
                  <TableRow key={idx}>
                    <TableCell className="text-sm text-muted-foreground">{m.tier}</TableCell>
                    <TableCell>{m.action}</TableCell>
                    <TableCell>
                      <Badge variant={m.priority === 'high' ? 'destructive' : m.priority === 'medium' ? 'warning' : 'secondary'}>
                        {m.priority}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-sm">{m.dueDate}</TableCell>
                  </TableRow>
                ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
};

// --- Main Component ---

const NTierVisibility = () => {
  const [currentTab, setCurrentTab] = useState('overview');
  const [tiers, setTiers] = useState([]);
  const [flows, setFlows] = useState([]);
  const [riskData, setRiskData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [tierRes, flowRes, riskRes] = await Promise.allSettled([
        api.get('/api/v1/n-tier/tiers'),
        api.get('/api/v1/n-tier/flows'),
        api.get('/api/v1/n-tier/risks'),
      ]);
      setTiers(tierRes.status === 'fulfilled' ? tierRes.value.data : generateTiers());
      setFlows(flowRes.status === 'fulfilled' ? flowRes.value.data : generateFlowData());
      setRiskData(riskRes.status === 'fulfilled' ? riskRes.value.data : generateRiskData());
    } catch {
      setTiers(generateTiers());
      setFlows(generateFlowData());
      setRiskData(generateRiskData());
    } finally {
      setLoading(false);
      setLastRefresh(new Date());
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const getStatusVariant = (status) => {
    const variants = { operational: 'success', warning: 'warning', critical: 'destructive' };
    return variants[status] || 'secondary';
  };

  const getTrendIcon = (trend) => {
    if (trend === 'improving') return <TrendingUp className="h-3 w-3 text-green-600" />;
    if (trend === 'degrading') return <TrendingDown className="h-3 w-3 text-red-600" />;
    return <Minus className="h-3 w-3 text-muted-foreground" />;
  };

  return (
    <div className="container mx-auto py-8 px-4 max-w-7xl">
      <div className="mb-8 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Eye className="h-10 w-10 text-primary" />
          <div>
            <h1 className="text-3xl font-bold">N-Tier Visibility</h1>
            {lastRefresh && (
              <p className="text-xs text-muted-foreground">
                Last refreshed: {lastRefresh.toLocaleTimeString()}
              </p>
            )}
          </div>
        </div>
        <button
          onClick={loadData}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      <Card className="mb-6">
        <CardContent className="pt-6">
          <p className="text-muted-foreground">
            Gain end-to-end visibility across all tiers of your supply chain network.
            Monitor inventory levels, capacity utilization, and operational status at each tier.
          </p>
        </CardContent>
      </Card>

      <Tabs value={currentTab} onValueChange={setCurrentTab}>
        <TabsList className="mb-6">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="inventory-flow">Inventory Flow</TabsTrigger>
          <TabsTrigger value="capacity">Capacity Analysis</TabsTrigger>
          <TabsTrigger value="risk">Risk Assessment</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {tiers.map((tier, index) => (
              <Card key={tier.id || index}>
                <CardContent className="pt-6">
                  <div className="flex items-center gap-3 mb-4">
                    <TierIcon type={tier.icon} className="h-5 w-5" />
                    <h3 className="text-lg font-semibold">{tier.name}</h3>
                    <Badge variant={getStatusVariant(tier.status)} className="ml-auto">
                      {tier.status.toUpperCase()}
                    </Badge>
                  </div>

                  <div className="space-y-3">
                    <div className="flex justify-between py-2 border-b">
                      <span className="text-muted-foreground">Current Inventory</span>
                      <span>{tier.inventory?.current ?? tier.inventory} {tier.inventory?.unit || 'units'}</span>
                    </div>
                    <div className="flex justify-between py-2 border-b">
                      <span className="text-muted-foreground">Capacity Utilization</span>
                      <span>{tier.capacity?.utilization ?? tier.capacity}%</span>
                    </div>
                    <div className="flex justify-between py-2 border-b">
                      <span className="text-muted-foreground">Average Lead Time</span>
                      <span className="flex items-center gap-1">
                        {tier.leadTime?.current ?? tier.leadTime}
                        {tier.leadTime?.trend && getTrendIcon(tier.leadTime.trend)}
                      </span>
                    </div>
                    <div className="flex justify-between py-2 border-b">
                      <span className="text-muted-foreground">Daily Throughput</span>
                      <span>{tier.throughput?.daily ?? '—'} units/day</span>
                    </div>
                    <div className="flex justify-between py-2">
                      <span className="text-muted-foreground">On-Time Delivery</span>
                      <span>{tier.onTimeDelivery ?? '—'}%</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="mt-8">
            <h2 className="text-xl font-bold mb-4">Supply Chain Health</h2>
            <Card>
              <CardContent className="pt-6">
                <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                  <div>
                    <p className="text-sm text-muted-foreground mb-1">Overall Health Score</p>
                    <p className="text-4xl font-bold text-green-600">87</p>
                    <p className="text-xs text-muted-foreground">Out of 100</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground mb-1">Total Network Inventory</p>
                    <p className="text-4xl font-bold">
                      {tiers.reduce((sum, t) => sum + (t.inventory?.current ?? t.inventory ?? 0), 0).toLocaleString()}
                    </p>
                    <p className="text-xs text-muted-foreground">Units across all tiers</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground mb-1">Average Service Level</p>
                    <p className="text-4xl font-bold text-primary">
                      {tiers.length > 0
                        ? (tiers.reduce((sum, t) => sum + (t.onTimeDelivery ?? 0), 0) / tiers.length).toFixed(1)
                        : '—'}%
                    </p>
                    <p className="text-xs text-muted-foreground">On-time delivery avg</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground mb-1">Avg Quality Rate</p>
                    <p className="text-4xl font-bold text-green-600">
                      {tiers.length > 0
                        ? (tiers.reduce((sum, t) => sum + (t.qualityRate ?? 0), 0) / tiers.length).toFixed(1)
                        : '—'}%
                    </p>
                    <p className="text-xs text-muted-foreground">Across all tiers</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="inventory-flow">
          <InventoryFlowTab tiers={tiers} flows={flows} />
        </TabsContent>

        <TabsContent value="capacity">
          <CapacityAnalysisTab tiers={tiers} />
        </TabsContent>

        <TabsContent value="risk">
          <RiskAssessmentTab riskData={riskData} />
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default NTierVisibility;
