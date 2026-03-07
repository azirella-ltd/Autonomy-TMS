/**
 * Alert Banner Component
 *
 * Dismissible alert strip for CDC triggers and condition monitor alerts.
 * Color-coded by severity. Shown at the top of the Decision Stream.
 */
import React, { useState } from 'react';
import { AlertTriangle, Info, XCircle, X, Zap } from 'lucide-react';
import { cn } from '../../lib/utils/cn';

const SEVERITY_CONFIG = {
  info: {
    bg: 'bg-blue-50 border-blue-200',
    text: 'text-blue-800',
    icon: Info,
  },
  warning: {
    bg: 'bg-amber-50 border-amber-200',
    text: 'text-amber-800',
    icon: AlertTriangle,
  },
  critical: {
    bg: 'bg-red-50 border-red-200',
    text: 'text-red-800',
    icon: XCircle,
  },
  emergency: {
    bg: 'bg-red-100 border-red-300',
    text: 'text-red-900',
    icon: Zap,
  },
};

const AlertBanner = ({ alerts = [], onDismiss }) => {
  const [dismissed, setDismissed] = useState(new Set());

  if (!alerts.length) return null;

  const visible = alerts.filter((a) => !dismissed.has(a.id || a.message));
  if (!visible.length) return null;

  const handleDismiss = (alert) => {
    const key = alert.id || alert.message;
    setDismissed((prev) => new Set([...prev, key]));
    onDismiss?.(alert);
  };

  // Group by severity for display
  const critical = visible.filter(
    (a) => a.severity === 'critical' || a.severity === 'emergency'
  );
  const warnings = visible.filter((a) => a.severity === 'warning');
  const infos = visible.filter(
    (a) => a.severity === 'info' || !a.severity
  );
  const ordered = [...critical, ...warnings, ...infos];

  return (
    <div className="space-y-2 mb-4">
      {ordered.map((alert, idx) => {
        const config = SEVERITY_CONFIG[alert.severity] || SEVERITY_CONFIG.warning;
        const IconComponent = config.icon;

        return (
          <div
            key={alert.id || idx}
            className={cn(
              'flex items-center gap-3 px-4 py-2.5 rounded-lg border',
              config.bg
            )}
          >
            <IconComponent className={cn('h-4 w-4 flex-shrink-0', config.text)} />
            <p className={cn('text-sm flex-1', config.text)}>{alert.message}</p>
            {alert.source && (
              <span className="text-xs opacity-60 flex-shrink-0">{alert.source}</span>
            )}
            <button
              onClick={() => handleDismiss(alert)}
              className={cn(
                'p-1 rounded hover:bg-black/10 transition-colors flex-shrink-0',
                config.text
              )}
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
};

export default AlertBanner;
