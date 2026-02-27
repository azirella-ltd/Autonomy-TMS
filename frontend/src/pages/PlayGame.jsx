import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, AlertDescription, AlertTitle, Spinner } from '../components/common';
import { getUserScenarios } from '../services/dashboardService';
import { useAuth } from '../contexts/AuthContext';
import { AlertTriangle } from 'lucide-react';

/**
 * PlayGame - Redirects scenarioUsers to their active scenario
 * This is the landing page for USER user type
 */
const PlayGame = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const loadGame = async () => {
      try {
        setLoading(true);

        // Fetch user's games
        const games = await getUserScenarios();

        if (games.length === 0) {
          setError('You are not assigned to any games. Please contact your facilitator.');
          setLoading(false);
          return;
        }

        // Find first active scenario or use most recent
        const activeScenario = games.find(g =>
          g.status === 'IN_PROGRESS' || g.status === 'STARTED'
        );
        const targetScenario = activeScenario || games[0];

        // Redirect to game board
        navigate(`/scenarios/${targetScenario.id}`, { replace: true });
      } catch (err) {
        console.error('Failed to load scenario:', err);
        setError('Unable to load your scenario. Please try again later.');
        setLoading(false);
      }
    };

    loadGame();
  }, [navigate]);

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] p-6">
      {loading ? (
        <>
          <Spinner size="lg" />
          <h2 className="text-xl font-semibold mt-6">Loading your scenario...</h2>
        </>
      ) : error ? (
        <Alert variant="warning" className="max-w-md">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>No Active Scenario</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
    </div>
  );
};

export default PlayGame;
