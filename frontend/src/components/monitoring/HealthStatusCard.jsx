/**
 * Health Status Card Component
 * Phase 6 Sprint 3: Monitoring & Observability
 *
 * Displays health status for individual system components.
 * Features:
 * - Traffic light color indicators
 * - Response time display
 * - Component details
 * - Status messages
 *
 * Migrated to Autonomy UI Kit (Tailwind CSS + lucide-react)
 */

import React, { useState } from 'react';
import { Card, CardContent, Badge, IconButton } from '../common';
import {
  CheckCircle,
  AlertTriangle,
  XCircle,
  ChevronDown,
} from 'lucide-react';
import { cn } from '../../lib/utils/cn';

const HealthStatusCard = ({ check }) => {
  const [expanded, setExpanded] = useState(false);

  // Get status icon
  const getStatusIcon = (status) => {
    switch (status) {
      case 'healthy':
        return <CheckCircle className="w-10 h-10 text-emerald-500" />;
      case 'degraded':
        return <AlertTriangle className="w-10 h-10 text-amber-500" />;
      case 'unhealthy':
        return <XCircle className="w-10 h-10 text-red-500" />;
      default:
        return <CheckCircle className="w-10 h-10 text-gray-400" />;
    }
  };

  // Get badge variant
  const getBadgeVariant = (status) => {
    switch (status) {
      case 'healthy':
        return 'success';
      case 'degraded':
        return 'warning';
      case 'unhealthy':
        return 'destructive';
      default:
        return 'secondary';
    }
  };

  // Get card border color
  const getBorderColorClass = (status) => {
    switch (status) {
      case 'healthy':
        return 'border-l-emerald-500';
      case 'degraded':
        return 'border-l-amber-500';
      case 'unhealthy':
        return 'border-l-red-500';
      default:
        return 'border-l-gray-300';
    }
  };

  // Format component name
  const formatName = (name) => {
    return name
      .split('_')
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  // Handle expand
  const handleExpandClick = () => {
    setExpanded(!expanded);
  };

  const hasDetails = check.details && Object.keys(check.details).length > 0;

  return (
    <Card
      className={cn(
        'h-full border-l-4 transition-all duration-200 hover:-translate-y-1 hover:shadow-lg',
        getBorderColorClass(check.status)
      )}
    >
      <CardContent className="p-4">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          {getStatusIcon(check.status)}
          <Badge variant={getBadgeVariant(check.status)} size="sm">
            {check.status.toUpperCase()}
          </Badge>
        </div>

        {/* Component Name */}
        <h3 className="text-lg font-semibold mb-2">
          {formatName(check.name)}
        </h3>

        {/* Status Message */}
        {check.message && (
          <p className="text-sm text-muted-foreground mb-2">
            {check.message}
          </p>
        )}

        {/* Response Time */}
        {check.response_time_ms !== undefined && check.response_time_ms !== null && (
          <div className="mt-4">
            <span className="text-xs text-muted-foreground block">
              Response Time
            </span>
            <span className="text-sm font-medium">
              {check.response_time_ms.toFixed(2)} ms
            </span>
          </div>
        )}

        {/* Expand button for details */}
        {hasDetails && (
          <div className="flex justify-end mt-2">
            <IconButton
              onClick={handleExpandClick}
              aria-expanded={expanded}
              aria-label={expanded ? 'Hide details' : 'Show details'}
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              title={expanded ? 'Hide details' : 'Show details'}
            >
              <ChevronDown
                className={cn(
                  'h-5 w-5 transition-transform duration-200',
                  expanded && 'rotate-180'
                )}
              />
            </IconButton>
          </div>
        )}

        {/* Details */}
        {hasDetails && expanded && (
          <div className="mt-4 pt-4 border-t border-border">
            <span className="text-xs text-muted-foreground block mb-2">
              Details
            </span>
            {Object.entries(check.details).map(([key, value]) => (
              <div key={key} className="flex justify-between mt-2">
                <span className="text-sm text-muted-foreground">
                  {formatName(key)}:
                </span>
                <span className="text-sm font-medium">
                  {typeof value === 'number' ? value.toFixed(2) : String(value)}
                </span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default HealthStatusCard;
