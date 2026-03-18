import React, { useState } from 'react';
import {
  ChevronDown, ChevronRight, AlertTriangle, TrendingUp, TrendingDown,
  Bot, Shield, Radio, BarChart3, Target, Star, GitCompare,
} from 'lucide-react';

const SECTION_META = {
  whats_changed: { label: "What's Changed", icon: GitCompare, color: 'text-indigo-600' },
  situation_overview: { label: 'Situation Overview', icon: BarChart3, color: 'text-blue-600' },
  scorecard_narrative: { label: 'Balanced Scorecard', icon: Target, color: 'text-green-600' },
  agent_performance_digest: { label: 'Agent Performance', icon: Bot, color: 'text-purple-600' },
  risk_report: { label: 'Risk Report', icon: AlertTriangle, color: 'text-red-600' },
  external_signals: { label: 'External Signals', icon: Radio, color: 'text-orange-600' },
  trend_analysis: { label: 'Trend Analysis', icon: TrendingUp, color: 'text-cyan-600' },
};

const SCORE_LABELS = {
  financial_impact: 'Financial Impact',
  urgency: 'Urgency',
  confidence: 'Confidence',
  strategic_alignment: 'Strategic Alignment',
  feasibility: 'Feasibility',
};

function ScoreBar({ label, value, max = 5 }) {
  const pct = (value / max) * 100;
  const color = value >= 4 ? 'bg-green-500' : value >= 3 ? 'bg-amber-500' : 'bg-red-500';
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-32 text-muted-foreground truncate">{label}</span>
      <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full`} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-6 text-right font-medium">{value}</span>
    </div>
  );
}

function CompositeScoreBadge({ score }) {
  const color =
    score >= 3.5 ? 'bg-green-100 text-green-800 border-green-200' :
    score >= 2.5 ? 'bg-amber-100 text-amber-800 border-amber-200' :
    'bg-red-100 text-red-800 border-red-200';
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-xs font-semibold ${color}`}>
      <Star className="h-3 w-3" />
      {score.toFixed(2)}
    </span>
  );
}

function NarrativeSection({ sectionKey, content }) {
  const [expanded, setExpanded] = useState(true);
  const meta = SECTION_META[sectionKey] || { label: sectionKey, icon: BarChart3, color: 'text-gray-600' };
  const Icon = meta.icon;

  if (!content) return null;

  return (
    <div className="border rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 p-4 hover:bg-muted/50 transition-colors text-left"
      >
        {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        <Icon className={`h-5 w-5 ${meta.color}`} />
        <span className="font-medium">{meta.label}</span>
      </button>
      {expanded && (
        <div className="px-4 pb-4 text-sm text-muted-foreground whitespace-pre-wrap leading-relaxed">
          {content}
        </div>
      )}
    </div>
  );
}

function RecommendationCard({ rec, index }) {
  const [expanded, setExpanded] = useState(index === 0);
  const scores = rec.scores || {};
  const categoryColors = {
    operations: 'bg-blue-100 text-blue-800',
    finance: 'bg-green-100 text-green-800',
    ai_agents: 'bg-purple-100 text-purple-800',
    risk: 'bg-red-100 text-red-800',
    strategy: 'bg-cyan-100 text-cyan-800',
  };

  return (
    <div className="border rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 p-4 hover:bg-muted/50 transition-colors text-left"
      >
        {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        <span className="flex-1 font-medium text-sm">
          {index + 1}. {rec.title}
        </span>
        <CompositeScoreBadge score={rec.composite_score || 0} />
        {rec.category && (
          <span className={`px-2 py-0.5 rounded text-xs ${categoryColors[rec.category] || 'bg-gray-100 text-gray-800'}`}>
            {rec.category}
          </span>
        )}
      </button>
      {expanded && (
        <div className="px-4 pb-4 space-y-3">
          <p className="text-sm text-muted-foreground">{rec.description}</p>
          <div className="space-y-1">
            {Object.entries(SCORE_LABELS).map(([key, label]) => (
              scores[key] != null && <ScoreBar key={key} label={label} value={scores[key]} />
            ))}
          </div>
          {rec.data_citations && rec.data_citations.length > 0 && (
            <div className="flex flex-wrap gap-1 pt-1">
              {rec.data_citations.map((citation, i) => (
                <span key={i} className="px-2 py-0.5 bg-muted rounded text-xs text-muted-foreground">
                  {citation}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function BriefingRenderer({ narrative, recommendations, dataQualityNotes }) {
  // Parse narrative if it's a JSON string
  let narrativeObj = narrative;
  if (typeof narrative === 'string') {
    try {
      narrativeObj = JSON.parse(narrative);
    } catch {
      narrativeObj = { situation_overview: narrative };
    }
  }

  const sectionOrder = [
    'whats_changed', 'situation_overview', 'scorecard_narrative', 'agent_performance_digest',
    'risk_report', 'external_signals', 'trend_analysis',
  ];

  return (
    <div className="space-y-6">
      {/* Narrative sections */}
      <div className="space-y-3">
        {sectionOrder.map((key) =>
          narrativeObj && narrativeObj[key] ? (
            <NarrativeSection key={key} sectionKey={key} content={narrativeObj[key]} />
          ) : null
        )}
      </div>

      {/* Recommendations */}
      {recommendations && recommendations.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <TrendingUp className="h-5 w-5 text-primary" />
            Recommendations
            <span className="text-sm text-muted-foreground font-normal">
              ({recommendations.length} items, ranked by composite score)
            </span>
          </h3>
          <div className="space-y-2">
            {recommendations
              .sort((a, b) => (b.composite_score || 0) - (a.composite_score || 0))
              .map((rec, idx) => (
                <RecommendationCard key={idx} rec={rec} index={idx} />
              ))}
          </div>
        </div>
      )}

      {/* Data quality notes */}
      {dataQualityNotes && (
        <div className="flex items-start gap-2 p-3 rounded-lg bg-amber-50 border border-amber-200 text-sm">
          <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
          <div>
            <span className="font-medium text-amber-800">Data Quality Notes: </span>
            <span className="text-amber-700">{dataQualityNotes}</span>
          </div>
        </div>
      )}
    </div>
  );
}
