/**
 * Equipment Reposition Agent — Empty container/trailer repositioning.
 *
 * Phase: REFLECT
 */
import { Container } from 'lucide-react';

export const equipmentRepositionType = {
  id: 'equipment_reposition',
  label: 'Equipment Reposition Agent',
  icon: Container,
  phase: 'REFLECT',
  editableFields: [
    { key: 'quantity', label: 'Equipment Qty', type: 'number' },
    { key: 'target_facility', label: 'Target Facility', type: 'text' },
    {
      key: 'action',
      label: 'Action',
      type: 'select',
      options: ['reposition', 'hold', 'defer'],
    },
  ],
  description: 'Empty container/trailer repositioning to deficit facilities',
};
