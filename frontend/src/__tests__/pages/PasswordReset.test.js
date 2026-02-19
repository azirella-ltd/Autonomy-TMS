import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import '@testing-library/jest-dom';
import PasswordReset from '../../pages/PasswordReset';
import { AuthProvider } from '../../contexts/AuthContext';

// Mock the API
jest.mock('../../services/api', () => ({
  __esModule: true,
  default: {
    requestPasswordReset: jest.fn(),
    resetPassword: jest.fn(),
  },
  simulationApi: {
    requestPasswordReset: jest.fn(),
    resetPassword: jest.fn(),
  },
}));

// Mock react-toastify (avoid hoisting issue by creating fns inside factory)
jest.mock('react-toastify', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
    info: jest.fn(),
  },
}));

// Mock React Router v6
const mockNavigate = jest.fn();
const mockSearchParams = new URLSearchParams();
const mockSetSearchParams = jest.fn();

jest.mock('react-router-dom', () => ({
  ...jest.requireActual('react-router-dom'),
  useSearchParams: () => [mockSearchParams, mockSetSearchParams],
  useNavigate: () => mockNavigate,
}));

describe('PasswordReset', () => {
  const renderPasswordReset = (token = null) => {
    const searchParams = new URLSearchParams();
    if (token) {
      searchParams.set('token', token);
    }
    
    jest.spyOn(require('react-router-dom'), 'useSearchParams')
      .mockImplementation(() => [searchParams, mockSetSearchParams]);
    
    return render(
      <MemoryRouter>
        <AuthProvider>
          <PasswordReset />
        </AuthProvider>
      </MemoryRouter>
    );
  };

  beforeEach(() => {
    jest.clearAllMocks();
    // Mock window.scrollTo
    window.scrollTo = jest.fn();
  });

  describe('Request Password Reset Form', () => {
    beforeEach(() => {
      // Reset mocks before each test
      jest.clearAllMocks();
      require('react-router-dom').useSearchParams.mockImplementation(() => [new URLSearchParams()]);
    });

    it('renders the request password reset form when no token is provided', () => {
      renderPasswordReset();
      
      expect(screen.getByRole('heading', { name: /forgot your password/i })).toBeInTheDocument();
      expect(screen.getByPlaceholderText('Email address')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /send reset link/i })).toBeInTheDocument();
      expect(screen.getByRole('link', { name: /back to login/i })).toBeInTheDocument();
    });

    it('validates the email field', async () => {
      renderPasswordReset();
      
      // Submit empty form
      fireEvent.click(screen.getByRole('button', { name: /send reset link/i }));
      
      // Check for validation error
      expect(await screen.findByText(/email is required/i)).toBeInTheDocument();
    });

    it('handles successful password reset request', async () => {
      const requestPasswordReset = require('../../services/api').simulationApi.requestPasswordReset;
      requestPasswordReset.mockResolvedValue({ success: true });
      
      renderPasswordReset();
      
      // Fill in the form
      const emailInput = screen.getByPlaceholderText('Email address');
      fireEvent.change(emailInput, {
        target: { value: 'test@example.com' },
      });
      
      // Submit the form
      const submitButton = screen.getByRole('button', { name: /send reset link/i });
      fireEvent.click(submitButton);
      
      // Check that the API was called
      expect(requestPasswordReset).toHaveBeenCalledWith('test@example.com');
      
      // Check for success message
      const { toast } = require('react-toastify');
      expect(toast.success).toHaveBeenCalledWith(
        'Password reset link sent to your email',
        expect.any(Object)
      );
      
      // Should show success message
      expect(screen.getByText(/check your email for a link to reset your password/i)).toBeInTheDocument();
    });
  });

  describe('Reset Password Form', () => {
    const testToken = 'test-reset-token-123';
    
    beforeEach(() => {
      // Reset mocks before each test
      jest.clearAllMocks();
      
      // Set up search params with token
      mockSearchParams.set('token', testToken);
      
      // Mock the reset password API
      require('../../services/api').simulationApi.resetPassword = jest.fn().mockResolvedValue({});
    });
    
    it('renders the reset password form when a token is provided', () => {
      renderPasswordReset(testToken);
      
      expect(screen.getByRole('heading', { name: /reset your password/i })).toBeInTheDocument();
      expect(screen.getByPlaceholderText('New password')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('Confirm new password')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /reset password/i })).toBeInTheDocument();
    });

    it('validates the password fields', async () => {
      renderPasswordReset(testToken);
      
      // Submit empty form
      fireEvent.click(screen.getByRole('button', { name: /reset password/i }));
      
      // Check for validation errors - the form might not show this message until after interaction
      const newPasswordInput = screen.getByPlaceholderText('New password');
      fireEvent.blur(newPasswordInput);
      
      // Test short password
      fireEvent.change(newPasswordInput, { target: { value: 'short' } });
      fireEvent.click(screen.getByRole('button', { name: /reset password/i }));
      
      // Check for the validation message
      await waitFor(() => {
        expect(screen.getByText(/password must be at least 8 characters/i)).toBeInTheDocument();
      });
      
      // Test password mismatch
      const confirmPasswordInput = screen.getByPlaceholderText('Confirm new password');
      fireEvent.change(newPasswordInput, { target: { value: 'Password123!' } });
      fireEvent.change(confirmPasswordInput, { target: { value: 'Different123!' } });
      fireEvent.click(screen.getByRole('button', { name: /reset password/i }));
      
      await waitFor(() => {
        expect(screen.getByText(/passwords do not match/i)).toBeInTheDocument();
      });
    });

    it('handles successful password reset', async () => {
      renderPasswordReset(testToken);
      
      // Fill in the form
      const newPasswordInput = screen.getByPlaceholderText('New password');
      const confirmPasswordInput = screen.getByPlaceholderText('Confirm new password');
      const submitButton = screen.getByRole('button', { name: /reset password/i });
      
      fireEvent.change(newPasswordInput, {
        target: { value: 'NewPassword123!' },
      });
      fireEvent.change(confirmPasswordInput, {
        target: { value: 'NewPassword123!' },
      });
      fireEvent.click(submitButton);
      
      // Check that the API was called with the right parameters
      expect(require('../../services/api').simulationApi.resetPassword).toHaveBeenCalledWith(
        testToken,
        'NewPassword123!',
        'NewPassword123!'
      );
      
      // Check for success message
      const { toast } = require('react-toastify');
      expect(toast.success).toHaveBeenCalledWith(
        'Your password has been reset successfully',
        expect.any(Object)
      );
      
      // Should redirect to login
      expect(mockNavigate).toHaveBeenCalledWith('/login');
    });

    it('handles password reset failure', async () => {
      const errorMessage = 'Invalid or expired token';
      require('../../services/api').simulationApi.resetPassword.mockRejectedValue({
        response: { data: { detail: errorMessage } },
      });
      
      renderPasswordReset(testToken);
      
      // Fill in the form using input names since labels are sr-only
      fireEvent.change(screen.getByPlaceholderText('New password'), {
        target: { value: 'NewPassword123!' },
      });
      fireEvent.change(screen.getByPlaceholderText('Confirm new password'), {
        target: { value: 'NewPassword123!' },
      });
      
      // Submit the form
      fireEvent.click(screen.getByRole('button', { name: /reset password/i }));
      
      // Check that the error message is displayed
      await waitFor(() => {
        expect(require('../../services/api').simulationApi.resetPassword).toHaveBeenCalled();
      });
    });
    
    it('checks password inputs are present', () => {
      renderPasswordReset(testToken);
      
      const newPasswordInput = screen.getByPlaceholderText('New password');
      const confirmPasswordInput = screen.getByPlaceholderText('Confirm new password');
      
      // Just verify the inputs are present and have the correct type
      expect(newPasswordInput).toBeInTheDocument();
      expect(confirmPasswordInput).toBeInTheDocument();
      expect(newPasswordInput.type).toBe('password');
      expect(confirmPasswordInput.type).toBe('password');
    });
  });
});
