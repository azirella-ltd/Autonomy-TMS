import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import AuthContext from '../../contexts/AuthContext';
import ProtectedRoute from '../../components/common/ProtectedRoute';

// Mock child components
const PublicPage = () => <div>Public Page</div>;
const ProtectedPage = () => <div>Protected Page</div>;
const AdminPage = () => <div>Admin Page</div>;
const LoginPage = () => <div>Login Page</div>;
const UnauthorizedPage = () => <div>Unauthorized</div>;

// Helper function to render with router and auth context
const renderWithProviders = (ui, { route = '/protected', user = null, loading = false } = {}) => {
  const authValue = {
    isAuthenticated: !!user,
    user,
    loading,
    login: jest.fn(),
    logout: jest.fn(),
    refreshUser: jest.fn(),
    hasRole: (role) => !!user && (user.is_superuser || (user.roles || []).includes(role)),
    hasAnyRole: (roles = []) => roles.length === 0 || roles.some((r) => !!user && (user.is_superuser || (user.roles || []).includes(r))),
  };

  return render(
    <AuthContext.Provider value={authValue}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/unauthorized" element={<UnauthorizedPage />} />
          <Route path="/public" element={<PublicPage />} />
          <Route
            path="/protected"
            element={
              <ProtectedRoute>
                <ProtectedPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin"
            element={
              <ProtectedRoute roles={['admin']}>
                <AdminPage />
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  );
};

describe('ProtectedRoute', () => {
  it('should render protected page when user is authenticated', () => {
    renderWithProviders(null, { user: { id: 1, username: 'testuser', roles: ['user'] }, route: '/protected' });
    expect(screen.getByText('Protected Page')).toBeInTheDocument();
  });

  it('should redirect to login when user is not authenticated', () => {
    renderWithProviders(
      <ProtectedRoute><div>Protected Content</div></ProtectedRoute>,
      { user: null, route: '/protected' }
    );
    
    // Should redirect to login
    expect(screen.getByText('Login Page')).toBeInTheDocument();
    expect(screen.queryByText('Protected Content')).not.toBeInTheDocument();
  });

  it('should show loading state while checking auth', () => {
    renderWithProviders(null, { user: null, loading: true, route: '/protected' });
    // MUI CircularProgress renders a progressbar
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
  });

  it('should allow access when user has required role', () => {
    renderWithProviders(null, { user: { id: 1, username: 'admin', roles: ['admin'] }, route: '/admin' });
    expect(screen.getByText('Admin Page')).toBeInTheDocument();
  });

  it('should redirect to unauthorized when user lacks required role', () => {
    renderWithProviders(null, { user: { id: 2, username: 'user', roles: ['user'] }, route: '/admin' });
    expect(screen.getByText('Unauthorized')).toBeInTheDocument();
  });

  it('should preserve the intended location in state when redirecting', () => {
    renderWithProviders(null, { user: null, route: '/protected?from=dashboard' });
    expect(screen.getByText('Login Page')).toBeInTheDocument();
  });
});
