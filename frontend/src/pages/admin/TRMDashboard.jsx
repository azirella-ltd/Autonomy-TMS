/**
 * TRM Dashboard Page
 *
 * Main dashboard for TRM (Tiny Recursive Model) management.
 * Combines training, model management, and testing functionality.
 */

import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  Card,
  CardContent,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
  Alert,
  Badge,
  Button,
} from '../../components/common';
import {
  GraduationCap,
  Database,
  FlaskConical,
  CheckCircle,
  AlertTriangle,
  AlertCircle,
  Play,
  ChevronRight,
} from 'lucide-react';
import TRMTrainingPanel from '../../components/admin/TRMTrainingPanelEnhanced';
import TRMModelManager from '../../components/admin/TRMModelManager';
import TRMTestPanel from '../../components/admin/TRMTestPanel';
import { getModelInfo, listCheckpoints, loadModel } from '../../services/trmApi';

const TRMDashboard = () => {
  const [currentTab, setCurrentTab] = useState('training');
  const [modelInfo, setModelInfo] = useState(null);
  const [checkpoints, setCheckpoints] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingModel, setLoadingModel] = useState(false);

  useEffect(() => {
    loadStatus();
  }, []);

  const loadStatus = async () => {
    setLoading(true);
    try {
      const [info, cpResponse] = await Promise.all([
        getModelInfo(),
        listCheckpoints()
      ]);
      setModelInfo(info);
      setCheckpoints(cpResponse.checkpoints || []);
    } catch (err) {
      console.error('Failed to load TRM status:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleQuickLoad = async () => {
    const bestCheckpoint = checkpoints.find(c => c.name?.includes('best')) || checkpoints[0];
    if (!bestCheckpoint) return;

    setLoadingModel(true);
    try {
      const info = await loadModel(bestCheckpoint.path, 'cpu');
      setModelInfo(info);
    } catch (err) {
      console.error('Failed to load model:', err);
    } finally {
      setLoadingModel(false);
    }
  };

  const handleTabChange = (value) => {
    setCurrentTab(value);
    loadStatus();
  };

  const getOverallStatus = () => {
    const hasCheckpoints = checkpoints.length > 0;
    const isLoaded = modelInfo?.model_loaded;
    const usingFallback = modelInfo?.use_fallback;

    if (isLoaded && !usingFallback) {
      return { level: 'success', message: 'Ready', detail: 'TRM model loaded and active for agent decisions' };
    } else if (hasCheckpoints && !isLoaded) {
      return { level: 'warning', message: 'Trained but not loaded', detail: 'Checkpoints available. Load a model to use TRM for agent decisions.' };
    } else if (!hasCheckpoints) {
      return { level: 'info', message: 'Not trained', detail: 'No checkpoints found. Train the model first.' };
    } else if (usingFallback) {
      return { level: 'warning', message: 'Using fallback', detail: 'TRM using heuristic fallback. Load a trained model for better performance.' };
    }
    return { level: 'info', message: 'Unknown', detail: 'Unable to determine status' };
  };

  const status = getOverallStatus();

  const getStatusIcon = () => {
    if (status.level === 'success') return <CheckCircle className="h-4 w-4" />;
    if (status.level === 'warning') return <AlertTriangle className="h-4 w-4" />;
    return <AlertCircle className="h-4 w-4" />;
  };

  const getStatusVariant = () => {
    if (status.level === 'success') return 'success';
    if (status.level === 'warning') return 'warning';
    return 'info';
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      {/* Breadcrumbs */}
      <nav className="flex items-center gap-2 text-sm text-muted-foreground mb-4">
        <Link to="/" className="hover:text-foreground">Home</Link>
        <ChevronRight className="h-4 w-4" />
        <Link to="/admin?section=training" className="hover:text-foreground">AI & Agents</Link>
        <ChevronRight className="h-4 w-4" />
        <span className="text-foreground">AI Agent Training</span>
      </nav>

      <div className="mb-6">
        <h1 className="text-3xl font-bold mb-2">Execution Agents</h1>
        <p className="text-muted-foreground">
          Execution / Site / Role — 11 narrow decision agents per site, sub-10ms inference.
        </p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {['ATP', 'PO Creation', 'MO Execution', 'TO Execution', 'Rebalancing',
            'Buffer Adj.', 'Order Tracking', 'Quality', 'Maintenance', 'Subcontracting', 'Forecast Adj.'].map(name => (
            <span key={name} className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-violet-50 text-violet-700 border border-violet-200">
              {name}
            </span>
          ))}
        </div>
      </div>

      {/* Status Banner */}
      {!loading && (
        <Alert variant={getStatusVariant()} className="mb-6">
          <div className="flex items-center justify-between w-full">
            <div className="flex items-center gap-3">
              {getStatusIcon()}
              <Badge variant={status.level === 'success' ? 'success' : status.level === 'warning' ? 'warning' : 'secondary'}>
                {status.message}
              </Badge>
              <span className="text-sm">{status.detail}</span>
              {modelInfo?.model_loaded && (
                <Badge variant="outline">Device: {modelInfo.device?.toUpperCase()}</Badge>
              )}
              {checkpoints.length > 0 && (
                <Badge variant="outline">{checkpoints.length} checkpoint{checkpoints.length !== 1 ? 's' : ''}</Badge>
              )}
            </div>
            {status.level === 'warning' && checkpoints.length > 0 && !modelInfo?.model_loaded && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleQuickLoad}
                disabled={loadingModel}
                leftIcon={<Play className="h-4 w-4" />}
              >
                {loadingModel ? 'Loading...' : 'Quick Load Best Model'}
              </Button>
            )}
          </div>
        </Alert>
      )}

      <Card className="mb-6">
        <Tabs value={currentTab} onValueChange={handleTabChange}>
          <TabsList className="w-full justify-start border-b rounded-none h-auto p-0">
            <TabsTrigger
              value="training"
              className="flex items-center gap-2 rounded-none border-b-2 border-transparent data-[state=active]:border-primary"
            >
              <GraduationCap className="h-4 w-4" />
              Training
            </TabsTrigger>
            <TabsTrigger
              value="models"
              className="flex items-center gap-2 rounded-none border-b-2 border-transparent data-[state=active]:border-primary"
            >
              <Database className="h-4 w-4" />
              Model Manager
            </TabsTrigger>
            <TabsTrigger
              value="testing"
              className="flex items-center gap-2 rounded-none border-b-2 border-transparent data-[state=active]:border-primary"
            >
              <FlaskConical className="h-4 w-4" />
              Testing
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </Card>

      {currentTab === 'training' && <TRMTrainingPanel />}
      {currentTab === 'models' && <TRMModelManager />}
      {currentTab === 'testing' && <TRMTestPanel />}
    </div>
  );
};

export default TRMDashboard;
