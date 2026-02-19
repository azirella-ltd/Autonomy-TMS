import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { toast } from 'react-toastify';
import simulationApi from '../services/api';
import {
  Card,
  CardHeader,
  CardContent,
  Button,
  Input,
  Label,
  FormField,
  Spinner,
  Tabs,
  TabsList,
  Tab,
  TabPanel,
} from '../components/common';
import { Shield, Monitor, Trash2 } from 'lucide-react';
import { cn } from '../lib/utils/cn';

const Profile = () => {
  const { user, updateProfile, changePassword } = useAuth();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('profile');
  const [isLoading, setIsLoading] = useState(false);
  const [mfaStatus, setMfaStatus] = useState({
    enabled: false,
    loading: false
  });

  // Profile form state
  const [profileForm, setProfileForm] = useState({
    username: '',
    email: '',
    firstName: '',
    lastName: '',
  });

  // Password form state
  const [passwordForm, setPasswordForm] = useState({
    currentPassword: '',
    newPassword: '',
    confirmPassword: '',
  });

  const [errors, setErrors] = useState({});

  // Initialize form with user data
  useEffect(() => {
    if (user) {
      setProfileForm({
        username: user.username || '',
        email: user.email || '',
        firstName: user.first_name || '',
        lastName: user.last_name || '',
      });

      setMfaStatus(prev => ({
        ...prev,
        enabled: user.mfa_enabled || false
      }));
    }
  }, [user]);

  const handleProfileChange = (e) => {
    const { name, value } = e.target;
    setProfileForm(prev => ({
      ...prev,
      [name]: value
    }));

    // Clear error when user types
    if (errors[name]) {
      setErrors(prev => ({
        ...prev,
        [name]: null
      }));
    }
  };

  const handlePasswordChange = (e) => {
    const { name, value } = e.target;
    setPasswordForm(prev => ({
      ...prev,
      [name]: value
    }));

    // Clear error when user types
    if (errors[name]) {
      setErrors(prev => ({
        ...prev,
        [name]: null
      }));
    }
  };

  const validateProfileForm = () => {
    const newErrors = {};

    if (!profileForm.username.trim()) {
      newErrors.username = 'Username is required';
    }

    if (!profileForm.email) {
      newErrors.email = 'Email is required';
    } else if (!/\S+@\S+\.\S+/.test(profileForm.email)) {
      newErrors.email = 'Email address is invalid';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const validatePasswordForm = () => {
    const newErrors = {};

    if (!passwordForm.currentPassword) {
      newErrors.currentPassword = 'Current password is required';
    }

    if (!passwordForm.newPassword) {
      newErrors.newPassword = 'New password is required';
    } else if (passwordForm.newPassword.length < 8) {
      newErrors.newPassword = 'Password must be at least 8 characters long';
    } else if (!/(?=.*[a-z])(?=.*[A-Z])(?=.*\d)/.test(passwordForm.newPassword)) {
      newErrors.newPassword = 'Password must contain at least one uppercase letter, one lowercase letter, and one number';
    }

    if (passwordForm.newPassword !== passwordForm.confirmPassword) {
      newErrors.confirmPassword = 'Passwords do not match';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleProfileSubmit = async (e) => {
    e.preventDefault();

    if (!validateProfileForm()) {
      return;
    }

    setIsLoading(true);

    try {
      await updateProfile(profileForm);
      toast.success('Profile updated successfully');
    } catch (error) {
      console.error('Profile update failed:', error);
      const errorMessage = error.response?.data?.detail || 'Failed to update profile';
      toast.error(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const handlePasswordSubmit = async (e) => {
    e.preventDefault();

    if (!validatePasswordForm()) {
      return;
    }

    setIsLoading(true);

    try {
      await changePassword(
        passwordForm.currentPassword,
        passwordForm.newPassword
      );

      toast.success('Password changed successfully');
      setPasswordForm({
        currentPassword: '',
        newPassword: '',
        confirmPassword: '',
      });
    } catch (error) {
      console.error('Password change failed:', error);
      const errorMessage = error.response?.data?.detail || 'Failed to change password';
      toast.error(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const toggleMfa = async () => {
    if (mfaStatus.loading) return;

    setMfaStatus(prev => ({ ...prev, loading: true }));

    try {
      if (mfaStatus.enabled) {
        // Disable MFA
        await simulationApi.disableMFA();
        setMfaStatus({ enabled: false, loading: false });
        toast.success('Two-factor authentication has been disabled');
      } else {
        // Enable MFA - this would typically redirect to a setup page
        // or show a QR code for the authenticator app
        navigate('/mfa/setup');
      }
    } catch (error) {
      console.error('Failed to update MFA status:', error);
      toast.error('Failed to update two-factor authentication settings');
      setMfaStatus(prev => ({ ...prev, loading: false }));
    }
  };

  return (
    <div className="min-h-screen bg-background py-8 px-4 sm:px-6 lg:px-8">
      <div className="max-w-4xl mx-auto">
        <Card>
          <CardHeader className="border-b border-border pb-6">
            <h3 className="text-lg font-medium text-foreground">
              Account Settings
            </h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Manage your account settings and preferences
            </p>
          </CardHeader>

          <Tabs value={activeTab} onChange={(_, val) => setActiveTab(val)}>
            <TabsList className="border-b border-border">
              <Tab value="profile">Profile</Tab>
              <Tab value="password">Password</Tab>
              <Tab value="security">Security</Tab>
            </TabsList>

            <CardContent className="pt-6">
              <TabPanel value="profile">
                <form onSubmit={handleProfileSubmit} className="space-y-6">
                  <div className="grid grid-cols-6 gap-6">
                    <div className="col-span-6 sm:col-span-3">
                      <FormField label="First name">
                        <Input
                          type="text"
                          name="firstName"
                          id="firstName"
                          value={profileForm.firstName}
                          onChange={handleProfileChange}
                        />
                      </FormField>
                    </div>

                    <div className="col-span-6 sm:col-span-3">
                      <FormField label="Last name">
                        <Input
                          type="text"
                          name="lastName"
                          id="lastName"
                          value={profileForm.lastName}
                          onChange={handleProfileChange}
                        />
                      </FormField>
                    </div>

                    <div className="col-span-6 sm:col-span-4">
                      <FormField label="Email address" error={errors.email}>
                        <Input
                          type="email"
                          name="email"
                          id="email"
                          autoComplete="email"
                          value={profileForm.email}
                          onChange={handleProfileChange}
                          error={!!errors.email}
                        />
                      </FormField>
                    </div>

                    <div className="col-span-6 sm:col-span-4">
                      <FormField label="Username" error={errors.username}>
                        <Input
                          type="text"
                          name="username"
                          id="username"
                          autoComplete="username"
                          value={profileForm.username}
                          onChange={handleProfileChange}
                          error={!!errors.username}
                        />
                      </FormField>
                    </div>
                  </div>

                  <div className="flex justify-end gap-3">
                    <Button type="button" variant="outline">
                      Cancel
                    </Button>
                    <Button type="submit" loading={isLoading}>
                      {isLoading ? 'Saving...' : 'Save'}
                    </Button>
                  </div>
                </form>
              </TabPanel>

              <TabPanel value="password">
                <form onSubmit={handlePasswordSubmit} className="space-y-6">
                  <div className="space-y-4">
                    <FormField label="Current password" error={errors.currentPassword}>
                      <Input
                        type="password"
                        name="currentPassword"
                        id="currentPassword"
                        autoComplete="current-password"
                        value={passwordForm.currentPassword}
                        onChange={handlePasswordChange}
                        error={!!errors.currentPassword}
                      />
                    </FormField>

                    <FormField label="New password" error={errors.newPassword}>
                      <Input
                        type="password"
                        name="newPassword"
                        id="newPassword"
                        autoComplete="new-password"
                        value={passwordForm.newPassword}
                        onChange={handlePasswordChange}
                        error={!!errors.newPassword}
                      />
                    </FormField>

                    <FormField label="Confirm new password" error={errors.confirmPassword}>
                      <Input
                        type="password"
                        name="confirmPassword"
                        id="confirmPassword"
                        autoComplete="new-password"
                        value={passwordForm.confirmPassword}
                        onChange={handlePasswordChange}
                        error={!!errors.confirmPassword}
                      />
                    </FormField>
                  </div>

                  <div className="flex justify-end gap-3">
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => setPasswordForm({
                        currentPassword: '',
                        newPassword: '',
                        confirmPassword: '',
                      })}
                    >
                      Cancel
                    </Button>
                    <Button type="submit" loading={isLoading}>
                      {isLoading ? 'Updating...' : 'Update Password'}
                    </Button>
                  </div>
                </form>
              </TabPanel>

              <TabPanel value="security">
                <div className="space-y-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <h4 className="text-lg font-medium text-foreground">Two-factor authentication</h4>
                      <p className="text-sm text-muted-foreground">
                        {mfaStatus.enabled
                          ? 'Two-factor authentication is currently enabled.'
                          : 'Add an extra layer of security to your account with two-factor authentication.'}
                      </p>
                    </div>
                    <Button
                      type="button"
                      onClick={toggleMfa}
                      disabled={mfaStatus.loading}
                      variant={mfaStatus.enabled ? 'destructive' : 'default'}
                    >
                      {mfaStatus.loading ? (
                        'Loading...'
                      ) : mfaStatus.enabled ? (
                        'Disable'
                      ) : (
                        'Enable'
                      )}
                    </Button>
                  </div>

                  <div className="border-t border-border pt-6">
                    <h4 className="text-lg font-medium text-foreground flex items-center gap-2">
                      <Monitor className="h-5 w-5" />
                      Sessions
                    </h4>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Manage and sign out of your active sessions on other browsers and devices.
                    </p>
                    <div className="mt-4">
                      <Button type="button" variant="outline">
                        View active sessions
                      </Button>
                    </div>
                  </div>

                  <div className="border-t border-border pt-6">
                    <h4 className="text-lg font-medium text-warning flex items-center gap-2">
                      <Shield className="h-5 w-5" />
                      Danger Zone
                    </h4>
                    <div className="mt-4">
                      <Button
                        type="button"
                        variant="outline"
                        className="border-destructive text-destructive hover:bg-destructive/10"
                        leftIcon={<Trash2 className="h-4 w-4" />}
                      >
                        Delete Account
                      </Button>
                      <p className="mt-2 text-sm text-muted-foreground">
                        Permanently delete your account and all of your data.
                      </p>
                    </div>
                  </div>
                </div>
              </TabPanel>
            </CardContent>
          </Tabs>
        </Card>
      </div>
    </div>
  );
};

export default Profile;
