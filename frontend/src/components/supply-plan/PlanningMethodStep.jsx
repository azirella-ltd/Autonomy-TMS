/**
 * Planning Method Selection Step
 *
 * Allows user to choose between:
 * 1. Deterministic Planning (safety stock heuristics) + Monte Carlo evaluation
 * 2. Two-Stage Stochastic MPS (direct stochastic optimization)
 */

import React, { useState } from 'react';
import { ChevronDown, CheckCircle, Info } from 'lucide-react';
import { Card, CardContent, Button, Alert, Badge, Input, Label, FormField } from '../common';
import { cn } from '@azirella-ltd/autonomy-frontend';

export default function PlanningMethodStep({ config, onUpdate, onNext, onBack }) {
  const [expandedRecourse, setExpandedRecourse] = useState(false);

  const handleMethodChange = (value) => {
    onUpdate({ planningMethod: value });
  };

  const handleDeterministicSettingChange = (field, value) => {
    onUpdate({
      deterministicSettings: {
        ...config.deterministicSettings,
        [field]: value,
      },
    });
  };

  const handleStochasticSettingChange = (field, value) => {
    onUpdate({
      stochasticSettings: {
        ...config.stochasticSettings,
        [field]: value,
      },
    });
  };

  const handleRecourseOptionChange = (field, value) => {
    onUpdate({
      stochasticSettings: {
        ...config.stochasticSettings,
        recourseOptions: {
          ...config.stochasticSettings.recourseOptions,
          [field]: value,
        },
      },
    });
  };

  return (
    <div>
      <h2 className="text-lg font-semibold mb-4">Select Planning Method</h2>

      <Alert variant="info" className="mb-6">
        <div>
          <strong>Deterministic:</strong> Uses classical inventory policies (safety stock, ROP, EOQ)
          then evaluates with Monte Carlo.
          <br />
          <strong>Stochastic MPS:</strong> Direct two-stage optimization that finds optimal hedging
          decisions under uncertainty.
        </div>
      </Alert>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Deterministic Method Card */}
        <Card
          className={cn(
            'h-full cursor-pointer transition-all',
            config.planningMethod === 'deterministic'
              ? 'border-2 border-primary ring-2 ring-primary/20'
              : 'border border-border hover:border-primary/50'
          )}
          padding="none"
          onClick={() => handleMethodChange('deterministic')}
        >
          <CardContent className="p-6">
            <div className="flex items-center mb-4">
              <input
                type="radio"
                checked={config.planningMethod === 'deterministic'}
                onChange={() => handleMethodChange('deterministic')}
                className="h-4 w-4 text-primary border-border focus:ring-primary"
              />
              <h3 className="text-lg font-semibold ml-3">Deterministic Planning</h3>
              {config.planningMethod === 'deterministic' && (
                <CheckCircle className="ml-auto h-5 w-5 text-primary" />
              )}
            </div>

            <p className="text-sm text-muted-foreground mb-4">
              Classical inventory policies: safety stock formulas, reorder points (ROP),
              economic order quantity (EOQ). Fast and simple.
            </p>

            <div className="flex flex-wrap gap-2 mb-4">
              <Badge variant="secondary" size="sm">Fast (~2 sec)</Badge>
              <Badge variant="secondary" size="sm">Proven methods</Badge>
              <Badge variant="secondary" size="sm">Easy to explain</Badge>
            </div>

            <p className="text-sm font-medium mb-2">Best for:</p>
            <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
              <li>Simple supply chains</li>
              <li>Quick what-if analysis</li>
              <li>Initial exploration</li>
            </ul>
          </CardContent>

          {config.planningMethod === 'deterministic' && (
            <CardContent className="border-t border-border p-6" onClick={(e) => e.stopPropagation()}>
              <p className="text-sm font-medium mb-4">Configuration:</p>

              <FormField
                label="Ordering Cost per Order"
                helperText="Cost per order placed"
                className="mb-4"
              >
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">$</span>
                  <Input
                    type="number"
                    value={config.deterministicSettings.orderingCost}
                    onChange={(e) =>
                      handleDeterministicSettingChange('orderingCost', parseFloat(e.target.value))
                    }
                    className="pl-7"
                  />
                </div>
              </FormField>

              <FormField
                label="Holding Cost Rate (Annual %)"
                helperText="Inventory holding cost as % of item value per year"
                className="mb-4"
              >
                <div className="relative">
                  <Input
                    type="number"
                    value={config.deterministicSettings.holdingCostRate}
                    onChange={(e) =>
                      handleDeterministicSettingChange('holdingCostRate', parseFloat(e.target.value))
                    }
                    className="pr-7"
                  />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground">%</span>
                </div>
              </FormField>

              <div className="mt-4">
                <Label className="mb-2 block">Safety Stock Method</Label>
                <div className="space-y-2">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      checked={config.deterministicSettings.safetyStockMethod === 'service_level'}
                      onChange={() =>
                        handleDeterministicSettingChange('safetyStockMethod', 'service_level')
                      }
                      className="h-4 w-4 text-primary border-border focus:ring-primary"
                    />
                    <span className="text-sm">Service level (z-score)</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      checked={config.deterministicSettings.safetyStockMethod === 'fixed_weeks'}
                      onChange={() =>
                        handleDeterministicSettingChange('safetyStockMethod', 'fixed_weeks')
                      }
                      className="h-4 w-4 text-primary border-border focus:ring-primary"
                    />
                    <span className="text-sm">Fixed weeks of supply</span>
                  </label>
                </div>
              </div>

              {config.deterministicSettings.safetyStockMethod === 'fixed_weeks' && (
                <FormField label="Safety Stock (Weeks of Supply)" className="mt-4">
                  <Input
                    type="number"
                    value={config.deterministicSettings.fixedSafetyWeeks}
                    onChange={(e) =>
                      handleDeterministicSettingChange('fixedSafetyWeeks', parseInt(e.target.value))
                    }
                  />
                </FormField>
              )}
            </CardContent>
          )}
        </Card>

        {/* Stochastic Method Card */}
        <Card
          className={cn(
            'h-full cursor-pointer transition-all',
            config.planningMethod === 'stochastic'
              ? 'border-2 border-primary ring-2 ring-primary/20'
              : 'border border-border hover:border-primary/50'
          )}
          padding="none"
          onClick={() => handleMethodChange('stochastic')}
        >
          <CardContent className="p-6">
            <div className="flex items-center mb-4">
              <input
                type="radio"
                checked={config.planningMethod === 'stochastic'}
                onChange={() => handleMethodChange('stochastic')}
                className="h-4 w-4 text-primary border-border focus:ring-primary"
              />
              <h3 className="text-lg font-semibold ml-3">Two-Stage Stochastic MPS</h3>
              {config.planningMethod === 'stochastic' && (
                <CheckCircle className="ml-auto h-5 w-5 text-primary" />
              )}
            </div>

            <p className="text-sm text-muted-foreground mb-4">
              Direct stochastic optimization. First-stage: production quantities. Second-stage:
              recourse (overtime, expediting, backorders). Provably optimal under uncertainty.
            </p>

            <div className="flex flex-wrap gap-2 mb-4">
              <Badge variant="default" size="sm">Optimal</Badge>
              <Badge variant="secondary" size="sm">Handles complexity</Badge>
              <Badge variant="secondary" size="sm">40% less nervous</Badge>
            </div>

            <p className="text-sm font-medium mb-2">Best for:</p>
            <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
              <li>Complex supply chains</li>
              <li>High demand variability</li>
              <li>Production planning</li>
            </ul>
          </CardContent>

          {config.planningMethod === 'stochastic' && (
            <CardContent className="border-t border-border p-6" onClick={(e) => e.stopPropagation()}>
              <p className="text-sm font-medium mb-4">Configuration:</p>

              <FormField
                label="Number of Scenarios"
                helperText="Recommended: 10-100 for two-stage stochastic MPS"
                className="mb-4"
              >
                <Input
                  type="number"
                  value={config.stochasticSettings.numScenarios}
                  onChange={(e) =>
                    handleStochasticSettingChange('numScenarios', parseInt(e.target.value))
                  }
                />
              </FormField>

              <div className="mb-4">
                <Label className="mb-2 block">Solver Method</Label>
                <div className="space-y-2">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      checked={config.stochasticSettings.solverMethod === 'progressive_hedging'}
                      onChange={() => handleStochasticSettingChange('solverMethod', 'progressive_hedging')}
                      className="h-4 w-4 text-primary border-border focus:ring-primary"
                    />
                    <span className="text-sm">Progressive Hedging (Recommended)</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      checked={config.stochasticSettings.solverMethod === 'l_shaped'}
                      onChange={() => handleStochasticSettingChange('solverMethod', 'l_shaped')}
                      className="h-4 w-4 text-primary border-border focus:ring-primary"
                    />
                    <span className="text-sm">L-Shaped Method</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      checked={config.stochasticSettings.solverMethod === 'saa'}
                      onChange={() => handleStochasticSettingChange('solverMethod', 'saa')}
                      className="h-4 w-4 text-primary border-border focus:ring-primary"
                    />
                    <span className="text-sm">Sample Average Approximation</span>
                  </label>
                </div>
              </div>

              {/* Accordion for Recourse Options */}
              <div className="border border-border rounded-lg mt-4">
                <button
                  type="button"
                  className="w-full px-4 py-3 flex items-center justify-between text-sm font-medium hover:bg-muted/50 transition-colors"
                  onClick={() => setExpandedRecourse(!expandedRecourse)}
                >
                  <span>Recourse Options</span>
                  <ChevronDown
                    className={cn(
                      'h-4 w-4 transition-transform',
                      expandedRecourse && 'transform rotate-180'
                    )}
                  />
                </button>
                {expandedRecourse && (
                  <div className="px-4 pb-4 space-y-4">
                    <label className="flex items-center gap-3 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={config.stochasticSettings.recourseOptions.allowOvertime}
                        onChange={(e) =>
                          handleRecourseOptionChange('allowOvertime', e.target.checked)
                        }
                        className="h-4 w-4 rounded text-primary border-border focus:ring-primary"
                      />
                      <span className="text-sm">Allow Overtime Production</span>
                    </label>
                    {config.stochasticSettings.recourseOptions.allowOvertime && (
                      <FormField
                        label="Overtime Cost Multiplier"
                        helperText="e.g., 1.5 = 50% higher cost than regular time"
                      >
                        <Input
                          type="number"
                          value={config.stochasticSettings.recourseOptions.overtimeCostMultiplier}
                          onChange={(e) =>
                            handleRecourseOptionChange(
                              'overtimeCostMultiplier',
                              parseFloat(e.target.value)
                            )
                          }
                        />
                      </FormField>
                    )}

                    <label className="flex items-center gap-3 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={config.stochasticSettings.recourseOptions.allowExpediting}
                        onChange={(e) =>
                          handleRecourseOptionChange('allowExpediting', e.target.checked)
                        }
                        className="h-4 w-4 rounded text-primary border-border focus:ring-primary"
                      />
                      <span className="text-sm">Allow Expedited Orders</span>
                    </label>
                    {config.stochasticSettings.recourseOptions.allowExpediting && (
                      <FormField label="Expediting Cost Multiplier">
                        <Input
                          type="number"
                          value={config.stochasticSettings.recourseOptions.expeditingCostMultiplier}
                          onChange={(e) =>
                            handleRecourseOptionChange(
                              'expeditingCostMultiplier',
                              parseFloat(e.target.value)
                            )
                          }
                        />
                      </FormField>
                    )}

                    <label className="flex items-center gap-3 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={config.stochasticSettings.recourseOptions.allowBackorders}
                        onChange={(e) =>
                          handleRecourseOptionChange('allowBackorders', e.target.checked)
                        }
                        className="h-4 w-4 rounded text-primary border-border focus:ring-primary"
                      />
                      <span className="text-sm">Allow Backorders</span>
                    </label>
                    {config.stochasticSettings.recourseOptions.allowBackorders && (
                      <FormField label="Backorder Penalty (per unit)">
                        <div className="relative">
                          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">$</span>
                          <Input
                            type="number"
                            value={config.stochasticSettings.recourseOptions.backorderPenalty}
                            onChange={(e) =>
                              handleRecourseOptionChange(
                                'backorderPenalty',
                                parseFloat(e.target.value)
                              )
                            }
                            className="pl-7"
                          />
                        </div>
                      </FormField>
                    )}
                  </div>
                )}
              </div>
            </CardContent>
          )}
        </Card>
      </div>

      {/* Navigation Buttons */}
      <div className="flex justify-between mt-8">
        <Button variant="outline" onClick={onBack}>
          Back
        </Button>
        <Button onClick={onNext}>Next: Configure Parameters</Button>
      </div>
    </div>
  );
}
