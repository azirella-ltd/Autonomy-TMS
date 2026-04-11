import { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useHelp } from '../contexts/HelpContext';
import {
  User,
  Bell,
  Settings2,
  ShieldCheck,
  Moon,
  Sun,
  Monitor,
  Check,
  HelpCircle,
  XCircle
} from 'lucide-react';
import { Card, CardContent, Button, Alert, Input, Label, Select, SelectOption } from '../components/common';
import { cn } from '@azirella-ltd/autonomy-frontend';

const Settings = () => {
  const { user } = useAuth();
  const { openHelp } = useHelp();

  // Settings state
  const [settings, setSettings] = useState({
    theme: 'system',
    notifications: {
      email: true,
      inApp: true,
      sound: true,
    },
    privacy: {
      showOnlineStatus: true,
      allowFriendRequests: true,
      showInLeaderboards: true,
    },
    simulation: {
      animationSpeed: 'normal',
      confirmBeforeLeavingGame: true,
      showTutorialTips: true,
    },
  });

  const [isSaving, setIsSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState({ type: '', message: '' });

  // Load saved settings when component mounts
  useEffect(() => {
    const savedSettings = localStorage.getItem('simulationSettings');
    if (savedSettings) {
      try {
        setSettings(JSON.parse(savedSettings));
      } catch (error) {
        console.error('Failed to parse saved settings', error);
      }
    }
  }, []);

  // Save settings to localStorage and update UI state
  const saveSettings = async (newSettings) => {
    setIsSaving(true);
    setSaveStatus({ type: '', message: '' });

    try {
      // In a real app, you would save these to your backend
      // await api.updateUserSettings(user.id, newSettings);

      // For now, just save to localStorage
      localStorage.setItem('simulationSettings', JSON.stringify(newSettings));

      // Update local state
      setSettings(newSettings);

      // Apply theme if changed
      if (settings.theme !== newSettings.theme) {
        applyTheme(newSettings.theme);
      }

      setSaveStatus({
        type: 'success',
        message: 'Settings saved successfully!'
      });
    } catch (error) {
      console.error('Failed to save settings', error);
      setSaveStatus({
        type: 'error',
        message: 'Failed to save settings. Please try again.'
      });
    } finally {
      setIsSaving(false);

      // Clear success message after 3 seconds
      if (saveStatus.type === 'success') {
        setTimeout(() => {
          setSaveStatus({ type: '', message: '' });
        }, 3000);
      }
    }
  };

  // Apply theme to document
  const applyTheme = (theme) => {
    const root = window.document.documentElement;

    // Remove all theme classes
    root.classList.remove('light', 'dark');

    if (theme === 'system') {
      // Use system preference
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      root.classList.add(prefersDark ? 'dark' : 'light');
    } else {
      root.classList.add(theme);
    }

    // Add a class to the body to indicate the theme
    document.body.className = `theme-${theme}`;
  };

  // Handle setting changes
  const handleSettingChange = (section, key, value) => {
    const newSettings = {
      ...settings,
      [section]: {
        ...settings[section],
        [key]: value
      }
    };

    // Special handling for theme changes
    if (section === 'theme') {
      newSettings.theme = value;
      applyTheme(value);
    }

    saveSettings(newSettings);
  };

  // Toggle boolean settings
  const toggleSetting = (section, key) => {
    handleSettingChange(section, key, !settings[section][key]);
  };

  // Render a section header
  const SectionHeader = ({ icon: Icon, title, description }) => (
    <div className="md:col-span-1">
      <div className="px-0">
        <div className="flex items-center">
          <Icon className="h-5 w-5 mr-2 text-muted-foreground" />
          <h3 className="text-lg font-semibold text-foreground">{title}</h3>
        </div>
        <p className="text-sm text-muted-foreground mt-1">{description}</p>
      </div>
    </div>
  );

  // Render a setting control
  const SettingControl = ({ label, description, children, className = '' }) => (
    <div className={cn('py-4', className)}>
      <div className="flex items-center justify-between">
        <div className="flex-grow">
          <p className="font-medium text-foreground">{label}</p>
          {description && (<p className="text-sm text-muted-foreground mt-0.5">{description}</p>)}
        </div>
        <div className="ml-4">
          {children}
        </div>
      </div>
    </div>
  );

  // Render a toggle switch
  const ToggleSwitch = ({ checked, onChange, id }) => (
    <button
      type="button"
      className={cn(
        'relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out',
        'focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2',
        checked ? 'bg-primary' : 'bg-muted'
      )}
      role="switch"
      aria-checked={checked}
      onClick={onChange}
      id={id}
    >
      <span className="sr-only">Toggle {id}</span>
      <span
        aria-hidden="true"
        className={cn(
          'pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out',
          checked ? 'translate-x-5' : 'translate-x-0'
        )}
      />
    </button>
  );

  return (
    <div className="max-w-7xl mx-auto p-8">
      <div className="md:flex md:items-center md:justify-between mb-8">
        <div className="flex-1 min-w-0">
          <h2 className="text-2xl font-bold text-foreground">Settings</h2>
          <p className="text-sm text-muted-foreground mt-1">Manage your account settings and preferences</p>
        </div>
        <div className="mt-4 flex md:mt-0 md:ml-4">
          <Button
            variant="secondary"
            onClick={() => openHelp('settings')}
            leftIcon={<HelpCircle className="h-5 w-5" />}
          >
            Help
          </Button>
        </div>
      </div>

      {saveStatus.message && (
        <Alert
          variant={saveStatus.type === 'error' ? 'error' : 'success'}
          className="mb-6"
          icon={saveStatus.type === 'error' ? XCircle : Check}
        >
          {saveStatus.message}
        </Alert>
      )}

      <div className="mt-10 divide-y divide-border">
        {/* Profile Settings */}
        <div className="space-y-6 py-6">
          <div className="md:grid md:grid-cols-3 md:gap-6">
            <SectionHeader
              icon={User}
              title="Profile"
              description="Update your profile information and avatar"
            />
            <div className="mt-5 md:mt-0 md:col-span-2">
              <Card variant="default" padding="none">
                <CardContent className="p-6">
                  <div className="grid grid-cols-6 gap-6">
                    <div className="col-span-6 sm:col-span-4">
                      <Label htmlFor="username">Username</Label>
                      <Input
                        type="text"
                        name="username"
                        id="username"
                        value={user?.username || ''}
                        disabled={isSaving}
                        className="mt-1"
                      />
                    </div>

                    <div className="col-span-6 sm:col-span-4">
                      <Label htmlFor="email">Email address</Label>
                      <Input
                        type="email"
                        name="email"
                        id="email"
                        value={user?.email || ''}
                        disabled={isSaving}
                        className="mt-1"
                      />
                    </div>

                    <div className="col-span-6">
                      <Label htmlFor="bio">Bio</Label>
                      <div className="mt-1">
                        <textarea
                          id="bio"
                          name="bio"
                          rows={3}
                          className={cn(
                            'w-full rounded-md border border-input bg-background px-3 py-2 text-sm',
                            'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
                            'placeholder:text-muted-foreground'
                          )}
                          placeholder="Tell us a little about yourself"
                          defaultValue={''}
                        />
                      </div>
                      <p className="mt-2 text-sm text-muted-foreground">
                        Brief description for your profile. URLs are hyperlinked.
                      </p>
                    </div>

                    <div className="col-span-6">
                      <Label>Photo</Label>
                      <div className="mt-1 flex items-center">
                        <span className="h-12 w-12 rounded-full overflow-hidden bg-muted">
                          <svg className="h-full w-full text-muted-foreground" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M24 20.993V24H0v-2.996A14.977 14.977 0 0112.004 15c4.904 0 9.26 2.354 11.996 5.993zM16.002 8.999a4 4 0 11-8 0 4 4 0 018 0z" />
                          </svg>
                        </span>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="ml-5"
                        >
                          Change
                        </Button>
                      </div>
                    </div>
                  </div>
                </CardContent>
                <div className="p-6 pt-0 text-right">
                  <Button
                    type="submit"
                    disabled={isSaving}
                    loading={isSaving}
                  >
                    {isSaving ? 'Saving...' : 'Save'}
                  </Button>
                </div>
              </Card>
            </div>
          </div>
        </div>

        {/* Theme Settings */}
        <div className="py-6">
          <div className="md:grid md:grid-cols-3 md:gap-6">
            <SectionHeader
              icon={settings.theme === 'dark' ? Moon : settings.theme === 'light' ? Sun : Monitor}
              title="Appearance"
              description="Customize how the app looks and feels"
            />
            <div className="mt-5 md:mt-0 md:col-span-2">
              <Card variant="default" padding="none">
                <CardContent className="p-6 space-y-6">
                  <SettingControl
                    label="Theme"
                    description="Select your preferred theme"
                  >
                    <div className="flex items-center space-x-4">
                      <div className="flex items-center">
                        <input
                          id="theme-light"
                          name="theme"
                          type="radio"
                          checked={settings.theme === 'light'}
                          onChange={() => handleSettingChange('theme', 'theme', 'light')}
                          className="h-4 w-4 text-primary focus:ring-primary border-input"
                        />
                        <label htmlFor="theme-light" className="ml-2 block text-sm text-foreground">
                          <div className="flex items-center">
                            <Sun className="h-5 w-5 mr-1 text-yellow-500" />
                            Light
                          </div>
                        </label>
                      </div>

                      <div className="flex items-center">
                        <input
                          id="theme-dark"
                          name="theme"
                          type="radio"
                          checked={settings.theme === 'dark'}
                          onChange={() => handleSettingChange('theme', 'theme', 'dark')}
                          className="h-4 w-4 text-primary focus:ring-primary border-input"
                        />
                        <label htmlFor="theme-dark" className="ml-2 block text-sm text-foreground">
                          <div className="flex items-center">
                            <Moon className="h-5 w-5 mr-1 text-info" />
                            Dark
                          </div>
                        </label>
                      </div>

                      <div className="flex items-center">
                        <input
                          id="theme-system"
                          name="theme"
                          type="radio"
                          checked={settings.theme === 'system'}
                          onChange={() => handleSettingChange('theme', 'theme', 'system')}
                          className="h-4 w-4 text-primary focus:ring-primary border-input"
                        />
                        <label htmlFor="theme-system" className="ml-2 block text-sm text-foreground">
                          <div className="flex items-center">
                            <Monitor className="h-5 w-5 mr-1 text-muted-foreground" />
                            System
                          </div>
                        </label>
                      </div>
                    </div>
                  </SettingControl>

                  <SettingControl
                    label="Animation Speed"
                    description="Adjust the speed of animations in the app"
                  >
                    <Select
                      id="animation-speed"
                      value={settings.simulation.animationSpeed}
                      onChange={(e) => handleSettingChange('game', 'animationSpeed', e.target.value)}
                      className="w-32"
                    >
                      <SelectOption value="fast">Fast</SelectOption>
                      <SelectOption value="normal">Normal</SelectOption>
                      <SelectOption value="slow">Slow</SelectOption>
                      <SelectOption value="off">Off</SelectOption>
                    </Select>
                  </SettingControl>
                </CardContent>
              </Card>
            </div>
          </div>
        </div>

        {/* Notification Settings */}
        <div className="py-6">
          <div className="md:grid md:grid-cols-3 md:gap-6">
            <SectionHeader
              icon={Bell}
              title="Notifications"
              description="Manage how and when you receive notifications"
            />
            <div className="mt-5 md:mt-0 md:col-span-2">
              <Card variant="default" padding="none">
                <CardContent className="p-6 space-y-6">
                  {/* Global Channels */}
                  <div>
                    <h4 className="font-semibold text-sm text-muted-foreground uppercase tracking-wide mb-3">Delivery Channels</h4>
                    <SettingControl
                      label="Email notifications"
                      description="Receive alerts and digests to your registered email"
                    >
                      <ToggleSwitch
                        checked={settings.notifications.email}
                        onChange={() => toggleSetting('notifications', 'email')}
                        id="email-notifications"
                      />
                    </SettingControl>

                    <SettingControl
                      label="In-app notifications"
                      description="Show real-time notification toasts and badge counts"
                    >
                      <ToggleSwitch
                        checked={settings.notifications.inApp}
                        onChange={() => toggleSetting('notifications', 'inApp')}
                        id="in-app-notifications"
                      />
                    </SettingControl>

                    <SettingControl
                      label="Sound effects"
                      description="Play sound for incoming notifications"
                    >
                      <ToggleSwitch
                        checked={settings.notifications.sound}
                        onChange={() => toggleSetting('notifications', 'sound')}
                        id="sound-effects"
                      />
                    </SettingControl>
                  </div>

                  {/* Per-Alert-Type Preferences */}
                  <div className="border-t border-border pt-4">
                    <h4 className="font-semibold text-sm text-muted-foreground uppercase tracking-wide mb-3">Alert Type Preferences</h4>
                    <div className="space-y-3">
                      {[
                        { key: 'stockout', label: 'Stockout Alerts', desc: 'Low inventory and stockout risk warnings' },
                        { key: 'overstock', label: 'Overstock Alerts', desc: 'Excess inventory and E&O risk warnings' },
                        { key: 'lead_time', label: 'Lead Time Alerts', desc: 'Vendor lead time drift and delays' },
                        { key: 'recommendations', label: 'Recommendation Actions', desc: 'New AI recommendations requiring review' },
                        { key: 'escalations', label: 'Escalations', desc: 'Decisions escalated to your authority level' },
                        { key: 'order_exceptions', label: 'Order Exceptions', desc: 'Order tracking and fulfillment issues' },
                      ].map((alertType) => (
                        <div key={alertType.key} className="flex items-center justify-between py-2 px-3 bg-muted/30 rounded-lg">
                          <div>
                            <p className="text-sm font-medium">{alertType.label}</p>
                            <p className="text-xs text-muted-foreground">{alertType.desc}</p>
                          </div>
                          <ToggleSwitch
                            checked={settings.notifications.alertTypes?.[alertType.key] !== false}
                            onChange={() => {
                              const current = settings.notifications.alertTypes?.[alertType.key] !== false;
                              const newSettings = {
                                ...settings,
                                notifications: {
                                  ...settings.notifications,
                                  alertTypes: {
                                    ...settings.notifications.alertTypes,
                                    [alertType.key]: !current,
                                  },
                                },
                              };
                              saveSettings(newSettings);
                            }}
                            id={`alert-${alertType.key}`}
                          />
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Digest Frequency */}
                  <div className="border-t border-border pt-4">
                    <h4 className="font-semibold text-sm text-muted-foreground uppercase tracking-wide mb-3">Email Digest Frequency</h4>
                    <SettingControl
                      label="Email digest schedule"
                      description="How often to receive email summaries of notifications"
                    >
                      <Select
                        id="digest-frequency"
                        value={settings.notifications.digestFrequency || 'daily'}
                        onChange={(e) => {
                          const newSettings = {
                            ...settings,
                            notifications: { ...settings.notifications, digestFrequency: e.target.value },
                          };
                          saveSettings(newSettings);
                        }}
                        className="w-36"
                      >
                        <SelectOption value="realtime">Real-time</SelectOption>
                        <SelectOption value="hourly">Hourly</SelectOption>
                        <SelectOption value="daily">Daily</SelectOption>
                        <SelectOption value="weekly">Weekly</SelectOption>
                      </Select>
                    </SettingControl>
                  </div>

                  {/* Quiet Hours */}
                  <div className="border-t border-border pt-4">
                    <h4 className="font-semibold text-sm text-muted-foreground uppercase tracking-wide mb-3">Quiet Hours</h4>
                    <SettingControl
                      label="Enable quiet hours"
                      description="Suppress non-critical notifications during specified hours"
                    >
                      <ToggleSwitch
                        checked={settings.notifications.quietHours?.enabled || false}
                        onChange={() => {
                          const current = settings.notifications.quietHours?.enabled || false;
                          const newSettings = {
                            ...settings,
                            notifications: {
                              ...settings.notifications,
                              quietHours: {
                                ...settings.notifications.quietHours,
                                enabled: !current,
                                start: settings.notifications.quietHours?.start || '22:00',
                                end: settings.notifications.quietHours?.end || '07:00',
                              },
                            },
                          };
                          saveSettings(newSettings);
                        }}
                        id="quiet-hours"
                      />
                    </SettingControl>
                    {settings.notifications.quietHours?.enabled && (
                      <div className="flex items-center gap-3 ml-4 mt-2">
                        <Label htmlFor="quiet-start" className="text-sm">From</Label>
                        <Input
                          id="quiet-start"
                          type="time"
                          value={settings.notifications.quietHours?.start || '22:00'}
                          onChange={(e) => {
                            const newSettings = {
                              ...settings,
                              notifications: {
                                ...settings.notifications,
                                quietHours: { ...settings.notifications.quietHours, start: e.target.value },
                              },
                            };
                            saveSettings(newSettings);
                          }}
                          className="w-28"
                        />
                        <Label htmlFor="quiet-end" className="text-sm">To</Label>
                        <Input
                          id="quiet-end"
                          type="time"
                          value={settings.notifications.quietHours?.end || '07:00'}
                          onChange={(e) => {
                            const newSettings = {
                              ...settings,
                              notifications: {
                                ...settings.notifications,
                                quietHours: { ...settings.notifications.quietHours, end: e.target.value },
                              },
                            };
                            saveSettings(newSettings);
                          }}
                          className="w-28"
                        />
                        <span className="text-xs text-muted-foreground">Critical alerts still delivered</span>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </div>

        {/* Privacy Settings */}
        <div className="py-6">
          <div className="md:grid md:grid-cols-3 md:gap-6">
            <SectionHeader
              icon={ShieldCheck}
              title="Privacy"
              description="Control your privacy settings"
            />
            <div className="mt-5 md:mt-0 md:col-span-2">
              <Card variant="default" padding="none">
                <CardContent className="p-6 space-y-6">
                  <SettingControl
                    label="Show online status"
                    description="Allow others to see when you're online"
                  >
                    <ToggleSwitch
                      checked={settings.privacy.showOnlineStatus}
                      onChange={() => toggleSetting('privacy', 'showOnlineStatus')}
                      id="online-status"
                    />
                  </SettingControl>

                  <SettingControl
                    label="Allow friend requests"
                    description="Let other users send you friend requests"
                  >
                    <ToggleSwitch
                      checked={settings.privacy.allowFriendRequests}
                      onChange={() => toggleSetting('privacy', 'allowFriendRequests')}
                      id="friend-requests"
                    />
                  </SettingControl>

                  <SettingControl
                    label="Show in leaderboards"
                    description="Include your stats in public leaderboards"
                    className="border-t border-border"
                  >
                    <ToggleSwitch
                      checked={settings.privacy.showInLeaderboards}
                      onChange={() => toggleSetting('privacy', 'showInLeaderboards')}
                      id="leaderboards"
                    />
                  </SettingControl>
                </CardContent>
              </Card>
            </div>
          </div>
        </div>

        {/* Simulation Settings */}
        <div className="py-6">
          <div className="md:grid md:grid-cols-3 md:gap-6">
            <SectionHeader
              icon={Settings2}
              title="Simulation Settings"
              description="Customize your scenario experience"
            />
            <div className="mt-5 md:mt-0 md:col-span-2">
              <Card variant="default" padding="none">
                <CardContent className="p-6 space-y-6">
                  <SettingControl
                    label="Confirm before leaving scenario"
                    description="Show a confirmation dialog when leaving a scenario in progress"
                  >
                    <ToggleSwitch
                      checked={settings.simulation.confirmBeforeLeavingGame}
                      onChange={() => toggleSetting('game', 'confirmBeforeLeavingGame')}
                      id="confirm-leave"
                    />
                  </SettingControl>

                  <SettingControl
                    label="Show tutorial tips"
                    description="Display helpful tips and tutorials"
                  >
                    <ToggleSwitch
                      checked={settings.simulation.showTutorialTips}
                      onChange={() => toggleSetting('game', 'showTutorialTips')}
                      id="tutorial-tips"
                    />
                  </SettingControl>
                </CardContent>

                <div className="p-6 pt-0 text-right">
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => {
                      // Reset to default settings
                      const defaultSettings = {
                        theme: 'system',
                        notifications: {
                          email: true,
                          inApp: true,
                          sound: true,
                        },
                        privacy: {
                          showOnlineStatus: true,
                          allowFriendRequests: true,
                          showInLeaderboards: true,
                        },
                        simulation: {
                          animationSpeed: 'normal',
                          confirmBeforeLeavingGame: true,
                          showTutorialTips: true,
                        },
                      };
                      saveSettings(defaultSettings);
                    }}
                  >
                    Reset to Defaults
                  </Button>
                </div>
              </Card>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Settings;
