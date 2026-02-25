import { Navigate } from 'react-router-dom';
import { Alert, Spinner } from '../../components/common';
import { useAuth } from '../../contexts/AuthContext';
import { isGroupAdmin as isGroupAdminUser } from '../../utils/authUtils';
import SupplyChainConfigForm from '../../components/supply-chain-config/SupplyChainConfigForm';

const GroupSupplyChainConfigForm = () => {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex justify-center items-center min-h-[50vh]">
        <Spinner size="lg" />
      </div>
    );
  }

  const canAccess = user?.is_superuser || isGroupAdminUser(user);
  if (!canAccess) {
    return <Navigate to="/unauthorized" replace />;
  }

  const customerId = user?.customer_id ?? null;

  if (isGroupAdminUser(user) && !customerId) {
    return (
      <div className="flex justify-center items-center min-h-[50vh]">
        <Alert variant="warning">
          You must be assigned to a customer before you can create or edit supply chain configurations.
        </Alert>
      </div>
    );
  }

  return (
    <SupplyChainConfigForm
      basePath="/admin/customer/supply-chain-configs"
      allowGroupSelection={false}
      defaultGroupId={customerId}
    />
  );
};

export default GroupSupplyChainConfigForm;
