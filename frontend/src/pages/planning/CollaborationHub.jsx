import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Button,
  Alert,
  Badge,
  Label,
  Input,
  Textarea,
  Modal,
  Spinner,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from '../../components/common';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../../components/ui/tooltip';
import {
  ChevronDown,
  Send,
  CheckCircle,
  XCircle,
  Edit,
  Info,
  RefreshCw,
  Activity,
  User,
  Bot,
  Bell,
  MessageCircle,
} from 'lucide-react';
import { api } from '../../services/api';
import { useActiveConfig } from '../../contexts/ActiveConfigContext';
import { useDisplayPreferences } from '../../contexts/DisplayPreferencesContext';
import TeamMessaging from '../../components/collaboration/TeamMessaging';

/**
 * CollaborationHub Component
 * Sprint 5: Collaboration with A2A/H2A/H2H
 *
 * Features:
 * - Agent-to-Agent (A2A) coordination threads
 * - Human-to-Agent (H2A) with explainability
 * - Human-to-Human (H2H) approval workflows
 */
const CollaborationHub = () => {
  const { effectiveConfigId } = useActiveConfig();
  const { formatProduct, loadLookupsForConfig } = useDisplayPreferences();

  useEffect(() => { if (effectiveConfigId) loadLookupsForConfig(effectiveConfigId); }, [effectiveConfigId, loadLookupsForConfig]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // A2A State
  const [a2aThreads, setA2aThreads] = useState([]);
  const [selectedThread, setSelectedThread] = useState(null);
  const [a2aDialogOpen, setA2aDialogOpen] = useState(false);
  const [newA2AMessage, setNewA2AMessage] = useState({
    from_agent: '',
    to_agent: '',
    content: '',
    message_type: 'coordination',
  });

  // H2A State
  const [agentSuggestions, setAgentSuggestions] = useState([]);
  const [selectedSuggestion, setSelectedSuggestion] = useState(null);
  const [explanation, setExplanation] = useState(null);
  const [explanationDialogOpen, setExplanationDialogOpen] = useState(false);
  const [decisionDialogOpen, setDecisionDialogOpen] = useState(false);
  const [decision, setDecision] = useState({
    decision: 'accept',
    rationale: '',
    modified_quantity: null,
    trade_off_preferences: {},
  });

  // H2H State
  const [myRequests, setMyRequests] = useState([]);
  const [pendingApprovals, setPendingApprovals] = useState([]);

  // Activity Feed State
  const [activities, setActivities] = useState([]);
  const [approvalDialogOpen, setApprovalDialogOpen] = useState(false);
  const [requestDialogOpen, setRequestDialogOpen] = useState(false);
  const [selectedRequest, setSelectedRequest] = useState(null);
  const [newRequest, setNewRequest] = useState({
    to_user: '',
    entity_type: 'supply_plan',
    entity_id: '',
    request_message: '',
    rationale: '',
    trade_offs: {},
    urgency: 'normal',
  });
  const [approvalResponse, setApprovalResponse] = useState({
    decision: 'approved',
    response_rationale: '',
    alternative_suggestion: null,
  });

  const [activeTab, setActiveTab] = useState('a2a');

  useEffect(() => {
    if (activeTab === 'a2a') loadA2AData();
    if (activeTab === 'h2a') loadH2AData();
    if (activeTab === 'h2h') loadH2HData();
    if (activeTab === 'activity') loadActivityFeed();
  }, [activeTab]);

  // ============================================================================
  // A2A Functions
  // ============================================================================

  const loadA2AData = async () => {
    try {
      const response = await api.get('/collaboration/a2a/threads');
      setA2aThreads(response.data || []);
    } catch (err) {
      console.error('Failed to load A2A threads:', err);
      setA2aThreads([]);
    }
  };

  const loadA2AThread = async (agent1, agent2) => {
    setLoading(true);
    try {
      const response = await api.get('/collaboration/a2a/thread', {
        params: { agent1, agent2 },
      });
      setSelectedThread(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load A2A thread');
    } finally {
      setLoading(false);
    }
  };

  const sendA2AMessage = async () => {
    setLoading(true);
    setError(null);
    try {
      await api.post('/collaboration/a2a/message', newA2AMessage);
      setSuccess('A2A message sent successfully');
      setA2aDialogOpen(false);
      setNewA2AMessage({
        from_agent: '',
        to_agent: '',
        content: '',
        message_type: 'coordination',
      });
      loadA2AData();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to send A2A message');
    } finally {
      setLoading(false);
    }
  };

  // ============================================================================
  // H2A Functions
  // ============================================================================

  const loadH2AData = async () => {
    try {
      const response = await api.get('/collaboration/h2a/suggestions');
      setAgentSuggestions(response.data || []);
    } catch (err) {
      console.error('Failed to load H2A suggestions:', err);
      setAgentSuggestions([]);
    }
  };

  const loadExplanation = async (suggestionId) => {
    setLoading(true);
    try {
      const response = await api.get(`/collaboration/h2a/explain/${suggestionId}`);
      setExplanation(response.data);
      setExplanationDialogOpen(true);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load explanation');
    } finally {
      setLoading(false);
    }
  };

  const captureHumanDecision = async () => {
    setLoading(true);
    setError(null);
    try {
      await api.post('/collaboration/h2a/decide', {
        suggestion_id: selectedSuggestion.id,
        ...decision,
      });
      setSuccess('Decision captured successfully');
      setDecisionDialogOpen(false);
      setDecision({
        decision: 'accept',
        rationale: '',
        modified_quantity: null,
        trade_off_preferences: {},
      });
      loadH2AData();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to capture decision');
    } finally {
      setLoading(false);
    }
  };

  // ============================================================================
  // H2H Functions
  // ============================================================================

  const loadH2HData = async () => {
    setLoading(true);
    try {
      const [requestsRes, approvalsRes] = await Promise.all([
        api.get('/collaboration/h2h/my-requests'),
        api.get('/collaboration/h2h/pending-approvals'),
      ]);
      setMyRequests(requestsRes.data);
      setPendingApprovals(approvalsRes.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load H2H data');
    } finally {
      setLoading(false);
    }
  };

  const sendApprovalRequest = async () => {
    setLoading(true);
    setError(null);
    try {
      await api.post('/collaboration/h2h/request-approval', newRequest);
      setSuccess('Approval request sent successfully');
      setRequestDialogOpen(false);
      setNewRequest({
        to_user: '',
        entity_type: 'supply_plan',
        entity_id: '',
        request_message: '',
        rationale: '',
        trade_offs: {},
        urgency: 'normal',
      });
      loadH2HData();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to send approval request');
    } finally {
      setLoading(false);
    }
  };

  const respondToApproval = async () => {
    setLoading(true);
    setError(null);
    try {
      await api.post('/collaboration/h2h/respond-approval', {
        request_id: selectedRequest.request_id,
        ...approvalResponse,
      });
      setSuccess('Approval response submitted successfully');
      setApprovalDialogOpen(false);
      setApprovalResponse({
        decision: 'approved',
        response_rationale: '',
        alternative_suggestion: null,
      });
      loadH2HData();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to respond to approval');
    } finally {
      setLoading(false);
    }
  };

  // ============================================================================
  // Activity Feed Functions
  // ============================================================================

  const loadActivityFeed = async () => {
    setLoading(true);
    try {
      const response = await api.get('/collaboration/activity-feed');
      setActivities(response.data || []);
    } catch (err) {
      console.error('Failed to load activity feed:', err);
      setActivities([]);
    } finally {
      setLoading(false);
    }
  };

  const formatTimeAgo = (timestamp) => {
    const now = new Date();
    const then = new Date(timestamp);
    const diffMs = now - then;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${diffDays}d ago`;
  };

  const getActivityIcon = (activity) => {
    if (activity.actor_type === 'agent') return <Bot className="h-5 w-5 text-primary" />;
    if (activity.actor_type === 'system') return <Bell className="h-5 w-5 text-muted-foreground" />;
    return <User className="h-5 w-5 text-purple-500" />;
  };

  const getActionVariant = (action) => {
    const variants = {
      approved: 'success',
      rejected: 'destructive',
      modified: 'warning',
      sent: 'info',
      generated: 'default',
      requested: 'warning',
      acknowledged: 'success',
      updated: 'info',
    };
    return variants[action] || 'secondary';
  };

  // ============================================================================
  // Render Functions
  // ============================================================================

  const renderActivityFeed = () => (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-lg font-semibold">Activity Feed</h2>
        <Button variant="outline" onClick={loadActivityFeed} leftIcon={<RefreshCw className="h-4 w-4" />}>
          Refresh
        </Button>
      </div>

      <Alert variant="info" className="mb-4">
        Real-time activity feed showing collaboration events across agents and humans.
        Activities are ordered by most recent first.
      </Alert>

      <div className="space-y-2">
        {activities.map((activity, index) => (
          <div
            key={activity.id}
            className="flex items-start gap-3 p-3 border rounded-lg hover:bg-muted/50 transition-colors"
          >
            <div className="mt-0.5">{getActivityIcon(activity)}</div>
            <div className="flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-medium text-sm">{activity.actor}</span>
                <Badge variant={getActionVariant(activity.action)}>{activity.action}</Badge>
                <span className="text-sm text-muted-foreground">
                  {activity.entity_type}
                  {activity.entity_id && ` (${activity.entity_id})`}
                </span>
              </div>
              <p className="text-sm mt-1">{activity.message}</p>
              <span className="text-xs text-muted-foreground">{formatTimeAgo(activity.timestamp)}</span>
            </div>
          </div>
        ))}
      </div>

      {activities.length === 0 && (
        <Card>
          <CardContent className="py-12 text-center">
            <Activity className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <p className="text-muted-foreground">
              No recent activity. Activities will appear here as collaboration events occur.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );

  const renderA2ATab = () => (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-lg font-semibold">Agent-to-Agent Coordination</h2>
        <Button onClick={() => setA2aDialogOpen(true)} leftIcon={<Send className="h-4 w-4" />}>
          Send A2A Message
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {a2aThreads.map((thread, index) => (
          <Card key={index}>
            <CardContent className="pt-4">
              <h3 className="font-semibold">
                {thread.agent1} ↔ {thread.agent2}
              </h3>
              <p className="text-sm text-muted-foreground mb-3">
                {thread.message_count} messages
              </p>
              <Button
                size="sm"
                variant="outline"
                onClick={() => loadA2AThread(thread.agent1, thread.agent2)}
              >
                View Thread
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      {selectedThread && (
        <Card className="mt-4">
          <CardContent className="pt-4">
            <h3 className="font-semibold mb-4">
              Thread: {selectedThread.agent1} ↔ {selectedThread.agent2}
            </h3>
            <div className="space-y-3">
              {selectedThread.messages?.map((msg, idx) => (
                <div key={idx} className="border-b pb-3">
                  <p className="font-medium text-sm">{msg.from_agent} → {msg.to_agent}</p>
                  <p className="text-sm mt-1">{msg.content}</p>
                  <Badge variant="secondary" className="mt-2">{msg.message_type}</Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* A2A Message Dialog */}
      <Modal
        isOpen={a2aDialogOpen}
        onClose={() => setA2aDialogOpen(false)}
        title="Send Agent-to-Agent Message"
        size="lg"
      >
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="fromAgent">From Agent</Label>
              <Input
                id="fromAgent"
                value={newA2AMessage.from_agent}
                onChange={(e) => setNewA2AMessage({ ...newA2AMessage, from_agent: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="toAgent">To Agent</Label>
              <Input
                id="toAgent"
                value={newA2AMessage.to_agent}
                onChange={(e) => setNewA2AMessage({ ...newA2AMessage, to_agent: e.target.value })}
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="messageType">Message Type</Label>
            <Select
              value={newA2AMessage.message_type}
              onValueChange={(value) => setNewA2AMessage({ ...newA2AMessage, message_type: value })}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select message type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="coordination">Coordination</SelectItem>
                <SelectItem value="negotiation">Negotiation</SelectItem>
                <SelectItem value="information">Information</SelectItem>
                <SelectItem value="request">Request</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="messageContent">Message Content</Label>
            <Textarea
              id="messageContent"
              rows={4}
              value={newA2AMessage.content}
              onChange={(e) => setNewA2AMessage({ ...newA2AMessage, content: e.target.value })}
            />
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="outline" onClick={() => setA2aDialogOpen(false)}>Cancel</Button>
          <Button onClick={sendA2AMessage} disabled={loading}>Send</Button>
        </div>
      </Modal>
    </div>
  );

  const renderH2ATab = () => (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-lg font-semibold">Human-to-Agent Collaboration</h2>
        <Button variant="outline" onClick={loadH2AData} leftIcon={<RefreshCw className="h-4 w-4" />}>
          Refresh
        </Button>
      </div>

      <Card>
        <CardContent className="pt-4">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Agent</TableHead>
                <TableHead>Product</TableHead>
                <TableHead>Suggested Quantity</TableHead>
                <TableHead>Confidence</TableHead>
                <TableHead>Rationale (Brief)</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {agentSuggestions.map((suggestion) => (
                <TableRow key={suggestion.id}>
                  <TableCell>{suggestion.agent_id}</TableCell>
                  <TableCell>{formatProduct(suggestion.product_id, suggestion.product_name)}</TableCell>
                  <TableCell>{suggestion.suggested_quantity}</TableCell>
                  <TableCell>
                    <Badge variant={suggestion.confidence > 0.9 ? 'success' : 'warning'}>
                      {(suggestion.confidence * 100).toFixed(0)}%
                    </Badge>
                  </TableCell>
                  <TableCell className="max-w-xs truncate">{suggestion.rationale}</TableCell>
                  <TableCell>
                    <Badge variant="secondary">{suggestion.status}</Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => loadExplanation(suggestion.id)}
                            >
                              <Info className="h-4 w-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>View Explanation</TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => {
                                setSelectedSuggestion(suggestion);
                                setDecisionDialogOpen(true);
                              }}
                            >
                              <CheckCircle className="h-4 w-4 text-primary" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Make Decision</TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Explanation Dialog */}
      <Modal
        isOpen={explanationDialogOpen}
        onClose={() => setExplanationDialogOpen(false)}
        title="Agent Decision Explanation"
        size="xl"
      >
        {explanation && (
          <Accordion type="single" collapsible defaultValue="rationale">
            <AccordionItem value="rationale">
              <AccordionTrigger>Rationale Breakdown</AccordionTrigger>
              <AccordionContent>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <h4 className="font-medium mb-2">Primary Factors:</h4>
                    <ul className="list-disc list-inside text-sm space-y-1">
                      {explanation.rationale_breakdown?.primary_factors?.map((factor, idx) => (
                        <li key={idx}>{factor}</li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <h4 className="font-medium mb-2">Data Sources:</h4>
                    <ul className="list-disc list-inside text-sm space-y-1">
                      {explanation.rationale_breakdown?.data_sources?.map((source, idx) => (
                        <li key={idx}>{source}</li>
                      ))}
                    </ul>
                  </div>
                  <div className="md:col-span-2">
                    <h4 className="font-medium mb-2">Assumptions:</h4>
                    <ul className="list-disc list-inside text-sm space-y-1">
                      {explanation.rationale_breakdown?.assumptions?.map((assumption, idx) => (
                        <li key={idx}>{assumption}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              </AccordionContent>
            </AccordionItem>

            <AccordionItem value="alternatives">
              <AccordionTrigger>Alternatives Considered</AccordionTrigger>
              <AccordionContent>
                <div className="space-y-3">
                  {explanation.alternatives_considered?.map((alt, idx) => (
                    <div key={idx} className="border-b pb-2">
                      <p className="font-medium">{alt.description}</p>
                      <p className="text-sm text-muted-foreground">
                        Score: {alt.score} | Reason not chosen: {alt.reason_not_chosen}
                      </p>
                    </div>
                  ))}
                </div>
              </AccordionContent>
            </AccordionItem>

            <AccordionItem value="tradeoffs">
              <AccordionTrigger>Trade-off Analysis</AccordionTrigger>
              <AccordionContent>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {Object.entries(explanation.trade_off_analysis || {}).map(([key, value]) => (
                    <Card key={key}>
                      <CardContent className="pt-4">
                        <h4 className="font-medium mb-1">{key}</h4>
                        <p className="text-sm text-muted-foreground">{JSON.stringify(value)}</p>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </AccordionContent>
            </AccordionItem>

            <AccordionItem value="risks">
              <AccordionTrigger>Risks and Assumptions</AccordionTrigger>
              <AccordionContent>
                <pre className="text-sm bg-muted p-3 rounded overflow-auto">
                  {JSON.stringify(explanation.risks_and_assumptions, null, 2)}
                </pre>
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        )}
        <div className="flex justify-end mt-6">
          <Button variant="outline" onClick={() => setExplanationDialogOpen(false)}>Close</Button>
        </div>
      </Modal>

      {/* Decision Dialog */}
      <Modal
        isOpen={decisionDialogOpen}
        onClose={() => setDecisionDialogOpen(false)}
        title="Capture Decision on Agent Suggestion"
        size="lg"
      >
        {selectedSuggestion && (
          <div className="space-y-4">
            <Alert variant="info">
              Agent: {selectedSuggestion.agent_id} | Product: {formatProduct(selectedSuggestion.product_id, selectedSuggestion.product_name)} |
              Suggested: {selectedSuggestion.suggested_quantity}
            </Alert>

            <div className="space-y-2">
              <Label htmlFor="decisionSelect">Decision</Label>
              <Select
                value={decision.decision}
                onValueChange={(value) => setDecision({ ...decision, decision: value })}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select decision" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="accept">Accept</SelectItem>
                  <SelectItem value="reject">Reject</SelectItem>
                  <SelectItem value="modify">Modify</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {decision.decision === 'modify' && (
              <div className="space-y-2">
                <Label htmlFor="modifiedQty">Modified Quantity</Label>
                <Input
                  id="modifiedQty"
                  type="number"
                  value={decision.modified_quantity || ''}
                  onChange={(e) =>
                    setDecision({ ...decision, modified_quantity: parseInt(e.target.value) })
                  }
                />
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="decisionRationale">Rationale (Why did you make this decision?) *</Label>
              <Textarea
                id="decisionRationale"
                rows={4}
                value={decision.rationale}
                onChange={(e) => setDecision({ ...decision, rationale: e.target.value })}
              />
            </div>

            <div className="space-y-2">
              <Label>Trade-off Preferences (Optional)</Label>
              <p className="text-xs text-muted-foreground">
                What factors influenced your decision? (e.g., cost vs service, risk vs flexibility)
              </p>
              <Textarea
                rows={2}
                placeholder='e.g., {"cost_priority": "high", "risk_tolerance": "low"}'
                value={JSON.stringify(decision.trade_off_preferences)}
                onChange={(e) => {
                  try {
                    setDecision({ ...decision, trade_off_preferences: JSON.parse(e.target.value) });
                  } catch {}
                }}
              />
            </div>
          </div>
        )}
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="outline" onClick={() => setDecisionDialogOpen(false)}>Cancel</Button>
          <Button onClick={captureHumanDecision} disabled={loading || !decision.rationale}>
            Submit Decision
          </Button>
        </div>
      </Modal>
    </div>
  );

  const renderH2HTab = () => (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-lg font-semibold">Human-to-Human Collaboration</h2>
        <Button onClick={() => setRequestDialogOpen(true)} leftIcon={<Send className="h-4 w-4" />}>
          Request Approval
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* My Requests */}
        <Card>
          <CardContent className="pt-4">
            <h3 className="font-semibold mb-4">My Approval Requests</h3>
            <div className="space-y-3">
              {myRequests.map((request) => (
                <div key={request.request_id} className="border-b pb-3">
                  <p className="font-medium">{request.request_message}</p>
                  <p className="text-sm text-muted-foreground">
                    To: {request.to_user} | Entity: {request.entity_type}
                  </p>
                  <div className="flex gap-2 mt-2">
                    <Badge variant="secondary">{request.status}</Badge>
                    <Badge variant="warning">{request.urgency}</Badge>
                  </div>
                </div>
              ))}
              {myRequests.length === 0 && (
                <p className="text-sm text-muted-foreground">No requests sent</p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Pending Approvals */}
        <Card>
          <CardContent className="pt-4">
            <h3 className="font-semibold mb-4">Pending Approvals (Assigned to Me)</h3>
            <div className="space-y-3">
              {pendingApprovals.map((request) => (
                <div key={request.request_id} className="border-b pb-3">
                  <p className="font-medium">{request.request_message}</p>
                  <p className="text-sm text-muted-foreground">
                    From: {request.from_user} | Entity: {request.entity_type}
                  </p>
                  <p className="text-sm text-muted-foreground mt-1">
                    Rationale: {request.rationale}
                  </p>
                  <Button
                    size="sm"
                    variant="outline"
                    className="mt-2"
                    onClick={() => {
                      setSelectedRequest(request);
                      setApprovalDialogOpen(true);
                    }}
                  >
                    Respond
                  </Button>
                </div>
              ))}
              {pendingApprovals.length === 0 && (
                <p className="text-sm text-muted-foreground">No pending approvals</p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Request Approval Dialog */}
      <Modal
        isOpen={requestDialogOpen}
        onClose={() => setRequestDialogOpen(false)}
        title="Request Approval"
        size="lg"
      >
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="toUser">To User (User ID) *</Label>
              <Input
                id="toUser"
                value={newRequest.to_user}
                onChange={(e) => setNewRequest({ ...newRequest, to_user: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label>Entity Type</Label>
              <Select
                value={newRequest.entity_type}
                onValueChange={(value) => setNewRequest({ ...newRequest, entity_type: value })}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select entity type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="supply_plan">Supply Plan</SelectItem>
                  <SelectItem value="recommendation">Recommendation</SelectItem>
                  <SelectItem value="demand_plan">Demand Plan</SelectItem>
                  <SelectItem value="policy_override">Policy Override</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="entityId">Entity ID *</Label>
              <Input
                id="entityId"
                value={newRequest.entity_id}
                onChange={(e) => setNewRequest({ ...newRequest, entity_id: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label>Urgency</Label>
              <Select
                value={newRequest.urgency}
                onValueChange={(value) => setNewRequest({ ...newRequest, urgency: value })}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select urgency" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="low">Low</SelectItem>
                  <SelectItem value="normal">Normal</SelectItem>
                  <SelectItem value="high">High</SelectItem>
                  <SelectItem value="critical">Critical</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="requestMessage">Request Message *</Label>
            <Input
              id="requestMessage"
              value={newRequest.request_message}
              onChange={(e) => setNewRequest({ ...newRequest, request_message: e.target.value })}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="requestRationale">Rationale (Why do you need approval?) *</Label>
            <Textarea
              id="requestRationale"
              rows={4}
              value={newRequest.rationale}
              onChange={(e) => setNewRequest({ ...newRequest, rationale: e.target.value })}
            />
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="outline" onClick={() => setRequestDialogOpen(false)}>Cancel</Button>
          <Button onClick={sendApprovalRequest} disabled={loading}>Send Request</Button>
        </div>
      </Modal>

      {/* Approval Response Dialog */}
      <Modal
        isOpen={approvalDialogOpen}
        onClose={() => setApprovalDialogOpen(false)}
        title="Respond to Approval Request"
        size="lg"
      >
        {selectedRequest && (
          <div className="space-y-4">
            <Alert variant="info">
              From: {selectedRequest.from_user} | Entity: {selectedRequest.entity_type} (
              {selectedRequest.entity_id})
              <br />
              Request: {selectedRequest.request_message}
              <br />
              Rationale: {selectedRequest.rationale}
            </Alert>

            <div className="space-y-2">
              <Label>Decision</Label>
              <Select
                value={approvalResponse.decision}
                onValueChange={(value) =>
                  setApprovalResponse({ ...approvalResponse, decision: value })
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select decision" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="approved">Approved</SelectItem>
                  <SelectItem value="rejected">Rejected</SelectItem>
                  <SelectItem value="needs_modification">Needs Modification</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="responseRationale">Response Rationale (Why did you make this decision?) *</Label>
              <Textarea
                id="responseRationale"
                rows={4}
                value={approvalResponse.response_rationale}
                onChange={(e) =>
                  setApprovalResponse({ ...approvalResponse, response_rationale: e.target.value })
                }
              />
            </div>

            {approvalResponse.decision === 'rejected' && (
              <div className="space-y-2">
                <Label>Alternative Suggestion (Optional)</Label>
                <Textarea
                  rows={3}
                  placeholder='e.g., {"alternative": "Reduce quantity by 20%", "reason": "Current capacity constraints"}'
                  onChange={(e) => {
                    try {
                      setApprovalResponse({
                        ...approvalResponse,
                        alternative_suggestion: JSON.parse(e.target.value),
                      });
                    } catch {}
                  }}
                />
              </div>
            )}
          </div>
        )}
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="outline" onClick={() => setApprovalDialogOpen(false)}>Cancel</Button>
          <Button
            onClick={respondToApproval}
            disabled={loading || !approvalResponse.response_rationale}
          >
            Submit Response
          </Button>
        </div>
      </Modal>
    </div>
  );

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Collaboration Hub</h1>
        <Badge>Sprint 5</Badge>
      </div>

      {error && (
        <Alert variant="destructive" className="mb-4" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {success && (
        <Alert variant="success" className="mb-4" onClose={() => setSuccess(null)}>
          {success}
        </Alert>
      )}

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="mb-4">
          <TabsTrigger value="a2a">Agent-to-Agent (A2A)</TabsTrigger>
          <TabsTrigger value="h2a">Human-to-Agent (H2A)</TabsTrigger>
          <TabsTrigger value="h2h">Human-to-Human (H2H)</TabsTrigger>
          <TabsTrigger value="activity" className="flex items-center gap-2">
            <Activity className="h-4 w-4" />
            Activity Feed
          </TabsTrigger>
          <TabsTrigger value="messaging" className="flex items-center gap-2">
            <MessageCircle className="h-4 w-4" />
            Team Messaging
          </TabsTrigger>
        </TabsList>

        <Card>
          <CardContent className="pt-4 min-h-[500px]">
            <TabsContent value="a2a">{renderA2ATab()}</TabsContent>
            <TabsContent value="h2a">{renderH2ATab()}</TabsContent>
            <TabsContent value="h2h">{renderH2HTab()}</TabsContent>
            <TabsContent value="activity">{renderActivityFeed()}</TabsContent>
            <TabsContent value="messaging"><TeamMessaging /></TabsContent>
          </CardContent>
        </Card>
      </Tabs>
    </div>
  );
};

export default CollaborationHub;
