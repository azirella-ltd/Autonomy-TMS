/**
 * Profile Screen
 * Phase 7 Sprint 1: Mobile Application
 */

import React, { useState } from 'react';
import {
  View,
  StyleSheet,
  ScrollView,
  Alert,
} from 'react-native';
import {
  Card,
  Text,
  Avatar,
  List,
  Switch,
  Button,
  Divider,
  Dialog,
  Portal,
} from 'react-native-paper';
import { useAppDispatch, useAppSelector } from '../../store';
import { logout } from '../../store/slices/authSlice';
import { toggleTheme } from '../../store/slices/uiSlice';
import { theme } from '../../theme';

export default function ProfileScreen({ navigation }: any) {
  const [logoutDialogVisible, setLogoutDialogVisible] = useState(false);
  const [notificationsEnabled, setNotificationsEnabled] = useState(true);
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);

  const dispatch = useAppDispatch();
  const { user } = useAppSelector((state) => state.auth);
  const { theme: currentTheme } = useAppSelector((state) => state.ui);

  const isDarkMode = currentTheme === 'dark';

  const handleLogout = () => {
    setLogoutDialogVisible(true);
  };

  const confirmLogout = () => {
    setLogoutDialogVisible(false);
    dispatch(logout());
  };

  const handleThemeToggle = () => {
    dispatch(toggleTheme());
  };

  const handleNotificationsToggle = () => {
    setNotificationsEnabled(!notificationsEnabled);
    // TODO: Update backend preference
  };

  const handleAutoRefreshToggle = () => {
    setAutoRefreshEnabled(!autoRefreshEnabled);
    // TODO: Update backend preference
  };

  const getInitials = (firstName?: string, lastName?: string) => {
    if (!firstName && !lastName) return 'U';
    return `${firstName?.charAt(0) || ''}${lastName?.charAt(0) || ''}`.toUpperCase();
  };

  return (
    <View style={styles.container}>
      <ScrollView contentContainerStyle={styles.scrollContent}>
        {/* User Profile Card */}
        <Card style={styles.profileCard}>
          <Card.Content style={styles.profileContent}>
            <Avatar.Text
              size={80}
              label={getInitials(user?.first_name, user?.last_name)}
              style={styles.avatar}
            />
            <View style={styles.userInfo}>
              <Text style={styles.userName}>
                {user?.first_name} {user?.last_name}
              </Text>
              <Text style={styles.userEmail}>{user?.email}</Text>
              {user?.role && (
                <Text style={styles.userRole}>{user.role}</Text>
              )}
            </View>
          </Card.Content>
        </Card>

        {/* Account Section */}
        <Card style={styles.sectionCard}>
          <Card.Title title="Account" titleStyle={styles.sectionTitle} />
          <Card.Content>
            <List.Item
              title="Edit Profile"
              description="Update your personal information"
              left={(props) => <List.Icon {...props} icon="account-edit" />}
              right={(props) => <List.Icon {...props} icon="chevron-right" />}
              onPress={() => {
                // TODO: Navigate to edit profile screen
                Alert.alert('Coming Soon', 'Profile editing will be available soon');
              }}
            />
            <Divider />
            <List.Item
              title="Change Password"
              description="Update your password"
              left={(props) => <List.Icon {...props} icon="lock" />}
              right={(props) => <List.Icon {...props} icon="chevron-right" />}
              onPress={() => {
                // TODO: Navigate to change password screen
                Alert.alert('Coming Soon', 'Password change will be available soon');
              }}
            />
          </Card.Content>
        </Card>

        {/* Preferences Section */}
        <Card style={styles.sectionCard}>
          <Card.Title title="Preferences" titleStyle={styles.sectionTitle} />
          <Card.Content>
            <List.Item
              title="Dark Mode"
              description="Use dark theme"
              left={(props) => <List.Icon {...props} icon="theme-light-dark" />}
              right={() => (
                <Switch
                  value={isDarkMode}
                  onValueChange={handleThemeToggle}
                  color={theme.colors.primary}
                />
              )}
            />
            <Divider />
            <List.Item
              title="Push Notifications"
              description="Receive game updates"
              left={(props) => <List.Icon {...props} icon="bell" />}
              right={() => (
                <Switch
                  value={notificationsEnabled}
                  onValueChange={handleNotificationsToggle}
                  color={theme.colors.primary}
                />
              )}
            />
            <Divider />
            <List.Item
              title="Auto-refresh"
              description="Automatically refresh game data"
              left={(props) => <List.Icon {...props} icon="refresh-auto" />}
              right={() => (
                <Switch
                  value={autoRefreshEnabled}
                  onValueChange={handleAutoRefreshToggle}
                  color={theme.colors.primary}
                />
              )}
            />
          </Card.Content>
        </Card>

        {/* Game Statistics Section */}
        <Card style={styles.sectionCard}>
          <Card.Title title="Game Statistics" titleStyle={styles.sectionTitle} />
          <Card.Content>
            <View style={styles.statsGrid}>
              <View style={styles.statItem}>
                <Text style={styles.statValue}>0</Text>
                <Text style={styles.statLabel}>Games Played</Text>
              </View>
              <View style={styles.statItem}>
                <Text style={styles.statValue}>0</Text>
                <Text style={styles.statLabel}>Games Won</Text>
              </View>
              <View style={styles.statItem}>
                <Text style={styles.statValue}>0</Text>
                <Text style={styles.statLabel}>Hours Played</Text>
              </View>
              <View style={styles.statItem}>
                <Text style={styles.statValue}>0</Text>
                <Text style={styles.statLabel}>Avg Score</Text>
              </View>
            </View>
          </Card.Content>
        </Card>

        {/* About Section */}
        <Card style={styles.sectionCard}>
          <Card.Title title="About" titleStyle={styles.sectionTitle} />
          <Card.Content>
            <List.Item
              title="Help & Support"
              description="Get help with the app"
              left={(props) => <List.Icon {...props} icon="help-circle" />}
              right={(props) => <List.Icon {...props} icon="chevron-right" />}
              onPress={() => {
                Alert.alert('Help & Support', 'Visit our help center at help.beergame.com');
              }}
            />
            <Divider />
            <List.Item
              title="Privacy Policy"
              description="Read our privacy policy"
              left={(props) => <List.Icon {...props} icon="shield-account" />}
              right={(props) => <List.Icon {...props} icon="chevron-right" />}
              onPress={() => {
                Alert.alert('Privacy Policy', 'View at beergame.com/privacy');
              }}
            />
            <Divider />
            <List.Item
              title="Terms of Service"
              description="Read our terms"
              left={(props) => <List.Icon {...props} icon="file-document" />}
              right={(props) => <List.Icon {...props} icon="chevron-right" />}
              onPress={() => {
                Alert.alert('Terms of Service', 'View at beergame.com/terms');
              }}
            />
            <Divider />
            <List.Item
              title="App Version"
              description="1.0.0"
              left={(props) => <List.Icon {...props} icon="information" />}
            />
          </Card.Content>
        </Card>

        {/* Logout Button */}
        <Button
          mode="contained"
          icon="logout"
          onPress={handleLogout}
          style={styles.logoutButton}
          buttonColor={theme.colors.error}
        >
          Logout
        </Button>

        {/* Footer */}
        <Text style={styles.footer}>
          The Beer Game {'\n'}
          Supply Chain Simulation Platform {'\n'}
          © 2026 Autonomy AI
        </Text>
      </ScrollView>

      {/* Logout Confirmation Dialog */}
      <Portal>
        <Dialog
          visible={logoutDialogVisible}
          onDismiss={() => setLogoutDialogVisible(false)}
        >
          <Dialog.Title>Confirm Logout</Dialog.Title>
          <Dialog.Content>
            <Text>Are you sure you want to logout?</Text>
          </Dialog.Content>
          <Dialog.Actions>
            <Button onPress={() => setLogoutDialogVisible(false)}>Cancel</Button>
            <Button onPress={confirmLogout} textColor={theme.colors.error}>
              Logout
            </Button>
          </Dialog.Actions>
        </Dialog>
      </Portal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  scrollContent: {
    padding: theme.spacing.md,
    paddingBottom: theme.spacing.xl * 2,
  },
  profileCard: {
    marginBottom: theme.spacing.md,
  },
  profileContent: {
    alignItems: 'center',
    paddingVertical: theme.spacing.lg,
  },
  avatar: {
    backgroundColor: theme.colors.primary,
    marginBottom: theme.spacing.md,
  },
  userInfo: {
    alignItems: 'center',
  },
  userName: {
    fontSize: 24,
    fontWeight: 'bold',
    color: theme.colors.text,
    marginBottom: theme.spacing.xs,
  },
  userEmail: {
    fontSize: 16,
    color: theme.colors.textSecondary,
    marginBottom: theme.spacing.xs,
  },
  userRole: {
    fontSize: 14,
    color: theme.colors.primary,
    fontWeight: '600',
  },
  sectionCard: {
    marginBottom: theme.spacing.md,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
  },
  statsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginTop: theme.spacing.sm,
  },
  statItem: {
    flex: 1,
    minWidth: '50%',
    alignItems: 'center',
    marginBottom: theme.spacing.md,
  },
  statValue: {
    fontSize: 32,
    fontWeight: 'bold',
    color: theme.colors.primary,
    marginBottom: theme.spacing.xs,
  },
  statLabel: {
    fontSize: 12,
    color: theme.colors.textSecondary,
    textAlign: 'center',
  },
  logoutButton: {
    marginVertical: theme.spacing.lg,
  },
  footer: {
    textAlign: 'center',
    fontSize: 12,
    color: theme.colors.textSecondary,
    marginTop: theme.spacing.lg,
    lineHeight: 20,
  },
});
