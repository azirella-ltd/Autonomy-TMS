/**
 * Error Boundary Component
 * Phase 7 Sprint 1: Mobile Application
 */

import React, { Component, ReactNode } from 'react';
import { View, StyleSheet } from 'react-native';
import { Card, Text, Button, Avatar } from 'react-native-paper';
import { theme } from '../../theme';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
    };
  }

  static getDerivedStateFromError(error: Error): State {
    return {
      hasError: true,
      error,
    };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
    // TODO: Log to error reporting service (Sentry, etc.)
  }

  handleReset = () => {
    this.setState({
      hasError: false,
      error: null,
    });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <View style={styles.container}>
          <Card style={styles.card}>
            <Card.Content style={styles.content}>
              <Avatar.Icon
                size={80}
                icon="alert-circle"
                style={styles.icon}
              />
              <Text style={styles.title}>Oops! Something went wrong</Text>
              <Text style={styles.message}>
                We're sorry for the inconvenience. Please try again.
              </Text>
              {this.state.error && __DEV__ && (
                <View style={styles.errorDetails}>
                  <Text style={styles.errorTitle}>Error Details:</Text>
                  <Text style={styles.errorText}>{this.state.error.message}</Text>
                </View>
              )}
              <Button
                mode="contained"
                onPress={this.handleReset}
                style={styles.button}
              >
                Try Again
              </Button>
            </Card.Content>
          </Card>
        </View>
      );
    }

    return this.props.children;
  }
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: theme.spacing.lg,
    backgroundColor: theme.colors.background,
  },
  card: {
    width: '100%',
    maxWidth: 400,
  },
  content: {
    alignItems: 'center',
    padding: theme.spacing.xl,
  },
  icon: {
    backgroundColor: theme.colors.error,
    marginBottom: theme.spacing.lg,
  },
  title: {
    fontSize: 20,
    fontWeight: 'bold',
    color: theme.colors.text,
    marginBottom: theme.spacing.sm,
    textAlign: 'center',
  },
  message: {
    fontSize: 14,
    color: theme.colors.textSecondary,
    marginBottom: theme.spacing.lg,
    textAlign: 'center',
  },
  errorDetails: {
    width: '100%',
    padding: theme.spacing.md,
    backgroundColor: theme.colors.error + '20',
    borderRadius: theme.roundness,
    marginBottom: theme.spacing.lg,
  },
  errorTitle: {
    fontSize: 12,
    fontWeight: '600',
    color: theme.colors.error,
    marginBottom: theme.spacing.xs,
  },
  errorText: {
    fontSize: 12,
    color: theme.colors.error,
    fontFamily: 'monospace',
  },
  button: {
    marginTop: theme.spacing.md,
    minWidth: 150,
  },
});
