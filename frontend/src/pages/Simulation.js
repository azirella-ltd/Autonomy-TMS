import React, { useEffect, useState } from 'react';
import {
  Button,
  Card,
  CardContent,
  Label,
  Switch,
} from '../components/common';
import {
  Play,
  Pause,
  Square,
  SkipForward,
  SkipBack,
} from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, Legend, ResponsiveContainer } from 'recharts';
import { LLM_BASE_MODEL_OPTIONS, DEFAULT_LLM_BASE_MODEL } from '../constants/llmModels';

// Sample data for the simulation
const sampleDemandData = [
  { week: 'W1', demand: 4000 },
  { week: 'W2', demand: 3000 },
  { week: 'W3', demand: 5000 },
  { week: 'W4', demand: 2780 },
  { week: 'W5', demand: 1890 },
  { week: 'W6', demand: 2390 },
];

const sampleInventoryData = [
  { week: 'W1', inventory: 4000, reorder: 2000 },
  { week: 'W2', inventory: 3000, reorder: 2000 },
  { week: 'W3', inventory: 2000, reorder: 2000 },
  { week: 'W4', inventory: 2780, reorder: 2000 },
  { week: 'W5', inventory: 1890, reorder: 2000 },
  { week: 'W6', inventory: 2390, reorder: 2000 },
];

const simulationSteps = [
  'Configure Simulation',
  'Review Parameters',
  'Run Simulation',
  'Analyze Results',
];

const demandPatternOptions = [
  { value: 'classic_step', label: 'Classic (Step Change)' },
  { value: 'random', label: 'Random' },
  { value: 'seasonal', label: 'Seasonal' },
  { value: 'custom', label: 'Custom Scenario' },
];

const llmModelOptions = LLM_BASE_MODEL_OPTIONS;

const ParameterSlider = ({
  label,
  description,
  value,
  min,
  max,
  step = 1,
  onChange,
  valueFormatter,
  disabled = false,
}) => (
  <div className={disabled ? 'opacity-60' : ''}>
    <div className="flex justify-between items-start">
      <div>
        <p className="text-sm font-medium">{label}</p>
        {description && (
          <p className="text-xs text-muted-foreground">{description}</p>
        )}
      </div>
      <p className="text-sm text-muted-foreground">
        {valueFormatter ? valueFormatter(value) : value}
      </p>
    </div>
    <input
      type="range"
      value={value}
      min={min}
      max={max}
      step={step}
      onChange={onChange}
      disabled={disabled}
      className="w-full mt-2 accent-primary"
    />
  </div>
);

const ToggleControl = ({ label, description, checked, onChange, disabled = false }) => (
  <div className={`flex justify-between items-center py-2 ${disabled ? 'opacity-60' : ''}`}>
    <div className="pr-4">
      <p className="text-sm font-medium">{label}</p>
      {description && (
        <p className="text-xs text-muted-foreground">{description}</p>
      )}
    </div>
    <Switch checked={checked} onCheckedChange={onChange} disabled={disabled} />
  </div>
);

const SummaryItem = ({ label, value }) => (
  <div>
    <p className="text-xs text-muted-foreground">{label}</p>
    <p className="text-sm font-medium">{value}</p>
  </div>
);

const SummaryRow = ({ label, value }) => (
  <div className="flex justify-between items-center py-2">
    <p className="text-sm text-muted-foreground">{label}</p>
    <p className="text-sm">{value}</p>
  </div>
);

const formatBoolean = (value) => (value ? 'Enabled' : 'Disabled');
const formatWeeks = (value) => `${value} week${value === 1 ? '' : 's'}`;
const formatUnits = (value) => `${value} unit${value === 1 ? '' : 's'}`;
const formatCurrencyPerUnit = (value) => `$${value.toFixed(2)}/unit/week`;

const Simulation = () => {
  const [activeStep, setActiveStep] = useState(0);
  const [simulationState, setSimulationState] = useState('idle'); // 'idle', 'running', 'paused', 'completed'
  const [currentWeek, setCurrentWeek] = useState(0);
  const [config, setConfig] = useState({
    duration: 40,
    orderLeadTime: 2,
    shippingLeadTime: 1,
    productionDelay: 2,
    initialInventory: 12,
    holdingCost: 0.5,
    backorderCost: 1.0,
    infoSharing: true,
    historicalWeeks: 6,
    demandVolatility: true,
    confidenceThreshold: 60,
    pipelineInventory: true,
    centralizedForecast: false,
    manufacturerVisibility: false,
    demandPattern: 'classic_step',
    initialDemand: 4,
    newDemand: 8,
    demandChangeWeek: 6,
    llmModel: DEFAULT_LLM_BASE_MODEL,
    useRlModel: false,
  });

  const handleNext = () => {
    setActiveStep((prevStep) => prevStep + 1);
  };

  const handleBack = () => {
    setActiveStep((prevStep) => prevStep - 1);
  };

  const updateConfig = (field, value) => {
    setConfig((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  const handleSliderChange = (field) => (e) => {
    updateConfig(field, Number(e.target.value));
  };

  const handleToggleChange = (field) => (checked) => {
    updateConfig(field, checked);
  };

  const handleSelectChange = (field) => (event) => {
    updateConfig(field, event.target.value);
  };

  useEffect(() => {
    if (currentWeek > config.duration - 1) {
      setCurrentWeek(Math.max(0, config.duration - 1));
    }
  }, [config.duration, currentWeek]);

  const handleStartSimulation = () => {
    setSimulationState('running');
    // In a real implementation, this would connect to the backend
  };

  const handlePauseSimulation = () => {
    setSimulationState('paused');
  };

  const handleStopSimulation = () => {
    setSimulationState('idle');
    setCurrentWeek(0);
  };

  const handleStepForward = () => {
    if (currentWeek < config.duration - 1) {
      setCurrentWeek(currentWeek + 1);
    } else {
      setSimulationState('completed');
    }
  };

  const handleStepBackward = () => {
    if (currentWeek > 0) {
      setCurrentWeek(currentWeek - 1);
    }
  };

  const renderStepContent = (step) => {
    switch (step) {
      case 0:
        return (
          <div className="grid grid-cols-1 lg:grid-cols-7 gap-6">
            <div className="lg:col-span-4">
              <Card>
                <CardContent className="pt-6">
                  <h3 className="text-lg font-semibold mb-4">Simulation Parameters</h3>
                  <div className="space-y-6">
                    <ParameterSlider
                      label="Number of weeks"
                      description="Duration of the simulation"
                      value={config.duration}
                      min={10}
                      max={52}
                      step={1}
                      onChange={handleSliderChange('duration')}
                      valueFormatter={formatWeeks}
                    />
                    <div className="grid grid-cols-2 gap-4">
                      <ParameterSlider
                        label="Order lead time (weeks)"
                        description="Time for scenarioUsers to receive orders"
                        value={config.orderLeadTime}
                        min={0}
                        max={8}
                        step={1}
                        onChange={handleSliderChange('orderLeadTime')}
                        valueFormatter={formatWeeks}
                      />
                      <ParameterSlider
                        label="Shipping lead time (weeks)"
                        description="Time for shipments to reach downstream partners"
                        value={config.shippingLeadTime}
                        min={0}
                        max={6}
                        step={1}
                        onChange={handleSliderChange('shippingLeadTime')}
                        valueFormatter={formatWeeks}
                      />
                      <ParameterSlider
                        label="Production delay (weeks)"
                        description="Time required to produce manufacturer orders"
                        value={config.productionDelay}
                        min={0}
                        max={6}
                        step={1}
                        onChange={handleSliderChange('productionDelay')}
                        valueFormatter={formatWeeks}
                      />
                      <ParameterSlider
                        label="Initial inventory"
                        description="Starting inventory for each scenarioUser"
                        value={config.initialInventory}
                        min={0}
                        max={50}
                        step={1}
                        onChange={handleSliderChange('initialInventory')}
                        valueFormatter={formatUnits}
                      />
                      <ParameterSlider
                        label="Holding cost"
                        description="Cost per unit of inventory per week"
                        value={config.holdingCost}
                        min={0}
                        max={5}
                        step={0.1}
                        onChange={handleSliderChange('holdingCost')}
                        valueFormatter={formatCurrencyPerUnit}
                      />
                      <ParameterSlider
                        label="Backorder cost"
                        description="Penalty per unit of unmet demand"
                        value={config.backorderCost}
                        min={0}
                        max={5}
                        step={0.1}
                        onChange={handleSliderChange('backorderCost')}
                        valueFormatter={formatCurrencyPerUnit}
                      />
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
            <div className="lg:col-span-3 space-y-6">
              <Card>
                <CardContent className="pt-6">
                  <h3 className="text-lg font-semibold mb-4">Decision Support Features</h3>
                  <div className="space-y-4">
                    <ToggleControl
                      label="Enable information sharing"
                      description="Share customer demand updates with all scenarioUsers"
                      checked={config.infoSharing}
                      onChange={handleToggleChange('infoSharing')}
                    />
                    <ParameterSlider
                      label="Historical weeks to share"
                      description="Amount of past demand data included in updates"
                      value={config.historicalWeeks}
                      min={0}
                      max={12}
                      step={1}
                      onChange={handleSliderChange('historicalWeeks')}
                      valueFormatter={formatWeeks}
                      disabled={!config.infoSharing}
                    />
                    <ToggleControl
                      label="Demand analysis with volatility insights"
                      description="Provide volatility commentary based on demand changes"
                      checked={config.demandVolatility}
                      onChange={handleToggleChange('demandVolatility')}
                    />
                    <ParameterSlider
                      label="Confidence threshold"
                      description="Minimum confidence required to surface volatility guidance"
                      value={config.confidenceThreshold}
                      min={0}
                      max={100}
                      step={5}
                      onChange={handleSliderChange('confidenceThreshold')}
                      valueFormatter={(value) => `${value}%`}
                      disabled={!config.demandVolatility}
                    />
                    <ToggleControl
                      label="Pipeline inventory sharing"
                      description="Show upstream orders and shipments to all scenarioUsers"
                      checked={config.pipelineInventory}
                      onChange={handleToggleChange('pipelineInventory')}
                    />
                    <ToggleControl
                      label="Centralized demand forecast"
                      description="Share a central demand forecast with each scenarioUser"
                      checked={config.centralizedForecast}
                      onChange={handleToggleChange('centralizedForecast')}
                    />
                    <ToggleControl
                      label="Supplier inventory visibility"
                      description="Reveal upstream manufacturer inventory levels"
                      checked={config.manufacturerVisibility}
                      onChange={handleToggleChange('manufacturerVisibility')}
                    />
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-6">
                  <h3 className="text-lg font-semibold mb-4">Demand Pattern</h3>
                  <div>
                    <Label htmlFor="demand-pattern">Demand Pattern</Label>
                    <select
                      id="demand-pattern"
                      value={config.demandPattern}
                      onChange={handleSelectChange('demandPattern')}
                      className="w-full mt-1 h-10 px-3 rounded-md border border-input bg-background"
                    >
                      {demandPatternOptions.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="space-y-4 mt-4">
                    <ParameterSlider
                      label="Initial demand"
                      description="Customer demand before any change"
                      value={config.initialDemand}
                      min={0}
                      max={20}
                      step={1}
                      onChange={handleSliderChange('initialDemand')}
                      valueFormatter={formatUnits}
                    />
                    <ParameterSlider
                      label="New demand after change"
                      description="Customer demand after the step change"
                      value={config.newDemand}
                      min={0}
                      max={30}
                      step={1}
                      onChange={handleSliderChange('newDemand')}
                      valueFormatter={formatUnits}
                      disabled={config.demandPattern !== 'classic_step'}
                    />
                    <ParameterSlider
                      label="Weeks before new demand"
                      description="Time before the demand shift takes effect"
                      value={config.demandChangeWeek}
                      min={1}
                      max={20}
                      step={1}
                      onChange={handleSliderChange('demandChangeWeek')}
                      valueFormatter={formatWeeks}
                      disabled={config.demandPattern !== 'classic_step'}
                    />
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-6">
                  <h3 className="text-lg font-semibold mb-4">Model Selection</h3>
                  <div>
                    <Label htmlFor="llm-model">Autonomy LLM Model</Label>
                    <select
                      id="llm-model"
                      value={config.llmModel}
                      onChange={handleSelectChange('llmModel')}
                      className="w-full mt-1 h-10 px-3 rounded-md border border-input bg-background"
                    >
                      {llmModelOptions.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="mt-4">
                    <ToggleControl
                      label="Enable RL model for decision making"
                      description="Use reinforcement learning support during the game"
                      checked={config.useRlModel}
                      onChange={handleToggleChange('useRlModel')}
                    />
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        );
      case 1: {
        const demandPatternLabel =
          demandPatternOptions.find((option) => option.value === config.demandPattern)?.label || config.demandPattern;
        const llmModelLabel =
          llmModelOptions.find((option) => option.value === config.llmModel)?.label || config.llmModel;
        const newDemandSummary =
          config.demandPattern === 'classic_step' ? formatUnits(config.newDemand) : 'N/A';
        const demandChangeSummary =
          config.demandPattern === 'classic_step' ? formatWeeks(config.demandChangeWeek) : 'N/A';

        return (
          <div className="grid grid-cols-1 lg:grid-cols-7 gap-6">
            <div className="lg:col-span-4">
              <Card>
                <CardContent className="pt-6">
                  <h3 className="text-lg font-semibold mb-4">Simulation Parameters Summary</h3>
                  <div className="grid grid-cols-2 gap-4">
                    <SummaryItem label="Number of weeks" value={formatWeeks(config.duration)} />
                    <SummaryItem label="Order lead time" value={formatWeeks(config.orderLeadTime)} />
                    <SummaryItem label="Shipping lead time" value={formatWeeks(config.shippingLeadTime)} />
                    <SummaryItem label="Production delay" value={formatWeeks(config.productionDelay)} />
                    <SummaryItem label="Initial inventory" value={formatUnits(config.initialInventory)} />
                    <SummaryItem label="Holding cost" value={formatCurrencyPerUnit(config.holdingCost)} />
                    <SummaryItem label="Backorder cost" value={formatCurrencyPerUnit(config.backorderCost)} />
                  </div>
                </CardContent>
              </Card>
            </div>
            <div className="lg:col-span-3 space-y-6">
              <Card>
                <CardContent className="pt-6">
                  <h3 className="text-lg font-semibold mb-4">Decision Support Features</h3>
                  <SummaryRow label="Information sharing" value={formatBoolean(config.infoSharing)} />
                  <SummaryRow
                    label="Historical weeks"
                    value={config.infoSharing ? formatWeeks(config.historicalWeeks) : 'Not shared'}
                  />
                  <SummaryRow label="Volatility analysis" value={formatBoolean(config.demandVolatility)} />
                  <SummaryRow
                    label="Confidence threshold"
                    value={config.demandVolatility ? `${config.confidenceThreshold}%` : 'N/A'}
                  />
                  <SummaryRow label="Pipeline inventory" value={formatBoolean(config.pipelineInventory)} />
                  <SummaryRow label="Centralized forecast" value={formatBoolean(config.centralizedForecast)} />
                  <SummaryRow label="Manufacturer visibility" value={formatBoolean(config.manufacturerVisibility)} />
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-6">
                  <h3 className="text-lg font-semibold mb-4">Demand Pattern</h3>
                  <SummaryRow label="Pattern" value={demandPatternLabel} />
                  <SummaryRow label="Initial demand" value={formatUnits(config.initialDemand)} />
                  <SummaryRow label="New demand" value={newDemandSummary} />
                  <SummaryRow label="Change occurs after" value={demandChangeSummary} />
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-6">
                  <h3 className="text-lg font-semibold mb-4">Models</h3>
                  <SummaryRow label="Autonomy LLM model" value={llmModelLabel} />
                  <SummaryRow label="RL model" value={formatBoolean(config.useRlModel)} />
                </CardContent>
              </Card>
            </div>
          </div>
        );
      }
      case 2:
        return (
          <div>
            <div className="flex justify-between items-center mb-6">
              <div>
                <h3 className="text-lg font-semibold">Simulation Controls</h3>
                <p className="text-sm text-muted-foreground">
                  {simulationState === 'idle' && 'Ready to start simulation'}
                  {simulationState === 'running' && 'Simulation in progress...'}
                  {simulationState === 'paused' && 'Simulation paused'}
                  {simulationState === 'completed' && 'Simulation completed'}
                </p>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="icon"
                  onClick={handleStepBackward}
                  disabled={currentWeek === 0 || simulationState === 'running'}
                >
                  <SkipBack className="h-4 w-4" />
                </Button>
                {simulationState === 'running' ? (
                  <Button variant="outline" size="icon" onClick={handlePauseSimulation}>
                    <Pause className="h-4 w-4" />
                  </Button>
                ) : (
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={handleStartSimulation}
                    disabled={simulationState === 'completed'}
                  >
                    <Play className="h-4 w-4" />
                  </Button>
                )}
                {simulationState !== 'completed' && (
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={handleStopSimulation}
                    disabled={simulationState === 'idle'}
                    className="text-destructive hover:text-destructive"
                  >
                    <Square className="h-4 w-4" />
                  </Button>
                )}
                <Button
                  variant="outline"
                  size="icon"
                  onClick={handleStepForward}
                  disabled={currentWeek >= config.duration - 1 || simulationState === 'running'}
                >
                  <SkipForward className="h-4 w-4" />
                </Button>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
              <Card>
                <CardContent className="pt-6">
                  <h3 className="text-lg font-semibold mb-4">Demand Forecast</h3>
                  <div className="h-[300px]">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={sampleDemandData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="week" />
                        <YAxis />
                        <RechartsTooltip />
                        <Legend />
                        <Line
                          type="monotone"
                          dataKey="demand"
                          stroke="#8884d8"
                          activeDot={{ r: 8 }}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-6">
                  <h3 className="text-lg font-semibold mb-4">Inventory Level</h3>
                  <div className="h-[300px]">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={sampleInventoryData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="week" />
                        <YAxis />
                        <RechartsTooltip />
                        <Legend />
                        <Line
                          type="monotone"
                          dataKey="inventory"
                          stroke="#82ca9d"
                          activeDot={{ r: 8 }}
                        />
                        <Line
                          type="monotone"
                          dataKey="reorder"
                          stroke="#ff7300"
                          strokeDasharray="5 5"
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardContent className="pt-6">
                <div className="flex justify-between items-center mb-4">
                  <h3 className="text-lg font-semibold">Simulation Progress</h3>
                  <p className="text-sm text-muted-foreground">
                    Week {currentWeek + 1} of {config.duration}
                  </p>
                </div>
                <input
                  type="range"
                  value={currentWeek}
                  min={0}
                  max={config.duration - 1}
                  onChange={(e) => setCurrentWeek(Number(e.target.value))}
                  disabled={simulationState === 'running'}
                  className="w-full accent-primary"
                />
                <div className="flex justify-between mt-2">
                  <span className="text-sm text-muted-foreground">Start</span>
                  <span className="text-sm text-muted-foreground">End</span>
                </div>
              </CardContent>
            </Card>
          </div>
        );
      case 3:
        return (
          <div>
            <h3 className="text-lg font-semibold mb-2">Simulation Results</h3>
            <p className="text-muted-foreground mb-6">
              Simulation completed successfully. Here are the key performance indicators:
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
              <Card>
                <CardContent className="pt-6">
                  <p className="text-sm text-muted-foreground mb-1">Total Cost</p>
                  <p className="text-4xl font-bold">$24,567</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-6">
                  <p className="text-sm text-muted-foreground mb-1">Average Inventory Level</p>
                  <p className="text-4xl font-bold">2,345 units</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-6">
                  <p className="text-sm text-muted-foreground mb-1">Service Level</p>
                  <p className="text-4xl font-bold">94.5%</p>
                </CardContent>
              </Card>
            </div>

            <h3 className="text-lg font-semibold mb-4">Detailed Analysis</h3>
            <div className="h-[400px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={sampleInventoryData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="week" />
                  <YAxis yAxisId="left" />
                  <YAxis yAxisId="right" orientation="right" />
                  <RechartsTooltip />
                  <Legend />
                  <Line yAxisId="left" type="monotone" dataKey="inventory" stroke="#8884d8" name="Inventory Level" />
                  <Line yAxisId="right" type="monotone" dataKey="reorder" stroke="#82ca9d" name="Reorder Point" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        );
      default:
        return 'Unknown step';
    }
  };

  return (
    <div className="container mx-auto py-8 px-4 max-w-7xl">
      <h1 className="text-3xl font-bold mb-6">Supply Chain Simulation</h1>

      {/* Stepper */}
      <div className="flex items-center mb-8">
        {simulationSteps.map((label, index) => (
          <React.Fragment key={label}>
            <div className="flex items-center">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                  index <= activeStep
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted text-muted-foreground'
                }`}
              >
                {index + 1}
              </div>
              <span className={`ml-2 text-sm ${index <= activeStep ? 'font-medium' : 'text-muted-foreground'}`}>
                {label}
              </span>
            </div>
            {index < simulationSteps.length - 1 && (
              <div className={`flex-1 h-0.5 mx-4 ${index < activeStep ? 'bg-primary' : 'bg-muted'}`} />
            )}
          </React.Fragment>
        ))}
      </div>

      {/* Step Content */}
      <div className="mb-8">
        {renderStepContent(activeStep)}
      </div>

      {/* Navigation */}
      <div className="flex justify-between pt-4">
        <Button
          variant="outline"
          onClick={handleBack}
          disabled={activeStep === 0}
        >
          Back
        </Button>
        {activeStep === simulationSteps.length - 1 ? (
          <Button onClick={handleStartSimulation}>
            Save Results
          </Button>
        ) : (
          <Button onClick={handleNext}>
            {activeStep === simulationSteps.length - 2 ? 'Finish' : 'Next'}
          </Button>
        )}
      </div>
    </div>
  );
};

export default Simulation;
