import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  BookOpen, RefreshCw, Clock, Loader2, AlertTriangle,
  Calendar, Settings2, History, FileText, Sparkles, ChevronRight,
} from 'lucide-react';
import executiveBriefingApi from '../services/executiveBriefingApi';
import BriefingRenderer from '../components/briefing/BriefingRenderer';
import FollowupChat from '../components/briefing/FollowupChat';

const STATUS_STYLES = {
  completed: 'bg-green-100 text-green-800',
  pending: 'bg-amber-100 text-amber-800',
  generating: 'bg-blue-100 text-blue-800',
  failed: 'bg-red-100 text-red-800',
};

const TYPE_STYLES = {
  daily: 'bg-blue-100 text-blue-800',
  weekly: 'bg-purple-100 text-purple-800',
  monthly: 'bg-cyan-100 text-cyan-800',
  adhoc: 'bg-gray-100 text-gray-800',
};

const DOW_OPTIONS = [
  { value: 'mon', label: 'Monday' },
  { value: 'tue', label: 'Tuesday' },
  { value: 'wed', label: 'Wednesday' },
  { value: 'thu', label: 'Thursday' },
  { value: 'fri', label: 'Friday' },
  { value: 'sat', label: 'Saturday' },
  { value: 'sun', label: 'Sunday' },
];

export default function ExecutiveBriefingPage() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('latest');

  // Latest briefing state
  const [briefing, setBriefing] = useState(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [pollId, setPollId] = useState(null);

  // History state
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  // Schedule state
  const [schedule, setSchedule] = useState(null);
  const [scheduleLoading, setScheduleLoading] = useState(false);
  const [scheduleSaving, setScheduleSaving] = useState(false);

  // Load latest briefing on mount
  useEffect(() => {
    loadLatest();
  }, []);

  const loadLatest = async () => {
    try {
      setLoading(true);
      const { data: resp } = await executiveBriefingApi.getLatest();
      if (resp.success) {
        setBriefing(resp.data);
      }
    } catch (error) {
      console.error('Failed to load latest briefing:', error);
    } finally {
      setLoading(false);
    }
  };

  // Poll for completion
  const pollForCompletion = useCallback((briefingId) => {
    const interval = setInterval(async () => {
      try {
        const { data: resp } = await executiveBriefingApi.getBriefing(briefingId);
        if (resp.success && resp.data) {
          const status = resp.data.status;
          if (status === 'completed' || status === 'failed') {
            clearInterval(interval);
            setBriefing(resp.data);
            setGenerating(false);
            setPollId(null);
          }
        }
      } catch (error) {
        console.error('Poll error:', error);
      }
    }, 2000);
    setPollId(interval);
    // Timeout after 120 seconds
    setTimeout(() => {
      clearInterval(interval);
      setGenerating(false);
      setPollId(null);
    }, 120000);
  }, []);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollId) clearInterval(pollId);
    };
  }, [pollId]);

  const handleGenerate = async () => {
    try {
      setGenerating(true);
      const { data: resp } = await executiveBriefingApi.generate('adhoc');
      if (resp.success && resp.briefing_id) {
        pollForCompletion(resp.briefing_id);
      }
    } catch (error) {
      console.error('Failed to start generation:', error);
      setGenerating(false);
    }
  };

  // Load history
  const loadHistory = async () => {
    try {
      setHistoryLoading(true);
      const { data: resp } = await executiveBriefingApi.listHistory(50);
      if (resp.success) {
        setHistory(resp.data || []);
      }
    } catch (error) {
      console.error('Failed to load history:', error);
    } finally {
      setHistoryLoading(false);
    }
  };

  const loadBriefingById = async (id) => {
    try {
      setLoading(true);
      const { data: resp } = await executiveBriefingApi.getBriefing(id);
      if (resp.success && resp.data) {
        setBriefing(resp.data);
        setActiveTab('latest');
      }
    } catch (error) {
      console.error('Failed to load briefing:', error);
    } finally {
      setLoading(false);
    }
  };

  // Load schedule
  const loadSchedule = async () => {
    try {
      setScheduleLoading(true);
      const { data: resp } = await executiveBriefingApi.getSchedule();
      if (resp.success) {
        setSchedule(resp.data);
      }
    } catch (error) {
      console.error('Failed to load schedule:', error);
    } finally {
      setScheduleLoading(false);
    }
  };

  const saveSchedule = async () => {
    if (!schedule) return;
    try {
      setScheduleSaving(true);
      const { data: resp } = await executiveBriefingApi.updateSchedule(schedule);
      if (resp.success) {
        setSchedule(resp.data);
      }
    } catch (error) {
      console.error('Failed to save schedule:', error);
    } finally {
      setScheduleSaving(false);
    }
  };

  // Load tab data on switch
  useEffect(() => {
    if (activeTab === 'history' && history.length === 0) loadHistory();
    if (activeTab === 'settings' && !schedule) loadSchedule();
  }, [activeTab]);

  // Parse narrative and recommendations from briefing
  let narrativeData = null;
  let recommendations = [];
  let dataQualityNotes = '';
  if (briefing) {
    try {
      const parsed = typeof briefing.narrative === 'string'
        ? JSON.parse(briefing.narrative)
        : briefing.narrative;
      narrativeData = parsed;
    } catch {
      narrativeData = briefing.narrative;
    }
    recommendations = briefing.recommendations || [];

    // Extract data_quality_notes from the LLM response if stored in recommendations or data_pack
    if (briefing.data_pack && typeof briefing.data_pack === 'object') {
      dataQualityNotes = briefing.data_pack.data_quality_notes || '';
    }
  }

  return (
    <div className="container mx-auto py-8 px-4 max-w-7xl">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <BookOpen className="h-10 w-10 text-primary" />
          <div>
            <h1 className="text-3xl font-bold">Strategy Briefing</h1>
            <p className="text-muted-foreground">AI-generated executive briefings with follow-up</p>
          </div>
        </div>
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg
                     hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {generating ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Generating...
            </>
          ) : (
            <>
              <Sparkles className="h-4 w-4" />
              Generate Now
            </>
          )}
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b mb-6">
        {[
          { id: 'latest', label: 'Latest Briefing', icon: FileText },
          { id: 'history', label: 'History', icon: History },
          { id: 'settings', label: 'Settings', icon: Settings2 },
        ].map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors
              ${activeTab === id
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground hover:border-muted-foreground/30'
              }`}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </div>

      {/* Tab: Latest Briefing */}
      {activeTab === 'latest' && (
        <div className="space-y-6">
          {loading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : generating ? (
            <div className="flex flex-col items-center justify-center py-20 gap-4">
              <Loader2 className="h-10 w-10 animate-spin text-primary" />
              <p className="text-muted-foreground">Generating executive briefing...</p>
              <p className="text-xs text-muted-foreground">Collecting metrics and synthesizing with AI. This usually takes 15-30 seconds.</p>
            </div>
          ) : !briefing ? (
            <div className="text-center py-20">
              <BookOpen className="h-16 w-16 mx-auto text-muted-foreground/30 mb-4" />
              <h2 className="text-xl font-semibold text-muted-foreground mb-2">No briefings yet</h2>
              <p className="text-muted-foreground mb-4">Generate your first executive briefing to get started.</p>
              <button
                onClick={handleGenerate}
                className="px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90"
              >
                Generate First Briefing
              </button>
            </div>
          ) : (
            <>
              {/* Briefing header */}
              <div className="flex items-center gap-3 flex-wrap">
                <h2 className="text-xl font-semibold">{briefing.title || 'Executive Briefing'}</h2>
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${TYPE_STYLES[briefing.briefing_type] || TYPE_STYLES.adhoc}`}>
                  {briefing.briefing_type}
                </span>
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_STYLES[briefing.status] || ''}`}>
                  {briefing.status}
                </span>
                {briefing.created_at && (
                  <span className="text-xs text-muted-foreground flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {new Date(briefing.created_at).toLocaleString()}
                  </span>
                )}
              </div>

              {/* Status: failed */}
              {briefing.status === 'failed' && (
                <div className="flex items-start gap-2 p-4 rounded-lg bg-red-50 border border-red-200">
                  <AlertTriangle className="h-5 w-5 text-red-600 mt-0.5" />
                  <div>
                    <p className="font-medium text-red-800">Briefing generation failed</p>
                    <p className="text-sm text-red-700 mt-1">{briefing.error_message || 'Unknown error'}</p>
                  </div>
                </div>
              )}

              {/* Executive summary */}
              {briefing.executive_summary && (
                <div className="p-4 rounded-lg bg-primary/5 border border-primary/20">
                  <p className="text-sm font-medium text-primary mb-1">Executive Summary</p>
                  <p className="text-base leading-relaxed">{briefing.executive_summary}</p>
                </div>
              )}

              {/* Narrative + Recommendations */}
              {briefing.status === 'completed' && (
                <BriefingRenderer
                  narrative={narrativeData}
                  recommendations={recommendations}
                  dataQualityNotes={dataQualityNotes}
                />
              )}

              {/* Generation metadata */}
              {briefing.model_used && (
                <div className="flex items-center gap-4 text-xs text-muted-foreground pt-2 border-t">
                  <span>Model: {briefing.model_used}</span>
                  {briefing.tokens_used && <span>Tokens: {briefing.tokens_used.toLocaleString()}</span>}
                  {briefing.generation_time_ms && <span>Generated in {(briefing.generation_time_ms / 1000).toFixed(1)}s</span>}
                </div>
              )}

              {/* Follow-up chat */}
              {briefing.status === 'completed' && (
                <FollowupChat
                  briefingId={briefing.id}
                  existingFollowups={briefing.followups || []}
                />
              )}
            </>
          )}
        </div>
      )}

      {/* Tab: History */}
      {activeTab === 'history' && (
        <div>
          {historyLoading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : history.length === 0 ? (
            <div className="text-center py-20 text-muted-foreground">
              <History className="h-12 w-12 mx-auto mb-3 opacity-30" />
              <p>No briefing history yet.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {history.map((item) => (
                <button
                  key={item.id}
                  onClick={() => loadBriefingById(item.id)}
                  className="w-full flex items-center gap-4 p-4 rounded-lg border hover:bg-muted/50
                             transition-colors text-left group"
                >
                  <FileText className="h-5 w-5 text-muted-foreground flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-medium text-sm truncate">
                        {item.title || 'Executive Briefing'}
                      </span>
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${TYPE_STYLES[item.briefing_type] || ''}`}>
                        {item.briefing_type}
                      </span>
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${STATUS_STYLES[item.status] || ''}`}>
                        {item.status}
                      </span>
                    </div>
                    {item.executive_summary && (
                      <p className="text-xs text-muted-foreground truncate">{item.executive_summary}</p>
                    )}
                  </div>
                  <div className="text-right flex-shrink-0">
                    <div className="text-xs text-muted-foreground">
                      {item.created_at ? new Date(item.created_at).toLocaleDateString() : ''}
                    </div>
                    {item.followup_count > 0 && (
                      <div className="text-[10px] text-muted-foreground">{item.followup_count} follow-ups</div>
                    )}
                  </div>
                  <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100" />
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tab: Settings */}
      {activeTab === 'settings' && (
        <div className="max-w-lg space-y-6">
          {scheduleLoading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : schedule ? (
            <>
              <div className="border rounded-lg p-6 space-y-4">
                <h3 className="font-semibold flex items-center gap-2">
                  <Calendar className="h-5 w-5 text-primary" />
                  Scheduled Generation
                </h3>

                {/* Enabled toggle */}
                <label className="flex items-center justify-between">
                  <span className="text-sm">Enable scheduled briefings</span>
                  <button
                    onClick={() => setSchedule({ ...schedule, enabled: !schedule.enabled })}
                    className={`relative w-11 h-6 rounded-full transition-colors ${schedule.enabled ? 'bg-primary' : 'bg-muted'}`}
                  >
                    <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform ${schedule.enabled ? 'translate-x-5' : ''}`} />
                  </button>
                </label>

                {schedule.enabled && (
                  <>
                    {/* Briefing type */}
                    <div>
                      <label className="text-sm text-muted-foreground mb-1 block">Frequency</label>
                      <select
                        value={schedule.briefing_type}
                        onChange={(e) => setSchedule({ ...schedule, briefing_type: e.target.value })}
                        className="w-full border rounded-md px-3 py-2 text-sm bg-background"
                      >
                        <option value="daily">Daily</option>
                        <option value="weekly">Weekly</option>
                        <option value="monthly">Monthly (1st of month)</option>
                      </select>
                    </div>

                    {/* Day of week (weekly only) */}
                    {schedule.briefing_type === 'weekly' && (
                      <div>
                        <label className="text-sm text-muted-foreground mb-1 block">Day of Week</label>
                        <select
                          value={schedule.cron_day_of_week}
                          onChange={(e) => setSchedule({ ...schedule, cron_day_of_week: e.target.value })}
                          className="w-full border rounded-md px-3 py-2 text-sm bg-background"
                        >
                          {DOW_OPTIONS.map((d) => (
                            <option key={d.value} value={d.value}>{d.label}</option>
                          ))}
                        </select>
                      </div>
                    )}

                    {/* Time */}
                    <div className="flex gap-4">
                      <div className="flex-1">
                        <label className="text-sm text-muted-foreground mb-1 block">Hour (UTC)</label>
                        <select
                          value={schedule.cron_hour}
                          onChange={(e) => setSchedule({ ...schedule, cron_hour: parseInt(e.target.value) })}
                          className="w-full border rounded-md px-3 py-2 text-sm bg-background"
                        >
                          {Array.from({ length: 24 }, (_, i) => (
                            <option key={i} value={i}>{String(i).padStart(2, '0')}:00</option>
                          ))}
                        </select>
                      </div>
                      <div className="flex-1">
                        <label className="text-sm text-muted-foreground mb-1 block">Minute</label>
                        <select
                          value={schedule.cron_minute}
                          onChange={(e) => setSchedule({ ...schedule, cron_minute: parseInt(e.target.value) })}
                          className="w-full border rounded-md px-3 py-2 text-sm bg-background"
                        >
                          <option value={0}>:00</option>
                          <option value={15}>:15</option>
                          <option value={30}>:30</option>
                          <option value={45}>:45</option>
                        </select>
                      </div>
                    </div>
                  </>
                )}

                <button
                  onClick={saveSchedule}
                  disabled={scheduleSaving}
                  className="w-full px-4 py-2 bg-primary text-primary-foreground rounded-md
                             hover:bg-primary/90 disabled:opacity-50 text-sm font-medium"
                >
                  {scheduleSaving ? 'Saving...' : 'Save Schedule'}
                </button>
              </div>

              {/* Knowledge Base link */}
              <div className="border rounded-lg p-6">
                <h3 className="font-semibold mb-2">Strategic Context</h3>
                <p className="text-sm text-muted-foreground mb-3">
                  Upload strategy documents, competitive intelligence, and decision frameworks
                  to the Knowledge Base. These will be used as context for richer briefings.
                </p>
                <button
                  onClick={() => navigate('/admin/knowledge-base')}
                  className="text-sm text-primary hover:underline flex items-center gap-1"
                >
                  Go to Knowledge Base
                  <ChevronRight className="h-3 w-3" />
                </button>
              </div>

              {/* Generation metadata */}
              {briefing && briefing.model_used && (
                <div className="border rounded-lg p-6">
                  <h3 className="font-semibold mb-2">Last Generation Details</h3>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <span className="text-muted-foreground">Model</span>
                    <span>{briefing.model_used}</span>
                    <span className="text-muted-foreground">Tokens</span>
                    <span>{briefing.tokens_used?.toLocaleString() || 'N/A'}</span>
                    <span className="text-muted-foreground">Generation Time</span>
                    <span>{briefing.generation_time_ms ? `${(briefing.generation_time_ms / 1000).toFixed(1)}s` : 'N/A'}</span>
                    <span className="text-muted-foreground">Est. Cost</span>
                    <span>{briefing.tokens_used ? `~$${((briefing.tokens_used / 1000000) * 9).toFixed(4)}` : 'N/A'}</span>
                  </div>
                </div>
              )}
            </>
          ) : (
            <p className="text-muted-foreground">Unable to load schedule configuration.</p>
          )}
        </div>
      )}
    </div>
  );
}
