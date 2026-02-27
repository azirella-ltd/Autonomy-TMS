import React, { useState } from 'react';
import {
  Card,
  CardContent,
  Chip,
  IconButton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  TabsList,
  Tab,
} from '../common';
import {
  Truck,
  CheckCircle2,
  Clock,
  ChevronDown,
  ChevronUp,
  Activity
} from 'lucide-react';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  Legend,
  ResponsiveContainer,
  Area,
  AreaChart
} from 'recharts';
import { cn } from '../../lib/utils/cn';

/**
 * Transfer Order Timeline Visualization
 *
 * Displays Transfer Orders with:
 * - Status timeline (IN_TRANSIT vs RECEIVED)
 * - Shipment routes (source -> destination)
 * - In-transit inventory tracking
 * - Delivery performance metrics
 */
const TransferOrderTimeline = ({ scenarioId, transferOrders, analytics }) => {
  const [activeTab, setActiveTab] = useState('timeline');
  const [expandedRoutes, setExpandedRoutes] = useState({});

  // Group TOs by status
  const tosByStatus = transferOrders.reduce((acc, to) => {
    if (!acc[to.status]) acc[to.status] = [];
    acc[to.status].push(to);
    return acc;
  }, {});

  // Get status variant for Chip
  const getStatusVariant = (status) => {
    switch (status) {
      case 'IN_TRANSIT':
        return 'default';
      case 'RECEIVED':
        return 'success';
      case 'SHIPPED':
        return 'info';
      case 'RELEASED':
        return 'warning';
      default:
        return 'secondary';
    }
  };

  // Get status icon
  const getStatusIcon = (status) => {
    switch (status) {
      case 'IN_TRANSIT':
        return <Truck className="h-3.5 w-3.5" />;
      case 'RECEIVED':
        return <CheckCircle2 className="h-3.5 w-3.5" />;
      default:
        return <Clock className="h-3.5 w-3.5" />;
    }
  };

  // Toggle route expansion
  const toggleRoute = (routeKey) => {
    setExpandedRoutes(prev => ({
      ...prev,
      [routeKey]: !prev[routeKey]
    }));
  };

  // Prepare timeline data (TOs created/received per round)
  const prepareTimelineData = () => {
    if (!analytics || !analytics.timeline) return [];

    return analytics.timeline.timeline.map(round => ({
      round: round.round,
      created: round.tos_created,
      received: round.tos_received,
      quantityCreated: round.quantity_created,
      quantityReceived: round.quantity_received
    }));
  };

  // Prepare route data
  const prepareRouteData = () => {
    if (!analytics || !analytics.route_analysis) return [];

    return analytics.route_analysis.routes.map(route => ({
      ...route,
      routeKey: `${route.source_site_id}-${route.destination_site_id}`
    }));
  };

  // Prepare in-transit data
  const prepareInTransitData = () => {
    if (!analytics || !analytics.in_transit_analysis) return [];

    const bysite = analytics.in_transit_analysis.in_transit_by_site || {};
    return Object.entries(bysite).map(([siteId, qty]) => ({
      site: siteId,
      quantity: qty
    }));
  };

  // Tab: Timeline View
  const renderTimelineView = () => {
    const timelineData = prepareTimelineData();

    return (
      <div>
        <h6 className="text-lg font-semibold mb-4 flex items-center">
          <Activity className="mr-2 h-5 w-5 align-middle" />
          Transfer Order Timeline
        </h6>

        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={timelineData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis
              dataKey="round"
              label={{ value: 'Round', position: 'insideBottom', offset: -5 }}
            />
            <YAxis
              label={{ value: 'Transfer Orders', angle: -90, position: 'insideLeft' }}
            />
            <RechartsTooltip />
            <Legend />
            <Area
              type="monotone"
              dataKey="created"
              stackId="1"
              stroke="#8884d8"
              fill="#8884d8"
              name="TOs Created"
            />
            <Area
              type="monotone"
              dataKey="received"
              stackId="2"
              stroke="#82ca9d"
              fill="#82ca9d"
              name="TOs Received"
            />
          </AreaChart>
        </ResponsiveContainer>

        <div className="mt-6">
          <h6 className="text-sm font-medium mb-2">
            Quantity Timeline
          </h6>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={timelineData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="round" />
              <YAxis />
              <RechartsTooltip />
              <Legend />
              <Line
                type="monotone"
                dataKey="quantityCreated"
                stroke="#8884d8"
                name="Quantity Created"
              />
              <Line
                type="monotone"
                dataKey="quantityReceived"
                stroke="#82ca9d"
                name="Quantity Received"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    );
  };

  // Tab: Route Analysis
  const renderRouteView = () => {
    const routeData = prepareRouteData();

    return (
      <div>
        <h6 className="text-lg font-semibold mb-4">
          Shipment Routes
        </h6>

        <TableContainer className="mt-4">
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Route</TableCell>
                <TableCell className="text-right">TOs</TableCell>
                <TableCell className="text-right">Total Qty</TableCell>
                <TableCell className="text-right">Avg Qty/TO</TableCell>
                <TableCell className="text-right">Avg Lead Time</TableCell>
                <TableCell></TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {routeData.map((route) => (
                <React.Fragment key={route.routeKey}>
                  <TableRow>
                    <TableCell>
                      <span className="text-sm">
                        {route.source_site_id} → {route.destination_site_id}
                      </span>
                    </TableCell>
                    <TableCell className="text-right">{route.to_count}</TableCell>
                    <TableCell className="text-right">
                      {route.total_quantity.toFixed(1)}
                    </TableCell>
                    <TableCell className="text-right">
                      {route.avg_quantity_per_to.toFixed(1)}
                    </TableCell>
                    <TableCell className="text-right">
                      {route.avg_lead_time_days.toFixed(1)} days
                    </TableCell>
                    <TableCell>
                      <IconButton
                        onClick={() => toggleRoute(route.routeKey)}
                        aria-label={expandedRoutes[route.routeKey] ? 'Collapse' : 'Expand'}
                      >
                        {expandedRoutes[route.routeKey] ? (
                          <ChevronUp className="h-4 w-4" />
                        ) : (
                          <ChevronDown className="h-4 w-4" />
                        )}
                      </IconButton>
                    </TableCell>
                  </TableRow>
                  {expandedRoutes[route.routeKey] && (
                    <TableRow hoverable={false}>
                      <TableCell
                        colSpan={6}
                        className="py-0 border-b-0"
                      >
                        <div className="py-4 pl-8 bg-muted/30 rounded">
                          {renderRouteTOs(route)}
                        </div>
                      </TableCell>
                    </TableRow>
                  )}
                </React.Fragment>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </div>
    );
  };

  // Render TOs for a specific route
  const renderRouteTOs = (route) => {
    const routeTOs = transferOrders.filter(
      to =>
        to.source_site_id === route.source_site_id &&
        to.destination_site_id === route.destination_site_id
    );

    return (
      <Table>
        <TableHead>
          <TableRow>
            <TableCell>TO Number</TableCell>
            <TableCell>Order Period</TableCell>
            <TableCell>Arrival Period</TableCell>
            <TableCell>Quantity</TableCell>
            <TableCell>Status</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {routeTOs.slice(0, 10).map((to) => (
            <TableRow key={to.to_number}>
              <TableCell>
                <span className="text-xs font-mono">{to.to_number}</span>
              </TableCell>
              <TableCell>{to.order_round}</TableCell>
              <TableCell>{to.arrival_round}</TableCell>
              <TableCell>{to.quantity?.toFixed(1) || 'N/A'}</TableCell>
              <TableCell>
                <Chip
                  size="sm"
                  icon={getStatusIcon(to.status)}
                  variant={getStatusVariant(to.status)}
                >
                  {to.status}
                </Chip>
              </TableCell>
            </TableRow>
          ))}
          {routeTOs.length > 10 && (
            <TableRow hoverable={false}>
              <TableCell colSpan={5} className="text-center">
                <span className="text-xs text-muted-foreground">
                  ... and {routeTOs.length - 10} more
                </span>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    );
  };

  // Tab: In-Transit View
  const renderInTransitView = () => {
    const inTransitData = prepareInTransitData();
    const inTransitTOs = tosByStatus['IN_TRANSIT'] || [];

    return (
      <div>
        <h6 className="text-lg font-semibold mb-4">
          Current In-Transit Inventory
        </h6>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-2">
          <Card variant="outlined" padding="none">
            <CardContent className="p-4">
              <span className="text-sm text-muted-foreground">
                In-Transit TOs
              </span>
              <p className="text-3xl font-bold">
                {inTransitTOs.length}
              </p>
            </CardContent>
          </Card>
          <Card variant="outlined" padding="none">
            <CardContent className="p-4">
              <span className="text-sm text-muted-foreground">
                Total In-Transit Quantity
              </span>
              <p className="text-3xl font-bold">
                {analytics?.in_transit_analysis?.current_in_transit_total?.toFixed(1) || 0}
              </p>
            </CardContent>
          </Card>
        </div>

        <div className="mt-6">
          <h6 className="text-sm font-medium mb-2">
            In-Transit by Destination
          </h6>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={inTransitData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="site" />
              <YAxis />
              <RechartsTooltip />
              <Bar dataKey="quantity" fill="#8884d8" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="mt-6">
          <h6 className="text-sm font-medium mb-2">
            In-Transit Transfer Orders
          </h6>
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>TO Number</TableCell>
                  <TableCell>Route</TableCell>
                  <TableCell>Order Period</TableCell>
                  <TableCell>Arrival Period</TableCell>
                  <TableCell className="text-right">Quantity</TableCell>
                  <TableCell>Est. Delivery</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {inTransitTOs.slice(0, 20).map((to) => (
                  <TableRow key={to.to_number}>
                    <TableCell>
                      <span className="text-xs font-mono">{to.to_number}</span>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm">
                        {to.source_site_id} → {to.destination_site_id}
                      </span>
                    </TableCell>
                    <TableCell>{to.order_round}</TableCell>
                    <TableCell>
                      <Chip size="sm" variant="default">
                        Round {to.arrival_round}
                      </Chip>
                    </TableCell>
                    <TableCell className="text-right">
                      {to.quantity?.toFixed(1) || 'N/A'}
                    </TableCell>
                    <TableCell>
                      {to.estimated_delivery_date
                        ? new Date(to.estimated_delivery_date).toLocaleDateString()
                        : 'N/A'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </div>
      </div>
    );
  };

  // Tab: Performance Metrics
  const renderPerformanceView = () => {
    if (!analytics || !analytics.delivery_performance) {
      return (
        <p className="text-sm text-muted-foreground">
          No performance data available
        </p>
      );
    }

    const delivery = analytics.delivery_performance;
    const leadTime = analytics.lead_time_analysis;

    return (
      <div>
        <h6 className="text-lg font-semibold mb-4">
          Delivery Performance
        </h6>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-2">
          <Card variant="outlined" padding="none">
            <CardContent className="p-4">
              <span className="text-sm text-muted-foreground">
                On-Time Delivery Rate
              </span>
              <p className="text-3xl font-bold text-primary">
                {delivery.on_time_delivery_rate.toFixed(1)}%
              </p>
              <span className="text-xs text-muted-foreground">
                {delivery.on_time_count} / {delivery.total_received} TOs
              </span>
            </CardContent>
          </Card>
          <Card variant="outlined" padding="none">
            <CardContent className="p-4">
              <span className="text-sm text-muted-foreground">
                Avg Planned Lead Time
              </span>
              <p className="text-3xl font-bold">
                {leadTime.planned_lead_time.avg.toFixed(1)}
              </p>
              <span className="text-xs text-muted-foreground">
                days
              </span>
            </CardContent>
          </Card>
          <Card variant="outlined" padding="none">
            <CardContent className="p-4">
              <span className="text-sm text-muted-foreground">
                Avg Actual Lead Time
              </span>
              <p className="text-3xl font-bold">
                {leadTime.actual_lead_time.avg.toFixed(1)}
              </p>
              <span className="text-xs text-muted-foreground">
                days
              </span>
            </CardContent>
          </Card>
        </div>

        <div className="mt-6">
          <h6 className="text-sm font-medium mb-2">
            Delivery Status Breakdown
          </h6>
          <div className="grid grid-cols-3 gap-4">
            <Card variant="outlined" padding="none" className="bg-emerald-500 text-white">
              <CardContent className="p-4">
                <span className="text-sm font-medium">On-Time</span>
                <p className="text-2xl font-bold">{delivery.on_time_count}</p>
              </CardContent>
            </Card>
            <Card variant="outlined" padding="none" className="bg-amber-500 text-white">
              <CardContent className="p-4">
                <span className="text-sm font-medium">Late</span>
                <p className="text-2xl font-bold">{delivery.late_count}</p>
              </CardContent>
            </Card>
            <Card variant="outlined" padding="none" className="bg-sky-500 text-white">
              <CardContent className="p-4">
                <span className="text-sm font-medium">Early</span>
                <p className="text-2xl font-bold">{delivery.early_count}</p>
              </CardContent>
            </Card>
          </div>
        </div>

        <div className="mt-6">
          <h6 className="text-sm font-medium mb-2">
            Lead Time Statistics
          </h6>
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Metric</TableCell>
                  <TableCell className="text-right">Planned</TableCell>
                  <TableCell className="text-right">Actual</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                <TableRow>
                  <TableCell>Average</TableCell>
                  <TableCell className="text-right">
                    {leadTime.planned_lead_time.avg.toFixed(2)} days
                  </TableCell>
                  <TableCell className="text-right">
                    {leadTime.actual_lead_time.avg.toFixed(2)} days
                  </TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>Minimum</TableCell>
                  <TableCell className="text-right">
                    {leadTime.planned_lead_time.min.toFixed(0)} days
                  </TableCell>
                  <TableCell className="text-right">
                    {leadTime.actual_lead_time.min.toFixed(0)} days
                  </TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>Maximum</TableCell>
                  <TableCell className="text-right">
                    {leadTime.planned_lead_time.max.toFixed(0)} days
                  </TableCell>
                  <TableCell className="text-right">
                    {leadTime.actual_lead_time.max.toFixed(0)} days
                  </TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>Median</TableCell>
                  <TableCell className="text-right">
                    {leadTime.planned_lead_time.median.toFixed(2)} days
                  </TableCell>
                  <TableCell className="text-right">
                    {leadTime.actual_lead_time.median.toFixed(2)} days
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </TableContainer>
        </div>
      </div>
    );
  };

  return (
    <Card padding="none">
      <CardContent className="p-6">
        <h5 className="text-xl font-semibold mb-4">
          Transfer Order Analytics
        </h5>

        {analytics && analytics.summary && (
          <div className="mb-4">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div>
                <span className="text-xs text-muted-foreground">
                  Total TOs
                </span>
                <p className="text-lg font-semibold">
                  {analytics.summary.total_tos}
                </p>
              </div>
              <div>
                <span className="text-xs text-muted-foreground">
                  In Transit
                </span>
                <p className="text-lg font-semibold">
                  {analytics.summary.status_breakdown?.IN_TRANSIT || 0}
                </p>
              </div>
              <div>
                <span className="text-xs text-muted-foreground">
                  Received
                </span>
                <p className="text-lg font-semibold">
                  {analytics.summary.status_breakdown?.RECEIVED || 0}
                </p>
              </div>
              <div>
                <span className="text-xs text-muted-foreground">
                  Total Quantity
                </span>
                <p className="text-lg font-semibold">
                  {analytics.summary.total_quantity_shipped.toFixed(0)}
                </p>
              </div>
            </div>
          </div>
        )}

        <div className="border-b border-border mb-4">
          <Tabs value={activeTab} onChange={(e, v) => setActiveTab(v)}>
            <TabsList className="bg-transparent">
              <Tab value="timeline" label="Timeline" />
              <Tab value="routes" label="Routes" />
              <Tab value="intransit" label="In-Transit" />
              <Tab value="performance" label="Performance" />
            </TabsList>
          </Tabs>
        </div>

        <div className="mt-4">
          {activeTab === 'timeline' && renderTimelineView()}
          {activeTab === 'routes' && renderRouteView()}
          {activeTab === 'intransit' && renderInTransitView()}
          {activeTab === 'performance' && renderPerformanceView()}
        </div>
      </CardContent>
    </Card>
  );
};

export default TransferOrderTimeline;
