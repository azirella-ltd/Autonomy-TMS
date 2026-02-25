import React, { useState, useEffect } from 'react';
import {
  Alert,
  AlertDescription,
  Button,
  Card,
  CardContent,
  Label,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '../components/common';
import { RefreshCw, BarChart3, Download } from 'lucide-react';
import AggregationAnalytics from '../components/analytics/AggregationAnalytics';
import CapacityAnalytics from '../components/analytics/CapacityAnalytics';
import PolicyEffectiveness from '../components/analytics/PolicyEffectiveness';
import ComparativeAnalytics from '../components/analytics/ComparativeAnalytics';
import simulationApi from '../services/api';

const AnalyticsDashboard = () => {
  const [activeTab, setActiveTab] = useState('aggregation');
  const [games, setGames] = useState([]);
  const [selectedGameId, setSelectedGameId] = useState('');
  const [selectedGame, setSelectedGame] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    fetchGames();
  }, []);

  const fetchGames = async () => {
    setLoading(true);
    setError(null);

    try {
      // Fetch available games
      const result = await simulationApi.getGames();

      if (result.success && result.data) {
        // Filter for games that use SC planning
        const scPlanningGames = result.data.filter(game => game.use_sc_planning);
        setGames(scPlanningGames);

        // Auto-select first game if available
        if (scPlanningGames.length > 0 && !selectedGameId) {
          setSelectedGameId(scPlanningGames[0].id);
          setSelectedGame(scPlanningGames[0]);
        }
      }
    } catch (err) {
      setError('Failed to load games');
    }

    setLoading(false);
  };

  const handleGameChange = (event) => {
    const gameId = event.target.value;
    setSelectedGameId(gameId);
    const game = games.find(g => g.id === gameId);
    setSelectedGame(game);
  };

  const handleRefresh = () => {
    setRefreshKey(prev => prev + 1);
  };

  const handleExportJSON = () => {
    if (selectedGameId) {
      simulationApi.exportAllJSON(selectedGameId);
    }
  };

  return (
    <div className="container mx-auto py-8 px-4 max-w-7xl">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <BarChart3 className="h-10 w-10 text-primary" />
          <h1 className="text-3xl font-bold">Analytics Dashboard</h1>
        </div>
        <p className="text-muted-foreground">
          View analytics and insights for Phase 3 features (Order Aggregation & Capacity Constraints)
        </p>
      </div>

      {/* Game Selector and Controls */}
      <Card className="mb-6">
        <CardContent className="pt-6">
          <div className="flex flex-wrap items-center gap-4">
            <div className="min-w-[300px]">
              <Label htmlFor="game-select">Select Game</Label>
              <select
                id="game-select"
                value={selectedGameId}
                onChange={handleGameChange}
                disabled={loading || games.length === 0}
                className="w-full mt-1 h-10 px-3 rounded-md border border-input bg-background disabled:opacity-50"
              >
                <option value="">Select a game...</option>
                {games.map((game) => (
                  <option key={game.id} value={game.id}>
                    {game.name} (ID: {game.id})
                  </option>
                ))}
              </select>
            </div>

            <div className="flex items-end gap-2">
              <Button
                variant="ghost"
                size="icon"
                onClick={handleRefresh}
                disabled={!selectedGameId}
                title="Refresh data"
              >
                <RefreshCw className="h-4 w-4" />
              </Button>

              <Button
                onClick={handleExportJSON}
                disabled={!selectedGameId}
              >
                <Download className="h-4 w-4 mr-2" />
                Export All (JSON)
              </Button>
            </div>
          </div>

          {games.length === 0 && !loading && (
            <Alert className="mt-4">
              <AlertDescription>
                No games with AWS SC planning features found. Create a game with advanced features enabled to view analytics.
              </AlertDescription>
            </Alert>
          )}

          {error && (
            <Alert variant="destructive" className="mt-4">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>

      {/* Tabs */}
      {selectedGameId && selectedGame && (
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="mb-6">
            <TabsTrigger value="aggregation">Order Aggregation</TabsTrigger>
            <TabsTrigger value="capacity">Capacity Constraints</TabsTrigger>
            <TabsTrigger value="policy">Policy Effectiveness</TabsTrigger>
            <TabsTrigger value="comparative">Comparative Analysis</TabsTrigger>
          </TabsList>

          <TabsContent value="aggregation">
            <AggregationAnalytics key={`agg-${refreshKey}`} gameId={selectedGameId} />
          </TabsContent>

          <TabsContent value="capacity">
            <CapacityAnalytics key={`cap-${refreshKey}`} gameId={selectedGameId} />
          </TabsContent>

          <TabsContent value="policy">
            <PolicyEffectiveness
              key={`pol-${refreshKey}`}
              configId={selectedGame.supply_chain_config_id}
              customerId={selectedGame.customer_id}
            />
          </TabsContent>

          <TabsContent value="comparative">
            <ComparativeAnalytics key={`comp-${refreshKey}`} gameId={selectedGameId} />
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
};

export default AnalyticsDashboard;
