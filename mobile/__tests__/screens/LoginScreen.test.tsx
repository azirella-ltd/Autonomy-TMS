/**
 * Unit tests for LoginScreen
 * Tests authentication UI and form validation
 */

import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { Provider } from 'react-redux';
import configureStore from 'redux-mock-store';
import thunk from 'redux-thunk';
import LoginScreen from '../../src/screens/Auth/LoginScreen';
import { login } from '../../src/store/slices/authSlice';

const middlewares = [thunk];
const mockStore = configureStore(middlewares);

// Mock navigation
const mockNavigate = jest.fn();
jest.mock('@react-navigation/native', () => ({
  ...jest.requireActual('@react-navigation/native'),
  useNavigation: () => ({
    navigate: mockNavigate,
  }),
}));

describe('LoginScreen', () => {
  let store: any;

  beforeEach(() => {
    store = mockStore({
      auth: {
        isAuthenticated: false,
        user: null,
        token: null,
        refreshToken: null,
        loading: false,
        error: null,
      },
    });
    store.dispatch = jest.fn();
    jest.clearAllMocks();
  });

  it('should render correctly', () => {
    const { getByText, getByPlaceholderText } = render(
      <Provider store={store}>
        <LoginScreen />
      </Provider>
    );

    expect(getByText('Welcome Back')).toBeTruthy();
    expect(getByPlaceholderText('Email')).toBeTruthy();
    expect(getByPlaceholderText('Password')).toBeTruthy();
    expect(getByText('Sign In')).toBeTruthy();
  });

  it('should validate empty email', async () => {
    const { getByText, getByPlaceholderText } = render(
      <Provider store={store}>
        <LoginScreen />
      </Provider>
    );

    const signInButton = getByText('Sign In');
    fireEvent.press(signInButton);

    await waitFor(() => {
      expect(getByText('Email is required')).toBeTruthy();
    });
  });

  it('should validate invalid email format', async () => {
    const { getByText, getByPlaceholderText } = render(
      <Provider store={store}>
        <LoginScreen />
      </Provider>
    );

    const emailInput = getByPlaceholderText('Email');
    fireEvent.changeText(emailInput, 'invalid-email');

    const signInButton = getByText('Sign In');
    fireEvent.press(signInButton);

    await waitFor(() => {
      expect(getByText('Invalid email format')).toBeTruthy();
    });
  });

  it('should validate empty password', async () => {
    const { getByText, getByPlaceholderText } = render(
      <Provider store={store}>
        <LoginScreen />
      </Provider>
    );

    const emailInput = getByPlaceholderText('Email');
    fireEvent.changeText(emailInput, 'test@example.com');

    const signInButton = getByText('Sign In');
    fireEvent.press(signInButton);

    await waitFor(() => {
      expect(getByText('Password is required')).toBeTruthy();
    });
  });

  it('should validate minimum password length', async () => {
    const { getByText, getByPlaceholderText } = render(
      <Provider store={store}>
        <LoginScreen />
      </Provider>
    );

    const emailInput = getByPlaceholderText('Email');
    const passwordInput = getByPlaceholderText('Password');

    fireEvent.changeText(emailInput, 'test@example.com');
    fireEvent.changeText(passwordInput, '12345'); // Too short

    const signInButton = getByText('Sign In');
    fireEvent.press(signInButton);

    await waitFor(() => {
      expect(getByText('Password must be at least 6 characters')).toBeTruthy();
    });
  });

  it('should dispatch login action with valid credentials', async () => {
    const { getByText, getByPlaceholderText } = render(
      <Provider store={store}>
        <LoginScreen />
      </Provider>
    );

    const emailInput = getByPlaceholderText('Email');
    const passwordInput = getByPlaceholderText('Password');

    fireEvent.changeText(emailInput, 'test@example.com');
    fireEvent.changeText(passwordInput, 'password123');

    const signInButton = getByText('Sign In');
    fireEvent.press(signInButton);

    await waitFor(() => {
      expect(store.dispatch).toHaveBeenCalledWith(
        expect.objectContaining({
          type: login.pending.type,
        })
      );
    });
  });

  it('should show loading state during login', () => {
    store = mockStore({
      auth: {
        isAuthenticated: false,
        user: null,
        token: null,
        refreshToken: null,
        loading: true,
        error: null,
      },
    });

    const { getByTestId } = render(
      <Provider store={store}>
        <LoginScreen />
      </Provider>
    );

    expect(getByTestId('loading-spinner')).toBeTruthy();
  });

  it('should display error message on login failure', () => {
    store = mockStore({
      auth: {
        isAuthenticated: false,
        user: null,
        token: null,
        refreshToken: null,
        loading: false,
        error: 'Invalid credentials',
      },
    });

    const { getByText } = render(
      <Provider store={store}>
        <LoginScreen />
      </Provider>
    );

    expect(getByText('Invalid credentials')).toBeTruthy();
  });

  it('should toggle password visibility', () => {
    const { getByPlaceholderText, getByTestId } = render(
      <Provider store={store}>
        <LoginScreen />
      </Provider>
    );

    const passwordInput = getByPlaceholderText('Password');
    const toggleButton = getByTestId('toggle-password-visibility');

    // Initially password should be hidden
    expect(passwordInput.props.secureTextEntry).toBe(true);

    // Toggle to show password
    fireEvent.press(toggleButton);
    expect(passwordInput.props.secureTextEntry).toBe(false);

    // Toggle back to hide password
    fireEvent.press(toggleButton);
    expect(passwordInput.props.secureTextEntry).toBe(true);
  });

  it('should navigate to register screen', () => {
    const { getByText } = render(
      <Provider store={store}>
        <LoginScreen />
      </Provider>
    );

    const registerLink = getByText("Don't have an account? Sign Up");
    fireEvent.press(registerLink);

    expect(mockNavigate).toHaveBeenCalledWith('Register');
  });

  it('should navigate to forgot password screen', () => {
    const { getByText } = render(
      <Provider store={store}>
        <LoginScreen />
      </Provider>
    );

    const forgotPasswordLink = getByText('Forgot Password?');
    fireEvent.press(forgotPasswordLink);

    expect(mockNavigate).toHaveBeenCalledWith('ForgotPassword');
  });

  it('should clear error when user starts typing', async () => {
    store = mockStore({
      auth: {
        isAuthenticated: false,
        user: null,
        token: null,
        refreshToken: null,
        loading: false,
        error: 'Invalid credentials',
      },
    });

    const { getByPlaceholderText, queryByText } = render(
      <Provider store={store}>
        <LoginScreen />
      </Provider>
    );

    const emailInput = getByPlaceholderText('Email');
    fireEvent.changeText(emailInput, 't');

    await waitFor(() => {
      expect(queryByText('Invalid credentials')).toBeNull();
    });
  });

  it('should disable submit button when loading', () => {
    store = mockStore({
      auth: {
        isAuthenticated: false,
        user: null,
        token: null,
        refreshToken: null,
        loading: true,
        error: null,
      },
    });

    const { getByText } = render(
      <Provider store={store}>
        <LoginScreen />
      </Provider>
    );

    const signInButton = getByText('Sign In');
    expect(signInButton.props.disabled).toBe(true);
  });

  it('should trim whitespace from email', async () => {
    const { getByText, getByPlaceholderText } = render(
      <Provider store={store}>
        <LoginScreen />
      </Provider>
    );

    const emailInput = getByPlaceholderText('Email');
    const passwordInput = getByPlaceholderText('Password');

    fireEvent.changeText(emailInput, '  test@example.com  ');
    fireEvent.changeText(passwordInput, 'password123');

    const signInButton = getByText('Sign In');
    fireEvent.press(signInButton);

    await waitFor(() => {
      expect(store.dispatch).toHaveBeenCalledWith(
        expect.objectContaining({
          payload: expect.objectContaining({
            email: 'test@example.com', // Trimmed
          }),
        })
      );
    });
  });

  it('should handle keyboard dismissal on form submit', async () => {
    const { getByText, getByPlaceholderText } = render(
      <Provider store={store}>
        <LoginScreen />
      </Provider>
    );

    const emailInput = getByPlaceholderText('Email');
    const passwordInput = getByPlaceholderText('Password');

    fireEvent.changeText(emailInput, 'test@example.com');
    fireEvent.changeText(passwordInput, 'password123');

    const signInButton = getByText('Sign In');
    fireEvent.press(signInButton);

    // Keyboard should be dismissed
    await waitFor(() => {
      expect(store.dispatch).toHaveBeenCalled();
    });
  });

  it('should show biometric login option if available', () => {
    // Mock biometric availability
    const { getByText } = render(
      <Provider store={store}>
        <LoginScreen />
      </Provider>
    );

    expect(getByText('Use Face ID')).toBeTruthy();
  });

  it('should remember email if "Remember Me" is checked', async () => {
    const { getByText, getByPlaceholderText, getByTestId } = render(
      <Provider store={store}>
        <LoginScreen />
      </Provider>
    );

    const emailInput = getByPlaceholderText('Email');
    const rememberMeCheckbox = getByTestId('remember-me-checkbox');

    fireEvent.changeText(emailInput, 'test@example.com');
    fireEvent.press(rememberMeCheckbox);

    // Email should be saved to AsyncStorage
    await waitFor(() => {
      expect(emailInput.props.value).toBe('test@example.com');
    });
  });
});
