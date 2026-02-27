import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Alert,
  AlertDescription,
  Button,
  Card,
  Spinner,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '../components/common';
import { ArrowLeft } from 'lucide-react';
import simulationApi from '../services/api';
import SupplyChain3D from '../components/visualization/SupplyChain3D';
import TimelineVisualization from '../components/visualization/TimelineVisualization';
import GeospatialSupplyChain from '../components/visualization/GeospatialSupplyChain';
import PredictiveAnalyticsDashboard from '../components/analytics/PredictiveAnalyticsDashboard';
import {
  extractVisualizationData,
  transformGameHistory,
} from '../utils/visualizationDataHelpers';

export default function ScenarioVisualizations() {
  const { scenarioId } = useParams();
  const navigate = useNavigate();
  const [tabValue, setTabValue] = useState('3d');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [gameState, setGameState] = useState(null);
  const [gameHistory, setGameHistory] = useState([]);
  const [visualizationData, setVisualizationData] = useState({
    sites: [],
    edges: [],
    inventoryData: {},
    activeFlows: [],
  });

  // Fetch game data
  useEffect(() => {
    const fetchGameData = async () => {
      try {
        setLoading(true);
        setError(null);

        // Fetch current game state
        const stateResponse = await simulationApi.getScenarioState(scenarioId);
        setGameState(stateResponse);

        // Extract visualization data from current state
        const vizData = extractVisualizationData(stateResponse);
        setVisualizationData(vizData);

        // Fetch game history for timeline visualization
        try {
          const historyResponse = await simulationApi.getPeriods(scenarioId);
          const formattedHistory = transformGameHistory(historyResponse);
          setGameHistory(formattedHistory);
        } catch (histError) {
          console.warn('Failed to fetch game history:', histError);
          // Continue without history - timeline tab will show message
        }

        setLoading(false);
      } catch (err) {
        console.error('Failed to fetch game data:', err);
        setError(err.message || 'Failed to load scenario data');
        setLoading(false);
      }
    };

    if (scenarioId) {
      fetchGameData();
    }
  }, [scenarioId]);

  const handleBackToReport = () => {
    navigate(`/scenarios/${scenarioId}/report`);
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center min-h-[80vh]">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="container mx-auto py-8 px-4">
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
        <Button onClick={handleBackToReport}>
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back to Report
        </Button>
      </div>
    );
  }

  // Visualization components use "nodes" terminology (D3/graph standard)
  // but extractVisualizationData returns "sites" (AWS SC DM terminology)
  const { sites: nodes, edges, inventoryData, activeFlows } = visualizationData;
  const hasData = nodes.length > 0;

  return (
    <div className="w-full h-[calc(100vh-100px)]">
      {/* Header */}
      <Card className="mx-4 mt-4 mb-4">
        <div className="p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Button variant="ghost" size="sm" onClick={handleBackToReport}>
                <ArrowLeft className="h-4 w-4 mr-2" />
                Back to Report
              </Button>
              <h1 className="text-xl font-semibold">Supply Chain Visualizations</h1>
            </div>
            <p className="text-sm text-muted-foreground">Scenario ID: {scenarioId}</p>
          </div>

          {/* Tabs */}
          <Tabs value={tabValue} onValueChange={setTabValue} className="mt-4">
            <TabsList>
              <TabsTrigger value="3d">3D Visualization</TabsTrigger>
              <TabsTrigger value="timeline" disabled={gameHistory.length === 0}>
                Timeline Replay
              </TabsTrigger>
              <TabsTrigger value="geo">Geospatial Map</TabsTrigger>
              <TabsTrigger value="analytics">Predictive Analytics</TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
      </Card>

      {/* No Data Warning */}
      {!hasData && (
        <Alert className="mx-4 mb-4">
          <AlertDescription>
            No visualization data available. The game may not have started yet or
            data is still loading.
          </AlertDescription>
        </Alert>
      )}

      {/* Tab Content */}
      {hasData && (
        <div className="px-4">
          <Tabs value={tabValue} onValueChange={setTabValue}>
            <TabsContent value="3d">
              <Card className="h-[calc(100vh-280px)]">
                <SupplyChain3D
                  nodes={nodes}
                  edges={edges}
                  inventoryData={inventoryData}
                  activeFlows={activeFlows}
                />
              </Card>
            </TabsContent>

            <TabsContent value="timeline">
              {gameHistory.length > 0 ? (
                <Card className="h-[calc(100vh-280px)]">
                  <TimelineVisualization
                    gameHistory={gameHistory}
                    nodes={nodes}
                    edges={edges}
                  />
                </Card>
              ) : (
                <Alert>
                  <AlertDescription>
                    No game history available for timeline replay. Play some rounds first!
                  </AlertDescription>
                </Alert>
              )}
            </TabsContent>

            <TabsContent value="geo">
              <Card className="h-[calc(100vh-280px)]">
                <GeospatialSupplyChain
                  nodes={nodes}
                  edges={edges}
                  inventoryData={inventoryData}
                  activeFlows={activeFlows}
                />
              </Card>
            </TabsContent>

            <TabsContent value="analytics">
              <Card className="h-[calc(100vh-280px)] overflow-auto p-4">
                <PredictiveAnalyticsDashboard
                  scenarioId={scenarioId}
                  nodeId={nodes[0]?.id} // Default to first site
                />
              </Card>
            </TabsContent>
          </Tabs>
        </div>
      )}
    </div>
  );
}
