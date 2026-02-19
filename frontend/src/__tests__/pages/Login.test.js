import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Login from '../../pages/Login.jsx';
import { AuthProvider } from '../../contexts/AuthContext';

jest.mock('../../config/api', () => ({ API_BASE_URL: 'http://localhost' }));
jest.mock('react-toastify', () => ({
  toast: {
    error: jest.fn(),
    info: jest.fn(),
  },
}));

// Mock the API
jest.mock('../../services/api', () => {
  const apiMock = {
    login: jest.fn(),
    getGames: jest.fn().mockResolvedValue([]),
    getCurrentUser: jest.fn().mockResolvedValue(null),
    refreshToken: jest.fn(),
    logout: jest.fn(),
  };
  return { __esModule: true, simulationApi: apiMock, default: apiMock };
});

// Mock the useNavigate hook
const mockNavigate = jest.fn();

jest.mock('react-router-dom', () => ({
  ...jest.requireActual('react-router-dom'),
  useNavigate: () => mockNavigate,
  useLocation: () => ({
    state: { from: { pathname: '/dashboard' } },
  }),
}));

describe('Login', () => {
  const { toast } = require('react-toastify');
  const renderLogin = async () => {
    const utils = render(
      <MemoryRouter>
        <AuthProvider>
          <Login />
        </AuthProvider>
      </MemoryRouter>
    );
    await screen.findByRole('heading', { name: /sign in to your account/i });
    return utils;
  };

  const getSignInButton = async () => {
    return screen.findByRole('button', { name: /^sign in$/i });
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders the login form', async () => {
    await renderLogin();

    expect(await screen.findByLabelText(/email address/i)).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: /^sign in$/i })).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: /forgot your password/i })).toBeInTheDocument();
    expect(await screen.findByText(/create a new account/i)).toBeInTheDocument();
  });

  it('validates form fields', async () => {
    await renderLogin();

    // Submit empty form
    const submitButton = await getSignInButton();
    fireEvent.click(submitButton);
    
    // Check for validation errors
    expect(await screen.findByText(/email is required/i)).toBeInTheDocument();
    expect(await screen.findByText(/password is required/i)).toBeInTheDocument();
    
    // Test invalid email
    const emailInput = await screen.findByPlaceholderText('Email address');
    fireEvent.change(emailInput, { target: { value: 'invalid-email' } });
    fireEvent.click(await getSignInButton());
    
    expect(await screen.findByText(/enter a valid email address/i)).toBeInTheDocument();
    
    // Test short password
    const passwordInput = await screen.findByPlaceholderText('Password');
    fireEvent.change(passwordInput, { target: { value: 'short' } });
    fireEvent.click(await getSignInButton());
    
    expect(await screen.findByText(/password must be at least 8 characters/i)).toBeInTheDocument();
  });

  it('handles successful login', async () => {
    const mockUser = { id: 1, username: 'testuser', email: 'test@example.com' };
    require('../../services/api').simulationApi.login.mockResolvedValue({ success: true, user: mockUser });

    await renderLogin();
    
    // Fill in the form
    fireEvent.change(await screen.findByPlaceholderText('Email address'), {
      target: { value: 'test@example.com' },
    });
    fireEvent.change(await screen.findByPlaceholderText('Password'), {
      target: { value: 'password123' },
    });
    
    // Submit the form
    fireEvent.click(await getSignInButton());
    
    // Check that the login function was called with the right parameters
    await waitFor(() => {
      expect(require('../../services/api').simulationApi.login).toHaveBeenCalledWith({
        username: 'test@example.com',
        password: 'password123',
      });
    });

    // Check that we navigate to the dashboard after successful login
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/dashboard', { replace: true });
    });
  });

  it('handles login failure', async () => {
    const errorMessage = 'Invalid credentials';
    require('../../services/api').simulationApi.login.mockResolvedValue({ success: false, error: errorMessage });

    await renderLogin();
    
    // Fill in the form
    fireEvent.change(await screen.findByPlaceholderText('Email address'), {
      target: { value: 'test@example.com' },
    });
    fireEvent.change(await screen.findByPlaceholderText('Password'), {
      target: { value: 'wrongpassword' },
    });

    // Submit the form
    fireEvent.click(await getSignInButton());
    
    // Check that the error message is displayed
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(errorMessage);
    });
  });
});
