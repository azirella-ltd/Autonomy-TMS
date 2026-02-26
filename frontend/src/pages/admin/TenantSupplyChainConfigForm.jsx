import { Navigate } from 'react-router-dom';
import { Alert, Spinner } from '../../components/common';
import { useAuth } from '../../contexts/AuthContext';
import { isTenantAdmin as isTenantAdminUser } from '../../utils/authUtils';
import SupplyChainConfigForm from '../../components/supply-chain-config/SupplyChainConfigForm';

const TenantSupplyChainConfigForm = () => {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex justify-center items-center min-h-[50vh]">
        <Spinner size="lg" />
      </div>
    );
  }

  const canAccess = user?.is_superuser || isTenantAdminUser(user);
  if (!canAccess) {
    return <Navigate to="/unauthorized" replace />;
  }

  const tenantId = user?.tenant_id ?? null;

  if (isTenantAdminUser(user) && !tenantId) {
    return (
      <div className="flex justify-center items-center min-h-[50vh]">
        <Alert variant="warning">
          You must be assigned to an organization before you can create or edit supply chain configurations.
        </Alert>
      </div>
    );
  }

  return (
    <SupplyChainConfigForm
      basePath="/admin/tenant/supply-chain-configs"
      allowGroupSelection={false}
      defaultGroupId={tenantId}
    />
  );
};

export default TenantSupplyChainConfigForm;
