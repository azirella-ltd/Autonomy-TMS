/**
 * Organization Supply Chain Config List
 *
 * Page for viewing and managing supply chain configurations within an organization.
 * Accessible to:
 * - System admins (full access, all organizations)
 * - Organization admins (their organization only)
 * - Users with view_sc_configs capability (their organization only, read access)
 */

import React, { useState, useEffect } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Alert, Spinner, Card, CardContent, Badge } from '../../components/common';
import { useAuth } from '../../contexts/AuthContext';
import { useCapabilities } from '../../hooks/useCapabilities';
import { isTenantAdmin as isTenantAdminUser, isSystemAdmin as isSystemAdminUser } from '../../utils/authUtils';
import SupplyChainConfigList from '../../components/supply-chain-config/SupplyChainConfigList';
import SupplyChainConfigSankey from '../../components/supply-chain-config/SupplyChainConfigSankey';
import { Sparkles, Package, TrendingUp, BarChart3, Truck, Wrench, Clock } from 'lucide-react';
import { api } from '../../services/api';

const VARIABLE_ICONS = {
  receipt: Package,
  demand: TrendingUp,
  forecast_bias: BarChart3,
  quality: Sparkles,
  supplier_lead_time: Truck,
  maintenance: Wrench,
  transit_time: Clock,
};

const ModelConfidencePanel = () => {
  const [data, setData] = useState(null);

  useEffect(() => {
    api.get('/conformal/suite/status')
      .then(res => setData(res.data))
      .catch(() => setData(null));
  }, []);

  if (!data?.extended) return null;

  const ext = data.extended;
  const total = ext.total_predictors || 0;

  return (
    <Card>
      <CardContent className="pt-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-primary" />
            <h2 className="text-lg font-semibold">Model Confidence</h2>
          </div>
          <Badge variant={total > 0 ? 'success' : 'warning'}>
            {total > 0 ? 'Healthy' : 'Not Calibrated'}
          </Badge>
        </div>
        <p className="text-sm text-muted-foreground mb-3">
          Conformal prediction coverage across {Object.keys(ext).filter(k => k !== 'total_predictors').length} variable types
        </p>
        <div className="space-y-2">
          {Object.entries(ext)
            .filter(([k]) => k !== 'total_predictors')
            .sort((a, b) => (b[1].count || 0) - (a[1].count || 0))
            .map(([vtype, info]) => {
              const Icon = VARIABLE_ICONS[vtype] || Sparkles;
              return (
                <div key={vtype} className="flex items-center justify-between py-1">
                  <div className="flex items-center gap-2">
                    <Icon className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm capitalize">{vtype.replace(/_/g, ' ')}</span>
                  </div>
                  <div className="flex items-center gap-3 text-sm">
                    <span className="font-medium">{info.count}</span>
                    <Badge variant="outline" className="text-xs">
                      @ {(info.coverage * 100).toFixed(0)}%
                    </Badge>
                  </div>
                </div>
              );
            })}
        </div>
        <div className="mt-3 pt-3 border-t flex justify-between items-center">
          <span className="text-sm text-muted-foreground">Total Predictors</span>
          <span className="text-lg font-bold">{total.toLocaleString()}</span>
        </div>
      </CardContent>
    </Card>
  );
};

const TenantSupplyChainConfigList = () => {
  const { user, loading: authLoading } = useAuth();
  const { hasCapability, loading: capLoading } = useCapabilities();
  const location = useLocation();

  const isSystemAdmin = isSystemAdminUser(user);
  const isTenantAdmin = isTenantAdminUser(user);

  // Access allowed if:
  // 1. System admin (full access)
  // 2. Organization admin of their organization
  // 3. User with view_sc_configs capability (can view their organization's configs)
  const canViewScConfigs = hasCapability('view_sc_configs');
  const canAccess = user?.is_superuser || isTenantAdmin || canViewScConfigs;

  // Can edit if system admin or organization admin
  const canEdit = user?.is_superuser || isTenantAdmin;

  if (authLoading || capLoading) {
    return (
      <div className="flex justify-center items-center min-h-[50vh]">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!user) {
    return (
      <Navigate
        to="/login"
        replace
        state={{
          from: location.pathname + location.search,
        }}
      />
    );
  }

  if (!canAccess) {
    return <Navigate to="/unauthorized" replace />;
  }

  const rawTenantId = user?.tenant_id;
  const parsedTenantId = typeof rawTenantId === 'number' ? rawTenantId : Number(rawTenantId);
  const restrictToTenantId = Number.isFinite(parsedTenantId) ? parsedTenantId : null;

  // Non-system-admins must be assigned to an organization
  if (!isSystemAdmin && !restrictToTenantId) {
    return (
      <div className="flex justify-center items-center min-h-[50vh]">
        <Alert variant="warning">
          You must be assigned to an organization before you can view supply chain configurations.
        </Alert>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <SupplyChainConfigList
        title={isSystemAdmin ? "All Supply Chain Configurations" : "My Supply Chain Configurations"}
        basePath="/admin/tenant/supply-chain-configs"
        restrictToTenantId={isSystemAdmin ? null : restrictToTenantId}
        enableTraining={canEdit}
        readOnly={!canEdit}
      />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <SupplyChainConfigSankey
          restrictToTenantId={isSystemAdmin ? null : restrictToTenantId}
        />
        <ModelConfidencePanel />
      </div>
    </div>
  );
};

export default TenantSupplyChainConfigList;
