import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import PageLayout from "../components/PageLayout";
import RoundTimer from "../components/RoundTimer";
import FallbackWarningModal from "../components/scenario/FallbackWarningModal";
import {
  DEFAULT_SITE_TYPE_DEFINITIONS,
  buildSiteTypeLabelMap,
} from "../services/supplyChainConfigService";
import {
  getTimePeriodLabel,
  formatTimePeriodDate,
  normalizeTimeBucket,
  buildTimePeriodDisplay,
} from "../utils/timePeriodUtils";
import {
  Card,
  CardContent,
  Button,
  Badge,
  Alert,
  Spinner,
  Input,
  Select,
  SelectOption,
  Modal,
  ModalHeader,
  ModalTitle,
  ModalBody,
  ModalFooter,
  Tabs,
  TabsList,
  Tab,
  TabPanel,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  useToast,
} from "../components/common";
import { cn } from "../lib/utils/cn";
import { AlertTriangle, Download } from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { useWebSocket } from "../contexts/WebSocketContext";
import { useAuth } from "../contexts/AuthContext";
import { getAdminDashboardPath } from "../utils/adminDashboardState";
import simulationApi from "../services/api";

const ScenarioBoard = () => {
  const { scenarioId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const { user, isGroupAdmin } = useAuth();
  const [gameState, setGameState] = useState(null);
  const [gameDetails, setGameDetails] = useState(null);
  const [assignedRole, setAssignedRole] = useState("");
  const [viewingRole, setViewingRole] = useState("");
  const [assignedPlayerId, setAssignedPlayerId] = useState(null);
  const [viewingPlayerId, setViewingPlayerId] = useState(null);
  const [isSpectatorMode, setIsSpectatorMode] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isPlayerTurn, setIsPlayerTurn] = useState(false);
  const [associatedGames, setAssociatedGames] = useState([]);
  const [orderComment, setOrderComment] = useState("");
  const [orderHistory, setOrderHistory] = useState([]);
  const [reportLoading, setReportLoading] = useState(false);
  const [gameReport, setGameReport] = useState(null);
  const [reportError, setReportError] = useState(null);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [activeSettingsTab, setActiveSettingsTab] = useState("general");
  const { gameStatus } = useWebSocket();

  // Fallback warning modal state
  const [fallbackWarningOpen, setFallbackWarningOpen] = useState(false);
  const [currentFallbacks, setCurrentFallbacks] = useState({});
  const acknowledgedFallbacksRef = useRef(new Set()); // Track which fallbacks user has acknowledged

  const timeBucket = normalizeTimeBucket(
    gameState?.time_bucket || gameDetails?.time_bucket
  );
  const periodLabelSingular = getTimePeriodLabel(timeBucket);
  const currentPeriodDisplay = useMemo(() => {
    if (!gameState?.current_round) {
      return "";
    }
    const referenceDate =
      gameState.current_period_start || gameDetails?.current_period_start;
    return buildTimePeriodDisplay(
      gameState.current_round,
      timeBucket,
      referenceDate
    );
  }, [
    gameDetails?.current_period_start,
    gameState?.current_period_start,
    gameState?.current_round,
    timeBucket,
  ]);

  const playerOptions = useMemo(
    () => (Array.isArray(gameDetails?.scenarioUsers) ? gameDetails.scenarioUsers : []),
    [gameDetails?.scenarioUsers]
  );
  const isReadOnlyView =
    !assignedPlayerId || viewingPlayerId !== assignedPlayerId;

  const handleRoleSelection = useCallback(
    (playerIdValue) => {
      const selected = playerOptions.find(
        (scenarioUser) => String(scenarioUser.id) === String(playerIdValue)
      );
      if (selected) {
        setViewingPlayerId(selected.id);
        setViewingRole(selected.role);
      } else {
        setViewingPlayerId(null);
        setViewingRole("");
      }
      setOrderComment("");
    },
    [playerOptions]
  );

  const siteTypeLabelMap = useMemo(
    () =>
      buildSiteTypeLabelMap(
        gameDetails?.config?.site_type_definitions || DEFAULT_SITE_TYPE_DEFINITIONS
      ),
    [gameDetails?.config?.site_type_definitions]
  );

  const formatRoleLabel = useCallback(
    (role) => {
      if (!role) {
        return "Unknown";
      }
      const key = role.toString().toLowerCase();
      if (siteTypeLabelMap[key]) {
        return siteTypeLabelMap[key];
      }
      return key
        .split("_")
        .filter(Boolean)
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(" ");
    },
    [siteTypeLabelMap]
  );

  const viewingIsCurrent = useMemo(() => {
    if (!gameState || !viewingRole) {
      return false;
    }
    return gameState.current_player_turn === viewingRole;
  }, [gameState, viewingRole]);

  // Update game state when game ID changes
  useEffect(() => {
    const fetchGameState = async () => {
      if (scenarioId) {
        try {
          const state = await simulationApi.getGameState(scenarioId);
          setGameState(state);

          // Update derived state
          if (state.current_round) {
            setIsPlayerTurn(
              state.current_round.current_scenario_user_id === state.scenario_user_id
            );
          }

          // Check for AI agent fallbacks in the latest history entry
          const historyEntries = state?.config?.history || [];
          if (historyEntries.length > 0) {
            const latestHistory = historyEntries[historyEntries.length - 1];
            const fallbacks = latestHistory?.agent_fallbacks || {};

            // Find new fallbacks that haven't been acknowledged
            const newFallbacks = {};
            Object.entries(fallbacks).forEach(([nodeKey, fallbackInfo]) => {
              const fallbackKey = `${latestHistory.round}-${nodeKey}`;
              if (!acknowledgedFallbacksRef.current.has(fallbackKey)) {
                newFallbacks[nodeKey] = {
                  ...fallbackInfo,
                  node_name: fallbackInfo.node_name || nodeKey,
                };
              }
            });

            // Show warning modal if there are new fallbacks
            if (Object.keys(newFallbacks).length > 0) {
              setCurrentFallbacks(newFallbacks);
              setFallbackWarningOpen(true);
            }
          }
        } catch (error) {
          console.error("Error fetching scenario state:", error);
          toast({
            title: "Error",
            description: "Failed to load scenario state",
            status: "error",
            duration: 5000,
            isClosable: true,
          });
        }
      }
    };

    fetchGameState();
  }, [scenarioId, toast]);

  useEffect(() => {
    if (!viewingPlayerId) {
      setViewingRole("");
      return;
    }
    const selected = playerOptions.find(
      (scenarioUser) => scenarioUser.id === viewingPlayerId
    );
    if (selected && selected.role !== viewingRole) {
      setViewingRole(selected.role);
    }
  }, [playerOptions, viewingPlayerId, viewingRole]);

  // Load list of games created by this admin to allow quick switch
  useEffect(() => {
    (async () => {
      try {
        const games = await simulationApi.getGames();
        const associated = (games || []).filter((g) => {
          const createdByUser = g.created_by === user?.id;
          const isPlayer = Array.isArray(g.scenarioUsers)
            ? g.scenarioUsers.some((p) => p.user_id === user?.id)
            : false;
          return createdByUser || isPlayer;
        });
        setAssociatedGames(associated);
      } catch (e) {
        // ignore
      }
    })();
  }, [user?.id]);

  const dropdownGames = useMemo(() => {
    const games = [...associatedGames];
    if (gameDetails && !games.some((g) => g.id === gameDetails.id)) {
      games.push({ id: gameDetails.id, name: gameDetails.name });
    }
    return games;
  }, [associatedGames, gameDetails]);

  // Load order history and rounds data
  useEffect(() => {
    const fetchRounds = async () => {
      if (scenarioId && viewingPlayerId) {
        try {
          const rounds = await simulationApi.getRounds(scenarioId);
          const history = rounds
            .map((r) => {
              const pr = (r.player_rounds || []).find(
                (p) => p.scenario_user_id === viewingPlayerId
              );
              if (!pr) return null;
              const formattedDate = formatTimePeriodDate(
                r.period_start,
                timeBucket
              );
              return {
                round: r.round_number,
                periodLabel: `${periodLabelSingular} ${r.round_number}${
                  formattedDate ? ` (${formattedDate})` : ""
                }`,
                formattedDate,
                inventory: pr.inventory_after,
                backlog: pr.backorders_after,
                order: pr.order_placed,
                comment: pr.comment || "",
              };
            })
            .filter(Boolean);
          setOrderHistory(history);
        } catch (e) {
          console.error("Failed to load rounds", e);
        }
      }
    };
    fetchRounds();
  }, [scenarioId, viewingPlayerId, gameStatus, timeBucket, periodLabelSingular]);

  // Fetch game details on component mount
  useEffect(() => {
    const fetchGameDetails = async () => {
      try {
        setIsLoading(true);
        const game = await simulationApi.getGame(scenarioId);
        setGameDetails(game);

        const scenarioUsers = Array.isArray(game.scenarioUsers) ? game.scenarioUsers : [];
        const currentUserId = user?.id;
        const assignedPlayer =
          scenarioUsers.find((p) => p.user_id === currentUserId) || null;

        if (assignedPlayer) {
          setAssignedRole(assignedPlayer.role);
          setViewingRole(assignedPlayer.role);
          setAssignedPlayerId(assignedPlayer.id);
          setViewingPlayerId(assignedPlayer.id);
          setIsSpectatorMode(false);
          setIsPlayerTurn(game.current_player_turn === assignedPlayer.role);
        } else {
          const existingViewer =
            scenarioUsers.find((p) => p.id === viewingPlayerId) || scenarioUsers[0] || null;
          setAssignedRole("");
          setAssignedPlayerId(null);
          setIsPlayerTurn(false);
          setIsSpectatorMode(true);
          if (existingViewer) {
            setViewingRole(existingViewer.role);
            setViewingPlayerId(existingViewer.id);
          } else {
            setViewingRole("");
            setViewingPlayerId(null);
          }
        }

        setOrderComment("");

        setIsLoading(false);
      } catch (error) {
        console.error("Error fetching scenario details:", error);
        toast({
          title: "Error",
          description: "Failed to load scenario details. Please try again.",
          status: "error",
          duration: 5000,
          isClosable: true,
        });
        navigate("/scenarios");
      }
    };

    fetchGameDetails();
  }, [scenarioId, navigate, toast, user?.id, viewingPlayerId]);

  useEffect(() => {
    let cancelled = false;
    if (!scenarioId || gameDetails?.status !== "completed") {
      setGameReport(null);
      setReportError(null);
      setReportLoading(false);
      return () => {
        cancelled = true;
      };
    }

    const loadReport = async () => {
      try {
        setReportLoading(true);
        const data = await simulationApi.getReport(scenarioId);
        if (!cancelled) {
          setGameReport(data);
          setReportError(null);
        }
      } catch (error) {
        if (!cancelled) {
          setReportError(
            error?.response?.data?.detail ||
              error?.message ||
              "Failed to load alternative report"
          );
          setGameReport(null);
        }
      } finally {
        if (!cancelled) {
          setReportLoading(false);
        }
      }
    };

    loadReport();

    return () => {
      cancelled = true;
    };
  }, [scenarioId, gameDetails?.status]);

  const handleDownloadReport = useCallback(() => {
    if (!gameReport) return;
    const blob = new Blob([JSON.stringify(gameReport, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `alternative-${scenarioId}-report.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, [gameReport, scenarioId]);

  // Handle fallback warning acknowledgement
  const handleFallbackConfirm = useCallback(() => {
    // Mark all current fallbacks as acknowledged
    const currentRound = gameState?.current_round || 1;
    Object.keys(currentFallbacks).forEach((nodeKey) => {
      acknowledgedFallbacksRef.current.add(`${currentRound}-${nodeKey}`);
    });
    setFallbackWarningOpen(false);
    setCurrentFallbacks({});
    toast({
      title: "Proceeding with Fallback",
      description: "AI agents will use heuristic strategies for this simulation.",
      status: "warning",
      duration: 5000,
      isClosable: true,
    });
  }, [currentFallbacks, gameState?.current_round, toast]);

  // Handle fallback warning cancellation
  const handleFallbackCancel = useCallback(() => {
    setFallbackWarningOpen(false);
    setCurrentFallbacks({});
    toast({
      title: "Alternative Cancelled",
      description: "Returning to alternatives list. Please ensure AI models are properly loaded before starting.",
      status: "info",
      duration: 5000,
      isClosable: true,
    });
    navigate("/alternatives");
  }, [navigate, toast]);

  const formatCurrency = useCallback((value) => {
    if (typeof value !== "number" || Number.isNaN(value)) {
      return "—";
    }
    return `$${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
  }, []);

  // Check if it's the scenarioUser's turn
  useEffect(() => {
    if (!assignedRole || !gameState) {
      if (isPlayerTurn) {
        setIsPlayerTurn(false);
      }
      return;
    }

    const currentPlayerTurn = gameState.current_player_turn === assignedRole;
    if (currentPlayerTurn && !isPlayerTurn) {
      toast({
        title: "Your Turn!",
        description: "It's your turn to place an order.",
        status: "info",
        duration: 5000,
        isClosable: true,
      });
    }
    if (currentPlayerTurn !== isPlayerTurn) {
      setIsPlayerTurn(currentPlayerTurn);
    }
  }, [assignedRole, gameState, isPlayerTurn, toast]);

  // Handle order submission
  const handleOrderSubmit = async (quantity, comment) => {
    if (!assignedPlayerId) {
      return;
    }

    const qty = parseInt(quantity, 10) || 0;
    try {
      await simulationApi.submitOrder(scenarioId, assignedPlayerId, qty, comment);
      toast({
        title: "Order submitted!",
        description: `Order of ${qty} units has been placed.`,
        status: "success",
        duration: 3000,
        isClosable: true,
      });
      setOrderComment("");
      const rounds = await simulationApi.getRounds(scenarioId);
      const history = rounds
        .map((r) => {
          const pr = (r.player_rounds || []).find(
            (p) => p.scenario_user_id === assignedPlayerId
          );
          if (!pr) return null;
          return {
            round: r.round_number,
            inventory: pr.inventory_after,
            backlog: pr.backorders_after,
            order: pr.order_placed,
            comment: pr.comment || "",
          };
        })
        .filter(Boolean);
      setOrderHistory(history);
    } catch (error) {
      console.error("Error submitting order:", error);
      toast({
        title: "Error",
        description: "Failed to submit order. Please try again.",
        status: "error",
        duration: 3000,
        isClosable: true,
      });
    }
  };

  // Render simulation board
  return (
    <PageLayout
      title={gameDetails?.supply_chain_name || gameDetails?.name || "Simulation"}
    >
      <div className="p-4">
        {isGroupAdmin && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => navigate(getAdminDashboardPath())}
            className="mb-4"
          >
            Back to Admin Dashboard
          </Button>
        )}
        {isLoading ? (
          <div className="flex items-center justify-center h-52">
            <Spinner size="lg" />
          </div>
        ) : (
          <div className="flex flex-col gap-6">
            {/* Simulation status bar with round timer */}
            <div className="flex gap-4 flex-wrap lg:flex-nowrap">
              {/* Alternative info card */}
              <Card variant="outlined" padding="default" className="flex-1 min-w-0">
                <CardContent>
                  <div className="flex flex-col gap-4">
                    <div className="flex flex-col">
                      <span className="text-sm text-muted-foreground">
                        Supply Chain
                      </span>
                      <span className="text-lg font-bold">
                        {gameDetails?.supply_chain_name ||
                          "Unassigned Supply Chain"}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="font-bold">Alternative:</span>
                      <Select
                        size="sm"
                        value={String(scenarioId)}
                        onChange={(e) => navigate(`/scenarios/${e.target.value}`)}
                        className="max-w-sm"
                      >
                        {dropdownGames.map((g) => (
                          <SelectOption key={g.id} value={g.id}>
                            {g.name}
                          </SelectOption>
                        ))}
                      </Select>
                    </div>

                    <div className="flex gap-6 flex-wrap">
                      <div className="flex flex-col">
                        <span className="text-sm text-muted-foreground">
                          {periodLabelSingular}
                        </span>
                        <span className="text-xl font-bold">
                          {currentPeriodDisplay ||
                            `${periodLabelSingular} ${
                              gameState?.current_round || 1
                            }`}
                        </span>
                      </div>

                      <div className="flex flex-col">
                        <span className="text-sm text-muted-foreground">
                          Status
                        </span>
                        <Badge
                          variant={
                            gameStatus === "in_progress" ? "success" : "warning"
                          }
                          className="mt-1"
                        >
                          {gameStatus === "in_progress"
                            ? "In Progress"
                            : "Waiting"}
                        </Badge>
                      </div>

                      <div className="flex flex-col flex-1 max-w-[240px]">
                        <span className="text-sm text-muted-foreground">
                          Your Role
                        </span>
                        {isSpectatorMode && playerOptions.length > 0 ? (
                          <Select
                            size="sm"
                            value={viewingPlayerId ? String(viewingPlayerId) : ""}
                            onChange={(event) =>
                              handleRoleSelection(event.target.value)
                            }
                            placeholder="Select role"
                            className="mt-1"
                          >
                            {playerOptions.map((scenarioUser) => (
                              <SelectOption key={scenarioUser.id} value={scenarioUser.id}>
                                {formatRoleLabel(scenarioUser.role)}
                              </SelectOption>
                            ))}
                          </Select>
                        ) : (
                          <Badge
                            variant="info"
                            className="capitalize mt-1"
                          >
                            {formatRoleLabel(viewingRole)}
                          </Badge>
                        )}
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Round timer component */}
              {gameStatus === "in_progress" && viewingPlayerId && (
                <div className="w-full lg:w-[400px]">
                  <RoundTimer
                    scenarioId={scenarioId}
                    scenarioUserId={viewingPlayerId}
                    roundNumber={gameState?.current_round || 1}
                    onOrderSubmit={handleOrderSubmit}
                    isPlayerTurn={viewingIsCurrent}
                    orderComment={orderComment}
                    onCommentChange={setOrderComment}
                    readOnly={isReadOnlyView}
                    timeBucket={timeBucket}
                    periodStart={
                      gameState?.current_period_start ||
                      gameDetails?.current_period_start
                    }
                    periodLabel={periodLabelSingular}
                  />
                </div>
              )}
            </div>

            {gameDetails?.status === "completed" && (
              <Card variant="outlined" padding="default">
                <CardContent>
                  <div className="flex justify-between items-center mb-3">
                    <h3 className="text-lg font-bold">Simulation Summary</h3>
                    <div className="flex items-center gap-2">
                      {reportLoading && <Spinner size="sm" />}
                      {gameReport && (
                        <Button
                          size="sm"
                          onClick={handleDownloadReport}
                          leftIcon={<Download className="h-4 w-4" />}
                        >
                          Download JSON
                        </Button>
                      )}
                    </div>
                  </div>
                  {reportError && (
                    <Alert variant="error" className="mb-3">
                      {reportError}
                    </Alert>
                  )}
                  {!reportLoading && gameReport && (
                    <div className="flex flex-col gap-3">
                      <p className="font-semibold">
                        Total Supply Chain Cost:{" "}
                        {formatCurrency(gameReport.total_cost)}
                      </p>
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Role</TableHead>
                            <TableHead className="text-right">Inventory</TableHead>
                            <TableHead className="text-right">Backlog</TableHead>
                            <TableHead className="text-right">Holding Cost</TableHead>
                            <TableHead className="text-right">Backorder Cost</TableHead>
                            <TableHead className="text-right">Total Cost</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {Object.entries(gameReport.totals || {}).map(
                            ([role, metrics]) => (
                              <TableRow key={role}>
                                <TableCell className="capitalize">{role}</TableCell>
                                <TableCell className="text-right">{metrics.inventory ?? "—"}</TableCell>
                                <TableCell className="text-right">{metrics.backlog ?? "—"}</TableCell>
                                <TableCell className="text-right">
                                  {formatCurrency(metrics.holding_cost)}
                                </TableCell>
                                <TableCell className="text-right">
                                  {formatCurrency(metrics.backorder_cost)}
                                </TableCell>
                                <TableCell className="text-right">
                                  {formatCurrency(metrics.total_cost)}
                                </TableCell>
                              </TableRow>
                            )
                          )}
                        </TableBody>
                      </Table>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            {/* Rest of the simulation board content */}
            <Card variant="outlined" padding="default">
              <CardContent>
                <div className="flex flex-col gap-4">
                  <h3 className="font-bold">
                    {currentPeriodDisplay ||
                      `${periodLabelSingular} ${gameState?.current_round || 1}`}
                  </h3>
                  <div className="h-[300px]">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={orderHistory}>
                        <XAxis
                          dataKey="periodLabel"
                          interval={0}
                          height={80}
                          tickMargin={12}
                          tick={{ angle: -90, textAnchor: "end" }}
                        />
                        <YAxis />
                        <RechartsTooltip
                          labelFormatter={(label, payload) => {
                            const datum = payload?.[0]?.payload;
                            return datum?.formattedDate || label;
                          }}
                        />
                        <Legend />
                        <Line
                          type="monotone"
                          dataKey="inventory"
                          stroke="#8884d8"
                          name="Inventory"
                        />
                        <Line
                          type="monotone"
                          dataKey="backlog"
                          stroke="#82ca9d"
                          name="Backlog"
                        />
                        <Line
                          type="monotone"
                          dataKey="order"
                          stroke="#ff7300"
                          name="Order"
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-1/4">{periodLabelSingular}</TableHead>
                        <TableHead className="w-1/4">Date</TableHead>
                        <TableHead className="w-[15%]">Order</TableHead>
                        <TableHead className="w-[35%]">Comment</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {orderHistory.map((h) => (
                        <TableRow key={h.round}>
                          <TableCell>{`${periodLabelSingular} ${h.round}`}</TableCell>
                          <TableCell>{h.formattedDate || "—"}</TableCell>
                          <TableCell>{h.order}</TableCell>
                          <TableCell className="whitespace-normal break-words">
                            {h.comment || "—"}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>

            {/* Simulation settings modal */}
            <Modal
              isOpen={isModalOpen}
              onClose={() => setIsModalOpen(false)}
              size="xl"
            >
              <ModalHeader>
                <ModalTitle>Simulation Settings</ModalTitle>
              </ModalHeader>
              <ModalBody>
                <Tabs
                  value={activeSettingsTab}
                  onChange={(_, val) => setActiveSettingsTab(val)}
                >
                  <TabsList>
                    <Tab value="general">General</Tab>
                    <Tab value="advanced">Advanced</Tab>
                  </TabsList>
                  <TabPanel value="general">
                    <div className="flex flex-col gap-4 pt-4">
                      <div className="space-y-2">
                        <label className="text-sm font-medium">Alternative Name</label>
                        <Input value={gameDetails?.name || ""} readOnly />
                      </div>
                    </div>
                  </TabPanel>
                  <TabPanel value="advanced">
                    <div className="flex flex-col gap-4 pt-4">
                      <Alert variant="warning">
                        <div>
                          <p className="font-bold">Advanced Settings</p>
                          <p className="text-sm">
                            These settings can affect simulation balance and
                            performance.
                          </p>
                        </div>
                      </Alert>
                    </div>
                  </TabPanel>
                </Tabs>
              </ModalBody>
              <ModalFooter>
                <Button variant="default" onClick={() => setIsModalOpen(false)}>
                  Close
                </Button>
              </ModalFooter>
            </Modal>

            {/* AI Agent Fallback Warning Modal */}
            <FallbackWarningModal
              isOpen={fallbackWarningOpen}
              onClose={() => setFallbackWarningOpen(false)}
              onConfirm={handleFallbackConfirm}
              onCancel={handleFallbackCancel}
              fallbacks={currentFallbacks}
              alternativeName={gameDetails?.name || "the simulation"}
            />
          </div>
        )}
      </div>
    </PageLayout>
  );
};

export default ScenarioBoard;
