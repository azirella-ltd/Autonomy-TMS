/**
 * useToast Hook - Toast notifications
 */

import React, { useState, useCallback } from 'react';

interface Toast {
  id: string;
  title?: string;
  description?: string;
  variant?: 'default' | 'destructive';
  action?: React.ReactNode;
}

interface ToastState {
  toasts: Toast[];
}

let toastCount = 0;

export function useToast() {
  const [state, setState] = useState<ToastState>({ toasts: [] });

  const toast = useCallback(({ title, description, variant = 'default' }: Omit<Toast, 'id'>) => {
    const id = String(++toastCount);
    const newToast: Toast = { id, title, description, variant };

    setState((prev) => ({
      toasts: [...prev.toasts, newToast],
    }));

    // Auto-dismiss after 5 seconds
    setTimeout(() => {
      setState((prev) => ({
        toasts: prev.toasts.filter((t) => t.id !== id),
      }));
    }, 5000);

    return { id, dismiss: () => {
      setState((prev) => ({
        toasts: prev.toasts.filter((t) => t.id !== id),
      }));
    }};
  }, []);

  const dismiss = useCallback((toastId?: string) => {
    setState((prev) => ({
      toasts: toastId
        ? prev.toasts.filter((t) => t.id !== toastId)
        : [],
    }));
  }, []);

  return {
    toast,
    dismiss,
    toasts: state.toasts,
  };
}

// Standalone toast function for external use
export const toast = ({ title, description, variant = 'default' }: Omit<Toast, 'id'>) => {
  console.log('Toast:', { title, description, variant });
  // This is a simple implementation - in production would dispatch to a global state
  return { id: String(++toastCount), dismiss: () => {} };
};

export type { Toast };
