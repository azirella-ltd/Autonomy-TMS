/**
 * Scenario Events Workspace
 *
 * Inject supply chain events (Kinaxis-style what-if analysis) into scenario branches.
 * Events modify data within a scenario; CDC/TRM cascade detects and responds.
 *
 * Layout:
 *   Left panel:  Event catalog (categorized, searchable)
 *   Center:      Event injection form (dynamic per type)
 *   Right panel: Event timeline (injected events + CDC responses)
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Zap, AlertTriangle, TrendingUp, Truck, Globe,
  ShoppingCart, Factory, Package, ArrowRight, Undo2,
  ChevronRight, Clock, CheckCircle2, XCircle,
} from 'lucide-react';
import { cn } from '../lib/utils/cn';
import { useAuth } from '../contexts/AuthContext';
import { useActiveConfig } from '../contexts/ActiveConfigContext';
import api from '../services/api';

// Category icons
const CATEGORY_ICONS = {
  demand: ShoppingCart,
  supply: Package,
  capacity: Factory,
  logistics: Truck,
  macro: Globe,
};

const CATEGORY_COLORS = {
  demand: 'text-blue-600 bg-blue-50 border-blue-200',
  supply: 'text-amber-600 bg-amber-50 border-amber-200',
  capacity: 'text-red-600 bg-red-50 border-red-200',
  logistics: 'text-purple-600 bg-purple-50 border-purple-200',
  macro: 'text-emerald-600 bg-emerald-50 border-emerald-200',
};

export default function ScenarioEvents() {
  const { user } = useAuth();
  const { activeConfigId } = useActiveConfig();
  const location = useLocation();
  const navigate = useNavigate();

  const [catalog, setCatalog] = useState(null);
  const [entities, setEntities] = useState(null);
  const [events, setEvents] = useState([]);
  const [selectedType, setSelectedType] = useState(null);
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [formValues, setFormValues] = useState({});
  const [scenarioName, setScenarioName] = useState('');
  const [injecting, setInjecting] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  const configId = location.state?.configId || activeConfigId;

  // Load catalog
  useEffect(() => {
    api.get('/scenario-events/catalog')
      .then(res => setCatalog(res.data))
      .catch(err => console.error('Failed to load event catalog:', err));
  }, []);

  // Load entities and existing events when config changes
  useEffect(() => {
    if (!configId) return;
    api.get(`/scenario-events/config/${configId}/entities`)
      .then(res => setEntities(res.data))
      .catch(err => console.error('Failed to load entities:', err));
    api.get(`/scenario-events/config/${configId}/events`)
      .then(res => setEvents(res.data))
      .catch(err => console.error('Failed to load events:', err));
  }, [configId]);

  const handleSelectType = useCallback((categoryKey, typeKey, typeDef) => {
    setSelectedCategory(categoryKey);
    setSelectedType({ key: typeKey, ...typeDef });
    setFormValues({});
    setScenarioName(`What-if: ${typeDef.label}`);
    setError(null);
    setSuccess(null);
  }, []);

  const handleFormChange = useCallback((key, value) => {
    setFormValues(prev => ({ ...prev, [key]: value }));
  }, []);

  const handleInject = useCallback(async () => {
    if (!configId || !selectedType) return;
    setInjecting(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await api.post(`/scenario-events/config/${configId}/inject`, {
        event_type: selectedType.key,
        parameters: formValues,
        scenario_name: scenarioName || undefined,
      });
      const result = response.data;
      setSuccess(result.summary || 'Event injected successfully');
      setEvents(prev => [result, ...prev]);
      setFormValues({});
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Injection failed');
    } finally {
      setInjecting(false);
    }
  }, [configId, selectedType, formValues, scenarioName]);

  const handleRevert = useCallback(async (eventId) => {
    try {
      await api.post(`/scenario-events/events/${eventId}/revert`);
      setEvents(prev => prev.map(e =>
        e.id === eventId ? { ...e, status: 'REVERTED', reverted_at: new Date().toISOString() } : e
      ));
    } catch (err) {
      setError(err.response?.data?.detail || 'Revert failed');
    }
  }, []);

  // Resolve select options from entities
  const getOptions = useCallback((source) => {
    if (!entities) return [];
    return entities[source] || [];
  }, [entities]);

  if (!configId) {
    return (
      <div className="p-8 text-center text-muted-foreground">
        No supply chain configuration selected. Please select a configuration first.
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-4rem)] overflow-hidden">
      {/* LEFT: Event Catalog */}
      <div className="w-72 border-r bg-muted/30 overflow-y-auto flex-shrink-0">
        <div className="p-4 border-b">
          <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <Zap className="h-4 w-4 text-violet-500" />
            Event Catalog
          </h2>
          <p className="text-xs text-muted-foreground mt-1">
            Select an event type to inject into the scenario
          </p>
        </div>

        {catalog && Object.entries(catalog).map(([catKey, cat]) => {
          const CatIcon = CATEGORY_ICONS[catKey] || AlertTriangle;
          const colorClass = CATEGORY_COLORS[catKey] || '';
          return (
            <div key={catKey} className="border-b">
              <div className={cn('px-4 py-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider', colorClass.split(' ')[0])}>
                <CatIcon className="h-3.5 w-3.5" />
                {cat.label}
              </div>
              {Object.entries(cat.types).map(([typeKey, typeDef]) => (
                <button
                  key={typeKey}
                  onClick={() => handleSelectType(catKey, typeKey, typeDef)}
                  className={cn(
                    'w-full text-left px-4 py-2.5 text-sm transition-colors',
                    'hover:bg-accent/60 border-l-2',
                    selectedType?.key === typeKey
                      ? 'bg-accent border-l-violet-500 font-medium'
                      : 'border-l-transparent',
                  )}
                >
                  <div className="font-medium text-foreground">{typeDef.label}</div>
                  <div className="text-xs text-muted-foreground mt-0.5">{typeDef.description}</div>
                </button>
              ))}
            </div>
          );
        })}
      </div>

      {/* CENTER: Injection Form */}
      <div className="flex-1 overflow-y-auto p-6">
        {!selectedType ? (
          <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
            <Zap className="h-12 w-12 mb-4 opacity-20" />
            <p className="text-lg font-medium">Select an event type</p>
            <p className="text-sm mt-1">Choose from the catalog on the left to begin</p>
            <p className="text-xs mt-4 max-w-md text-center">
              Or use <span className="font-medium text-violet-600">Azirella</span> — try
              "what if Bigmart places a rush order for 500 C900 bikes"
            </p>
          </div>
        ) : (
          <div className="max-w-xl mx-auto">
            {/* Header */}
            <div className={cn('rounded-lg border p-4 mb-6', CATEGORY_COLORS[selectedCategory])}>
              <div className="flex items-center gap-2">
                {React.createElement(CATEGORY_ICONS[selectedCategory] || Zap, { className: 'h-5 w-5' })}
                <h3 className="text-lg font-semibold">{selectedType.label}</h3>
              </div>
              <p className="text-sm mt-1 opacity-80">{selectedType.description}</p>
              {selectedType.triggers && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {selectedType.triggers.map(t => (
                    <span key={t} className="text-[10px] px-1.5 py-0.5 rounded bg-white/50 font-mono">
                      {t}
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* Scenario Name */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-foreground mb-1">
                Scenario Name
              </label>
              <input
                type="text"
                value={scenarioName}
                onChange={e => setScenarioName(e.target.value)}
                className="w-full px-3 py-2 border rounded-md text-sm bg-background"
                placeholder="What-if: ..."
              />
              <p className="text-xs text-muted-foreground mt-1">
                A new scenario branch will be created from the current baseline
              </p>
            </div>

            {/* Dynamic Parameters */}
            {selectedType.parameters?.map(param => (
              <div key={param.key} className="mb-4">
                <label className="block text-sm font-medium text-foreground mb-1">
                  {param.label}
                  {param.required && <span className="text-red-500 ml-1">*</span>}
                </label>

                {param.type === 'select' && param.source ? (
                  <select
                    value={formValues[param.key] || ''}
                    onChange={e => handleFormChange(param.key, e.target.value)}
                    className="w-full px-3 py-2 border rounded-md text-sm bg-background"
                  >
                    <option value="">Select...</option>
                    {getOptions(param.source).map(opt => (
                      <option key={opt.id} value={opt.id}>
                        {opt.name}
                      </option>
                    ))}
                  </select>
                ) : param.type === 'select' && param.options ? (
                  <select
                    value={formValues[param.key] || param.default || ''}
                    onChange={e => handleFormChange(param.key, e.target.value)}
                    className="w-full px-3 py-2 border rounded-md text-sm bg-background"
                  >
                    <option value="">Select...</option>
                    {param.options.map(opt => (
                      <option key={opt} value={opt}>{opt}</option>
                    ))}
                  </select>
                ) : param.type === 'number' ? (
                  <input
                    type="number"
                    value={formValues[param.key] || ''}
                    onChange={e => handleFormChange(param.key, e.target.value)}
                    className="w-full px-3 py-2 border rounded-md text-sm bg-background"
                    placeholder={`Enter ${param.label.toLowerCase()}`}
                  />
                ) : param.type === 'date' ? (
                  <input
                    type="date"
                    value={formValues[param.key] || ''}
                    onChange={e => handleFormChange(param.key, e.target.value)}
                    className="w-full px-3 py-2 border rounded-md text-sm bg-background"
                  />
                ) : (
                  <input
                    type="text"
                    value={formValues[param.key] || ''}
                    onChange={e => handleFormChange(param.key, e.target.value)}
                    className="w-full px-3 py-2 border rounded-md text-sm bg-background"
                    placeholder={`Enter ${param.label.toLowerCase()}`}
                  />
                )}
              </div>
            ))}

            {/* Error / Success */}
            {error && (
              <div className="mb-4 p-3 rounded-md bg-red-50 border border-red-200 text-red-700 text-sm flex items-start gap-2">
                <XCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
                {error}
              </div>
            )}
            {success && (
              <div className="mb-4 p-3 rounded-md bg-emerald-50 border border-emerald-200 text-emerald-700 text-sm flex items-start gap-2">
                <CheckCircle2 className="h-4 w-4 mt-0.5 flex-shrink-0" />
                {success}
              </div>
            )}

            {/* Inject Button */}
            <button
              onClick={handleInject}
              disabled={injecting}
              className={cn(
                'w-full py-3 rounded-md text-sm font-semibold flex items-center justify-center gap-2 transition-colors',
                injecting
                  ? 'bg-muted text-muted-foreground cursor-not-allowed'
                  : 'bg-violet-600 text-white hover:bg-violet-700',
              )}
            >
              {injecting ? (
                <>Injecting...</>
              ) : (
                <>
                  <Zap className="h-4 w-4" />
                  Inject Event
                  <ArrowRight className="h-4 w-4" />
                </>
              )}
            </button>

            <p className="text-xs text-muted-foreground text-center mt-3">
              This creates a scenario branch and triggers CDC condition checks.
              Results appear in the Decision Stream.
            </p>
          </div>
        )}
      </div>

      {/* RIGHT: Event Timeline */}
      <div className="w-80 border-l bg-muted/20 overflow-y-auto flex-shrink-0">
        <div className="p-4 border-b">
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <Clock className="h-4 w-4" />
            Event Timeline
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            {events.length} event{events.length !== 1 ? 's' : ''} in this scenario
          </p>
        </div>

        {events.length === 0 ? (
          <div className="p-4 text-center text-xs text-muted-foreground">
            No events injected yet
          </div>
        ) : (
          <div className="divide-y">
            {events.map(event => {
              const colorClass = CATEGORY_COLORS[event.category] || '';
              const isReverted = event.status === 'REVERTED';
              return (
                <div key={event.id} className={cn('p-3', isReverted && 'opacity-50')}>
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <span className={cn(
                        'inline-block text-[10px] font-semibold px-1.5 py-0.5 rounded',
                        colorClass,
                      )}>
                        {event.category}
                      </span>
                      <div className="text-sm font-medium mt-1">{event.label}</div>
                    </div>
                    {!isReverted && (
                      <button
                        onClick={() => handleRevert(event.id)}
                        className="text-muted-foreground hover:text-red-500 transition-colors p-1"
                        title="Revert event"
                      >
                        <Undo2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">{event.summary}</p>
                  {event.cdc_triggered?.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1.5">
                      {event.cdc_triggered.map((t, i) => (
                        <span key={i} className="text-[9px] px-1 py-0.5 rounded bg-orange-100 text-orange-700 font-mono">
                          {t}
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="flex items-center gap-2 mt-1.5 text-[10px] text-muted-foreground">
                    <Clock className="h-3 w-3" />
                    {event.created_at ? new Date(event.created_at).toLocaleTimeString() : ''}
                    {isReverted && (
                      <span className="text-red-500 font-medium">REVERTED</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
