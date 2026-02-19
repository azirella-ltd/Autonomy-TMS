import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Card,
  CardContent,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../common';

const DEMAND_TYPE_OPTIONS = [
  { value: 'none', label: 'None' },
  { value: 'constant', label: 'Constant' },
  { value: 'random', label: 'Random' },
  { value: 'seasonal', label: 'Seasonal' },
  { value: 'trending', label: 'Trending' },
  { value: 'classic', label: 'Classic (Step)' },
  { value: 'lognormal', label: 'Log-Normal' },
];

const VARIABILITY_OPTIONS = [
  { value: 'flat', label: 'Flat' },
  { value: 'step', label: 'Step' },
  { value: 'uniform', label: 'Uniform' },
  { value: 'lognormal', label: 'LogNormal' },
  { value: 'normal', label: 'Normal' },
];

const SEASONALITY_OPTIONS = [
  { value: 'none', label: 'None' },
  { value: 'multiplicative', label: 'Multiplicative' },
];

const TREND_OPTIONS = [
  { value: 'none', label: 'None' },
  { value: 'linear', label: 'Linear' },
];

const DEFAULT_PATTERN = {
  demand_type: 'constant',
  variability: { type: 'flat', value: 4 },
  seasonality: { type: 'none', amplitude: 0, period: 12, phase: 0 },
  trend: { type: 'none', slope: 0, intercept: 0 },
  parameters: { value: 4 },
  params: { value: 4 },
};

const DemandPatternInput = ({ value = DEFAULT_PATTERN, onChange, disabled = false }) => {
  const [pattern, setPattern] = useState(() => ({ ...DEFAULT_PATTERN, ...value }));
  const [errors, setErrors] = useState({});

  useEffect(() => {
    setPattern((prev) => ({ ...prev, ...value }));
  }, [value]);

  const syncParameters = useCallback((nextPattern) => {
    const params = { ...(nextPattern.parameters || {}), ...(nextPattern.params || {}) };

    switch (nextPattern.demand_type) {
      case 'classic': {
        const initial = Number(params.initial_demand ?? params.value ?? 4) || 4;
        const changeWeek = Number(params.change_week ?? 15) || 15;
        const finalDemand = Number(params.final_demand ?? initial) || initial;
        params.initial_demand = initial;
        params.change_week = changeWeek;
        params.final_demand = finalDemand;
        break;
      }
      case 'constant': {
        const baseValue = Number(
          nextPattern.variability?.value ?? params.value ?? params.initial_demand
        ) || 0;
        params.value = baseValue;
        break;
      }
      case 'random': {
        if (nextPattern.variability?.type === 'uniform') {
          const fallbackMin =
            nextPattern.variability.minimum ??
            params.min_demand ??
            params.min ??
            0;
          const resolvedMin = Number(fallbackMin) || 0;
          const fallbackMax =
            nextPattern.variability.maximum ??
            params.max_demand ??
            params.max ??
            fallbackMin;
          const resolvedMax = Number(fallbackMax) || resolvedMin || 0;

          params.min_demand = resolvedMin;
          params.max_demand = resolvedMax < resolvedMin ? resolvedMin : resolvedMax;

          delete params.min;
          delete params.max;
        }
        break;
      }
      case 'lognormal':
      case 'normal': {
        const mean = Number(nextPattern.variability?.mean ?? params.mean ?? 4) || 4;
        const cov = Number(nextPattern.variability?.cov ?? params.cov ?? 0.5) || 0.5;
        params.mean = mean;
        params.cov = cov;
        break;
      }
      default:
        break;
    }

    return {
      ...nextPattern,
      parameters: params,
      params,
    };
  }, []);

  const updatePattern = useCallback((updater) => {
    setPattern((prev) => {
      const next = syncParameters(updater(prev));
      onChange?.(next);
      return next;
    });
  }, [onChange, syncParameters]);

  const handleDemandTypeChange = (nextType) => {
    updatePattern((prev) => ({
      ...prev,
      demand_type: nextType,
    }));
  };

  const handleVariabilityChange = useCallback((field, rawValue) => {
    const valueAsNumber = rawValue === '' ? '' : Number(rawValue);
    updatePattern((prev) => ({
      ...prev,
      variability: {
        ...prev.variability,
        [field]: Number.isNaN(valueAsNumber) ? prev.variability?.[field] : valueAsNumber,
      },
    }));
  }, [updatePattern]);

  const handleVariabilityTypeChange = (type) => {
    updatePattern((prev) => ({
      ...prev,
      variability: {
        type,
        value: type === 'flat' ? prev.variability?.value ?? 4 : undefined,
        start: undefined,
        end: undefined,
        period: undefined,
        minimum: undefined,
        maximum: undefined,
        mean: undefined,
        cov: undefined,
      },
    }));
  };

  const handleSeasonalityChange = (field, rawValue) => {
    const valueAsNumber = rawValue === '' ? '' : Number(rawValue);
    updatePattern((prev) => ({
      ...prev,
      seasonality: {
        ...prev.seasonality,
        [field]: Number.isNaN(valueAsNumber) ? prev.seasonality?.[field] : valueAsNumber,
      },
    }));
  };

  const handleSeasonalityTypeChange = (type) => {
    updatePattern((prev) => ({
      ...prev,
      seasonality: {
        type,
        amplitude: type === 'none' ? 0 : prev.seasonality?.amplitude ?? 1,
        period: type === 'none' ? 12 : prev.seasonality?.period ?? 12,
        phase: prev.seasonality?.phase ?? 0,
      },
    }));
  };

  const handleTrendChange = (field, rawValue) => {
    const valueAsNumber = rawValue === '' ? '' : Number(rawValue);
    updatePattern((prev) => ({
      ...prev,
      trend: {
        ...prev.trend,
        [field]: Number.isNaN(valueAsNumber) ? prev.trend?.[field] : valueAsNumber,
      },
    }));
  };

  const handleTrendTypeChange = (type) => {
    updatePattern((prev) => ({
      ...prev,
      trend: {
        type,
        slope: type === 'linear' ? prev.trend?.slope ?? 0 : 0,
        intercept: type === 'linear' ? prev.trend?.intercept ?? 0 : 0,
      },
    }));
  };

  const handleParameterChange = (field, rawValue) => {
    const valueAsNumber = rawValue === '' ? '' : Number(rawValue);
    updatePattern((prev) => ({
      ...prev,
      parameters: {
        ...prev.parameters,
        [field]: Number.isNaN(valueAsNumber) ? prev.parameters?.[field] : valueAsNumber,
      },
      params: {
        ...prev.params,
        [field]: Number.isNaN(valueAsNumber) ? prev.params?.[field] : valueAsNumber,
      },
    }));
  };

  useEffect(() => {
    const nextErrors = {};
    if (pattern.demand_type !== 'none') {
      if (pattern.variability?.type === 'step') {
        if (
          pattern.variability.start === undefined ||
          pattern.variability.end === undefined ||
          pattern.variability.period === undefined
        ) {
          nextErrors.variability = 'Step variability requires start, end, and period.';
        }
      }
      if (pattern.variability?.type === 'uniform') {
        if (
          pattern.variability.minimum === undefined ||
          pattern.variability.maximum === undefined ||
          pattern.variability.maximum < pattern.variability.minimum
        ) {
          nextErrors.variability = 'Uniform variability requires valid min and max values.';
        }
      }
      if (
        ['lognormal', 'normal'].includes(pattern.variability?.type) &&
        (pattern.variability.mean === undefined || pattern.variability.cov === undefined)
      ) {
        nextErrors.variability = 'Normal and LogNormal variability require mean and CoV.';
      }
    }
    setErrors(nextErrors);
  }, [pattern]);

  const variabilityFields = useMemo(() => {
    const type = pattern.variability?.type || 'flat';
    switch (type) {
      case 'flat':
        return (
          <div className="col-span-12 sm:col-span-4">
            <Label>Value</Label>
            <Input
              type="number"
              value={pattern.variability?.value ?? ''}
              onChange={(e) => handleVariabilityChange('value', e.target.value)}
              disabled={disabled}
            />
          </div>
        );
      case 'step':
        return (
          <>
            <div className="col-span-12 sm:col-span-4">
              <Label>Starting</Label>
              <Input
                type="number"
                value={pattern.variability?.start ?? ''}
                onChange={(e) => handleVariabilityChange('start', e.target.value)}
                disabled={disabled}
              />
            </div>
            <div className="col-span-12 sm:col-span-4">
              <Label>Ending</Label>
              <Input
                type="number"
                value={pattern.variability?.end ?? ''}
                onChange={(e) => handleVariabilityChange('end', e.target.value)}
                disabled={disabled}
              />
            </div>
            <div className="col-span-12 sm:col-span-4">
              <Label>Period</Label>
              <Input
                type="number"
                value={pattern.variability?.period ?? ''}
                onChange={(e) => handleVariabilityChange('period', e.target.value)}
                disabled={disabled}
              />
            </div>
          </>
        );
      case 'uniform':
        return (
          <>
            <div className="col-span-12 sm:col-span-6">
              <Label>Minimum</Label>
              <Input
                type="number"
                value={pattern.variability?.minimum ?? ''}
                onChange={(e) => handleVariabilityChange('minimum', e.target.value)}
                disabled={disabled}
              />
            </div>
            <div className="col-span-12 sm:col-span-6">
              <Label>Maximum</Label>
              <Input
                type="number"
                value={pattern.variability?.maximum ?? ''}
                onChange={(e) => handleVariabilityChange('maximum', e.target.value)}
                disabled={disabled}
              />
            </div>
          </>
        );
      case 'lognormal':
      case 'normal':
        return (
          <>
            <div className="col-span-12 sm:col-span-6">
              <Label>Mean</Label>
              <Input
                type="number"
                value={pattern.variability?.mean ?? ''}
                onChange={(e) => handleVariabilityChange('mean', e.target.value)}
                disabled={disabled}
              />
            </div>
            <div className="col-span-12 sm:col-span-6">
              <Label>CoV</Label>
              <Input
                type="number"
                value={pattern.variability?.cov ?? ''}
                onChange={(e) => handleVariabilityChange('cov', e.target.value)}
                disabled={disabled}
              />
            </div>
          </>
        );
      default:
        return null;
    }
  }, [pattern.variability, disabled, handleVariabilityChange]);

  return (
    <Card variant="outline">
      <CardContent className="pt-4">
        <h3 className="font-medium mb-4">Demand Pattern</h3>
        <div className="grid grid-cols-12 gap-4">
          <div className="col-span-12 sm:col-span-4">
            <Label>Demand Type</Label>
            <Select
              value={pattern.demand_type}
              onValueChange={handleDemandTypeChange}
              disabled={disabled}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DEMAND_TYPE_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="mt-6">
          <h4 className="text-sm font-medium mb-3">Variability</h4>
          <div className="grid grid-cols-12 gap-4">
            <div className="col-span-12 sm:col-span-4">
              <Label>Type</Label>
              <Select
                value={pattern.variability?.type || 'flat'}
                onValueChange={handleVariabilityTypeChange}
                disabled={disabled}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {VARIABILITY_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {variabilityFields}
          </div>
          {errors.variability && (
            <p className="text-sm text-destructive mt-2">{errors.variability}</p>
          )}
        </div>

        <div className="mt-6">
          <h4 className="text-sm font-medium mb-3">Seasonality</h4>
          <div className="grid grid-cols-12 gap-4">
            <div className="col-span-12 sm:col-span-4">
              <Label>Type</Label>
              <Select
                value={pattern.seasonality?.type || 'none'}
                onValueChange={handleSeasonalityTypeChange}
                disabled={disabled}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SEASONALITY_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {pattern.seasonality?.type !== 'none' && (
              <>
                <div className="col-span-12 sm:col-span-4">
                  <Label>Amplitude</Label>
                  <Input
                    type="number"
                    value={pattern.seasonality?.amplitude ?? ''}
                    onChange={(e) => handleSeasonalityChange('amplitude', e.target.value)}
                    disabled={disabled}
                  />
                </div>
                <div className="col-span-12 sm:col-span-4">
                  <Label>Period</Label>
                  <Input
                    type="number"
                    value={pattern.seasonality?.period ?? ''}
                    onChange={(e) => handleSeasonalityChange('period', e.target.value)}
                    disabled={disabled}
                  />
                </div>
                <div className="col-span-12 sm:col-span-4">
                  <Label>Phase</Label>
                  <Input
                    type="number"
                    value={pattern.seasonality?.phase ?? ''}
                    onChange={(e) => handleSeasonalityChange('phase', e.target.value)}
                    disabled={disabled}
                  />
                </div>
              </>
            )}
          </div>
        </div>

        <div className="mt-6">
          <h4 className="text-sm font-medium mb-3">Trend</h4>
          <div className="grid grid-cols-12 gap-4">
            <div className="col-span-12 sm:col-span-4">
              <Label>Type</Label>
              <Select
                value={pattern.trend?.type || 'none'}
                onValueChange={handleTrendTypeChange}
                disabled={disabled}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TREND_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {pattern.trend?.type === 'linear' && (
              <>
                <div className="col-span-12 sm:col-span-4">
                  <Label>Slope</Label>
                  <Input
                    type="number"
                    value={pattern.trend?.slope ?? ''}
                    onChange={(e) => handleTrendChange('slope', e.target.value)}
                    disabled={disabled}
                  />
                </div>
                <div className="col-span-12 sm:col-span-4">
                  <Label>Intercept</Label>
                  <Input
                    type="number"
                    value={pattern.trend?.intercept ?? ''}
                    onChange={(e) => handleTrendChange('intercept', e.target.value)}
                    disabled={disabled}
                  />
                </div>
              </>
            )}
          </div>
        </div>

        {pattern.demand_type === 'classic' && (
          <div className="mt-6">
            <h4 className="text-sm font-medium mb-3">Classic Parameters</h4>
            <div className="grid grid-cols-12 gap-4">
              <div className="col-span-12 sm:col-span-4">
                <Label>Initial Demand</Label>
                <Input
                  type="number"
                  value={pattern.parameters?.initial_demand ?? ''}
                  onChange={(e) => handleParameterChange('initial_demand', e.target.value)}
                  disabled={disabled}
                />
              </div>
              <div className="col-span-12 sm:col-span-4">
                <Label>Change Week</Label>
                <Input
                  type="number"
                  value={pattern.parameters?.change_week ?? ''}
                  onChange={(e) => handleParameterChange('change_week', e.target.value)}
                  disabled={disabled}
                />
              </div>
              <div className="col-span-12 sm:col-span-4">
                <Label>Final Demand</Label>
                <Input
                  type="number"
                  value={pattern.parameters?.final_demand ?? ''}
                  onChange={(e) => handleParameterChange('final_demand', e.target.value)}
                  disabled={disabled}
                />
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default DemandPatternInput;
