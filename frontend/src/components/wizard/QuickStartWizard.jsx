/**
 * Quick Start Wizard Component
 * Phase 6 Sprint 4: User Experience Enhancements
 *
 * 3-step wizard for quick game configuration.
 * Features:
 * - Industry and difficulty selection
 * - Template recommendations
 * - Configuration preview
 * - One-click setup
 */

import React, { useState } from 'react';
import {
  ChevronRight,
  ChevronLeft,
  Check,
  X,
  Star,
  TrendingUp,
} from 'lucide-react';
import {
  Modal,
  ModalHeader,
  ModalTitle,
  ModalBody,
  ModalFooter,
  Button,
  Card,
  CardContent,
  Badge,
  Alert,
  Spinner,
  Input,
  Label,
  FormField,
} from '../common';
import { api } from '../../services/api';
import { cn } from '@azirella-ltd/autonomy-frontend';

const INDUSTRIES = [
  { value: 'general', label: 'General', description: 'Standard supply chain' },
  { value: 'retail', label: 'Retail', description: 'Consumer goods distribution' },
  { value: 'manufacturing', label: 'Manufacturing', description: 'Production and assembly' },
  { value: 'logistics', label: 'Logistics', description: 'Transportation and warehousing' },
  { value: 'healthcare', label: 'Healthcare', description: 'Medical supplies' },
  { value: 'technology', label: 'Technology', description: 'Electronics and components' },
  { value: 'food_beverage', label: 'Food & Beverage', description: 'Perishable goods' },
  { value: 'automotive', label: 'Automotive', description: 'Auto parts and assembly' }
];

const DIFFICULTIES = [
  { value: 'beginner', label: 'Beginner', description: 'Simple, predictable patterns' },
  { value: 'intermediate', label: 'Intermediate', description: 'Moderate complexity' },
  { value: 'advanced', label: 'Advanced', description: 'Complex scenarios' },
  { value: 'expert', label: 'Expert', description: 'Maximum challenge' }
];

const FEATURES = [
  { value: 'stochastic', label: 'Stochastic Demand', description: 'Variable demand patterns' },
  { value: 'monte_carlo', label: 'Monte Carlo Simulation', description: 'Risk analysis' },
  { value: 'multi_tier', label: 'Multi-Tier Network', description: '3+ echelons' },
  { value: 'ai_agents', label: 'AI Agents', description: 'Automated users' }
];

const steps = ['Select Industry', 'Choose Template', 'Configure & Launch'];

const QuickStartWizard = ({ open, onClose, onComplete }) => {
  const [activeStep, setActiveStep] = useState(0);
  const [industry, setIndustry] = useState('general');
  const [difficulty, setDifficulty] = useState('beginner');
  const [features, setFeatures] = useState([]);
  const [numScenarioUsers, setNumScenarioUsers] = useState(4);
  const [useMonteCarlo, setUseMonteCarlo] = useState(false);

  const [recommendations, setRecommendations] = useState(null);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleNext = async () => {
    if (activeStep === 0) {
      // Step 1: Get recommendations
      await fetchRecommendations();
    } else if (activeStep === 1 && !selectedTemplate) {
      setError('Please select a template');
      return;
    }

    setActiveStep((prev) => prev + 1);
  };

  const handleBack = () => {
    setActiveStep((prev) => prev - 1);
    setError(null);
  };

  const handleReset = () => {
    setActiveStep(0);
    setIndustry('general');
    setDifficulty('beginner');
    setFeatures([]);
    setNumScenarioUsers(4);
    setUseMonteCarlo(false);
    setRecommendations(null);
    setSelectedTemplate(null);
    setError(null);
  };

  const fetchRecommendations = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await api.post('/templates/quick-start', {
        industry,
        difficulty,
        features,
        use_monte_carlo: useMonteCarlo,
        num_scenario_users: numScenarioUsers
      });

      setRecommendations(response.data);
      setSelectedTemplate(response.data.recommended_template);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to fetch recommendations');
    } finally {
      setLoading(false);
    }
  };

  const handleFeatureToggle = (feature) => {
    setFeatures((prev) =>
      prev.includes(feature) ? prev.filter((f) => f !== feature) : [...prev, feature]
    );

    if (feature === 'monte_carlo') {
      setUseMonteCarlo(!useMonteCarlo);
    }
  };

  const handleLaunch = () => {
    if (onComplete && selectedTemplate) {
      onComplete({
        template: selectedTemplate,
        configuration: recommendations.configuration,
        numScenarioUsers,
        useMonteCarlo
      });
    }
    onClose();
  };

  const renderStepContent = (step) => {
    switch (step) {
      case 0:
        return (
          <div>
            <h3 className="text-lg font-semibold mb-4">
              Choose Your Industry & Difficulty
            </h3>

            {/* Industry Selection */}
            <div className="mb-6">
              <Label className="mb-2 block">Industry</Label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {INDUSTRIES.map((ind) => (
                  <Card
                    key={ind.value}
                    variant="outlined"
                    padding="none"
                    className={cn(
                      'cursor-pointer transition-colors',
                      industry === ind.value
                        ? 'border-2 border-primary'
                        : 'hover:border-primary/50'
                    )}
                    onClick={() => setIndustry(ind.value)}
                  >
                    <CardContent className="p-3">
                      <label className="flex items-start gap-2 cursor-pointer">
                        <input
                          type="radio"
                          name="industry"
                          value={ind.value}
                          checked={industry === ind.value}
                          onChange={() => setIndustry(ind.value)}
                          className="mt-1"
                        />
                        <div>
                          <p className="text-sm font-medium">{ind.label}</p>
                          <p className="text-xs text-muted-foreground">{ind.description}</p>
                        </div>
                      </label>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>

            {/* Difficulty Selection */}
            <div className="mb-6">
              <Label className="mb-2 block">Difficulty Level</Label>
              <div className="flex flex-wrap gap-3">
                {DIFFICULTIES.map((diff) => (
                  <label key={diff.value} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="difficulty"
                      value={diff.value}
                      checked={difficulty === diff.value}
                      onChange={() => setDifficulty(diff.value)}
                    />
                    <span className="text-sm">{diff.label}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* Features */}
            <div className="mb-6">
              <Label className="mb-2 block">Optional Features</Label>
              <div className="flex flex-wrap gap-2">
                {FEATURES.map((feature) => (
                  <Badge
                    key={feature.value}
                    variant={features.includes(feature.value) ? 'default' : 'outline'}
                    className="cursor-pointer"
                    icon={features.includes(feature.value) ? <Check className="h-3 w-3" /> : null}
                    onClick={() => handleFeatureToggle(feature.value)}
                  >
                    {feature.label}
                  </Badge>
                ))}
              </div>
            </div>

            {/* Number of ScenarioUsers */}
            <FormField label="Number of ScenarioUsers" className="mb-4">
              <Input
                type="number"
                value={numScenarioUsers}
                onChange={(e) => setNumScenarioUsers(Math.max(1, Math.min(10, parseInt(e.target.value) || 4)))}
                min={1}
                max={10}
              />
            </FormField>
          </div>
        );

      case 1:
        return (
          <div>
            <h3 className="text-lg font-semibold mb-4">
              Select a Template
            </h3>

            {loading && (
              <div className="flex justify-center py-8">
                <Spinner size="lg" />
              </div>
            )}

            {recommendations && (
              <div className="space-y-4">
                {/* Recommended Template */}
                <Card
                  variant="outlined"
                  className={cn(
                    'cursor-pointer transition-all',
                    selectedTemplate?.id === recommendations.recommended_template.id
                      ? 'border-2 border-primary'
                      : 'hover:border-primary/50'
                  )}
                  onClick={() => setSelectedTemplate(recommendations.recommended_template)}
                >
                  <CardContent className="p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <Star className="h-5 w-5 text-primary" />
                      <h4 className="text-lg font-semibold">
                        {recommendations.recommended_template.name}
                      </h4>
                      <Badge>Recommended</Badge>
                    </div>
                    <p className="text-sm text-muted-foreground mb-3">
                      {recommendations.recommended_template.description}
                    </p>
                    <div className="flex gap-2">
                      <Badge variant="outline" size="sm">{recommendations.recommended_template.industry}</Badge>
                      <Badge variant="outline" size="sm">{recommendations.recommended_template.difficulty}</Badge>
                      <Badge variant="secondary" size="sm" icon={<TrendingUp className="h-3 w-3" />}>
                        {recommendations.recommended_template.usage_count} uses
                      </Badge>
                    </div>
                  </CardContent>
                </Card>

                {/* Alternative Templates */}
                {recommendations.alternative_templates.length > 0 && (
                  <>
                    <div className="flex items-center gap-4">
                      <hr className="flex-grow border-border" />
                      <span className="text-xs text-muted-foreground">Alternatives</span>
                      <hr className="flex-grow border-border" />
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {recommendations.alternative_templates.map((template) => (
                        <Card
                          key={template.id}
                          variant="outlined"
                          className={cn(
                            'cursor-pointer transition-all h-full',
                            selectedTemplate?.id === template.id
                              ? 'border-2 border-primary'
                              : 'hover:border-primary/50'
                          )}
                          onClick={() => setSelectedTemplate(template)}
                        >
                          <CardContent className="p-3">
                            <h5 className="font-medium mb-1">{template.name}</h5>
                            <p className="text-xs text-muted-foreground mb-2">
                              {template.short_description || template.description.substring(0, 100) + '...'}
                            </p>
                            <div className="flex gap-1 flex-wrap">
                              <Badge variant="outline" size="sm">{template.industry}</Badge>
                              <Badge variant="outline" size="sm">{template.difficulty}</Badge>
                            </div>
                          </CardContent>
                        </Card>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        );

      case 2:
        return (
          <div>
            <h3 className="text-lg font-semibold mb-4">
              Review & Launch
            </h3>

            {selectedTemplate && (
              <div className="space-y-4">
                <Card variant="outlined">
                  <CardContent className="p-4">
                    <p className="text-sm text-muted-foreground mb-1">Selected Template</p>
                    <h4 className="text-lg font-semibold text-primary">
                      {selectedTemplate.name}
                    </h4>
                    <p className="text-sm text-muted-foreground mt-1">
                      {selectedTemplate.description}
                    </p>
                  </CardContent>
                </Card>

                <Card variant="outlined">
                  <CardContent className="p-4">
                    <p className="text-sm text-muted-foreground mb-3">Configuration Summary</p>
                    <div className="space-y-2">
                      <div className="flex justify-between text-sm">
                        <span>Industry:</span>
                        <span className="font-medium">{industry}</span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span>Difficulty:</span>
                        <span className="font-medium">{difficulty}</span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span>ScenarioUsers:</span>
                        <span className="font-medium">{numScenarioUsers}</span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span>Monte Carlo:</span>
                        <span className="font-medium">{useMonteCarlo ? 'Enabled' : 'Disabled'}</span>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {recommendations && recommendations.next_steps && (
                  <Card variant="outlined">
                    <CardContent className="p-4">
                      <p className="text-sm text-muted-foreground mb-2">Next Steps</p>
                      <ol className="list-decimal pl-4 space-y-1">
                        {recommendations.next_steps.map((step, index) => (
                          <li key={index} className="text-sm">{step}</li>
                        ))}
                      </ol>
                    </CardContent>
                  </Card>
                )}
              </div>
            )}
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <Modal isOpen={open} onClose={onClose} size="lg">
      <ModalHeader>
        <div className="flex justify-between items-center w-full">
          <ModalTitle>Quick Start Wizard</ModalTitle>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      </ModalHeader>

      <ModalBody>
        {/* Stepper */}
        <div className="flex items-center mb-6">
          {steps.map((label, index) => (
            <React.Fragment key={label}>
              <div className="flex items-center">
                <div
                  className={cn(
                    'w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium',
                    index < activeStep && 'bg-primary text-primary-foreground',
                    index === activeStep && 'bg-primary text-primary-foreground',
                    index > activeStep && 'bg-muted text-muted-foreground'
                  )}
                >
                  {index < activeStep ? <Check className="h-4 w-4" /> : index + 1}
                </div>
                <span className={cn(
                  'ml-2 text-sm hidden sm:inline',
                  index === activeStep && 'font-medium'
                )}>
                  {label}
                </span>
              </div>
              {index < steps.length - 1 && (
                <div className={cn(
                  'flex-1 h-0.5 mx-2',
                  index < activeStep ? 'bg-primary' : 'bg-muted'
                )} />
              )}
            </React.Fragment>
          ))}
        </div>

        {error && (
          <Alert variant="error" className="mb-4" onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        {renderStepContent(activeStep)}
      </ModalBody>

      <ModalFooter>
        <Button variant="ghost" onClick={handleReset}>Reset</Button>
        <div className="flex-1" />
        <Button
          variant="ghost"
          disabled={activeStep === 0}
          onClick={handleBack}
          leftIcon={<ChevronLeft className="h-4 w-4" />}
        >
          Back
        </Button>
        {activeStep === steps.length - 1 ? (
          <Button
            onClick={handleLaunch}
            disabled={!selectedTemplate}
            rightIcon={<Check className="h-4 w-4" />}
          >
            Launch Game
          </Button>
        ) : (
          <Button
            onClick={handleNext}
            disabled={loading}
            rightIcon={<ChevronRight className="h-4 w-4" />}
          >
            Next
          </Button>
        )}
      </ModalFooter>
    </Modal>
  );
};

export default QuickStartWizard;
