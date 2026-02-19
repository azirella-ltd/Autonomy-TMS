import React, { useState, useEffect } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Title,
  Tooltip as ChartTooltip,
  Legend,
} from 'chart.js';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Badge,
  Label,
  Spinner,
  Progress,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from '../../components/common';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../../components/ui/tooltip';
import {
  LayoutDashboard,
  TrendingUp,
  TrendingDown,
  CheckCircle,
  AlertTriangle,
  XCircle,
  RefreshCw,
  Download,
  Activity,
  Package,
  Truck,
  DollarSign,
  Gauge,
  Star,
} from 'lucide-react';
import { Line, Bar, Doughnut } from 'react-chartjs-2';
import { api } from '../../services/api';

// Register Chart.js components
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Title,
  ChartTooltip,
  Legend
);

const KPIMonitoring = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('financial');
  const [timeRange, setTimeRange] = useState('last_30_days');
  const [kpiData, setKpiData] = useState(null);

  useEffect(() => {
    loadKPIData();
  }, [timeRange]);

  const loadKPIData = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await api.get('/analytics/kpis', {
        params: { time_range: timeRange },
      });
      setKpiData(response.data);
    } catch (err) {
      console.warn('KPI endpoint not available, using mock data');
      setKpiData(generateMockKPIData());
    } finally {
      setLoading(false);
    }
  };

  const generateMockKPIData = () => {
    return {
      financial: {
        total_cost: 1250000,
        total_cost_trend: -3.5,
        inventory_holding_cost: 450000,
        backlog_cost: 180000,
        transportation_cost: 320000,
        production_cost: 300000,
        cost_by_week: Array.from({ length: 12 }, (_, i) => ({
          week: i + 1,
          cost: 100000 + Math.random() * 50000,
        })),
      },
      customer: {
        otif: 92.5,
        otif_trend: 2.1,
        otif_target: 95.0,
        fill_rate: 94.8,
        fill_rate_trend: 1.5,
        service_level: 96.2,
        service_level_trend: -0.8,
        customer_complaints: 12,
        complaints_trend: -25.0,
        otif_by_week: Array.from({ length: 12 }, (_, i) => ({
          week: i + 1,
          otif: 90 + Math.random() * 8,
        })),
      },
      operational: {
        inventory_turns: 8.5,
        inventory_turns_trend: 1.2,
        days_of_supply: 42.9,
        days_of_supply_trend: -2.5,
        bullwhip_ratio: 1.35,
        bullwhip_trend: -5.6,
        stockout_incidents: 5,
        stockout_trend: -40.0,
        capacity_utilization: 78.5,
        utilization_trend: 3.2,
        on_time_delivery: 93.2,
        delivery_trend: 1.8,
        inventory_trend: Array.from({ length: 12 }, (_, i) => ({
          week: i + 1,
          inventory: 5000 + Math.random() * 2000,
        })),
      },
      strategic: {
        supplier_reliability: 95.3,
        supplier_trend: 0.5,
        network_flexibility: 72.0,
        flexibility_trend: 4.2,
        forecast_accuracy: 85.7,
        forecast_trend: 2.3,
        carbon_emissions: 1250,
        emissions_trend: -8.5,
        risk_score: 3.2,
        risk_trend: -12.5,
      },
    };
  };

  const renderKPICard = (title, value, unit, trend, target, Icon, colorClass = 'text-primary') => {
    const trendColor = trend >= 0 ? 'text-green-600' : 'text-red-600';
    const TrendIcon = trend >= 0 ? TrendingUp : TrendingDown;

    return (
      <Card>
        <CardContent className="pt-4">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-sm text-muted-foreground mb-1">{title}</p>
              <div className="flex items-baseline gap-1">
                <span className={`text-3xl font-bold ${colorClass}`}>
                  {typeof value === 'number' ? value.toFixed(1) : value}
                </span>
                <span className="text-sm text-muted-foreground">{unit}</span>
              </div>
              {target && (
                <p className="text-xs text-muted-foreground mt-1">
                  Target: {target}
                  {unit}
                </p>
              )}
              <div className="flex items-center gap-1 mt-2">
                <Badge variant={trend >= 0 ? 'success' : 'destructive'} className="flex items-center gap-1">
                  <TrendIcon className="h-3 w-3" />
                  {Math.abs(trend).toFixed(1)}%
                </Badge>
                <span className="text-xs text-muted-foreground">vs last period</span>
              </div>
            </div>
            <Icon className={`h-10 w-10 ${colorClass} opacity-30`} />
          </div>
          {target && (
            <div className="mt-4">
              <Progress
                value={Math.min((value / target) * 100, 100)}
                className={`h-2 ${value >= target ? '[&>div]:bg-green-500' : '[&>div]:bg-amber-500'}`}
              />
            </div>
          )}
        </CardContent>
      </Card>
    );
  };

  const renderFinancialTab = () => {
    if (!kpiData) return null;
    const { financial } = kpiData;

    return (
      <div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          {renderKPICard('Total Cost', financial.total_cost, '$', financial.total_cost_trend, null, DollarSign, 'text-primary')}
          {renderKPICard('Inventory Holding Cost', financial.inventory_holding_cost, '$', -2.1, null, Package, 'text-amber-600')}
          {renderKPICard('Backlog Cost', financial.backlog_cost, '$', -15.3, null, AlertTriangle, 'text-red-600')}
          {renderKPICard('Transportation Cost', financial.transportation_cost, '$', 1.8, null, Truck, 'text-blue-600')}
        </div>

        <Card>
          <CardContent className="pt-4">
            <h3 className="text-lg font-semibold mb-4">Cost Trend</h3>
            <Line
              data={{
                labels: financial.cost_by_week.map((d) => `Week ${d.week}`),
                datasets: [
                  {
                    label: 'Total Cost',
                    data: financial.cost_by_week.map((d) => d.cost),
                    borderColor: 'rgb(75, 192, 192)',
                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                    tension: 0.1,
                  },
                ],
              }}
              options={{
                responsive: true,
                plugins: { legend: { position: 'top' } },
                scales: { y: { beginAtZero: false, title: { display: true, text: 'Cost ($)' } } },
              }}
            />
          </CardContent>
        </Card>
      </div>
    );
  };

  const renderCustomerTab = () => {
    if (!kpiData) return null;
    const { customer } = kpiData;

    return (
      <div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          {renderKPICard(
            'OTIF (On-Time In-Full)',
            customer.otif,
            '%',
            customer.otif_trend,
            customer.otif_target,
            CheckCircle,
            customer.otif >= customer.otif_target ? 'text-green-600' : 'text-amber-600'
          )}
          {renderKPICard('Fill Rate', customer.fill_rate, '%', customer.fill_rate_trend, 95.0, Star, 'text-blue-600')}
          {renderKPICard('Service Level', customer.service_level, '%', customer.service_level_trend, 95.0, TrendingUp, 'text-primary')}
          {renderKPICard('Customer Complaints', customer.customer_complaints, '', customer.complaints_trend, null, AlertTriangle, 'text-red-600')}
        </div>

        <Card>
          <CardContent className="pt-4">
            <h3 className="text-lg font-semibold mb-4">OTIF Performance</h3>
            <Bar
              data={{
                labels: customer.otif_by_week.map((d) => `Week ${d.week}`),
                datasets: [
                  {
                    label: 'OTIF %',
                    data: customer.otif_by_week.map((d) => d.otif),
                    backgroundColor: customer.otif_by_week.map((d) =>
                      d.otif >= customer.otif_target ? 'rgba(75, 192, 75, 0.6)' : 'rgba(255, 165, 0, 0.6)'
                    ),
                  },
                  {
                    label: 'Target',
                    data: Array(customer.otif_by_week.length).fill(customer.otif_target),
                    type: 'line',
                    borderColor: 'rgb(255, 99, 132)',
                    borderDash: [5, 5],
                    fill: false,
                  },
                ],
              }}
              options={{
                responsive: true,
                plugins: { legend: { position: 'top' } },
                scales: { y: { beginAtZero: false, min: 80, max: 100, title: { display: true, text: 'OTIF (%)' } } },
              }}
            />
          </CardContent>
        </Card>
      </div>
    );
  };

  const renderOperationalTab = () => {
    if (!kpiData) return null;
    const { operational } = kpiData;

    return (
      <div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          {renderKPICard('Inventory Turns', operational.inventory_turns, 'x/year', operational.inventory_turns_trend, 10.0, Package, 'text-primary')}
          {renderKPICard('Days of Supply', operational.days_of_supply, 'days', operational.days_of_supply_trend, 30.0, Activity, 'text-blue-600')}
          {renderKPICard(
            'Bullwhip Ratio',
            operational.bullwhip_ratio,
            '',
            operational.bullwhip_trend,
            1.0,
            TrendingUp,
            operational.bullwhip_ratio <= 1.5 ? 'text-green-600' : 'text-amber-600'
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          {renderKPICard('Stockout Incidents', operational.stockout_incidents, '', operational.stockout_trend, null, XCircle, 'text-red-600')}
          {renderKPICard('Capacity Utilization', operational.capacity_utilization, '%', operational.utilization_trend, 85.0, Gauge, 'text-amber-600')}
          {renderKPICard('On-Time Delivery', operational.on_time_delivery, '%', operational.delivery_trend, 95.0, Truck, 'text-green-600')}
        </div>

        <Card>
          <CardContent className="pt-4">
            <h3 className="text-lg font-semibold mb-4">Inventory Levels</h3>
            <Line
              data={{
                labels: operational.inventory_trend.map((d) => `Week ${d.week}`),
                datasets: [
                  {
                    label: 'Inventory',
                    data: operational.inventory_trend.map((d) => d.inventory),
                    borderColor: 'rgb(54, 162, 235)',
                    backgroundColor: 'rgba(54, 162, 235, 0.2)',
                    tension: 0.1,
                  },
                ],
              }}
              options={{
                responsive: true,
                plugins: { legend: { position: 'top' } },
                scales: { y: { beginAtZero: true, title: { display: true, text: 'Units' } } },
              }}
            />
          </CardContent>
        </Card>
      </div>
    );
  };

  const renderStrategicTab = () => {
    if (!kpiData) return null;
    const { strategic } = kpiData;

    return (
      <div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          {renderKPICard('Supplier Reliability', strategic.supplier_reliability, '%', strategic.supplier_trend, 95.0, CheckCircle, 'text-green-600')}
          {renderKPICard('Network Flexibility', strategic.network_flexibility, '%', strategic.flexibility_trend, 80.0, Activity, 'text-blue-600')}
          {renderKPICard('Forecast Accuracy', strategic.forecast_accuracy, '%', strategic.forecast_trend, 90.0, TrendingUp, 'text-primary')}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {renderKPICard(
            'Carbon Emissions',
            strategic.carbon_emissions,
            'tons CO2',
            strategic.emissions_trend,
            null,
            AlertTriangle,
            strategic.emissions_trend < 0 ? 'text-green-600' : 'text-amber-600'
          )}
          {renderKPICard(
            'Supply Chain Risk Score',
            strategic.risk_score,
            '/10',
            strategic.risk_trend,
            null,
            XCircle,
            strategic.risk_score <= 5 ? 'text-green-600' : 'text-red-600'
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="flex justify-between items-center mb-6">
        <div className="flex items-center gap-2">
          <LayoutDashboard className="h-8 w-8 text-primary" />
          <h1 className="text-2xl font-bold">KPI Monitoring</h1>
        </div>
        <div className="flex items-center gap-2">
          <Select value={timeRange} onValueChange={setTimeRange}>
            <SelectTrigger className="w-48">
              <SelectValue placeholder="Select time range" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="last_7_days">Last 7 Days</SelectItem>
              <SelectItem value="last_30_days">Last 30 Days</SelectItem>
              <SelectItem value="last_90_days">Last 90 Days</SelectItem>
              <SelectItem value="last_12_months">Last 12 Months</SelectItem>
              <SelectItem value="ytd">Year to Date</SelectItem>
            </SelectContent>
          </Select>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="sm" onClick={loadKPIData}>
                  <RefreshCw className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Refresh</TooltipContent>
            </Tooltip>
          </TooltipProvider>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="sm">
                  <Download className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Export</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      </div>

      {error && (
        <Alert variant="destructive" className="mb-4" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {loading ? (
        <div className="flex justify-center p-8">
          <Spinner size="lg" />
        </div>
      ) : (
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="mb-4">
            <TabsTrigger value="financial" className="flex items-center gap-2">
              <DollarSign className="h-4 w-4" />
              Financial
            </TabsTrigger>
            <TabsTrigger value="customer" className="flex items-center gap-2">
              <Star className="h-4 w-4" />
              Customer
            </TabsTrigger>
            <TabsTrigger value="operational" className="flex items-center gap-2">
              <Gauge className="h-4 w-4" />
              Operational
            </TabsTrigger>
            <TabsTrigger value="strategic" className="flex items-center gap-2">
              <Activity className="h-4 w-4" />
              Strategic
            </TabsTrigger>
          </TabsList>

          <TabsContent value="financial">{renderFinancialTab()}</TabsContent>
          <TabsContent value="customer">{renderCustomerTab()}</TabsContent>
          <TabsContent value="operational">{renderOperationalTab()}</TabsContent>
          <TabsContent value="strategic">{renderStrategicTab()}</TabsContent>
        </Tabs>
      )}
    </div>
  );
};

export default KPIMonitoring;
