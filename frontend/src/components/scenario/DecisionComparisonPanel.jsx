/**
 * Decision Comparison Panel Component
 *
 * Phase 2: Agent Copilot Mode
 * Shows side-by-side comparison of AI recommendation vs human decision
 * with actual outcomes after round completion.
 *
 * Migrated to Autonomy UI Kit (shadcn/ui + Tailwind CSS + lucide-react)
 *
 * Props:
 * - roundResults: Array of decision comparisons for the round
 * - currentRound: Round number
 * - scenarioUserId: Current scenarioUser ID (to highlight their comparison)
 */

import React, { useState } from 'react';
import {
  Card,
  CardContent,
  Badge,
  Alert,
  AlertTitle,
  AlertDescription,
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
  TableContainer,
  Progress,
} from '../common';
import {
  ArrowRightLeft as CompareIcon,
  ThumbsUp as AcceptedIcon,
  Pencil as ModifiedIcon,
  Ban as RejectedIcon,
  ChevronDown as ExpandMoreIcon,
  ChevronUp as ExpandLessIcon,
  TrendingUp as BetterIcon,
  TrendingDown as WorseIcon,
  Minus as EqualIcon,
  Brain as AgentIcon,
  User as HumanIcon,
  Trophy as TrophyIcon,
} from 'lucide-react';
import { cn } from '../../lib/utils/cn';

const DecisionComparisonPanel = ({
  roundResults = [],
  currentRound,
  scenarioUserId,
}) => {
  const [expanded, setExpanded] = useState(true);

  if (!roundResults || roundResults.length === 0) {
    return null;
  }

  // Calculate aggregate stats
  const aiWins = roundResults.filter(r => r.preference_label === 'ai_better').length;
  const humanWins = roundResults.filter(r => r.preference_label === 'human_better').length;
  const ties = roundResults.filter(r => r.preference_label === 'equivalent').length;
  const totalComparisons = aiWins + humanWins + ties;

  // Get action icon
  const getActionIcon = (action) => {
    switch (action) {
      case 'accepted':
        return <AcceptedIcon className="h-4 w-4 text-emerald-500" />;
      case 'modified':
        return <ModifiedIcon className="h-4 w-4 text-amber-500" />;
      case 'rejected':
        return <RejectedIcon className="h-4 w-4 text-red-500" />;
      default:
        return null;
    }
  };

  // Get preference icon
  const getPreferenceIcon = (preference) => {
    switch (preference) {
      case 'human_better':
        return <BetterIcon className="h-4 w-4 text-emerald-500" />;
      case 'ai_better':
        return <WorseIcon className="h-4 w-4 text-red-500" />;
      case 'equivalent':
        return <EqualIcon className="h-4 w-4 text-blue-500" />;
      default:
        return null;
    }
  };

  // Get preference variant
  const getPreferenceVariant = (preference) => {
    switch (preference) {
      case 'human_better':
        return 'success';
      case 'ai_better':
        return 'error';
      case 'equivalent':
        return 'info';
      default:
        return 'secondary';
    }
  };

  // Format percentage
  const formatPct = (value) => `${(value * 100).toFixed(1)}%`;

  // Calculate cost difference
  const formatCostDiff = (aiCost, humanCost) => {
    const diff = humanCost - aiCost;
    const pct = aiCost > 0 ? ((diff / aiCost) * 100).toFixed(1) : 0;
    if (diff < 0) {
      return (
        <span className="text-emerald-600">
          -${Math.abs(diff).toFixed(2)} ({Math.abs(pct)}% saved)
        </span>
      );
    } else if (diff > 0) {
      return (
        <span className="text-red-600">
          +${diff.toFixed(2)} ({pct}% more)
        </span>
      );
    }
    return <span className="text-muted-foreground">Same</span>;
  };

  const aiWinRate = totalComparisons > 0 ? (aiWins / totalComparisons) * 100 : 0;
  const humanWinRate = totalComparisons > 0 ? (humanWins / totalComparisons) * 100 : 0;

  return (
    <Card className="mb-4 border-l-4 border-l-violet-500">
      <CardContent className="pt-4">
        <div className="space-y-4">
          {/* Header */}
          <div
            className="flex justify-between items-center cursor-pointer"
            onClick={() => setExpanded(!expanded)}
          >
            <div className="flex items-center gap-3">
              <CompareIcon className="h-6 w-6 text-violet-500" />
              <div>
                <h3 className="text-lg font-semibold">
                  Round {currentRound} Decision Comparison
                </h3>
                <div className="flex gap-2 mt-1">
                  <Badge variant="info" className="flex items-center gap-1">
                    <TrophyIcon className="h-3 w-3" />
                    AI: {aiWins}
                  </Badge>
                  <Badge variant="success" className="flex items-center gap-1">
                    <TrophyIcon className="h-3 w-3" />
                    Human: {humanWins}
                  </Badge>
                  <Badge variant="secondary">
                    Tie: {ties}
                  </Badge>
                </div>
              </div>
            </div>
            <button className="p-2 hover:bg-muted rounded-md transition-colors">
              {expanded ? (
                <ExpandLessIcon className="h-5 w-5" />
              ) : (
                <ExpandMoreIcon className="h-5 w-5" />
              )}
            </button>
          </div>

          {expanded && (
            <div className="space-y-4">
              {/* Win Rate Progress */}
              {totalComparisons > 0 && (
                <div>
                  <div className="flex justify-between mb-2">
                    <div className="flex items-center gap-1">
                      <AgentIcon className="h-4 w-4 text-primary" />
                      <span className="text-sm">AI Win Rate</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <span className="text-sm">Human Win Rate</span>
                      <HumanIcon className="h-4 w-4 text-emerald-500" />
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="flex-1">
                      <Progress value={aiWinRate} className="h-2.5" />
                    </div>
                    <span className="text-sm text-muted-foreground w-16 text-center">
                      {formatPct(aiWins / totalComparisons)}
                    </span>
                    <span className="text-sm text-muted-foreground">vs</span>
                    <span className="text-sm text-muted-foreground w-16 text-center">
                      {formatPct(humanWins / totalComparisons)}
                    </span>
                    <div className="flex-1">
                      <Progress
                        value={humanWinRate}
                        className="h-2.5 [&>div]:bg-emerald-500"
                      />
                    </div>
                  </div>
                </div>
              )}

              <hr className="border-border" />

              {/* Detailed Comparison Table */}
              <TableContainer>
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/50">
                      <TableHead>User</TableHead>
                      <TableHead className="text-center">
                        <div className="flex items-center justify-center gap-1">
                          <AgentIcon className="h-4 w-4" />
                          <span>AI Suggested</span>
                        </div>
                      </TableHead>
                      <TableHead className="text-center">
                        <div className="flex items-center justify-center gap-1">
                          <HumanIcon className="h-4 w-4" />
                          <span>Human Decision</span>
                        </div>
                      </TableHead>
                      <TableHead className="text-center">Action</TableHead>
                      <TableHead className="text-center">Cost Impact</TableHead>
                      <TableHead className="text-center">Winner</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {roundResults.map((result, idx) => {
                      const isCurrentPlayer = result.scenario_user_id === scenarioUserId;
                      return (
                        <TableRow
                          key={idx}
                          className={cn(
                            isCurrentPlayer && 'bg-primary/5',
                            'hover:bg-muted/50'
                          )}
                        >
                          <TableCell>
                            <div className="flex items-center gap-2">
                              <span
                                className={cn(
                                  'text-sm',
                                  isCurrentPlayer && 'font-semibold'
                                )}
                              >
                                {result.player_role}
                              </span>
                              {isCurrentPlayer && (
                                <Badge variant="info" size="sm">You</Badge>
                              )}
                            </div>
                          </TableCell>
                          <TableCell className="text-center">
                            <div className="text-primary font-semibold">
                              {result.ai_suggestion} units
                            </div>
                            {result.ai_confidence && (
                              <div className="text-xs text-muted-foreground">
                                ({formatPct(result.ai_confidence)} conf.)
                              </div>
                            )}
                          </TableCell>
                          <TableCell className="text-center">
                            <div
                              className={cn(
                                'font-semibold',
                                result.human_decision !== result.ai_suggestion
                                  ? 'text-amber-600'
                                  : 'text-foreground'
                              )}
                            >
                              {result.human_decision} units
                            </div>
                            {result.human_decision !== result.ai_suggestion && (
                              <div className="text-xs text-muted-foreground">
                                ({result.human_decision > result.ai_suggestion ? '+' : ''}
                                {result.human_decision - result.ai_suggestion})
                              </div>
                            )}
                          </TableCell>
                          <TableCell className="text-center">
                            <div
                              className="inline-flex items-center justify-center"
                              title={result.feedback_action}
                            >
                              {getActionIcon(result.feedback_action)}
                            </div>
                          </TableCell>
                          <TableCell className="text-center">
                            {result.ai_outcome && result.human_outcome ? (
                              <div className="text-sm">
                                {formatCostDiff(
                                  result.ai_outcome.total_cost || 0,
                                  result.human_outcome.total_cost || 0
                                )}
                              </div>
                            ) : (
                              <span className="text-xs text-muted-foreground">
                                Pending
                              </span>
                            )}
                          </TableCell>
                          <TableCell className="text-center">
                            {result.preference_label && result.preference_label !== 'unknown' ? (
                              <Badge
                                variant={getPreferenceVariant(result.preference_label)}
                                className="flex items-center gap-1 w-fit mx-auto"
                              >
                                {getPreferenceIcon(result.preference_label)}
                                {result.preference_label === 'human_better'
                                  ? 'Human'
                                  : result.preference_label === 'ai_better'
                                  ? 'AI'
                                  : 'Tie'}
                              </Badge>
                            ) : (
                              <Badge variant="secondary" size="sm">TBD</Badge>
                            )}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </TableContainer>

              {/* Insights */}
              {humanWins > aiWins && (
                <Alert variant="success">
                  <TrophyIcon className="h-4 w-4" />
                  <AlertTitle>Human Outperforming AI This Round</AlertTitle>
                  <AlertDescription>
                    Human decisions achieved better outcomes in {humanWins} of {totalComparisons} comparisons.
                    Keep trusting your supply chain expertise!
                  </AlertDescription>
                </Alert>
              )}

              {aiWins > humanWins && (
                <Alert variant="info">
                  <AgentIcon className="h-4 w-4" />
                  <AlertTitle>AI Recommendations Were Better</AlertTitle>
                  <AlertDescription>
                    AI suggestions would have yielded better outcomes in {aiWins} of {totalComparisons} comparisons.
                    Consider following AI recommendations more closely.
                  </AlertDescription>
                </Alert>
              )}

              {aiWins === humanWins && ties > 0 && (
                <Alert variant="info">
                  <AlertTitle>Close Match</AlertTitle>
                  <AlertDescription>
                    Human and AI decisions performed similarly this round. Great collaboration!
                  </AlertDescription>
                </Alert>
              )}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default DecisionComparisonPanel;
