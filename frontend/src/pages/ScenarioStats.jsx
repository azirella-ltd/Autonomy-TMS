import { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import simulationApi from '../services/api';
import { 
  Chart as ChartJS, 
  CategoryScale, 
  LinearScale, 
  BarElement, 
  LineElement, 
  PointElement, 
  Title, 
  Tooltip, 
  Legend, 
  ArcElement 
} from 'chart.js';
import { Line, Pie } from 'react-chartjs-2';
import { format, subDays } from 'date-fns';
import { 
  ArrowUpIcon, 
  ArrowDownIcon, 
  TrophyIcon, 
  UserGroupIcon, 
  ClockIcon, 
  ChartBarIcon,
  StarIcon
} from '@heroicons/react/24/outline';

// Register ChartJS components
ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  Title,
  Tooltip,
  Legend,
  ArcElement
);

const ScenarioStats = () => {
  const { user } = useAuth();
  const [stats, setStats] = useState(null);
  const [history, setHistory] = useState([]);
  const [timeRange, setTimeRange] = useState('7days');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  // Fetch game statistics and history
  useEffect(() => {
    const fetchData = async () => {
      try {
        setIsLoading(true);
        
        // Fetch scenarioUser stats
        const statsResponse = await simulationApi.getScenarioUserStats();
        setStats(statsResponse);
        
        // Fetch game history
        const historyResponse = await simulationApi.getGameHistory();
        setHistory(historyResponse);
        
        setError(null);
      } catch (err) {
        console.error('Failed to fetch game stats:', err);
        setError('Failed to load game statistics. Please try again later.');
      } finally {
        setIsLoading(false);
      }
    };
    
    fetchData();
  }, [timeRange]);

  // Filter history based on selected time range
  const filteredHistory = history.filter(game => {
    const gameDate = new Date(game.ended_at || game.created_at);
    const now = new Date();
    
    switch (timeRange) {
      case '7days':
        return gameDate > subDays(now, 7);
      case '30days':
        return gameDate > subDays(now, 30);
      case 'all':
      default:
        return true;
    }
  });

  // Prepare data for charts
  const preparePerformanceData = () => {
    const labels = [];
    const scores = [];
    const inventories = [];
    const backlogs = [];
    
    // Get last 10 games for the performance chart
    const recentGames = [...filteredHistory]
      .sort((a, b) => new Date(a.ended_at || a.created_at) - new Date(b.ended_at || b.created_at))
      .slice(-10);
    
    recentGames.forEach(game => {
      const scenarioUser = game.scenarioUsers?.find(p => p.user_id === user?.id);
      if (!scenarioUser) return;
      
      const gameDate = new Date(game.ended_at || game.created_at);
      labels.push(format(gameDate, 'MMM d'));
      scores.push(scenarioUser.score || 0);
      inventories.push(scenarioUser.inventory || 0);
      backlogs.push(scenarioUser.backlog || 0);
    });
    
    return {
      labels,
      datasets: [
        {
          label: 'Score',
          data: scores,
          borderColor: 'rgb(99, 102, 241)',
          backgroundColor: 'rgba(99, 102, 241, 0.5)',
          yAxisID: 'y',
        },
        {
          label: 'Inventory',
          data: inventories,
          borderColor: 'rgb(16, 185, 129)',
          backgroundColor: 'rgba(16, 185, 129, 0.5)',
          yAxisID: 'y1',
        },
        {
          label: 'Backlog',
          data: backlogs,
          borderColor: 'rgb(239, 68, 68)',
          backgroundColor: 'rgba(239, 68, 68, 0.5)',
          yAxisID: 'y1',
        },
      ],
    };
  };

  // Prepare data for win/loss pie chart
  const prepareWinLossData = () => {
    if (!stats) return { labels: [], datasets: [] };
    
    const wins = stats.games_won || 0;
    const losses = (stats.games_played || 0) - wins;
    
    return {
      labels: ['Wins', 'Losses'],
      datasets: [
        {
          data: [wins, losses],
          backgroundColor: [
            'rgba(16, 185, 129, 0.8)',
            'rgba(239, 68, 68, 0.8)',
          ],
          borderColor: [
            'rgba(16, 185, 129, 1)',
            'rgba(239, 68, 68, 1)',
          ],
          borderWidth: 1,
        },
      ],
    };
  };

  // Chart options
  const performanceOptions = {
    responsive: true,
    interaction: {
      mode: 'index',
      intersect: false,
    },
    scales: {
      y: {
        type: 'linear',
        display: true,
        position: 'left',
        title: {
          display: true,
          text: 'Score',
        },
      },
      y1: {
        type: 'linear',
        display: true,
        position: 'right',
        grid: {
          drawOnChartArea: false,
        },
        title: {
          display: true,
          text: 'Inventory/Backlog',
        },
      },
    },
    plugins: {
      title: {
        display: true,
        text: 'Recent Game Performance',
      },
      tooltip: {
        callbacks: {
          label: function(context) {
            let label = context.dataset.label || '';
            if (label) {
              label += ': ';
            }
            if (context.parsed.y !== null) {
              label += context.parsed.y;
            }
            return label;
          },
        },
      },
    },
  };

  const winLossOptions = {
    responsive: true,
    plugins: {
      legend: {
        position: 'top',
      },
      title: {
        display: true,
        text: 'Win/Loss Ratio',
      },
    },
  };

  // Stats cards
  const StatCard = ({ title, value, icon: Icon, change, changeType = 'neutral' }) => (
    <div className="card-surface overflow-hidden rounded-lg">
      <div className="pad-6">
        <div className="flex items-center">
          <div className="flex-shrink-0 bg-indigo-500 rounded-md p-3">
            <Icon className="h-6 w-6 text-white" aria-hidden="true" />
          </div>
          <div className="ml-5 w-0 flex-1">
            <dt className="text-sm font-medium text-gray-500 truncate">{title}</dt>
            <dd className="flex items-baseline">
              <div className="text-2xl font-semibold text-gray-900">{value}</div>
              {change && (
                <div className={`ml-2 flex items-baseline text-sm font-semibold ${
                  changeType === 'increase' ? 'text-green-600' : 
                  changeType === 'decrease' ? 'text-red-600' : 'text-gray-500'
                }`}>
                  {changeType === 'increase' ? (
                    <ArrowUpIcon className="h-4 w-4 flex-shrink-0 self-center text-green-500" />
                  ) : changeType === 'decrease' ? (
                    <ArrowDownIcon className="h-4 w-4 flex-shrink-0 self-center text-red-500" />
                  ) : null}
                  <span className="sr-only">
                    {changeType === 'increase' ? 'Increased' : 'Decreased'} by
                  </span>
                  {change}
                </div>
              )}
            </dd>
          </div>
        </div>
      </div>
    </div>
  );

  // Game history item
  const GameHistoryItem = ({ game }) => {
    const scenarioUser = game.scenarioUsers?.find(p => p.user_id === user?.id);
    if (!scenarioUser) return null;
    
    const isWinner = game.winner_id === user?.id;
    const gameDate = new Date(game.ended_at || game.created_at);
    const duration = game.duration_seconds ? 
      `${Math.floor(game.duration_seconds / 60)}m ${game.duration_seconds % 60}s` : 'N/A';
    
    return (
      <div className="card-surface overflow-hidden sm:rounded-lg mb-4">
        <div className="pad-6 flex justify-between items-center">
          <div>
            <h3 className="text-lg leading-6 font-medium text-gray-900">
              {game.name || 'Untitled Game'}
            </h3>
            <p className="mt-1 max-w-2xl text-sm text-gray-500">
              {format(gameDate, 'PPpp')}
            </p>
          </div>
          <span className={`inline-flex items-center px-3 py-0.5 rounded-full text-sm font-medium ${
            isWinner 
              ? 'bg-green-100 text-green-800' 
              : 'bg-gray-100 text-gray-800'
          }`}>
            {isWinner ? 'Victory' : 'Defeat'}
          </span>
        </div>
        <div className="border-t border-gray-200 px-4 py-5 sm:p-0">
          <dl className="sm:divide-y sm:divide-gray-200">
            <div className="py-4 sm:py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
              <dt className="text-sm font-medium text-gray-500">Score</dt>
              <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">
                {scenarioUser.score || 0} points
              </dd>
            </div>
            <div className="py-4 sm:py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
              <dt className="text-sm font-medium text-gray-500">Position</dt>
              <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">
                #{scenarioUser.position || 'N/A'} of {game.scenarioUsers?.length || 0} scenarioUsers
              </dd>
            </div>
            <div className="py-4 sm:py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
              <dt className="text-sm font-medium text-gray-500">Duration</dt>
              <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">
                {duration}
              </dd>
            </div>
          </dl>
        </div>
      </div>
    );
  };

  if (isLoading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-indigo-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-md bg-red-50 p-4">
        <div className="flex">
          <div className="ml-3">
            <h3 className="text-sm font-medium text-red-800">Error loading statistics</h3>
            <p className="mt-2 text-sm text-red-700">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto pad-8">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Game Statistics</h1>
          <p className="mt-1 text-sm text-gray-500">Track your performance and game history</p>
        </div>
        <div className="flex space-x-2">
          <select
            value={timeRange}
            onChange={(e) => setTimeRange(e.target.value)}
            className="mt-1 block pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-md"
          >
            <option value="7days">Last 7 days</option>
            <option value="30days">Last 30 days</option>
            <option value="all">All time</option>
          </select>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 gap-5 mt-5 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard 
          title="Games Played" 
          value={stats?.games_played || 0} 
          icon={TrophyIcon}
          change={`${stats?.games_played_change || 0}%`}
          changeType={stats?.games_played_change > 0 ? 'increase' : stats?.games_played_change < 0 ? 'decrease' : 'neutral'}
        />
        <StatCard 
          title="Win Rate" 
          value={`${stats?.win_rate || 0}%`} 
          icon={StarIcon}
          change={`${stats?.win_rate_change || 0}%`}
          changeType={stats?.win_rate_change > 0 ? 'increase' : stats?.win_rate_change < 0 ? 'decrease' : 'neutral'}
        />
        <StatCard 
          title="Average Score" 
          value={Math.round(stats?.average_score || 0)} 
          icon={ChartBarIcon}
          change={`${stats?.average_score_change || 0}%`}
          changeType={stats?.average_score_change > 0 ? 'increase' : stats?.average_score_change < 0 ? 'decrease' : 'neutral'}
        />
        <StatCard 
          title="Average Game Time" 
          value={stats?.average_game_time ? `${Math.floor(stats.average_game_time / 60)}m` : 'N/A'} 
          icon={ClockIcon}
        />
      </div>

      {/* Charts */}
      <div className="mt-8 grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="card-surface pad-6 rounded-lg">
          {preparePerformanceData().labels.length > 0 ? (
            <Line data={preparePerformanceData()} options={performanceOptions} />
          ) : (
            <div className="text-center py-12 text-gray-500">
              <p>No recent game data available</p>
            </div>
          )}
        </div>
        <div className="card-surface pad-6 rounded-lg">
          {stats?.games_played > 0 ? (
            <div className="h-64 flex items-center justify-center">
              <Pie data={prepareWinLossData()} options={winLossOptions} />
            </div>
          ) : (
            <div className="text-center py-12 text-gray-500">
              <p>Play some games to see your win/loss ratio</p>
            </div>
          )}
        </div>
      </div>

      {/* Game History */}
      <div className="mt-12">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-lg font-medium text-gray-900">Recent Games</h2>
          <span className="text-sm text-gray-500">
            Showing {filteredHistory.length} of {history.length} games
          </span>
        </div>
        
        {filteredHistory.length > 0 ? (
          <div className="space-y-4">
            {filteredHistory.map((game) => (
              <GameHistoryItem key={game.id} game={game} />
            ))}
          </div>
        ) : (
          <div className="text-center py-12 card-surface rounded-lg">
            <UserGroupIcon className="mx-auto h-12 w-12 text-gray-400" />
            <h3 className="mt-2 text-sm font-medium text-gray-900">No games played yet</h3>
            <p className="mt-1 text-sm text-gray-500">
              Get started by joining or creating a game from the lobby.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default ScenarioStats;
