import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useNavigate, useSearchParams, Link, useParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { toast } from 'sonner';
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Checkbox,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Spinner,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Textarea,
} from '../components/common';
import { Info, AlertCircle } from 'lucide-react';
import PageLayout from '../components/PageLayout';
import { getAllConfigs, getSupplyChainConfigById } from '../services/supplyChainConfigService';
import { getUserType as resolveUserType } from '../utils/authUtils';
import PricingConfigForm from '../components/PricingConfigForm';
import simulationApi, { api } from '../services/api';
import { getModelStatus } from '../services/modelService';
import { useSystemConfig } from '../contexts/SystemConfigContext.jsx';
import { LLM_BASE_MODEL_OPTIONS, DEFAULT_LLM_BASE_MODEL } from '../constants/llmModels';

const playerRoles = [
  { value: 'retailer', label: 'Retailer' },
  { value: 'wholesaler', label: 'Wholesaler' },
  { value: 'distributor', label: 'Distributor' },
  { value: 'manufacturer', label: 'Manufacturer' },
];

const agentStrategies = [
  {
    group: 'Basic',
    options: [
      { value: 'NAIVE', label: 'Naive (heuristic)' },
      { value: 'BULLWHIP', label: 'Bullwhip (heuristic)' },
      { value: 'CONSERVATIVE', label: 'Conservative (heuristic)' },
      { value: 'RANDOM', label: 'Random (heuristic)' },
      { value: 'PID_HEURISTIC', label: 'PID Heuristic (control)' },
    ]
  },
  {
    group: 'Autonomy LLM',
    options: [
      { value: 'LLM_CONSERVATIVE', label: 'Autonomy LLM - Conservative' },
      { value: 'LLM_BALANCED', label: 'Autonomy LLM - Balanced' },
      { value: 'LLM_AGGRESSIVE', label: 'Autonomy LLM - Aggressive' },
      { value: 'LLM_ADAPTIVE', label: 'Autonomy LLM - Adaptive' },
      { value: 'LLM_SUPERVISED', label: 'Autonomy LLM - Roles + Supervisor' },
      { value: 'LLM_GLOBAL', label: 'Autonomy LLM - SC Orchestrator' },
    ]
  },
  {
    group: 'Autonomy',
    options: [
      { value: 'AUTONOMY_DTCE', label: 'Autonomy - Roles', requiresModel: true },
      { value: 'AUTONOMY_DTCE_CENTRAL', label: 'Autonomy - Roles + Supervisor', requiresModel: true },
      { value: 'AUTONOMY_DTCE_GLOBAL', label: 'Autonomy - SC Orchestrator', requiresModel: true },
    ]
  }
];

const strategyLabelMap = agentStrategies.reduce((acc, group) => {
  group.options.forEach((option) => {
    acc[option.value] = option.label;
  });
  return acc;
}, {});

const getStrategyLabel = (strategy) => strategyLabelMap[strategy] || strategy;

const autonomyStrategyDescriptions = {
  AUTONOMY_DTCE: 'Autonomy - Roles deploys one agent per supply chain role.',
  AUTONOMY_DTCE_CENTRAL:
    'Autonomy - Roles + Supervisor allows a network supervisor to adjust orders within the configured percentage.',
  AUTONOMY_DTCE_GLOBAL: 'Autonomy - SC Orchestrator runs a single agent across the entire supply chain.',
};

const DEFAULT_CLASSIC_PARAMS = {
  initial_demand: 4,
  change_week: 6,
  final_demand: 8,
};

const strategyDescriptions = {
  NAIVE: 'Basic heuristic that matches orders to demand.',
  BULLWHIP: 'Tends to overreact to demand changes.',
  CONSERVATIVE: 'Maintains stable inventory levels.',
  RANDOM: 'Makes random order decisions.',
  PID_HEURISTIC: 'Uses a proportional-integral-derivative controller to balance demand forecast, inventory error, and rate of change.',
  DEMAND_DRIVEN: 'Autonomy LLM: demand-driven analysis.',
  COST_OPTIMIZATION: 'Autonomy LLM: optimizes for lower cost.',
  LLM_CONSERVATIVE: 'Autonomy LLM strategy focused on stable inventory.',
  LLM_BALANCED: 'Autonomy LLM strategy balancing service and cost.',
  LLM_AGGRESSIVE: 'Autonomy LLM strategy that minimizes inventory aggressively.',
  LLM_ADAPTIVE: 'Autonomy LLM strategy that adapts to observed trends.',
  LLM_SUPERVISED: 'Autonomy LLM roles with a central supervisor that can smooth orders within the configured percentage.',
  LLM_GLOBAL: 'Single Autonomy LLM agent that coordinates decisions for every role in the chain.',
  AUTONOMY_DTCE: autonomyStrategyDescriptions.AUTONOMY_DTCE,
  AUTONOMY_DTCE_CENTRAL: autonomyStrategyDescriptions.AUTONOMY_DTCE_CENTRAL,
  AUTONOMY_DTCE_GLOBAL: autonomyStrategyDescriptions.AUTONOMY_DTCE_GLOBAL,
};

const HelperText = ({ children, className = '' }) => (
  <p className={`text-xs text-muted-foreground mt-1 ${className}`}>
    {children}
  </p>
);

const progressionOptions = [
  {
    value: 'supervised',
    label: 'Supervised',
    description: 'Group Admin advances rounds manually.',
  },
  {
    value: 'unsupervised',
    label: 'Unsupervised',
    description: 'Advance automatically when every user submits.',
  },
];

const DEFAULT_SYSTEM_CONFIG = {
  min_order_quantity: 0,
  max_order_quantity: 100,
  min_holding_cost: 0,
  max_holding_cost: 10,
  min_backlog_cost: 0,
  max_backlog_cost: 20,
  min_demand: 0,
  max_demand: 100,
  min_lead_time: 0,
  max_lead_time: 4,
  min_starting_inventory: 0,
  max_starting_inventory: 100,
};

const DEFAULT_POLICY = {
  order_leadtime: 2,
  supply_leadtime: 2,
  init_inventory: 12,
  holding_cost: 0.5,
  backlog_cost: 1.0,
  max_inbound_per_link: 100,
  max_order: 100,
};

const DEFAULT_PRICING_CONFIG = {
  retailer: { selling_price: 100.0, standard_cost: 80.0 },
  wholesaler: { selling_price: 75.0, standard_cost: 60.0 },
  distributor: { selling_price: 60.0, standard_cost: 45.0 },
  manufacturer: { selling_price: 45.0, standard_cost: 30.0 },
};

const DEFAULT_AUTONOMY_LLM_CONFIG = {
  toggles: {
    customer_demand_history_sharing: false,
    volatility_signal_sharing: false,
    downstream_inventory_visibility: false,
  },
  shared_history_weeks: null,
  volatility_window: null,
};

const demandPatterns = [
  { value: 'classic', label: 'Classic (Step Increase)' },
  { value: 'random', label: 'Random' },
  { value: 'seasonal', label: 'Seasonal' },
  { value: 'constant', label: 'Constant' },
];

const clampOverridePercent = (value) => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return 5;
  }
  return Math.min(50, Math.max(5, numeric));
};

const toNumberOr = (value, fallback) => {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
};

const normalizeStrategyForPayload = (strategy) => {
  if (!strategy) {
    return null;
  }
  const raw = String(strategy).toLowerCase();
  if (raw === 'pi' || raw === 'pi_controller' || raw === 'pid' || raw === 'pid_controller') {
    return 'pid_heuristic';
  }
  return raw;
};

const CreateMixedGame = () => {
  const { gameId } = useParams();
  const isEditing = Boolean(gameId);
  const [searchParams] = useSearchParams();
  const [gameName, setGameName] = useState(searchParams.get('name') || '');
  const [systemConfig, setSystemConfig] = useState(() => ({
    ...DEFAULT_SYSTEM_CONFIG,
  }));
  const [maxRounds, setMaxRounds] = useState(20);
  const [description, setDescription] = useState(searchParams.get('description') || '');
  const [isPublic, setIsPublic] = useState(true);
  const [progressionMode, setProgressionMode] = useState('supervised');
  const [demandPattern, setDemandPattern] = useState(demandPatterns[0].value);
  const [initialDemand, setInitialDemand] = useState(4);
  const [demandChangeWeek, setDemandChangeWeek] = useState(6);
  const [finalDemand, setFinalDemand] = useState(8);
  const [pricingConfig, setPricingConfig] = useState(() => ({ ...DEFAULT_PRICING_CONFIG }));
  const [sitePolicies, setSitePolicies] = useState({});
  const [policy, setPolicy] = useState(() => ({ ...DEFAULT_POLICY }));
  const [autonomyLlmConfig, setAutonomyLlmConfig] = useState(() => ({
    toggles: { ...DEFAULT_AUTONOMY_LLM_CONFIG.toggles },
    shared_history_weeks: DEFAULT_AUTONOMY_LLM_CONFIG.shared_history_weeks,
    volatility_window: DEFAULT_AUTONOMY_LLM_CONFIG.volatility_window,
  }));
  const [savedSnapshot, setSavedSnapshot] = useState(null);
  const { user } = useAuth();
  const [modelStatus, setModelStatus] = useState(null);
  const { ranges: systemRanges } = useSystemConfig();
  const [availableUsers, setAvailableUsers] = useState([]);
  const [loadingUsers, setLoadingUsers] = useState(true);

  const [players, setPlayers] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [configs, setConfigs] = useState([]);
  const [activeConfigId, setActiveConfigId] = useState(null);
  const [activeSupplyChainConfig, setActiveSupplyChainConfig] = useState(null);
  const [loadingSupplyChain, setLoadingSupplyChain] = useState(true);
  const [supplyChainError, setSupplyChainError] = useState(null);
  const [selectedSiteType, setSelectedNodeType] = useState(null);
  const [activeTab, setActiveTab] = useState('settings');
  const navigate = useNavigate();
  const [initializing, setInitializing] = useState(isEditing);

  const userLookup = useMemo(() => {
    if (!Array.isArray(availableUsers)) {
      return new Map();
    }
    return new Map(
      availableUsers.map((entry) => [Number(entry?.id), entry?.username || `User #${entry?.id}`])
    );
  }, [availableUsers]);

  const usesAutonomyStrategist = useMemo(
    () =>
      players.some(
        (player) => player.playerType === 'ai' && String(player.strategy || '').startsWith('LLM_')
      ),
    [players]
  );

  const hasAutonomyOverrides = useMemo(() => {
    const toggles = autonomyLlmConfig?.toggles || {};
    return Object.values(toggles).some(Boolean);
  }, [autonomyLlmConfig]);

  const showAutonomySharingCard = usesAutonomyStrategist || hasAutonomyOverrides;

  const summaryProgressionMode = progressionMode || 'supervised';

  const progressionLabel = useMemo(() => {
    const option = progressionOptions.find((entry) => entry.value === summaryProgressionMode);
    return option ? option.label : summaryProgressionMode;
  }, [summaryProgressionMode]);

  const normalizeSiteName = useCallback((value) => String(value || '').trim().toLowerCase(), []);
  const normalizeSiteType = useCallback((value) => String(value || '').trim().toLowerCase(), []);

  const playableTypeToRole = useMemo(
    () => ({
      retailer: 'retailer',
      wholesaler: 'wholesaler',
      distributor: 'distributor',
      manufacturer: 'manufacturer',
    }),
    []
  );

  const siteTypeLabels = {
    market_supply: 'Market Supply',
    manufacturer: 'Manufacturer',
    distributor: 'Distributor',
    wholesaler: 'Wholesaler',
    retailer: 'Retailer',
    market_demand: 'Market Demand',
  };

  const computeRangeMidpoint = useCallback((range, fallback = 0) => {
    if (!range || (range.min == null && range.max == null)) {
      return fallback;
    }
    const min = Number(range.min ?? range.max ?? fallback);
    const max = Number(range.max ?? range.min ?? fallback);
    if (!Number.isFinite(min) && !Number.isFinite(max)) {
      return fallback;
    }
    if (!Number.isFinite(min)) return max;
    if (!Number.isFinite(max)) return min;
    return (min + max) / 2;
  }, []);

  const formatNumber = useCallback((value) => {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return '—';
    }
    return numeric.toLocaleString();
  }, []);

  const formatCurrency = useCallback((value) => {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return '—';
    }
    return `$${numeric.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }, []);

  const formatRangeValue = useCallback((min, max, suffix = '') => {
    const parsedMin = Number(min);
    const parsedMax = Number(max);
    const hasMin = Number.isFinite(parsedMin);
    const hasMax = Number.isFinite(parsedMax);
    const suffixText = suffix ? ` ${suffix}` : '';

    if (hasMin && hasMax) {
      if (parsedMin === parsedMax) {
        return `${parsedMin}${suffixText}`;
      }
      return `${parsedMin}${suffixText} – ${parsedMax}${suffixText}`;
    }
    if (hasMin) {
      return `≥ ${parsedMin}${suffixText}`;
    }
    if (hasMax) {
      return `≤ ${parsedMax}${suffixText}`;
    }
    return '—';
  }, []);

  const formatCurrencyRange = useCallback((min, max) => {
    const parsedMin = Number(min);
    const parsedMax = Number(max);
    const hasMin = Number.isFinite(parsedMin);
    const hasMax = Number.isFinite(parsedMax);

    if (hasMin && hasMax) {
      if (parsedMin === parsedMax) {
        return formatCurrency(parsedMin);
      }
      return `${formatCurrency(parsedMin)} – ${formatCurrency(parsedMax)}`;
    }
    if (hasMin) {
      return `≥ ${formatCurrency(parsedMin)}`;
    }
    if (hasMax) {
      return `≤ ${formatCurrency(parsedMax)}`;
    }
    return '—';
  }, [formatCurrency]);

  const formatWeeks = useCallback((value) => {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return '—';
    }
    const rounded = Math.round(numeric);
    return `${rounded} week${rounded === 1 ? '' : 's'}`;
  }, []);

  const clampToRange = useCallback((value, range) => {
    if (!Number.isFinite(value)) return value;
    if (!range) return value;
    let result = value;
    if (range.min != null) {
      const min = Number(range.min);
      if (Number.isFinite(min)) {
        result = Math.max(result, min);
      }
    }
    if (range.max != null) {
      const max = Number(range.max);
      if (Number.isFinite(max)) {
        result = Math.min(result, max);
      }
    }
    return result;
  }, []);

  const normalizeRange = useCallback((range) => {
    if (!range) {
      return { min: null, max: null };
    }
    const parsedMin = Number(range.min);
    const parsedMax = Number(range.max);
    return {
      min: Number.isFinite(parsedMin) ? parsedMin : null,
      max: Number.isFinite(parsedMax) ? parsedMax : null,
    };
  }, []);

  const formatRangeIndicator = useCallback((range, { decimals } = {}) => {
    const { min, max } = normalizeRange(range);
    const formatValue = (value) => {
      if (value == null) {
        return '—';
      }
      if (decimals != null) {
        return value.toFixed(decimals);
      }
      if (Math.abs(value - Math.round(value)) < 1e-6) {
        return String(Math.round(value));
      }
      return value.toFixed(2).replace(/\.0+$/, '').replace(/\.$/, '');
    };
    return `[${formatValue(min)}, ${formatValue(max)}]`;
  }, [normalizeRange]);

  const buildDefaultSitePolicy = useCallback(
    (node, config) => {
      const key = normalizeSiteName(node?.name);
      if (!key) {
        return null;
      }
      const nodeType = normalizeSiteType(node?.type);
      const itemConfig = node?.item_configs && node.item_configs.length > 0 ? node.item_configs[0] : null;
      const inboundLanes = (config?.lanes || []).filter((lane) => lane?.to_site_id === node.id);
      const leadRanges = inboundLanes.map((lane) => lane?.lead_time_days || {});
      const leadMin = leadRanges.reduce((acc, range) => {
        const value = Number(range?.min);
        if (!Number.isFinite(value)) return acc;
        if (acc == null || value < acc) return value;
        return acc;
      }, null);
      const leadMax = leadRanges.reduce((acc, range) => {
        const value = Number(range?.max);
        if (!Number.isFinite(value)) return acc;
        if (acc == null || value > acc) return value;
        return acc;
      }, null);
      const defaultInit = itemConfig?.initial_inventory_range
        ? computeRangeMidpoint(itemConfig.initial_inventory_range, 12)
        : 12;
      const supplyLeadTime = leadMin != null && leadMax != null
        ? Math.round((leadMin + leadMax) / 2)
        : leadMin != null
          ? leadMin
          : leadMax != null
            ? leadMax
            : 0;

      const isMarketSite = ['market_supply', 'market_demand'].includes(nodeType);
      return {
        order_leadtime: isMarketSite ? 0 : 1,
        supply_leadtime: isMarketSite ? 0 : supplyLeadTime,
        init_inventory: isMarketSite ? 0 : Math.round(defaultInit),
        min_order_qty: isMarketSite ? 0 : 0,
        variable_cost: 0,
      };
    },
    [computeRangeMidpoint, normalizeSiteName, normalizeSiteType]
  );

  const normalizeLoadedPolicies = useCallback((rawPolicies = {}) => {
    const normalised = {};
    Object.entries(rawPolicies || {}).forEach(([name, value]) => {
      if (!value) {
        return;
      }
      const key = normalizeSiteName(name);
      normalised[key] = {
        order_leadtime: Number.isFinite(Number(value.order_leadtime)) ? Number(value.order_leadtime) : 0,
        supply_leadtime: Number.isFinite(Number(value.supply_leadtime)) ? Number(value.supply_leadtime) : 0,
        init_inventory: Number.isFinite(Number(value.init_inventory)) ? Number(value.init_inventory) : 0,
        min_order_qty: Number.isFinite(Number(value.min_order_qty)) ? Number(value.min_order_qty) : 0,
        variable_cost: Number.isFinite(Number(value.variable_cost)) ? Number(value.variable_cost) : 0,
      };
    });
    return normalised;
  }, [normalizeSiteName]);

  const buildGameSnapshot = useCallback((statePayload) => {
    if (!statePayload) {
      return null;
    }

    const game = statePayload?.game ?? statePayload ?? {};
    const config = statePayload?.config ?? game?.config ?? {};

    const statusValue = String(
      statePayload?.status ??
      game?.status ??
      config?.status ??
      ''
    ).toLowerCase();

    const currentRoundValue = toNumberOr(
      statePayload?.current_round ??
      game?.current_round ??
      config?.current_round,
      0
    );

    const demandBlock = statePayload?.demand_pattern ?? game?.demand_pattern ?? config?.demand_pattern ?? {};
    const demandParams = demandBlock?.params ?? {};
    const initialDemandValue = toNumberOr(
      demandParams.initial_demand ?? demandParams.initialDemand,
      DEFAULT_CLASSIC_PARAMS.initial_demand
    );
    const changeWeekValue = toNumberOr(
      demandParams.change_week ?? demandParams.changeWeek,
      DEFAULT_CLASSIC_PARAMS.change_week
    );
    const finalDemandValue = toNumberOr(
      demandParams.final_demand ?? demandParams.new_demand ?? demandParams.finalDemand,
      DEFAULT_CLASSIC_PARAMS.final_demand
    );
    const demandType = String(demandBlock?.type || 'classic').toLowerCase();

    const pricing = statePayload?.pricing_config ?? game?.pricing_config ?? config?.pricing_config ?? {};
    const pricingConfigSnapshot = {
      retailer: {
        selling_price: toNumberOr(pricing?.retailer?.selling_price, DEFAULT_PRICING_CONFIG.retailer.selling_price),
        standard_cost: toNumberOr(pricing?.retailer?.standard_cost, DEFAULT_PRICING_CONFIG.retailer.standard_cost),
      },
      wholesaler: {
        selling_price: toNumberOr(pricing?.wholesaler?.selling_price, DEFAULT_PRICING_CONFIG.wholesaler.selling_price),
        standard_cost: toNumberOr(pricing?.wholesaler?.standard_cost, DEFAULT_PRICING_CONFIG.wholesaler.standard_cost),
      },
      distributor: {
        selling_price: toNumberOr(pricing?.distributor?.selling_price, DEFAULT_PRICING_CONFIG.distributor.selling_price),
        standard_cost: toNumberOr(pricing?.distributor?.standard_cost, DEFAULT_PRICING_CONFIG.distributor.standard_cost),
      },
      manufacturer: {
        selling_price: toNumberOr(pricing?.manufacturer?.selling_price, DEFAULT_PRICING_CONFIG.manufacturer.selling_price),
        standard_cost: toNumberOr(pricing?.manufacturer?.standard_cost, DEFAULT_PRICING_CONFIG.manufacturer.standard_cost),
      },
    };

    const resolvedSitePolicies = statePayload?.site_policies ?? game?.site_policies ?? config?.site_policies ?? {};
    const normalizedPolicies = normalizeLoadedPolicies(resolvedSitePolicies);
    const sitePoliciesSnapshot = Object.entries(normalizedPolicies).reduce((acc, [key, value]) => {
      acc[key] = { ...value };
      return acc;
    }, {});

    const resolvedSystemConfig = statePayload?.system_config ?? game?.system_config ?? config?.system_config ?? {};
    const systemConfigSnapshot = { ...DEFAULT_SYSTEM_CONFIG, ...resolvedSystemConfig };

    const resolvedPolicy = statePayload?.global_policy ?? game?.global_policy ?? config?.global_policy ?? {};
    const policySnapshot = { ...DEFAULT_POLICY, ...resolvedPolicy };

    const autonomyBlock = statePayload?.autonomy_llm ?? game?.autonomy_llm ?? config?.autonomy_llm ?? {};
    const toggles = autonomyBlock?.toggles ?? {};
    const autonomySnapshot = {
      toggles: {
        customer_demand_history_sharing: Boolean(toggles.customer_demand_history_sharing),
        volatility_signal_sharing: Boolean(toggles.volatility_signal_sharing),
        downstream_inventory_visibility: Boolean(toggles.downstream_inventory_visibility),
      },
      shared_history_weeks: autonomyBlock?.shared_history_weeks != null ? autonomyBlock.shared_history_weeks : null,
      volatility_window: autonomyBlock?.volatility_window != null ? autonomyBlock.volatility_window : null,
    };

    const overrides = statePayload?.autonomy_overrides ?? game?.autonomy_overrides ?? config?.autonomy_overrides ?? {};

    const rawPlayers = Array.isArray(statePayload?.players)
      ? statePayload.players
      : Array.isArray(game?.players)
        ? game.players
        : [];

    const mappedPlayers = rawPlayers.reduce((acc, record) => {
      const roleValue = String(record?.role || '').toLowerCase();
      if (!roleValue) {
        return acc;
      }
      const isAi = Boolean(record?.is_ai ?? record?.type === 'agent');
      const rawStrategy = record?.ai_strategy ?? record?.strategy;
      const normalizedStrategy = rawStrategy ? String(rawStrategy).toUpperCase() : 'NAIVE';
      const overrideValue =
        overrides?.[roleValue] ??
        overrides?.[roleValue.toUpperCase()] ??
        overrides?.[roleValue.toLowerCase()];
      acc[roleValue] = {
        role: roleValue,
        playerType: isAi ? 'ai' : 'human',
        strategy: isAi ? normalizedStrategy : 'NAIVE',
        canSeeDemand:
          record?.can_see_demand != null ? Boolean(record.can_see_demand) : roleValue === 'retailer',
        userId: record?.user_id ?? null,
        llmModel: record?.llm_model || DEFAULT_LLM_BASE_MODEL,
        autonomyOverridePct:
          overrideValue != null ? clampOverridePercent(Number(overrideValue) * 100) : undefined,
        displayName: record?.name || record?.display_name || roleValue,
      };
      return acc;
    }, {});

    const playersSnapshot = playerRoles.map(({ value: roleValue, label }) => {
      const entry = mappedPlayers[roleValue];
      if (entry) {
        return { ...entry, displayName: entry.displayName || label };
      }
      return {
        role: roleValue,
        playerType: 'ai',
        strategy: 'NAIVE',
        canSeeDemand: roleValue === 'retailer',
        userId: null,
        llmModel: DEFAULT_LLM_BASE_MODEL,
        autonomyOverridePct: undefined,
        displayName: label,
      };
    });

    return {
      gameName: game?.name || statePayload?.name || config?.name || '',
      description: game?.description || config?.description || '',
      maxRounds: toNumberOr(game?.max_rounds ?? statePayload?.max_rounds ?? config?.max_rounds, 20),
      isPublic:
        game?.is_public !== undefined
          ? Boolean(game.is_public)
          : Boolean(config?.is_public ?? statePayload?.is_public ?? true),
      progressionMode:
        statePayload?.progression_mode ??
        game?.progression_mode ??
        config?.progression_mode ??
        'supervised',
      demandPattern: demandType,
      demandParams: {
        initial_demand: initialDemandValue,
        change_week: changeWeekValue,
        final_demand: finalDemandValue,
      },
      pricingConfig: pricingConfigSnapshot,
      sitePolicies: sitePoliciesSnapshot,
      systemConfig: systemConfigSnapshot,
      policy: policySnapshot,
      players: playersSnapshot,
      autonomyLlm: autonomySnapshot,
      autonomyOverrides: overrides,
      supplyChainConfigId:
        config?.supply_chain_config_id ??
        game?.supply_chain_config_id ??
        statePayload?.supply_chain_config_id ??
        null,
      supplyChainName:
        config?.supply_chain_name ??
        game?.supply_chain_name ??
        statePayload?.supply_chain_name ??
        '',
      supplyChainConfig: statePayload?.supply_chain_config ?? null,
      status: statusValue,
      currentRound: currentRoundValue,
    };
  }, [normalizeLoadedPolicies]);

  const formatDemandPatternSummary = useCallback((pattern, params) => {
    if (!pattern) {
      return '—';
    }
    const type = String(pattern.demand_type || pattern.type || params?.type || 'unknown').toLowerCase();
    const payload = params || pattern.params || {};
    switch (type) {
      case 'constant':
        return `Constant at ${payload.value ?? payload.mean ?? payload.demand ?? '?'}`;
      case 'random':
        return `Random between ${payload.min ?? '?'} and ${payload.max ?? '?'}`;
      case 'seasonal':
        return `Seasonal base ${payload.value ?? '?'} (period ${payload?.seasonality?.period ?? '?'} weeks)`;
      case 'trending':
        return `Trending base ${payload.value ?? '?'} (trend ${payload.trend ?? 0})`;
      case 'classic':
        return `Classic: starts ${payload.initial_demand ?? '?'}, week ${payload.change_week ?? '?'}, final ${payload.final_demand ?? payload.new_demand ?? '?'}`;
      case 'lognormal':
        return `LogNormal mean ${payload.mean ?? '?'} (CoV ${payload.cov ?? '?'})`;
      default:
        return type.replace(/_/g, ' ');
    }
  }, []);

  const summaryGameName = gameName;
  const summaryMaxRounds = maxRounds;
  const summaryDemandPattern = demandPattern;

  const summaryDemandParams = useMemo(
    () => ({
      initial_demand: toNumberOr(initialDemand, DEFAULT_CLASSIC_PARAMS.initial_demand),
      change_week: toNumberOr(demandChangeWeek, DEFAULT_CLASSIC_PARAMS.change_week),
      final_demand: toNumberOr(finalDemand, DEFAULT_CLASSIC_PARAMS.final_demand),
    }),
    [initialDemand, demandChangeWeek, finalDemand]
  );

  const demandSummary = useMemo(() => (
    formatDemandPatternSummary(
      { type: summaryDemandPattern, params: summaryDemandParams },
      summaryDemandParams
    )
  ), [summaryDemandPattern, summaryDemandParams, formatDemandPatternSummary]);

  const formatLeadTimeRange = useCallback((range) => {
    if (!range) {
      return '—';
    }
    const min = Number(range.min);
    const max = Number(range.max);
    if (Number.isFinite(min) && Number.isFinite(max)) {
      if (min === max) {
        return `${min} week${min === 1 ? '' : 's'}`;
      }
      return `${min}–${max} weeks`;
    }
    if (Number.isFinite(min)) {
      return `${min}+ weeks`;
    }
    if (Number.isFinite(max)) {
      return `≤ ${max} weeks`;
    }
    return '—';
  }, []);

  const resolvePolicyValue = useCallback(
    (policies, nodeKey, field, fallback = 0) => {
      if (!nodeKey) {
        return fallback;
      }
      const policy = policies?.[nodeKey];
      if (policy && policy[field] != null) {
        return policy[field];
      }
      const defaultPolicy = buildDefaultSitePolicy(
        (activeSupplyChainConfig?.sites || []).find((node) => normalizeSiteName(node?.name) === nodeKey),
        activeSupplyChainConfig
      );
      if (defaultPolicy && defaultPolicy[field] != null) {
        return defaultPolicy[field];
      }
      return fallback;
    },
    [activeSupplyChainConfig, buildDefaultSitePolicy, normalizeSiteName]
  );

  const getPolicyValue = useCallback(
    (nodeKey, field, fallback = 0) => resolvePolicyValue(sitePolicies, nodeKey, field, fallback),
    [sitePolicies, resolvePolicyValue]
  );

  const describeRange = useCallback((range, unit = '') => {
    if (!range) {
      return null;
    }
    const min = range.min != null ? Number(range.min) : null;
    const max = range.max != null ? Number(range.max) : null;
    if (Number.isFinite(min) && Number.isFinite(max)) {
      return `${min}${unit ? ` ${unit}` : ''} – ${max}${unit ? ` ${unit}` : ''}`;
    }
    if (Number.isFinite(min)) {
      return `≥ ${min}${unit ? ` ${unit}` : ''}`;
    }
    if (Number.isFinite(max)) {
      return `≤ ${max}${unit ? ` ${unit}` : ''}`;
    }
    return null;
  }, []);

  // Fetch available users
  useEffect(() => {
    const fetchUsers = async () => {
      try {
        const response = await api.get('/auth/users/');
        setAvailableUsers(response.data);
      } catch (error) {
        console.error('Error fetching users:', error);
        toast.error('Failed to load users');
      } finally {
        setLoadingUsers(false);
      }
    };

    fetchUsers();
  }, []);

  // Load available saved Game Configurations (core game setup)
  useEffect(() => {
    (async () => {
      try {
        const cfgs = await getAllConfigs();
        if (Array.isArray(cfgs)) setConfigs(cfgs);
      } catch (e) {
        // non-blocking
      }
    })();
  }, []);

  useEffect(() => {
    if (!Array.isArray(configs) || isEditing) {
      return;
    }
    const groupIdRaw = user?.group_id;
    const groupId = Number.isFinite(Number(groupIdRaw)) ? Number(groupIdRaw) : null;
    const candidates = configs.filter((config) => {
      if (groupId == null) return true;
      return Number(config?.group_id) === groupId;
    });
    const chosen = candidates.find((config) => Boolean(config?.is_active)) || candidates[0] || configs[0] || null;
    setActiveConfigId(chosen ? chosen.id : null);
  }, [configs, user, isEditing]);

  useEffect(() => {
    let ignore = false;
    const loadActiveConfig = async () => {
      if (!activeConfigId) {
        setActiveSupplyChainConfig(null);
        setLoadingSupplyChain(false);
        return;
      }
      try {
        setLoadingSupplyChain(true);
        setSupplyChainError(null);
        const detailed = await getSupplyChainConfigById(activeConfigId);
        if (!ignore) {
          setActiveSupplyChainConfig(detailed || null);
        }
      } catch (error) {
        if (!ignore) {
          console.error('Failed to load supply chain configuration', error);
          setSupplyChainError('Unable to load supply chain configuration.');
        }
      } finally {
        if (!ignore) {
          setLoadingSupplyChain(false);
        }
      }
    };
    loadActiveConfig();
    return () => {
      ignore = true;
    };
  }, [activeConfigId]);

  // Load Autonomy agent model status
  useEffect(() => {
    (async () => {
      try {
        const status = await getModelStatus();
        setModelStatus(status);
      } catch (e) {
        console.error('Failed to get model status', e);
      }
    })();
  }, []);

  useEffect(() => {
    if (!isEditing) {
      return;
    }

    let cancelled = false;

    const loadGame = async () => {
      try {
        setInitializing(true);
        const state = await simulationApi.getGameState(gameId);
        if (cancelled) return;

        const snapshot = buildGameSnapshot(state);
        if (!snapshot) {
          setInitializing(false);
          return;
        }

        setGameName(snapshot.gameName || '');
        setDescription(snapshot.description || '');
        setMaxRounds(snapshot.maxRounds || 20);
        setIsPublic(snapshot.isPublic !== undefined ? Boolean(snapshot.isPublic) : true);
        setProgressionMode(snapshot.progressionMode || 'supervised');

        setDemandPattern(snapshot.demandPattern || 'classic');
        const demandParams = snapshot.demandParams || {};
        setInitialDemand(
          demandParams.initial_demand != null
            ? toNumberOr(demandParams.initial_demand, DEFAULT_CLASSIC_PARAMS.initial_demand)
            : DEFAULT_CLASSIC_PARAMS.initial_demand
        );
        setDemandChangeWeek(
          demandParams.change_week != null
            ? toNumberOr(demandParams.change_week, DEFAULT_CLASSIC_PARAMS.change_week)
            : DEFAULT_CLASSIC_PARAMS.change_week
        );
        setFinalDemand(
          demandParams.final_demand != null
            ? toNumberOr(demandParams.final_demand, DEFAULT_CLASSIC_PARAMS.final_demand)
            : DEFAULT_CLASSIC_PARAMS.final_demand
        );

        const snapshotPricing = snapshot.pricingConfig || DEFAULT_PRICING_CONFIG;
        setPricingConfig({
          retailer: { ...snapshotPricing.retailer },
          wholesaler: { ...snapshotPricing.wholesaler },
          distributor: { ...snapshotPricing.distributor },
          manufacturer: { ...snapshotPricing.manufacturer },
        });

        const snapshotPolicies = Object.entries(snapshot.sitePolicies || {}).reduce((acc, [key, value]) => {
          acc[key] = { ...value };
          return acc;
        }, {});
        setSitePolicies(snapshotPolicies);

        setSystemConfig({ ...DEFAULT_SYSTEM_CONFIG, ...(snapshot.systemConfig || {}) });
        setPolicy({ ...DEFAULT_POLICY, ...(snapshot.policy || {}) });

        const snapshotAutonomy = snapshot.autonomyLlm || {};
        setAutonomyLlmConfig({
          toggles: {
            ...DEFAULT_AUTONOMY_LLM_CONFIG.toggles,
            ...(snapshotAutonomy.toggles || {}),
          },
          shared_history_weeks:
            snapshotAutonomy.shared_history_weeks != null ? snapshotAutonomy.shared_history_weeks : null,
          volatility_window:
            snapshotAutonomy.volatility_window != null ? snapshotAutonomy.volatility_window : null,
        });

        setPlayers((snapshot.players || []).map((player) => ({ ...player })));

        if (snapshot.supplyChainConfig) {
          setActiveSupplyChainConfig(snapshot.supplyChainConfig);
        }

        if (snapshot.supplyChainConfigId) {
          setActiveConfigId(snapshot.supplyChainConfigId);
        }

        setSavedSnapshot(snapshot);
      } catch (error) {
        console.error('Failed to load alternative configuration', error);
        toast.error('Error loading alternative', {
          description: error?.response?.data?.detail || 'Unable to load existing alternative configuration.',
        });
        navigate('/alternatives');
      } finally {
        if (!cancelled) {
          setInitializing(false);
        }
      }
    };

    loadGame();
    return () => {
      cancelled = true;
    };
  }, [isEditing, gameId, navigate, buildGameSnapshot]);

  // Optional prefill via query params for site policies (JSON-encoded)
  useEffect(() => {
    const np = searchParams.get('site_policies');
    if (np) {
      try {
        const parsed = JSON.parse(np);
        if (parsed && typeof parsed === 'object') setSitePolicies(normalizeLoadedPolicies(parsed));
      } catch {}
    }
    const sc = searchParams.get('system_config');
    if (sc) {
      try {
        const parsed = JSON.parse(sc);
        if (parsed && typeof parsed === 'object') setSystemConfig(parsed);
      } catch {}
    }
    const pc = searchParams.get('pricing_config');
    if (pc) {
      try {
        const parsed = JSON.parse(pc);
        if (parsed && typeof parsed === 'object') setPricingConfig(parsed);
      } catch {}
    }
    // Load system ranges from backend, then merge local defaults and localStorage
    (async () => {
      try {
        const serverCfg = await simulationApi.getSystemConfig();
        if (serverCfg && typeof serverCfg === 'object') setSystemConfig((prev)=> ({...prev, ...serverCfg}));
      } catch {}
    })();
    // Load system ranges from localStorage if present
    const stored = localStorage.getItem('systemConfigRanges');
    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        if (parsed && typeof parsed === 'object') setSystemConfig((prev)=> ({...prev, ...parsed}));
      } catch {}
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // If context ranges become available later, merge them
  useEffect(() => {
    if (!systemRanges || !Object.keys(systemRanges).length) {
      return;
    }
    if (isEditing && !initializing) {
      return;
    }
    setSystemConfig(prev => ({ ...prev, ...systemRanges }));
  }, [systemRanges, isEditing, initializing]);


  const sitesByType = useMemo(() => {
    if (!activeSupplyChainConfig?.sites) {
      return {};
    }
    return activeSupplyChainConfig.sites.reduce((acc, node) => {
      const type = normalizeSiteType(node?.type);
      if (!type) {
        return acc;
      }
      if (!acc[type]) {
        acc[type] = [];
      }
      acc[type].push(node);
      return acc;
    }, {});
  }, [activeSupplyChainConfig, normalizeSiteType]);

  const siteTypeOptions = useMemo(() => {
    const types = Object.keys(sitesByType);
    const order = ['market_supply', 'manufacturer', 'distributor', 'wholesaler', 'retailer', 'market_demand'];
    return order.filter((type) => types.includes(type));
  }, [sitesByType]);

  const playableSites = useMemo(() => {
    const order = ['retailer', 'wholesaler', 'distributor', 'manufacturer'];
    return order
      .map((type) => {
        const nodes = sitesByType[type] || [];
        return nodes.length > 0 ? nodes[0] : null;
      })
      .filter(Boolean);
  }, [sitesByType]);

  useEffect(() => {
    if (!activeSupplyChainConfig) {
      return;
    }
    setSitePolicies((prev) => {
      const updated = { ...prev };
      (activeSupplyChainConfig.sites || []).forEach((node) => {
        const key = normalizeSiteName(node?.name);
        if (!key) {
          return;
        }
        if (!updated[key]) {
          const defaults = buildDefaultSitePolicy(node, activeSupplyChainConfig);
          if (defaults) {
            updated[key] = defaults;
          }
        }
      });
      return updated;
    });
  }, [activeSupplyChainConfig, buildDefaultSitePolicy, normalizeSiteName]);

  useEffect(() => {
    if (!activeSupplyChainConfig) {
      return;
    }
    const availableTypes = Object.keys(sitesByType);
    if (availableTypes.length === 0) {
      setSelectedNodeType(null);
      return;
    }
    if (!selectedSiteType || !availableTypes.includes(selectedSiteType)) {
      const ordered = ['market_supply', 'manufacturer', 'distributor', 'wholesaler', 'retailer', 'market_demand'];
      const nextType = ordered.find((type) => availableTypes.includes(type)) || availableTypes[0];
      setSelectedNodeType(nextType);
    }
  }, [activeSupplyChainConfig, sitesByType, selectedSiteType]);

  useEffect(() => {
    if (!activeSupplyChainConfig) {
      return;
    }
    setPlayers((prevPlayers) => {
      const existingByRole = new Map(prevPlayers.map((player) => [player.role, player]));
      const defaults = playableSites.map((node) => {
        const nodeType = normalizeSiteType(node?.type);
        const roleKey = playableTypeToRole[nodeType];
        if (!roleKey) {
          return null;
        }
        const base = {
          role: roleKey,
          playerType: 'ai',
          strategy: 'NAIVE',
          canSeeDemand: roleKey === 'retailer',
          userId: roleKey === 'retailer' && user ? user.id : null,
          llmModel: DEFAULT_LLM_BASE_MODEL,
          autonomyOverridePct: 5,
          displayName: node?.name || roleKey,
          nodeId: node?.id,
          nodeType,
        };
        const existing = existingByRole.get(roleKey);
        return existing ? { ...base, ...existing, displayName: node?.name || existing.displayName } : base;
      }).filter(Boolean);
      return defaults;
    });
  }, [activeSupplyChainConfig, playableSites, normalizeSiteType, playableTypeToRole, user]);

  const sitesById = useMemo(() => {
    if (!activeSupplyChainConfig?.sites) {
      return new Map();
    }
    return new Map(activeSupplyChainConfig.sites.map((node) => [node.id, node]));
  }, [activeSupplyChainConfig]);

  const marketsById = useMemo(() => {
    if (!activeSupplyChainConfig?.markets) {
      return new Map();
    }
    return new Map(activeSupplyChainConfig.markets.map((market) => [market.id, market]));
  }, [activeSupplyChainConfig]);

  const itemsById = useMemo(() => {
    if (!activeSupplyChainConfig?.items) {
      return new Map();
    }
    return new Map(activeSupplyChainConfig.items.map((item) => [item.id, item]));
  }, [activeSupplyChainConfig]);

  const sitePolicyBounds = useMemo(() => {
    if (!activeSupplyChainConfig) {
      return {};
    }
    const bounds = {};
    (activeSupplyChainConfig.sites || []).forEach((node) => {
      const key = normalizeSiteName(node?.name);
      if (!key) {
        return;
      }
      const itemConfig = node?.item_configs && node.item_configs.length > 0 ? node.item_configs[0] : null;
      const inboundLanes = (activeSupplyChainConfig.lanes || []).filter((lane) => lane?.to_site_id === node.id);
      const leadRange = inboundLanes.reduce(
        (acc, lane) => {
          const range = lane?.lead_time_days || {};
          const min = Number(range.min);
          const max = Number(range.max);
          return {
            min: Number.isFinite(min) ? (acc.min == null ? min : Math.min(acc.min, min)) : acc.min,
            max: Number.isFinite(max) ? (acc.max == null ? max : Math.max(acc.max, max)) : acc.max,
          };
        },
        { min: null, max: null }
      );
      bounds[key] = {
        init_inventory: itemConfig?.initial_inventory_range,
        min_order_qty: itemConfig?.inventory_target_range,
        supply_leadtime: leadRange,
        order_leadtime: { min: 0, max: 12 },
        variable_cost: itemConfig?.selling_price_range
          ? { min: 0, max: Number(itemConfig.selling_price_range.max) }
          : { min: 0, max: 100 },
      };
    });
    return bounds;
  }, [activeSupplyChainConfig, normalizeSiteName]);

  const marketDemandRows = useMemo(() => {
    const demands = activeSupplyChainConfig?.market_demands || [];
    if (!demands.length) {
      return [];
    }
    return demands.map((demand) => {
      const item = itemsById.get(demand.item_id);
      const market = marketsById.get(demand.market_id);
      const pattern = demand.demand_pattern || demand.pattern || {};
      const params = pattern.params || pattern;
      return {
        id: demand.id,
        itemName: item?.name || `Item ${demand.item_id}`,
        pattern,
        params,
        marketName: market?.name || 'Unknown Market',
      };
    });
  }, [activeSupplyChainConfig, itemsById, marketsById]);

  const marketSupplyRows = useMemo(() => {
    if (!activeSupplyChainConfig) {
      return [];
    }
    const lanes = activeSupplyChainConfig.lanes || [];
    return (sitesByType.market_supply || []).map((node) => {
      const outbound = lanes.filter((lane) => lane?.from_site_id === node.id);
      return {
        node,
        outbound,
      };
    });
  }, [activeSupplyChainConfig, sitesByType]);


  const handleAutonomyToggleChange = (key) => (checked) => {
    setAutonomyLlmConfig((prev) => ({
      ...prev,
      toggles: { ...prev.toggles, [key]: checked },
    }));
  };

  const handleNodePolicyNumberChange = useCallback(
    (nodeKey, field) => (e) => {
      const rawValue = parseFloat(e.target.value);
      setSitePolicies((prev) => {
        const prevPolicy = prev[nodeKey] || {};
        const bounds = sitePolicyBounds[nodeKey]?.[field];
        const defaultPolicy = prevPolicy.init_inventory != null ? prevPolicy : buildDefaultSitePolicy(
          (activeSupplyChainConfig?.sites || []).find((node) => normalizeSiteName(node?.name) === nodeKey),
          activeSupplyChainConfig
        ) || {};
        let nextValue = Number.isFinite(rawValue) ? rawValue : prevPolicy[field] ?? defaultPolicy[field] ?? 0;
        nextValue = Number.isFinite(nextValue) ? clampToRange(nextValue, bounds) : nextValue;
        return {
          ...prev,
          [nodeKey]: {
            ...defaultPolicy,
            ...prevPolicy,
            [field]: Number.isFinite(nextValue) ? nextValue : prevPolicy[field] ?? defaultPolicy[field] ?? 0,
          },
        };
      });
    },
    [activeSupplyChainConfig, buildDefaultSitePolicy, clampToRange, sitePolicyBounds, normalizeSiteName]
  );

  const handlePlayerTypeChange = (index, type) => {
    setPlayers((prevPlayers) =>
      prevPlayers.map((player, i) => {
        if (i !== index) {
          return player;
        }
        const updatedPlayer = {
          ...player,
          playerType: type,
        };
        if (type === 'human') {
          updatedPlayer.strategy = agentStrategies[0].options[0].value;
          if (player.role === 'retailer' && !player.userId && user) {
            updatedPlayer.userId = user.id;
          }
          updatedPlayer.autonomyOverridePct = undefined;
        } else if (type === 'ai') {
          updatedPlayer.userId = null;
          updatedPlayer.strategy = updatedPlayer.strategy || agentStrategies[0].options[0].value;
          if (!updatedPlayer.llmModel) {
            updatedPlayer.llmModel = DEFAULT_LLM_BASE_MODEL;
          }
        }
        return updatedPlayer;
      })
    );
  };

  const handleStrategyChange = (index, strategy) => {
    setPlayers((prevPlayers) =>
      prevPlayers.map((player, i) => {
        if (i !== index) {
          return player;
        }
        const updated = { ...player, strategy };
        if (String(strategy).startsWith('LLM_') && !updated.llmModel) {
          updated.llmModel = DEFAULT_LLM_BASE_MODEL;
        }
        if (strategy === 'AUTONOMY_DTCE_CENTRAL' || strategy === 'LLM_SUPERVISED') {
          const basePct = player.autonomyOverridePct ?? 5;
          updated.autonomyOverridePct = clampOverridePercent(basePct);
        }
        return updated;
      })
    );
  };

  const handleUserChange = (index, userId) => {
    setPlayers((prevPlayers) =>
      prevPlayers.map((player, i) =>
        i === index ? { ...player, userId: userId || null } : player
      )
    );
  };

  const handleCanSeeDemandChange = (index, canSeeDemand) => {
    setPlayers((prevPlayers) =>
      prevPlayers.map((player, i) => (i === index ? { ...player, canSeeDemand } : player))
    );
  };

  const handleSubmit = async (e) => {
    if (e) e.preventDefault();

    // Validate that each human role has a user assigned
    const invalidPlayers = players.filter(
      (p) => p.playerType === 'human' && !p.userId
    );

    if (invalidPlayers.length > 0) {
      toast.error('Validation Error', {
        description: 'Please assign a user to all human roles',
      });
      return null;
    }

    // Validate pricing configuration
    const invalidPricing = Object.entries(pricingConfig).some(([, prices]) => {
      return (
        !prices.selling_price ||
        !prices.standard_cost ||
        prices.selling_price <= prices.standard_cost
      );
    });

    if (invalidPricing) {
      toast.error('Validation Error', {
        description: 'Please ensure selling price is greater than standard cost for all roles',
      });
      return null;
    }

    let submissionAction = isEditing ? 'update' : 'create';
    let shouldResetAfterSave = false;

    if (isEditing) {
      const status = String(savedSnapshot?.status || '').toLowerCase();
      const currentRoundValue = Number(savedSnapshot?.currentRound ?? 0);
      const hasProgress =
        currentRoundValue > 0 ||
        ['in_progress', 'round_in_progress', 'finished', 'completed'].includes(status);

      if (hasProgress) {
        const confirmReset = window.confirm(
          'This alternative has already been played. Click OK to update and reset the existing alternative, or Cancel to create a new alternative with your changes.'
        );

        if (confirmReset) {
          shouldResetAfterSave = true;
        } else {
          submissionAction = 'create';
        }
      }
    }

    setIsLoading(true);

    try {
      const sitePolicyPayload = (() => {
        if (activeSupplyChainConfig?.sites) {
          const payload = {};
          activeSupplyChainConfig.sites.forEach((node) => {
            const key = normalizeSiteName(node?.name);
            if (!key) {
              return;
            }
            const base = buildDefaultSitePolicy(node, activeSupplyChainConfig) || {};
            const stored = sitePolicies[key] || {};
            const merged = { ...base, ...stored };
            const roleKey = playableTypeToRole[normalizeSiteType(node?.type)];
            const pricing = roleKey ? pricingConfig[roleKey] : null;
            payload[key] = {
              order_leadtime: Number.isFinite(Number(merged.order_leadtime)) ? Number(merged.order_leadtime) : 0,
              supply_leadtime: Number.isFinite(Number(merged.supply_leadtime)) ? Number(merged.supply_leadtime) : 0,
              init_inventory: Number.isFinite(Number(merged.init_inventory)) ? Number(merged.init_inventory) : 0,
              min_order_qty: Number.isFinite(Number(merged.min_order_qty)) ? Number(merged.min_order_qty) : 0,
              variable_cost: Number.isFinite(Number(merged.variable_cost)) ? Number(merged.variable_cost) : 0,
              price: pricing ? Number(pricing.selling_price) : 0,
              standard_cost: pricing ? Number(pricing.standard_cost) : 0,
            };
          });
          return payload;
        }
        const fallback = {};
        Object.entries(sitePolicies || {}).forEach(([key, value]) => {
          fallback[key] = {
            order_leadtime: Number.isFinite(Number(value.order_leadtime)) ? Number(value.order_leadtime) : 0,
            supply_leadtime: Number.isFinite(Number(value.supply_leadtime)) ? Number(value.supply_leadtime) : 0,
            init_inventory: Number.isFinite(Number(value.init_inventory)) ? Number(value.init_inventory) : 0,
            min_order_qty: Number.isFinite(Number(value.min_order_qty)) ? Number(value.min_order_qty) : 0,
            variable_cost: Number.isFinite(Number(value.variable_cost)) ? Number(value.variable_cost) : 0,
            price: 0,
            standard_cost: 0,
          };
        });
        return fallback;
      })();

      const gameData = {
        name: gameName,
        max_rounds: maxRounds,
        description,
        is_public: isPublic,
        progression_mode: progressionMode,
        demand_pattern: {
          type: demandPattern,
          params:
            demandPattern === 'classic'
              ? {
                  initial_demand: Math.max(0, Number.isFinite(Number(initialDemand)) ? Number(initialDemand) : 0),
                  change_week: Math.max(1, Number.isFinite(Number(demandChangeWeek)) ? Number(demandChangeWeek) : 1),
                  final_demand: Math.max(0, Number.isFinite(Number(finalDemand)) ? Number(finalDemand) : 0),
                }
              : {},
        },
        site_policies: sitePolicyPayload,
        system_config: systemConfig,
        global_policy: policy,
        supply_chain_config_id: activeSupplyChainConfig?.id || null,
        supply_chain_name: activeSupplyChainConfig?.name || null,
        pricing_config: {
          retailer: {
            selling_price: parseFloat(pricingConfig.retailer.selling_price),
            standard_cost: parseFloat(pricingConfig.retailer.standard_cost),
          },
          wholesaler: {
            selling_price: parseFloat(pricingConfig.wholesaler.selling_price),
            standard_cost: parseFloat(pricingConfig.wholesaler.standard_cost),
          },
          distributor: {
            selling_price: parseFloat(pricingConfig.distributor.selling_price),
            standard_cost: parseFloat(pricingConfig.distributor.standard_cost),
          },
          manufacturer: {
            selling_price: parseFloat(pricingConfig.manufacturer.selling_price),
            standard_cost: parseFloat(pricingConfig.manufacturer.standard_cost),
          },
        },
        player_assignments: players.map((player) => {
          const role = String(player?.role || '').toLowerCase();
          const isAi = player.playerType === 'ai';
          const normalizedStrategy = isAi ? normalizeStrategyForPayload(player.strategy) : null;
          const overridePercent =
            normalizedStrategy === 'autonomy_dtce_central' || normalizedStrategy === 'llm_supervised'
              ? clampOverridePercent(player.autonomyOverridePct) / 100
              : null;

          return {
            role,
            player_type: isAi ? 'agent' : 'human',
            strategy: normalizedStrategy,
            can_see_demand: Boolean(player.canSeeDemand),
            user_id: isAi ? null : player.userId || null,
            llm_model:
              isAi && String(player.strategy || '')
                .toUpperCase()
                .startsWith('LLM_')
                ? player.llmModel
                : null,
            autonomy_override_pct: overridePercent,
          };
        }),
      };

      if (usesAutonomyStrategist) {
        const toggles = autonomyLlmConfig?.toggles || {};
        const autonomyPayload = {
          toggles: {
            customer_demand_history_sharing: Boolean(toggles.customer_demand_history_sharing),
            volatility_signal_sharing: Boolean(toggles.volatility_signal_sharing),
            downstream_inventory_visibility: Boolean(toggles.downstream_inventory_visibility),
          },
        };
        if (autonomyLlmConfig?.shared_history_weeks != null) {
          autonomyPayload.shared_history_weeks = autonomyLlmConfig.shared_history_weeks;
        }
        if (autonomyLlmConfig?.volatility_window != null) {
          autonomyPayload.volatility_window = autonomyLlmConfig.volatility_window;
        }
        gameData.autonomy_llm = autonomyPayload;
      }

      let response;
      if (submissionAction === 'update') {
        response = await simulationApi.updateGame(gameId, gameData);
      } else {
        response = await simulationApi.createGame(gameData);
      }

      if (submissionAction === 'update' && response) {
        const snapshot = buildGameSnapshot(response);
        if (snapshot) {
          setSavedSnapshot(snapshot);
          setGameName(snapshot.gameName || '');
          setDescription(snapshot.description || '');
          setMaxRounds(snapshot.maxRounds || 20);
          setIsPublic(snapshot.isPublic !== undefined ? Boolean(snapshot.isPublic) : true);
          setProgressionMode(snapshot.progressionMode || 'supervised');

          setDemandPattern(snapshot.demandPattern || 'classic');
          const params = snapshot.demandParams || {};
          setInitialDemand(
            params.initial_demand != null
              ? toNumberOr(params.initial_demand, DEFAULT_CLASSIC_PARAMS.initial_demand)
              : DEFAULT_CLASSIC_PARAMS.initial_demand
          );
          setDemandChangeWeek(
            params.change_week != null
              ? toNumberOr(params.change_week, DEFAULT_CLASSIC_PARAMS.change_week)
              : DEFAULT_CLASSIC_PARAMS.change_week
          );
          setFinalDemand(
            params.final_demand != null
              ? toNumberOr(params.final_demand, DEFAULT_CLASSIC_PARAMS.final_demand)
              : DEFAULT_CLASSIC_PARAMS.final_demand
          );

          const updatedPricing = snapshot.pricingConfig || DEFAULT_PRICING_CONFIG;
          setPricingConfig({
            retailer: { ...updatedPricing.retailer },
            wholesaler: { ...updatedPricing.wholesaler },
            distributor: { ...updatedPricing.distributor },
            manufacturer: { ...updatedPricing.manufacturer },
          });

          const updatedPolicies = Object.entries(snapshot.sitePolicies || {}).reduce((acc, [key, value]) => {
            acc[key] = { ...value };
            return acc;
          }, {});
          setSitePolicies(updatedPolicies);

          setSystemConfig({ ...DEFAULT_SYSTEM_CONFIG, ...(snapshot.systemConfig || {}) });
          setPolicy({ ...DEFAULT_POLICY, ...(snapshot.policy || {}) });

          const updatedAutonomy = snapshot.autonomyLlm || {};
          setAutonomyLlmConfig({
            toggles: {
              ...DEFAULT_AUTONOMY_LLM_CONFIG.toggles,
              ...(updatedAutonomy.toggles || {}),
            },
            shared_history_weeks:
              updatedAutonomy.shared_history_weeks != null ? updatedAutonomy.shared_history_weeks : null,
            volatility_window:
              updatedAutonomy.volatility_window != null ? updatedAutonomy.volatility_window : null,
          });

          setPlayers((snapshot.players || []).map((player) => ({ ...player })));

          if (snapshot.supplyChainConfig) {
            setActiveSupplyChainConfig(snapshot.supplyChainConfig);
          }

          if (snapshot.supplyChainConfigId) {
            setActiveConfigId(snapshot.supplyChainConfigId);
          }
        }
      }

      if (submissionAction === 'update' && shouldResetAfterSave) {
        try {
          await simulationApi.resetGame(gameId);
          setSavedSnapshot((prev) => (prev ? { ...prev, currentRound: 0, status: 'created' } : prev));
        } catch (resetError) {
          console.error('Error resetting alternative after update:', resetError);
          toast.warning('Alternative saved but reset failed', {
            description: resetError?.response?.data?.detail || 'The alternative was updated, but it could not be reset automatically.',
          });
        }
      }

      return { response, action: submissionAction, resetApplied: shouldResetAfterSave };
    } catch (error) {
      const wasUpdating = submissionAction === 'update';
      console.error(wasUpdating ? 'Error updating alternative:' : 'Error creating alternative:', error);
      toast.error(wasUpdating ? 'Error updating alternative' : 'Error creating alternative', {
        description: error?.response?.data?.detail || (wasUpdating ? 'Failed to update alternative configuration.' : 'Failed to create alternative configuration.'),
      });
      if (typeof error === 'object' && error) {
        error.submissionAction = submissionAction;
      }
      throw error;
    } finally {
      setIsLoading(false);
    }
  };

  const handleFormSubmit = async (e) => {
    if (e) e.preventDefault();
    try {
      const result = await handleSubmit();
      if (!result || !result.response) {
        return null;
      }

      const { response, action, resetApplied } = result;
      const wasUpdate = action === 'update';

      toast.success(wasUpdate ? 'Alternative updated!' : 'Alternative created!', {
        description: wasUpdate
          ? resetApplied
            ? 'The alternative configuration has been saved and reset.'
            : 'The alternative configuration has been saved.'
          : 'The simulation alternative has been created successfully.',
      });

      setTimeout(() => {
        if (wasUpdate) {
          navigate('/alternatives', { state: { refresh: Date.now() } });
        } else if (response && response.id) {
          navigate(`/alternatives/${response.id}`);
        } else {
          navigate('/alternatives');
        }
      }, 1500);

      return response;
    } catch (error) {
      const attemptedAction = error?.submissionAction || (isEditing ? 'update' : 'create');
      console.error(
        attemptedAction === 'update' ? 'Error updating alternative:' : 'Error creating alternative:',
        error
      );
      return null;
    }
  };

  const summarySupplyChainName =
    activeSupplyChainConfig?.name ??
    savedSnapshot?.supplyChainName ??
    savedSnapshot?.supplyChainConfig?.name ??
    null;

  const overviewItems = useMemo(() => [
    { label: 'Alternative Name', value: summaryGameName || '—' },
    { label: 'Max Rounds', value: formatNumber(summaryMaxRounds) },
    { label: 'Progression Mode', value: progressionLabel || '—' },
    { label: 'Demand Pattern', value: demandSummary },
    { label: 'Linked Supply Chain', value: summarySupplyChainName || '—' },
  ], [summaryGameName, summaryMaxRounds, progressionLabel, demandSummary, summarySupplyChainName, formatNumber]);

  const summaryPolicy = policy;

  const globalPolicyItems = useMemo(() => [
    { label: 'Order Lead Time', value: formatWeeks(summaryPolicy?.order_leadtime) },
    { label: 'Supply Lead Time', value: formatWeeks(summaryPolicy?.supply_leadtime) },
    { label: 'Initial Inventory', value: formatNumber(summaryPolicy?.init_inventory) },
    { label: 'Holding Cost', value: formatCurrency(summaryPolicy?.holding_cost) },
    { label: 'Backlog Cost', value: formatCurrency(summaryPolicy?.backlog_cost) },
    { label: 'Max Order', value: formatNumber(summaryPolicy?.max_order) },
    { label: 'Max Inbound / Link', value: formatNumber(summaryPolicy?.max_inbound_per_link) },
  ], [summaryPolicy, formatWeeks, formatNumber, formatCurrency]);

  const summarySystemConfig = systemConfig;

  const systemConstraintItems = useMemo(() => [
    { label: 'Order Quantity Range', value: formatRangeValue(summarySystemConfig?.min_order_quantity, summarySystemConfig?.max_order_quantity, 'units') },
    { label: 'Starting Inventory Range', value: formatRangeValue(summarySystemConfig?.min_starting_inventory, summarySystemConfig?.max_starting_inventory, 'units') },
    { label: 'Demand Range', value: formatRangeValue(summarySystemConfig?.min_demand, summarySystemConfig?.max_demand, 'units') },
    { label: 'Lead Time Range', value: formatRangeValue(summarySystemConfig?.min_lead_time, summarySystemConfig?.max_lead_time, 'weeks') },
    { label: 'Holding Cost Range', value: formatCurrencyRange(summarySystemConfig?.min_holding_cost, summarySystemConfig?.max_holding_cost) },
    { label: 'Backlog Cost Range', value: formatCurrencyRange(summarySystemConfig?.min_backlog_cost, summarySystemConfig?.max_backlog_cost) },
  ], [summarySystemConfig, formatRangeValue, formatCurrencyRange]);

  const summaryPlayers = players;

  const playerSummaryRows = useMemo(() =>
    playerRoles.map(({ value, label }) => {
      const player = (summaryPlayers || []).find((entry) => entry.role === value) || {};
      const isHuman = player.playerType === 'human';
      const assignmentLabel = isHuman
        ? (player.userId ? userLookup.get(Number(player.userId)) || `User #${player.userId}` : 'Unassigned')
        : 'AI Agent';
      const strategyLabel = isHuman
        ? 'Human Controlled'
        : getStrategyLabel(player.strategy || 'NAIVE');
      const llmModel = !isHuman && String(player.strategy || '').toUpperCase().startsWith('LLM_')
        ? player.llmModel
        : null;
      const overridePct = !isHuman && Number.isFinite(Number(player.autonomyOverridePct))
        ? `${clampOverridePercent(player.autonomyOverridePct)}%`
        : null;

      return {
        roleKey: value,
        roleLabel: label,
        typeLabel: isHuman ? 'Human' : 'Agent',
        assignmentLabel,
        strategyLabel,
        llmModel,
        overridePct,
        canSeeDemand: Boolean(player.canSeeDemand ?? (value === 'retailer')),
      };
    }),
    [summaryPlayers, userLookup]
  );

  const summaryNodePolicies = sitePolicies;
  const summaryPricingConfig = pricingConfig;

  const roleParameterRows = useMemo(() =>
    playerRoles.map(({ value, label }) => {
      const nodeKey = normalizeSiteName(value);
      return {
        roleKey: value,
        roleLabel: label,
        orderLeadtime: resolvePolicyValue(summaryNodePolicies, nodeKey, 'order_leadtime', 0),
        supplyLeadTime: resolvePolicyValue(summaryNodePolicies, nodeKey, 'supply_leadtime', 0),
        initInventory: resolvePolicyValue(summaryNodePolicies, nodeKey, 'init_inventory', 0),
        price: summaryPricingConfig?.[value]?.selling_price ?? null,
        standardCost: summaryPricingConfig?.[value]?.standard_cost ?? null,
      };
    }),
    [normalizeSiteName, resolvePolicyValue, summaryNodePolicies, summaryPricingConfig]
  );

  if (isEditing && initializing) {
    return (
      <PageLayout title="Edit Alternative">
        <div className="flex justify-center items-center min-h-[60vh]">
          <Spinner size="lg" />
        </div>
      </PageLayout>
    );
  }

  return (
    <PageLayout title={isEditing ? 'Edit Alternative' : 'Alternative Definition'}>
      <div className="space-y-6">
        {/* Quick links to saved Simulation Configurations */}
        {!isEditing && configs?.length > 0 && (
          <div className="mb-4">
            <Alert>
              <Info className="h-4 w-4" />
              <AlertTitle>Saved Simulation Configurations</AlertTitle>
              <AlertDescription>Use a configuration to prefill this form.</AlertDescription>
            </Alert>
            <div className="flex flex-wrap gap-2 mt-3">
              {configs.map((c) => (
                <Button key={c.id} asChild size="sm" variant="outline">
                  <Link to={`/alternatives/new-from-config/${c.id}`}>Use: {c.name}</Link>
                </Button>
              ))}
            </div>
          </div>
        )}

        {modelStatus && !modelStatus.is_trained && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Autonomy Agent Not Trained</AlertTitle>
            <AlertDescription>
              The Autonomy agent has not yet been trained, so it cannot be used until training completes. You may still select Basic (heuristics) or Autonomy LLM agents.
            </AlertDescription>
          </Alert>
        )}

        <form onSubmit={handleFormSubmit} className="space-y-6 max-w-6xl mx-auto w-full">
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="settings">Simulation Settings</TabsTrigger>
              <TabsTrigger value="pricing">Pricing</TabsTrigger>
              <TabsTrigger value="players">Users</TabsTrigger>
            </TabsList>

            <TabsContent value="settings" className="space-y-6 mt-6">
              {/* Alternative Details Card */}
              <Card>
                <CardHeader>
                  <CardTitle>Simulation Settings</CardTitle>
                  <p className="text-sm text-muted-foreground">Configure the basic settings for your simulation alternative</p>
                </CardHeader>
                <CardContent className="space-y-5">
                  <div>
                    <Label className="font-semibold">Alternative Name</Label>
                    <Input
                      value={gameName}
                      onChange={(e) => setGameName(e.target.value)}
                      placeholder="Enter alternative name"
                      className="mt-1"
                      required
                    />
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div>
                      <Label className="font-semibold">Maximum Rounds</Label>
                      <Input
                        type="number"
                        min={1}
                        max={999}
                        value={maxRounds}
                        onChange={(e) => setMaxRounds(parseInt(e.target.value) || 0)}
                        className="mt-1"
                        required
                      />
                      <HelperText>Maximum 999 rounds</HelperText>
                    </div>

                    <div className="flex flex-col justify-end">
                      <Label className="font-semibold mb-2">Visibility</Label>
                      <div className="flex items-center gap-4">
                        <span className={`text-sm ${isPublic ? 'text-muted-foreground' : 'font-medium'}`}>Private</span>
                        <Switch
                          checked={isPublic}
                          onCheckedChange={setIsPublic}
                        />
                        <span className={`text-sm ${isPublic ? 'font-medium' : 'text-muted-foreground'}`}>Public</span>
                      </div>
                      <HelperText>
                        {isPublic
                          ? 'Anyone can join this simulation'
                          : 'Only invited users can join this simulation'}
                      </HelperText>
                    </div>
                  </div>

                  <div>
                    <Label className="font-semibold">Simulation Orchestration</Label>
                    <div className="space-y-3 mt-2">
                      {progressionOptions.map((option) => (
                        <div
                          key={option.value}
                          className={`border rounded-md px-4 py-3 cursor-pointer hover:border-primary ${
                            progressionMode === option.value ? 'border-primary bg-primary/5' : 'border-border'
                          }`}
                          onClick={() => setProgressionMode(option.value)}
                        >
                          <div className="flex items-start gap-3">
                            <span className="text-md">{progressionMode === option.value ? '☒' : '☐'}</span>
                            <div>
                              <p className="font-semibold">{option.label}</p>
                              <HelperText className="mt-0">{option.description}</HelperText>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                    <HelperText>Select how rounds should progress.</HelperText>
                  </div>

                  {progressionMode === 'unsupervised' && (
                    <Alert>
                      <Info className="h-4 w-4" />
                      <AlertTitle>Unsupervised mode</AlertTitle>
                      <AlertDescription>
                        Rounds advance automatically once all users submit their orders. Use this for self-paced simulations.
                      </AlertDescription>
                    </Alert>
                  )}

                  <div>
                    <Label className="font-semibold">Description (Optional)</Label>
                    <Textarea
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      placeholder="Enter a description for your alternative"
                      className="mt-1 min-h-[140px]"
                    />
                  </div>
                </CardContent>
              </Card>

              {/* Market Demand Settings */}
              <Card>
                <CardHeader>
                  <CardTitle>Market Demand</CardTitle>
                  <p className="text-sm text-muted-foreground">Configure how customer demand evolves during the simulation</p>
                </CardHeader>
                <CardContent className="space-y-5">
                  <div>
                    <Label className="font-semibold">Demand Pattern</Label>
                    <select
                      value={demandPattern}
                      onChange={(e) => setDemandPattern(e.target.value)}
                      className="w-full mt-1 h-10 px-3 rounded-md border border-input bg-background"
                    >
                      {demandPatterns.map((pattern) => (
                        <option key={pattern.value} value={pattern.value}>
                          {pattern.label}
                        </option>
                      ))}
                    </select>
                    <HelperText>Select the demand model to use for this simulation</HelperText>
                  </div>

                  {demandPattern === 'classic' && (
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                      <div>
                        <Label className="font-semibold">Initial demand</Label>
                        <Input
                          type="number"
                          min={0}
                          value={initialDemand}
                          onChange={(e) => setInitialDemand(parseInt(e.target.value) || 0)}
                          className="mt-1"
                        />
                        <HelperText>Customer demand before the change occurs</HelperText>
                      </div>
                      <div>
                        <Label className="font-semibold">Change occurs in week</Label>
                        <Input
                          type="number"
                          min={1}
                          value={demandChangeWeek}
                          onChange={(e) => setDemandChangeWeek(parseInt(e.target.value) || 1)}
                          className="mt-1"
                        />
                        <HelperText>Week when demand switches to the new level</HelperText>
                      </div>
                      <div>
                        <Label className="font-semibold">Final demand</Label>
                        <Input
                          type="number"
                          min={0}
                          value={finalDemand}
                          onChange={(e) => setFinalDemand(parseInt(e.target.value) || 0)}
                          className="mt-1"
                        />
                        <HelperText>Customer demand after the change</HelperText>
                      </div>
                    </div>
                  )}

                  {demandPattern !== 'classic' && (
                    <p className="text-sm text-muted-foreground">
                      Additional configuration for this pattern will be added in a future update.
                    </p>
                  )}
                </CardContent>
              </Card>

              {/* Supply Chain Network */}
              <Card>
                <CardHeader>
                  <CardTitle>Supply Chain Network</CardTitle>
                  <p className="text-sm text-muted-foreground">
                    Configure node-level parameters using the active supply chain configuration.
                  </p>
                </CardHeader>
                <CardContent>
                  {loadingSupplyChain ? (
                    <div className="py-10 flex justify-center">
                      <Spinner size="lg" />
                    </div>
                  ) : supplyChainError ? (
                    <Alert variant="destructive">
                      <AlertCircle className="h-4 w-4" />
                      <AlertTitle>Unable to load supply chain</AlertTitle>
                      <AlertDescription>{supplyChainError}</AlertDescription>
                    </Alert>
                  ) : !activeSupplyChainConfig ? (
                    <p className="text-sm text-muted-foreground">
                      No supply chain configuration is linked to this group yet.
                    </p>
                  ) : (
                    <div className="space-y-5">
                      <div>
                        <Label className="font-semibold">Node Type</Label>
                        {siteTypeOptions.length > 0 ? (
                          <div className="flex flex-wrap gap-2 mt-2">
                            {siteTypeOptions.map((type) => (
                              <Button
                                key={type}
                                type="button"
                                size="sm"
                                variant={selectedSiteType === type ? 'default' : 'outline'}
                                onClick={() => setSelectedNodeType(type)}
                              >
                                {siteTypeLabels[type] || type}
                              </Button>
                            ))}
                          </div>
                        ) : (
                          <p className="text-sm text-muted-foreground mt-2">No sites available in this configuration.</p>
                        )}
                      </div>

                      {selectedSiteType ? (
                        (() => {
                          const nodes = sitesByType[selectedSiteType] || [];

                          if (selectedSiteType === 'market_demand') {
                            if (marketDemandRows.length === 0) {
                              return (
                                <p className="text-sm text-muted-foreground">
                                  No market demand records are defined for this configuration.
                                </p>
                              );
                            }
                            return (
                              <div className="overflow-x-auto">
                                <Table>
                                  <TableHeader>
                                    <TableRow>
                                      <TableHead>Item</TableHead>
                                      <TableHead>Market</TableHead>
                                      <TableHead>Demand Pattern</TableHead>
                                    </TableRow>
                                  </TableHeader>
                                  <TableBody>
                                    {marketDemandRows.map((row) => (
                                      <TableRow key={row.id}>
                                        <TableCell>{row.itemName}</TableCell>
                                        <TableCell>{row.marketName}</TableCell>
                                        <TableCell>{formatDemandPatternSummary(row.pattern, row.params)}</TableCell>
                                      </TableRow>
                                    ))}
                                  </TableBody>
                                </Table>
                                <HelperText className="mt-2">Demand patterns are defined in the linked supply chain configuration.</HelperText>
                              </div>
                            );
                          }

                          if (selectedSiteType === 'market_supply') {
                            if (marketSupplyRows.length === 0) {
                              return (
                                <p className="text-sm text-muted-foreground">
                                  No market supply sites are present in this configuration.
                                </p>
                              );
                            }
                            return (
                              <div className="space-y-4">
                                {marketSupplyRows.map(({ node, outbound }) => (
                                  <div key={node.id} className="p-4 border rounded-md">
                                    <p className="font-semibold">{node.name}</p>
                                    {outbound.length === 0 ? (
                                      <HelperText>No outbound lanes configured.</HelperText>
                                    ) : (
                                      <div className="space-y-1 mt-2">
                                        {outbound.map((lane) => {
                                          const downstream = sitesById.get(lane.to_site_id);
                                          return (
                                            <p key={lane.id} className="text-sm">
                                              Supplies <strong>{downstream?.name || lane.to_site_id}</strong> • Lead time {formatLeadTimeRange(lane.lead_time_days)}
                                            </p>
                                          );
                                        })}
                                      </div>
                                    )}
                                    <HelperText>Market supply sites provide infinite supply with the configured lead times.</HelperText>
                                  </div>
                                ))}
                              </div>
                            );
                          }

                          if (nodes.length === 0) {
                            return <p className="text-sm text-muted-foreground">No sites of this type are defined.</p>;
                          }

                          return (
                            <div className="space-y-4">
                              {nodes.map((node) => {
                                const nodeKey = normalizeSiteName(node?.name);
                                const bounds = sitePolicyBounds[nodeKey] || {};
                                const orderLeadRange = normalizeRange(bounds.order_leadtime);
                                const shipRange = normalizeRange(bounds.supply_leadtime);
                                const initInventoryRange = normalizeRange(bounds.init_inventory);
                                const minOrderRange = normalizeRange(bounds.min_order_qty);
                                const variableCostRange = normalizeRange(bounds.variable_cost);
                                const orderLeadRangeLabel = formatRangeIndicator(bounds.order_leadtime, { decimals: 0 });
                                const shipRangeLabel = formatRangeIndicator(bounds.supply_leadtime, { decimals: 0 });
                                const initInventoryRangeLabel = formatRangeIndicator(bounds.init_inventory, { decimals: 0 });
                                const minOrderRangeLabel = formatRangeIndicator(bounds.min_order_qty, { decimals: 0 });
                                const variableCostRangeLabel = formatRangeIndicator(bounds.variable_cost, { decimals: 2 });

                                return (
                                  <div key={node.id} className="p-4 border rounded-md">
                                    <p className="font-semibold mb-2">{node.name}</p>
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                      <div>
                                        <Label className="font-semibold text-sm">Information Delay (weeks)</Label>
                                        <div className="flex items-center gap-3 mt-1">
                                          <Input
                                            type="number"
                                            min={orderLeadRange.min ?? 0}
                                            max={orderLeadRange.max ?? 12}
                                            step={1}
                                            value={getPolicyValue(nodeKey, 'order_leadtime')}
                                            onChange={handleNodePolicyNumberChange(nodeKey, 'order_leadtime')}
                                            className="flex-1"
                                          />
                                          <span className="text-sm text-muted-foreground min-w-[84px] text-right whitespace-nowrap">{orderLeadRangeLabel}</span>
                                        </div>
                                        {describeRange(bounds.order_leadtime, 'weeks') && (
                                          <HelperText>Allowed: {describeRange(bounds.order_leadtime, 'weeks')}</HelperText>
                                        )}
                                      </div>
                                      <div>
                                        <Label className="font-semibold text-sm">Shipment Delay (weeks)</Label>
                                        <div className="flex items-center gap-3 mt-1">
                                          <Input
                                            type="number"
                                            min={shipRange.min ?? 0}
                                            max={shipRange.max ?? 12}
                                            step={1}
                                            value={getPolicyValue(nodeKey, 'supply_leadtime')}
                                            onChange={handleNodePolicyNumberChange(nodeKey, 'supply_leadtime')}
                                            className="flex-1"
                                          />
                                          <span className="text-sm text-muted-foreground min-w-[84px] text-right whitespace-nowrap">{shipRangeLabel}</span>
                                        </div>
                                        {describeRange(bounds.supply_leadtime, 'weeks') && (
                                          <HelperText>Allowed: {describeRange(bounds.supply_leadtime, 'weeks')}</HelperText>
                                        )}
                                      </div>
                                      <div>
                                        <Label className="font-semibold text-sm">Initial Inventory</Label>
                                        <div className="flex items-center gap-3 mt-1">
                                          <Input
                                            type="number"
                                            min={initInventoryRange.min ?? 0}
                                            max={initInventoryRange.max ?? 9999}
                                            step={1}
                                            value={getPolicyValue(nodeKey, 'init_inventory')}
                                            onChange={handleNodePolicyNumberChange(nodeKey, 'init_inventory')}
                                            className="flex-1"
                                          />
                                          <span className="text-sm text-muted-foreground min-w-[84px] text-right whitespace-nowrap">{initInventoryRangeLabel}</span>
                                        </div>
                                        {describeRange(bounds.init_inventory, 'units') && (
                                          <HelperText>Allowed: {describeRange(bounds.init_inventory, 'units')}</HelperText>
                                        )}
                                      </div>
                                      <div>
                                        <Label className="font-semibold text-sm">Minimum Order Quantity</Label>
                                        <div className="flex items-center gap-3 mt-1">
                                          <Input
                                            type="number"
                                            min={minOrderRange.min ?? 0}
                                            max={minOrderRange.max ?? 9999}
                                            step={1}
                                            value={getPolicyValue(nodeKey, 'min_order_qty')}
                                            onChange={handleNodePolicyNumberChange(nodeKey, 'min_order_qty')}
                                            className="flex-1"
                                          />
                                          <span className="text-sm text-muted-foreground min-w-[84px] text-right whitespace-nowrap">{minOrderRangeLabel}</span>
                                        </div>
                                        {describeRange(bounds.min_order_qty, 'units') && (
                                          <HelperText>Allowed: {describeRange(bounds.min_order_qty, 'units')}</HelperText>
                                        )}
                                      </div>
                                      <div>
                                        <Label className="font-semibold text-sm">Variable Cost</Label>
                                        <div className="flex items-center gap-3 mt-1">
                                          <Input
                                            type="number"
                                            min={variableCostRange.min ?? 0}
                                            max={variableCostRange.max ?? 1000}
                                            step={0.1}
                                            value={getPolicyValue(nodeKey, 'variable_cost')}
                                            onChange={handleNodePolicyNumberChange(nodeKey, 'variable_cost')}
                                            className="flex-1"
                                          />
                                          <span className="text-sm text-muted-foreground min-w-[84px] text-right whitespace-nowrap">{variableCostRangeLabel}</span>
                                        </div>
                                        {describeRange(bounds.variable_cost, 'cost') && (
                                          <HelperText>Suggested range: {describeRange(bounds.variable_cost)}</HelperText>
                                        )}
                                      </div>
                                    </div>
                                    <HelperText className="mt-2">Selling prices are configured on the Pricing tab.</HelperText>
                                  </div>
                                );
                              })}
                            </div>
                          );
                        })()
                      ) : (
                        <p className="text-sm text-muted-foreground">Select a node type to view details.</p>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>

              {showAutonomySharingCard && (
                <Card>
                  <CardHeader>
                    <CardTitle>Autonomy Strategist Sharing</CardTitle>
                    <p className="text-sm text-muted-foreground">
                      Choose which information the Autonomy Strategist can see when any role uses an Autonomy LLM strategy.
                    </p>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="flex items-center space-x-2">
                      <Checkbox
                        id="demand-history"
                        checked={autonomyLlmConfig.toggles.customer_demand_history_sharing}
                        onCheckedChange={handleAutonomyToggleChange('customer_demand_history_sharing')}
                      />
                      <label htmlFor="demand-history" className="text-sm cursor-pointer">
                        Share retailer demand history with upstream roles
                      </label>
                    </div>
                    <div className="flex items-center space-x-2">
                      <Checkbox
                        id="volatility"
                        checked={autonomyLlmConfig.toggles.volatility_signal_sharing}
                        onCheckedChange={handleAutonomyToggleChange('volatility_signal_sharing')}
                      />
                      <label htmlFor="volatility" className="text-sm cursor-pointer">
                        Share volatility signal (variance + trend) from the retailer
                      </label>
                    </div>
                    <div className="flex items-center space-x-2">
                      <Checkbox
                        id="downstream-visibility"
                        checked={autonomyLlmConfig.toggles.downstream_inventory_visibility}
                        onCheckedChange={handleAutonomyToggleChange('downstream_inventory_visibility')}
                      />
                      <label htmlFor="downstream-visibility" className="text-sm cursor-pointer">
                        Allow visibility into the immediate downstream inventory/backlog
                      </label>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Disable a toggle to keep the strategist limited to local information for that scope.
                    </p>
                  </CardContent>
                </Card>
              )}

              {isEditing && (
                <Card>
                  <CardHeader>
                    <CardTitle>Current Alternative Snapshot</CardTitle>
                    <p className="text-sm text-muted-foreground">
                      Review the configuration currently saved for this alternative.
                    </p>
                  </CardHeader>
                  <CardContent className="space-y-5">
                    <div>
                      <h4 className="text-sm font-semibold mb-2">Alternative Overview</h4>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        {overviewItems.map((item) => (
                          <div key={item.label}>
                            <p className="text-xs text-muted-foreground uppercase tracking-wider">{item.label}</p>
                            <p className="text-sm font-medium">{item.value}</p>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div>
                      <h4 className="text-sm font-semibold mb-2">Global Policy</h4>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        {globalPolicyItems.map((item) => (
                          <div key={item.label}>
                            <p className="text-xs text-muted-foreground uppercase tracking-wider">{item.label}</p>
                            <p className="text-sm font-medium">{item.value}</p>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div>
                      <h4 className="text-sm font-semibold mb-2">System Constraints</h4>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        {systemConstraintItems.map((item) => (
                          <div key={item.label}>
                            <p className="text-xs text-muted-foreground uppercase tracking-wider">{item.label}</p>
                            <p className="text-sm font-medium">{item.value}</p>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div>
                      <h4 className="text-sm font-semibold mb-2">Users</h4>
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Role</TableHead>
                            <TableHead>Assignment</TableHead>
                            <TableHead>Strategy</TableHead>
                            <TableHead>Demand Visibility</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {playerSummaryRows.map((row) => (
                            <TableRow key={row.roleKey}>
                              <TableCell>{row.roleLabel}</TableCell>
                              <TableCell>
                                <p className="font-medium">{row.assignmentLabel}</p>
                                <p className="text-xs text-muted-foreground">{row.typeLabel}</p>
                              </TableCell>
                              <TableCell>
                                <p className="font-medium">{row.strategyLabel}</p>
                                {row.llmModel && (
                                  <p className="text-xs text-muted-foreground">LLM: {row.llmModel}</p>
                                )}
                                {row.overridePct && (
                                  <p className="text-xs text-muted-foreground">Override ±{row.overridePct}</p>
                                )}
                              </TableCell>
                              <TableCell>{row.canSeeDemand ? 'Yes' : 'No'}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>

                    <div>
                      <h4 className="text-sm font-semibold mb-2">Role Parameters</h4>
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Role</TableHead>
                            <TableHead>Info Delay</TableHead>
                            <TableHead>Ship Delay</TableHead>
                            <TableHead>Initial Inventory</TableHead>
                            <TableHead>Price</TableHead>
                            <TableHead>Standard Cost</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {roleParameterRows.map((row) => (
                            <TableRow key={row.roleKey}>
                              <TableCell>{row.roleLabel}</TableCell>
                              <TableCell>{formatWeeks(row.orderLeadtime)}</TableCell>
                              <TableCell>{formatWeeks(row.supplyLeadTime)}</TableCell>
                              <TableCell>{formatNumber(row.initInventory)}</TableCell>
                              <TableCell>{formatCurrency(row.price)}</TableCell>
                              <TableCell>{formatCurrency(row.standardCost)}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  </CardContent>
                </Card>
              )}
            </TabsContent>

            <TabsContent value="pricing" className="mt-6">
              <div className="flex justify-end mb-3">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    const priceMid = (k) => {
                      const r = systemConfig[k] || {};
                      const min = Number(r.min ?? 0);
                      const max = Number(r.max ?? 0) || min;
                      return min + (max - min) / 2;
                    };
                    const p = Math.round(priceMid('price') * 100) / 100;
                    const stdMin = Number(systemConfig.standard_cost?.min ?? 0);
                    const std = Math.max(stdMin, Math.round(p * 0.8 * 100) / 100);
                    setPricingConfig({
                      retailer: { selling_price: p, standard_cost: std },
                      wholesaler: { selling_price: p, standard_cost: std },
                      distributor: { selling_price: p, standard_cost: std },
                      manufacturer: { selling_price: p, standard_cost: std },
                    });
                  }}
                >
                  Reset Pricing to Server Defaults
                </Button>
              </div>
              <PricingConfigForm pricingConfig={pricingConfig} onChange={setPricingConfig} />
            </TabsContent>

            <TabsContent value="players" className="mt-6">
              <Card>
                <CardHeader>
                  <CardTitle>User Configuration</CardTitle>
                  <p className="text-sm text-muted-foreground">
                    Configure users and AI agents for each role
                  </p>
                </CardHeader>
                <CardContent className="space-y-6">
                  {players.map((player, index) => {
                    const selectedStrategy = player.strategy || agentStrategies[0].options[0].value;
                    const badgeLabel =
                      player.playerType === 'human'
                        ? 'Human User'
                        : getStrategyLabel(selectedStrategy);
                    const isAutonomySelection =
                      player.playerType === 'ai' &&
                      ['AUTONOMY_DTCE', 'AUTONOMY_DTCE_CENTRAL', 'AUTONOMY_DTCE_GLOBAL'].includes(selectedStrategy);
                    const autonomyTrainingLocked =
                      isAutonomySelection && !(modelStatus && modelStatus.is_trained);
                    const humanHelper = 'Assign a user to control this role.';
                    const agentHelper =
                      strategyDescriptions[selectedStrategy] || 'AI agent will manage ordering for this role.';
                    const agentHelperText = autonomyTrainingLocked
                      ? `${agentHelper} Training must complete before using Autonomy agents.`
                      : agentHelper;

                    return (
                      <div
                        key={player.role}
                        className="w-full p-5 border rounded-lg hover:shadow-md hover:-translate-y-0.5 transition-all"
                      >
                        <div className="space-y-4">
                          <div className="flex justify-between items-start">
                            <div>
                              <div className="flex items-center gap-3">
                                <span className="text-lg font-semibold">
                                  {player.displayName || player.role}
                                </span>
                                {player.role === 'retailer' && (
                                  <Badge variant="info">Required</Badge>
                                )}
                              </div>
                              <div className="flex items-center gap-2 mt-1">
                                <Badge variant="secondary" className="text-xs">
                                  Role: {player.role}
                                </Badge>
                                <Badge
                                  variant={player.playerType === 'human' ? 'success' : 'default'}
                                >
                                  {badgeLabel}
                                </Badge>
                              </div>
                            </div>
                          </div>

                          <div>
                            <Label className="font-semibold">Participant Type</Label>
                            <div className="flex gap-3 mt-2">
                              <Button
                                type="button"
                                variant={player.playerType === 'human' ? 'default' : 'outline'}
                                onClick={() => handlePlayerTypeChange(index, 'human')}
                                size="sm"
                                className={player.playerType === 'human' ? 'bg-green-600 hover:bg-green-700' : ''}
                              >
                                Human
                              </Button>
                              <Button
                                type="button"
                                variant={player.playerType === 'ai' ? 'default' : 'outline'}
                                onClick={() => handlePlayerTypeChange(index, 'ai')}
                                size="sm"
                                className={player.playerType === 'ai' ? 'bg-purple-600 hover:bg-purple-700' : ''}
                              >
                                Agent
                              </Button>
                            </div>
                            <HelperText>
                              {player.playerType === 'human' ? humanHelper : agentHelper}
                            </HelperText>
                          </div>

                          {player.playerType === 'ai' && (
                            <div>
                              <Label className="font-semibold">Agent Strategy</Label>
                              <select
                                value={selectedStrategy}
                                onChange={(e) => handleStrategyChange(index, e.target.value)}
                                className="w-full mt-1 h-10 px-3 rounded-md border border-input bg-background"
                              >
                                {agentStrategies.map((group, groupIndex) => (
                                  <optgroup key={groupIndex} label={group.group}>
                                    {group.options.map((option) => (
                                      <option
                                        key={option.value}
                                        value={option.value}
                                        disabled={option.requiresModel && !(modelStatus && modelStatus.is_trained)}
                                      >
                                        {option.label}
                                      </option>
                                    ))}
                                  </optgroup>
                                ))}
                              </select>
                              <HelperText>{agentHelperText}</HelperText>
                            </div>
                          )}

                          {player.playerType === 'ai' && (
                            <div className="space-y-3">
                              {String(player.strategy).startsWith('LLM_') && (
                                <div>
                                  <Label className="font-semibold">Choose Autonomy LLM</Label>
                                  <select
                                    value={player.llmModel}
                                    onChange={(e) =>
                                      setPlayers((prev) =>
                                        prev.map((p, i) => (i === index ? { ...p, llmModel: e.target.value } : p))
                                      )
                                    }
                                    className="w-full mt-1 h-10 px-3 rounded-md border border-input bg-background"
                                  >
                                    {LLM_BASE_MODEL_OPTIONS.map((option) => (
                                      <option key={option.value} value={option.value}>
                                        {option.label}
                                      </option>
                                    ))}
                                  </select>
                                  <HelperText>Pick the Autonomy LLM backend for this agent.</HelperText>
                                </div>
                              )}

                              {['AUTONOMY_DTCE_CENTRAL', 'LLM_SUPERVISED'].includes(player.strategy) && (
                                <div>
                                  <Label className="font-semibold">Supervisor Override (±%)</Label>
                                  <Input
                                    type="number"
                                    min={5}
                                    max={50}
                                    step={1}
                                    value={clampOverridePercent(player.autonomyOverridePct)}
                                    onChange={(e) => {
                                      const raw = parseFloat(e.target.value);
                                      const next = clampOverridePercent(
                                        Number.isFinite(raw) ? raw : player.autonomyOverridePct
                                      );
                                      setPlayers((prev) =>
                                        prev.map((p, i) =>
                                          i === index ? { ...p, autonomyOverridePct: next } : p
                                        )
                                      );
                                    }}
                                    className="mt-1"
                                  />
                                  <HelperText>
                                    Supervisor may adjust the Autonomy recommendation by up to this percentage.
                                  </HelperText>
                                </div>
                              )}
                            </div>
                          )}

                          {player.playerType === 'human' && (
                            <div>
                              <Label className="font-semibold">Assign User</Label>
                              <select
                                value={player.userId || ''}
                                onChange={(e) => handleUserChange(index, e.target.value || null)}
                                disabled={loadingUsers}
                                className="w-full mt-1 h-10 px-3 rounded-md border border-input bg-background disabled:opacity-50"
                              >
                                <option value="">-- Select User --</option>
                                {availableUsers.map((u) => (
                                  <option
                                    key={u.id}
                                    value={u.id}
                                    disabled={players.some(p => p.userId === u.id && p.role !== player.role)}
                                  >
                                    {u.username} {resolveUserType(u) === 'systemadmin' ? '(Admin)' : ''}
                                    {players.some(p => p.userId === u.id && p.role !== player.role) ? ' (Assigned)' : ''}
                                  </option>
                                ))}
                              </select>
                              <HelperText>
                                {loadingUsers
                                  ? 'Loading users...'
                                  : player.userId
                                    ? `Assigned to: ${availableUsers.find(u => u.id === player.userId)?.username || 'Unknown'}`
                                    : 'Select a user to assign to this role'}
                              </HelperText>
                            </div>
                          )}

                          <div className="flex items-center space-x-3">
                            <Switch
                              id={`demand-${index}`}
                              checked={player.canSeeDemand}
                              onCheckedChange={(checked) => handleCanSeeDemandChange(index, checked)}
                              disabled={player.role === 'retailer'}
                            />
                            <Label
                              htmlFor={`demand-${index}`}
                              className={`font-semibold ${player.role === 'retailer' ? 'opacity-70' : ''}`}
                            >
                              Can see customer demand
                              {player.role === 'retailer' && ' (Always enabled for Retailer)'}
                            </Label>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>

          {/* Action Buttons */}
          <div className="flex justify-end gap-4 mt-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => navigate('/alternatives')}
              disabled={isLoading}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isLoading}>
              {isLoading ? (isEditing ? 'Saving...' : 'Creating...') : (isEditing ? 'Save Changes' : 'Create Alternative')}
            </Button>
          </div>
        </form>
      </div>
    </PageLayout>
  );
};

export default CreateMixedGame;
