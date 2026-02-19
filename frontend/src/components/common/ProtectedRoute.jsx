// Legacy wrapper that forwards to the unified ProtectedRoute API
import React from 'react';
import UnifiedProtectedRoute from '../ProtectedRoute';

const LegacyProtectedRoute = ({ children, roles = [], ...rest }) => (
  <UnifiedProtectedRoute allowedRoles={roles} {...rest}>
    {children}
  </UnifiedProtectedRoute>
);

export default LegacyProtectedRoute;
