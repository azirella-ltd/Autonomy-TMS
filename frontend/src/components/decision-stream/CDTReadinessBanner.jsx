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

const CDTReadinessBanner = () => {
  const [data, setData] = useState(null);
  const [expanded, setExpanded] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    api.get('/conformal-prediction/cdt/readiness')
      .then(r => setData(r.data))
      .catch(() => setData(null));
  }, []);

  // Don't render if fully calibrated, dismissed, or no data
  if (!data || data.ready || dismissed) return null;

  const { summary, message, trm_types } = data;
  const uncalibratedTypes = trm_types?.filter(t => t.status !== 'calibrated') || [];

  return (
    <div className="mb-4 rounded-lg border border-amber-500/20 bg-amber-500/5 overflow-hidden">
      <div
        className="flex items-start gap-3 px-4 py-3 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <ShieldAlert className="h-4 w-4 text-amber-500 flex-shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-amber-700 dark:text-amber-400">
              Uncertainty Calibration: {summary.calibrated}/{summary.total} agents ready
            </span>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
            {summary.uncalibrated > 0
              ? `${summary.uncalibrated} TRM agent${summary.uncalibrated > 1 ? 's' : ''} lack calibration data. `
              : ''}
            {summary.partial > 0
              ? `${summary.partial} accumulating data (auto-calibrates at 30 decision-outcome pairs). `
              : ''}
            Uncalibrated agents use conservative risk bounds, which may trigger more escalations.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            className="text-xs text-muted-foreground hover:text-foreground px-1"
            onClick={(e) => { e.stopPropagation(); setDismissed(true); }}
          >
            Dismiss
          </button>
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
