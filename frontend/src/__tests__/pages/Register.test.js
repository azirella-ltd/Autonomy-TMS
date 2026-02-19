import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Register from '../../pages/Register';
import { AuthProvider } from '../../contexts/AuthContext';

// Mock the API
jest.mock('../../services/api', () => ({
  __esModule: true,
  default: {
    register: jest.fn(),
  },
  simulationApi: {
    register: jest.fn(),
  },
}));

// Mock the useNavigate hook
const mockNavigate = jest.fn();

jest.mock('react-router-dom', () => ({
  ...jest.requireActual('react-router-dom'),
  useNavigate: () => mockNavigate,
  useSearchParams: () => [new URLSearchParams(), jest.fn()],
}));

// Mock react-toastify
jest.mock('react-toastify', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
  },
}));

describe('Register', () => {
  const renderRegister = () => {
    return render(
      <MemoryRouter>
        <AuthProvider>
          <Register />
        </AuthProvider>
      </MemoryRouter>
    );
  };

  beforeEach(() => {
    jest.clearAllMocks();
    // Mock window.scrollTo
    window.scrollTo = jest.fn();
  });

  it('renders the registration form', () => {
    renderRegister();
    
    expect(screen.getByLabelText(/username/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/first name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/last name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^password/i)).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: /terms/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /create account/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /sign in to your existing account/i })).toBeInTheDocument();
  });

  it('validates form fields', async () => {
    renderRegister();
    
    // Submit empty form
    fireEvent.click(screen.getByRole('button', { name: /create account/i }));
    
    // Check for validation errors
    expect(await screen.findByText(/username is required/i)).toBeInTheDocument();
    expect(await screen.findByText(/email is required/i)).toBeInTheDocument();
    expect(await screen.findByText(/first name is required/i)).toBeInTheDocument();
    expect(await screen.findByText(/last name is required/i)).toBeInTheDocument();
    expect(await screen.findByText(/password is required/i)).toBeInTheDocument();
    expect(await screen.findByText(/you must accept the terms/i)).toBeInTheDocument();
    
    // Test invalid username
    const usernameInput = screen.getByLabelText(/username/i);
    fireEvent.change(usernameInput, { target: { value: 'ab' } });
    fireEvent.click(screen.getByRole('button', { name: /create account/i }));
    expect(await screen.findByText(/username must be at least 3 characters/i)).toBeInTheDocument();
    
    // Test invalid email
    const emailInput = screen.getByLabelText(/email address/i);
    fireEvent.change(emailInput, { target: { value: 'invalid-email' } });
    fireEvent.click(screen.getByRole('button', { name: /create account/i }));
    expect(await screen.findByText(/enter a valid email address/i)).toBeInTheDocument();
    
    // Test password mismatch
    const passwordInput = screen.getByLabelText(/^password/i);
    const confirmPasswordInput = screen.getByLabelText(/confirm password/i);
    fireEvent.change(passwordInput, { target: { value: 'Password123!' } });
    fireEvent.change(confirmPasswordInput, { target: { value: 'Different123!' } });
    fireEvent.click(screen.getByRole('button', { name: /create account/i }));
    expect(await screen.findByText(/passwords do not match/i)).toBeInTheDocument();
  });

  it('handles successful registration', async () => {
    require('../../services/api').simulationApi.register.mockResolvedValue({ success: true });
    
    renderRegister();
    
    // Fill in the form
    fireEvent.change(screen.getByLabelText(/username/i), {
      target: { value: 'testuser' },
    });
    fireEvent.change(screen.getByLabelText(/email address/i), {
      target: { value: 'test@example.com' },
    });
    fireEvent.change(screen.getByLabelText(/first name/i), {
      target: { value: 'Test' },
    });
    fireEvent.change(screen.getByLabelText(/last name/i), {
      target: { value: 'User' },
    });
    fireEvent.change(screen.getByLabelText(/^password/i), {
      target: { value: 'Password123!' },
    });
    fireEvent.change(screen.getByLabelText(/confirm password/i), {
      target: { value: 'Password123!' },
    });
    fireEvent.click(screen.getByRole('checkbox', { name: /terms/i }));
    
    // Submit the form
    fireEvent.click(screen.getByRole('button', { name: /create account/i }));
    
    // Check that the register function was called with the right parameters
    await waitFor(() => {
      expect(require('../../services/api').simulationApi.register).toHaveBeenCalledWith({
        username: 'testuser',
        email: 'test@example.com',
        firstName: 'Test',
        lastName: 'User',
        password: 'Password123!',
      });
    });
    
    // Check for success message and redirection
    await waitFor(() => {
      const { toast } = require('react-toastify');
      expect(toast.success).toHaveBeenCalled();
    });
    const { toast } = require('react-toastify');
    expect(toast.success.mock.calls[0][0]).toBe(
      'Registration successful! Please check your email to verify your account.'
    );
  });

  it('handles registration failure', async () => {
    const errorMessage = 'Username already exists';
    require('../../services/api').simulationApi.register.mockRejectedValue({
      response: { data: { detail: errorMessage } },
    });
    
    renderRegister();
    
    // Fill in the form with minimal valid data
    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: 'existinguser' } });
    fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: 'test@example.com' } });
    fireEvent.change(screen.getByLabelText(/first name/i), { target: { value: 'Test' } });
    fireEvent.change(screen.getByLabelText(/last name/i), { target: { value: 'User' } });
    fireEvent.change(screen.getByLabelText(/^password/i), { target: { value: 'Password123!' } });
    fireEvent.change(screen.getByLabelText(/confirm password/i), { target: { value: 'Password123!' } });
    fireEvent.click(screen.getByRole('checkbox', { name: /terms/i }));
    
    // Submit the form
    fireEvent.click(screen.getByRole('button', { name: /create account/i }));
    
    // Check that the error message is displayed
    await waitFor(() => {
      const { toast } = require('react-toastify');
      expect(toast.error).toHaveBeenCalled();
    });
  });

  it.skip('toggles password visibility', () => {});
});
