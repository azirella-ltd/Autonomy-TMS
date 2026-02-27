import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Card,
  CardContent,
  Input,
  Label,
  Progress,
  Spinner,
  Textarea,
} from '../components/common';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
} from 'chart.js';
import { format } from 'date-fns';
import { useAuth } from '../contexts/AuthContext';
import { useWebSocket } from '../contexts/WebSocketContext';
import { getHumanDashboard, formatChartData } from '../services/dashboardService';
import simulationApi from '../services/api';
import PageLayout from '../components/PageLayout';
import { toast } from 'sonner';
import { TrendingUp, TrendingDown } from 'lucide-react';

// Register ChartJS components
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

const ROLE_COLORS = {
  RETAILER: 'blue',
  WHOLESALER: 'green',
  DISTRIBUTOR: 'purple',
  MANUFACTURER: 'orange',
  SUPPLIER: 'red'
};

const HumanDashboard = () => {
  const [dashboardData, setDashboardData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [orderQuantity, setOrderQuantity] = useState('');
  const [orderReason, setOrderReason] = useState('');
  const [orderError, setOrderError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { user } = useAuth();
  const { connect, subscribe } = useWebSocket();
  const lastRoundRef = useRef(null);

  const fetchDashboardData = useCallback(
    async (withLoader = false) => {
      try {
        if (withLoader) {
          setLoading(true);
        }
        setError(null);
        const data = await getHumanDashboard();
        setDashboardData(data);
      } catch (err) {
        console.error('Error fetching dashboard data:', err);
        setError('Failed to load dashboard data');
        if (withLoader) {
          toast.error('Failed to load dashboard data. Please try again later.');
        }
      } finally {
        if (withLoader) {
          setLoading(false);
        }
      }
    },
    []
  );

  useEffect(() => {
    fetchDashboardData(true);
  }, [fetchDashboardData]);

  useEffect(() => {
    if (!dashboardData?.scenario_id || !dashboardData?.scenario_user_id) {
      return undefined;
    }

    connect(dashboardData.scenario_id, dashboardData.scenario_user_id);

    const unsubscribe = subscribe((event, payload) => {
      if (event !== 'message') {
        return;
      }

      const messageType = payload?.type;
      if (
        [
          'game_state',
          'round_completed',
          'round_started',
          'order_submitted',
          'inventory_update',
        ].includes(messageType)
      ) {
        fetchDashboardData(false);
      }
    });

    return () => {
      unsubscribe();
    };
  }, [dashboardData?.scenario_id, dashboardData?.scenario_user_id, connect, subscribe, fetchDashboardData]);

  useEffect(() => {
    if (!dashboardData?.current_round) {
      return;
    }

    const currentRound = dashboardData.current_round;
    if (lastRoundRef.current === currentRound) {
      return;
    }

    const series = dashboardData.time_series || [];
    const matchingEntry =
      series.find(entry => entry.week === currentRound) ||
      [...series].sort((a, b) => (a.week ?? 0) - (b.week ?? 0)).pop();

    if (matchingEntry && typeof matchingEntry.order === 'number') {
      setOrderQuantity(String(matchingEntry.order));
    } else {
      setOrderQuantity('');
    }

    setOrderReason('');
    setOrderError('');
    lastRoundRef.current = currentRound;
  }, [dashboardData, lastRoundRef]);

  const handleOrderSubmit = useCallback(async (event) => {
    event.preventDefault();
    setOrderError('');

    if (!dashboardData?.scenario_id || !dashboardData?.scenario_user_id) {
      setOrderError('Unable to determine the current game or user.');
      return;
    }

    if (orderQuantity === '') {
      setOrderError('Please enter an order quantity.');
      return;
    }

    const quantityValue = Number(orderQuantity);
    if (Number.isNaN(quantityValue) || quantityValue < 0) {
      setOrderError('Order quantity must be zero or a positive number.');
      return;
    }

    try {
      setIsSubmitting(true);
      await simulationApi.submitOrder(
        dashboardData.scenario_id,
        dashboardData.scenario_user_id,
        quantityValue,
        orderReason.trim() ? orderReason.trim() : undefined
      );

      toast.success(`Your order of ${quantityValue} units has been recorded.`);

      await fetchDashboardData(false);
    } catch (err) {
      console.error('Failed to submit order:', err);
      const detail = err?.response?.data?.detail;
      const errorMessage = typeof detail === 'string' ? detail : 'Failed to submit order.';
      setOrderError(errorMessage);
      toast.error(errorMessage);
    } finally {
      setIsSubmitting(false);
    }
  }, [dashboardData, orderQuantity, orderReason, fetchDashboardData]);

  const sliderMax = useMemo(() => {
    if (!dashboardData) {
      return 0;
    }
    return Math.max(dashboardData.max_rounds || 0, dashboardData.current_round || 0);
  }, [dashboardData]);

  const sliderDisplayMax = sliderMax || 1;
  const sliderValue = Math.min(dashboardData?.current_round || 0, sliderDisplayMax);
  const progressPercent = sliderDisplayMax
    ? Math.round((sliderValue / sliderDisplayMax) * 100)
    : 0;

  const reasoningTimeline = useMemo(() => {
    if (!dashboardData?.time_series?.length) {
      return [];
    }

    return [...dashboardData.time_series]
      .sort((a, b) => (b.week ?? 0) - (a.week ?? 0));
  }, [dashboardData]);

  const renderMetrics = () => {
    if (!dashboardData?.metrics) return null;

    const { metrics } = dashboardData;
    const serviceLevelPercent = (metrics.service_level || 0) * 100;
    const serviceLevelChangePercent = (metrics.service_level_change || 0) * 100;

    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <Card>
          <CardContent className="p-4">
            <p className="text-sm text-muted-foreground">Current Inventory</p>
            <p className="text-2xl font-bold">{Math.round(metrics.current_inventory || 0)}</p>
            <div className="flex items-center text-sm text-muted-foreground mt-1">
              {metrics.inventory_change >= 0 ? (
                <TrendingUp className="h-4 w-4 text-green-500 mr-1" />
              ) : (
                <TrendingDown className="h-4 w-4 text-red-500 mr-1" />
              )}
              {Math.abs(metrics.inventory_change || 0).toFixed(1)}% from last week
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <p className="text-sm text-muted-foreground">Current Backlog</p>
            <p className={`text-2xl font-bold ${metrics.backlog > 0 ? 'text-red-500' : ''}`}>
              {Math.round(metrics.backlog || 0)}
            </p>
            <p className="text-sm text-muted-foreground mt-1">
              {metrics.backlog > 0 ? 'Orders pending' : 'No pending orders'}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <p className="text-sm text-muted-foreground">Total Cost</p>
            <p className="text-2xl font-bold">${(metrics.total_cost || 0).toFixed(2)}</p>
            <p className="text-sm text-muted-foreground mt-1">
              ${(metrics.avg_weekly_cost || 0).toFixed(2)} per week
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <p className="text-sm text-muted-foreground">Service Level</p>
            <p className="text-2xl font-bold">{serviceLevelPercent.toFixed(1)}%</p>
            <div className="flex items-center text-sm text-muted-foreground mt-1">
              {serviceLevelChangePercent >= 0 ? (
                <TrendingUp className="h-4 w-4 text-green-500 mr-1" />
              ) : (
                <TrendingDown className="h-4 w-4 text-red-500 mr-1" />
              )}
              {Math.abs(serviceLevelChangePercent).toFixed(1)}% from last week
            </div>
          </CardContent>
        </Card>
      </div>
    );
  };

  const renderChart = () => {
    if (!dashboardData?.time_series?.length) return null;

    const { time_series, scenario_user_role } = dashboardData;
    const chartData = formatChartData(time_series, scenario_user_role);
    const labels = chartData.map(item => `Week ${item.week}`);

    const datasets = [
      {
        label: 'Inventory',
        data: chartData.map(item => item.inventory || 0),
        borderColor: 'rgb(75, 192, 192)',
        backgroundColor: 'rgba(75, 192, 192, 0.2)',
        tension: 0.3,
        fill: true,
        yAxisID: 'y',
      },
      {
        label: 'Orders',
        data: chartData.map(item => item.order || 0),
        borderColor: 'rgb(54, 162, 235)',
        backgroundColor: 'rgba(54, 162, 235, 0.2)',
        tension: 0.3,
        fill: false,
        yAxisID: 'y',
      },
      {
        label: 'Backlog',
        data: chartData.map(item => item.backlog || 0),
        borderColor: 'rgb(255, 159, 64)',
        backgroundColor: 'rgba(255, 159, 64, 0.2)',
        tension: 0.3,
        fill: false,
        yAxisID: 'y',
      },
      {
        label: 'Cost',
        data: chartData.map(item => item.cost || 0),
        borderColor: 'rgb(201, 203, 207)',
        backgroundColor: 'rgba(201, 203, 207, 0.2)',
        tension: 0.3,
        fill: false,
        yAxisID: 'y1',
        hidden: true,
      }
    ];

    const showDemand = scenario_user_role === 'RETAILER' || scenario_user_role === 'MANUFACTURER' || scenario_user_role === 'DISTRIBUTOR';
    const showSupply = scenario_user_role === 'SUPPLIER' || scenario_user_role === 'MANUFACTURER' || scenario_user_role === 'DISTRIBUTOR';

    if (showDemand) {
      datasets.push({
        label: 'Demand',
        data: chartData.map(item => item.demand || 0),
        borderColor: 'rgb(255, 99, 132)',
        backgroundColor: 'rgba(255, 99, 132, 0.2)',
        tension: 0.3,
        fill: false,
        borderDash: [5, 5],
        yAxisID: 'y',
      });
    }

    if (showSupply) {
      datasets.push({
        label: 'Supply',
        data: chartData.map(item => item.supply || 0),
        borderColor: 'rgb(153, 102, 255)',
        backgroundColor: 'rgba(153, 102, 255, 0.2)',
        tension: 0.3,
        fill: false,
        borderDash: [5, 5],
        yAxisID: 'y',
      });
    }

    const options = {
      responsive: true,
      interaction: {
        mode: 'index',
        intersect: false,
      },
      plugins: {
        legend: {
          position: 'top',
        },
        title: {
          display: true,
          text: 'Weekly Performance Metrics',
        },
      },
      scales: {
        y: {
          type: 'linear',
          display: true,
          position: 'left',
          title: {
            display: true,
            text: 'Units',
          },
          beginAtZero: true,
        },
        y1: {
          type: 'linear',
          display: false,
          position: 'right',
          title: {
            display: true,
            text: 'Cost ($)',
          },
          beginAtZero: true,
          grid: {
            drawOnChartArea: false,
          },
        },
        x: {
          title: {
            display: true,
            text: 'Week'
          },
          grid: {
            display: false,
          },
        }
      },
    };

    return (
      <Card className="mb-6">
        <CardContent className="p-4">
          <Line options={options} data={{ labels, datasets }} />
        </CardContent>
      </Card>
    );
  };

  if (loading) {
    return (
      <PageLayout title="Loading Dashboard...">
        <div className="flex flex-col items-center justify-center mt-8 gap-4">
          <Spinner size="lg" />
          <p>Loading your dashboard...</p>
        </div>
      </PageLayout>
    );
  }

  if (error) {
    return (
      <PageLayout title="Error">
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>
            <strong>Error loading dashboard:</strong> {error}
          </AlertDescription>
        </Alert>
      </PageLayout>
    );
  }

  if (!dashboardData) {
    return (
      <PageLayout title="No Active Scenario">
        <Alert className="mb-4">
          <AlertDescription>
            You are not currently part of any active scenario.
          </AlertDescription>
        </Alert>
      </PageLayout>
    );
  }

  const { game_name, scenario_user_role, current_round, last_updated } = dashboardData;
  const roleColor = ROLE_COLORS[scenario_user_role] || 'gray';
  const roleVariant = roleColor === 'blue' ? 'info' :
                      roleColor === 'green' ? 'success' :
                      roleColor === 'purple' ? 'default' :
                      roleColor === 'orange' ? 'warning' :
                      roleColor === 'red' ? 'destructive' : 'secondary';

  return (
    <PageLayout title="My Dashboard">
      <div className="space-y-6">
        {/* Header */}
        <Card>
          <CardContent className="p-6">
            <div className="flex justify-between items-start mb-4">
              <div>
                <h1 className="text-2xl font-bold">{game_name || 'My Game'}</h1>
                <p className="text-muted-foreground mt-1">
                  Welcome back, {user?.username || 'User'}
                </p>
              </div>
              <div className="text-right">
                <Badge variant={roleVariant} className="text-base p-2">
                  {scenario_user_role || 'PLAYER'}
                </Badge>
                <p className="text-sm text-muted-foreground mt-1">
                  Round {current_round || 1}
                </p>
              </div>
            </div>
            <hr className="my-4" />
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Last updated: {last_updated ? format(new Date(last_updated), 'PPpp') : '—'}
              </p>
              <div>
                <div className="flex justify-between items-center mb-2">
                  <span className="text-sm font-medium">Scenario Progress</span>
                  <span className="text-sm text-muted-foreground">
                    {`${sliderValue} / ${sliderDisplayMax}`} ({progressPercent}% complete)
                  </span>
                </div>
                <Progress value={progressPercent} />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Order submission */}
        <Card>
          <CardContent className="p-6">
            <h2 className="text-lg font-semibold mb-4">
              Submit order for Week {current_round || 1}
            </h2>
            <form onSubmit={handleOrderSubmit}>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="order-quantity">Order quantity *</Label>
                  <Input
                    id="order-quantity"
                    type="number"
                    min={0}
                    value={orderQuantity}
                    onChange={(e) => setOrderQuantity(e.target.value)}
                    placeholder="Enter units to order"
                  />
                  {orderError && (
                    <p className="text-sm text-destructive mt-1">{orderError}</p>
                  )}
                </div>
                <div>
                  <Label htmlFor="order-reason">Reason (optional)</Label>
                  <Textarea
                    id="order-reason"
                    value={orderReason}
                    onChange={(e) => setOrderReason(e.target.value)}
                    placeholder="Provide context for your order decision"
                    rows={orderReason ? 4 : 3}
                  />
                </div>
              </div>
              <div className="flex justify-between items-center mt-4 flex-wrap gap-3">
                <p className="text-sm text-muted-foreground">
                  Round {current_round || 1} of {sliderDisplayMax}. Keep orders flowing to avoid backlog.
                </p>
                <Button type="submit" disabled={isSubmitting}>
                  {isSubmitting ? 'Submitting...' : 'Submit order'}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        {/* Metrics */}
        <div>
          <h2 className="text-lg font-semibold mb-4">Performance Metrics</h2>
          {renderMetrics()}
        </div>

        {/* Chart */}
        <div>
          <h2 className="text-lg font-semibold mb-4">Weekly Performance</h2>
          {renderChart()}
        </div>

        {/* Order reasoning timeline */}
        <div>
          <h2 className="text-lg font-semibold mb-4">Order Reasoning by Week</h2>
          <Card>
            <CardContent className="p-4">
              {reasoningTimeline.length ? (
                <div className="space-y-3">
                  {reasoningTimeline.map((entry) => (
                    <div
                      key={`reason-${entry.week}`}
                      className="p-4 rounded-md border bg-muted/30"
                    >
                      <div className="flex justify-between items-start gap-3">
                        <div className="flex items-center gap-3">
                          <Badge variant="info">Week {entry.week}</Badge>
                          <Badge variant="secondary">
                            Order {Math.round(entry.order ?? 0)}
                          </Badge>
                        </div>
                        <span className="text-sm text-muted-foreground">
                          {entry.reason ? 'Reason documented' : 'No reason provided'}
                        </span>
                      </div>
                      <p className="mt-3 text-sm">
                        {entry.reason || 'No reasoning provided for this order.'}
                      </p>
                      <div className="flex gap-4 mt-3 text-xs text-muted-foreground">
                        <span>Inventory: {Math.round(entry.inventory ?? 0)}</span>
                        <span>Backlog: {Math.round(entry.backlog ?? 0)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-muted-foreground">
                  No order history is available yet. Your reasoning will appear here as you submit orders.
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </PageLayout>
  );
};

export default HumanDashboard;
