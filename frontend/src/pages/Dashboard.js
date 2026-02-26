import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  Badge,
  Button,
  Spinner,
  Alert,
  AlertDescription,
  Select,
  Modal,
  ModalHeader,
  ModalTitle,
  ModalBody,
  ModalFooter,
  Slider,
  useToast,
} from '../components/common';
import { cn } from '../lib/utils/cn';
import PageLayout from '../components/PageLayout';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import FilterBar from '../components/FilterBar';
import KPIStat from '../components/KPIStat';
import SkuTable from '../components/SkuTable';
import { useAuth } from '../contexts/AuthContext';
import { getHumanDashboard, getUserGames } from '../services/dashboardService';

const FALLBACK_DEMAND_SERIES = [
  { name: 'W1', actual: 2100, forecast: 2200, target: 2000 },
  { name: 'W2', actual: 2250, forecast: 2300, target: 2050 },
  { name: 'W3', actual: 2150, forecast: 2350, target: 2100 },
  { name: 'W4', actual: 2300, forecast: 2400, target: 2100 },
  { name: 'W5', actual: 2400, forecast: 2380, target: 2150 },
  { name: 'W6', actual: 2350, forecast: 2450, target: 2150 },
  { name: 'W7', actual: 2420, forecast: 2500, target: 2200 },
  { name: 'W8', actual: 2380, forecast: 2480, target: 2200 },
  { name: 'W9', actual: 2450, forecast: 2550, target: 2250 },
  { name: 'W10', actual: 2480, forecast: 2580, target: 2250 },
  { name: 'W11', actual: 2460, forecast: 2600, target: 2300 },
  { name: 'W12', actual: 2520, forecast: 2650, target: 2300 },
];

const FALLBACK_STOCK_VS_SAFETY = [
  { name: 'Widget A', stock: 1800, safety: 400 },
  { name: 'Widget B', stock: 900, safety: 300 },
  { name: 'Component C', stock: 7500, safety: 800 },
  { name: 'Assembly D', stock: 1200, safety: 350 },
  { name: 'Module E', stock: 320, safety: 100 },
  { name: 'Part F', stock: 6780, safety: 500 },
];

const FALLBACK_STOCK_VS_FORECAST = [
  { name: 'Widget A', stock: 1800, forecast: 2200 },
  { name: 'Widget B', stock: 900, forecast: 1200 },
  { name: 'Component C', stock: 7500, forecast: 3900 },
  { name: 'Assembly D', stock: 1200, forecast: 1500 },
  { name: 'Module E', stock: 320, forecast: 500 },
  { name: 'Part F', stock: 6780, forecast: 5200 },
];

const FALLBACK_TOTAL_ROUNDS = 36;
const FALLBACK_CURRENT_ROUND = 18;

const FALLBACK_DECISION_TIMELINE = [
  {
    week: 18,
    order: 2450,
    reason: 'Anticipating a regional promotion and aligning safety stock.',
    inventory: 1820,
    backlog: 90,
  },
  {
    week: 17,
    order: 2320,
    reason: 'Backlog declined after expedited shipment; stabilizing pipeline.',
    inventory: 1765,
    backlog: 110,
  },
  {
    week: 16,
    order: 2280,
    reason: 'Maintained previous order to absorb variability from manufacturer delay.',
    inventory: 1690,
    backlog: 140,
  },
  {
    week: 15,
    order: 2200,
    reason: 'Raised order size to offset three-week moving average increase.',
    inventory: 1580,
    backlog: 180,
  },
];

const normalizeNumber = (value) => {
  if (value === null || value === undefined) {
    return null;
  }
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
};

const formatNumber = (value, options) => {
  const numeric = normalizeNumber(value);
  if (numeric === null) {
    return '--';
  }
  return new Intl.NumberFormat('en-US', options).format(numeric);
};

const formatCurrency = (value) => formatNumber(value, { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });

const formatPercent = (value) => {
  const numeric = normalizeNumber(value);
  if (numeric === null) {
    return '--';
  }
  return `${(numeric * 100).toFixed(1)}%`;
};

const formatSigned = (value, { asPercent = false } = {}) => {
  const numeric = normalizeNumber(value);
  if (numeric === null) {
    return null;
  }
  const prefix = numeric > 0 ? '+' : '';
  if (asPercent) {
    return `${prefix}${(numeric * 100).toFixed(1)}%`;
  }
  return `${prefix}${formatNumber(numeric)}`;
};

const Dashboard = () => {
  const navigate = useNavigate();
  const toast = useToast();
  const { logout, user } = useAuth();

  const [loading, setLoading] = useState(true);
  const [dashboardData, setDashboardData] = useState(null);
  const [assignmentModalOpen, setAssignmentModalOpen] = useState(false);
  const [assignmentMessage, setAssignmentMessage] = useState('You are not assigned to a game yet. Please contact your facilitator to be added to a session.');
  const [error, setError] = useState(null);
  const [availableGames, setAvailableGames] = useState([]);
  const [selectedGameId, setSelectedGameId] = useState(null);
  const [gamesLoading, setGamesLoading] = useState(true);

  // Redirect scenarioUsers to their active game board
  useEffect(() => {
    if (user && user.user_type === 'USER') {
      const fetchAndRedirect = async () => {
        try {
          const games = await getUserGames();
          if (games.length > 0) {
            const activeGame = games.find(g => g.status === 'IN_PROGRESS' || g.status === 'STARTED');
            const targetGame = activeGame || games[0];
            navigate(`/scenarios/${targetGame.id}`, { replace: true });
          } else {
            setAssignmentMessage('You are not assigned to any games. Please contact your facilitator.');
            setAssignmentModalOpen(true);
            setGamesLoading(false);
          }
        } catch (err) {
          console.error('Failed to fetch user games:', err);
          setAssignmentMessage('Unable to load your game assignments.');
          setAssignmentModalOpen(true);
          setGamesLoading(false);
        }
      };
      fetchAndRedirect();
    }
  }, [user, navigate]);

  // Fetch available games for admins viewing the dashboard
  useEffect(() => {
    if (!user || user.user_type === 'USER') return;

    let isMounted = true;

    const fetchGames = async () => {
      setGamesLoading(true);
      try {
        const games = await getUserGames();
        if (!isMounted) return;

        setAvailableGames(games);

        if (games.length > 0) {
          const activeGame = games.find(g => g.status === 'IN_PROGRESS' || g.status === 'STARTED');
          setSelectedGameId(activeGame?.id || games[0].id);
        } else {
          setAssignmentMessage('You are not assigned to any games. Please contact your facilitator.');
          setAssignmentModalOpen(true);
        }
      } catch (err) {
        if (!isMounted) return;
        console.error('Failed to fetch user games:', err);
        setAssignmentMessage('Unable to load your game assignments.');
        setAssignmentModalOpen(true);
      } finally {
        if (isMounted) {
          setGamesLoading(false);
        }
      }
    };

    fetchGames();

    return () => {
      isMounted = false;
    };
  }, [user]);

  // Fetch dashboard data for selected game
  useEffect(() => {
    if (!selectedGameId || gamesLoading) return;

    let isMounted = true;

    const fetchDashboard = async () => {
      setLoading(true);
      try {
        const data = await getHumanDashboard(selectedGameId);
        if (!isMounted) {
          return;
        }
        setDashboardData(data);
        setError(null);
        setAssignmentModalOpen(false);
      } catch (err) {
        if (!isMounted) {
          return;
        }
        const status = err?.response?.status;
        if (status === 404) {
          setAssignmentMessage(err?.response?.data?.detail || 'We could not find data for this game.');
          setDashboardData(null);
          setError('Game data not found.');
        } else if (status === 403) {
          setAssignmentMessage('You do not have access to this game.');
          setDashboardData(null);
          setError('Access denied to this game.');
        } else {
          console.error('Unable to load dashboard data:', err);
          setError('Unable to load the dashboard right now. Please try again later.');
          toast({
            title: 'Failed to load dashboard',
            description: err?.response?.data?.detail || err?.message || 'Unexpected error occurred.',
            status: 'error',
            duration: 9000,
            isClosable: true,
          });
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    fetchDashboard();

    return () => {
      isMounted = false;
    };
  }, [toast, user?.id, selectedGameId, gamesLoading]);

  const handleAssignmentLogout = async () => {
    try {
      await logout();
    } finally {
      navigate('/login');
    }
  };

  const metrics = dashboardData?.metrics;
  const timeSeriesRaw = dashboardData?.time_series;
  const timeSeries = useMemo(() => timeSeriesRaw ?? [], [timeSeriesRaw]);
  const totalRounds = normalizeNumber(dashboardData?.max_rounds) || FALLBACK_TOTAL_ROUNDS;
  const currentRoundRaw = normalizeNumber(dashboardData?.current_round) ?? FALLBACK_CURRENT_ROUND;
  const sliderMax = totalRounds > 0 ? totalRounds : FALLBACK_TOTAL_ROUNDS;
  const sliderValue = Math.min(Math.max(currentRoundRaw, 0), sliderMax);
  const progressPercent = sliderMax ? Math.round((sliderValue / sliderMax) * 100) : 0;
  const scenarioUserRoleLabel = dashboardData?.scenario_user_role ? dashboardData.scenario_user_role.replace(/_/g, ' ') : null;

  const demandSeries = useMemo(() => {
    if (!timeSeries.length) {
      return FALLBACK_DEMAND_SERIES;
    }
    return timeSeries.map((point) => ({
      name: `W${point.week}`,
      actual: normalizeNumber(point.demand) ?? normalizeNumber(point.order) ?? 0,
      forecast: normalizeNumber(point.order) ?? 0,
      target: normalizeNumber(point.inventory) ?? 0,
    }));
  }, [timeSeries]);

  const stockVsSafety = useMemo(() => {
    if (!timeSeries.length) {
      return FALLBACK_STOCK_VS_SAFETY;
    }
    return timeSeries.slice(-6).map((point) => ({
      name: `Week ${point.week}`,
      stock: normalizeNumber(point.inventory) ?? 0,
      safety: normalizeNumber(point.inventory) !== null && normalizeNumber(point.backlog) !== null
        ? Math.max(0, normalizeNumber(point.inventory) - normalizeNumber(point.backlog))
        : normalizeNumber(point.backlog) ?? 0,
    }));
  }, [timeSeries]);

  const stockVsForecast = useMemo(() => {
    if (!timeSeries.length) {
      return FALLBACK_STOCK_VS_FORECAST;
    }
    return timeSeries.slice(-6).map((point) => ({
      name: `Week ${point.week}`,
      stock: normalizeNumber(point.inventory) ?? 0,
      forecast: normalizeNumber(point.order) ?? 0,
    }));
  }, [timeSeries]);

  const decisionTimeline = useMemo(() => {
    if (!timeSeries.length) {
      return FALLBACK_DECISION_TIMELINE;
    }
    return [...timeSeries]
      .slice(-6)
      .reverse()
      .map((point) => ({
        week: point.week,
        order: normalizeNumber(point.order) ?? 0,
        inventory: normalizeNumber(point.inventory) ?? 0,
        backlog: normalizeNumber(point.backlog) ?? 0,
        reason: point.reason || 'No decision notes captured.',
      }));
  }, [timeSeries]);

  const kpiCards = useMemo(() => {
    if (!metrics) {
      return [
        { title: 'Current Inventory', value: '--', subtitle: 'Units on hand' },
        { title: 'Backlog', value: '--', subtitle: 'Open orders' },
        { title: 'Average Weekly Cost', value: '--', subtitle: 'Recent average' },
        { title: 'Service Level', value: '--', subtitle: 'Fulfillment rate' },
      ];
    }

    const inventoryChange = formatSigned(metrics.inventory_change);
    const serviceLevelChange = formatSigned(metrics.service_level_change, { asPercent: true });

    return [
      {
        title: 'Current Inventory',
        value: formatNumber(metrics.current_inventory),
        subtitle: 'Units on hand',
        delta: inventoryChange,
        deltaPositive: (normalizeNumber(metrics.inventory_change) ?? 0) >= 0,
      },
      {
        title: 'Backlog',
        value: formatNumber(metrics.backlog),
        subtitle: 'Outstanding demand',
        delta: null,
      },
      {
        title: 'Average Weekly Cost',
        value: formatCurrency(metrics.avg_weekly_cost),
        subtitle: 'Rolling average',
        delta: null,
      },
      {
        title: 'Service Level',
        value: formatPercent(metrics.service_level),
        subtitle: 'Fulfillment rate',
        delta: serviceLevelChange,
        deltaPositive: (normalizeNumber(metrics.service_level_change) ?? 0) >= 0,
      },
    ];
  }, [metrics]);

  const pageTitle = dashboardData?.game_name ? `${dashboardData.game_name} Dashboard` : 'Dashboard';

  return (
    <>
      <PageLayout title={pageTitle}>
        <div className="p-4">
          {loading ? (
            <div className="flex justify-center items-center min-h-[50vh]">
              <Spinner size="lg" />
            </div>
          ) : (
            <>
              {error && (
                <Alert variant="error" className="mb-4">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}

              <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 mt-2 gap-4">
                <div className="flex flex-col gap-1">
                  <h1 className="text-3xl font-semibold">
                    {dashboardData?.game_name || 'Dashboard'}
                  </h1>
                  <p className="text-xs text-muted-foreground">
                    Overview of your supply chain performance
                  </p>
                  <div className="flex gap-2 mt-1">
                    {scenarioUserRoleLabel && (
                      <Badge variant="default" className="capitalize">{scenarioUserRoleLabel}</Badge>
                    )}
                    <Badge variant="secondary">Round {sliderValue} / {sliderMax}</Badge>
                  </div>
                </div>
              </div>

              {/* Game Selector */}
              {availableGames.length > 1 && (
                <Card className="mb-4 bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-700">
                  <CardContent className="py-3">
                    <div className="flex items-center gap-3">
                      <span className="font-semibold text-sm min-w-[80px]">
                        Select Game:
                      </span>
                      <Select
                        value={selectedGameId || ''}
                        onChange={(e) => setSelectedGameId(Number(e.target.value))}
                        size="sm"
                        className="max-w-[400px]"
                      >
                        {availableGames.map((game) => (
                          <option key={game.id} value={game.id}>
                            {game.name} - {game.role} (Round {game.current_round}/{game.max_rounds})
                          </option>
                        ))}
                      </Select>
                      <Badge variant={
                        availableGames.find(g => g.id === selectedGameId)?.status === 'IN_PROGRESS' ||
                        availableGames.find(g => g.id === selectedGameId)?.status === 'STARTED'
                          ? 'success'
                          : 'secondary'
                      }>
                        {availableGames.find(g => g.id === selectedGameId)?.status || 'Unknown'}
                      </Badge>
                    </div>
                  </CardContent>
                </Card>
              )}

              <FilterBar />

              <Card className="mb-6 bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-700">
                <CardHeader className="pb-2">
                  <CardTitle>Game Progress</CardTitle>
                </CardHeader>
                <CardContent className="pt-0">
                  <div className="flex flex-col gap-3">
                    <div className="flex justify-between items-center">
                      <span className="text-muted-foreground">Rounds completed</span>
                      <span className="font-semibold">{progressPercent}%</span>
                    </div>
                    <Slider
                      value={sliderValue}
                      min={0}
                      max={sliderMax}
                      isReadOnly
                      showValue
                      colorScheme="green"
                    />
                    <p className="text-xs text-muted-foreground">Week {sliderValue} of {sliderMax}</p>
                  </div>
                </CardContent>
              </Card>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                {kpiCards.map((card) => (
                  <KPIStat
                    key={card.title}
                    title={card.title}
                    value={card.value}
                    subtitle={card.subtitle}
                    delta={card.delta}
                    deltaPositive={card.deltaPositive}
                  />
                ))}
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
                <div className="lg:col-span-2 space-y-6">
                  <Card className="bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-700">
                    <CardHeader>
                      <CardTitle>Demand Forecast vs Actual</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="h-[300px]">
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart data={demandSeries}>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="name" />
                            <YAxis />
                            <Tooltip />
                            <Legend />
                            <Line type="monotone" dataKey="actual" stroke="#3182CE" name="Actual" strokeWidth={2} />
                            <Line type="monotone" dataKey="forecast" stroke="#38A169" name="Forecast" strokeWidth={2} strokeDasharray="5 5" />
                            <Line type="monotone" dataKey="target" stroke="#DD6B20" name="Target" strokeWidth={1} strokeDasharray="3 3" />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </CardContent>
                  </Card>

                  <Card className="bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-700">
                    <CardHeader>
                      <CardTitle>Stock vs Forecast (Recent)</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="h-[300px]">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={stockVsForecast}>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="name" />
                            <YAxis />
                            <Tooltip />
                            <Legend />
                            <Bar dataKey="stock" fill="#3182CE" name="Current Stock" />
                            <Bar dataKey="forecast" fill="#DD6B20" name="Forecast" />
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    </CardContent>
                  </Card>
                </div>

                <div>
                  <Card className="h-full bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-700">
                    <CardHeader>
                      <CardTitle>Stock vs Safety Stock</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="h-[300px]">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={stockVsSafety}>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="name" />
                            <YAxis />
                            <Tooltip />
                            <Legend />
                            <Bar dataKey="stock" fill="#3182CE" name="Current Stock" />
                            <Bar dataKey="safety" fill="#38A169" name="Safety Stock" />
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    </CardContent>
                  </Card>
                </div>
              </div>

              <Card className="bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-700">
                <CardContent className="p-0">
                  <SkuTable data={[]} />
                </CardContent>
              </Card>

              <Card className="mt-6 bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-700">
                <CardHeader className="pb-2">
                  <CardTitle>Order Reasoning Timeline</CardTitle>
                  <p className="text-xs text-muted-foreground">Most recent decisions are shown first</p>
                </CardHeader>
                <CardContent className="pt-0">
                  <div className="flex flex-col gap-4">
                    {decisionTimeline.map((entry) => (
                      <div
                        key={`timeline-${entry.week}`}
                        className="p-4 border rounded-md bg-green-100 dark:bg-green-800/30 border-green-200 dark:border-green-700"
                      >
                        <div className="flex flex-wrap justify-between items-start mb-2 gap-3">
                          <div className="flex items-center gap-3">
                            <Badge variant="default">Week {entry.week}</Badge>
                            <Badge variant="secondary">Order {entry.order}</Badge>
                          </div>
                          <span className="text-xs text-muted-foreground">Inventory {entry.inventory} · Backlog {entry.backlog}</span>
                        </div>
                        <p className="text-xs text-foreground/80">{entry.reason}</p>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </>
          )}
        </div>
      </PageLayout>

      <Modal
        isOpen={assignmentModalOpen}
        onClose={() => {}}
        closeOnOverlayClick={false}
        closeOnEsc={false}
      >
        <ModalHeader>
          <ModalTitle>Join a Game</ModalTitle>
        </ModalHeader>
        <ModalBody>
          <p className="mb-4">{assignmentMessage}</p>
          <p className="text-sm text-muted-foreground">
            Once you have been assigned to a game, log in again to access the dashboard.
          </p>
        </ModalBody>
        <ModalFooter>
          <Button onClick={handleAssignmentLogout}>
            Return to Login
          </Button>
        </ModalFooter>
      </Modal>
    </>
  );
};

export default Dashboard;
