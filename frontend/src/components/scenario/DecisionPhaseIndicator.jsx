/**
 * Decision Phase Indicator Component
 *
 * Displays current round phase and scenarioUser completion status for DAG sequential execution.
 * Shows visual progress through: Waiting → Fulfillment → Replenishment → Completed
 *
 * Migrated to Autonomy UI Kit (shadcn/ui + Tailwind CSS + lucide-react)
 *
 * Props:
 * - phase: Current phase ('waiting', 'fulfillment', 'replenishment', 'completed')
 * - scenarioUsersCompleted: Number of scenarioUsers who have submitted their decision
 * - totalScenarioUsers: Total number of scenarioUsers in the scenario
 * - currentRound: Current round number
 * - phaseStartedAt: Timestamp when current phase started (optional)
 */

import React, { useState, useEffect } from 'react';
import { Card, CardContent, Badge, Progress } from '../common';
import {
  Hourglass as WaitingIcon,
  Truck as ShipIcon,
  ShoppingCart as OrderIcon,
  CheckCircle2 as CompletedIcon,
  Users as PeopleIcon,
} from 'lucide-react';
import { cn } from '@azirella-ltd/autonomy-frontend';

const DecisionPhaseIndicator = ({
  phase = 'waiting',
  scenarioUsersCompleted = 0,
  totalScenarioUsers = 4,
  currentRound = 1,
  phaseStartedAt = null,
}) => {
  // Phase configuration
  const phases = [
    {
      key: 'waiting',
      label: 'Waiting',
      fullLabel: 'Waiting for Round',
      icon: WaitingIcon,
      color: 'secondary',
      bgClass: 'bg-muted',
      textClass: 'text-muted-foreground',
      borderClass: 'border-l-muted-foreground',
      description: 'Round will start shortly',
    },
    {
      key: 'fulfillment',
      label: 'Fulfillment',
      fullLabel: 'Fulfillment Phase',
      icon: ShipIcon,
      color: 'default',
      bgClass: 'bg-primary/10',
      textClass: 'text-primary',
      borderClass: 'border-l-primary',
      description: 'Users fulfill downstream orders (ATP-based)',
    },
    {
      key: 'replenishment',
      label: 'Replenishment',
      fullLabel: 'Replenishment Phase',
      icon: OrderIcon,
      color: 'info',
      bgClass: 'bg-blue-100 dark:bg-blue-950/30',
      textClass: 'text-blue-600 dark:text-blue-400',
      borderClass: 'border-l-blue-500',
      description: 'Users order from upstream suppliers',
    },
    {
      key: 'completed',
      label: 'Completed',
      fullLabel: 'Round Completed',
      icon: CompletedIcon,
      color: 'success',
      bgClass: 'bg-emerald-100 dark:bg-emerald-950/30',
      textClass: 'text-emerald-600 dark:text-emerald-400',
      borderClass: 'border-l-emerald-500',
      description: 'Processing round results',
    },
  ];

  // Find current phase index
  const currentPhaseIndex = phases.findIndex((p) => p.key === phase);
  const currentPhaseConfig = phases[currentPhaseIndex] || phases[0];

  // Calculate completion percentage
  const completionPercentage = totalScenarioUsers > 0 ? (scenarioUsersCompleted / totalScenarioUsers) * 100 : 0;

  // Time elapsed (if phaseStartedAt provided)
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  useEffect(() => {
    if (!phaseStartedAt) {
      setElapsedSeconds(0);
      return;
    }

    const interval = setInterval(() => {
      const now = new Date();
      const started = new Date(phaseStartedAt);
      const elapsed = Math.floor((now - started) / 1000);
      setElapsedSeconds(elapsed);
    }, 1000);

    return () => clearInterval(interval);
  }, [phaseStartedAt]);

  const formatElapsed = (seconds) => {
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${minutes}m ${secs}s`;
  };

  const Icon = currentPhaseConfig.icon;

  return (
    <Card className={cn('mb-4 border-l-4', currentPhaseConfig.borderClass)}>
      <CardContent className="pt-4">
        <div className="space-y-4">
          {/* Header */}
          <div className="flex justify-between items-start">
            <div className="flex items-center gap-4">
              <div
                className={cn(
                  'flex items-center justify-center w-12 h-12 rounded-full',
                  currentPhaseConfig.bgClass
                )}
              >
                <Icon className={cn('h-6 w-6', currentPhaseConfig.textClass)} />
              </div>
              <div>
                <h3 className="text-lg font-semibold">
                  Round {currentRound} - {currentPhaseConfig.fullLabel}
                </h3>
                <p className="text-sm text-muted-foreground">
                  {currentPhaseConfig.description}
                </p>
              </div>
            </div>

            {/* Phase badge and elapsed time */}
            <div className="flex flex-col items-end gap-1">
              <Badge variant={currentPhaseConfig.color} className="gap-1">
                <Icon className="h-3 w-3" />
                {currentPhaseConfig.fullLabel}
              </Badge>
              {phaseStartedAt && elapsedSeconds > 0 && phase !== 'completed' && (
                <span className="text-xs text-muted-foreground">
                  Elapsed: {formatElapsed(elapsedSeconds)}
                </span>
              )}
            </div>
          </div>

          {/* Stepper */}
          <div className="flex items-center justify-between">
            {phases.map((phaseConfig, index) => {
              const StepIcon = phaseConfig.icon;
              const isCompleted = index < currentPhaseIndex;
              const isCurrent = index === currentPhaseIndex;
              const isPending = index > currentPhaseIndex;

              return (
                <React.Fragment key={phaseConfig.key}>
                  {/* Step */}
                  <div className="flex flex-col items-center flex-1">
                    <div
                      className={cn(
                        'flex items-center justify-center w-10 h-10 rounded-full border-2 transition-colors',
                        isCompleted && 'bg-primary border-primary text-primary-foreground',
                        isCurrent && 'bg-primary/10 border-primary text-primary',
                        isPending && 'bg-muted border-muted-foreground/30 text-muted-foreground'
                      )}
                    >
                      {isCompleted ? (
                        <CompletedIcon className="h-5 w-5" />
                      ) : (
                        <StepIcon className="h-5 w-5" />
                      )}
                    </div>
                    <span
                      className={cn(
                        'text-xs mt-1 text-center',
                        isCurrent ? 'font-medium text-foreground' : 'text-muted-foreground'
                      )}
                    >
                      {phaseConfig.label}
                    </span>
                  </div>

                  {/* Connector line (except after last step) */}
                  {index < phases.length - 1 && (
                    <div
                      className={cn(
                        'flex-1 h-0.5 mx-2 -mt-4',
                        index < currentPhaseIndex ? 'bg-primary' : 'bg-muted-foreground/30'
                      )}
                    />
                  )}
                </React.Fragment>
              );
            })}
          </div>

          {/* ScenarioUser completion status (only show during active phases) */}
          {(phase === 'fulfillment' || phase === 'replenishment') && (
            <div className="space-y-2">
              <div className="flex items-center gap-3">
                <PeopleIcon className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm text-muted-foreground">
                  Users Completed: <strong className="text-foreground">{scenarioUsersCompleted}</strong> / {totalScenarioUsers}
                </span>
                <span className="text-xs text-muted-foreground">
                  ({completionPercentage.toFixed(0)}%)
                </span>
              </div>
              <Progress
                value={completionPercentage}
                className={cn(
                  'h-2',
                  completionPercentage === 100 && '[&>div]:bg-emerald-500'
                )}
              />
            </div>
          )}

          {/* Completion message */}
          {phase === 'completed' && (
            <div className="p-3 bg-emerald-100 dark:bg-emerald-950/30 rounded-lg text-center">
              <p className="text-sm text-emerald-700 dark:text-emerald-300">
                All scenarioUsers have submitted their decisions. Processing round results...
              </p>
            </div>
          )}

          {/* Waiting message */}
          {phase === 'waiting' && (
            <div className="p-3 bg-muted rounded-lg text-center">
              <p className="text-sm text-muted-foreground">
                Waiting for round to start. Please stand by.
              </p>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default DecisionPhaseIndicator;
