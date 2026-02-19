/**
 * Agent Mode Selector Component
 *
 * Phase 4: Multi-Agent Orchestration
 * Allows players to dynamically switch between manual, copilot, and autonomous modes
 * during active gameplay.
 *
 * Migrated to Autonomy UI Kit (shadcn/ui + Tailwind CSS + lucide-react)
 *
 * Props:
 * - gameId: Game ID
 * - playerId: Player ID
 * - currentMode: Current agent mode
 * - onModeChange: Callback when mode changes successfully
 */

import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Button,
  IconButton,
  Alert,
  Badge,
  Spinner,
  Modal,
  ModalHeader,
  ModalTitle,
  ModalBody,
  ModalFooter,
  Label,
} from '../common';
import {
  User as ManualIcon,
  Brain as CopilotIcon,
  Bot as AutonomousIcon,
  ArrowLeftRight as SwitchIcon,
  CheckCircle2 as CheckIcon,
  AlertTriangle as WarningIcon,
  History as HistoryIcon,
  ChevronDown as ExpandMoreIcon,
  ChevronUp as ExpandLessIcon,
} from 'lucide-react';
import { cn } from '../../lib/utils/cn';
import { api } from '../../services/api';

const AgentModeSelector = ({
  gameId,
  playerId,
  currentMode = 'manual',
  onModeChange,
}) => {
  const [selectedMode, setSelectedMode] = useState(currentMode);
  const [switching, setSwitching] = useState(false);
  const [error, setError] = useState(null);
  const [confirmDialogOpen, setConfirmDialogOpen] = useState(false);
  const [switchResult, setSwitchResult] = useState(null);
  const [modeHistory, setModeHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);

  useEffect(() => {
    setSelectedMode(currentMode);
  }, [currentMode]);

  // Mode configurations
  const modeConfigs = {
    manual: {
      label: 'Manual',
      icon: ManualIcon,
      colorClass: 'text-primary',
      bgClass: 'bg-primary/10',
      badgeVariant: 'default',
      description: 'You make all decisions. Full control over fulfillment and replenishment orders.',
      benefits: [
        'Complete decision control',
        'Learn supply chain dynamics',
        'Develop strategic thinking',
      ],
      considerations: [
        'Requires active participation every round',
        'Performance depends on your expertise',
      ],
    },
    copilot: {
      label: 'Copilot',
      icon: CopilotIcon,
      colorClass: 'text-violet-600 dark:text-violet-400',
      bgClass: 'bg-violet-100 dark:bg-violet-950/30',
      badgeVariant: 'secondary',
      description: 'AI suggests orders, you approve or modify. Collaborative decision-making with explanations.',
      benefits: [
        'AI-powered recommendations',
        'Explanations for each suggestion',
        'Learn from AI reasoning',
        'Override when needed',
      ],
      considerations: [
        'Requires LLM agent availability',
        'May add slight decision delay',
      ],
    },
    autonomous: {
      label: 'Autonomous',
      icon: AutonomousIcon,
      colorClass: 'text-emerald-600 dark:text-emerald-400',
      bgClass: 'bg-emerald-100 dark:bg-emerald-950/30',
      badgeVariant: 'success',
      description: 'AI makes all decisions automatically. Observe and learn from AI performance.',
      benefits: [
        'Fully automated gameplay',
        'Consistent decision-making',
        'Benchmark AI performance',
        'Can override if needed',
      ],
      considerations: [
        'Less hands-on learning',
        'Requires agent configuration',
      ],
    },
  };

  const handleModeSelect = (mode) => {
    setSelectedMode(mode);
    setError(null);
    setSwitchResult(null);
  };

  const handleSwitchClick = () => {
    // Show confirmation dialog if mode is changing
    if (selectedMode !== currentMode) {
      setConfirmDialogOpen(true);
    }
  };

  const handleConfirmSwitch = async () => {
    setConfirmDialogOpen(false);
    setSwitching(true);
    setError(null);

    try {
      const response = await api.post(`/mixed-scenarios/${gameId}/switch-mode`, {
        player_id: playerId,
        new_mode: selectedMode,
        reason: 'user_request',
        force: false,
      });

      const result = response.data;
      setSwitchResult(result);

      // Call callback
      if (onModeChange) {
        onModeChange(result.new_mode);
      }

      // Refresh history
      if (showHistory) {
        fetchModeHistory();
      }
    } catch (err) {
      console.error('Mode switch error:', err);
      setError(err.response?.data?.detail || 'Failed to switch mode');
      // Reset selected mode to current mode
      setSelectedMode(currentMode);
    } finally {
      setSwitching(false);
    }
  };

  const handleCancelSwitch = () => {
    setConfirmDialogOpen(false);
    setSelectedMode(currentMode);
  };

  const fetchModeHistory = async () => {
    setLoadingHistory(true);
    try {
      const response = await api.get(
        `/mixed-scenarios/${gameId}/mode-history/${playerId}?limit=10`
      );
      setModeHistory(response.data.history || []);
    } catch (err) {
      console.error('Failed to fetch mode history:', err);
    } finally {
      setLoadingHistory(false);
    }
  };

  const toggleHistory = () => {
    if (!showHistory) {
      fetchModeHistory();
    }
    setShowHistory(!showHistory);
  };

  const getModeIcon = (mode) => {
    const Icon = modeConfigs[mode]?.icon;
    return Icon ? <Icon className="h-4 w-4" /> : null;
  };

  const getModeConfig = (mode) => {
    return modeConfigs[mode] || modeConfigs.manual;
  };

  return (
    <Card className="mb-4">
      <CardContent className="pt-6">
        <div className="space-y-6">
          {/* Header */}
          <div className="flex justify-between items-center">
            <h3 className="text-lg font-semibold">Agent Mode</h3>
            <Badge
              variant={getModeConfig(currentMode).badgeVariant}
              icon={getModeIcon(currentMode)}
            >
              {getModeConfig(currentMode).label}
            </Badge>
          </div>

          {/* Switch Result Alert */}
          {switchResult && switchResult.success && (
            <Alert
              variant="success"
              icon={CheckIcon}
              onClose={() => setSwitchResult(null)}
            >
              <strong>{switchResult.message}</strong>
              {switchResult.warnings && switchResult.warnings.length > 0 && (
                <div className="mt-2">
                  {switchResult.warnings.map((warning, idx) => (
                    <span key={idx} className="block text-xs">
                      Warning: {warning}
                    </span>
                  ))}
                </div>
              )}
            </Alert>
          )}

          {/* Error Alert */}
          {error && (
            <Alert
              variant="error"
              icon={WarningIcon}
              onClose={() => setError(null)}
            >
              {error}
            </Alert>
          )}

          <hr className="border-border" />

          {/* Mode Selection */}
          <div className="space-y-3">
            <Label className="text-sm font-medium text-muted-foreground">Select Agent Mode</Label>
            <div className="space-y-2">
              {Object.entries(modeConfigs).map(([mode, config]) => {
                const Icon = config.icon;
                const isSelected = selectedMode === mode;
                const isCurrent = mode === currentMode;

                return (
                  <label
                    key={mode}
                    className={cn(
                      'flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors',
                      isSelected
                        ? 'border-primary bg-primary/5'
                        : 'border-border hover:bg-muted/50'
                    )}
                  >
                    <input
                      type="radio"
                      name="agent-mode"
                      value={mode}
                      checked={isSelected}
                      onChange={() => handleModeSelect(mode)}
                      className="mt-1 h-4 w-4 border-border text-primary focus:ring-primary"
                    />
                    <div className="flex-1 py-1">
                      <div className="flex items-center gap-2">
                        <Icon className={cn('h-5 w-5', config.colorClass)} />
                        <span className="font-medium">{config.label}</span>
                        {isCurrent && (
                          <Badge variant="outline" size="sm">
                            Current
                          </Badge>
                        )}
                      </div>
                      <p className="text-sm text-muted-foreground mt-1">
                        {config.description}
                      </p>
                    </div>
                  </label>
                );
              })}
            </div>
          </div>

          {/* Selected Mode Details */}
          {selectedMode !== currentMode && (
            <div className="p-4 bg-muted rounded-lg">
              <h4 className="font-medium mb-2">
                {modeConfigs[selectedMode]?.label} Mode Details
              </h4>

              <p className="text-xs font-semibold text-muted-foreground mt-3 mb-1">
                Benefits:
              </p>
              <ul className="list-disc pl-5 space-y-0.5">
                {modeConfigs[selectedMode]?.benefits.map((benefit, idx) => (
                  <li key={idx} className="text-sm">{benefit}</li>
                ))}
              </ul>

              <p className="text-xs font-semibold text-muted-foreground mt-3 mb-1">
                Considerations:
              </p>
              <ul className="list-disc pl-5 space-y-0.5">
                {modeConfigs[selectedMode]?.considerations.map((consideration, idx) => (
                  <li key={idx} className="text-sm">{consideration}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Switch Button */}
          <div className="flex justify-between items-center">
            <Button
              onClick={handleSwitchClick}
              disabled={switching || selectedMode === currentMode}
              leftIcon={switching ? <Spinner size="sm" /> : <SwitchIcon className="h-4 w-4" />}
            >
              {switching ? 'Switching...' : 'Switch Mode'}
            </Button>

            <Button
              variant="ghost"
              size="sm"
              onClick={toggleHistory}
              leftIcon={showHistory ? <ExpandLessIcon className="h-4 w-4" /> : <HistoryIcon className="h-4 w-4" />}
            >
              {showHistory ? 'Hide' : 'Show'} History
            </Button>
          </div>

          {/* Mode History */}
          {showHistory && (
            <div className="p-4 bg-card rounded-lg border border-border">
              <h4 className="font-medium mb-3">Mode Switch History</h4>

              {loadingHistory ? (
                <div className="flex justify-center py-4">
                  <Spinner size="default" />
                </div>
              ) : modeHistory.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No mode switches yet
                </p>
              ) : (
                <div className="relative">
                  {/* Timeline */}
                  {modeHistory.map((record, idx) => {
                    const config = getModeConfig(record.new_mode);
                    const Icon = config.icon;
                    const isLast = idx === modeHistory.length - 1;

                    return (
                      <div key={record.id} className="flex gap-4 pb-4 last:pb-0">
                        {/* Left side - time info */}
                        <div className="w-20 text-right flex-shrink-0">
                          <span className="text-xs text-muted-foreground block">
                            Round {record.round_number}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {new Date(record.timestamp).toLocaleTimeString()}
                          </span>
                        </div>

                        {/* Timeline connector */}
                        <div className="flex flex-col items-center">
                          <div
                            className={cn(
                              'w-8 h-8 rounded-full flex items-center justify-center',
                              config.bgClass
                            )}
                          >
                            <Icon className={cn('h-4 w-4', config.colorClass)} />
                          </div>
                          {!isLast && (
                            <div className="w-0.5 flex-1 bg-border mt-2" />
                          )}
                        </div>

                        {/* Right side - content */}
                        <div className="flex-1 pt-1">
                          <p className="text-sm">
                            <strong>{record.previous_mode}</strong>
                            {' -> '}
                            <strong>{record.new_mode}</strong>
                          </p>
                          <span className="text-xs text-muted-foreground">
                            Reason: {record.reason}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      </CardContent>

      {/* Confirmation Dialog */}
      <Modal
        isOpen={confirmDialogOpen}
        onClose={handleCancelSwitch}
        size="md"
      >
        <ModalHeader>
          <ModalTitle>Confirm Mode Switch</ModalTitle>
        </ModalHeader>
        <ModalBody>
          <p className="text-muted-foreground">
            You are about to switch from <strong className="text-foreground">{currentMode}</strong> mode to{' '}
            <strong className="text-foreground">{selectedMode}</strong> mode.
          </p>
          <div className="mt-4 p-4 bg-warning/10 border border-warning/30 rounded-lg">
            <p className="text-sm font-medium mb-1">
              This will take effect immediately:
            </p>
            <p className="text-sm text-muted-foreground">
              {modeConfigs[selectedMode]?.description}
            </p>
          </div>
          <p className="text-muted-foreground mt-4">
            Are you sure you want to continue?
          </p>
        </ModalBody>
        <ModalFooter className="flex gap-2 justify-end">
          <Button variant="ghost" onClick={handleCancelSwitch}>
            Cancel
          </Button>
          <Button onClick={handleConfirmSwitch}>
            Confirm Switch
          </Button>
        </ModalFooter>
      </Modal>
    </Card>
  );
};

export default AgentModeSelector;
