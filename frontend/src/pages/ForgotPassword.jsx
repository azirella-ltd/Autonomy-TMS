import { useState } from 'react';
import { Link } from 'react-router-dom';
import { toast } from 'react-toastify';
import { CheckCircle2, Mail } from 'lucide-react';
import simulationApi from '../services/api';
import { Card, CardContent, Button, Alert, Input, Label } from '../components/common';
import { cn } from '@azirella-ltd/autonomy-frontend';

const ForgotPassword = () => {
  const [email, setEmail] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [emailSent, setEmailSent] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!email) {
      toast.error('Please enter your email address');
      return;
    }

    setIsSubmitting(true);

    try {
      await simulationApi.requestPasswordReset(email);
      setEmailSent(true);
      toast.success('Password reset instructions have been sent to your email');
    } catch (error) {
      console.error('Password reset request failed:', error);
      const errorMessage = error.response?.data?.detail || 'Failed to send password reset email';
      toast.error(errorMessage);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (emailSent) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background py-12 px-4 sm:px-6 lg:px-8">
        <div className="max-w-md w-full space-y-8 text-center">
          <Alert variant="success" className="text-left">
            <div className="flex items-start gap-3">
              <CheckCircle2 className="h-5 w-5 text-emerald-500 flex-shrink-0 mt-0.5" />
              <div>
                <h3 className="text-sm font-medium text-emerald-800 dark:text-emerald-200">Check your email</h3>
                <p className="mt-2 text-sm text-emerald-700 dark:text-emerald-300">
                  We've sent password reset instructions to {email}. Please check your email and follow the link to reset your password.
                </p>
                <div className="mt-4">
                  <button
                    type="button"
                    className="text-sm font-medium text-emerald-800 dark:text-emerald-200 hover:text-emerald-700 dark:hover:text-emerald-100 focus:outline-none focus:underline transition duration-150 ease-in-out"
                    onClick={() => setEmailSent(false)}
                  >
                    Resend email
                  </button>
                </div>
              </div>
            </div>
          </Alert>
          <div className="text-sm text-center">
            <Link to="/login" className="font-medium text-primary hover:text-primary-hover">
              Back to sign in
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <div>
          <h2 className="mt-6 text-center text-3xl font-extrabold text-foreground">
            Forgot your password?
          </h2>
          <p className="mt-2 text-center text-sm text-muted-foreground">
            Enter your email address and we'll send you a link to reset your password.
          </p>
        </div>

        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          <div className="space-y-4">
            <div>
              <Label htmlFor="email-address" className="sr-only">
                Email address
              </Label>
              <Input
                id="email-address"
                name="email"
                type="email"
                autoComplete="email"
                required
                placeholder="Email address"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
          </div>

          <div>
            <Button
              type="submit"
              loading={isSubmitting}
              disabled={isSubmitting}
              fullWidth
              leftIcon={<Mail className="h-4 w-4" />}
            >
              {isSubmitting ? 'Sending...' : 'Send reset link'}
            </Button>
          </div>

          <div className="text-sm text-center">
            <Link to="/login" className="font-medium text-primary hover:text-primary-hover">
              Back to sign in
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
};

export default ForgotPassword;
