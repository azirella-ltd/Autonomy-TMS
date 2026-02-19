/**
 * System Admin Protected Route
 *
 * Restricts access to SYSTEM_ADMIN users only.
 * Used for routes that should only be accessible to the most senior admin level:
 * - Group creation and management
 * - Synthetic data generation wizard
 * - System-wide configuration
 */

import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Spinner } from './common';
import { useAuth } from '../contexts/AuthContext';

const SystemAdminRoute = ({ children }) => {
  const { user, loading } = useAuth();
  const location = useLocation();

  // Show loading spinner while checking auth
  if (loading) {
    return (
      <div className="flex flex-col justify-center items-center min-h-[60vh]">
        <Spinner size="lg" />
        <p className="text-sm text-muted-foreground mt-4">
          Checking permissions...
        </p>
      </div>
    );
  }

  // Redirect to unauthorized if user is not SYSTEM_ADMIN
  if (!user || user.user_type !== 'SYSTEM_ADMIN') {
    return (
      <Navigate
        to="/unauthorized"
        state={{
          message: 'This feature is only available to System Administrators.',
          from: location
        }}
        replace
      />
    );
  }

  // User is SYSTEM_ADMIN, render children
  return children;
};

export default SystemAdminRoute;
