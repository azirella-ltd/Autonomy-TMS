/**
 * Training Compare Page
 *
 * Allows users to compare performance across multiple completed scenarios.
 * Reuses the TenantScenarioComparisonPanel component.
 */

import React, { useState, useEffect } from 'react';
import simulationApi from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';
import TenantScenarioComparisonPanel from '../admin/TenantScenarioComparisonPanel';
import {
  Card,
  CardContent,
  Spinner,
  Alert,
} from '../../components/common';
import { ChartBarIcon } from '@heroicons/react/24/outline';

const TrainingCompare = () => {
  const { user } = useAuth();
  const [games, setGames] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchGames();
  }, []);

  const fetchGames = async () => {
    try {
      setLoading(true);
      const response = await simulationApi.listGames();
      setGames(response?.data || response || []);
      setError(null);
    } catch (err) {
      console.error('Error fetching games:', err);
      setError('Failed to load games');
    } finally {
      setLoading(false);
    }
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
      <div>
        <h1 className="text-2xl font-bold text-foreground">Compare Games</h1>
        <p className="text-muted-foreground mt-1">
          Select completed games to compare performance metrics side by side
        </p>
      </div>

      {error && (
        <Alert variant="destructive">
          {error}
        </Alert>
      )}

      {/* Comparison Panel */}
      <TenantScenarioComparisonPanel
        games={games}
        loading={loading}
        error={error}
        onRefresh={fetchGames}
        groupId={user?.tenant_id}
        currentUserId={user?.id}
        selectedSupplyChainId="all"
      />

      {/* Help Text */}
      <Card>
        <CardContent className="p-4">
          <div className="flex items-start gap-3">
            <ChartBarIcon className="h-5 w-5 text-primary mt-0.5" />
            <div>
              <p className="text-sm font-medium text-foreground">How to Compare</p>
              <p className="text-sm text-muted-foreground mt-1">
                Select multiple completed games from the table above to see a side-by-side
                comparison of key metrics like total cost, service level, and inventory turns.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default TrainingCompare;
