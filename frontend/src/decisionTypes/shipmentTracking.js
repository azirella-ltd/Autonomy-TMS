/**
 * Shipment Tracking Agent — In-transit visibility, ETA, exception detection.
 *
 * Phase: SENSE
 */
import { MapPin } from 'lucide-react';

export const shipmentTrackingType = {
  id: 'shipment_tracking',
  label: 'Shipment Tracking Agent',
  icon: MapPin,
  phase: 'SENSE',
  editableFields: [
    { key: 'eta_override', label: 'ETA Override', type: 'date' },
    {
      key: 'exception_action',
      label: 'Action',
      type: 'select',
      options: ['reroute', 'retender', 'hold', 'escalate'],
    },
  ],
  description: 'In-transit visibility, ETA prediction, exception detection',
};
