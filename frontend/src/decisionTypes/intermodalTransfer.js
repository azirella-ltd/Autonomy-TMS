/**
 * Intermodal Transfer Agent — Cross-mode transfers (truck/rail/ocean).
 *
 * Phase: BUILD
 */
import { Train } from 'lucide-react';

export const intermodalTransferType = {
  id: 'intermodal_transfer',
  label: 'Intermodal Transfer Agent',
  icon: Train,
  phase: 'BUILD',
  editableFields: [
    {
      key: 'target_mode',
      label: 'Target Mode',
      type: 'select',
      options: ['road', 'rail', 'ocean', 'air'],
    },
    {
      key: 'accept_transit_penalty',
      label: 'Accept Transit Penalty',
      type: 'select',
      options: ['yes', 'no'],
    },
  ],
  description: 'Cross-mode transfer decisions and drayage coordination',
};
