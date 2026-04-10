/**
 * Capacity Promise Agent — Lane/carrier capacity to promise on a date.
 *
 * Phase: SENSE
 * Replaces TMS DecisionCard.jsx EDITABLE_FIELDS.capacity_promise
 */
import { Gauge } from 'lucide-react';

export const capacityPromiseType = {
  id: 'capacity_promise',
  label: 'Capacity Promise Agent',
  icon: Gauge,
  phase: 'SENSE',
  editableFields: [
    { key: 'available_loads', label: 'Available Loads', type: 'number' },
    { key: 'promised_date', label: 'Promise Date', type: 'date' },
    { key: 'carrier_id', label: 'Carrier', type: 'text' },
  ],
  description: 'Available capacity to promise on lane/carrier/date',
};
