/**
 * CDTReadinessBanner — Shows conformal decision theory calibration status.
 *
 * Fetches CDT readiness from /conformal-prediction/cdt/readiness and displays
 * an info banner when not all TRM agents are calibrated. Hidden when fully ready.
 *
 * Uncalibrated TRMs use conservative risk_bound=0.50 which triggers more
 * escalations to human review — this banner explains that to the user.
 */
import { useState, useEffect } from 'react';
import { Info, CheckCircle2, ShieldAlert, ChevronDown, ChevronUp } from 'lucide-react';
import { api } from '../../services/api';
import { cn } from '../../lib/utils/cn';
import { useAuth } from '../../contexts/AuthContext';

const CDTReadinessBanner = ({ configId }) => {
  const { user, isTenantAdmin } = useAuth();
  const isAdmin = isTenantAdmin || user?.decision_level === 'DEMO_ALL';

  const [data, setData] = useState(null);
  const [expanded, setExpanded] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    const params = configId ? { config_id: configId } : {};
    api.get('/conformal-prediction/cdt/readiness', { params })
      .then(r => setData(r.data))
      .catch(() => setData(null));
  }, [configId]);

  if (!data) return null;

  const { summary, trm_types } = data;
  const isFullyCalibrated = data.ready;

  // Non-admin users: only see a brief note when NOT calibrated, nothing when healthy
  if (!isAdmin) {
    if (isFullyCalibrated) return null;
    return (
      <div className="mb-4 rounded-lg border border-amber-500/20 bg-amber-500/5 px-4 py-3">
        <div className="flex items-center gap-3">
          <Info className="h-4 w-4 text-amber-500 flex-shrink-0" />
          <p className="text-xs text-muted-foreground">
            Some agent decisions are using conservative risk bounds while calibration completes.
            Contact your tenant administrator for details.
          </p>
        </div>
      </div>
    );
  }

  // Admin users: full detail below
  const uncalibratedTypes = trm_types?.filter(t => t.status !== 'calibrated') || [];

  // Visual state: green when fully calibrated, amber when partial
  const borderColor = isFullyCalibrated ? 'border-green-500/20' : 'border-amber-500/20';
  const bgColor = isFullyCalibrated ? 'bg-green-500/5' : 'bg-amber-500/5';
  const IconComponent = isFullyCalibrated ? CheckCircle2 : ShieldAlert;
  const iconColor = isFullyCalibrated ? 'text-green-500' : 'text-amber-500';
  const titleColor = isFullyCalibrated
    ? 'text-green-700 dark:text-green-400'
    : 'text-amber-700 dark:text-amber-400';

  return (
    <div className={cn('mb-4 rounded-lg border overflow-hidden', borderColor, bgColor)}>
      <div
        className="flex items-start gap-3 px-4 py-3 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <IconComponent className={cn('h-4 w-4 flex-shrink-0 mt-0.5', iconColor)} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={cn('text-sm font-medium', titleColor)}>
              Uncertainty Calibration: {summary.calibrated}/{summary.total} agents ready
            </span>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
            {isFullyCalibrated
              ? 'All applicable TRM agents have conformal coverage guarantees. Decisions are risk-bounded.'
              : <>
                  {summary.uncalibrated > 0
                    ? `${summary.uncalibrated} TRM agent${summary.uncalibrated > 1 ? 's' : ''} lack calibration data. `
                    : ''}
                  {summary.partial > 0
                    ? `${summary.partial} accumulating data (auto-calibrates at 30 decision-outcome pairs). `
                    : ''}
                  Uncalibrated agents use conservative risk bounds, which may trigger more escalations.
                </>
            }
          </p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {expanded ? (
            <ChevronUp className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          )}
        </div>
      </div>

      {expanded && uncalibratedTypes.length > 0 && (
        <div className="px-4 pb-3 border-t border-amber-500/10">
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mt-2">
            {uncalibratedTypes.map(t => (
              <div
                key={t.trm_type}
                className={cn(
                  'flex items-center gap-2 px-2.5 py-1.5 rounded text-xs',
                  t.status === 'partial'
                    ? 'bg-amber-500/10 text-amber-700 dark:text-amber-400'
                    : 'bg-muted/50 text-muted-foreground',
                )}
              >
                <div className={cn(
                  'h-1.5 w-1.5 rounded-full flex-shrink-0',
                  t.status === 'partial' ? 'bg-amber-500' : 'bg-muted-foreground/30',
                )} />
                <span className="truncate">{t.label}</span>
                <span className="ml-auto tabular-nums text-[10px]">
                  {t.calibration_pairs}/{t.min_required}
                </span>
              </div>
            ))}
          </div>
          <p className="text-[10px] text-muted-foreground mt-2">
            Calibration data accumulates automatically as TRM decisions receive outcomes
            (hourly at :32). Each agent needs 30 decision-outcome pairs for full coverage guarantees.
          </p>
        </div>
      )}
    </div>
  );
};

export default CDTReadinessBanner;
