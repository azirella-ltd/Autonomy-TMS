import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  RefreshCw,
  Undo2,
  MessageCircle,
  Users,
  BarChart3,
  Sparkles,
  Eye,
  PieChart,
  Handshake,
  Trophy,
  FileBarChart,
  TrendingUp,
} from "lucide-react";
import simulationApi from "../services/api";
import { useAuth } from "../contexts/AuthContext";
import { toast } from "react-toastify";
import { emitStartupNotices } from "../utils/startupNotices";
import AISuggestion from "../components/scenario/AISuggestion";
import AIConversation from "../components/scenario/AIConversation";
import VisibilityDashboard from "../components/scenario/VisibilityDashboard";
import AIAnalytics from "../components/scenario/AIAnalytics";
import NegotiationPanel from "../components/scenario/NegotiationPanel";
import AchievementsPanel from "../components/scenario/AchievementsPanel";
import LeaderboardPanel from "../components/scenario/LeaderboardPanel";
import ScenarioUserProfileBadge from "../components/scenario/ScenarioUserProfileBadge";
import ReportsPanel from "../components/scenario/ReportsPanel";
import FulfillmentForm from "../components/scenario/FulfillmentForm";
import ReplenishmentForm from "../components/scenario/ReplenishmentForm";
import DecisionPhaseIndicator from "../components/scenario/DecisionPhaseIndicator";
import DecisionComparisonPanel from "../components/scenario/DecisionComparisonPanel";
import OverrideApprovalDialog from "../components/scenario/OverrideApprovalDialog";
import ProbabilisticATPChart from "../components/scenario/ProbabilisticATPChart";
import ProbabilisticPipelineChart from "../components/scenario/ProbabilisticPipelineChart";
import ATPHistoryChart from "../components/scenario/ATPHistoryChart";
import ConformalATPChart from "../components/scenario/ConformalATPChart";
import {
  getTimePeriodLabel,
  normalizeTimeBucket,
  buildTimePeriodDisplay,
} from "../utils/timePeriodUtils";
import { Card, CardContent, Button, Badge, Spinner } from "../components/common";
import { cn } from "../lib/utils/cn";

const ScenarioRoom = () => {
  const { scenarioId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [game, setGame] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [activeTab, setActiveTab] = useState("game");
  const [orderAmount, setOrderAmount] = useState("");
  const [chatMessages, setChatMessages] = useState([]);
  const [message, setMessage] = useState("");
  const chatEndRef = useRef(null);
  const ws = useRef(null);

  // DAG Sequential Execution state (Phase 1)
  const [roundPhase, setRoundPhase] = useState("waiting"); // 'waiting', 'fulfillment', 'replenishment', 'completed'
  const [atpData, setAtpData] = useState(null);
  const [pipelineData, setPipelineData] = useState([]);
  const [playersCompleted, setPlayersCompleted] = useState(0);
  const [demandHistory, setDemandHistory] = useState([]);

  // Agent Copilot Mode state (Phase 2)
  const [overrideDialogOpen, setOverrideDialogOpen] = useState(false);
  const [overrideData, setOverrideData] = useState(null);
  const [pendingApproval, setPendingApproval] = useState(false);
  const [roundComparisonResults, setRoundComparisonResults] = useState([]);
  const [lastComparedRound, setLastComparedRound] = useState(null);

  const timeBucket = normalizeTimeBucket(game?.time_bucket);
  const periodLabelSingular = getTimePeriodLabel(timeBucket);
  const periodLabelPlural = getTimePeriodLabel(timeBucket, { plural: true });
  const currentPeriodDisplay = game?.current_round
    ? buildTimePeriodDisplay(
        game.current_round,
        timeBucket,
        game?.current_period_start
      )
    : "";
  const maxPeriodDisplay = game?.settings?.max_rounds
    ? `${game.settings.max_rounds} ${periodLabelPlural}`
    : "";

  // Fetch game data
  const fetchGame = useCallback(async () => {
    try {
      const gameData = await simulationApi.getGame(scenarioId);
      setGame(gameData);
      return gameData;
    } catch (error) {
      console.error("Failed to fetch alternative:", error);
      toast.error(
        "Failed to load alternative. It may not exist or you may not have permission."
      );
      navigate("/");
    } finally {
      setIsLoading(false);
    }
  }, [scenarioId, navigate]);

  // Set up WebSocket connection
  useEffect(() => {
    // Initialize WebSocket connection
    const setupWebSocket = () => {
      const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const wsUrl = `${wsProtocol}//${window.location.host}/ws/game/${scenarioId}/`;

      ws.current = new WebSocket(wsUrl);

      ws.current.onopen = async () => {
        console.log("WebSocket connected");
        // Obtain a fresh access token via cookie-based refresh and authenticate WS
        try {
          const { access_token } = await simulationApi.refreshToken();
          if (access_token) {
            ws.current.send(
              JSON.stringify({ type: "authenticate", token: access_token })
            );
          }
        } catch (e) {
          console.warn("WS auth token refresh failed:", e?.message || e);
        }
      };

      ws.current.onmessage = (e) => {
        const data = JSON.parse(e.data);
        console.log("WebSocket message received:", data);

        switch (data.type) {
          case "game_update":
            setGame(data.game);
            break;

          case "chat_message":
            setChatMessages((prev) => [...prev, data.message]);
            break;

          case "chat:analysis_complete":
            // What-if analysis completed
            toast.success("What-if analysis complete!");
            console.log("What-if analysis result:", data.data);
            break;

          case "round_phase_change":
            // DAG Sequential: Phase transition (FULFILLMENT → REPLENISHMENT → COMPLETED)
            console.log("Phase changed to:", data.phase);
            setRoundPhase(data.phase.toLowerCase());
            setPlayersCompleted(0); // Reset counter on phase change
            if (data.phase.toUpperCase() === "FULFILLMENT") {
              // Fetch ATP data when fulfillment phase starts
              fetchATPData();
            }
            if (data.phase.toUpperCase() === "REPLENISHMENT") {
              // Fetch pipeline data when replenishment phase starts
              fetchPipelineData();
            }
            if (data.phase.toUpperCase() === "COMPLETED" && data.round_number) {
              // Phase 2 Copilot: Fetch comparison results when round completes
              fetchComparisonResults(data.round_number);
            }
            toast.info(`Round phase: ${data.phase}`);
            break;

          case "scenario_user_action_required":
            // DAG Sequential: Notify scenarioUser it's their turn
            toast.info(`Action required: ${data.action}`);
            break;

          case "fulfillment_completed":
            // DAG Sequential: ScenarioUser submitted fulfillment
            setPlayersCompleted((prev) => prev + 1);
            if (data.scenario_user_id !== currentPlayer?.id) {
              toast.success(`${data.node_key} completed fulfillment`);
            }
            break;

          case "all_players_ready_for_replenishment":
            // DAG Sequential: All users submitted fulfillment
            toast.success("All users completed fulfillment. Transitioning to replenishment phase.");
            break;

          case "agent_recommendation_ready":
            // Phase 2 Copilot: Agent recommendation calculated
            console.log("Agent recommendation ready:", data);
            // Recommendations are fetched directly by components, so this is informational
            break;

          case "override_requires_approval":
            // Phase 2 Copilot: Override exceeds authority, needs approval
            console.log("Override requires approval:", data);
            setOverrideData(data.authority_check);
            setOverrideDialogOpen(true);
            setPendingApproval(true);
            toast.warning(data.message, { autoClose: false });
            break;

          case "approval_requested":
            // Phase 2 Copilot: Manager notified of approval request
            if (user?.role === 'manager' || user?.role === 'executive' || user?.role === 'admin') {
              toast.info(`Approval requested for proposal #${data.proposal_id}`, {
                autoClose: 5000,
              });
            }
            break;

          case "override_approved":
            // Phase 2 Copilot: Manager approved override
            console.log("Override approved:", data);
            if (data.scenario_user_id === currentPlayer?.id) {
              toast.success(data.message);
              setPendingApproval(false);
              setOverrideDialogOpen(false);
            } else {
              toast.info(`ScenarioUser ${data.scenario_user_id}'s override was approved`);
            }
            // Refresh game state
            fetchGame();
            break;

          case "override_rejected":
            // Phase 2 Copilot: Manager rejected override
            console.log("Override rejected:", data);
            if (data.scenario_user_id === currentPlayer?.id) {
              toast.error(data.message);
              setPendingApproval(false);
              setOverrideDialogOpen(false);
            } else {
              toast.info(`ScenarioUser ${data.scenario_user_id}'s override was rejected`);
            }
            // Refresh game state
            fetchGame();
            break;

          case "error":
            toast.error(data.message);
            break;

          default:
            console.warn("Unknown message type:", data.type);
        }
      };

      ws.current.onclose = () => {
        console.log("WebSocket disconnected");
        // Try to reconnect after a delay
        setTimeout(() => {
          if (ws.current) setupWebSocket();
        }, 3000);
      };

      ws.current.onerror = (error) => {
        console.error("WebSocket error:", error);
      };
    };

    setupWebSocket();

    // Initial data fetch
    fetchGame();

    // Clean up WebSocket on unmount
    return () => {
      if (ws.current) {
        ws.current.close();
        ws.current = null;
      }
    };
  }, [scenarioId, navigate, fetchGame]);

  // Auto-scroll chat to bottom when new messages arrive
  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [chatMessages]);

  const handleSubmitOrder = async (e) => {
    e.preventDefault();
    if (!orderAmount || isNaN(orderAmount) || orderAmount < 0) {
      toast.error("Please enter a valid order amount");
      return;
    }

    try {
      setIsSubmitting(true);
      await simulationApi.submitOrder(scenarioId, { amount: parseInt(orderAmount, 10) });
      setOrderAmount("");
      toast.success("Order submitted successfully");
    } catch (error) {
      console.error("Failed to submit order:", error);
      toast.error(error.response?.data?.detail || "Failed to submit order");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSendMessage = (e) => {
    e.preventDefault();
    if (!message.trim()) return;

    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      ws.current.send(
        JSON.stringify({
          type: "chat_message",
          message: message.trim(),
          sender: user.username,
        })
      );
      setMessage("");
    }
  };

  const startSimulation = async () => {
    try {
      setIsSubmitting(true);
      const response = await simulationApi.startGame(scenarioId);  // API still uses game terminology
      toast.success("Simulation started!");
      emitStartupNotices(response, (message) => toast.warn(message));
    } catch (error) {
      console.error("Failed to start simulation:", error);
      toast.error(error.response?.data?.detail || "Failed to start simulation");
    } finally {
      setIsSubmitting(false);
    }
  };

  const leaveSimulation = async () => {
    try {
      await simulationApi.leaveGame(scenarioId);  // API still uses game terminology
      navigate("/");
      toast.success("Left the simulation");
    } catch (error) {
      console.error("Failed to leave simulation:", error);
      toast.error("Failed to leave simulation");
    }
  };

  // DAG Sequential: Fetch ATP data for fulfillment phase
  const fetchATPData = async () => {
    if (!currentPlayer?.id || !game?.use_dag_sequential) return;

    try {
      const response = await simulationApi.get(
        `/mixed-scenarios/${scenarioId}/atp/${currentPlayer.id}`
      );
      setAtpData(response.data);
    } catch (error) {
      console.error("Failed to fetch ATP data:", error);
      // Don't show error toast - ATP may not be available yet
    }
  };

  // DAG Sequential: Fetch pipeline data for replenishment phase
  const fetchPipelineData = async () => {
    if (!currentPlayer?.id || !game?.use_dag_sequential) return;

    try {
      const response = await simulationApi.get(
        `/mixed-scenarios/${scenarioId}/pipeline/${currentPlayer.id}`
      );
      setPipelineData(response.data.in_transit || []);
    } catch (error) {
      console.error("Failed to fetch pipeline data:", error);
    }
  };

  // Phase 2 Copilot: Fetch decision comparison results after round completes
  const fetchComparisonResults = async (roundNumber) => {
    if (!game?.use_dag_sequential) return;

    try {
      const response = await simulationApi.get(
        `/mixed-scenarios/${scenarioId}/rounds/${roundNumber}/decision-comparison`
      );
      setRoundComparisonResults(response.data.comparisons || []);
      setLastComparedRound(roundNumber);
    } catch (error) {
      console.error("Failed to fetch comparison results:", error);
      // Don't show error toast - comparison data may not be available
    }
  };

  // DAG Sequential: Submit fulfillment decision
  const handleFulfillmentSubmit = async (fulfillQty) => {
    if (!currentPlayer?.id) {
      toast.error("User not found");
      return;
    }

    try {
      setIsSubmitting(true);
      const response = await simulationApi.post(
        `/mixed-scenarios/${scenarioId}/rounds/${game.current_round}/fulfillment`,
        {
          scenario_user_id: currentPlayer.id,
          fulfill_qty: fulfillQty,
        }
      );

      toast.success(`Fulfillment submitted: ${fulfillQty} units`);

      // Update ATP data after submission
      setAtpData((prev) => ({
        ...prev,
        current_atp: response.data.updated_atp,
        on_hand: response.data.updated_inventory,
      }));

      // Refresh game state
      await fetchGame();
    } catch (error) {
      console.error("Failed to submit fulfillment:", error);
      toast.error(error.response?.data?.detail || "Failed to submit fulfillment");
      throw error;
    } finally {
      setIsSubmitting(false);
    }
  };

  // DAG Sequential: Submit replenishment decision
  const handleReplenishmentSubmit = async (orderQty) => {
    if (!currentPlayer?.id) {
      toast.error("User not found");
      return;
    }

    try {
      setIsSubmitting(true);
      const response = await simulationApi.post(
        `/mixed-scenarios/${scenarioId}/rounds/${game.current_round}/replenishment`,
        {
          scenario_user_id: currentPlayer.id,
          order_qty: orderQty,
        }
      );

      toast.success(`Replenishment order placed: ${orderQty} units`);
      toast.info(`Order will arrive in round ${response.data.arrival_round}`);

      // Refresh pipeline data
      await fetchPipelineData();

      // Refresh game state
      await fetchGame();
    } catch (error) {
      console.error("Failed to submit replenishment:", error);
      toast.error(error.response?.data?.detail || "Failed to submit replenishment");
      throw error;
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handle override approval (Phase 2: Copilot Mode)
  const handleApproveOverride = async (proposalId) => {
    if (!proposalId) {
      toast.error("Invalid proposal ID");
      return;
    }

    try {
      await simulationApi.post(`/decision-proposals/${proposalId}/approve`);
      toast.success("Override approved");
      setPendingApproval(false);
      setOverrideDialogOpen(false);

      // Refresh game state
      await fetchGame();
    } catch (error) {
      console.error("Failed to approve override:", error);
      toast.error(error.response?.data?.detail || "Failed to approve override");
      throw error;
    }
  };

  // Handle override rejection (Phase 2: Copilot Mode)
  const handleRejectOverride = async (proposalId) => {
    if (!proposalId) {
      toast.error("Invalid proposal ID");
      return;
    }

    try {
      await simulationApi.post(`/decision-proposals/${proposalId}/reject`);
      toast.success("Override rejected - using agent recommendation");
      setPendingApproval(false);
      setOverrideDialogOpen(false);

      // Refresh game state
      await fetchGame();
    } catch (error) {
      console.error("Failed to reject override:", error);
      toast.error(error.response?.data?.detail || "Failed to reject override");
      throw error;
    }
  };

  if (isLoading || !game) {
    return (
      <div className="flex justify-center items-center h-screen">
        <Spinner size="lg" />
      </div>
    );
  }

  const currentPlayer = game.users.find((p) => p.user_id === user.id);
  const isGameMaster = game.created_by === user.id;
  const isGameActive = game.status === "in_progress";
  const isPlayerReady = currentPlayer?.is_ready;
  const allPlayersReady =
    game.users.every((p) => p.is_ready) && game.users.length >= 2;

  // Tab configuration
  const tabs = [
    { id: "chat", label: "Chat", icon: MessageCircle },
    { id: "scenarioUsers", label: "Users", icon: Users },
    { id: "stats", label: "Stats", icon: BarChart3 },
    { id: "atpctp", label: "ATP/CTP", icon: TrendingUp },
    { id: "ai", label: "AI", icon: Sparkles },
    { id: "analytics", label: "Analytics", icon: PieChart },
    { id: "talk", label: "Talk", icon: MessageCircle },
    { id: "visibility", label: "Visibility", icon: Eye },
    { id: "negotiations", label: "Negotiate", icon: Handshake },
    { id: "achievements", label: "Achievements", icon: Trophy },
    { id: "leaderboard", label: "Leaderboard", icon: Trophy },
    { id: "reports", label: "Reports", icon: FileBarChart },
  ];

  // Render simulation board based on user role
  const renderGameBoard = () => {
    if (!isGameActive) {
      return (
        <Card variant="elevated" padding="default">
          <CardContent className="text-center">
            <h2 className="text-xl font-semibold mb-4">
              Waiting for simulation to start
            </h2>
            <p className="text-muted-foreground mb-6">
              {isGameMaster
                ? "You are the simulation master. Start the simulation when all users are ready."
                : "The simulation will start once the simulation master begins."}
            </p>

            <div className="space-y-4 max-w-md mx-auto">
              <div className="bg-muted/50 p-4 rounded-lg">
                <h3 className="font-medium mb-2">
                  Users ({game.users.length}/{game.max_players})
                </h3>
                <ul className="space-y-2">
                  {game.users.map((scenarioUser) => (
                    <li
                      key={user.id}
                      className="flex items-center justify-between"
                    >
                      <span
                        className={cn(
                          user.is_ready ? "text-emerald-600" : "text-muted-foreground"
                        )}
                      >
                        {user.username}
                        {user.is_ready && " \u2713"}
                        {user.user_id === game.created_by && " \uD83D\uDC51"}
                      </span>
                      {user.user_id === user.id && !isPlayerReady && (
                        <Button
                          size="sm"
                          variant="default"
                          onClick={async () => {
                            try {
                              await simulationApi.setPlayerReady(scenarioId, {
                                is_ready: true,
                              });
                              toast.success("You are ready!");
                            } catch (error) {
                              toast.error("Failed to update status");
                            }
                          }}
                          className="bg-emerald-500 hover:bg-emerald-600"
                        >
                          I'm Ready
                        </Button>
                      )}
                    </li>
                  ))}
                </ul>
              </div>

              {isGameMaster && (
                <div className="pt-4">
                  <Button
                    onClick={startSimulation}
                    disabled={!allPlayersReady || isSubmitting}
                    fullWidth
                    loading={isSubmitting}
                  >
                    Start
                  </Button>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      );
    }

    // Render actual simulation board when in progress
    return (
      <Card variant="elevated" padding="default">
        <CardContent>
          {/* DAG Sequential: Phase Indicator */}
          {game?.use_dag_sequential && (
            <DecisionPhaseIndicator
              phase={roundPhase}
              playersCompleted={playersCompleted}
              totalPlayers={game.users.length}
              currentRound={game.current_round}
              phaseStartedAt={game.phase_started_at}
            />
          )}

          <div className="flex justify-between items-center mb-6">
            <h2 className="text-xl font-semibold">{game.name}</h2>
            <div className="flex items-center space-x-4">
              <Badge variant="info" size="lg">
                {currentPeriodDisplay ||
                  `${periodLabelSingular} ${game.current_round || 0}`}{" "}
                {maxPeriodDisplay ? `of ${maxPeriodDisplay}` : ""}
              </Badge>
              <Badge variant="success" size="lg">
                ${game.current_balance || 0}
              </Badge>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* ScenarioUser's inventory and orders */}
            <div className="md:col-span-2 space-y-6">
              <div className="bg-muted/50 p-4 rounded-lg">
                <h3 className="font-medium mb-3">Your Supply Chain</h3>
                <div className="grid grid-cols-3 gap-4">
                  <div className="text-center">
                    <div className="text-2xl font-bold">
                      {currentPlayer?.inventory || 0}
                    </div>
                    <div className="text-sm text-muted-foreground">Inventory</div>
                  </div>
                  <div className="text-center">
                    <div className="text-2xl font-bold">
                      {currentPlayer?.backlog || 0}
                    </div>
                    <div className="text-sm text-muted-foreground">Backlog</div>
                  </div>
                  <div className="text-center">
                    <div className="text-2xl font-bold">
                      {currentPlayer?.incoming_order || 0}
                    </div>
                    <div className="text-sm text-muted-foreground">Incoming</div>
                  </div>
                </div>

                {/* DAG Sequential: Dual-Decision Forms (Phase 1) */}
                {game?.use_dag_sequential ? (
                  <div className="mt-4">
                    {roundPhase === 'fulfillment' && atpData && (
                      <FulfillmentForm
                        atp={atpData.current_atp}
                        demand={
                          (currentPlayer?.incoming_order || 0) +
                          (currentPlayer?.backlog || 0)
                        }
                        currentInventory={currentPlayer?.inventory || 0}
                        backlog={currentPlayer?.backlog || 0}
                        agentMode={currentPlayer?.agent_mode || 'manual'}
                        scenarioId={scenarioId}
                        scenarioUserId={currentPlayer?.id}
                        onSubmit={handleFulfillmentSubmit}
                        disabled={isSubmitting || pendingApproval}
                      />
                    )}

                    {roundPhase === 'replenishment' && (
                      <ReplenishmentForm
                        currentInventory={currentPlayer?.inventory || 0}
                        pipeline={pipelineData}
                        backlog={currentPlayer?.backlog || 0}
                        demandHistory={demandHistory}
                        currentRound={game.current_round}
                        agentMode={currentPlayer?.agent_mode || 'manual'}
                        scenarioId={scenarioId}
                        scenarioUserId={currentPlayer?.id}
                        onSubmit={handleReplenishmentSubmit}
                        disabled={isSubmitting || pendingApproval}
                      />
                    )}

                    {roundPhase === 'waiting' && (
                      <div className="p-4 bg-muted/30 rounded-lg text-center">
                        <p className="text-sm text-muted-foreground">
                          Waiting for round to start...
                        </p>
                      </div>
                    )}

                    {roundPhase === 'completed' && (
                      <div className="space-y-4">
                        <div className="p-4 bg-muted/30 rounded-lg text-center">
                          <p className="text-sm text-muted-foreground">
                            Round completed. Processing results...
                          </p>
                        </div>

                        {/* Phase 2 Copilot: Decision Comparison Panel */}
                        {roundComparisonResults.length > 0 && (
                          <DecisionComparisonPanel
                            roundResults={roundComparisonResults}
                            currentRound={lastComparedRound || game.current_round - 1}
                            scenarioUserId={currentPlayer?.id}
                          />
                        )}
                      </div>
                    )}
                  </div>
                ) : (
                  /* Legacy: Single Order Form */
                  <form onSubmit={handleSubmitOrder} className="mt-4">
                    <label
                      htmlFor="orderAmount"
                      className="block text-sm font-medium text-foreground mb-1"
                    >
                      Place Order (0-
                      {currentPlayer?.inventory +
                        (currentPlayer?.incoming_order || 0) +
                        10}
                      )
                    </label>
                    <div className="flex space-x-2">
                      <input
                        type="number"
                        id="orderAmount"
                        min="0"
                        max={
                          currentPlayer?.inventory +
                          (currentPlayer?.incoming_order || 0) +
                          10
                        }
                        value={orderAmount}
                        onChange={(e) => setOrderAmount(e.target.value)}
                        className="flex-1 h-10 rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                        placeholder="Enter amount"
                      />
                      <Button
                        type="submit"
                        disabled={isSubmitting || !isGameActive}
                        loading={isSubmitting}
                      >
                        Order
                      </Button>
                    </div>
                  </form>
                )}
              </div>

              {/* Game status and history */}
              <Card variant="outlined" padding="default">
                <CardContent>
                  <h3 className="font-medium mb-3">Game Status</h3>
                  <div className="space-y-2">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">
                        Current {periodLabelSingular}:
                      </span>
                      <span className="font-medium">
                        {currentPeriodDisplay || game.current_round}
                        {maxPeriodDisplay ? ` / ${maxPeriodDisplay}` : ""}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Time Left:</span>
                      <span className="font-medium">2:30</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Your Score:</span>
                      <span className="font-medium">
                        {currentPlayer?.score || 0} pts
                      </span>
                    </div>
                  </div>

                  <h4 className="font-medium mt-4 mb-2">Recent Orders</h4>
                  <div className="bg-muted/30 p-3 rounded max-h-32 overflow-y-auto">
                    {game.recent_orders?.length > 0 ? (
                      <ul className="space-y-1">
                        {game.recent_orders.map((order, idx) => (
                          <li key={idx} className="text-sm">
                            <span className="font-medium">{order.scenarioUser}:</span>{" "}
                            Ordered {order.amount} units
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-sm text-muted-foreground">No orders placed yet</p>
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* ScenarioUsers list */}
            <div className="bg-muted/50 p-4 rounded-lg">
              <h3 className="font-medium mb-3">Users</h3>
              <ul className="space-y-3">
                {game.users.map((scenarioUser) => (
                  <li
                    key={user.id}
                    className={cn(
                      "p-3 rounded",
                      user.user_id === user.id
                        ? "bg-primary/10 border border-primary/20"
                        : "bg-card"
                    )}
                  >
                    <div className="flex justify-between items-center">
                      <div>
                        <span className="font-medium">
                          {user.username}
                          {user.user_id === game.created_by && " \uD83D\uDC51"}
                        </span>
                        <p className="text-sm text-muted-foreground">
                          Score: {user.score || 0}
                        </p>
                      </div>
                      <div className="text-right">
                        <div className="text-sm">
                          Inv: {user.inventory || 0}
                        </div>
                        <div className="text-sm text-muted-foreground">
                          Bklog: {user.backlog || 0}
                        </div>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  };

  return (
    <div className="max-w-7xl mx-auto p-8">
      <div className="flex items-center justify-between mb-6">
        <button
          onClick={() => navigate("/")}
          className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <Undo2 className="h-5 w-5 mr-1" />
          Back to Lobby
        </button>

        <div className="flex space-x-2">
          <button
            onClick={() => window.location.reload()}
            className="p-2 text-muted-foreground hover:text-foreground transition-colors"
            title="Refresh"
          >
            <RefreshCw className="h-5 w-5" />
          </button>
          <Button
            variant="destructive"
            size="sm"
            onClick={leaveGame}
          >
            Leave Game
          </Button>
        </div>
      </div>

      <div className="flex flex-col md:flex-row gap-6">
        {/* Main game area */}
        <div className="flex-1">{renderGameBoard()}</div>

        {/* Right sidebar */}
        <div className="w-full md:w-80 flex-shrink-0">
          {/* Tabs */}
          <div className="border-b border-border">
            <nav className="-mb-px flex space-x-1 overflow-x-auto pb-px">
              {tabs.map((tab) => {
                const Icon = tab.icon;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={cn(
                      "py-3 px-2 border-b-2 font-medium text-xs whitespace-nowrap transition-colors",
                      activeTab === tab.id
                        ? "border-primary text-primary"
                        : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
                    )}
                  >
                    <Icon className="h-4 w-4 inline-block mr-1" />
                    {tab.label}
                  </button>
                );
              })}
            </nav>
          </div>

          {/* Tab content */}
          <div className="mt-2">
            {activeTab === "chat" && (
              <Card variant="outlined" padding="none" className="overflow-hidden flex flex-col h-96">
                <div className="p-3 border-b border-border">
                  <h3 className="text-sm font-medium">Game Chat</h3>
                </div>
                <div className="flex-1 overflow-y-auto p-3 space-y-3">
                  {chatMessages.length > 0 ? (
                    chatMessages.map((msg, idx) => (
                      <div key={idx} className="text-sm">
                        <span className="font-medium">{msg.sender}:</span>{" "}
                        <span>{msg.message}</span>
                      </div>
                    ))
                  ) : (
                    <div className="text-center text-muted-foreground text-sm h-full flex items-center justify-center">
                      No messages yet. Say hello!
                    </div>
                  )}
                  <div ref={chatEndRef} />
                </div>
                <div className="p-3 border-t border-border">
                  <form onSubmit={handleSendMessage} className="flex">
                    <input
                      type="text"
                      value={message}
                      onChange={(e) => setMessage(e.target.value)}
                      placeholder="Type a message..."
                      className="flex-1 h-9 rounded-l-md border border-r-0 border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                    />
                    <Button
                      type="submit"
                      className="rounded-l-none"
                    >
                      Send
                    </Button>
                  </form>
                </div>
              </Card>
            )}

            {activeTab === "scenarioUsers" && (
              <Card variant="outlined" padding="default">
                <CardContent>
                  <h3 className="font-medium mb-3">
                    ScenarioUsers ({game.users.length}/{game.max_players})
                  </h3>
                  <ul className="space-y-2">
                    {game.users.map((scenarioUser) => (
                      <li
                        key={user.id}
                        className="flex items-center justify-between p-2 hover:bg-muted/50 rounded transition-colors"
                      >
                        <div className="flex items-center">
                          <div
                            className={cn(
                              "h-2 w-2 rounded-full mr-2",
                              user.is_online ? "bg-emerald-500" : "bg-muted-foreground/30"
                            )}
                          ></div>
                          <span
                            className={cn(
                              user.user_id === user.id && "font-medium text-primary"
                            )}
                          >
                            {user.username}
                            {user.user_id === game.created_by && " \uD83D\uDC51"}
                          </span>
                        </div>
                        <span className="text-sm text-muted-foreground">
                          {user.score || 0} pts
                        </span>
                      </li>
                    ))}
                  </ul>

                  {isGameMaster && (
                    <div className="mt-4 pt-4 border-t border-border">
                      <h4 className="text-sm font-medium mb-2">
                        Game Master Controls
                      </h4>
                      <div className="space-y-2">
                        <Button
                          onClick={startGame}
                          disabled={
                            !allPlayersReady || isSubmitting || isGameActive
                          }
                          fullWidth
                          variant="secondary"
                          loading={isSubmitting}
                        >
                          Start
                        </Button>
                        <Button
                          onClick={async () => {
                            if (
                              window.confirm(
                                "Are you sure you want to end the game?"
                              )
                            ) {
                              try {
                                await simulationApi.endGame(scenarioId);
                                toast.success("Game ended");
                              } catch (error) {
                                toast.error("Failed to end game");
                              }
                            }
                          }}
                          disabled={!isGameActive}
                          fullWidth
                          variant="destructive"
                        >
                          End Game
                        </Button>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            {activeTab === "stats" && (
              <Card variant="outlined" padding="default">
                <CardContent>
                  <h3 className="font-medium mb-3">Game Statistics</h3>
                  <div className="space-y-4">
                    <div>
                      <h4 className="text-sm font-medium text-muted-foreground mb-1">
                        Current {periodLabelSingular}
                      </h4>
                      <div className="w-full bg-muted rounded-full h-2.5">
                        <div
                          className="bg-primary h-2.5 rounded-full transition-all"
                          style={{
                            width: `${
                              (game.current_round / game.settings.max_rounds) *
                              100
                            }%`,
                          }}
                        ></div>
                      </div>
                      <div className="flex justify-between text-xs text-muted-foreground mt-1">
                        <span>0</span>
                        <span>
                          {currentPeriodDisplay ||
                            `${periodLabelSingular} ${game.current_round}`}
                          {maxPeriodDisplay ? ` of ${maxPeriodDisplay}` : ""}
                        </span>
                      </div>
                    </div>

                    <div>
                      <h4 className="text-sm font-medium text-muted-foreground mb-2">
                        Leaderboard
                      </h4>
                      <ol className="space-y-2">
                        {[...game.scenarioUsers]
                          .sort((a, b) => (b.score || 0) - (a.score || 0))
                          .slice(0, 3)
                          .map((scenarioUser, idx) => (
                            <li key={user.id} className="flex items-center">
                              <span className="text-muted-foreground w-6">
                                {idx + 1}.
                              </span>
                              <span className="flex-1">{user.username}</span>
                              <span className="font-medium">
                                {user.score || 0} pts
                              </span>
                            </li>
                          ))}
                      </ol>
                    </div>

                    <div className="pt-2 border-t border-border">
                      <h4 className="text-sm font-medium text-muted-foreground mb-2">
                        Game Info
                      </h4>
                      <dl className="space-y-2">
                        <div className="flex justify-between text-sm">
                          <dt className="text-muted-foreground">
                            {periodLabelSingular} Time:
                          </dt>
                          <dd>{game.settings.round_duration} sec</dd>
                        </div>
                        <div className="flex justify-between text-sm">
                          <dt className="text-muted-foreground">
                            Max {periodLabelPlural}:
                          </dt>
                          <dd>{game.settings.max_rounds}</dd>
                        </div>
                        <div className="flex justify-between text-sm">
                          <dt className="text-muted-foreground">Starting Inventory:</dt>
                          <dd>{game.settings.starting_inventory}</dd>
                        </div>
                      </dl>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            {activeTab === "atpctp" && (
              <div className="space-y-4">
                <h3 className="text-lg font-semibold">
                  ATP/CTP Analysis (Probabilistic)
                </h3>
                <p className="text-sm text-muted-foreground mb-4">
                  Monte Carlo simulation with stochastic lead times showing P10/P50/P90 confidence bands.
                </p>

                {/* Probabilistic ATP Chart */}
                <ProbabilisticATPChart
                  scenarioId={parseInt(scenarioId)}
                  scenarioUserId={currentPlayer?.id}
                  nSimulations={100}
                />

                {/* Probabilistic Pipeline Chart */}
                <ProbabilisticPipelineChart
                  scenarioId={parseInt(scenarioId)}
                  scenarioUserId={currentPlayer?.id}
                  currentRound={game?.current_round}
                  nSimulations={100}
                />

                {/* ATP/CTP Historical Trend Chart */}
                <ATPHistoryChart
                  scenarioId={parseInt(scenarioId)}
                  scenarioUserId={currentPlayer?.id}
                  showCTP={currentPlayer?.role === "MANUFACTURER"}
                  limit={20}
                />

                {/* Conformal Prediction ATP Chart */}
                <div className="mt-4">
                  <h4 className="text-md font-semibold mb-2">
                    Conformal Prediction (Guaranteed Coverage)
                  </h4>
                  <p className="text-xs text-muted-foreground mb-2">
                    Statistical coverage guarantees - the interval will contain the true value
                    at least X% of the time.
                  </p>
                  <ConformalATPChart
                    scenarioId={parseInt(scenarioId)}
                    scenarioUserId={currentPlayer?.id}
                    coverage={0.90}
                    method="adaptive"
                  />
                </div>
              </div>
            )}

            {activeTab === "ai" && (
              <div className="max-h-[600px] overflow-y-auto">
                <AISuggestion
                  scenarioId={scenarioId}
                  scenarioUserRole={currentPlayer?.role || "RETAILER"}
                  onAcceptSuggestion={(orderQty) => {
                    setOrderAmount(orderQty.toString());
                    setActiveTab("game");
                  }}
                />
              </div>
            )}

            {activeTab === "analytics" && (
              <div>
                <AIAnalytics
                  scenarioId={scenarioId}
                  scenarioUserRole={currentPlayer?.role || "RETAILER"}
                />
              </div>
            )}

            {activeTab === "talk" && (
              <div className="h-[600px]">
                <AIConversation
                  scenarioId={scenarioId}
                  scenarioUserRole={currentPlayer?.role || "RETAILER"}
                />
              </div>
            )}

            {activeTab === "visibility" && (
              <div>
                <VisibilityDashboard scenarioId={scenarioId} />
              </div>
            )}

            {activeTab === "negotiations" && (
              <div>
                <NegotiationPanel
                  scenarioId={scenarioId}
                  scenarioUserRole={currentPlayer?.role || "RETAILER"}
                  currentPlayerId={currentPlayer?.id || user?.id}
                />
              </div>
            )}

            {activeTab === "achievements" && (
              <div>
                <AchievementsPanel
                  scenarioId={scenarioId}
                  scenarioUserId={currentPlayer?.id || user?.id}
                />
              </div>
            )}

            {activeTab === "leaderboard" && (
              <div>
                <LeaderboardPanel
                  scenarioUserId={currentPlayer?.id || user?.id}
                />
              </div>
            )}

            {activeTab === "reports" && (
              <div>
                <ReportsPanel scenarioId={scenarioId} />
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Override Approval Dialog (Phase 2: Copilot Mode) */}
      <OverrideApprovalDialog
        open={overrideDialogOpen}
        onClose={() => setOverrideDialogOpen(false)}
        overrideData={overrideData}
        onApprove={handleApproveOverride}
        onReject={handleRejectOverride}
        userRole={user?.role || 'user'}
      />
    </div>
  );
};

export default ScenarioRoom;
