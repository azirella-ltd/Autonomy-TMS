/**
 * Tutorial System Component
 * Phase 6 Sprint 4: User Experience Enhancements
 *
 * Interactive step-by-step tutorial system with progress tracking.
 * Features:
 * - Step navigation
 * - Progress indicator
 * - Interactive highlights
 * - Context-sensitive help
 */

import React, { useState, useEffect } from 'react';
import {
  ChevronRight,
  ChevronLeft,
  X,
  CheckCircle,
  Play,
  RotateCcw,
} from 'lucide-react';
import {
  Modal,
  ModalHeader,
  ModalTitle,
  ModalBody,
  ModalFooter,
  Button,
  Badge,
  Progress,
  Card,
  CardContent,
} from '../common';
import { api } from '../../services/api';
import { cn } from '../../lib/utils/cn';

const TutorialSystem = ({ tutorialId, steps, onComplete, onClose }) => {
  const [activeStep, setActiveStep] = useState(0);
  const [completed, setCompleted] = useState(false);
  const [progress, setProgress] = useState(null);
  const [loading, setLoading] = useState(false);

  // Load tutorial progress
  useEffect(() => {
    loadProgress();
  }, [tutorialId]);

  const loadProgress = async () => {
    try {
      const response = await api.get(`/templates/tutorials/progress/${tutorialId}`);
      setProgress(response.data);
      setActiveStep(response.data.current_step);
      setCompleted(response.data.completed);
    } catch (error) {
      // No existing progress, start fresh
      console.log('No existing progress, starting fresh');
    }
  };

  const startTutorial = async () => {
    setLoading(true);
    try {
      const response = await api.post('/templates/tutorials/progress', {
        tutorial_id: tutorialId,
        current_step: 0,
        total_steps: steps.length,
        state: {}
      });
      setProgress(response.data);
      setActiveStep(0);
      setCompleted(false);
    } catch (error) {
      console.error('Failed to start tutorial:', error);
    } finally {
      setLoading(false);
    }
  };

  const updateProgress = async (newStep, isComplete = false) => {
    if (!progress) return;

    try {
      await api.put(`/templates/tutorials/progress/${tutorialId}`, {
        current_step: newStep,
        completed: isComplete,
        state: { last_step: newStep }
      });

      if (isComplete) {
        setCompleted(true);
        if (onComplete) onComplete();
      }
    } catch (error) {
      console.error('Failed to update progress:', error);
    }
  };

  const handleNext = () => {
    const newStep = activeStep + 1;
    setActiveStep(newStep);

    if (newStep >= steps.length) {
      // Tutorial completed
      updateProgress(steps.length, true);
    } else {
      updateProgress(newStep, false);
    }
  };

  const handleBack = () => {
    const newStep = activeStep - 1;
    setActiveStep(newStep);
    updateProgress(newStep, false);
  };

  const handleReset = () => {
    setActiveStep(0);
    setCompleted(false);
    startTutorial();
  };

  const handleStepClick = (stepIndex) => {
    setActiveStep(stepIndex);
    updateProgress(stepIndex, false);
  };

  const progressPercentage = ((activeStep + 1) / steps.length) * 100;

  if (!progress && !loading) {
    // Show start screen
    return (
      <Modal isOpen={true} onClose={onClose} size="sm">
        <ModalHeader>
          <div className="flex justify-between items-center w-full">
            <ModalTitle>Tutorial</ModalTitle>
            <Button variant="ghost" size="icon" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </ModalHeader>
        <ModalBody>
          <div className="text-center py-8">
            <Play className="h-20 w-20 text-primary mx-auto mb-4" />
            <h3 className="text-lg font-semibold mb-2">
              Ready to get started?
            </h3>
            <p className="text-sm text-muted-foreground mb-6">
              This tutorial will guide you through {steps.length} steps to help you understand the features.
            </p>
            <Button
              size="lg"
              leftIcon={<Play className="h-4 w-4" />}
              onClick={startTutorial}
              disabled={loading}
            >
              Start Tutorial
            </Button>
          </div>
        </ModalBody>
      </Modal>
    );
  }

  if (completed) {
    // Show completion screen
    return (
      <Modal isOpen={true} onClose={onClose} size="sm">
        <ModalHeader>
          <div className="flex justify-between items-center w-full">
            <ModalTitle>Tutorial Complete!</ModalTitle>
            <Button variant="ghost" size="icon" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </ModalHeader>
        <ModalBody>
          <div className="text-center py-8">
            <CheckCircle className="h-20 w-20 text-emerald-500 mx-auto mb-4" />
            <h3 className="text-lg font-semibold mb-2">
              Congratulations!
            </h3>
            <p className="text-sm text-muted-foreground mb-6">
              You've completed all {steps.length} steps of this tutorial.
            </p>
            <div className="flex gap-3 justify-center">
              <Button
                variant="outline"
                leftIcon={<RotateCcw className="h-4 w-4" />}
                onClick={handleReset}
              >
                Restart Tutorial
              </Button>
              <Button onClick={onClose}>
                Close
              </Button>
            </div>
          </div>
        </ModalBody>
      </Modal>
    );
  }

  return (
    <Modal isOpen={true} onClose={onClose} size="lg">
      <ModalHeader>
        <div className="flex justify-between items-center w-full">
          <div>
            <ModalTitle>Tutorial</ModalTitle>
            <p className="text-sm text-muted-foreground">
              Step {activeStep + 1} of {steps.length}
            </p>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        <Progress
          value={progressPercentage}
          className="mt-3"
        />
      </ModalHeader>

      <ModalBody>
        {/* Custom vertical stepper */}
        <div className="space-y-4">
          {steps.map((step, index) => (
            <div key={index} className="relative">
              {/* Step indicator */}
              <div
                className={cn(
                  'flex items-start gap-3 cursor-pointer',
                  index > activeStep && 'opacity-50'
                )}
                onClick={() => handleStepClick(index)}
              >
                <div
                  className={cn(
                    'flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium',
                    index < activeStep && 'bg-primary text-primary-foreground',
                    index === activeStep && 'bg-primary text-primary-foreground ring-2 ring-primary ring-offset-2',
                    index > activeStep && 'bg-muted text-muted-foreground'
                  )}
                >
                  {index < activeStep ? (
                    <CheckCircle className="h-4 w-4" />
                  ) : (
                    index + 1
                  )}
                </div>
                <div className="flex-grow">
                  <div className="flex items-center gap-2">
                    <span className={cn(
                      'font-medium',
                      index === activeStep && 'text-primary'
                    )}>
                      {step.title}
                    </span>
                    {step.optional && (
                      <Badge variant="secondary" size="sm">Optional</Badge>
                    )}
                  </div>
                </div>
              </div>

              {/* Step content - only show for active step */}
              {index === activeStep && (
                <div className="ml-11 mt-3 pb-4">
                  <p className="text-sm text-muted-foreground mb-3">
                    {step.description}
                  </p>

                  {step.content && (
                    <Card variant="outlined" className="mb-3 bg-muted/30">
                      <CardContent className="p-3">
                        {typeof step.content === 'string' ? (
                          <p className="text-sm">{step.content}</p>
                        ) : (
                          step.content
                        )}
                      </CardContent>
                    </Card>
                  )}

                  {step.tips && step.tips.length > 0 && (
                    <div className="mb-3">
                      <p className="text-xs text-muted-foreground mb-1">Tips:</p>
                      <div className="flex flex-wrap gap-1">
                        {step.tips.map((tip, tipIndex) => (
                          <Badge key={tipIndex} variant="secondary" size="sm">
                            {tip}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="flex gap-2 mt-4">
                    <Button
                      variant="ghost"
                      disabled={index === 0}
                      onClick={handleBack}
                      leftIcon={<ChevronLeft className="h-4 w-4" />}
                    >
                      Back
                    </Button>
                    <Button
                      onClick={handleNext}
                      rightIcon={index === steps.length - 1 ? <CheckCircle className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                    >
                      {index === steps.length - 1 ? 'Complete' : 'Next'}
                    </Button>
                  </div>
                </div>
              )}

              {/* Connector line */}
              {index < steps.length - 1 && (
                <div
                  className={cn(
                    'absolute left-4 top-8 w-0.5 h-full -translate-x-1/2',
                    index < activeStep ? 'bg-primary' : 'bg-muted'
                  )}
                />
              )}
            </div>
          ))}
        </div>
      </ModalBody>

      <ModalFooter>
        <Button variant="ghost" onClick={handleReset} leftIcon={<RotateCcw className="h-4 w-4" />}>
          Restart
        </Button>
        <Button variant="ghost" onClick={onClose}>Close</Button>
      </ModalFooter>
    </Modal>
  );
};

export default TutorialSystem;
