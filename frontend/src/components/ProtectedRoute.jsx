import React from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Spinner } from './common';
import { buildLoginRedirectPath } from '../utils/authUtils';

// Unified ProtectedRoute with optional role checks and children support
function ProtectedRoute({ children, allowedRoles = [] }) {
  const { isAuthenticated, loading, hasAnyRole } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex justify-center items-center min-h-screen">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to={buildLoginRedirectPath(location)} replace />;
  }

  if (allowedRoles.length > 0 && !hasAnyRole(allowedRoles)) {
    return <Navigate to="/unauthorized" state={{ from: location }} replace />;
  }

  // If children are provided, render them; otherwise render nested routes
  return children ? children : <Outlet />;
}

export default ProtectedRoute;
