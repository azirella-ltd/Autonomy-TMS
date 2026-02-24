import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import simulationApi, { api } from '../services/api';
import {
  isGroupAdmin,
  isSystemAdmin,
  resolvePostLoginDestination,
} from '../utils/authUtils';
import { toast } from 'react-toastify';
import ContactSystemAdminForm from '../components/ContactSystemAdminForm';
import { Button, Input, Label, Alert, AlertDescription, Spinner } from '../components/common';
import { AlertCircle, Eye, EyeOff, HelpCircle, Mail, KeyRound } from 'lucide-react';
import { cn } from '../lib/utils/cn';

/**
 * Check if user has Powell Framework capabilities via API.
 * Powell capabilities indicate the user should go through DashboardRouter
 * instead of being redirected to a game.
 */
const checkPowellCapabilities = async () => {
  try {
    const response = await api.get('/capabilities/me');
    const capabilities = response.data.capabilities || [];
    // Check for any Powell-specific capability
    return capabilities.some(cap =>
      cap === 'view_executive_dashboard' ||
      cap === 'view_sop_worklist' ||
      cap === 'view_agent_decisions'
    );
  } catch (e) {
    console.error('Failed to check Powell capabilities:', e);
    return false;
  }
};

const Login = () => {
  const [formData, setFormData] = useState({
    email: '',
    password: '',
    rememberMe: false,
  });
  const [showPassword, setShowPassword] = useState(false);

  const [errors, setErrors] = useState({});
  const [contactPrompt, setContactPrompt] = useState(null);
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const { login, isAuthenticated, loading: authLoading, user } = useAuth();

  // Redirect if already authenticated
  useEffect(() => {
    const maybeRedirect = async () => {
      if (!isAuthenticated) return;
      const redirectTo = searchParams.get('redirect');
      const destination = resolvePostLoginDestination(user, redirectTo);

      if (isSystemAdmin(user)) {
        navigate(destination, { replace: true });
        return;
      }
      if (isGroupAdmin(user)) {
        navigate(destination, { replace: true });
        return;
      }

      // Check for Powell capabilities BEFORE game-finding logic
      // Users with Powell capabilities should go through DashboardRouter
      const hasPowellCaps = await checkPowellCapabilities();
      if (hasPowellCaps) {
        navigate('/dashboard', { replace: true });
        return;
      }

      try {
        const games = await simulationApi.getGames();
        const assigned = games.find(g => Array.isArray(g.scenarioUsers) && g.users.some(p => p.user_id === user?.id));
        if (assigned) {
          navigate(`/scenarios/${assigned.id}` , { replace: true });
          return;
        }
      } catch (e) {
        // Fall through to default navigation
      }

      navigate(destination, { replace: true });
    };

    maybeRedirect();
  }, [isAuthenticated, navigate, searchParams, user]);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));

    if (name === 'email' && contactPrompt) {
      setContactPrompt(null);
    }

    if (errors[name]) {
      setErrors(prev => ({
        ...prev,
        [name]: undefined
      }));
    }
  };

  const validateForm = () => {
    const newErrors = {};

    if (!formData.email.trim()) {
      newErrors.email = 'Email is required';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      newErrors.email = 'Please enter a valid email address';
    }

    if (!formData.password) {
      newErrors.password = 'Password is required';
    } else if (formData.password.length < 8) {
      newErrors.password = 'Password must be at least 8 characters';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    try {
      const { success, error, detail, user: loggedInUser } = await login({
        username: formData.email,
        password: formData.password,
      });

      if (success) {
        setContactPrompt(null);
        setErrors({});
        const redirectTo = searchParams.get('redirect');
        const destination = resolvePostLoginDestination(loggedInUser, redirectTo);
        if (isSystemAdmin(loggedInUser)) {
          navigate(destination, { replace: true });
          return;
        }

        if (!isGroupAdmin(loggedInUser)) {
          // Check for Powell capabilities BEFORE game-finding logic
          const hasPowellCaps = await checkPowellCapabilities();
          if (hasPowellCaps) {
            navigate('/dashboard', { replace: true });
            return;
          }

          try {
            const games = await simulationApi.getGames();
            const assigned = games.find(g => Array.isArray(g.scenarioUsers) && g.users.some(p => p.user_id === loggedInUser?.id));
            if (assigned) {
              navigate(`/scenarios/${assigned.id}`, { replace: true });
              return;
            }
          } catch (e) {
            // ignore and fall back
          }
          navigate(destination, { replace: true });
        } else {
          navigate(destination, { replace: true });
        }
      } else {
        const message = error || 'Login failed. Please check your credentials.';
        setErrors(prev => ({
          ...prev,
          form: message,
        }));

        if (detail?.show_contact_form) {
          setContactPrompt({
            email: formData.email,
            systemAdminEmail: detail?.systemadmin_email || detail?.superadmin_email,
          });
          toast.info(message);
        } else {
          setContactPrompt(null);
          // Don't show toast for auth errors - the inline error is more helpful
        }
      }
    } catch (error) {
      console.error('Login error:', error);
      const fallbackMessage = error.message || 'An unexpected error occurred. Please try again.';
      setErrors(prev => ({
        ...prev,
        form: fallbackMessage,
      }));
      setContactPrompt(null);
      toast.error(fallbackMessage);
    }
  };

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Spinner size="xl" />
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-muted/30 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <div className="flex flex-col items-center gap-4 text-center">
          {/* Autonomy company branding */}
          <div className="flex items-center">
            <img
              src="/autonomy_logo.svg"
              alt="Autonomy"
              className="h-10 w-auto"
            />
          </div>
          <h2 className="mt-4 text-center text-3xl font-extrabold text-foreground">
            Sign in to your account
          </h2>
          <p className="mt-2 text-center text-sm text-muted-foreground">
            Or{' '}
            <Link to="/register" className="font-medium text-primary hover:text-primary/80">
              create a new account
            </Link>
          </p>
        </div>

        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          {errors.form && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 space-y-3">
              <div className="flex items-start gap-3">
                <div className="flex-shrink-0 mt-0.5">
                  <AlertCircle className="h-5 w-5 text-destructive" />
                </div>
                <div className="flex-1 space-y-1">
                  <p className="font-medium text-destructive">Unable to sign in</p>
                  <p className="text-sm text-muted-foreground">
                    The email or password you entered doesn't match our records.
                  </p>
                </div>
              </div>

              <div className="pl-8 space-y-2">
                <p className="text-sm font-medium text-foreground">Please check:</p>
                <ul className="text-sm text-muted-foreground space-y-1.5">
                  <li className="flex items-center gap-2">
                    <Mail className="h-3.5 w-3.5 text-muted-foreground/70" />
                    Your email address is spelled correctly
                  </li>
                  <li className="flex items-center gap-2">
                    <KeyRound className="h-3.5 w-3.5 text-muted-foreground/70" />
                    Caps Lock is off and password is correct
                  </li>
                </ul>
              </div>

              <div className="pl-8 pt-1 flex flex-wrap gap-x-4 gap-y-1 text-sm">
                <Link
                  to="/forgot-password"
                  className="text-primary hover:text-primary/80 inline-flex items-center gap-1"
                >
                  <KeyRound className="h-3.5 w-3.5" />
                  Reset password
                </Link>
                <Link
                  to="/register"
                  className="text-primary hover:text-primary/80 inline-flex items-center gap-1"
                >
                  <HelpCircle className="h-3.5 w-3.5" />
                  Create account
                </Link>
              </div>
            </div>
          )}

          <div className="space-y-4">
            <div>
              <Label htmlFor="email" className="sr-only">Email address</Label>
              <Input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                required
                placeholder="Email address"
                value={formData.email}
                onChange={handleChange}
                disabled={authLoading}
                error={errors.email}
                className="rounded-t-md rounded-b-none"
              />
              {errors.email && (
                <p className="mt-1 text-sm text-destructive">{errors.email}</p>
              )}
            </div>
            <div>
              <Label htmlFor="password" className="sr-only">Password</Label>
              <div className="relative">
                <Input
                  id="password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  required
                  placeholder="Password"
                  value={formData.password}
                  onChange={handleChange}
                  disabled={authLoading}
                  error={errors.password}
                  className="rounded-t-none rounded-b-md -mt-px pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute inset-y-0 right-0 flex items-center pr-3 text-muted-foreground hover:text-foreground"
                  tabIndex={-1}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? (
                    <EyeOff className="h-4 w-4" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                </button>
              </div>
              {errors.password && (
                <p className="mt-1 text-sm text-destructive">{errors.password}</p>
              )}
            </div>
          </div>

          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <input
                id="remember-me"
                name="rememberMe"
                type="checkbox"
                className="h-4 w-4 text-primary focus:ring-primary border-input rounded"
                checked={formData.rememberMe}
                onChange={handleChange}
                disabled={authLoading}
              />
              <label htmlFor="remember-me" className="ml-2 block text-sm text-foreground">
                Remember me
              </label>
            </div>

            <div className="text-sm">
              <Link to="/forgot-password" className="font-medium text-primary hover:text-primary/80">
                Forgot your password?
              </Link>
            </div>
          </div>

          <div>
            <Button
              type="submit"
              disabled={authLoading}
              className="w-full"
              size="lg"
            >
              {authLoading ? (
                <>
                  <Spinner size="sm" className="mr-2" />
                  Signing in...
                </>
              ) : 'Sign in'}
            </Button>
          </div>
        </form>

        {contactPrompt && (
          <ContactSystemAdminForm
            email={contactPrompt.email}
            systemAdminEmail={contactPrompt.systemAdminEmail}
            onClose={() => setContactPrompt(null)}
          />
        )}

        <div className="mt-6">
          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-border"></div>
            </div>
            <div className="relative flex justify-center text-sm">
              <span className="px-2 bg-muted/30 text-muted-foreground">Or continue with</span>
            </div>
          </div>

          <div className="mt-6 grid grid-cols-2 gap-3">
            <Button variant="outline" type="button" className="w-full">
              <span className="sr-only">Sign in with Google</span>
              <svg className="w-5 h-5" aria-hidden="true" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12.48 10.92v3.28h7.84c-.24 1.84-.853 3.187-1.787 4.133-1.147 1.147-2.933 2.4-6.053 2.4-4.827 0-8.6-3.893-8.6-8.72s3.773-8.72 8.6-8.72c2.6 0 4.507 1.027 5.907 2.347l2.307-2.307C18.747 1.44 16.133 0 12.48 0 5.867 0 .307 5.387.307 12s5.56 12 12.173 12c3.573 0 6.267-1.173 8.373-3.36 2.16-2.16 2.84-5.213 2.84-7.667 0-.76-.053-1.467-.173-2.053H12.48z" />
              </svg>
            </Button>

            <Button variant="outline" type="button" className="w-full">
              <span className="sr-only">Sign in with GitHub</span>
              <svg className="w-5 h-5" aria-hidden="true" fill="currentColor" viewBox="0 0 20 20">
                <path
                  fillRule="evenodd"
                  d="M10 0C4.477 0 0 4.484 0 10.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.603-3.369-1.343-3.369-1.343-.454-1.156-1.11-1.462-1.11-1.462-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.268 2.75 1.026A9.564 9.564 0 0110 4.844c.85.004 1.705.115 2.504.337 1.909-1.294 2.747-1.027 2.747-1.027.546 1.379.203 2.398.1 2.651.64.699 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.942.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.743 0 .267.18.578.688.48C17.14 18.178 20 14.426 20 10.017 20 4.484 15.522 0 10 0z"
                  clipRule="evenodd"
                />
              </svg>
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Login;
