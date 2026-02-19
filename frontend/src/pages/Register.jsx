import { useState, useEffect } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'react-toastify';
import simulationApi from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { buildLoginRedirectPath } from '../utils/authUtils';
import { Button, Input, Label, Alert, AlertDescription, Spinner } from '../components/common';
import { CheckCircle2 } from 'lucide-react';

const Register = () => {
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    firstName: '',
    lastName: '',
    password: '',
    confirmPassword: '',
    acceptTerms: false,
  });

  const [errors, setErrors] = useState({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [verificationSent, setVerificationSent] = useState(false);
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/');
    }
  }, [isAuthenticated, navigate]);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));

    if (errors[name]) {
      setErrors(prev => ({
        ...prev,
        [name]: null
      }));
    }
  };

  const validateForm = () => {
    const newErrors = {};

    if (!formData.username.trim()) {
      newErrors.username = 'Username is required';
    } else if (formData.username.length < 3) {
      newErrors.username = 'Username must be at least 3 characters';
    } else if (!/^[a-zA-Z0-9_]+$/.test(formData.username)) {
      newErrors.username = 'Username can only contain letters, numbers, and underscores';
    }

    if (!formData.email) {
      newErrors.email = 'Email is required';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      newErrors.email = 'Please enter a valid email address';
    }

    if (!formData.firstName.trim()) {
      newErrors.firstName = 'First name is required';
    }

    if (!formData.lastName.trim()) {
      newErrors.lastName = 'Last name is required';
    }

    if (!formData.password) {
      newErrors.password = 'Password is required';
    } else if (formData.password.length < 8) {
      newErrors.password = 'Password must be at least 8 characters';
    } else if (!/(?=.*[a-z])(?=.*[A-Z])(?=.*\d)/.test(formData.password)) {
      newErrors.password = 'Must include uppercase, lowercase, and number';
    }

    if (formData.password !== formData.confirmPassword) {
      newErrors.confirmPassword = 'Passwords do not match';
    }

    if (!formData.acceptTerms) {
      newErrors.acceptTerms = 'You must accept the terms and conditions';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    setIsSubmitting(true);

    try {
      const { confirmPassword, acceptTerms, ...userData } = formData;
      const { success, error } = await simulationApi.register(userData);

      if (success) {
        setVerificationSent(true);
        toast.success('Registration successful! Please check your email to verify your account.');

        setTimeout(() => {
          const redirectTo = searchParams.get('redirect') || '/';
          const loginPath = buildLoginRedirectPath(redirectTo);
          navigate(loginPath);
        }, 5000);
      } else {
        throw new Error(error || 'Registration failed. Please try again.');
      }
    } catch (error) {
      console.error('Registration error:', error);
      toast.error(error.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (verificationSent) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-muted/30 py-12 px-4 sm:px-6 lg:px-8">
        <div className="max-w-md w-full space-y-8 text-center">
          <Alert variant="success">
            <CheckCircle2 className="h-5 w-5" />
            <div>
              <h3 className="font-medium">Verification Email Sent</h3>
              <AlertDescription className="mt-2">
                We've sent a verification link to <span className="font-medium">{formData.email}</span>.
                Please check your email and click the link to verify your account.
              </AlertDescription>
              <p className="mt-4 text-sm text-muted-foreground">
                You'll be redirected to the login page in a few seconds...
              </p>
            </div>
          </Alert>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-muted/30 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-6">
        <div>
          <h2 className="text-center text-3xl font-extrabold text-foreground">
            Create your account
          </h2>
          <p className="mt-4 text-center text-sm text-muted-foreground">
            By creating an account, you agree to our{' '}
            <a href="/terms" className="font-medium text-primary hover:text-primary/80">
              Terms of Service
            </a>{' '}
            and{' '}
            <a href="/privacy" className="font-medium text-primary hover:text-primary/80">
              Privacy Policy
            </a>
          </p>
          <p className="mt-2 text-center text-sm text-muted-foreground">
            Or{' '}
            <Link
              to="/login"
              className="font-medium text-primary hover:text-primary/80"
            >
              sign in to your existing account
            </Link>
          </p>
        </div>

        <div className="bg-card py-8 px-4 shadow rounded-lg sm:px-10 border">
          <form className="space-y-6" onSubmit={handleSubmit}>
            <div className="grid grid-cols-1 gap-y-6 gap-x-4 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <Label htmlFor="email">
                  Email address <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  value={formData.email}
                  onChange={handleChange}
                  disabled={isSubmitting}
                  error={errors.email}
                  className="mt-1"
                />
                {errors.email && (
                  <p className="mt-1 text-sm text-destructive">{errors.email}</p>
                )}
              </div>

              <div className="sm:col-span-1">
                <Label htmlFor="firstName">
                  First name <span className="text-destructive">*</span>
                </Label>
                <Input
                  type="text"
                  id="firstName"
                  name="firstName"
                  autoComplete="given-name"
                  value={formData.firstName}
                  onChange={handleChange}
                  disabled={isSubmitting}
                  error={errors.firstName}
                  className="mt-1"
                />
                {errors.firstName && (
                  <p className="mt-1 text-sm text-destructive">{errors.firstName}</p>
                )}
              </div>

              <div className="sm:col-span-1">
                <Label htmlFor="lastName">
                  Last name <span className="text-destructive">*</span>
                </Label>
                <Input
                  type="text"
                  id="lastName"
                  name="lastName"
                  autoComplete="family-name"
                  value={formData.lastName}
                  onChange={handleChange}
                  disabled={isSubmitting}
                  error={errors.lastName}
                  className="mt-1"
                />
                {errors.lastName && (
                  <p className="mt-1 text-sm text-destructive">{errors.lastName}</p>
                )}
              </div>

              <div className="sm:col-span-2">
                <Label htmlFor="username">
                  Username <span className="text-destructive">*</span>
                </Label>
                <div className="mt-1 flex rounded-md shadow-sm">
                  <span className="inline-flex items-center px-3 rounded-l-md border border-r-0 border-input bg-muted text-muted-foreground sm:text-sm">
                    @
                  </span>
                  <Input
                    type="text"
                    id="username"
                    name="username"
                    autoComplete="username"
                    placeholder="username"
                    value={formData.username}
                    onChange={handleChange}
                    disabled={isSubmitting}
                    error={errors.username}
                    className="rounded-l-none"
                  />
                </div>
                {errors.username ? (
                  <p className="mt-1 text-sm text-destructive">{errors.username}</p>
                ) : (
                  <p className="mt-1 text-xs text-muted-foreground">Letters, numbers, and underscores only</p>
                )}
              </div>

              <div className="sm:col-span-2">
                <Label htmlFor="password">
                  Password <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="new-password"
                  value={formData.password}
                  onChange={handleChange}
                  disabled={isSubmitting}
                  error={errors.password}
                  className="mt-1"
                />
                {errors.password ? (
                  <p className="mt-1 text-sm text-destructive">{errors.password}</p>
                ) : (
                  <p className="mt-1 text-xs text-muted-foreground">
                    At least 8 characters with uppercase, lowercase, and number
                  </p>
                )}
              </div>

              <div className="sm:col-span-2">
                <Label htmlFor="confirmPassword">
                  Confirm password <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="confirmPassword"
                  name="confirmPassword"
                  type="password"
                  autoComplete="new-password"
                  value={formData.confirmPassword}
                  onChange={handleChange}
                  disabled={isSubmitting}
                  error={errors.confirmPassword}
                  className="mt-1"
                />
                {errors.confirmPassword && (
                  <p className="mt-1 text-sm text-destructive">{errors.confirmPassword}</p>
                )}
              </div>
            </div>

            <div className="sm:col-span-2">
              <div className="flex items-start">
                <div className="flex items-center h-5">
                  <input
                    id="terms"
                    name="acceptTerms"
                    type="checkbox"
                    className="focus:ring-primary h-4 w-4 text-primary border-input rounded"
                    checked={formData.acceptTerms}
                    onChange={handleChange}
                    disabled={isSubmitting}
                  />
                </div>
                <div className="ml-3 text-sm">
                  <label htmlFor="terms" className="font-medium text-foreground">
                    I agree to the{' '}
                    <a href="/terms" className="text-primary hover:text-primary/80">
                      Terms of Service
                    </a>{' '}
                    and{' '}
                    <a href="/privacy" className="text-primary hover:text-primary/80">
                      Privacy Policy
                    </a>
                    <span className="text-destructive">*</span>
                  </label>
                  {errors.acceptTerms && (
                    <p className="mt-1 text-destructive">{errors.acceptTerms}</p>
                  )}
                </div>
              </div>
            </div>

            <div className="sm:col-span-2">
              <Button
                type="submit"
                disabled={isSubmitting}
                className="w-full"
                size="lg"
              >
                {isSubmitting ? (
                  <>
                    <Spinner size="sm" className="mr-2" />
                    Creating Account...
                  </>
                ) : 'Create Account'}
              </Button>
            </div>
          </form>
        </div>

        <div className="mt-6">
          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-border"></div>
            </div>
            <div className="relative flex justify-center text-sm">
              <span className="px-2 bg-muted/30 text-muted-foreground">Or continue with</span>
            </div>
          </div>

          <div className="mt-6 grid grid-cols-3 gap-3">
            <Button variant="outline" asChild>
              <a href="/api/auth/google">
                <span className="sr-only">Sign in with Google</span>
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M12.48 10.92v3.28h7.84c-.24 1.84-.853 3.187-1.787 4.133-1.147 1.147-2.933 2.4-6.053 2.4-4.827 0-8.6-3.893-8.6-8.72s3.773-8.72 8.6-8.72c2.6 0 4.507 1.027 5.907 2.347l2.307-2.307C18.747 1.44 16.133 0 12.48 0 5.867 0 .307 5.387.307 12s5.56 12 12.173 12c3.573 0 6.267-1.173 8.373-3.36 2.16-2.16 2.84-5.213 2.84-7.667 0-.76-.053-1.467-.173-2.053H12.48z" />
                </svg>
              </a>
            </Button>

            <Button variant="outline" asChild>
              <a href="/api/auth/github">
                <span className="sr-only">Sign in with GitHub</span>
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path fillRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.743 0 .267.18.578.688.48A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" clipRule="evenodd" />
                </svg>
              </a>
            </Button>

            <Button variant="outline" asChild>
              <a href="/api/auth/microsoft">
                <span className="sr-only">Sign in with Microsoft</span>
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 16 16" aria-hidden="true">
                  <path d="M7.462 0H0v7.19h7.465V0zM16 0H8.538v7.19H16V0zM7.465 8.211H0V16h7.465V8.211zm8.535 0H8.538V16H16V8.211z" />
                </svg>
              </a>
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Register;
