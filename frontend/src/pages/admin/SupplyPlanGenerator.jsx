/**
 * Supply Plan Generator
 *
 * Main interface for generating supply plans with probabilistic evaluation.
 * Supports both deterministic and stochastic planning approaches.
 */

import { useState } from 'react';
import { Card, CardContent, Alert } from '../../components/common';
import { CheckCircle } from 'lucide-react';

import ObjectivesStep from '../../components/supply-plan/ObjectivesStep';
import ParametersStep from '../../components/supply-plan/ParametersStep';
import PlanningMethodStep from '../../components/supply-plan/PlanningMethodStep';
import GenerationProgress from '../../components/supply-plan/GenerationProgress';
import BalancedScorecardDashboard from '../../components/supply-plan/BalancedScorecardDashboard';

const steps = [
  'Select Configuration & Objectives',
  'Configure Planning Method',
  'Set Stochastic Parameters',
  'Generate Plan',
  'View Results'
];

export default function SupplyPlanGenerator() {
  const [activeStep, setActiveStep] = useState(0);
  const [error, setError] = useState(null);

  // Planning configuration state
  const [planConfig, setPlanConfig] = useState({
    configId: null,
    configName: '',
    planningMethod: 'deterministic',
    objectives: {
      planningHorizon: 52,
      primaryObjective: 'minimize_cost',
      serviceLevelTarget: 0.95,
      serviceLevelConfidence: 0.90,
      budgetLimit: null,
      inventoryDosMin: null,
      inventoryDosMax: null,
    },
    stochasticParams: {
      demandModel: 'normal',
      demandVariability: 0.15,
      leadTimeModel: 'normal',
      leadTimeVariability: 0.10,
      supplierReliability: 0.95,
      randomSeed: 42,
    },
    deterministicSettings: {
      orderingCost: 100.0,
      holdingCostRate: 0.20,
      safetyStockMethod: 'service_level',
      fixedSafetyWeeks: 2,
    },
    stochasticSettings: {
      numScenarios: 50,
      solverMethod: 'progressive_hedging',
      recourseOptions: {
        allowOvertime: true,
        allowExpediting: true,
        allowBackorders: true,
        overtimeCostMultiplier: 1.5,
        expeditingCostMultiplier: 2.0,
        backorderPenalty: 100.0,
      },
    },
    evaluationScenarios: 1000,
  });

  const [taskId, setTaskId] = useState(null);
  const [taskStatus, setTaskStatus] = useState(null);
  const [results, setResults] = useState(null);

  const handleNext = () => {
    setActiveStep((prevActiveStep) => prevActiveStep + 1);
  };

  const handleBack = () => {
    setActiveStep((prevActiveStep) => prevActiveStep - 1);
  };

  const handleReset = () => {
    setActiveStep(0);
    setTaskId(null);
    setTaskStatus(null);
    setResults(null);
    setError(null);
  };

  const updatePlanConfig = (updates) => {
    setPlanConfig((prev) => ({
      ...prev,
      ...updates,
    }));
  };

  const renderStepContent = (step) => {
    switch (step) {
      case 0:
        return (
          <ObjectivesStep
            config={planConfig}
            onUpdate={updatePlanConfig}
            onNext={handleNext}
          />
        );
      case 1:
        return (
          <PlanningMethodStep
            config={planConfig}
            onUpdate={updatePlanConfig}
            onNext={handleNext}
            onBack={handleBack}
          />
        );
      case 2:
        return (
          <ParametersStep
            config={planConfig}
            onUpdate={updatePlanConfig}
            onNext={handleNext}
            onBack={handleBack}
          />
        );
      case 3:
        return (
          <GenerationProgress
            config={planConfig}
            taskId={taskId}
            setTaskId={setTaskId}
            taskStatus={taskStatus}
            setTaskStatus={setTaskStatus}
            onComplete={(resultData) => {
              setResults(resultData);
              handleNext();
            }}
            onError={(err) => setError(err)}
          />
        );
      case 4:
        return (
          <BalancedScorecardDashboard
            results={results}
            config={planConfig}
            onReset={handleReset}
            onExport={() => {
              const blob = new Blob([JSON.stringify(results, null, 2)], { type: 'application/json' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = `supply-plan-${planConfig?.config_id || 'unknown'}-${new Date().toISOString().slice(0,10)}.json`;
              a.click();
              URL.revokeObjectURL(url);
            }}
          />
        );
      default:
        return 'Unknown step';
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <Card>
        <CardContent className="p-6">
          <h1 className="text-2xl font-bold mb-2">Supply Plan Generator</h1>

          <p className="text-muted-foreground mb-6">
            Generate probabilistic supply plans with balanced scorecard evaluation.
            Choose between deterministic planning with Monte Carlo evaluation or
            direct two-stage stochastic MPS optimization.
          </p>

          {error && (
            <Alert variant="destructive" className="mb-6" onClose={() => setError(null)}>
              {error}
            </Alert>
          )}

          {/* Stepper */}
          <div className="flex items-center mb-8">
            {steps.map((label, index) => (
              <div key={label} className="flex items-center">
                <div className="flex flex-col items-center">
                  <div
                    className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                      index < activeStep
                        ? 'bg-primary text-primary-foreground'
                        : index === activeStep
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-muted text-muted-foreground'
                    }`}
                  >
                    {index < activeStep ? (
                      <CheckCircle className="h-5 w-5" />
                    ) : (
                      index + 1
                    )}
                  </div>
                  <span
                    className={`text-xs mt-1 text-center max-w-[100px] ${
                      index <= activeStep ? 'text-foreground' : 'text-muted-foreground'
                    }`}
                  >
                    {label}
                  </span>
                </div>
                {index < steps.length - 1 && (
                  <div
                    className={`w-12 h-0.5 mx-2 ${
                      index < activeStep ? 'bg-primary' : 'bg-muted'
                    }`}
                  />
                )}
              </div>
            ))}
          </div>

          <div>
            {renderStepContent(activeStep)}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
