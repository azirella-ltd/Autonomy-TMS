/**
 * FallbackWarningModal Component
 *
 * Displays a warning modal when AI agents fall back to naive/heuristic strategies
 * because their trained models are not available or failed to load.
 *
 * Requires user acknowledgement before proceeding and allows cancellation.
 */

import React from 'react';
import {
  Modal,
  ModalHeader,
  ModalTitle,
  ModalBody,
  ModalFooter,
} from '../common/Modal';
import { Button } from '../common/Button';
import { Alert, AlertDescription } from '../common/Alert';
import { AlertTriangle } from 'lucide-react';

const FallbackWarningModal = ({
  isOpen,
  onClose,
  onConfirm,
  onCancel,
  fallbacks = {},
  alternativeName = 'the simulation',
  gameName,  // Deprecated: use alternativeName
}) => {
  // Backward compatibility: use gameName if alternativeName not provided
  const displayName = alternativeName || gameName || 'the simulation';
  const fallbackEntries = Object.entries(fallbacks);
  const hasMultipleFallbacks = fallbackEntries.length > 1;

  const handleConfirm = () => {
    if (onConfirm) onConfirm();
    if (onClose) onClose();
  };

  const handleCancel = () => {
    if (onCancel) onCancel();
    if (onClose) onClose();
  };

  // Map strategy names to user-friendly display names
  const getStrategyDisplayName = (strategy) => {
    const strategyNames = {
      trm: 'AI Agent',
      gnn: 'Network Agent',
      rl: 'RL (Reinforcement Learning)',
      llm: 'LLM (Large Language Model)',
    };
    return strategyNames[strategy?.toLowerCase()] || strategy || 'AI Model';
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleCancel}
      size="md"
      closeOnOverlayClick={false}
      closeOnEsc={false}
    >
      <ModalHeader>
        <ModalTitle className="flex items-center gap-2 text-amber-600">
          <AlertTriangle className="h-5 w-5" />
          AI Agent Fallback Warning
        </ModalTitle>
      </ModalHeader>

      <ModalBody>
        <Alert variant="warning" className="mb-4">
          <AlertDescription>
            {hasMultipleFallbacks
              ? `${fallbackEntries.length} AI agents have fallen back to basic heuristic strategies.`
              : 'An AI agent has fallen back to a basic heuristic strategy.'}
          </AlertDescription>
        </Alert>

        <p className="text-sm text-muted-foreground mb-4">
          The following AI agent{hasMultipleFallbacks ? 's are' : ' is'} using fallback
          strategies because the trained model{hasMultipleFallbacks ? 's are' : ' is'} not available:
        </p>

        <div className="space-y-3 max-h-60 overflow-y-auto">
          {fallbackEntries.map(([nodeKey, fallbackInfo]) => (
            <div
              key={nodeKey}
              className="p-3 border rounded-md bg-amber-50 dark:bg-amber-950/30 border-amber-200 dark:border-amber-800"
            >
              <div className="flex justify-between items-start">
                <div>
                  <span className="font-medium">
                    {fallbackInfo.node_name || nodeKey}
                  </span>
                  <span className="text-sm text-muted-foreground ml-2">
                    ({getStrategyDisplayName(fallbackInfo.original_strategy)})
                  </span>
                </div>
              </div>
              {fallbackInfo.fallback_reason && (
                <p className="text-xs text-muted-foreground mt-1">
                  Reason: {fallbackInfo.fallback_reason}
                </p>
              )}
            </div>
          ))}
        </div>

        <div className="mt-4 p-3 bg-muted rounded-md">
          <p className="text-sm">
            <strong>What this means:</strong> Instead of using the trained AI model,
            these agents will use a simple base-stock heuristic policy. This may result
            in suboptimal decisions compared to the trained model.
          </p>
        </div>

        <p className="text-sm text-muted-foreground mt-4">
          To use the trained AI models, ensure:
        </p>
        <ul className="text-sm text-muted-foreground list-disc list-inside mt-2 space-y-1">
          <li>A model has been trained for this supply chain configuration</li>
          <li>The model checkpoint file exists and is accessible</li>
          <li>The required dependencies (PyTorch, etc.) are installed</li>
        </ul>
      </ModalBody>

      <ModalFooter className="flex justify-end gap-3">
        <Button variant="outline" onClick={handleCancel}>
          Cancel
        </Button>
        <Button variant="default" onClick={handleConfirm}>
          Continue with Fallback
        </Button>
      </ModalFooter>
    </Modal>
  );
};

export default FallbackWarningModal;
