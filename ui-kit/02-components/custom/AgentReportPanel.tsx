import { Sheet, SheetContent } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Slider } from "@/components/ui/slider";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { X, ChevronDown, ChevronUp, AlertTriangle, TrendingUp, Package, Download, FileText, ChartLine, MessageSquare, ArrowLeft, Send, Bot, User, CheckCircle, AlertCircle, StopCircle, Users, Calculator, FileCheck, Sparkles, ChevronLeft, ArrowRight, Target, Brain, Sliders, BarChart3, ExternalLink, ChevronRight, ArrowLeftRight, Edit3, Play, Check, Info, Edit2, Eye, Database, GitBranch, LineChart as LineChartIcon } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { CollapsibleReportSummary } from "./CollapsibleReportSummary";
import { FindingCard } from "./AgentChat/FindingCard";
import { CognitiveProcessView, CognitiveProcess } from "./AgentChat/CognitiveProcessView";
import { ContextTags, ContextTag } from "./AgentChat/ContextTags";
import { CompactRecommendationCard } from "./AgentChat/CompactRecommendationCard";
import { EditWorkflowCard } from "./AgentChat/EditWorkflowCard";
import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { useDataSource } from "@/contexts/DataSourceContext";
import defaultReportData from "@/data/default/agent_report-default.json";
import chatScript from "@/data/default/agent_chat_script-default.json";
import { V1ReportPanel } from "./V1ReportPanel";
import { VersionedReportPanel } from "./VersionedReportPanel";
import { V4ReportPanel } from "./V4ReportPanel";

// Initial cognitive process data for first message
const INITIAL_COGNITIVE_PROCESS: CognitiveProcess[] = [
  { step: "Pattern Recognition", description: "Identified viral social media event (TikTok) driving +47% demand lift", status: "complete" },
  { step: "Temporal Analysis", description: "Validated 3-month sustained momentum vs. temporary spike", status: "complete" },
  { step: "Model Calibration", description: "Detected ML model systematic under-prediction (-12% bias)", status: "complete" },
  { step: "Risk Assessment", description: "Evaluated confidence at 87% based on signal strength", status: "complete" },
];

const INITIAL_CONTEXT_TAGS: ContextTag[] = [
  { source: "TikTok Viral Event (May 2025)", type: "external", description: "#HydraBoostChallenge reached 2.4M views" },
  { source: "Historical Sales Data", type: "historical", description: "12-month actuals vs. forecast performance" },
  { source: "ML Base Forecast", type: "ml_model", description: "Conservative bias detected in new product ramp" },
  { source: "Customer POS Data", type: "user_provided", description: "Costco +52%, Target +38% actual vs. forecast" },
];

// Quick action pills for agent mode
const QUICK_ACTIONS = [
  "Why +15%?",
  "What if 12%?",
  "Break down by customer",
  "Show me risks",
  "Make an edit",
  "Different scenarios",
];

// Reason tag categories for edit workflow
const REASON_TAG_CATEGORIES: Record<string, string[]> = {
  "Seasonality & Marketing": ["Seasonal Shift", "One-Time Event", "Marketing/Promo"],
  "Customer & Channel": ["Customer Input", "Contract Change", "Distribution"],
  "Market Signals": ["Competitor", "Consumer Sentiment", "Economic", "Regulatory"],
  "Product & Portfolio": ["NPI", "Product Change", "Quality"],
  "Strategy & Judgment": ["Plan Change", "Planner Judgment"]
};

// Customer weights for breakdown calculations
const CUSTOMER_WEIGHTS: Record<string, number> = {
  "Costco": 0.32,
  "Target": 0.28,
  "Walmart": 0.25,
  "Whole Foods": 0.15
};

// Edit workflow data structures - matches EditWorkflowCard conversational steps
interface EditWorkflowData {
  step: "adjustmentInput" | "explainLearning" | "contextTags" | "confidence" | "reasoning" | "confirmation" | "processing" | "complete";
  agentRec: number;
  currentValue: number;
  userAdjustment?: number;
  adjustmentMode?: "percent" | "number" | "overwrite";
  adjustmentInput?: string;
  customerBreakdown?: CustomerEdit[];
  selectedTags?: string[];
  confidence?: number;
  reasoning?: string;
  isPinpointMode?: boolean;
  delta?: number;
  deltaPercent?: number;
}

interface CustomerEdit {
  name: string;
  agentRec: number;
  userEdit: number;
  change: number;
  percentage: number;
}

// Natural language command parser
// IMPORTANT: This ONLY parses explicit edit commands, not "what if" scenarios
function parseUserCommand(input: string): {
  type: "edit_adjustment" | "customer_specific" | "confidence" | "what_if_scenario" | "unknown";
  value?: number;
  mode?: "percent" | "number" | "overwrite";
  customer?: string;
} {
  const normalized = input.toLowerCase().trim();

  // CRITICAL: "What if 12%?" is a SCENARIO query, NOT an edit command
  // Check for "what if" pattern FIRST before other patterns
  if (normalized.includes("what if") || normalized.includes("what about")) {
    const percentMatch = normalized.match(/(\d+)%?/);
    if (percentMatch) {
      return { type: "what_if_scenario", value: parseFloat(percentMatch[1]), mode: "percent" };
    }
    return { type: "what_if_scenario" };
  }

  // Only parse as edit if user explicitly says "edit", "change", "adjust", "set to", "make it"
  const isExplicitEdit = normalized.includes("edit") || 
                          normalized.includes("change") || 
                          normalized.includes("adjust") ||
                          normalized.includes("set to") ||
                          normalized.includes("make it");

  // Percentage: "+12%", "12%", "+12 percent" - ONLY if explicit edit intent
  if (isExplicitEdit && (normalized.match(/[+-]?\d+%/) || normalized.includes("percent"))) {
    const match = normalized.match(/([+-]?\d+)%?/);
    if (match) {
      return { type: "edit_adjustment", value: parseFloat(match[1]), mode: "percent" };
    }
  }

  // Absolute value: "2000", "2000 units" - ONLY if it's the entire message (direct value input)
  if (normalized.match(/^\d+$/) || normalized.match(/^\d+\s*units?$/)) {
    const match = normalized.match(/(\d+)/);
    if (match) {
      return { type: "edit_adjustment", value: parseFloat(match[1]), mode: "overwrite" };
    }
  }

  // Unit adjustment: "+200", "-200 units" - ONLY if it's a direct adjustment
  if (normalized.match(/^[+-]\d+\s*(units?)?$/)) {
    const match = normalized.match(/([+-]\d+)/);
    if (match) {
      return { type: "edit_adjustment", value: parseFloat(match[1]), mode: "number" };
    }
  }

  // Customer-specific: "reduce Walmart to 500", "set Costco to 650"
  const customers = ["costco", "target", "walmart", "whole foods"];
  for (const customer of customers) {
    if (normalized.includes(customer) && (normalized.includes("set") || normalized.includes("to"))) {
      const valueMatch = normalized.match(/\d+/);
      if (valueMatch) {
        return {
          type: "customer_specific",
          customer: customer.split(" ").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" "),
          value: parseFloat(valueMatch[0])
        };
      }
    }
  }

  // Confidence: "I'm 80% confident", "80% confidence"
  if (normalized.includes("confident") || normalized.includes("confidence")) {
    const match = normalized.match(/(\d+)%?/);
    if (match) {
      return { type: "confidence", value: parseFloat(match[1]) };
    }
  }

  return { type: "unknown" };
}

// Helper: Calculate adjusted value
function calculateAdjustedValue(currentValue: number, input: number, mode: "percent" | "number" | "overwrite"): number {
  if (mode === "percent") {
    return Math.round(currentValue * (1 + input / 100));
  } else if (mode === "number") {
    return currentValue + input;
  } else {
    return input;
  }
}

// Helper: Calculate customer breakdown
function calculateCustomerBreakdown(totalValue: number, isPinpoint: boolean): CustomerEdit[] {
  const agentRecTotal = 2128;
  
  return Object.entries(CUSTOMER_WEIGHTS).map(([name, weight]) => {
    const userEdit = Math.round(totalValue * weight);
    const agentRec = Math.round(agentRecTotal * weight);
    return {
      name,
      agentRec,
      userEdit,
      change: userEdit - agentRec,
      percentage: weight * 100
    };
  });
}

// Helper: Calculate smart confidence
function calculateSmartConfidence(agentRec: number, userEdit: number, tags: string[]): number {
  const deviation = Math.abs((userEdit - agentRec) / agentRec);
  const baseConfidence = 85;
  const deviationPenalty = deviation * 30;
  
  const uncertaintyTags = ["One-Time Event", "Planner Judgment", "Economic"];
  const hasUncertainty = tags.some(t => uncertaintyTags.includes(t));
  const tagPenalty = hasUncertainty ? 10 : 0;
  
  return Math.round(Math.max(50, Math.min(95, baseConfidence - deviationPenalty - tagPenalty)));
}

// Helper: Generate smart reasoning suggestions
function generateSmartSuggestions(editWorkflow: EditWorkflowData): string[] {
  const suggestions: string[] = [];
  const tags = editWorkflow.selectedTags || [];
  const change = editWorkflow.userAdjustment && editWorkflow.agentRec 
    ? ((editWorkflow.userAdjustment - editWorkflow.agentRec) / editWorkflow.agentRec * 100).toFixed(1)
    : "0";
  
  if (tags.includes("One-Time Event")) {
    suggestions.push(`TikTok event impact seems ${editWorkflow.userAdjustment! < editWorkflow.agentRec ? 'overestimated' : 'underestimated'} based on current data`);
  }
  
  if (tags.includes("Customer Input")) {
    suggestions.push(`Customer POS data suggests ${change}% adjustment is more realistic given current trends`);
  }
  
  if (tags.includes("Planner Judgment")) {
    suggestions.push(`Based on experience with similar products, ${Math.abs(parseFloat(change))}% adjustment feels appropriate`);
  }
  
  // Default suggestions
  if (suggestions.length === 0) {
    suggestions.push(`Adjusting based on market signals and recent performance data`);
    suggestions.push(`Historical patterns suggest this adjustment level is appropriate`);
  }
  
  return suggestions.slice(0, 3);
}

// Customer data for disaggregation
const CUSTOMERS = {
  "Costco": { weight: 0.32, original: 592 },
  "Target": { weight: 0.28, original: 518 },
  "Walmart": { weight: 0.25, original: 463 },
  "Whole Foods": { weight: 0.15, original: 278 }
};

// Reason tag groups
const REASON_TAG_GROUPS = [
  {
    group: "Seasonality & Marketing",
    items: [
      { code: "SEASONAL", label: "Seasonal Shift" },
      { code: "ONE-TIME-EVENT", label: "One-Time Event" },
      { code: "MKT-PROMO", label: "Marketing/Promo" }
    ]
  },
  {
    group: "Customer & Channel",
    items: [
      { code: "CUST-MKT-INTEL", label: "Customer/Market Input" },
      { code: "CONTRACT-CHG", label: "Major Contract Change" },
      { code: "DIST-CHNL-CHG", label: "Channel/Distribution" }
    ]
  },
  {
    group: "Market & Macro Signals",
    items: [
      { code: "COMPETITOR", label: "Competitor Activity" },
      { code: "CONSUM-SENT", label: "Consumer Sentiment" },
      { code: "ECON-KNOWL", label: "Economic Indicators" },
      { code: "REGULATORY", label: "Regulatory Change" }
    ]
  },
  {
    group: "Product & Portfolio",
    items: [
      { code: "NPI", label: "New Product Intro (NPI)" },
      { code: "PRODUCT-SPEC", label: "Product Spec Change" },
      { code: "QUALITY", label: "Quality Recovery" }
    ]
  },
  {
    group: "Strategy & Judgement",
    items: [
      { code: "COMP-STRAT-FIN", label: "Internal Plan Change" },
      { code: "JUDGEMNT", label: "Planner Judgement" }
    ]
  }
];

interface ChatMessage {
  id: string;
  role: 'user' | 'agent';
  content: string;
  type?: 'text' | 'recommendation' | 'calculation' | 'modify_options' | 'edit_preview' | 'reasoning_form' | 'confirmation' | 'scenario_analysis' | 'customer_breakdown' | 'finding' | 'comparison' | 'edit_panel';
  data?: any;
}

interface AgentMessage {
  role: 'user' | 'agent';
  type: string;
  content: string;
  data?: any;
  cognitiveProcess?: CognitiveProcess[];
  contextTags?: ContextTag[];
  comparisonData?: {
    scenario1: { label: string; value: number; confidence: number; risk: string };
    scenario2: { label: string; value: number; confidence: number; risk: string };
  };
  customerBreakdown?: { name: string; current: number; adjusted: number; change: number }[];
  editWorkflow?: EditWorkflowData;
  verificationLinks?: {
    decisionLog: string;
    validation: string;
    chart: string;
    scenarios: string;
  };
  // NEW: Chart data for visualizations
  chartData?: { month: string; historical: number | null; scenario1: number; agentRec: number }[];
  customerBreakdownChart?: {
    type: "bar";
    data: Array<{ customer: string; current: number; adjusted: number }>;
  };
  riskDistribution?: {
    upside: { label: string; probability: number; impact: string; factors: string[] };
    base: { label: string; probability: number; impact: string; factors: string[] };
    downside: { label: string; probability: number; impact: string; factors: string[] };
  };
}

interface AgentReportPanelProps {
  open: boolean;
  onClose: () => void;
  productLink?: string | null;
  dataParam?: string | null;
  skuId?: number | null;
  onUpdateStatus?: (productLink: string, newStatus: "Submitted" | "Pending") => void;
  hideActionButtons?: boolean;
}

export function AgentReportPanel({ open, onClose, productLink, dataParam, skuId, onUpdateStatus, hideActionButtons = false }: AgentReportPanelProps) {
  const navigate = useNavigate();
  const { dataSource } = useDataSource();
  const [reportData, setReportData] = useState(defaultReportData);
  const [chatMode, setChatMode] = useState(false);
  const [showReportInChat, setShowReportInChat] = useState(false);
  
  // Agent workspace state - Full editing capabilities
  const [agentMode, setAgentMode] = useState(false);
  const [agentMessages, setAgentMessages] = useState<AgentMessage[]>([]);
  const [agentUserInput, setAgentUserInput] = useState('');
  const [workflowState, setWorkflowState] = useState<'exploring' | 'comparing' | 'adjusting' | 'reasoning' | 'confirming'>('exploring');
  const [agentAdjustmentValue, setAgentAdjustmentValue] = useState(15);
  const [agentAdjustmentMode, setAgentAdjustmentMode] = useState<'percent' | 'units'>('percent');
  const [agentAdjustmentReason, setAgentAdjustmentReason] = useState('');
  const [showAgentCustomerBreakdown, setShowAgentCustomerBreakdown] = useState(false);
  const [customerAdjustments, setCustomerAdjustments] = useState<{[key: string]: number}>({
    'Costco': 15,
    'Target': 15,
    'Walmart': 15,
    'Whole Foods': 15
  });
  const [agentEditMode, setAgentEditMode] = useState<'aggregate' | 'pinpoint'>('aggregate');
  
  // Ref for auto-scrolling in agent mode
  const agentMessagesEndRef = useRef<HTMLDivElement>(null);
  const agentChatContainerRef = useRef<HTMLDivElement>(null);
  
  // Edit workflow state
  const [editWorkflow, setEditWorkflow] = useState<EditWorkflowData | null>(null);
  const [showEditBreakdown, setShowEditBreakdown] = useState(false);
  const [editReasonTags, setEditReasonTags] = useState<string[]>([]);
  const [editConfidence, setEditConfidence] = useState(75);
  const [editReasoning, setEditReasoning] = useState('');
  
  // Product-specific history state (only for 3 specific SKUs)
  const [productHistory, setProductHistory] = useState<any>(null);
  const [showExpandedHistoryChart, setShowExpandedHistoryChart] = useState(false);
  const [decisionHistoryOpen, setDecisionHistoryOpen] = useState(false);
  const [overrideReasoningOpen, setOverrideReasoningOpen] = useState(false);
  
  // V1 Report state for 3 specific SKUs
  const [v1ReportData, setV1ReportData] = useState<any>(null);
  const [isV1Report, setIsV1Report] = useState(false);

  // Auto-scroll when agent messages change - with delay for DOM update
  useEffect(() => {
    if (agentMessagesEndRef.current && agentChatContainerRef.current) {
      // Small delay to ensure DOM has fully updated
      setTimeout(() => {
        const container = agentChatContainerRef.current;
        if (!container) return;

        const scrollHeight = container.scrollHeight;
        const height = container.clientHeight;
        const maxScrollTop = scrollHeight - height;

        container.scrollTo({
          top: maxScrollTop,
          behavior: "smooth"
        });
      }, 100);
    }
  }, [agentMessages]);

  // Version mapping for specific SKUs - keyed by data source
  const versionMaps: Record<string, Record<string, { identifier: string; version: string }>> = {
    default: {
      'Hydraboost Classic - Los Angeles - Costco': { identifier: 'hydraboost_classic_la', version: 'v1' },
      'Hydralite Alkaline - Philadelphia - Kroger': { identifier: 'hydralite_philly', version: 'v2' },
      'Hydrapure Mountain Spring 36-Pack - Chicago - Costco': { identifier: 'hydrapure_chicago', version: 'v3' },
      'Hydraboost Classic - Atlanta - Kroger': { identifier: 'hydraboost_classic_atlanta', version: 'v4' }
    },
    fooddist: {
      'Chobani Greek Yogurt Blueberry 5.3oz - Burley DC - Site 127293-1': { identifier: 'chobani_burley', version: 'v1' },
      "King's Hawaiian Sweet Ham 12-12.8oz - Burley DC - Site 147550-2": { identifier: 'kings_hawaiian_burley', version: 'v2' },
      'Kraft Ranch Dressing 60pk - Cambridge City DC - Site 134892-1': { identifier: 'kraft_cambridge', version: 'v3' }
    }
  };

  // Get the version map for the current data source
  const versionMap = versionMaps[dataSource] || versionMaps.default;

  // State for versioned report
  const [versionedReportData, setVersionedReportData] = useState<any>(null);
  const [reportVersion, setReportVersion] = useState<string | null>(null);
  const [isLoadingVersionedReport, setIsLoadingVersionedReport] = useState(false);

  // Load product-specific history and versioned report for specific SKUs
  useEffect(() => {
    const loadProductData = async () => {
      if (productLink && versionMap[productLink]) {
        const { identifier, version } = versionMap[productLink];

        // Determine the data folder based on data source
        const dataFolder = dataSource === 'default' ? 'default' : dataSource;

        // Set loading state FIRST - prevents flash of default design
        setIsLoadingVersionedReport(true);

        try {
          // Load product history (if exists) - try data source folder first, fall back to default
          try {
            const historyModule = await import(`@/data/${dataFolder}/product_history-${identifier}.json`);
            setProductHistory(historyModule.default);
          } catch {
            // Try default folder as fallback
            try {
              const historyModule = await import(`@/data/default/product_history-${identifier}.json`);
              setProductHistory(historyModule.default);
            } catch {
              setProductHistory(null);
            }
          }

          // Load versioned report data based on SKU-specific version
          // Try data source folder first, fall back to default
          let reportModule;
          try {
            reportModule = await import(`@/data/${dataFolder}/agent_report-${identifier}-${version}.json`);
          } catch {
            // Fall back to default folder
            reportModule = await import(`@/data/default/agent_report-${identifier}-${version}.json`);
          }

          setVersionedReportData(reportModule.default);
          setReportVersion(version);
          setV1ReportData(reportModule.default); // Keep for backward compatibility
          setIsV1Report(true);
        } catch (error) {
          console.error('Failed to load versioned report data:', error);
          setProductHistory(null);
          setVersionedReportData(null);
          setReportVersion(null);
          setV1ReportData(null);
          setIsV1Report(false);
        } finally {
          // Clear loading state when done (success or failure)
          setIsLoadingVersionedReport(false);
        }
      } else {
        setProductHistory(null);
        setVersionedReportData(null);
        setReportVersion(null);
        setV1ReportData(null);
        setIsV1Report(false);
        setIsLoadingVersionedReport(false);
      }
    };

    if (open) {
      loadProductData();
    }
  }, [productLink, open, dataSource, versionMap]);

  // Initialize agent workspace with greeting including cognitive process
  const initializeAgentMode = () => {
    setAgentMode(true);
    setWorkflowState('exploring');
    setAgentMessages([{
      role: 'agent',
      type: 'recommendation',
      content: "I recommend increasing HydraBoost Zero forecast by +15% (1,850 → 2,128 units) for Q3 2025.",
      data: chatScript.initialGreeting.content,
      cognitiveProcess: INITIAL_COGNITIVE_PROCESS,
      contextTags: INITIAL_CONTEXT_TAGS
    }]);
  };

  // Handler for agent workspace questions with sophisticated cognitive responses
  const handleAgentQuestion = (question: string) => {
    const lowerQ = question.toLowerCase();
    
    // Add user message
    setAgentMessages(prev => [...prev, { role: 'user', type: 'text', content: question }]);
    
    // Try to parse natural language command first
    const parsedCommand = parseUserCommand(question);
    
    // Simulate agent response with delay
    setTimeout(() => {
      // PRIORITY 1: Handle "what if" scenario queries (NOT edit commands)
      if (parsedCommand.type === "what_if_scenario") {
        const percent = parsedCommand.value || 12;
        setWorkflowState('comparing');
        setAgentMessages(prev => [...prev, {
          role: 'agent',
          type: 'comparison',
          content: `Comparing +${percent}% vs. +15% (agent rec) scenarios reveals trade-offs in risk-adjusted outcomes:`,
          comparisonData: {
            scenario1: { 
              label: `+${percent}%`, 
              value: Math.round(1850 * (1 + percent / 100)), 
              confidence: Math.max(60, 87 - Math.abs(15 - percent) * 2), 
              risk: percent < 15 
                ? `Miss $${Math.round((15 - percent) * 1850 * 0.15 / 10)}K revenue upside if momentum sustains`
                : `Carry $${Math.round((percent - 15) * 1850 * 0.05 / 10)}K excess inventory if trend reverses`
            },
            scenario2: { label: "+15% (Agent Rec)", value: 2128, confidence: 87, risk: "Balanced risk-return profile based on signal strength" }
          },
          cognitiveProcess: [
            { step: "Scenario Modeling", description: `Generated parallel forecasts at +${percent}% and +15% adjustment levels`, status: "complete" as const },
            { step: "Risk-Return Analysis", description: "Quantified upside capture vs. overstock exposure", status: "complete" as const },
            { step: "Financial Impact Assessment", description: "Calculated revenue and margin implications", status: "complete" as const },
          ],
          contextTags: [
            { source: "Scenario Engine", type: "ml_model" as const, description: "Monte Carlo simulation across demand paths" },
            { source: "Financial Planning", type: "historical" as const, description: "Margin and carrying cost assumptions" },
          ],
          // Chart data for visualization
          chartData: [
            { month: "Feb", historical: 1650, scenario1: Math.round(1750 * (1 + percent / 100) / 1.15), agentRec: 1750 },
            { month: "Mar", historical: 1720, scenario1: Math.round(1800 * (1 + percent / 100) / 1.15), agentRec: 1800 },
            { month: "Apr", historical: 1850, scenario1: Math.round(1820 * (1 + percent / 100) / 1.15), agentRec: 1820 },
            { month: "May", historical: 2100, scenario1: Math.round(2050 * (1 + percent / 100) / 1.15), agentRec: 2050 },
            { month: "Jun", historical: 2050, scenario1: Math.round(2100 * (1 + percent / 100) / 1.15), agentRec: 2100 },
            { month: "Jul (Forecast)", historical: null, scenario1: Math.round(1850 * (1 + percent / 100)), agentRec: 2128 },
          ]
        }]);
        return;
      }

      // PRIORITY 2: Handle explicit edit commands
      if (parsedCommand.type === "edit_adjustment" && parsedCommand.value !== undefined && parsedCommand.mode) {
        const calculatedValue = calculateAdjustedValue(1850, parsedCommand.value, parsedCommand.mode);
        const newWorkflow: EditWorkflowData = {
          step: "adjustmentInput",
          agentRec: 2128,
          currentValue: 1850,
          userAdjustment: calculatedValue,
          adjustmentMode: parsedCommand.mode,
          adjustmentInput: question,
          customerBreakdown: calculateCustomerBreakdown(calculatedValue, false)
        };
        setEditWorkflow(newWorkflow);
        setWorkflowState('adjusting');
        setAgentMessages(prev => [...prev, {
          role: 'agent',
          type: 'edit_workflow',
          content: `Got it! I'll adjust the forecast to ${parsedCommand.mode === 'percent' ? (parsedCommand.value > 0 ? '+' : '') + parsedCommand.value + '%' : calculatedValue + ' units'}.`,
          editWorkflow: newWorkflow
        }]);
        return;
      }
      
      // Handle customer-specific commands
      if (parsedCommand.type === "customer_specific" && parsedCommand.customer && parsedCommand.value !== undefined) {
        const newWorkflow: EditWorkflowData = {
          step: "adjustmentInput",
          agentRec: 2128,
          currentValue: 1850,
          isPinpointMode: true,
          customerBreakdown: calculateCustomerBreakdown(2128, false).map(c => 
            c.name === parsedCommand.customer ? { ...c, userEdit: parsedCommand.value! } : c
          )
        };
        setEditWorkflow(newWorkflow);
        setWorkflowState('adjusting');
        setAgentMessages(prev => [...prev, {
          role: 'agent',
          type: 'edit_workflow',
          content: `Got it! I'll set ${parsedCommand.customer} to ${parsedCommand.value} units. Here's the updated breakdown:`,
          editWorkflow: newWorkflow
        }]);
        return;
      }
      
      // PRIORITY 3: Customer breakdown (check early to avoid conflicts)
      if ((lowerQ.includes('break') && lowerQ.includes('customer')) || lowerQ.includes('breakdown')) {
        const base = editWorkflow?.userAdjustment || 2128;
        setAgentMessages(prev => [...prev, {
          role: 'agent',
          type: 'text',
          content: "Here's how the +15% adjustment breaks down by customer:",
          customerBreakdown: [
            { name: 'Costco', current: 592, adjusted: Math.round(base * 0.32), change: Math.round(base * 0.32) - 592 },
            { name: 'Target', current: 518, adjusted: Math.round(base * 0.28), change: Math.round(base * 0.28) - 518 },
            { name: 'Walmart', current: 463, adjusted: Math.round(base * 0.25), change: Math.round(base * 0.25) - 463 },
            { name: 'Whole Foods', current: 277, adjusted: Math.round(base * 0.15), change: Math.round(base * 0.15) - 277 }
          ],
          cognitiveProcess: [
            { step: "Segmentation Analysis", description: "Decomposed aggregate demand into customer-specific trends", status: "complete" as const },
            { step: "Penetration Modeling", description: "Assessed TikTok demographic overlap by retail channel", status: "complete" as const },
          ],
          contextTags: [
            { source: "Customer Demographics", type: "historical" as const, description: "Costco aligns with TikTok audience (18-34 demo)" },
            { source: "Channel POS Data", type: "user_provided" as const, description: "Real-time sell-through rates by customer" },
          ],
          // Bar chart data for visualization
          customerBreakdownChart: {
            type: "bar" as const,
            data: [
              { customer: "Costco", current: 592, adjusted: Math.round(base * 0.32) },
              { customer: "Target", current: 518, adjusted: Math.round(base * 0.28) },
              { customer: "Walmart", current: 463, adjusted: Math.round(base * 0.25) },
              { customer: "Whole Foods", current: 277, adjusted: Math.round(base * 0.15) },
            ]
          }
        }]);
        return;
      }
      
      // Why +15%? reasoning
      if (lowerQ.includes('why') && (lowerQ.includes('15') || lowerQ.includes('recommend'))) {
        setAgentMessages(prev => [...prev, {
          role: 'agent',
          type: 'text',
          content: "The +15% adjustment is derived from converging signals across multiple analytical dimensions:",
          data: null,
          cognitiveProcess: [
            { step: "Causal Inference", description: "Established TikTok event as primary driver (correlation: 0.89)", status: "complete" as const },
            { step: "Momentum Decomposition", description: "Separated viral spike (47% lift) from baseline trend (8% growth)", status: "complete" as const },
            { step: "Bias Correction", description: "Applied +12% correction for ML systematic under-prediction", status: "complete" as const },
            { step: "Constraint Integration", description: "Factored Walmart inventory capacity (-5% offset)", status: "complete" as const },
            { step: "Scenario Synthesis", description: "Net recommendation: +15% balances upside capture vs. overstock risk", status: "complete" as const },
          ],
          contextTags: [
            { source: "Social Media Analytics", type: "external" as const, description: "2.4M TikTok views, 47% demand correlation" },
            { source: "Customer POS Streams", type: "user_provided" as const, description: "Costco, Target showing sustained lift" },
            { source: "ML Forecast Diagnostics", type: "ml_model" as const, description: "Detected conservative bias in new product ramp" },
          ]
        }]);
      } else if ((lowerQ.includes('12') || lowerQ.includes('what if')) && !lowerQ.includes('edit') && !lowerQ.includes('make')) {
        // Fallback for "what if" queries that didn't go through parser
        setWorkflowState('comparing');
        setAgentMessages(prev => [...prev, {
          role: 'agent',
          type: 'comparison',
          content: 'Comparing +12% vs. +15% scenarios reveals trade-offs in risk-adjusted outcomes:',
          data: null,
          comparisonData: {
            scenario1: { label: "+12%", value: 2072, confidence: 73, risk: "Miss $47K revenue upside if momentum sustains" },
            scenario2: { label: "+15%", value: 2128, confidence: 87, risk: "Carry $12K excess inventory if trend reverses" }
          },
          cognitiveProcess: [
            { step: "Scenario Modeling", description: "Generated parallel forecasts at +12% and +15% adjustment levels", status: "complete" as const },
            { step: "Risk Quantification", description: "Estimated revenue at risk vs. inventory carrying cost", status: "complete" as const },
          ],
          contextTags: [
            { source: "Scenario Engine", type: "ml_model" as const, description: "Monte Carlo simulation across demand paths" },
          ],
          chartData: [
            { month: "Feb", historical: 1650, scenario1: 1648, agentRec: 1750 },
            { month: "Mar", historical: 1720, scenario1: 1750, agentRec: 1800 },
            { month: "Apr", historical: 1850, scenario1: 1770, agentRec: 1820 },
            { month: "May", historical: 2100, scenario1: 1993, agentRec: 2050 },
            { month: "Jun", historical: 2050, scenario1: 2041, agentRec: 2100 },
            { month: "Jul (Forecast)", historical: null, scenario1: 2072, agentRec: 2128 },
          ]
        }]);
      } else if (lowerQ.includes('scenario') || lowerQ.includes('different')) {
        // Show different scenarios
        setAgentMessages(prev => [...prev, {
          role: 'agent',
          type: 'comparison',
          content: 'Here are alternative scenarios to consider:',
          data: null,
          comparisonData: {
            scenario1: { label: "+10%", value: 2035, confidence: 65, risk: "Conservative: May miss upside but limits overstock" },
            scenario2: { label: "+20%", value: 2220, confidence: 72, risk: "Aggressive: Captures full momentum but higher risk" }
          },
          cognitiveProcess: [
            { step: "Scenario Modeling", description: "Generated parallel forecasts across adjustment spectrum", status: "complete" as const },
          ],
          contextTags: [
            { source: "Scenario Engine", type: "ml_model" as const, description: "Risk-adjusted demand projections" },
          ],
          chartData: [
            { month: "Feb", historical: 1650, scenario1: 1600, agentRec: 1750 },
            { month: "Mar", historical: 1720, scenario1: 1700, agentRec: 1800 },
            { month: "Apr", historical: 1850, scenario1: 1750, agentRec: 1820 },
            { month: "May", historical: 2100, scenario1: 1950, agentRec: 2050 },
            { month: "Jun", historical: 2050, scenario1: 2000, agentRec: 2100 },
            { month: "Jul (Forecast)", historical: null, scenario1: 2035, agentRec: 2128 },
          ]
        }]);
      } else if (lowerQ.includes('risk') || lowerQ.includes('reject')) {
        // Risk assessment with distribution visualization
        setAgentMessages(prev => [...prev, {
          role: 'agent',
          type: 'text',
          content: `Here are the key risk factors for the +15% adjustment:`,
          data: null,
          cognitiveProcess: [
            { step: "Risk Assessment", description: "Evaluated overstock risk (8-12% excess inventory if momentum fades)", status: "complete" as const },
            { step: "Supply Chain Validation", description: "Current capacity can support +18% volume increase", status: "complete" as const },
            { step: "Cannibalization Check", description: "Minimal cross-SKU impact detected (<2% substitution)", status: "complete" as const },
          ],
          contextTags: [
            { source: "Inventory Planning", type: "historical" as const, description: "Safety stock levels and carrying costs" },
            { source: "Supply Network", type: "user_provided" as const, description: "Warehouse capacity and distribution constraints" },
          ],
          riskDistribution: {
            upside: {
              label: "Upside Scenario",
              probability: 25,
              impact: "+$75K revenue",
              factors: ["TikTok momentum accelerates", "Competitor stockouts drive share gains"]
            },
            base: {
              label: "Base Case (+15%)",
              probability: 50,
              impact: "$2.1M forecasted",
              factors: ["TikTok effect sustains 3 months", "POS data trends hold"]
            },
            downside: {
              label: "Downside Scenario",
              probability: 25,
              impact: "-$45K excess inventory",
              factors: ["Viral effect decays faster", "Competitor response aggressive"]
            }
          }
        }]);
      } else if (lowerQ.includes('make an edit') || (lowerQ.includes('edit') && !lowerQ.includes('let me'))) {
        // Start agentic edit workflow
        const newWorkflow: EditWorkflowData = {
          step: "adjustmentInput",
          agentRec: 2128,
          currentValue: 1850,
          userAdjustment: 2128, // Default to agent rec
          adjustmentMode: "percent",
          customerBreakdown: calculateCustomerBreakdown(2128, false)
        };
        setEditWorkflow(newWorkflow);
        setWorkflowState('adjusting');
        setAgentMessages(prev => [...prev, {
          role: 'agent',
          type: 'edit_workflow',
          content: "I'll help you adjust this forecast. Here's what I'm proposing:",
          editWorkflow: newWorkflow
        }]);
      } else if (lowerQ.includes('adjust') || lowerQ.includes('change') || lowerQ.includes('let me')) {
        // Open legacy edit panel
        setWorkflowState('adjusting');
        setAgentMessages(prev => [...prev, {
          role: 'agent',
          type: 'edit_panel',
          content: 'I\'ll help you adjust the forecast. You can edit the aggregate number or drill down per customer.',
          data: {
            editMode: 'aggregate',
            customers: []
          }
        }]);
      } else if (lowerQ.includes('apply') || lowerQ.includes('accept')) {
        // Go straight to reasoning form
        setWorkflowState('reasoning');
        setAgentMessages(prev => [...prev, {
          role: 'agent',
          type: 'reasoning_form',
          content: 'Great! Now help me understand your reasoning so I can log this decision properly.',
          data: { adjustmentValue: 15, editMode: 'aggregate' }
        }]);
      } else if (lowerQ.includes('risk') || lowerQ.includes('reject')) {
        // Risk assessment with cognitive framing
        setAgentMessages(prev => [...prev, {
          role: 'agent',
          type: 'text',
          content: `Risk analysis for the +15% adjustment:`,
          data: null,
          cognitiveProcess: [
            { step: "Risk Assessment", description: "Overstock Risk (Medium): 8-12% excess inventory if momentum fades", status: "complete" as const },
            { step: "Supply Chain Validation", description: "Current capacity can support +18% volume increase", status: "complete" as const },
            { step: "Cannibalization Check", description: "Minimal cross-SKU impact detected (<2% substitution)", status: "complete" as const },
          ],
          contextTags: [
            { source: "Inventory Planning", type: "historical" as const, description: "Safety stock levels and carrying costs" },
            { source: "Supply Network", type: "user_provided" as const, description: "Warehouse capacity and distribution constraints" },
          ]
        }]);
      } else if (lowerQ.includes('evidence') || lowerQ.includes('show me')) {
        // Show detailed evidence
        setAgentMessages(prev => [...prev, {
          role: 'agent',
          type: 'text',
          content: "Here's the evidence supporting my recommendation:",
          data: null,
          cognitiveProcess: [
            { step: "Pattern Recognition", description: "TikTok #HydraBoostChallenge drove 47% demand lift in May 2025", status: "complete" as const },
            { step: "Temporal Validation", description: "June sustained at 24,200 units (not one-time spike)", status: "complete" as const },
            { step: "Model Diagnostics", description: "ML forecast underestimated by 12% on similar ramp patterns", status: "complete" as const },
            { step: "Cross-validation", description: "4/4 retail channels confirm above-forecast performance", status: "complete" as const },
          ],
          contextTags: [
            { source: "TikTok Analytics", type: "external" as const, description: "2.4M views, 892K engagements, 47% demand correlation" },
            { source: "Historical Actuals", type: "historical" as const, description: "May 28,500 units → June 24,200 units sustained" },
            { source: "Retailer Feedback", type: "user_provided" as const, description: "All 4 major accounts requesting increased allocation" },
          ]
        }]);
      } else {
        // Generic helpful response
        setAgentMessages(prev => [...prev, {
          role: 'agent',
          type: 'text',
          content: `I can help you explore this recommendation further. Try asking:\n\n• "Why did you recommend +15%?" — See my analytical reasoning\n• "What if we did +12%?" — Compare alternative scenarios\n• "Break down by customer" — View per-customer impact\n• "What's the risk?" — Understand potential downsides\n• "Show me the evidence" — Review supporting data`,
          data: null
        }]);
      }
    }, 400);
  };
  
  // Load appropriate report data based on productLink
  useEffect(() => {
    setReportData(defaultReportData);
  }, [productLink]);
  
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  
  // Edit workflow state
  const [editMode, setEditMode] = useState<'aggregated' | 'pinpoint'>('aggregated');
  const [adjustmentMode, setAdjustmentMode] = useState<'percent' | 'number' | 'overwrite'>('percent');
  const [customerEdits, setCustomerEdits] = useState<Record<string, number>>({});
  const [showCustomerBreakdown, setShowCustomerBreakdown] = useState(false);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [confidence, setConfidence] = useState(75);
  const [reasoning, setReasoning] = useState('');
  const [decisionId, setDecisionId] = useState<string | null>(null);
  const [pendingEdit, setPendingEdit] = useState<{ percent: number; calculations: any[] } | null>(null);
  
  const [expandedSections, setExpandedSections] = useState({
    executiveSummary: true,
    recommendation: true,
    validation: true,
    historicalContext: true,
    riskAssessment: true,
    actions: true,
  });

  // Initialize chat with greeting when chatMode becomes true
  useEffect(() => {
    if (chatMode && messages.length === 0) {
      const greeting = chatScript.initialGreeting.content;
      setMessages([{
        id: '1',
        role: 'agent',
        content: '',
        type: 'recommendation',
        data: greeting
      }]);
    }
  }, [chatMode]);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSendMessage = () => {
    if (!inputValue.trim()) return;
    
    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: inputValue,
      type: 'text'
    };
    
    setMessages(prev => [...prev, userMessage]);
    const input = inputValue.toLowerCase();
    setInputValue('');
    
    // Pattern matching for responses
    setTimeout(() => {
      let agentResponse: ChatMessage;
      
      // Check for "why 15%" question
      if (input.includes('why') && (input.includes('15') || input.includes('recommend'))) {
        const calcData = chatScript.naturalLanguagePatterns.clarification_questions.why_15_percent.response.content;
        agentResponse = {
          id: (Date.now() + 1).toString(),
          role: 'agent',
          content: '',
          type: 'calculation',
          data: calcData
        };
      }
      // Check for "ignore" or "what if" scenario questions
      else if (input.includes('ignore') || input.includes('what if')) {
        const scenarioData = chatScript.naturalLanguagePatterns.clarification_questions.what_if_ignore?.response?.content || {
          summary: "If you ignore this recommendation and keep the current forecast:",
          scenarios: [
            { scenario: "Demand exceeds forecast", impact: "Stockouts in 3 of 4 retail channels", probability: "65%" },
            { scenario: "Lost revenue opportunity", impact: "~$127K in missed sales (Aug-Oct)", probability: "High" },
            { scenario: "Customer satisfaction", impact: "Reduced fill rates, potential delistings", probability: "Medium" }
          ],
          agentNote: "I understand the hesitation. These projections are based on similar pattern matches, but you know your market better than my models."
        };
        agentResponse = {
          id: (Date.now() + 1).toString(),
          role: 'agent',
          content: '',
          type: 'scenario_analysis',
          data: scenarioData
        };
      }
      // Check for percentage modification (e.g., "make it 12%", "change to 12%")
      else if (input.match(/(\d+)%/) || input.match(/(\d+)\s*percent/)) {
        const match = input.match(/(\d+)/);
        const percent = match ? parseInt(match[1]) : 12;
        showEditPreviewForPercent(percent);
        return;
      }
      // Check for "show me the data" or "walk me through" - show finding card
      else if (input.includes('show me') || input.includes('walk me through') || input.includes('explain') || input.includes('analysis')) {
        agentResponse = {
          id: (Date.now() + 1).toString(),
          role: 'agent',
          content: '',
          type: 'finding',
          data: {
            findingNumber: 1,
            title: "Viral Event Created New Baseline",
            subtitle: "May 2025 TikTok Spike Analysis",
            confidence: "HIGH" as const,
            metric: {
              value: "+47%",
              label: "spike in May",
              from: 1845,
              to: 2715,
              unit: "units"
            },
            explanations: [
              "In May 2025, a TikTok viral event drove demand to <span class='font-semibold font-mono'>2,715</span> units—a 47% spike above April.",
              "But here's what's important: <span class='font-semibold'>June stayed at 2,640</span>. This wasn't a one-time spike—it's a new plateau."
            ],
            evidence: [
              { type: 'data_source' as const, label: "Data Source", value: "Actuals from Forecast Table (May-Jun 2025)" },
              { type: 'calculation' as const, label: "Calculation", value: "(2715 - 1845) / 1845 = 0.47 = +47%" },
              { type: 'confidence' as const, label: "Confidence Rationale", value: "HIGH: Direct measurement from actuals, no estimation involved" }
            ],
            nextFinding: {
              label: "Ready for Finding #2?",
              title: "Next: ML Forecast Analysis"
            },
            actions: {
              primary: { label: "View in Forecast Table", action: "view_forecast_table" },
              secondary: { label: "Challenge this finding", action: "challenge" }
            }
          }
        };
      }
      // Check for "modify" or "change" intent
      else if (input.includes('modify') || input.includes('change') || input.includes('adjust')) {
        agentResponse = {
          id: (Date.now() + 1).toString(),
          role: 'agent',
          content: '',
          type: 'modify_options',
          data: chatScript.intentResponses.modify_recommendation.content
        };
      }
      // Check for customer-specific requests
      else if (input.includes('customer') || input.includes('costco') || input.includes('target') || input.includes('walmart')) {
        showCustomerBreakdownMessage();
        return;
      }
      // Default response
      else {
        agentResponse = {
          id: (Date.now() + 1).toString(),
          role: 'agent',
          content: "I understand. Could you tell me more about what you'd like to adjust? You can:\n• Say \"walk me through\" to see my detailed analysis\n• Specify a different percentage (e.g., \"make it 12%\")\n• Ask about specific customers\n• Say \"what if I ignore this\" to see impact scenarios",
          type: 'text'
        };
      }
      
      setMessages(prev => [...prev, agentResponse]);
    }, 500);
  };

  const handleQuickAction = (action: string) => {
    setInputValue('');
    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: action,
      type: 'text'
    };
    setMessages(prev => [...prev, userMessage]);

    setTimeout(() => {
      let agentResponse: ChatMessage;
      
      if (action === 'Why this forecast?') {
        const calcData = chatScript.naturalLanguagePatterns.clarification_questions.why_15_percent.response.content;
        agentResponse = {
          id: (Date.now() + 1).toString(),
          role: 'agent',
          content: '',
          type: 'calculation',
          data: calcData
        };
      } else if (action === 'Show me the data' || action === 'Walk me through') {
        // Show finding card for detailed analysis
        agentResponse = {
          id: (Date.now() + 1).toString(),
          role: 'agent',
          content: '',
          type: 'finding',
          data: {
            findingNumber: 1,
            title: "Viral Event Created New Baseline",
            subtitle: "May 2025 TikTok Spike Analysis",
            confidence: "HIGH" as const,
            metric: {
              value: "+47%",
              label: "spike in May",
              from: 1845,
              to: 2715,
              unit: "units"
            },
            explanations: [
              "In May 2025, a TikTok viral event drove demand to <span class='font-semibold font-mono'>2,715</span> units—a 47% spike above April.",
              "But here's what's important: <span class='font-semibold'>June stayed at 2,640</span>. This wasn't a one-time spike—it's a new plateau."
            ],
            evidence: [
              { type: 'data_source' as const, label: "Data Source", value: "Actuals from Forecast Table (May-Jun 2025)" },
              { type: 'calculation' as const, label: "Calculation", value: "(2715 - 1845) / 1845 = 0.47 = +47%" },
              { type: 'confidence' as const, label: "Confidence Rationale", value: "HIGH: Direct measurement from actuals, no estimation involved" }
            ],
            nextFinding: {
              label: "Ready for Finding #2?",
              title: "Next: ML Forecast Analysis"
            },
            actions: {
              primary: { label: "View in Forecast Table", action: "view_forecast_table" },
              secondary: { label: "Challenge this finding", action: "challenge" }
            }
          }
        };
      } else if (action === 'Make it higher') {
        showEditPreviewForPercent(18);
        return;
      } else if (action === 'Make it lower') {
        showEditPreviewForPercent(10);
        return;
      } else if (action === 'Apply this edit') {
        handleApplyClick();
        return;
      } else {
        agentResponse = {
          id: (Date.now() + 1).toString(),
          role: 'agent',
          content: "I understand. How can I help you with this forecast?",
          type: 'text'
        };
      }
      
      setMessages(prev => [...prev, agentResponse]);
    }, 500);
  };

  const showEditPreviewForPercent = (percent: number) => {
    const baseData = chatScript.metadata.baseRecommendation.originalForecast;
    const multiplier = 1 + (percent / 100);
    
    const calculations = [
      { month: 'Aug', original: baseData.Aug, adjusted: Math.round(baseData.Aug * multiplier), diff: Math.round(baseData.Aug * multiplier) - baseData.Aug },
      { month: 'Sep', original: baseData.Sep, adjusted: Math.round(baseData.Sep * multiplier), diff: Math.round(baseData.Sep * multiplier) - baseData.Sep },
      { month: 'Oct', original: baseData.Oct, adjusted: Math.round(baseData.Oct * multiplier), diff: Math.round(baseData.Oct * multiplier) - baseData.Oct }
    ];
    
    const customerBreakdownData = Object.entries(CUSTOMERS).map(([name, data]) => ({
      customer: name,
      weight: data.weight,
      original: data.original,
      adjusted: Math.round(data.original * multiplier),
      diff: Math.round(data.original * multiplier) - data.original
    }));
    
    setPendingEdit({ percent, calculations });
    
    const agentResponse: ChatMessage = {
      id: (Date.now() + 1).toString(),
      role: 'agent',
      content: '',
      type: 'edit_preview',
      data: {
        percent,
        calculations,
        customerBreakdown: customerBreakdownData
      }
    };
    
    setMessages(prev => [...prev, agentResponse]);
  };

  const showCustomerBreakdownMessage = () => {
    const customerData = Object.entries(CUSTOMERS).map(([name, data]) => ({
      customer: name,
      weight: `${(data.weight * 100).toFixed(0)}%`,
      original: data.original,
      recommended: Math.round(data.original * 1.15),
      diff: Math.round(data.original * 0.15)
    }));
    
    const agentResponse: ChatMessage = {
      id: (Date.now() + 1).toString(),
      role: 'agent',
      content: '',
      type: 'customer_breakdown',
      data: {
        title: "Customer-Level Breakdown",
        description: "Here's how the 15% increase would affect each customer:",
        customers: customerData,
        editPrompt: "Would you like to adjust specific customers differently? Just tell me which one."
      }
    };
    
    setMessages(prev => [...prev, agentResponse]);
  };

  const handleApplyEditWithReasoning = () => {
    if (!pendingEdit) return;
    
    // Show reasoning form
    const agentResponse: ChatMessage = {
      id: (Date.now() + 1).toString(),
      role: 'agent',
      content: '',
      type: 'reasoning_form',
      data: {
        title: "Document Your Reasoning",
        description: `Before I apply the ${pendingEdit.percent}% adjustment, let's capture why you're making this change.`,
        suggestedReasoning: `Adjusting forecast by ${pendingEdit.percent}% based on...`
      }
    };
    
    setMessages(prev => [...prev, agentResponse]);
  };

  const handleSubmitReasoning = () => {
    if (!pendingEdit || selectedTags.length === 0) return;
    
    // Generate decision ID
    const newDecisionId = `FC-${Date.now().toString(36).toUpperCase()}`;
    setDecisionId(newDecisionId);
    
    // Add user reasoning message
    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: `Reasoning: ${selectedTags.map(t => REASON_TAG_GROUPS.flatMap(g => g.items).find(i => i.code === t)?.label).join(', ')}. Confidence: ${confidence}%. ${reasoning}`,
      type: 'text'
    };
    
    // Generate confirmation message
    const totalOriginal = pendingEdit.calculations.reduce((sum, c) => sum + c.original, 0);
    const totalAdjusted = pendingEdit.calculations.reduce((sum, c) => sum + c.adjusted, 0);
    
    const confirmationResponse: ChatMessage = {
      id: (Date.now() + 1).toString(),
      role: 'agent',
      content: '',
      type: 'confirmation',
      data: {
        decisionId: newDecisionId,
        timestamp: new Date().toISOString(),
        summary: {
          adjustment: `+${pendingEdit.percent}%`,
          periods: "Aug-Oct 2025",
          totalChange: `${totalOriginal.toLocaleString()} → ${totalAdjusted.toLocaleString()} (+${(totalAdjusted - totalOriginal).toLocaleString()} units)`
        },
        auditTrail: {
          reasonTags: selectedTags,
          confidence: confidence,
          notes: reasoning,
          reviewer: "Current User"
        },
        dataProvenance: {
          agentVersion: chatScript.metadata.modelId,
          baseRecommendation: "15%",
          userOverride: `${pendingEdit.percent}%`,
          source: chatScript.metadata.agentId
        }
      }
    };
    
    setMessages(prev => [...prev, userMessage, confirmationResponse]);
    
    // Reset form state
    setSelectedTags([]);
    setConfidence(75);
    setReasoning('');
    setPendingEdit(null);
  };


  const handleModifyClick = () => {
    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: 'I want to modify this recommendation',
      type: 'text'
    };
    
    const agentResponse: ChatMessage = {
      id: (Date.now() + 1).toString(),
      role: 'agent',
      content: '',
      type: 'modify_options',
      data: chatScript.intentResponses.modify_recommendation.content
    };
    
    setMessages(prev => [...prev, userMessage, agentResponse]);
  };

  const handleApplyClick = () => {
    if (productLink && onUpdateStatus) {
      onUpdateStatus(productLink, "Submitted");
    }
    onClose();
    navigate('/');
  };

  const handleShowMoreClick = () => {
    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: 'Show me more details',
      type: 'text'
    };
    
    const calcData = chatScript.intentResponses.request_details.content;
    const agentResponse: ChatMessage = {
      id: (Date.now() + 1).toString(),
      role: 'agent',
      content: '',
      type: 'calculation',
      data: calcData
    };
    
    setMessages(prev => [...prev, userMessage, agentResponse]);
  };

  const toggleSection = (section: keyof typeof expandedSections) => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }));
  };

  const handleDownloadPDF = () => {
    // Expand all sections before printing
    setExpandedSections({
      executiveSummary: true,
      recommendation: true,
      validation: true,
      historicalContext: true,
      riskAssessment: true,
      actions: true,
    });

    // Wait a bit for sections to expand, then trigger print
    setTimeout(() => {
      window.print();
    }, 300);
  };

  // Prepare chart data for Recommendation section bar chart (Historical Actuals, ML Forecast, Agent Recommendation)
  const recommendationChartData = reportData.recommendationAndIntervention.comparisonData.months.map((month, idx) => ({
    month,
    "Historical Actuals": reportData.recommendationAndIntervention.comparisonData.historicalActuals[idx],
    "ML Forecast": reportData.recommendationAndIntervention.comparisonData.mlForecast[idx],
    "Agent Recommendation": reportData.recommendationAndIntervention.comparisonData.agentRecommendation[idx],
  }));

  // Prepare data for treatment rationale line chart (Original ML vs Agent Adjusted)
  const treatmentRationaleChartData = reportData.treatmentRationale.visualData.months.map((month, idx) => ({
    month,
    "Original ML Forecast": reportData.treatmentRationale.visualData.originalMLForecast[idx],
    "Agent Adjusted": reportData.treatmentRationale.visualData.agentAdjusted[idx],
  }));

  // Prepare data for demand history line chart
  const demandHistoryData = reportData.demandHistoryChart.periods.map((period, idx) => ({
    period,
    Actual: reportData.demandHistoryChart.actualValues[idx],
    Forecast: reportData.demandHistoryChart.forecastValues[idx],
  }));

  const getConfidenceBadgeColor = (score: number) => {
    if (score >= 80) return "primary3";
    if (score >= 60) return "warning3";
    return "destructive3";
  };

  const getRiskBadgeColor = (severity: string) => {
    if (severity === "High") return "destructive2";
    if (severity === "Medium") return "warning2";
    return "primary2";
  };

  return (
    <Sheet open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <SheetContent side="right" className="w-full sm:max-w-4xl overflow-y-auto p-0">
        {/* Header */}
        <div className="sticky top-0 z-10 bg-slate-100 border-b px-6 py-4">
          <div className="flex items-start justify-between mb-3">
            <div className="flex-1">
              <h2 className="text-xl font-semibold text-foreground">
                {reportData.metadata.reportTitle}
              </h2>
            </div>
            <Button variant="ghost" size="icon" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>
          {!chatMode && !agentMode ? (
            // REPORT MODE: Show all action buttons
            <div className="flex items-center justify-between w-full">
              {/* Left: Export (only in report mode) */}
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={handleDownloadPDF}>
                  <Download className="h-4 w-4 mr-1" />
                  Export
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="border-blue-300 bg-blue-50 text-blue-700 hover:bg-blue-100 hover:border-blue-400"
                  onClick={() => {
                    const id = skuId || 1;
                    if (dataParam) {
                      navigate(`/forecast-workflow/${id}?data=${dataParam}&from=drawer`);
                    } else {
                      navigate(`/forecast-workflow/${id}?from=drawer`);
                    }
                  }}
                >
                  <ChartLine className="h-4 w-4 mr-1" />
                  Analyze Myself
                </Button>
              </div>

              {/* Right: Primary actions */}
              <div className="flex items-center gap-2">
                <Button 
                  className="bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 text-white gap-2 shadow-md"
                  onClick={initializeAgentMode}
                >
                  <Sparkles className="h-4 w-4" />
                  Work with Agent
                </Button>
                {!hideActionButtons && (
                  <Button
                    variant="default"
                    onClick={() => {
                      if (productLink && onUpdateStatus) {
                        onUpdateStatus(productLink, "Submitted");
                      }
                      onClose();
                      navigate('/');
                    }}
                  >
                    <CheckCircle className="h-4 w-4 mr-1" />
                    Accept
                  </Button>
                )}
              </div>
            </div>
          ) : agentMode ? (
            // AGENT MODE: Minimal controls with green branding
            <div className="flex items-center justify-between w-full">
              <Button 
                variant="ghost" 
                size="sm"
                onClick={() => setAgentMode(false)}
                className="text-slate-600 hover:text-slate-900 text-xs"
              >
                <ChevronLeft className="h-4 w-4 mr-1" />
                View Full Report
              </Button>
              <div className="flex items-center gap-2">
                {!hideActionButtons && (
                  <Button
                    size="sm"
                    className="bg-emerald-600 hover:bg-emerald-700 text-white"
                    onClick={() => {
                      if (productLink && onUpdateStatus) {
                        onUpdateStatus(productLink, "Submitted");
                      }
                      onClose();
                      navigate('/');
                    }}
                  >
                    <CheckCircle className="h-4 w-4 mr-1" />
                    Accept
                  </Button>
                )}
              </div>
            </div>
          ) : (
            // CHAT MODE: Minimal controls
            <div className="flex items-center gap-2">
              <Button 
                variant="outline" 
                size="sm"
                onClick={() => setShowReportInChat(!showReportInChat)}
              >
                <FileText className="h-4 w-4 mr-2" />
                {showReportInChat ? "Hide" : "Show"} Report Summary
              </Button>
              <Button 
                variant="ghost" 
                size="sm"
                onClick={() => setChatMode(false)}
              >
                <ChevronLeft className="h-4 w-4 mr-2" />
                Back to Full Report
              </Button>
            </div>
          )}
        </div>

        {/* Content - Conditional rendering based on chatMode and agentMode */}
        <div className="transition-all duration-300">
          {agentMode ? (
            /* Agent Mode View - Compact intelligent workspace with full editing */
            <div className="flex flex-col h-[calc(100vh-200px)]">
              {/* Conversation Area - Scrollable */}
              <div 
                ref={agentChatContainerRef}
                className="flex-1 overflow-y-auto p-4 space-y-4"
              >
                {agentMessages.map((msg, idx) => (
                  <div key={idx}>
                    {msg.role === 'agent' && msg.type === 'recommendation' && (
                      /* COMPACT Recommendation Card with Cognitive Process */
                      <CompactRecommendationCard
                        recommendation={msg.content || msg.data?.recommendation || "Increase forecast by +15% (1,850 → 2,128 units)"}
                        confidenceScore={msg.data?.confidence?.score || 87}
                        whyConfident={msg.data?.whyConfident || []}
                        whyUncertain={msg.data?.whyUncertain || []}
                        cognitiveProcess={msg.cognitiveProcess}
                        contextTags={msg.contextTags}
                        onApply={() => handleAgentQuestion("Apply this recommendation")}
                        onShowMore={() => handleAgentQuestion("Why did you recommend +15%?")}
                      />
                    )}

                    {msg.role === 'agent' && msg.type === 'text' && (
                      /* Agent Text Response with Cognitive Process and Context Tags */
                      <div className="flex gap-2">
                        <div className="flex-shrink-0">
                          <div className="w-6 h-6 rounded-full bg-slate-100 flex items-center justify-center">
                            <div className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                          </div>
                        </div>
                        <div className="flex-1 space-y-2">
                          <Card className="border border-slate-200">
                            <CardContent className="p-2.5 space-y-2">
                              <p className="text-[13px] whitespace-pre-line text-slate-900 leading-snug">{msg.content}</p>
                              
                              {/* Customer Breakdown Table - inline rendering */}
                              {msg.customerBreakdown && (
                                <div className="pt-1.5 border-t border-slate-100">
                                  <table className="w-full text-[11px]">
                                    <thead>
                                      <tr className="border-b border-slate-200">
                                        <th className="text-left py-1 font-medium text-slate-600">Customer</th>
                                        <th className="text-right py-1 font-medium text-slate-600">Current</th>
                                        <th className="text-right py-1 font-medium text-slate-600">Adj</th>
                                        <th className="text-right py-1 font-medium text-slate-600">Δ</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {msg.customerBreakdown.map((customer, cIdx) => (
                                        <tr key={cIdx} className="border-b border-slate-100 last:border-0">
                                          <td className="py-1 font-medium text-slate-900">{customer.name}</td>
                                          <td className="text-right py-1 text-slate-600">{customer.current}</td>
                                          <td className="text-right py-1 text-slate-900">{customer.adjusted}</td>
                                          <td className={`text-right py-1 font-medium ${
                                            customer.change >= 0 ? 'text-emerald-700' : 'text-red-700'
                                          }`}>
                                            {customer.change >= 0 ? '+' : ''}{customer.change}
                                          </td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              )}
                              
                              {/* Customer Breakdown Bar Chart */}
                              {msg.customerBreakdownChart && (
                                <div className="pt-1.5 border-t border-slate-100">
                                  <p className="text-[11px] font-medium text-slate-600 mb-1">Visual Comparison:</p>
                                  <ResponsiveContainer width="100%" height={120}>
                                    <BarChart data={msg.customerBreakdownChart.data}>
                                      <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" vertical={false} />
                                      <XAxis dataKey="customer" tick={{ fontSize: 9 }} stroke="#94A3B8" />
                                      <YAxis tick={{ fontSize: 9 }} stroke="#94A3B8" />
                                      <Tooltip contentStyle={{ fontSize: "11px", padding: "4px 8px" }} />
                                      <Bar dataKey="current" fill="#CBD5E1" name="Current" />
                                      <Bar dataKey="adjusted" fill="#10B981" name="Adjusted" />
                                    </BarChart>
                                  </ResponsiveContainer>
                                </div>
                              )}
                              
                              {/* Risk Distribution Visualization */}
                              {msg.riskDistribution && (
                                <div className="pt-1.5 border-t border-slate-100 space-y-1.5">
                                  <p className="text-[11px] font-medium text-slate-600">Risk Distribution:</p>
                                  <div className="flex h-7 rounded overflow-hidden border border-slate-200">
                                    <div 
                                      className="bg-emerald-100 flex items-center justify-center text-[10px] font-medium text-emerald-700"
                                      style={{ width: `${msg.riskDistribution.upside.probability}%` }}
                                    >
                                      {msg.riskDistribution.upside.probability}%
                                    </div>
                                    <div 
                                      className="bg-blue-100 flex items-center justify-center text-[10px] font-medium text-blue-700"
                                      style={{ width: `${msg.riskDistribution.base.probability}%` }}
                                    >
                                      {msg.riskDistribution.base.probability}%
                                    </div>
                                    <div 
                                      className="bg-amber-100 flex items-center justify-center text-[10px] font-medium text-amber-700"
                                      style={{ width: `${msg.riskDistribution.downside.probability}%` }}
                                    >
                                      {msg.riskDistribution.downside.probability}%
                                    </div>
                                  </div>

                                  {/* Risk details - compact with functional colors */}
                                  <div className="grid grid-cols-3 gap-1.5 text-[10px]">
                                    <div className="bg-emerald-50 rounded p-1.5 border border-emerald-200">
                                      <p className="font-medium text-emerald-900 mb-0.5">
                                        {msg.riskDistribution.upside.label}
                                      </p>
                                      <p className="text-emerald-700 mb-0.5">
                                        {msg.riskDistribution.upside.impact}
                                      </p>
                                      <ul className="space-y-0 text-emerald-600">
                                        {msg.riskDistribution.upside.factors.slice(0, 2).map((f, i) => (
                                          <li key={i}>• {f}</li>
                                        ))}
                                      </ul>
                                    </div>

                                    <div className="bg-blue-50 rounded p-1.5 border border-blue-200">
                                      <p className="font-medium text-blue-900 mb-0.5">
                                        {msg.riskDistribution.base.label}
                                      </p>
                                      <p className="text-blue-700 mb-0.5">
                                        {msg.riskDistribution.base.impact}
                                      </p>
                                      <ul className="space-y-0 text-blue-600">
                                        {msg.riskDistribution.base.factors.slice(0, 2).map((f, i) => (
                                          <li key={i}>• {f}</li>
                                        ))}
                                      </ul>
                                    </div>

                                    <div className="bg-amber-50 rounded p-1.5 border border-amber-200">
                                      <p className="font-medium text-amber-900 mb-0.5">
                                        {msg.riskDistribution.downside.label}
                                      </p>
                                      <p className="text-amber-700 mb-0.5">
                                        {msg.riskDistribution.downside.impact}
                                      </p>
                                      <ul className="space-y-0 text-amber-600">
                                        {msg.riskDistribution.downside.factors.slice(0, 2).map((f, i) => (
                                          <li key={i}>• {f}</li>
                                        ))}
                                      </ul>
                                    </div>
                                  </div>
                                </div>
                              )}
                              
                              {/* Cognitive Process View */}
                              {msg.cognitiveProcess && msg.cognitiveProcess.length > 0 && (
                                <CognitiveProcessView processes={msg.cognitiveProcess} />
                              )}
                              
                              {/* Legacy calculation breakdown */}
                              {msg.data?.calculationBreakdown && (
                                <div className="space-y-1 bg-slate-50 rounded-lg p-2">
                                  {msg.data.calculationBreakdown.map((item: string, i: number) => (
                                    <p key={i} className="text-xs text-slate-600 font-mono">{item}</p>
                                  ))}
                                </div>
                              )}
                              
                              {/* Context Tags */}
                              {msg.contextTags && msg.contextTags.length > 0 && (
                                <ContextTags tags={msg.contextTags} />
                              )}
                            </CardContent>
                          </Card>
                        </div>
                      </div>
                    )}

                    {msg.role === 'agent' && msg.type === 'comparison' && (
                      /* Comparison Card with Cognitive Process */
                      <div className="space-y-2">
                        <Card className="border border-slate-200">
                          <CardContent className="p-2.5 space-y-2">
                            <p className="text-[13px] font-medium text-slate-900">{msg.content}</p>
                            
                            {/* New comparison data format */}
                            {msg.comparisonData && (
                              <div className="grid grid-cols-2 gap-2">
                                <div className="p-2 rounded border border-slate-200 bg-white">
                                  <span className="font-mono font-semibold text-[14px]">{msg.comparisonData.scenario1.label}</span>
                                  <div className="space-y-0.5 text-[11px] text-slate-600 mt-1.5">
                                    <p className="flex justify-between">
                                      <span>Forecast:</span>
                                      <span className="font-medium text-slate-900">{msg.comparisonData.scenario1.value.toLocaleString()}</span>
                                    </p>
                                    <p className="flex justify-between">
                                      <span>Confidence:</span>
                                      <span className="font-medium">{msg.comparisonData.scenario1.confidence}%</span>
                                    </p>
                                    <p className="text-slate-500 mt-1 text-[10px] leading-tight">{msg.comparisonData.scenario1.risk}</p>
                                  </div>
                                </div>
                                {/* Emerald background + styling for recommended scenario */}
                                <div className="p-2 rounded border border-emerald-200 bg-emerald-50/30">
                                  <div className="flex items-center gap-1 mb-1.5">
                                    <div className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                                    <span className="font-mono font-semibold text-[14px] text-slate-900">
                                      {msg.comparisonData.scenario2.label.replace(" (Agent Rec)", "")}
                                    </span>
                                    <span className="text-[10px] text-emerald-600 font-medium">REC</span>
                                  </div>
                                  <div className="space-y-0.5 text-[11px] text-slate-600">
                                    <p className="flex justify-between">
                                      <span>Forecast:</span>
                                      <span className="font-semibold text-emerald-900">{msg.comparisonData.scenario2.value.toLocaleString()}</span>
                                    </p>
                                    <p className="flex justify-between">
                                      <span>Confidence:</span>
                                      <Badge className="bg-emerald-600 text-white text-[10px] font-medium px-1 py-0">
                                        {msg.comparisonData.scenario2.confidence}%
                                      </Badge>
                                    </p>
                                    <p className="text-emerald-800 mt-1 text-[10px] leading-tight">{msg.comparisonData.scenario2.risk}</p>
                                  </div>
                                </div>
                              </div>
                            )}
                            
                            {/* Legacy scenarios format */}
                            {msg.data?.scenarios && (
                              <>
                                <div className="grid grid-cols-2 gap-3">
                                  {msg.data.scenarios.map((scenario: any, i: number) => (
                                    <div key={i} className={`p-3 rounded-lg border ${scenario.recommended ? 'border-emerald-400 bg-emerald-50' : 'border-slate-200 bg-white'}`}>
                                      <div className="flex items-center gap-2 mb-2">
                                        <span className="font-mono font-bold text-lg">{scenario.adjustment}</span>
                                        {scenario.recommended && <Badge className="bg-emerald-100 text-emerald-700 text-[10px]">Recommended</Badge>}
                                      </div>
                                      <div className="space-y-1 text-xs text-slate-600">
                                        <p className="flex justify-between"><span>New forecast:</span><span className="font-mono font-medium">{scenario.newForecast}</span></p>
                                        <p className="flex justify-between"><span>Confidence:</span><span className="font-medium">{scenario.confidence}%</span></p>
                                        <p className="text-slate-500 mt-1.5 italic">{scenario.tradeoff}</p>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                                <div className="flex gap-2">
                                  <Button size="sm" variant="outline" className="text-xs" onClick={() => { setAgentAdjustmentValue(msg.data.scenarios[0].value); setWorkflowState('reasoning'); setAgentMessages(prev => [...prev, { role: 'agent', type: 'reasoning_form', content: 'Great! Now help me understand your reasoning.', data: { adjustmentValue: msg.data.scenarios[0].value, editMode: 'aggregate' } }]); }}>Apply {msg.data.scenarios[0].adjustment}</Button>
                                  <Button size="sm" className="bg-emerald-600 hover:bg-emerald-700 text-white text-xs" onClick={() => { setAgentAdjustmentValue(msg.data.scenarios[1].value); setWorkflowState('reasoning'); setAgentMessages(prev => [...prev, { role: 'agent', type: 'reasoning_form', content: 'Great! Now help me understand your reasoning.', data: { adjustmentValue: msg.data.scenarios[1].value, editMode: 'aggregate' } }]); }}>Apply {msg.data.scenarios[1].adjustment}</Button>
                                </div>
                              </>
                            )}
                            
                            {/* Scenario Comparison Chart */}
                            {msg.chartData && (
                              <div className="pt-1.5 border-t border-slate-100">
                                <p className="text-[11px] font-medium text-slate-600 mb-1">Forecast Comparison:</p>
                                <ResponsiveContainer width="100%" height={120}>
                                  <LineChart data={msg.chartData}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" vertical={false} />
                                    <XAxis dataKey="month" tick={{ fontSize: 9 }} stroke="#94A3B8" />
                                    <YAxis tick={{ fontSize: 9 }} domain={[1500, 2300]} stroke="#94A3B8" />
                                    <Tooltip contentStyle={{ fontSize: "11px", padding: "4px 8px" }} />
                                    <Line 
                                      type="monotone" 
                                      dataKey="historical" 
                                      stroke="#94A3B8" 
                                      strokeWidth={1.5} 
                                      name="Historical"
                                      connectNulls={false}
                                      dot={false}
                                    />
                                    <Line 
                                      type="monotone" 
                                      dataKey="scenario1" 
                                      stroke="#6366F1" 
                                      strokeWidth={1.5} 
                                      strokeDasharray="3 3" 
                                      name={msg.comparisonData?.scenario1?.label || "Scenario"}
                                      dot={false}
                                    />
                                    <Line 
                                      type="monotone" 
                                      dataKey="agentRec" 
                                      stroke="#10B981" 
                                      strokeWidth={2} 
                                      name="Agent Rec" 
                                    />
                                  </LineChart>
                                </ResponsiveContainer>
                              </div>
                            )}
                            
                            {/* Cognitive Process */}
                            {msg.cognitiveProcess && msg.cognitiveProcess.length > 0 && (
                              <CognitiveProcessView processes={msg.cognitiveProcess} />
                            )}
                            
                            {/* Context Tags */}
                            {msg.contextTags && msg.contextTags.length > 0 && (
                              <ContextTags tags={msg.contextTags} />
                            )}
                          </CardContent>
                        </Card>
                      </div>
                    )}

                    {msg.role === 'agent' && msg.type === 'customer_breakdown' && (
                      /* Customer Breakdown Table with Edit Option */
                      <Card className="border-emerald-200">
                        <CardContent className="p-4 space-y-3">
                          <div className="flex items-center justify-between">
                            <p className="text-sm font-semibold text-slate-800">Customer-Level Impact</p>
                            <Button
                              size="sm"
                              variant="outline"
                              className="text-xs border-emerald-300 text-emerald-700"
                              onClick={() => {
                                setAgentEditMode('pinpoint');
                                setWorkflowState('adjusting');
                                setAgentMessages(prev => [...prev, {
                                  role: 'agent',
                                  type: 'edit_panel',
                                  content: 'You can now adjust each customer individually. Make your changes and I\'ll apply them.',
                                  data: { 
                                    editMode: 'pinpoint',
                                    customers: msg.data.customers 
                                  }
                                }]);
                              }}
                            >
                              <Edit2 className="h-3 w-3 mr-1" />
                              Edit per Customer
                            </Button>
                          </div>
                          <div className="rounded-lg border overflow-hidden">
                            <Table>
                              <TableHeader>
                                <TableRow className="bg-slate-50">
                                  <TableHead className="text-xs py-2">Customer</TableHead>
                                  <TableHead className="text-xs py-2 text-right">Current</TableHead>
                                  <TableHead className="text-xs py-2 text-right">Adjusted</TableHead>
                                  <TableHead className="text-xs py-2 text-right">Change</TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {msg.data.customers.map((customer: any, i: number) => (
                                  <TableRow key={i}>
                                    <TableCell className="text-xs py-2 font-medium">{customer.name}</TableCell>
                                    <TableCell className="text-xs py-2 text-right font-mono">{customer.current}</TableCell>
                                    <TableCell className="text-xs py-2 text-right font-mono text-emerald-600">
                                      {customer.adjusted}
                                    </TableCell>
                                    <TableCell className="text-xs py-2 text-right font-mono text-emerald-500">
                                      +{customer.change}
                                    </TableCell>
                                  </TableRow>
                                ))}
                              </TableBody>
                            </Table>
                          </div>
                          <p className="text-xs text-slate-500 italic">{msg.data.insight}</p>
                        </CardContent>
                      </Card>
                    )}

                    {msg.role === 'agent' && msg.type === 'edit_panel' && (
                      /* Interactive Edit Panel */
                      <Card className="border-2 border-blue-300 bg-gradient-to-br from-blue-50 to-indigo-50">
                        <CardContent className="p-4 space-y-4">
                          <div className="flex items-center gap-2">
                            <Edit3 className="h-4 w-4 text-blue-600" />
                            <span className="text-sm font-semibold text-slate-800">
                              {msg.data.editMode === 'pinpoint' ? 'Edit Per Customer' : 'Edit Aggregate Forecast'}
                            </span>
                          </div>

                          {msg.data.editMode === 'aggregate' ? (
                            /* Aggregate Editing */
                            <div className="space-y-4">
                              {/* Mode Toggle */}
                              <div className="flex gap-2">
                                <Button
                                  size="sm"
                                  variant={agentAdjustmentMode === 'percent' ? 'default' : 'outline'}
                                  onClick={() => setAgentAdjustmentMode('percent')}
                                  className="text-xs"
                                >
                                  Percentage
                                </Button>
                                <Button
                                  size="sm"
                                  variant={agentAdjustmentMode === 'units' ? 'default' : 'outline'}
                                  onClick={() => setAgentAdjustmentMode('units')}
                                  className="text-xs"
                                >
                                  Units
                                </Button>
                              </div>

                              {/* Adjustment Input */}
                              <div className="space-y-2">
                                <label className="text-xs font-medium text-slate-700">
                                  {agentAdjustmentMode === 'percent' ? 'Adjustment %' : 'New Total Units'}
                                </label>
                                <div className="flex items-center gap-2">
                                  <Input
                                    type="number"
                                    value={agentAdjustmentValue}
                                    onChange={(e) => setAgentAdjustmentValue(Number(e.target.value))}
                                    className="w-32 text-center font-mono text-base"
                                  />
                                  <span className="text-slate-600 text-sm">
                                    {agentAdjustmentMode === 'percent' ? '%' : 'units'}
                                  </span>
                                  {agentAdjustmentMode === 'percent' && (
                                    <div className="flex gap-1">
                                      <button
                                        onClick={() => setAgentAdjustmentValue(agentAdjustmentValue + 2)}
                                        className="text-xs px-2 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium"
                                      >
                                        +2%
                                      </button>
                                      <button
                                        onClick={() => setAgentAdjustmentValue(agentAdjustmentValue + 5)}
                                        className="text-xs px-2 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium"
                                      >
                                        +5%
                                      </button>
                                      <button
                                        onClick={() => setAgentAdjustmentValue(agentAdjustmentValue - 2)}
                                        className="text-xs px-2 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium"
                                      >
                                        -2%
                                      </button>
                                      <button
                                        onClick={() => setAgentAdjustmentValue(agentAdjustmentValue - 5)}
                                        className="text-xs px-2 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium"
                                      >
                                        -5%
                                      </button>
                                    </div>
                                  )}
                                </div>
                              </div>

                              {/* Preview */}
                              <div className="bg-white rounded-lg p-3 border border-blue-200">
                                <p className="text-xs font-medium text-slate-700 mb-2">Preview Impact</p>
                                <div className="flex justify-between text-sm">
                                  <span className="text-slate-600">New forecast:</span>
                                  <span className="font-mono font-semibold text-blue-600">
                                    {agentAdjustmentMode === 'percent' 
                                      ? Math.round(1850 * (1 + agentAdjustmentValue / 100))
                                      : agentAdjustmentValue
                                    } units
                                  </span>
                                </div>
                                <div className="flex justify-between text-sm mt-1">
                                  <span className="text-slate-600">vs Current:</span>
                                  <span className={`font-mono font-semibold ${agentAdjustmentValue >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                                    {agentAdjustmentMode === 'percent'
                                      ? `${agentAdjustmentValue > 0 ? '+' : ''}${agentAdjustmentValue}%`
                                      : `${agentAdjustmentValue - 1850 > 0 ? '+' : ''}${agentAdjustmentValue - 1850} units`
                                    }
                                  </span>
                                </div>
                              </div>

                              <Button
                                size="sm"
                                variant="outline"
                                className="w-full text-xs"
                                onClick={() => handleAgentQuestion("show customer breakdown")}
                              >
                                Show Customer Breakdown
                              </Button>

                              <Button
                                className="w-full bg-blue-600 hover:bg-blue-700 text-white"
                                onClick={() => {
                                  setWorkflowState('reasoning');
                                  setAgentMessages(prev => [...prev, {
                                    role: 'agent',
                                    type: 'reasoning_form',
                                    content: 'Great! Now help me understand your reasoning so I can log this decision properly.',
                                    data: { 
                                      adjustmentValue: agentAdjustmentMode === 'percent' 
                                        ? agentAdjustmentValue 
                                        : Math.round(((agentAdjustmentValue - 1850) / 1850) * 100),
                                      editMode: 'aggregate' 
                                    }
                                  }]);
                                }}
                              >
                                Looks Good, Next Step
                              </Button>
                            </div>
                          ) : (
                            /* Per-Customer Editing */
                            <div className="space-y-3">
                              <p className="text-xs text-slate-600">Adjust each customer's forecast individually:</p>
                              
                              <div className="space-y-2">
                                {['Costco', 'Target', 'Walmart', 'Whole Foods'].map((customer, idx) => {
                                  const baseValues = [592, 518, 463, 277];
                                  const base = baseValues[idx];
                                  return (
                                    <div key={customer} className="flex items-center justify-between bg-white p-2 rounded-lg border">
                                      <div className="flex-1">
                                        <span className="text-xs font-medium text-slate-800">{customer}</span>
                                        <span className="text-[10px] text-slate-500 ml-2">Base: {base} units</span>
                                      </div>
                                      <div className="flex items-center gap-2">
                                        <Input
                                          type="number"
                                          value={customerAdjustments[customer]}
                                          onChange={(e) => setCustomerAdjustments(prev => ({
                                            ...prev,
                                            [customer]: Number(e.target.value)
                                          }))}
                                          className="w-24 text-center font-mono text-sm"
                                        />
                                        <span className="text-xs text-slate-600">%</span>
                                        <div className="flex gap-1">
                                          <button
                                            onClick={() => setCustomerAdjustments(prev => ({
                                              ...prev,
                                              [customer]: prev[customer] + 2
                                            }))}
                                            className="text-xs px-1.5 py-0.5 rounded bg-slate-100 hover:bg-slate-200"
                                          >
                                            +2
                                          </button>
                                          <button
                                            onClick={() => setCustomerAdjustments(prev => ({
                                              ...prev,
                                              [customer]: prev[customer] - 2
                                            }))}
                                            className="text-xs px-1.5 py-0.5 rounded bg-slate-100 hover:bg-slate-200"
                                          >
                                            -2
                                          </button>
                                        </div>
                                        <span className="text-xs font-mono text-emerald-600 w-16 text-right">
                                          → {Math.round(base * (1 + customerAdjustments[customer] / 100))} units
                                        </span>
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>

                              {/* Total Preview */}
                              <div className="bg-white rounded-lg p-3 border border-blue-200">
                                <div className="flex justify-between text-sm">
                                  <span className="font-medium text-slate-700">Total New Forecast:</span>
                                  <span className="font-mono font-bold text-blue-600">
                                    {Math.round(
                                      592 * (1 + customerAdjustments['Costco'] / 100) +
                                      518 * (1 + customerAdjustments['Target'] / 100) +
                                      463 * (1 + customerAdjustments['Walmart'] / 100) +
                                      277 * (1 + customerAdjustments['Whole Foods'] / 100)
                                    )} units
                                  </span>
                                </div>
                              </div>

                              <Button
                                className="w-full bg-blue-600 hover:bg-blue-700 text-white"
                                onClick={() => {
                                  const totalNew = Math.round(
                                    592 * (1 + customerAdjustments['Costco'] / 100) +
                                    518 * (1 + customerAdjustments['Target'] / 100) +
                                    463 * (1 + customerAdjustments['Walmart'] / 100) +
                                    277 * (1 + customerAdjustments['Whole Foods'] / 100)
                                  );
                                  const avgAdjustment = Math.round(((totalNew - 1850) / 1850) * 100);
                                  
                                  setWorkflowState('reasoning');
                                  setAgentMessages(prev => [...prev, {
                                    role: 'agent',
                                    type: 'reasoning_form',
                                    content: 'Great! Now help me understand your reasoning so I can log this decision properly.',
                                    data: { 
                                      adjustmentValue: avgAdjustment,
                                      editMode: 'pinpoint',
                                      customerBreakdown: customerAdjustments
                                    }
                                  }]);
                                }}
                              >
                                Looks Good, Next Step
                              </Button>
                            </div>
                          )}
                        </CardContent>
                      </Card>
                    )}

                    {msg.role === 'agent' && msg.type === 'edit_workflow' && msg.editWorkflow && (
                      /* Agentic Edit Workflow Card */
                      <EditWorkflowCard
                        workflow={msg.editWorkflow}
                        onWorkflowUpdate={(updatedWorkflow) => {
                          setEditWorkflow(updatedWorkflow);
                          // Update the message with new workflow state
                          setAgentMessages(prev => prev.map((m, i) => 
                            i === prev.length - 1 && m.type === 'edit_workflow' 
                              ? { ...m, editWorkflow: updatedWorkflow }
                              : m
                          ));
                        }}
                        onComplete={(finalWorkflow) => {
                          setWorkflowState('confirming');
                          // Add completion message with verification links
                          setAgentMessages(prev => [...prev, {
                            role: 'agent',
                            type: 'text',
                            content: '✅ Edit confirmed and saved!\n\nYour adjustment has been captured in the decision log and will improve future recommendations.'
                          }, {
                            role: 'agent',
                            type: 'edit_workflow',
                            content: '',
                            editWorkflow: { ...finalWorkflow, step: 'complete' }
                          }]);
                        }}
                        onShowBreakdown={() => {
                          // Show customer breakdown as new message
                          const totalValue = editWorkflow?.userAdjustment || 2128;
                          setAgentMessages(prev => [...prev, {
                            role: 'agent',
                            type: 'customer_breakdown',
                            content: "Here's how your adjustment breaks down by customer:",
                            customerBreakdown: [
                              { name: 'Costco', current: 592, adjusted: Math.round(totalValue * 0.32), change: Math.round(totalValue * 0.32) - 592 },
                              { name: 'Target', current: 518, adjusted: Math.round(totalValue * 0.28), change: Math.round(totalValue * 0.28) - 518 },
                              { name: 'Walmart', current: 463, adjusted: Math.round(totalValue * 0.25), change: Math.round(totalValue * 0.25) - 463 },
                              { name: 'Whole Foods', current: 277, adjusted: Math.round(totalValue * 0.15), change: Math.round(totalValue * 0.15) - 277 }
                            ],
                            contextTags: [
                              { source: "Customer Demographics", type: "historical" as const, description: "Costco aligns with TikTok audience (18-34 demo)" },
                              { source: "Channel POS Data", type: "user_provided" as const, description: "Real-time sell-through rates by customer" },
                            ]
                          }]);
                        }}
                        onAdvanceStep={(newStep, data) => {
                          // CONVERSATIONAL FLOW: Each step adds NEW agent message
                          const updatedWorkflow: EditWorkflowData = { 
                            ...editWorkflow!, 
                            ...data, 
                            step: newStep as EditWorkflowData['step']
                          };
                          setEditWorkflow(updatedWorkflow);
                          
                          // Generate appropriate agent message for each step
                          let agentContent = "";
                          switch (newStep) {
                            case "explainLearning":
                              const delta = (data.userAdjustment || updatedWorkflow.userAdjustment || 0) - updatedWorkflow.agentRec;
                              const deltaPercent = ((delta / updatedWorkflow.agentRec) * 100).toFixed(1);
                              agentContent = `Got it — ${data.adjustmentInput || 'your adjustment'} gives us ${(data.userAdjustment || updatedWorkflow.userAdjustment || 0).toLocaleString()} units (${delta >= 0 ? '+' : ''}${delta} units vs my recommendation).\n\nBefore we save this, I want to learn from your thinking so I can improve future recommendations. Can I ask you a few quick questions?`;
                              break;
                            case "contextTags":
                              agentContent = `What drove your decision to adjust?\n\nI'm asking because different factors have different reliability patterns. Pick 1-3 tags that best explain your thinking:`;
                              break;
                            case "confidence":
                              agentContent = `Thanks! Now — how confident are you in this adjustment?\n\nThis helps me calibrate how much weight to give your overrides.`;
                              break;
                            case "reasoning":
                              agentContent = `Last question — can you explain your thinking in a sentence or two?\n\nThis is the most valuable input you can give me.`;
                              break;
                            case "confirmation":
                              agentContent = `Perfect! Here's what I learned from you:`;
                              break;
                            case "processing":
                              agentContent = `✅ Decision confirmed! Here's what I'm doing now:`;
                              break;
                          }
                          
                          // Add new agent message with the step's card
                          setAgentMessages(prev => [...prev, {
                            role: 'agent' as const,
                            type: 'edit_workflow',
                            content: agentContent,
                            editWorkflow: updatedWorkflow
                          }]);
                        }}
                        skuId={skuId || 1}
                      />
                    )}

                    {msg.role === 'agent' && msg.type === 'reasoning_form' && (
                      /* Reasoning Form */
                      <Card className="border-2 border-amber-300 bg-gradient-to-br from-amber-50 to-yellow-50">
                        <CardContent className="p-4 space-y-4">
                          <div className="flex items-center gap-2">
                            <FileCheck className="h-4 w-4 text-amber-600" />
                            <span className="text-sm font-semibold text-slate-800">
                              {msg.content}
                            </span>
                          </div>

                          {/* Adjustment Summary */}
                          <div className="bg-white rounded-lg p-3 border border-amber-200">
                            <div className="flex justify-between text-sm">
                              <span className="text-slate-600">Adjustment:</span>
                              <span className="font-mono font-bold text-emerald-600">
                                {msg.data.adjustmentValue > 0 ? '+' : ''}{msg.data.adjustmentValue}%
                              </span>
                            </div>
                            <div className="flex justify-between text-sm mt-1">
                              <span className="text-slate-600">New forecast:</span>
                              <span className="font-mono font-semibold">
                                {Math.round(1850 * (1 + msg.data.adjustmentValue / 100))} units
                              </span>
                            </div>
                            {msg.data.editMode === 'pinpoint' && (
                              <p className="text-xs text-amber-600 mt-2 italic">
                                Per-customer adjustments applied
                              </p>
                            )}
                          </div>

                          {/* Reasoning Input */}
                          <div className="space-y-2">
                            <label className="text-xs font-medium text-slate-700">
                              Why are you making this adjustment? *
                            </label>
                            <Textarea
                              placeholder="e.g., Based on retail partner feedback and Q4 promotional calendar..."
                              value={agentAdjustmentReason}
                              onChange={(e) => setAgentAdjustmentReason(e.target.value)}
                              className="min-h-[80px] text-sm"
                            />
                          </div>

                          {/* Apply Button */}
                          <Button
                            className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-semibold"
                            disabled={!agentAdjustmentReason.trim()}
                            onClick={() => {
                              setWorkflowState('confirming');
                              setAgentMessages(prev => [...prev, 
                                { role: 'user', type: 'text', content: agentAdjustmentReason },
                                {
                                  role: 'agent',
                                  type: 'text',
                                  content: `Perfect! I've applied your ${msg.data.adjustmentValue > 0 ? '+' : ''}${msg.data.adjustmentValue}% adjustment${msg.data.editMode === 'pinpoint' ? ' with per-customer breakdown' : ''} with the reasoning: "${agentAdjustmentReason}"\n\nThis change has been logged in the decision trail. You can now:\n• View it in the Forecast Table\n• Check the Decision Log\n• Download the full audit trail`,
                                  data: null
                                }
                              ]);
                              setAgentAdjustmentReason('');
                            }}
                          >
                            <Check className="h-4 w-4 mr-2" />
                            Have Me Apply This
                          </Button>
                        </CardContent>
                      </Card>
                    )}

                    {msg.role === 'user' && (
                      /* User Message */
                      <div className="flex gap-3 justify-end">
                        <div className="bg-slate-100 border border-slate-200 rounded-lg p-3 max-w-[80%]">
                          <p className="text-sm text-slate-800">{msg.content}</p>
                        </div>
                        <div className="flex-shrink-0">
                          <div className="w-7 h-7 rounded-full bg-slate-300 flex items-center justify-center">
                            <span className="text-xs font-semibold text-slate-700">You</span>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {/* Chat Input Area - Fixed at Bottom, No Wasted Space */}
              <div className="border-t bg-white p-4 space-y-3">
                {/* Input Field */}
                <div className="flex items-center gap-2">
                  <Input
                    placeholder="Ask me anything..."
                    value={agentUserInput}
                    onChange={(e) => setAgentUserInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && agentUserInput.trim()) {
                        handleAgentQuestion(agentUserInput);
                        setAgentUserInput('');
                      }
                    }}
                    className="flex-1 border-emerald-300 focus:border-emerald-500 focus:ring-emerald-500 text-sm"
                  />
                  <Button
                    size="sm"
                    onClick={() => {
                      if (agentUserInput.trim()) {
                        handleAgentQuestion(agentUserInput);
                        setAgentUserInput('');
                      }
                    }}
                    className="bg-emerald-600 hover:bg-emerald-700 text-white"
                  >
                    <Send className="h-3.5 w-3.5" />
                  </Button>
                </div>

                {/* Preset Questions - ALWAYS VISIBLE (not just in exploring state) */}
                <div className="flex flex-wrap gap-1.5">
                  {QUICK_ACTIONS.map((action, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleAgentQuestion(action)}
                      className="text-xs px-2.5 py-1 rounded-full bg-slate-50 border border-slate-200 text-slate-700 hover:bg-slate-100 font-medium transition-colors"
                    >
                      {action}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : chatMode ? (
            /* Chat Mode View */
            <div className="flex flex-col h-[calc(100vh-200px)]">
              {/* Collapsible Report Summary */}
              {showReportInChat && (
                <Card className="mx-4 mt-4 border-primary/20">
                  <CardHeader className="py-3 px-4">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-sm font-medium">Report Summary</CardTitle>
                      <Button 
                        variant="ghost" 
                        size="sm"
                        onClick={() => setShowReportInChat(false)}
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent className="py-3 px-4">
                    <div className="grid grid-cols-3 gap-4 mb-3">
                      <div>
                        <p className="text-xs text-muted-foreground">Recommendation</p>
                        <p className="text-sm font-semibold text-primary">+15% Aug-Oct</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Confidence</p>
                        <p className="text-sm font-semibold">{reportData.executiveSummary.confidenceScore}%</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Validation</p>
                        <p className="text-sm font-semibold">12/14 Passed</p>
                      </div>
                    </div>
                    <p className="text-xs text-muted-foreground line-clamp-2">
                      {reportData.executiveSummary.summaryText}
                    </p>
                  </CardContent>
                </Card>
              )}
              
              {/* Chat Messages Area */}
              <ScrollArea className="flex-1 p-4">
                <div className="space-y-4">
                  {messages.map((message) => (
                    <div key={message.id} className={`flex gap-3 ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                      {message.role === 'agent' && (
                        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-primary/20 to-primary/10 flex items-center justify-center">
                          <Sparkles className="h-4 w-4 text-primary" />
                        </div>
                      )}
                      <div className={`max-w-[85%] ${message.role === 'user' ? 'bg-primary text-primary-foreground rounded-2xl rounded-tr-sm px-4 py-2' : ''}`}>
                        {message.role === 'user' ? (
                          <p className="text-sm">{message.content}</p>
                        ) : message.type === 'recommendation' ? (
                          <Card className="border-primary/20 shadow-sm">
                            <CardContent className="p-4 space-y-4">
                              <div className="flex items-center gap-2">
                                <h4 className="font-semibold text-base">{message.data.recommendation}</h4>
                                <Badge variant="warning3">{message.data.confidence.score}% {message.data.confidence.badge}</Badge>
                              </div>
                              <div className="grid grid-cols-2 gap-4">
                                <div className="space-y-2">
                                  <h5 className="text-sm font-medium flex items-center gap-1">
                                    <CheckCircle className="h-4 w-4 text-primary" />
                                    Why I'm Confident
                                  </h5>
                                  <ul className="text-sm text-muted-foreground space-y-1">
                                    {message.data.whyConfident.map((item: string, idx: number) => (
                                      <li key={idx} className="flex items-start gap-2">
                                        <span className="text-primary mt-1">•</span>
                                        <span>{item}</span>
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                                <div className="space-y-2">
                                  <h5 className="text-sm font-medium flex items-center gap-1">
                                    <AlertCircle className="h-4 w-4 text-warning" />
                                    Why I'm Uncertain
                                  </h5>
                                  <ul className="text-sm text-muted-foreground space-y-1">
                                    {message.data.whyUncertain.map((item: string, idx: number) => (
                                      <li key={idx} className="flex items-start gap-2">
                                        <span className="text-warning mt-1">•</span>
                                        <span>{item}</span>
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              </div>
                              <div className="flex gap-2 pt-2">
                                <Button size="sm" onClick={handleApplyClick}>Apply This</Button>
                                <Button size="sm" variant="secondary" onClick={handleModifyClick}>Modify It</Button>
                                <Button size="sm" variant="outline" onClick={handleShowMoreClick}>Show Me More</Button>
                              </div>
                            </CardContent>
                          </Card>
                        ) : message.type === 'calculation' ? (
                          <Card className="border-muted">
                            <CardContent className="p-4 space-y-3">
                              <p className="text-sm font-medium">{message.data.summary}</p>
                              {message.data.breakdown && (
                                <div className="space-y-2">
                                  {message.data.breakdown.map((item: any, idx: number) => (
                                    <div key={idx} className="flex items-center justify-between bg-muted/50 rounded px-3 py-2">
                                      <span className="text-sm">{item.component}</span>
                                      <div className="text-right">
                                        <span className="font-mono font-medium">{item.value}</span>
                                        <p className="text-xs text-muted-foreground">{item.rationale}</p>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              )}
                              {message.data.layeredExplanation && (
                                <div className="space-y-2 text-sm">
                                  <p><strong>I see:</strong> {message.data.layeredExplanation.iSee}</p>
                                  <p><strong>I think:</strong> {message.data.layeredExplanation.iThink}</p>
                                  <p><strong>I recommend:</strong> {message.data.layeredExplanation.iRecommend}</p>
                                  <p className="text-muted-foreground italic">{message.data.layeredExplanation.butYouDecide}</p>
                                </div>
                              )}
                              {message.data.transparencyNote && (
                                <p className="text-xs text-muted-foreground italic border-t pt-2">{message.data.transparencyNote}</p>
                              )}
                            </CardContent>
                          </Card>
                        ) : message.type === 'modify_options' ? (
                          <Card className="border-muted">
                            <CardContent className="p-4 space-y-3">
                              <p className="text-sm font-medium">{message.data.question}</p>
                              <p className="text-xs text-muted-foreground italic">{message.data.humanDeferenceLanguage}</p>
                              <div className="grid grid-cols-3 gap-2">
                                {message.data.structuredOptions.map((option: any, idx: number) => (
                                  <Button key={idx} variant="outline" size="sm" className="h-auto py-2 flex flex-col">
                                    <span className="font-medium">{option.label}</span>
                                    <span className="text-xs text-muted-foreground">{option.description}</span>
                                  </Button>
                                ))}
                              </div>
                              <p className="text-xs text-muted-foreground">{message.data.naturalLanguagePrompt}</p>
                            </CardContent>
                          </Card>
                        ) : message.type === 'edit_preview' ? (
                          <Card className="border-primary/20">
                            <CardContent className="p-4 space-y-3">
                              <div className="flex items-center gap-2">
                                <Calculator className="h-4 w-4 text-primary" />
                                <h4 className="font-medium">Preview: +{message.data.percent}% Adjustment</h4>
                                <Badge variant="outline">Draft</Badge>
                              </div>
                              <Table>
                                <TableHeader>
                                  <TableRow>
                                    <TableHead>Month</TableHead>
                                    <TableHead className="text-right">Original</TableHead>
                                    <TableHead className="text-right">Adjusted</TableHead>
                                    <TableHead className="text-right">Change</TableHead>
                                  </TableRow>
                                </TableHeader>
                                <TableBody>
                                  {message.data.calculations.map((calc: any) => (
                                    <TableRow key={calc.month}>
                                      <TableCell className="font-medium">{calc.month}</TableCell>
                                      <TableCell className="text-right">{calc.original.toLocaleString()}</TableCell>
                                      <TableCell className="text-right font-medium text-primary">{calc.adjusted.toLocaleString()}</TableCell>
                                      <TableCell className="text-right text-primary">+{calc.diff}</TableCell>
                                    </TableRow>
                                  ))}
                                </TableBody>
                              </Table>
                              
                              {/* Customer Breakdown Toggle */}
                              {message.data.customerBreakdown && (
                                <div className="border-t pt-3">
                                  <Button 
                                    variant="ghost" 
                                    size="sm" 
                                    onClick={() => setShowCustomerBreakdown(!showCustomerBreakdown)}
                                    className="w-full justify-between"
                                  >
                                    <span className="flex items-center gap-2">
                                      <Users className="h-4 w-4" />
                                      Customer Breakdown
                                    </span>
                                    {showCustomerBreakdown ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                                  </Button>
                                  {showCustomerBreakdown && (
                                    <Table className="mt-2">
                                      <TableHeader>
                                        <TableRow>
                                          <TableHead>Customer</TableHead>
                                          <TableHead className="text-right">Weight</TableHead>
                                          <TableHead className="text-right">Original</TableHead>
                                          <TableHead className="text-right">Adjusted</TableHead>
                                        </TableRow>
                                      </TableHeader>
                                      <TableBody>
                                        {message.data.customerBreakdown.map((cust: any) => (
                                          <TableRow key={cust.customer}>
                                            <TableCell className="font-medium">{cust.customer}</TableCell>
                                            <TableCell className="text-right text-muted-foreground">{(cust.weight * 100).toFixed(0)}%</TableCell>
                                            <TableCell className="text-right">{cust.original.toLocaleString()}</TableCell>
                                            <TableCell className="text-right text-primary">{cust.adjusted.toLocaleString()}</TableCell>
                                          </TableRow>
                                        ))}
                                      </TableBody>
                                    </Table>
                                  )}
                                </div>
                              )}
                              
                              <div className="flex gap-2">
                                <Button size="sm" onClick={handleApplyEditWithReasoning}>
                                  <FileCheck className="h-4 w-4 mr-1" />
                                  Apply & Document
                                </Button>
                                <Button size="sm" variant="outline" onClick={() => setInputValue(`make it ${message.data.percent + 2}%`)}>
                                  Adjust Further
                                </Button>
                              </div>
                            </CardContent>
                          </Card>
                        ) : message.type === 'scenario_analysis' ? (
                          <Card className="border-warning/30 bg-warning/5">
                            <CardContent className="p-4 space-y-3">
                              <div className="flex items-center gap-2">
                                <AlertTriangle className="h-4 w-4 text-warning" />
                                <h4 className="font-medium">Scenario Analysis</h4>
                              </div>
                              <p className="text-sm">{message.data.summary}</p>
                              <div className="space-y-2">
                                {message.data.scenarios.map((scenario: any, idx: number) => (
                                  <div key={idx} className="bg-background rounded-lg p-3 border">
                                    <div className="flex justify-between items-start">
                                      <div>
                                        <p className="text-sm font-medium">{scenario.scenario}</p>
                                        <p className="text-xs text-muted-foreground">{scenario.impact}</p>
                                      </div>
                                      <Badge variant="outline" className="text-xs">{scenario.probability}</Badge>
                                    </div>
                                  </div>
                                ))}
                              </div>
                              <p className="text-xs text-muted-foreground italic border-t pt-2">{message.data.agentNote}</p>
                            </CardContent>
                          </Card>
                        ) : message.type === 'customer_breakdown' ? (
                          <Card className="border-muted">
                            <CardContent className="p-4 space-y-3">
                              <div className="flex items-center gap-2">
                                <Users className="h-4 w-4 text-primary" />
                                <h4 className="font-medium">{message.data.title}</h4>
                              </div>
                              <p className="text-sm text-muted-foreground">{message.data.description}</p>
                              <Table>
                                <TableHeader>
                                  <TableRow>
                                    <TableHead>Customer</TableHead>
                                    <TableHead className="text-right">Weight</TableHead>
                                    <TableHead className="text-right">Current</TableHead>
                                    <TableHead className="text-right">Recommended</TableHead>
                                  </TableRow>
                                </TableHeader>
                                <TableBody>
                                  {message.data.customers.map((cust: any) => (
                                    <TableRow key={cust.customer}>
                                      <TableCell className="font-medium">{cust.customer}</TableCell>
                                      <TableCell className="text-right text-muted-foreground">{cust.weight}</TableCell>
                                      <TableCell className="text-right">{cust.original.toLocaleString()}</TableCell>
                                      <TableCell className="text-right text-primary">{cust.recommended.toLocaleString()}</TableCell>
                                    </TableRow>
                                  ))}
                                </TableBody>
                              </Table>
                              <p className="text-xs text-muted-foreground">{message.data.editPrompt}</p>
                            </CardContent>
                          </Card>
                        ) : message.type === 'reasoning_form' ? (
                          <Card className="border-primary/20">
                            <CardContent className="p-4 space-y-4">
                              <div className="flex items-center gap-2">
                                <FileCheck className="h-4 w-4 text-primary" />
                                <h4 className="font-medium">{message.data.title}</h4>
                              </div>
                              <p className="text-sm text-muted-foreground">{message.data.description}</p>
                              
                              {/* Reason Tags */}
                              <div className="space-y-3">
                                <p className="text-sm font-medium">Select reasons for this change:</p>
                                {REASON_TAG_GROUPS.map((group) => (
                                  <div key={group.group} className="space-y-1">
                                    <p className="text-xs text-muted-foreground">{group.group}</p>
                                    <div className="flex flex-wrap gap-1">
                                      {group.items.map((item) => (
                                        <Badge
                                          key={item.code}
                                          variant={selectedTags.includes(item.code) ? "default" : "outline"}
                                          className="cursor-pointer transition-colors"
                                          onClick={() => {
                                            setSelectedTags(prev => 
                                              prev.includes(item.code) 
                                                ? prev.filter(t => t !== item.code)
                                                : [...prev, item.code]
                                            );
                                          }}
                                        >
                                          {item.label}
                                        </Badge>
                                      ))}
                                    </div>
                                  </div>
                                ))}
                              </div>
                              
                              {/* Confidence Slider */}
                              <div className="space-y-2">
                                <div className="flex justify-between items-center">
                                  <p className="text-sm font-medium">Your confidence in this adjustment</p>
                                  <Badge variant={confidence >= 75 ? "primary3" : confidence >= 50 ? "warning3" : "destructive3"}>
                                    {confidence}%
                                  </Badge>
                                </div>
                                <Slider
                                  value={[confidence]}
                                  onValueChange={(value) => setConfidence(value[0])}
                                  min={0}
                                  max={100}
                                  step={5}
                                  className="w-full"
                                />
                              </div>
                              
                              {/* Reasoning Text */}
                              <div className="space-y-2">
                                <p className="text-sm font-medium">Additional notes (optional)</p>
                                <Textarea
                                  placeholder={message.data.suggestedReasoning}
                                  value={reasoning}
                                  onChange={(e) => setReasoning(e.target.value)}
                                  className="min-h-[80px]"
                                />
                              </div>
                              
                              <Button 
                                onClick={handleSubmitReasoning}
                                disabled={selectedTags.length === 0}
                                className="w-full"
                              >
                                Submit Edit with Reasoning
                              </Button>
                              {selectedTags.length === 0 && (
                                <p className="text-xs text-muted-foreground text-center">Select at least one reason tag to continue</p>
                              )}
                            </CardContent>
                          </Card>
                        ) : message.type === 'confirmation' ? (
                          <Card className="border-primary bg-primary/5">
                            <CardContent className="p-4 space-y-4">
                              <div className="flex items-center gap-2">
                                <CheckCircle className="h-5 w-5 text-primary" />
                                <h4 className="font-medium text-primary">Edit Applied Successfully</h4>
                              </div>
                              
                              {/* Decision Summary */}
                              <div className="bg-background rounded-lg p-3 border space-y-2">
                                <div className="flex justify-between text-sm">
                                  <span className="text-muted-foreground">Decision ID</span>
                                  <span className="font-mono font-medium">{message.data.decisionId}</span>
                                </div>
                                <div className="flex justify-between text-sm">
                                  <span className="text-muted-foreground">Adjustment</span>
                                  <span className="font-medium text-primary">{message.data.summary.adjustment}</span>
                                </div>
                                <div className="flex justify-between text-sm">
                                  <span className="text-muted-foreground">Periods</span>
                                  <span>{message.data.summary.periods}</span>
                                </div>
                                <div className="flex justify-between text-sm">
                                  <span className="text-muted-foreground">Total Impact</span>
                                  <span className="font-medium">{message.data.summary.totalChange}</span>
                                </div>
                              </div>
                              
                              {/* Audit Trail */}
                              <div className="space-y-2">
                                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Audit Trail</p>
                                <div className="bg-background rounded-lg p-3 border text-sm space-y-1">
                                  <div className="flex gap-2">
                                    <span className="text-muted-foreground">Reasons:</span>
                                    <span>{message.data.auditTrail.reasonTags.map((t: string) => 
                                      REASON_TAG_GROUPS.flatMap(g => g.items).find(i => i.code === t)?.label
                                    ).join(', ')}</span>
                                  </div>
                                  <div className="flex gap-2">
                                    <span className="text-muted-foreground">Confidence:</span>
                                    <span>{message.data.auditTrail.confidence}%</span>
                                  </div>
                                  {message.data.auditTrail.notes && (
                                    <div className="flex gap-2">
                                      <span className="text-muted-foreground">Notes:</span>
                                      <span>{message.data.auditTrail.notes}</span>
                                    </div>
                                  )}
                                </div>
                              </div>
                              
                              {/* Data Provenance */}
                              <div className="space-y-2">
                                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Data Provenance</p>
                                <div className="bg-background rounded-lg p-3 border text-xs space-y-1 font-mono">
                                  <div>Agent: {message.data.dataProvenance.source}</div>
                                  <div>Model: {message.data.dataProvenance.agentVersion}</div>
                                  <div>Base Rec: {message.data.dataProvenance.baseRecommendation} → Override: {message.data.dataProvenance.userOverride}</div>
                                  <div>Timestamp: {new Date(message.data.timestamp).toLocaleString()}</div>
                                </div>
                              </div>
                              
                              <Button onClick={handleApplyClick} className="w-full">
                                Close & Return to Dashboard
                              </Button>
                            </CardContent>
                          </Card>
                        ) : message.type === 'finding' ? (
                          <FindingCard 
                            data={message.data} 
                            onAction={(action) => {
                              if (action === 'view_forecast_table') {
                                const id = skuId || 1;
                                if (dataParam) {
                                  navigate(`/forecast-review/${id}?data=${dataParam}`);
                                } else {
                                  navigate(`/forecast-review/${id}`);
                                }
                              } else if (action === 'challenge') {
                                setInputValue('I want to challenge this finding');
                              }
                            }}
                            onNext={() => {
                              // Add the next finding when user clicks Next
                              const nextFindingMessage: ChatMessage = {
                                id: (Date.now() + 1).toString(),
                                role: 'agent',
                                content: '',
                                type: 'finding',
                                data: {
                                  findingNumber: message.data.findingNumber + 1,
                                  title: "ML Forecast Conservative Bias",
                                  subtitle: "Statistical Model Analysis",
                                  confidence: "MEDIUM" as const,
                                  metric: {
                                    value: "-8.2%",
                                    label: "underforecast vs actuals",
                                    from: "18,450",
                                    to: "16,940",
                                    unit: "units"
                                  },
                                  explanations: [
                                    "The ML model has <span class='font-semibold'>systematically underforecast</span> by an average of 8.2% over the past 6 months.",
                                    "This conservative bias is expected for new products, but it's creating a <span class='font-semibold'>gap between supply and demand</span>."
                                  ],
                                  evidence: [
                                    { type: 'data_source' as const, label: "Data Source", value: "6-month MAPE analysis (Jan-Jun 2025)" },
                                    { type: 'calculation' as const, label: "Calculation", value: "Avg((Actual - Forecast) / Actual) = -8.2%" },
                                    { type: 'confidence' as const, label: "Confidence Rationale", value: "MEDIUM: Statistical measure with limited sample size" }
                                  ],
                                  nextFinding: {
                                    label: "Ready for Finding #3?",
                                    title: "Next: Recommendation Synthesis"
                                  },
                                  actions: {
                                    primary: { label: "View ML Performance", action: "view_ml_performance" },
                                    secondary: { label: "Challenge this finding", action: "challenge" }
                                  }
                                }
                              };
                              setMessages(prev => [...prev, nextFindingMessage]);
                            }}
                          />
                        ) : (
                          <Card className="border-muted">
                            <CardContent className="p-3">
                              <p className="text-sm whitespace-pre-line">{message.content}</p>
                            </CardContent>
                          </Card>
                        )}
                      </div>
                      {message.role === 'user' && (
                        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary flex items-center justify-center">
                          <User className="h-4 w-4 text-primary-foreground" />
                        </div>
                      )}
                    </div>
                  ))}
                  <div ref={messagesEndRef} />
                </div>
              </ScrollArea>
              
              {/* Fixed Input Area */}
              <div className="p-4 border-t bg-background space-y-3">
                {/* Quick Actions */}
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs text-muted-foreground">Quick:</span>
                  <Button 
                    variant="outline" 
                    size="sm" 
                    className="h-7 text-xs"
                    onClick={() => handleQuickAction('Why this forecast?')}
                  >
                    Why this forecast?
                  </Button>
                  <Button 
                    variant="outline" 
                    size="sm" 
                    className="h-7 text-xs bg-blue-50 border-blue-200 text-blue-700 hover:bg-blue-100"
                    onClick={() => handleQuickAction('Walk me through')}
                  >
                    Walk me through
                  </Button>
                  <Button 
                    variant="outline" 
                    size="sm" 
                    className="h-7 text-xs"
                    onClick={() => handleQuickAction('Make it higher')}
                  >
                    Make it higher
                  </Button>
                  <Button 
                    variant="outline" 
                    size="sm" 
                    className="h-7 text-xs"
                    onClick={() => handleQuickAction('Make it lower')}
                  >
                    Make it lower
                  </Button>
                  <Button 
                    variant="outline" 
                    size="sm" 
                    className="h-7 text-xs bg-primary/5"
                    onClick={() => handleQuickAction('Apply this edit')}
                  >
                    Apply this edit
                  </Button>
                </div>
                
                {/* Input with Textarea */}
                <div className="flex gap-2 items-end">
                  <div className="flex-1">
                    <Textarea
                      value={inputValue}
                      onChange={(e) => setInputValue(e.target.value)}
                      placeholder="Ask a question or give an instruction..."
                      className="min-h-[44px] max-h-[120px] resize-none rounded-xl border-muted focus:border-primary focus:ring-1 focus:ring-primary"
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault();
                          handleSendMessage();
                        }
                      }}
                    />
                    <p className="text-xs text-muted-foreground mt-1 px-2">
                      Press Enter to send, Shift+Enter for new line
                    </p>
                  </div>
                  <Button 
                    size="lg"
                    className="h-[44px] w-[44px] rounded-full p-0 flex-shrink-0"
                    disabled={!inputValue.trim()}
                    onClick={handleSendMessage}
                  >
                    <Send className="h-5 w-5" />
                  </Button>
                </div>
              </div>
            </div>
          ) : isLoadingVersionedReport ? (
            /* Loading Skeleton - Shows while data is loading */
            <div className="flex items-center justify-center h-64">
              <div className="flex flex-col items-center gap-3">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-slate-600"></div>
                <p className="text-sm text-slate-500">Loading report...</p>
              </div>
            </div>
          ) : isV1Report && versionedReportData && versionedReportData.reportVersion === 'v4_ultra_compact' ? (
            /* V4 Ultra-Compact Report View */
            <V4ReportPanel 
              reportData={versionedReportData}
              onAccept={() => {
                if (productLink && onUpdateStatus) {
                  onUpdateStatus(productLink, "Submitted");
                }
                onClose();
                navigate('/');
              }}
              onEdit={initializeAgentMode}
            />
          ) : isV1Report && versionedReportData ? (
            /* Versioned Report View for V1, V2, V3 SKUs */
            <VersionedReportPanel 
              reportData={versionedReportData}
              productHistory={productHistory}
              onAccept={() => {
                if (productLink && onUpdateStatus) {
                  onUpdateStatus(productLink, "Submitted");
                }
                onClose();
                navigate('/');
              }}
              onEdit={initializeAgentMode}
              onReviewLater={onClose}
            />
          ) : (
            /* Full Report View */
            <div className="p-6 space-y-4">
              {/* Executive Summary */}
              <Card>
                <CardHeader className="cursor-pointer bg-slate-100" onClick={() => toggleSection('executiveSummary')}>
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base flex items-center gap-2">
                      <FileText className="h-[24px] w-[24px] text-primary bg-green-100 rounded-full p-1" />
                      Executive Summary
                    </CardTitle>
                    {expandedSections.executiveSummary ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                  </div>
                </CardHeader>
                {expandedSections.executiveSummary && (
                  <CardContent className="space-y-4 pt-2">
                    <p className="text-sm text-foreground leading-relaxed">
                      {reportData.executiveSummary.summaryText}
                    </p>
                    <div className="bg-muted/50 rounded-lg p-4 space-y-3">
                      <div>
                        <h4 className="text-sm font-medium mb-2">{reportData.executiveSummary.rationale.title}</h4>
                        <p className="text-sm text-muted-foreground leading-relaxed">
                          {reportData.executiveSummary.rationale.text}
                        </p>
                      </div>
                      <div>
                        <h4 className="text-sm font-medium mb-2">{reportData.executiveSummary.confidenceLevelText.title}</h4>
                        <p className="text-sm text-muted-foreground leading-relaxed">
                          {reportData.executiveSummary.confidenceLevelText.text}
                        </p>
                      </div>
                    </div>
                  </CardContent>
                )}
              </Card>

              {/* Product-Specific History Section (only for 3 specific SKUs) */}
              {productHistory && (
                <Card>
                  <CardHeader className="cursor-pointer bg-slate-100">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-base flex items-center gap-2">
                        <BarChart3 className="h-[24px] w-[24px] text-blue-800 bg-blue-100 rounded-full p-1" />
                        📊 Product-Specific History
                      </CardTitle>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4 pt-4">
                    {productHistory.hasHistory ? (
                      <>
                        {/* Time Series Chart */}
                        <div className="space-y-3">
                          <div className="flex items-center justify-between">
                            <h4 className="text-sm font-semibold">Forecast Accuracy Over Time</h4>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => setShowExpandedHistoryChart(!showExpandedHistoryChart)}
                            >
                              {showExpandedHistoryChart ? 'Show Summary' : 'Show Detail'}
                            </Button>
                          </div>
                          
                          <ResponsiveContainer width="100%" height={200}>
                            <LineChart data={productHistory.timeSeriesData.cycles}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
                              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                              <YAxis tick={{ fontSize: 11 }} />
                              <Tooltip 
                                contentStyle={{ backgroundColor: "#ffffff", border: "1px solid #E5E7EB", borderRadius: "6px" }}
                                formatter={(value: any, name: string) => [
                                  typeof value === 'number' ? value.toLocaleString() : value,
                                  name
                                ]}
                              />
                              <Legend />
                              {/* Always visible: Final Forecast and Actuals */}
                              <Line 
                                type="monotone" 
                                dataKey="finalForecast" 
                                name="Final Forecast" 
                                stroke="#0066CC" 
                                strokeWidth={2}
                                dot={{ r: 4 }}
                              />
                              <Line 
                                type="monotone" 
                                dataKey="actual" 
                                name="Actuals" 
                                stroke="#39B15A" 
                                strokeWidth={2}
                                dot={{ r: 4 }}
                              />
                              {/* Show when expanded: Agent Rec and Planner Edit */}
                              {showExpandedHistoryChart && (
                                <>
                                  <Line 
                                    type="monotone" 
                                    dataKey="agentRec" 
                                    name="Agent Rec" 
                                    stroke="#8B5CF6" 
                                    strokeWidth={2}
                                    strokeDasharray="5 5"
                                    dot={{ r: 3 }}
                                  />
                                  <Line 
                                    type="monotone" 
                                    dataKey="plannerEdit" 
                                    name="Planner Edit" 
                                    stroke="#F59E0B" 
                                    strokeWidth={2}
                                    strokeDasharray="3 3"
                                    dot={{ r: 3 }}
                                    connectNulls={false}
                                  />
                                </>
                              )}
                            </LineChart>
                          </ResponsiveContainer>
                        </div>

                        {/* Collapsible: Decision History */}
                        <Collapsible open={decisionHistoryOpen} onOpenChange={setDecisionHistoryOpen}>
                          <CollapsibleTrigger asChild>
                            <Button variant="ghost" className="w-full justify-between p-3 h-auto bg-muted/30 hover:bg-muted/50">
                              <span className="text-sm font-medium">📊 Decision History</span>
                              <ChevronDown className={`h-4 w-4 transition-transform ${decisionHistoryOpen ? 'rotate-180' : ''}`} />
                            </Button>
                          </CollapsibleTrigger>
                          <CollapsibleContent className="pt-3">
                            <div className="space-y-2 mb-4">
                              {productHistory.timeSeriesData.cycles.map((cycle: any, idx: number) => (
                                <div key={idx} className="flex items-center justify-between p-2 bg-muted/20 rounded-lg text-sm">
                                  <span className="font-medium">{cycle.date}:</span>
                                  {cycle.plannerEdit ? (
                                    <span className="text-amber-600">📝 Planner override → {cycle.accuracy}% accurate</span>
                                  ) : (
                                    <span className="text-emerald-600">✅ Agent accepted → {cycle.accuracy}% accurate</span>
                                  )}
                                </div>
                              ))}
                            </div>
                            
                            <div className="bg-muted/30 rounded-lg p-3">
                              <h5 className="text-sm font-semibold mb-2">Summary:</h5>
                              <div className="space-y-1 text-sm text-muted-foreground">
                                <p>
                                  <span className="text-emerald-600">●</span> When agent recommendation accepted: {productHistory.trackRecord.agentAcceptedCycles.count} cycles, {productHistory.trackRecord.agentAcceptedCycles.averageAccuracy}% avg accuracy
                                </p>
                                <p>
                                  <span className="text-amber-600">●</span> When planner override applied: {productHistory.trackRecord.plannerOverrideCycles.count} cycles, {productHistory.trackRecord.plannerOverrideCycles.averageAccuracy}% avg accuracy
                                </p>
                                <p className="font-medium text-foreground">
                                  Overall: {productHistory.trackRecord.overallAccuracy}% avg accuracy
                                </p>
                              </div>
                            </div>
                          </CollapsibleContent>
                        </Collapsible>

                        {/* Collapsible: Override Reasoning (only show if overrides exist) */}
                        {productHistory.overrideReasoning.length > 0 && (
                          <Collapsible open={overrideReasoningOpen} onOpenChange={setOverrideReasoningOpen}>
                            <CollapsibleTrigger asChild>
                              <Button variant="ghost" className="w-full justify-between p-3 h-auto bg-muted/30 hover:bg-muted/50">
                                <span className="text-sm font-medium">💬 Past Override Reasoning</span>
                                <ChevronDown className={`h-4 w-4 transition-transform ${overrideReasoningOpen ? 'rotate-180' : ''}`} />
                              </Button>
                            </CollapsibleTrigger>
                            <CollapsibleContent className="pt-3 space-y-3">
                              {productHistory.overrideReasoning.map((override: any, idx: number) => (
                                <div key={idx} className="p-3 bg-amber-50 border border-amber-200 rounded-lg">
                                  <p className="text-sm font-medium text-amber-800">{override.cycle} ({override.adjustment} adjustment):</p>
                                  <p className="text-sm text-muted-foreground italic">"{override.reasoning}"</p>
                                  <p className="text-xs text-muted-foreground mt-1">→ Result: {override.outcome}</p>
                                </div>
                              ))}
                            </CollapsibleContent>
                          </Collapsible>
                        )}
                      </>
                    ) : (
                      /* New product with no history */
                      <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                        <p className="text-sm text-blue-800 flex items-center gap-2">
                          <Info className="h-4 w-4" />
                          ℹ️ No historical data yet - this is the first forecast cycle for this product
                        </p>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}

              {/* Recommendation & Intervention */}
              <Card>
                <CardHeader className="cursor-pointer  bg-slate-100" onClick={() => toggleSection('recommendation')}>
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base flex items-center gap-2">
                      <ChartLine className="h-[24px] w-[24px] text-yellow-800 bg-yellow-100 rounded-full p-1" />
                      {reportData.recommendationAndIntervention.title}
                    </CardTitle>
                    {expandedSections.recommendation ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                  </div>
                </CardHeader>
                {expandedSections.recommendation && (
                  <CardContent className="space-y-4 pt-2">
                    <p className="text-sm text-foreground">
                      {reportData.recommendationAndIntervention.summaryText}
                    </p>
                    <ul className="space-y-2">
                      {reportData.recommendationAndIntervention.bulletPoints.map((point, idx) => (
                        <li key={idx} className="text-sm text-muted-foreground flex items-start gap-2">
                          <span className="text-primary mt-1">•</span>
                          <span>{point}</span>
                        </li>
                      ))}
                    </ul>

                    {/* Visual Comparison Bar Chart */}
                    <div className="mt-4">
                      <h4 className="text-sm font-medium mb-3">{reportData.recommendationAndIntervention.visualComparisonTitle}</h4>
                      <ResponsiveContainer width="100%" height={300}>
                        <BarChart data={recommendationChartData}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
                          <XAxis dataKey="month" tick={{ fontSize: 12 }} />
                          <YAxis tick={{ fontSize: 12 }} domain={[16000, 18500]} />
                          <Tooltip contentStyle={{ backgroundColor: "#ffffff", border: "1px solid #E5E7EB", borderRadius: "6px" }} />
                          <Legend />
                          <Bar dataKey="Historical Actuals" fill="#FFC560" />
                          <Bar dataKey="ML Forecast" fill="#00327D" />
                          <Bar dataKey="Agent Recommendation" fill="#39B15A" />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </CardContent>
                )}
              </Card>

              {/* Treatment Rationale / Baseline Forecast Validation Checks */}
              <Card>
                <CardHeader className="cursor-pointer bg-slate-100" onClick={() => toggleSection('validation')}>
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base">{reportData.treatmentRationale.title}</CardTitle>
                    {expandedSections.validation ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                  </div>
                </CardHeader>
                {expandedSections.validation && (
                  <CardContent className="space-y-4 pt-2">
                    {/* Evidence for Adjustment */}
                    <div>
                      <h4 className="text-sm font-semibold mb-3">Evidence for Adjustment:</h4>
                      <div className="space-y-2">
                        <div>
                          <span className="text-sm font-medium">Product Maturity:</span>{" "}
                          <span className="text-sm text-muted-foreground">{reportData.treatmentRationale.evidenceForAdjustment.productMaturity}</span>
                        </div>
                        <div>
                          <span className="text-sm font-medium">Viral Breakthrough:</span>{" "}
                          <span className="text-sm text-muted-foreground">{reportData.treatmentRationale.evidenceForAdjustment.viralBreakthrough}</span>
                        </div>
                        <div>
                          <span className="text-sm font-medium">Demand Repricing:</span>{" "}
                          <span className="text-sm text-muted-foreground">{reportData.treatmentRationale.evidenceForAdjustment.demandRepricing}</span>
                        </div>
                        <div>
                          <span className="text-sm font-medium">Conservative Bias:</span>{" "}
                          <span className="text-sm text-muted-foreground">{reportData.treatmentRationale.evidenceForAdjustment.conservativeBias}</span>
                        </div>
                        <div>
                          <span className="text-sm font-medium">Forecast Philosophy:</span>{" "}
                          <span className="text-sm text-muted-foreground">{reportData.treatmentRationale.evidenceForAdjustment.forecastPhilosophy}</span>
                        </div>
                      </div>
                    </div>

                    {/* Strategy Applied */}
                    <div>
                      <h4 className="text-sm font-semibold mb-3">Strategy Applied:</h4>
                      <ul className="space-y-1">
                        {reportData.treatmentRationale.strategyApplied.map((strategy, idx) => (
                          <li key={idx} className="text-sm text-muted-foreground">{strategy}</li>
                        ))}
                      </ul>
                    </div>

                    {/* Period-by-Period Breakdown Table */}
                    <div>
                      <h4 className="text-sm font-semibold mb-3">Period-by-Period Adjustment Breakdown</h4>
                      <div className="rounded-md border">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Period</TableHead>
                              <TableHead className="text-right">Original Forecast</TableHead>
                              <TableHead className="text-right">Adjusted Forecast</TableHead>
                              <TableHead className="text-right">Adjustment %</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {reportData.treatmentRationale.periodByPeriodBreakdown.map((period, idx) => (
                              <TableRow key={idx}>
                                <TableCell className="font-medium">{period.period}</TableCell>
                                <TableCell className="text-right">{period.originalForecast.toLocaleString()}</TableCell>
                                <TableCell className="text-right font-medium text-primary">
                                  {period.adjustedForecast.toLocaleString()}
                                </TableCell>
                                <TableCell className="text-right">
                                  <span className={period.adjustmentPercent > 0 ? "text-primary font-medium" : "text-destructive font-medium"}>
                                    {period.adjustmentPercent > 0 ? '+' : ''}{period.adjustmentPercent}%
                                  </span>
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </div>
                    </div>

                    {/* Visual: Original vs Adjusted Forecast Line Chart */}
                    <div>
                      <h4 className="text-sm font-semibold mb-3">Visual: Original vs Adjusted Forecast</h4>
                      <ResponsiveContainer width="100%" height={300}>
                        <LineChart data={treatmentRationaleChartData}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
                          <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                          <YAxis tick={{ fontSize: 12 }} />
                          <Tooltip contentStyle={{ backgroundColor: "#ffffff", border: "1px solid #E5E7EB", borderRadius: "6px" }} />
                          <Legend />
                          <Line 
                            type="monotone" 
                            dataKey="Original ML Forecast" 
                            stroke="#E7000B" 
                            strokeWidth={2}
                            dot={{ r: 4, fill: "#E7000B" }}
                          />
                          <Line 
                            type="monotone" 
                            dataKey="Agent Adjusted" 
                            stroke="#39B15A" 
                            strokeWidth={2}
                            dot={{ r: 4, fill: "#39B15A" }}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </CardContent>
                )}
              </Card>

              {/* Historical Context */}
              <Card>
                <CardHeader className="cursor-pointer bg-slate-100" onClick={() => toggleSection('historicalContext')}>
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base">Historical Context</CardTitle>
                    {expandedSections.historicalContext ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                  </div>
                </CardHeader>
                {expandedSections.historicalContext && (
                  <CardContent className="space-y-4 pt-2">
                    <div className="grid grid-cols-4 gap-3">
                      <Card>
                        <CardContent className="p-4">
                          <div className="text-xs text-muted-foreground mb-1">Agent Run ID</div>
                          <div className="text-xs font-mono">{reportData.technicalDetails.agentRunId.slice(0, 8)}...</div>
                        </CardContent>
                      </Card>
                      <Card>
                        <CardContent className="p-4">
                          <div className="text-xs text-muted-foreground mb-1">Forecast Cycle</div>
                          <div className="text-sm font-medium">{reportData.technicalDetails.forecastCycle}</div>
                        </CardContent>
                      </Card>
                      <Card>
                        <CardContent className="p-4">
                          <div className="text-xs text-muted-foreground mb-1">Data Quality</div>
                          <div className="text-sm font-medium">{reportData.technicalDetails.dataQuality}</div>
                        </CardContent>
                      </Card>
                      <Card>
                        <CardContent className="p-4">
                          <div className="text-xs text-muted-foreground mb-1">Confidence</div>
                          <div className="text-sm font-medium">{reportData.technicalDetails.confidenceLevel}</div>
                        </CardContent>
                      </Card>
                    </div>

                    <div>
                      <h4 className="text-sm font-medium mb-3">{reportData.demandHistoryChart.title}</h4>
                      <ResponsiveContainer width="100%" height={250}>
                        <LineChart data={demandHistoryData}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="period" tick={{ fontSize: 11 }} />
                          <YAxis />
                          <Tooltip contentStyle={{ backgroundColor: "#ffffff", border: "1px solid #E5E7EB", borderRadius: "6px" }} />
                          <Legend />
                          <Line 
                            type="monotone" 
                            dataKey="Actual" 
                            stroke="#0066CC" 
                            strokeWidth={2}
                            dot={{ r: 3 }}
                            connectNulls={false}
                          />
                          <Line 
                            type="monotone" 
                            dataKey="Forecast" 
                            stroke="#39B15A" 
                            strokeWidth={2}
                            strokeDasharray="5 5"
                            dot={{ r: 3 }}
                            connectNulls={false}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </CardContent>
                )}
              </Card>

              {/* Risk Assessment */}
              <Card>
                <CardHeader className="cursor-pointer bg-slate-100" onClick={() => toggleSection('riskAssessment')}>
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base flex items-center gap-2">
                      <AlertTriangle className="h-[24px] w-[24px] text-red-800 bg-red-100 rounded-full p-1" />
                      {reportData.riskAssessment.title}
                    </CardTitle>
                    {expandedSections.riskAssessment ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                  </div>
                </CardHeader>
                {expandedSections.riskAssessment && (
                  <CardContent className="space-y-3 pt-2">
                    {/* High Priority Risks */}
                    {reportData.riskAssessment.highPriorityRisks.map((risk, idx) => (
                      <div key={idx} className="bg-destructive/10 border border-destructive/20 rounded-lg p-4">
                        <div className="flex items-start justify-between mb-2">
                          <h4 className="text-sm font-medium">{risk.title}</h4>
                          <Badge className={getRiskBadgeColor(risk.severity)}>{risk.severity}</Badge>
                        </div>
                        <p className="text-sm text-muted-foreground mb-2">{risk.description}</p>
                        <div className="text-xs text-muted-foreground">
                          <span className="font-medium">Impact:</span> {risk.impact}
                        </div>
                      </div>
                    ))}

                    {/* Medium Priority Risks */}
                    {reportData.riskAssessment.mediumPriorityRisks.map((risk, idx) => (
                      <div key={idx} className="bg-warning/10 border border-warning/20 rounded-lg p-4">
                        <div className="flex items-start justify-between mb-2">
                          <h4 className="text-sm font-medium">{risk.title}</h4>
                          <Badge className={getRiskBadgeColor(risk.severity)}>{risk.severity}</Badge>
                        </div>
                        <p className="text-sm text-muted-foreground mb-2">{risk.description}</p>
                        <div className="text-xs text-muted-foreground">
                          <span className="font-medium">Impact:</span> {risk.impact}
                        </div>
                      </div>
                    ))}

                    {/* Mitigated Risks */}
                    {reportData.riskAssessment.mitigatedRisks.map((risk, idx) => (
                      <div key={idx} className="bg-primary/10 border border-primary/20 rounded-lg p-4">
                        <div className="flex items-start justify-between mb-2">
                          <h4 className="text-sm font-medium">{risk.title}</h4>
                          <Badge className={getRiskBadgeColor(risk.severity)}>{risk.severity}</Badge>
                        </div>
                        <p className="text-sm text-muted-foreground mb-2">{risk.description}</p>
                        <div className="text-xs text-muted-foreground">
                          <span className="font-medium">Mitigation:</span> {risk.mitigation}
                        </div>
                      </div>
                    ))}
                  </CardContent>
                )}
              </Card>

              {/* Recommended Actions */}
              <Card>
                <CardHeader className="cursor-pointer bg-slate-100" onClick={() => toggleSection('actions')}>
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base flex items-center gap-2">
                      <Package className="h-4 w-4" />
                      Recommended Actions & Evidence
                    </CardTitle>
                    {expandedSections.actions ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                  </div>
                </CardHeader>
                {expandedSections.actions && (
                  <CardContent className="space-y-4">
                    <div className="grid grid-cols-2 gap-3">
                      {reportData.monitoringRecommendations.map((rec) => (
                        <div key={rec.number} className="bg-muted/50 rounded-lg p-4">
                          <div className="flex items-start gap-3">
                            <div className="flex-shrink-0 w-6 h-6 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-xs font-medium">
                              {rec.number}
                            </div>
                            <div className="flex-1">
                              <h4 className="text-sm font-medium mb-1">{rec.title}</h4>
                              <p className="text-sm text-muted-foreground">{rec.description}</p>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>

                    <div className="bg-muted/30 rounded-lg p-4">
                      <h4 className="text-sm font-medium mb-3">Supporting Evidence</h4>
                      <div className="space-y-2">
                        {reportData.technicalDetails.supportingEvidence.map((evidence, idx) => (
                          <div key={idx} className="text-sm">
                            <span className="font-medium">{evidence.title}:</span>{" "}
                            <span className="text-muted-foreground">{evidence.description}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </CardContent>
                )}
              </Card>
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
