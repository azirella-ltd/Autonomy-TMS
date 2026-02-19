/**
 * Training Reports Page
 *
 * Shows completed games and links to their detailed reports.
 * Allows users to review their past game performance.
 */

import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { format } from 'date-fns';
import simulationApi from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Button,
  Spinner,
  Alert,
  Badge,
} from '../../components/common';
import {
  ChartBarIcon,
  ClockIcon,
  TrophyIcon,
  DocumentTextIcon,
} from '@heroicons/react/24/outline';

const TrainingReports = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [games, setGames] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchCompletedGames();
  }, []);

  const fetchCompletedGames = async () => {
    try {
      setLoading(true);
      const response = await simulationApi.listGames();
      // Filter for completed games
      const completedGames = (response?.data || response || [])
        .filter(game =>
          game.status?.toLowerCase() === 'finished' ||
          game.status?.toLowerCase() === 'completed'
        )
        .sort((a, b) => new Date(b.finished_at || b.created_at) - new Date(a.finished_at || a.created_at));
      setGames(completedGames);
      setError(null);
    } catch (err) {
      console.error('Error fetching games:', err);
      setError('Failed to load completed games');
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return '—';
    try {
      return format(new Date(dateString), 'MMM d, yyyy HH:mm');
    } catch {
      return '—';
    }
  };

  const getGameStats = (game) => {
    // Extract basic stats from game data
    const rounds = game.current_round || game.max_rounds || 0;
    return { rounds };
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Game Reports</h1>
          <p className="text-muted-foreground mt-1">
            Review your completed training games and analyze your decisions
          </p>
        </div>
        <Button variant="outline" onClick={fetchCompletedGames}>
          Refresh
        </Button>
      </div>

      {error && (
        <Alert variant="destructive">
          {error}
        </Alert>
      )}

      {/* Games List */}
      {games.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <DocumentTextIcon className="h-16 w-16 text-muted-foreground mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-foreground">No Completed Games</h3>
            <p className="text-muted-foreground mt-2">
              Complete some games to see reports here
            </p>
            <Button
              className="mt-4"
              onClick={() => navigate('/scenarios/new')}
            >
              Start a New Game
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4">
          {games.map((game) => {
            const stats = getGameStats(game);
            return (
              <Card key={game.id} className="hover:shadow-md transition-shadow">
                <CardContent className="p-6">
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-3">
                        <h3 className="text-lg font-semibold text-foreground">
                          {game.name}
                        </h3>
                        <Badge variant="secondary">
                          {stats.rounds} rounds
                        </Badge>
                      </div>
                      <div className="flex items-center gap-4 mt-2 text-sm text-muted-foreground">
                        <span className="flex items-center">
                          <ClockIcon className="h-4 w-4 mr-1" />
                          {formatDate(game.finished_at || game.created_at)}
                        </span>
                        {game.supply_chain_config?.name && (
                          <span className="flex items-center">
                            <ChartBarIcon className="h-4 w-4 mr-1" />
                            {game.supply_chain_config.name}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => navigate(`/scenarios/${game.id}/visualizations`)}
                      >
                        <ChartBarIcon className="h-4 w-4 mr-2" />
                        Charts
                      </Button>
                      <Button
                        size="sm"
                        onClick={() => navigate(`/scenarios/${game.id}/report`)}
                      >
                        <DocumentTextIcon className="h-4 w-4 mr-2" />
                        Full Report
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default TrainingReports;
