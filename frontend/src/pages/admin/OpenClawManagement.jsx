/**
 * OpenClaw Gateway Management
 *
 * Admin page for managing OpenClaw chat gateway configuration, skills,
 * channels, LLM settings, and session monitoring.
 */

import React, { useState, useEffect } from 'react';
import { openClawApi } from '../../services/edgeAgentApi';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
  Button,
  Spinner,
  Alert,
  AlertDescription,
  Tabs,
  TabsList,
  Tab,
  Input,
  NativeSelect,
  Badge,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '../../components/common';
import {
  MessageSquare,
  Settings,
  ChevronRight,
  CheckCircle,
  AlertTriangle,
  Clock,
  RefreshCw,
  Puzzle,
  Radio,
  Brain,
  Activity,
  Play,
  Pause,
  Eye,
  EyeOff,
  Copy,
  ToggleLeft,
  ToggleRight,
  Send,
  Zap,
  Shield,
  Server,
  Wifi,
  Hash,
} from 'lucide-react';
import { cn } from '../../lib/utils/cn';

const tabItems = [
  { value: 'overview', label: 'Overview', icon: <Activity className="h-4 w-4" /> },
  { value: 'skills', label: 'Skills', icon: <Puzzle className="h-4 w-4" /> },
  { value: 'channels', label: 'Channels', icon: <Radio className="h-4 w-4" /> },
  { value: 'llm', label: 'LLM Config', icon: <Brain className="h-4 w-4" /> },
  { value: 'sessions', label: 'Sessions', icon: <MessageSquare className="h-4 w-4" /> },
];

// ============================================================================
// Overview Tab
// ============================================================================
const OverviewTab = ({ status, loading, onRefresh }) => {
  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Spinner size="lg" />
      </div>
    );
  }

  const isRunning = status?.gateway_running;
  const version = status?.version || 'Unknown';
  const meetsMinVersion = status?.meets_min_version !== false;

  return (
    <div className="space-y-6">
      {/* Gateway Status */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className={cn(
              "p-4 rounded-lg border-2",
              isRunning ? "border-green-500 bg-green-50" : "border-red-500 bg-red-50"
            )}>
              <div className="flex items-center gap-2 mb-2">
                {isRunning ? (
                  <CheckCircle className="h-5 w-5 text-green-500" />
                ) : (
                  <AlertTriangle className="h-5 w-5 text-red-500" />
                )}
                <span className="font-medium">Gateway</span>
              </div>
              <p className="text-sm text-muted-foreground">
                {isRunning ? 'Running' : 'Not Connected'}
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className={cn(
              "p-4 rounded-lg border-2",
              meetsMinVersion ? "border-green-500 bg-green-50" : "border-yellow-500 bg-yellow-50"
            )}>
              <div className="flex items-center gap-2 mb-2">
                {meetsMinVersion ? (
                  <CheckCircle className="h-5 w-5 text-green-500" />
                ) : (
                  <AlertTriangle className="h-5 w-5 text-yellow-500" />
                )}
                <span className="font-medium">Version</span>
              </div>
              <p className="text-sm text-muted-foreground">
                {version}
                {!meetsMinVersion && ' (min: v2026.2.15)'}
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="p-4 rounded-lg border-2 border-blue-500 bg-blue-50">
              <div className="flex items-center gap-2 mb-2">
                <Radio className="h-5 w-5 text-blue-500" />
                <span className="font-medium">Channels</span>
              </div>
              <p className="text-sm text-muted-foreground">
                {status?.channels_connected || 0} connected
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="p-4 rounded-lg border-2 border-purple-500 bg-purple-50">
              <div className="flex items-center gap-2 mb-2">
                <Puzzle className="h-5 w-5 text-purple-500" />
                <span className="font-medium">Skills</span>
              </div>
              <p className="text-sm text-muted-foreground">
                {status?.skills_active || 0} active
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Security Notice */}
      {!meetsMinVersion && (
        <Alert variant="warning">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>
            OpenClaw version {version} does not meet the minimum required version (v2026.2.15).
            Several critical CVEs (CVE-2026-25253, CVE-2026-26325) affect older versions.
            Please upgrade immediately.
          </AlertDescription>
        </Alert>
      )}

      {/* Quick Stats */}
      <Card>
        <CardHeader>
          <CardTitle>Gateway Statistics</CardTitle>
          <CardDescription>Performance metrics for the current session</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            <div className="text-center">
              <p className="text-sm text-muted-foreground">Queries Today</p>
              <p className="text-2xl font-bold">{status?.queries_today || 0}</p>
            </div>
            <div className="text-center">
              <p className="text-sm text-muted-foreground">Avg Response Time</p>
              <p className="text-2xl font-bold">{status?.avg_response_ms || 0}ms</p>
            </div>
            <div className="text-center">
              <p className="text-sm text-muted-foreground">Active Sessions</p>
              <p className="text-2xl font-bold">{status?.active_sessions || 0}</p>
            </div>
            <div className="text-center">
              <p className="text-sm text-muted-foreground">Signals Captured</p>
              <p className="text-2xl font-bold">{status?.signals_captured_today || 0}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Gateway Configuration */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Gateway Configuration</CardTitle>
            <Button variant="outline" size="sm" onClick={onRefresh}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Refresh
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            <div className="flex justify-between py-2 border-b">
              <span className="text-sm font-medium">Gateway Binding</span>
              <span className="text-sm font-mono">{status?.gateway_binding || '127.0.0.1:3100'}</span>
            </div>
            <div className="flex justify-between py-2 border-b">
              <span className="text-sm font-medium">Auth Token</span>
              <span className="text-sm font-mono">
                {status?.auth_configured ? '****configured****' : 'Not Set'}
              </span>
            </div>
            <div className="flex justify-between py-2 border-b">
              <span className="text-sm font-medium">Workspace</span>
              <span className="text-sm font-mono">{status?.workspace_path || '/opt/openclaw/workspace'}</span>
            </div>
            <div className="flex justify-between py-2 border-b">
              <span className="text-sm font-medium">SOUL.md</span>
              <Badge variant={status?.soul_configured ? 'success' : 'secondary'}>
                {status?.soul_configured ? 'Configured' : 'Default'}
              </Badge>
            </div>
            <div className="flex justify-between py-2">
              <span className="text-sm font-medium">ClawHub Skills</span>
              <Badge variant="destructive">
                <Shield className="h-3 w-3 mr-1" />
                Disabled (Security)
              </Badge>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

// ============================================================================
// Skills Tab
// ============================================================================
const SkillsTab = () => {
  const [skills, setSkills] = useState([]);
  const [loading, setLoading] = useState(true);
  const [testingSkill, setTestingSkill] = useState(null);
  const [testInput, setTestInput] = useState('');
  const [testResult, setTestResult] = useState(null);

  useEffect(() => {
    loadSkills();
  }, []);

  const loadSkills = async () => {
    setLoading(true);
    try {
      const res = await openClawApi.getSkills();
      setSkills(res.data || []);
    } catch {
      // Default skill definitions for initial rendering
      setSkills([
        { id: 'supply-plan-query', name: 'Supply Plan Query', enabled: true, category: 'planning', description: 'Query supply plan data (product, demand, inventory, OTIF)' },
        { id: 'atp-check', name: 'ATP Check', enabled: true, category: 'execution', description: 'Check Available-to-Promise for orders' },
        { id: 'override-decision', name: 'Override Decision', enabled: true, category: 'governance', description: 'Capture planner overrides with reasoning' },
        { id: 'ask-why', name: 'Ask Why', enabled: true, category: 'explainability', description: 'Explain agent decisions with evidence citations' },
        { id: 'kpi-dashboard', name: 'KPI Dashboard', enabled: true, category: 'monitoring', description: 'Service level, inventory, exceptions summary' },
        { id: 'signal-capture', name: 'Signal Capture', enabled: true, category: 'signals', description: 'Extract demand/disruption signals from messages' },
        { id: 'voice-signal', name: 'Voice Signal', enabled: false, category: 'signals', description: 'Transcribe and classify voice notes via Whisper' },
        { id: 'email-signal', name: 'Email Signal', enabled: false, category: 'signals', description: 'Parse emails for supply chain signals' },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleToggle = async (skillId, currentEnabled) => {
    try {
      await openClawApi.toggleSkill(skillId, !currentEnabled);
      setSkills(prev => prev.map(s => s.id === skillId ? { ...s, enabled: !s.enabled } : s));
    } catch (err) {
      console.error('Failed to toggle skill:', err);
    }
  };

  const handleTest = async (skillId) => {
    setTestingSkill(skillId);
    setTestResult(null);
    try {
      const res = await openClawApi.testSkill(skillId, testInput);
      setTestResult(res.data);
    } catch (err) {
      setTestResult({ error: err.message || 'Test failed' });
    }
  };

  const categoryColors = {
    planning: 'bg-blue-100 text-blue-800',
    execution: 'bg-green-100 text-green-800',
    governance: 'bg-purple-100 text-purple-800',
    explainability: 'bg-orange-100 text-orange-800',
    monitoring: 'bg-cyan-100 text-cyan-800',
    signals: 'bg-yellow-100 text-yellow-800',
  };

  return (
    <div className="space-y-4">
      <Alert variant="warning">
        <Shield className="h-4 w-4" />
        <AlertDescription>
          Only locally-developed skills are allowed. Installing skills from the public ClawHub marketplace
          is disabled due to the ClawHavoc supply chain attack (1,184 malicious skills discovered in Jan 2026).
        </AlertDescription>
      </Alert>

      {loading ? (
        <div className="flex justify-center py-12"><Spinner size="lg" /></div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {skills.map((skill) => (
            <Card key={skill.id} className={cn(!skill.enabled && "opacity-60")}>
              <CardContent className="pt-6">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Puzzle className="h-5 w-5 text-primary" />
                    <h3 className="font-semibold">{skill.name}</h3>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleToggle(skill.id, skill.enabled)}
                    className={skill.enabled ? 'text-green-600' : 'text-gray-400'}
                  >
                    {skill.enabled ? (
                      <ToggleRight className="h-6 w-6" />
                    ) : (
                      <ToggleLeft className="h-6 w-6" />
                    )}
                  </Button>
                </div>

                <p className="text-sm text-muted-foreground mb-3">{skill.description}</p>

                <div className="flex items-center justify-between">
                  <span className={cn("text-xs px-2 py-1 rounded-full", categoryColors[skill.category] || 'bg-gray-100')}>
                    {skill.category}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => { setTestingSkill(skill.id); setTestResult(null); setTestInput(''); }}
                    disabled={!skill.enabled}
                  >
                    <Play className="h-3 w-3 mr-1" />
                    Test
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Test Dialog */}
      <Dialog open={!!testingSkill} onOpenChange={() => setTestingSkill(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Test Skill: {testingSkill}</DialogTitle>
            <DialogDescription>Send a test message to verify skill functionality</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium block mb-1">Test Input</label>
              <Input
                value={testInput}
                onChange={(e) => setTestInput(e.target.value)}
                placeholder="e.g., What is the ATP for SKU-1234 at DC-East?"
              />
            </div>
            <Button onClick={() => handleTest(testingSkill)} className="w-full">
              <Send className="h-4 w-4 mr-2" />
              Run Test
            </Button>
            {testResult && (
              <div className={cn(
                "p-3 rounded-lg",
                testResult.error ? "bg-red-50 border border-red-200" : "bg-green-50 border border-green-200"
              )}>
                <pre className="text-xs whitespace-pre-wrap">
                  {JSON.stringify(testResult, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

// ============================================================================
// Channels Tab
// ============================================================================
const ChannelsTab = () => {
  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadChannels();
  }, []);

  const loadChannels = async () => {
    setLoading(true);
    try {
      const res = await openClawApi.getChannels();
      setChannels(res.data || []);
    } catch {
      // Default channel definitions
      setChannels([
        { id: 'slack', name: 'Slack', type: 'slack', status: 'disconnected', configured: false, icon: 'Hash' },
        { id: 'teams', name: 'Microsoft Teams', type: 'teams', status: 'disconnected', configured: false, icon: 'MessageSquare' },
        { id: 'whatsapp', name: 'WhatsApp', type: 'whatsapp', status: 'disconnected', configured: false, icon: 'MessageSquare', warning: 'Uses Baileys (unofficial). Review ToS compliance.' },
        { id: 'telegram', name: 'Telegram', type: 'telegram', status: 'disconnected', configured: false, icon: 'Send' },
        { id: 'email', name: 'Email (IMAP)', type: 'email', status: 'disconnected', configured: false, icon: 'MessageSquare' },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleTest = async (channelId) => {
    try {
      const res = await openClawApi.testChannel(channelId);
      setChannels(prev => prev.map(c =>
        c.id === channelId ? { ...c, status: res.data?.success ? 'connected' : 'error' } : c
      ));
    } catch {
      setChannels(prev => prev.map(c =>
        c.id === channelId ? { ...c, status: 'error' } : c
      ));
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Configure messaging channels for planner chat and signal capture.
        Each channel connects through OpenClaw's gateway and normalizes messages into MsgContext format.
      </p>

      {loading ? (
        <div className="flex justify-center py-12"><Spinner size="lg" /></div>
      ) : (
        <div className="space-y-4">
          {channels.map((channel) => (
            <Card key={channel.id}>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={cn(
                      "w-10 h-10 rounded-lg flex items-center justify-center",
                      channel.status === 'connected' ? 'bg-green-100' :
                      channel.status === 'error' ? 'bg-red-100' : 'bg-gray-100'
                    )}>
                      <MessageSquare className={cn(
                        "h-5 w-5",
                        channel.status === 'connected' ? 'text-green-600' :
                        channel.status === 'error' ? 'text-red-600' : 'text-gray-400'
                      )} />
                    </div>
                    <div>
                      <h3 className="font-semibold">{channel.name}</h3>
                      <div className="flex items-center gap-2">
                        <Badge variant={
                          channel.status === 'connected' ? 'success' :
                          channel.status === 'error' ? 'destructive' : 'secondary'
                        }>
                          {channel.status === 'connected' ? 'Connected' :
                           channel.status === 'error' ? 'Error' : 'Not Configured'}
                        </Badge>
                        {channel.warning && (
                          <Badge variant="warning" className="text-xs">
                            <AlertTriangle className="h-3 w-3 mr-1" />
                            Review Required
                          </Badge>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={() => handleTest(channel.id)}>
                      <Wifi className="h-4 w-4 mr-1" />
                      Test
                    </Button>
                    <Button variant="outline" size="sm">
                      <Settings className="h-4 w-4 mr-1" />
                      Configure
                    </Button>
                  </div>
                </div>

                {channel.warning && (
                  <div className="mt-3 p-2 bg-yellow-50 rounded text-xs text-yellow-800 flex items-center gap-2">
                    <AlertTriangle className="h-3 w-3 flex-shrink-0" />
                    {channel.warning}
                  </div>
                )}

                {/* Configuration Fields (collapsed by default) */}
                {channel.configured && (
                  <div className="mt-4 pt-4 border-t space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Signal Source Mapping</span>
                      <Badge variant="outline">{channel.signal_source || 'Not mapped'}</Badge>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Reliability Weight</span>
                      <span>{channel.reliability_weight || '—'}</span>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};

// ============================================================================
// LLM Config Tab
// ============================================================================
const LLMConfigTab = () => {
  const [llmStatus, setLlmStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [config, setConfig] = useState({
    provider: 'vllm',
    model: 'qwen3-8b',
    api_base: 'http://localhost:8001/v1',
    api_key: '',
    max_tokens: 4096,
    temperature: 0.1,
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadLLMStatus();
  }, []);

  const loadLLMStatus = async () => {
    setLoading(true);
    try {
      const res = await openClawApi.getLLMStatus();
      setLlmStatus(res.data);
      if (res.data?.config) {
        setConfig(prev => ({ ...prev, ...res.data.config }));
      }
    } catch {
      setLlmStatus(null);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await openClawApi.updateLLMConfig(config);
    } catch (err) {
      console.error('Failed to save LLM config:', err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* LLM Service Status */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Brain className="h-5 w-5" />
            LLM Service Status
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex justify-center py-4"><Spinner /></div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="text-center">
                <p className="text-sm text-muted-foreground">Status</p>
                <Badge variant={llmStatus?.running ? 'success' : 'destructive'} className="mt-1">
                  {llmStatus?.running ? 'Running' : 'Offline'}
                </Badge>
              </div>
              <div className="text-center">
                <p className="text-sm text-muted-foreground">Model</p>
                <p className="font-semibold">{llmStatus?.model || config.model}</p>
              </div>
              <div className="text-center">
                <p className="text-sm text-muted-foreground">VRAM Usage</p>
                <p className="font-semibold">{llmStatus?.vram_used_gb?.toFixed(1) || '—'} GB</p>
              </div>
              <div className="text-center">
                <p className="text-sm text-muted-foreground">Avg Latency</p>
                <p className="font-semibold">{llmStatus?.avg_latency_ms || '—'} ms</p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* LLM Configuration */}
      <Card>
        <CardHeader>
          <CardTitle>LLM Configuration</CardTitle>
          <CardDescription>
            Configure the LLM provider used by OpenClaw for chat and signal classification
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium block mb-1">Provider</label>
              <NativeSelect
                value={config.provider}
                onChange={(e) => setConfig(prev => ({ ...prev, provider: e.target.value }))}
              >
                <option value="vllm">vLLM (Self-Hosted, Recommended)</option>
                <option value="openai">OpenAI API</option>
                <option value="anthropic">Anthropic API</option>
              </NativeSelect>
            </div>

            <div>
              <label className="text-sm font-medium block mb-1">Model</label>
              <NativeSelect
                value={config.model}
                onChange={(e) => setConfig(prev => ({ ...prev, model: e.target.value }))}
              >
                {config.provider === 'vllm' ? (
                  <>
                    <option value="qwen3-8b">Qwen 3 8B (8GB VRAM, recommended)</option>
                    <option value="qwen3-14b">Qwen 3 14B (16GB VRAM)</option>
                    <option value="qwen3-32b">Qwen 3 32B (24GB VRAM)</option>
                  </>
                ) : config.provider === 'openai' ? (
                  <>
                    <option value="gpt-5-mini">GPT-5 Mini</option>
                    <option value="gpt-5">GPT-5</option>
                  </>
                ) : (
                  <>
                    <option value="claude-sonnet-4-6">Claude Sonnet 4.6</option>
                    <option value="claude-haiku-4-5">Claude Haiku 4.5</option>
                  </>
                )}
              </NativeSelect>
            </div>

            <div>
              <label className="text-sm font-medium block mb-1">API Base URL</label>
              <Input
                value={config.api_base}
                onChange={(e) => setConfig(prev => ({ ...prev, api_base: e.target.value }))}
                placeholder="http://localhost:8001/v1"
              />
            </div>

            <div>
              <label className="text-sm font-medium block mb-1">API Key</label>
              <Input
                type="password"
                value={config.api_key}
                onChange={(e) => setConfig(prev => ({ ...prev, api_key: e.target.value }))}
                placeholder="sk-... or leave empty for self-hosted"
              />
            </div>

            <div>
              <label className="text-sm font-medium block mb-1">Max Tokens</label>
              <Input
                type="number"
                value={config.max_tokens}
                onChange={(e) => setConfig(prev => ({ ...prev, max_tokens: Number(e.target.value) }))}
              />
            </div>

            <div>
              <label className="text-sm font-medium block mb-1">Temperature</label>
              <Input
                type="number"
                step="0.1"
                min="0"
                max="2"
                value={config.temperature}
                onChange={(e) => setConfig(prev => ({ ...prev, temperature: Number(e.target.value) }))}
              />
            </div>
          </div>

          <div className="flex justify-end pt-4">
            <Button onClick={handleSave} disabled={saving}>
              {saving ? <Spinner className="mr-2" /> : null}
              Save Configuration
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

// ============================================================================
// Sessions Tab
// ============================================================================
const SessionsTab = () => {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadSessions();
  }, []);

  const loadSessions = async () => {
    setLoading(true);
    try {
      const res = await openClawApi.getSessionLog({ limit: 50 });
      setSessions(res.data || []);
    } catch {
      setSessions([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <p className="text-sm text-muted-foreground">
          Recent OpenClaw sessions across all channels
        </p>
        <Button variant="outline" size="sm" onClick={loadSessions}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Refresh
        </Button>
      </div>

      <Card>
        <CardContent className="pt-6">
          {loading ? (
            <div className="flex justify-center py-8"><Spinner size="lg" /></div>
          ) : sessions.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <MessageSquare className="h-12 w-12 mx-auto mb-4 text-muted-foreground/50" />
              <p>No sessions recorded yet</p>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-3 px-4 font-medium">Channel</th>
                  <th className="text-left py-3 px-4 font-medium">User</th>
                  <th className="text-left py-3 px-4 font-medium">Skill Used</th>
                  <th className="text-left py-3 px-4 font-medium">Query</th>
                  <th className="text-left py-3 px-4 font-medium">Duration</th>
                  <th className="text-left py-3 px-4 font-medium">Signal?</th>
                  <th className="text-left py-3 px-4 font-medium">Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map((session, i) => (
                  <tr key={i} className="border-b hover:bg-muted/50">
                    <td className="py-3 px-4">
                      <Badge variant="outline">{session.channel || 'unknown'}</Badge>
                    </td>
                    <td className="py-3 px-4">{session.user || '—'}</td>
                    <td className="py-3 px-4">
                      <Badge variant="secondary">{session.skill || 'chat'}</Badge>
                    </td>
                    <td className="py-3 px-4 max-w-xs truncate" title={session.query}>
                      {session.query || '—'}
                    </td>
                    <td className="py-3 px-4">{session.duration_ms ? `${session.duration_ms}ms` : '—'}</td>
                    <td className="py-3 px-4">
                      {session.signal_captured && (
                        <Badge variant="warning">
                          <Zap className="h-3 w-3 mr-1" />
                          Signal
                        </Badge>
                      )}
                    </td>
                    <td className="py-3 px-4 text-xs">
                      {session.timestamp ? new Date(session.timestamp).toLocaleString() : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

// ============================================================================
// Main Component
// ============================================================================
const OpenClawManagement = () => {
  const [currentTab, setCurrentTab] = useState('overview');
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadStatus();
  }, []);

  const loadStatus = async () => {
    setLoading(true);
    try {
      const res = await openClawApi.getGatewayStatus();
      setStatus(res.data);
      setError(null);
    } catch (err) {
      setStatus({ gateway_running: false, version: 'Unknown', channels_connected: 0, skills_active: 0 });
      setError('Unable to connect to OpenClaw gateway. Verify the gateway is running.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Breadcrumbs */}
      <nav className="flex items-center gap-2 text-sm text-muted-foreground mb-4">
        <a href="/admin" className="hover:text-foreground">Administration</a>
        <ChevronRight className="h-4 w-4" />
        <span className="text-foreground">OpenClaw Gateway</span>
      </nav>

      {/* Title */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold flex items-center gap-3">
          <MessageSquare className="h-7 w-7 text-primary" />
          OpenClaw Gateway Management
        </h1>
        <p className="text-muted-foreground mt-1">
          Configure the OpenClaw chat gateway for planner interactions, skill management,
          channel connections, and signal capture across Slack, Teams, WhatsApp, Telegram, and Email.
        </p>
      </div>

      {error && (
        <Alert variant="warning" className="mb-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Tabs */}
      <Tabs value={currentTab} onValueChange={setCurrentTab}>
        <TabsList className="w-full justify-start border-b rounded-none h-auto p-0 mb-6">
          {tabItems.map((tab) => (
            <Tab
              key={tab.value}
              value={tab.value}
              className="flex items-center gap-2 rounded-none border-b-2 border-transparent data-[state=active]:border-primary px-4 py-3"
            >
              {tab.icon}
              {tab.label}
            </Tab>
          ))}
        </TabsList>

        {currentTab === 'overview' && (
          <OverviewTab status={status} loading={loading} onRefresh={loadStatus} />
        )}
        {currentTab === 'skills' && <SkillsTab />}
        {currentTab === 'channels' && <ChannelsTab />}
        {currentTab === 'llm' && <LLMConfigTab />}
        {currentTab === 'sessions' && <SessionsTab />}
      </Tabs>
    </div>
  );
};

export default OpenClawManagement;
