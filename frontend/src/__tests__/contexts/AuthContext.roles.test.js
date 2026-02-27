import React from 'react';
import { renderHook } from '@testing-library/react';
import AuthContext from '../../contexts/AuthContext';

jest.mock('../../config/api', () => ({ API_BASE_URL: 'http://localhost' }));

describe('AuthContext role helpers', () => {
  const wrapperWithUser = (user) => ({ children }) => (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        hasRole: (role) => !!user && (user.is_superuser || (user.roles || []).includes(role)),
        hasAnyRole: (roles = []) => roles.length === 0 || roles.some((r) => !!user && (user.is_superuser || (user.roles || []).includes(r))),
        hasAllRoles: (roles = []) => roles.length === 0 || roles.every((r) => !!user && (user.is_superuser || (user.roles || []).includes(r))),
        isTenantAdmin: !!user && (user.is_superuser || (user.roles || []).includes('tenantadmin')),
      }}
    >
      {children}
    </AuthContext.Provider>
  );

  it('detects tenant admin via roles and treats superusers as system admins', () => {
    const userRoles = { roles: ['user', 'tenantadmin'], is_superuser: false };
    const { result: r1 } = renderHook(() => React.useContext(AuthContext), { wrapper: wrapperWithUser(userRoles) });
    expect(r1.current.isTenantAdmin).toBe(true);

    const userSuper = { roles: ['user'], is_superuser: true };
    const { result: r2 } = renderHook(() => React.useContext(AuthContext), { wrapper: wrapperWithUser(userSuper) });
    expect(r2.current.isTenantAdmin).toBe(true);
  });

  it('checks hasRole / hasAnyRole / hasAllRoles', () => {
    const user = { roles: ['user', 'moderator'], is_superuser: false };
    const { result } = renderHook(() => React.useContext(AuthContext), { wrapper: wrapperWithUser(user) });
    expect(result.current.hasRole('user')).toBe(true);
    expect(result.current.hasAnyRole(['admin', 'user'])).toBe(true);
    expect(result.current.hasAllRoles(['user', 'moderator'])).toBe(true);
    expect(result.current.hasAllRoles(['user', 'admin'])).toBe(false);
  });
});
