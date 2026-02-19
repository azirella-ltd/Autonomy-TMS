/**
 * Group Supply Chain Config List
 *
 * Page for viewing and managing supply chain configurations within a group.
 * Accessible to:
 * - System admins (full access, all groups)
 * - Group admins (their group only)
 * - Users with view_sc_configs capability (their group only, read access)
 */

import { Navigate, useLocation } from 'react-router-dom';
import { Alert, Spinner } from '../../components/common';
import { useAuth } from '../../contexts/AuthContext';
import { useCapabilities } from '../../hooks/useCapabilities';
import { isGroupAdmin as isGroupAdminUser, isSystemAdmin as isSystemAdminUser } from '../../utils/authUtils';
import SupplyChainConfigList from '../../components/supply-chain-config/SupplyChainConfigList';
import SupplyChainConfigSankey from '../../components/supply-chain-config/SupplyChainConfigSankey';
import { TrainingPanel } from './Training';

const GroupSupplyChainConfigList = () => {
  const { user, loading: authLoading } = useAuth();
  const { hasCapability, loading: capLoading } = useCapabilities();
  const location = useLocation();

  const isSystemAdmin = isSystemAdminUser(user);
  const isGroupAdmin = isGroupAdminUser(user);

  // Access allowed if:
  // 1. System admin (full access)
  // 2. Group admin of their group
  // 3. User with view_sc_configs capability (can view their group's configs)
  const canViewScConfigs = hasCapability('view_sc_configs');
  const canAccess = user?.is_superuser || isGroupAdmin || canViewScConfigs;

  // Can edit if system admin or group admin
  const canEdit = user?.is_superuser || isGroupAdmin;

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

  const rawGroupId = user?.group_id;
  const parsedGroupId = typeof rawGroupId === 'number' ? rawGroupId : Number(rawGroupId);
  const restrictToGroupId = Number.isFinite(parsedGroupId) ? parsedGroupId : null;

  // Non-system-admins must be assigned to a group
  if (!isSystemAdmin && !restrictToGroupId) {
    return (
      <div className="flex justify-center items-center min-h-[50vh]">
        <Alert variant="warning">
          You must be assigned to a group before you can view supply chain configurations.
        </Alert>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <SupplyChainConfigList
        title={isSystemAdmin ? "All Supply Chain Configurations" : "My Group's Supply Chain Configurations"}
        basePath="/admin/group/supply-chain-configs"
        restrictToGroupId={isSystemAdmin ? null : restrictToGroupId}
        enableTraining={canEdit}
        readOnly={!canEdit}
      />
      <SupplyChainConfigSankey
        restrictToGroupId={isSystemAdmin ? null : restrictToGroupId}
      />
      {canEdit && <TrainingPanel />}
    </div>
  );
};

export default GroupSupplyChainConfigList;
