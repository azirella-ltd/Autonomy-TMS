/**
 * Capability Protected Route Component
 *
 * Wraps routes that require specific capabilities from RBAC system.
 * Redirects to Unauthorized page if user lacks required capability.
 */

import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Spinner } from './common';
import { useCapabilities } from '../hooks/useCapabilities';

const CapabilityProtectedRoute = ({ children, requiredCapability }) => {
  const { hasCapability, loading } = useCapabilities();
  const location = useLocation();

  // Check if user has the required capability
  const hasRequiredCapability = hasCapability(requiredCapability);

  // Show loading spinner while checking capabilities
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

  // Redirect to unauthorized if user doesn't have required capability
  if (!hasRequiredCapability) {
    return (
      <Navigate
        to="/unauthorized"
        state={{ requiredCapability, from: location }}
        replace
      />
    );
  }

  // User has required capability, render children
  return children;
};

export default CapabilityProtectedRoute;
