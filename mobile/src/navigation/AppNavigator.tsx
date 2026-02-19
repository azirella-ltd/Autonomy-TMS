/**
 * App Navigator
 * Phase 7 Sprint 1: Mobile Application
 *
 * Main navigation structure for the app
 */

import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createStackNavigator } from '@react-navigation/stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import Icon from 'react-native-vector-icons/MaterialCommunityIcons';
import { useSelector } from 'react-redux';

// Auth Screens
import LoginScreen from '../screens/Auth/LoginScreen';
import RegisterScreen from '../screens/Auth/RegisterScreen';

// Main Screens
import DashboardScreen from '../screens/Dashboard/DashboardScreen';
import GamesListScreen from '../screens/Games/GamesListScreen';
import GameDetailScreen from '../screens/Games/GameDetailScreen';
import CreateGameScreen from '../screens/Games/CreateGameScreen';
import TemplateLibraryScreen from '../screens/Templates/TemplateLibraryScreen';
import AnalyticsScreen from '../screens/Analytics/AnalyticsScreen';
import ProfileScreen from '../screens/Profile/ProfileScreen';

// Navigation Types
export type RootStackParamList = {
  Auth: undefined;
  Main: undefined;
};

export type AuthStackParamList = {
  Login: undefined;
  Register: undefined;
};

export type MainTabParamList = {
  Dashboard: undefined;
  Games: undefined;
  Templates: undefined;
  Analytics: undefined;
  Profile: undefined;
};

export type GamesStackParamList = {
  GamesList: undefined;
  GameDetail: { gameId: number };
  CreateGame: undefined;
};

const RootStack = createStackNavigator<RootStackParamList>();
const AuthStack = createStackNavigator<AuthStackParamList>();
const MainTab = createBottomTabNavigator<MainTabParamList>();
const GamesStack = createStackNavigator<GamesStackParamList>();

// Auth Navigator
function AuthNavigator() {
  return (
    <AuthStack.Navigator
      screenOptions={{
        headerShown: false,
      }}
    >
      <AuthStack.Screen name="Login" component={LoginScreen} />
      <AuthStack.Screen name="Register" component={RegisterScreen} />
    </AuthStack.Navigator>
  );
}

// Games Stack Navigator
function GamesNavigator() {
  return (
    <GamesStack.Navigator
      screenOptions={{
        headerStyle: {
          backgroundColor: '#1976d2',
        },
        headerTintColor: '#fff',
      }}
    >
      <GamesStack.Screen
        name="GamesList"
        component={GamesListScreen}
        options={{ title: 'My Games' }}
      />
      <GamesStack.Screen
        name="GameDetail"
        component={GameDetailScreen}
        options={{ title: 'Game Details' }}
      />
      <GamesStack.Screen
        name="CreateGame"
        component={CreateGameScreen}
        options={{ title: 'Create Game' }}
      />
    </GamesStack.Navigator>
  );
}

// Main Tab Navigator
function MainNavigator() {
  return (
    <MainTab.Navigator
      screenOptions={({ route }) => ({
        tabBarIcon: ({ focused, color, size }) => {
          let iconName: string;

          switch (route.name) {
            case 'Dashboard':
              iconName = focused ? 'view-dashboard' : 'view-dashboard-outline';
              break;
            case 'Games':
              iconName = focused ? 'gamepad-variant' : 'gamepad-variant-outline';
              break;
            case 'Templates':
              iconName = focused ? 'file-multiple' : 'file-multiple-outline';
              break;
            case 'Analytics':
              iconName = focused ? 'chart-line' : 'chart-line-variant';
              break;
            case 'Profile':
              iconName = focused ? 'account' : 'account-outline';
              break;
            default:
              iconName = 'help-circle-outline';
          }

          return <Icon name={iconName} size={size} color={color} />;
        },
        tabBarActiveTintColor: '#1976d2',
        tabBarInactiveTintColor: 'gray',
        headerStyle: {
          backgroundColor: '#1976d2',
        },
        headerTintColor: '#fff',
      })}
    >
      <MainTab.Screen
        name="Dashboard"
        component={DashboardScreen}
        options={{ title: 'Dashboard' }}
      />
      <MainTab.Screen
        name="Games"
        component={GamesNavigator}
        options={{ headerShown: false }}
      />
      <MainTab.Screen
        name="Templates"
        component={TemplateLibraryScreen}
        options={{ title: 'Templates' }}
      />
      <MainTab.Screen
        name="Analytics"
        component={AnalyticsScreen}
        options={{ title: 'Analytics' }}
      />
      <MainTab.Screen
        name="Profile"
        component={ProfileScreen}
        options={{ title: 'Profile' }}
      />
    </MainTab.Navigator>
  );
}

// Root Navigator
export default function AppNavigator() {
  const isAuthenticated = useSelector((state: any) => !!state.auth.token);

  return (
    <NavigationContainer>
      <RootStack.Navigator screenOptions={{ headerShown: false }}>
        {isAuthenticated ? (
          <RootStack.Screen name="Main" component={MainNavigator} />
        ) : (
          <RootStack.Screen name="Auth" component={AuthNavigator} />
        )}
      </RootStack.Navigator>
    </NavigationContainer>
  );
}
