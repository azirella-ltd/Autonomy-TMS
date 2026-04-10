/**
 * Demand Sensing Agent — Shipping volume forecast adjustments from signals.
 *
 * Phase: SENSE
 */
import { Signal } from 'lucide-react';

export const demandSensingType = {
  id: 'demand_sensing',
  label: 'Demand Sensing Agent',
  icon: Signal,
  phase: 'SENSE',
  editableFields: [
    { key: 'adjusted_forecast_loads', label: 'Adjusted Forecast (loads)', type: 'number' },
    {
      key: 'adjustment_reason',
      label: 'Adjustment Reason',
      type: 'select',
      options: [
        'seasonal_shift',
        'volume_surge',
        'volume_drop',
        'signal_override',
        'market_intelligence',
      ],
    },
  ],
  description: 'Shipping volume forecast adjustments from real-time signals',
};
