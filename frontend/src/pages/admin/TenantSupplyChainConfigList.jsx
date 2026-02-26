/**
 * Organization Supply Chain Config List
 *
 * Page for viewing and managing supply chain configurations within an organization.
 * Accessible to:
 * - System admins (full access, all organizations)
 * - Organization admins (their organization only)
 * - Users with view_sc_configs capability (their organization only, read access)
 */

import { Navigate, useLocation } from 'react-router-dom';
import { Alert, Spinner } from '../../components/common';
import { useAuth } from '../../contexts/AuthContext';
import { useCapabilities } from '../../hooks/useCapabilities';
import { isTenantAdmin as isTenantAdminUser, isSystemAdmin as isSystemAdminUser } from '../../utils/authUtils';
import SupplyChainConfigList from '../../components/supply-chain-config/SupplyChainConfigList';
import SupplyChainConfigSankey from '../../components/supply-chain-config/SupplyChainConfigSankey';
import { TrainingPanel } from './Training';

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
        restrictToGroupId={isSystemAdmin ? null : restrictToTenantId}
        enableTraining={canEdit}
        readOnly={!canEdit}
      />
      <SupplyChainConfigSankey
        restrictToGroupId={isSystemAdmin ? null : restrictToTenantId}
      />
      {canEdit && <TrainingPanel />}
    </div>
  );
};

export default TenantSupplyChainConfigList;
