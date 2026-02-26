import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { PlusIcon, ArrowPathIcon, UserGroupIcon, ClockIcon } from '@heroicons/react/24/outline';
import simulationApi from '../services/api';
import { toast } from 'react-toastify';

const ScenarioLobby = () => {
  const [games, setGames] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const navigate = useNavigate();

  const fetchGames = async () => {
    try {
      setIsLoading(true);
      const data = await simulationApi.getGames();
      setGames(data);
    } catch (error) {
      console.error('Failed to fetch games:', error);
      toast.error('Failed to load games. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchGames();
    
    // Refresh games every 10 seconds
    const interval = setInterval(fetchGames, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleCreateGame = async () => {
    try {
      setIsCreating(true);
      const newGame = await simulationApi.createGame({
        name: `Game ${new Date().toLocaleString()}`,
        max_scenario_users: 4,
        settings: {
          round_duration: 60, // seconds
          max_rounds: 20,
          starting_inventory: 12,
        },
      });
      navigate(`/scenarios/${newGame.id}`);
    } catch (error) {
      console.error('Failed to create game:', error);
      toast.error('Failed to create game. Please try again.');
    } finally {
      setIsCreating(false);
    }
  };

  const joinGame = async (gameId) => {
    try {
      await simulationApi.joinGame(gameId);
      navigate(`/scenarios/${gameId}`);
    } catch (error) {
      console.error('Failed to join game:', error);
      toast.error('Failed to join game. It may be full or already started.');
    }
  };

  return (
    <div className="max-w-7xl mx-auto pad-8">
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Game Lobby</h1>
        <div className="flex space-x-3">
          <button
            onClick={fetchGames}
            disabled={isLoading}
            className="inline-flex items-center px-4 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50"
          >
            <ArrowPathIcon className={`-ml-1 mr-2 h-5 w-5 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          <button
            onClick={handleCreateGame}
            disabled={isCreating || isLoading}
            className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50"
          >
            <PlusIcon className="-ml-1 mr-2 h-5 w-5" />
            New Game
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="flex justify-center items-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-indigo-500"></div>
        </div>
      ) : games.length === 0 ? (
        <div className="text-center py-12">
          <svg
            className="mx-auto h-12 w-12 text-gray-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <h3 className="mt-2 text-sm font-medium text-gray-900">No games available</h3>
          <p className="mt-1 text-sm text-gray-500">Get started by creating a new game.</p>
          <div className="mt-6">
            <button
              type="button"
              onClick={handleCreateGame}
              disabled={isCreating}
              className="inline-flex items-center px-4 py-2 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50"
            >
              <PlusIcon className="-ml-1 mr-2 h-5 w-5" />
              New Game
            </button>
          </div>
        </div>
      ) : (
        <div className="card-surface overflow-hidden sm:rounded-md">
          <ul className="divide-y divide-gray-200">
            {games.map((game) => (
              <li key={game.id}>
                <div className="px-4 py-4 sm:px-6">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center">
                          <p className="text-sm font-medium text-indigo-600 truncate">
                            {game.name}
                          </p>
                          <p className="ml-2 flex-shrink-0 text-xs text-gray-500">
                            {game.status === 'waiting' ? (
                              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                                Waiting for scenarioUsers
                              </span>
                            ) : game.status === 'in_progress' ? (
                              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                                In Progress
                              </span>
                            ) : (
                              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                                Completed
                              </span>
                            )}
                          </p>
                        </div>
                        <div className="mt-2 flex">
                          <div className="flex items-center text-sm text-gray-500">
                            <UserGroupIcon className="flex-shrink-0 mr-1.5 h-5 w-5 text-gray-400" />
                            <p>
                              {game.users.length}/{game.max_scenario_users} scenarioUsers
                            </p>
                          </div>
                          {game.status === 'in_progress' && (
                            <div className="ml-6 flex items-center text-sm text-gray-500">
                              <ClockIcon className="flex-shrink-0 mr-1.5 h-5 w-5 text-gray-400" />
                              <p>Round {game.current_round} of {game.settings.max_rounds}</p>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="ml-4 flex-shrink-0">
                      {game.status === 'waiting' ? (
                        <button
                          onClick={() => joinGame(game.id)}
                          className="inline-flex items-center px-3 py-1.5 border border-transparent text-xs font-medium rounded-full shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                        >
                          Join Game
                        </button>
                      ) : game.status === 'in_progress' ? (
                        <button
                          onClick={() => navigate(`/scenarios/${game.id}`)}
                          className="inline-flex items-center px-3 py-1.5 border border-transparent text-xs font-medium rounded-full shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                        >
                          View Game
                        </button>
                      ) : (
                        <button
                          onClick={() => navigate(`/scenarios/${game.id}`)}
                          className="inline-flex items-center px-3 py-1.5 border border-transparent text-xs font-medium rounded-full shadow-sm text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500"
                        >
                          View Results
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
      
      <div className="mt-8 card-surface sm:rounded-lg pad-6">
        <div className="pad-6">
          <h3 className="text-lg leading-6 font-medium text-gray-900">How to Play</h3>
          <div className="mt-2 max-w-xl text-sm text-gray-500">
            <p>The supply chain game simulation demonstrates the challenges of supply chain management.</p>
          </div>
          <div className="mt-3 text-sm">
            <Link to="/tutorial" className="font-medium text-indigo-600 hover:text-indigo-500">
              View tutorial <span aria-hidden="true">→</span>
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ScenarioLobby;
