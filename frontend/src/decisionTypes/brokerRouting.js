/**
 * Broker Routing Agent — Broker vs asset carrier decision.
 *
 * Phase: ACQUIRE
 */
import { GitBranch } from 'lucide-react';

export const brokerRoutingType = {
  id: 'broker_routing',
  label: 'Broker Routing Agent',
  icon: GitBranch,
  phase: 'ACQUIRE',
  editableFields: [
    { key: 'broker_id', label: 'Broker', type: 'text' },
    { key: 'max_rate', label: 'Max Rate ($)', type: 'number' },
  ],
  description: 'Broker vs asset carrier routing for overflow loads',
};
