/**
 * Toast Component
 * Phase 7 Sprint 1: Mobile Application
 */

import React, { useEffect } from 'react';
import { StyleSheet } from 'react-native';
import { Snackbar } from 'react-native-paper';
import { useAppDispatch, useAppSelector } from '../../store';
import { hideToast } from '../../store/slices/uiSlice';
import { theme } from '../../theme';

export default function Toast() {
  const dispatch = useAppDispatch();
  const { toasts } = useAppSelector((state) => state.ui);

  const currentToast = toasts[0]; // Show first toast in queue

  useEffect(() => {
    if (currentToast) {
      const timer = setTimeout(() => {
        dispatch(hideToast(currentToast.id));
      }, currentToast.duration || 3000);

      return () => clearTimeout(timer);
    }
  }, [currentToast, dispatch]);

  if (!currentToast) return null;

  const getBackgroundColor = (type: string) => {
    switch (type) {
      case 'success':
        return theme.colors.success;
      case 'error':
        return theme.colors.error;
      case 'warning':
        return theme.colors.warning;
      case 'info':
        return theme.colors.info;
      default:
        return theme.colors.surface;
    }
  };

  return (
    <Snackbar
      visible={!!currentToast}
      onDismiss={() => dispatch(hideToast(currentToast.id))}
      duration={currentToast.duration || 3000}
      action={{
        label: 'Dismiss',
        onPress: () => dispatch(hideToast(currentToast.id)),
      }}
      style={[
        styles.snackbar,
        { backgroundColor: getBackgroundColor(currentToast.type) },
      ]}
    >
      {currentToast.message}
    </Snackbar>
  );
}

const styles = StyleSheet.create({
  snackbar: {
    marginBottom: theme.spacing.md,
  },
});
