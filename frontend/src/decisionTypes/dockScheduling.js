/**
 * Dock Scheduling Agent — Appointment and dock door optimization.
 *
 * Phase: PROTECT
 */
import { DoorOpen } from 'lucide-react';

export const dockSchedulingType = {
  id: 'dock_scheduling',
  label: 'Dock Scheduling Agent',
  icon: DoorOpen,
  phase: 'PROTECT',
  editableFields: [
    { key: 'dock_door_id', label: 'Dock Door', type: 'text' },
    { key: 'appointment_time', label: 'Appointment Time', type: 'date' },
    {
      key: 'priority',
      label: 'Priority',
      type: 'select',
      options: ['expedite', 'standard', 'defer'],
    },
  ],
  description: 'Appointment scheduling and dock door optimization',
};
