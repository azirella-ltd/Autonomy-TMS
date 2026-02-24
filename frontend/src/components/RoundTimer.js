import React, { useState, useEffect, useCallback, useRef } from "react";
import { Clock, CheckCircle, AlertTriangle } from "lucide-react";
import { Button, Badge, Textarea, Input } from "./common";
import { Progress } from "./common";
import { useToast } from "./common";
import simulationApi from "../services/api";
import {
  formatTimePeriodDate,
  normalizeTimeBucket,
  getTimePeriodLabel,
} from "../utils/timePeriodUtils";

const RoundTimer = ({
  gameId,
  scenarioUserId,
  roundNumber,
  onOrderSubmit,
  isPlayerTurn,
  orderComment = "",
  onCommentChange,
  readOnly = false,
  timeBucket = "week",
  periodStart,
  periodLabel,
}) => {
  const [timeLeft, setTimeLeft] = useState(60);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [orderQuantity, setOrderQuantity] = useState(0);
  const [roundEndsAt, setRoundEndsAt] = useState(null);
  const [hasSubmitted, setHasSubmitted] = useState(false);
  const { toast } = useToast();
  const timerRef = useRef(null);

  const normalizedBucket = normalizeTimeBucket(timeBucket);
  const resolvedPeriodLabel =
    periodLabel || getTimePeriodLabel(normalizedBucket);
  const periodDate = formatTimePeriodDate(periodStart, normalizedBucket);
  const headerLabel = periodDate
    ? `${resolvedPeriodLabel} ${roundNumber} (${periodDate})`
    : `${resolvedPeriodLabel} ${roundNumber}`;

  const instructionText = readOnly
    ? "Viewing order entry details for this role"
    : `Place your order for the next ${resolvedPeriodLabel.toLowerCase()}`;

  // Handle order submission
  const handleSubmit = useCallback(
    async (quantity) => {
      if (readOnly) {
        return;
      }

      if (quantity === null || quantity < 0) return;

      setIsSubmitting(true);
      try {
        await onOrderSubmit(quantity, orderComment);
        setHasSubmitted(true);
        toast({
          title: "Order submitted!",
          variant: "success",
          duration: 2000,
        });
      } catch (error) {
        console.error("Error submitting order:", error);
        toast({
          title: "Error submitting order",
          description: error.message,
          variant: "destructive",
          duration: 5000,
        });
      } finally {
        setIsSubmitting(false);
      }
    },
    [readOnly, onOrderSubmit, orderComment, toast]
  );

  // Fetch round status when component mounts or round changes
  useEffect(() => {
    const fetchRoundStatus = async () => {
      try {
        const status = await simulationApi.getRoundStatus(gameId);
        setRoundEndsAt(new Date(status.ends_at));

        // Check if scenarioUser has already submitted
        if (status.submitted_players?.some((p) => p.id === scenarioUserId)) {
          setHasSubmitted(true);
          const playerOrder = status.submitted_players.find(
            (p) => p.id === scenarioUserId
          );
          if (playerOrder) {
            setOrderQuantity(playerOrder.quantity);
            if (playerOrder.comment && onCommentChange) {
              onCommentChange(playerOrder.comment);
            }
          }
        }
      } catch (error) {
        console.error("Error fetching round status:", error);
      }
    };

    fetchRoundStatus();

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, [gameId, scenarioUserId, roundNumber, onCommentChange]);

  // Set up timer
  useEffect(() => {
    if (!roundEndsAt) return;

    const updateTimer = () => {
      const now = new Date();
      const diff = Math.max(0, Math.floor((roundEndsAt - now) / 1000));
      setTimeLeft(diff);

      // If time's up and we haven't submitted, submit zero
      if (diff <= 0 && !hasSubmitted && isPlayerTurn) {
        handleSubmit(0);
      }
    };

    // Initial update
    updateTimer();

    // Set up interval
    timerRef.current = setInterval(updateTimer, 1000);

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, [roundEndsAt, hasSubmitted, isPlayerTurn, handleSubmit]);

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs < 10 ? "0" : ""}${secs}`;
  };

  const progressValue = (timeLeft / 60) * 100; // Assuming 60 seconds per round

  return (
    <div className="flex flex-col gap-4 p-4 border rounded-lg bg-white shadow-sm">
      <div className="flex w-full justify-between items-center">
        <p className="text-lg font-bold">{headerLabel}</p>
        <div className="flex items-center gap-2">
          <Clock
            className={`h-5 w-5 ${
              timeLeft < 10 ? "text-red-500" : "text-gray-500"
            }`}
          />
          <span
            className={`font-semibold ${
              timeLeft < 10 ? "text-red-500" : "text-gray-700"
            }`}
          >
            {formatTime(timeLeft)}
          </span>
          {hasSubmitted ? (
            <Badge variant="success" className="p-1 rounded-md">
              <span className="flex items-center gap-1">
                <CheckCircle className="h-4 w-4" />
                <span>Submitted: {orderQuantity}</span>
              </span>
            </Badge>
          ) : (
            <Badge
              variant={isPlayerTurn ? "warning" : "secondary"}
              className="p-1 rounded-md"
            >
              {readOnly
                ? isPlayerTurn
                  ? "Active"
                  : "Waiting"
                : isPlayerTurn
                ? "Your Turn"
                : "Waiting..."}
            </Badge>
          )}
        </div>
      </div>

      <Progress
        value={progressValue}
        size="sm"
        className={`w-full rounded-full ${
          timeLeft < 10
            ? "[&>div]:bg-red-500"
            : "[&>div]:bg-green-500"
        }`}
      />

      {((isPlayerTurn && !hasSubmitted) || readOnly) && (
        <div className="flex flex-col w-full gap-4 mt-4">
          <p className="text-sm text-gray-600">{instructionText}</p>
          <div className="flex w-full items-start gap-3">
            <Input
              type="number"
              min={0}
              value={orderQuantity}
              onChange={(e) => setOrderQuantity(parseInt(e.target.value) || 0)}
              className="w-36"
              disabled={readOnly}
            />
            <Textarea
              value={orderComment}
              onChange={(event) => onCommentChange?.(event.target.value)}
              placeholder="Why are you ordering this amount?"
              className="flex-1 min-h-[80px] resize-y"
              disabled={readOnly}
            />
            <Button
              onClick={() => handleSubmit(orderQuantity)}
              loading={isSubmitting}
              disabled={readOnly}
            >
              {isSubmitting ? "Submitting..." : "Submit Order"}
            </Button>
          </div>
          {!readOnly && timeLeft < 10 && (
            <div className="flex items-center gap-1 text-sm text-red-500">
              <AlertTriangle className="h-4 w-4" />
              <span>Time is running out! Submit your order soon.</span>
            </div>
          )}
        </div>
      )}

      {!readOnly && !isPlayerTurn && !hasSubmitted && (
        <p className="text-sm text-gray-500 text-center">
          Waiting for your turn to place an order...
        </p>
      )}

      {readOnly && !isPlayerTurn && !hasSubmitted && (
        <p className="text-sm text-gray-500 text-center">
          Waiting for this role to place an order...
        </p>
      )}

      {hasSubmitted && (
        <p
          className={`text-sm text-center ${
            readOnly ? "text-gray-600" : "text-green-600"
          }`}
        >
          {readOnly
            ? `Submitted order: ${orderQuantity} units.`
            : `Your order of ${orderQuantity} units has been submitted for this ${resolvedPeriodLabel.toLowerCase()}.`}
        </p>
      )}
    </div>
  );
};

export default RoundTimer;
