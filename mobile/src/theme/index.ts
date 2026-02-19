/**
 * Theme Configuration
 * Phase 7 Sprint 1: Mobile Application
 */

import { MD3LightTheme as DefaultTheme } from 'react-native-paper';

export const theme = {
  ...DefaultTheme,
  colors: {
    ...DefaultTheme.colors,
    primary: '#1976d2',
    secondary: '#424242',
    tertiary: '#f50057',
    background: '#f5f5f5',
    surface: '#ffffff',
    error: '#d32f2f',
    success: '#388e3c',
    warning: '#f57c00',
    info: '#0288d1',
    text: '#212121',
    textSecondary: '#757575',
    disabled: '#bdbdbd',
    placeholder: '#9e9e9e',
    backdrop: 'rgba(0, 0, 0, 0.5)',
  },
  roundness: 8,
  spacing: {
    xs: 4,
    sm: 8,
    md: 16,
    lg: 24,
    xl: 32,
  },
  typography: {
    h1: {
      fontSize: 32,
      fontWeight: 'bold' as const,
      lineHeight: 40,
    },
    h2: {
      fontSize: 28,
      fontWeight: 'bold' as const,
      lineHeight: 36,
    },
    h3: {
      fontSize: 24,
      fontWeight: '600' as const,
      lineHeight: 32,
    },
    h4: {
      fontSize: 20,
      fontWeight: '600' as const,
      lineHeight: 28,
    },
    body1: {
      fontSize: 16,
      fontWeight: 'normal' as const,
      lineHeight: 24,
    },
    body2: {
      fontSize: 14,
      fontWeight: 'normal' as const,
      lineHeight: 20,
    },
    caption: {
      fontSize: 12,
      fontWeight: 'normal' as const,
      lineHeight: 16,
    },
  },
};

export const darkTheme = {
  ...theme,
  colors: {
    ...theme.colors,
    background: '#121212',
    surface: '#1e1e1e',
    text: '#ffffff',
    textSecondary: '#b0b0b0',
  },
};

export type Theme = typeof theme;
