/**
 * Customer Supply Chain Config List
 *
 * Page for viewing and managing supply chain configurations within a customer.
 * Accessible to:
 * - System admins (full access, all customers)
 * - Customer admins (their customer only)
 * - Users with view_sc_configs capability (their customer only, read access)
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
  // 2. Customer admin of their customer
  // 3. User with view_sc_configs capability (can view their customer's configs)
  const canViewScConfigs = hasCapability('view_sc_configs');
  const canAccess = user?.is_superuser || isGroupAdmin || canViewScConfigs;

  // Can edit if system admin or customer admin
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

  const rawCustomerId = user?.customer_id;
  const parsedCustomerId = typeof rawCustomerId === 'number' ? rawCustomerId : Number(rawCustomerId);
  const restrictToCustomerId = Number.isFinite(parsedCustomerId) ? parsedCustomerId : null;

  // Non-system-admins must be assigned to a customer
  if (!isSystemAdmin && !restrictToCustomerId) {
    return (
      <div className="flex justify-center items-center min-h-[50vh]">
        <Alert variant="warning">
          You must be assigned to a customer before you can view supply chain configurations.
        </Alert>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <SupplyChainConfigList
        title={isSystemAdmin ? "All Supply Chain Configurations" : "My Supply Chain Configurations"}
        basePath="/admin/customer/supply-chain-configs"
        restrictToGroupId={isSystemAdmin ? null : restrictToCustomerId}
        enableTraining={canEdit}
        readOnly={!canEdit}
      />
      <SupplyChainConfigSankey
        restrictToGroupId={isSystemAdmin ? null : restrictToCustomerId}
      />
      {canEdit && <TrainingPanel />}
    </div>
  );
};

export default GroupSupplyChainConfigList;
