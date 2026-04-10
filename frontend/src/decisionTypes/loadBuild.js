/**
 * Load Build Agent — Load consolidation and optimization.
 *
 * Phase: BUILD
 */
import { Layers } from 'lucide-react';

export const loadBuildType = {
  id: 'load_build',
  label: 'Load Build Agent',
  icon: Layers,
  phase: 'BUILD',
  editableFields: [
    {
      key: 'action',
      label: 'Action',
      type: 'select',
      options: ['consolidate', 'split', 'hold', 'expedite'],
    },
    {
      key: 'equipment_type',
      label: 'Equipment',
      type: 'select',
      options: ['dry_van', 'reefer', 'flatbed', 'container'],
    },
  ],
  description: 'Load consolidation, weight/volume optimization, multi-stop sequencing',
};
