/**
 * Toast Component - Autonomy UI Kit
 *
 * Simple toast notifications using Radix Toast primitive.
 * Provides easy migration from Chakra UI useToast.
 */

import React, { createContext, useContext, useState, useCallback } from 'react';
import { cn } from '@azirella-ltd/autonomy-frontend';
import { X, CheckCircle2, AlertCircle, AlertTriangle, Info } from 'lucide-react';

const ToastContext = createContext(null);

export const ToastProvider = ({ children }) => {
  const [toasts, setToasts] = useState([]);

  const addToast = useCallback(({
    title,
    description,
    status = 'info',
    duration = 5000,
    isClosable = true,
  }) => {
    const id = Date.now() + Math.random();

    setToasts((prev) => [...prev, { id, title, description, status, isClosable }]);

    if (duration) {
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, duration);
    }

    return id;
  }, []);

  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback((options) => addToast(options), [addToast]);

  return (
    <ToastContext.Provider value={{ toast, removeToast }}>
      {children}
      <ToastContainer toasts={toasts} onClose={removeToast} />
    </ToastContext.Provider>
  );
};

export const useToast = () => {
  const context = useContext(ToastContext);
  if (!context) {
    // Return a no-op function if used outside provider
    return () => {};
  }
  return context.toast;
};

const ToastContainer = ({ toasts, onClose }) => {
  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
      {toasts.map((toast) => (
        <Toast key={toast.id} {...toast} onClose={() => onClose(toast.id)} />
      ))}
    </div>
  );
};

const Toast = ({
  title,
  description,
  status = 'info',
  isClosable,
  onClose,
}) => {
  const statusConfig = {
    info: {
      icon: Info,
      className: 'border-blue-200 bg-blue-50 text-blue-900 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-100',
      iconClassName: 'text-blue-500',
    },
    success: {
      icon: CheckCircle2,
      className: 'border-green-200 bg-green-50 text-green-900 dark:border-green-800 dark:bg-green-950 dark:text-green-100',
      iconClassName: 'text-green-500',
    },
    warning: {
      icon: AlertTriangle,
      className: 'border-yellow-200 bg-yellow-50 text-yellow-900 dark:border-yellow-800 dark:bg-yellow-950 dark:text-yellow-100',
      iconClassName: 'text-yellow-500',
    },
    error: {
      icon: AlertCircle,
      className: 'border-red-200 bg-red-50 text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-100',
      iconClassName: 'text-red-500',
    },
  };

  const config = statusConfig[status] || statusConfig.info;
  const Icon = config.icon;

  return (
    <div
      className={cn(
        'flex items-start gap-3 rounded-lg border p-4 shadow-lg',
        'animate-in slide-in-from-right-full',
        config.className
      )}
    >
      <Icon className={cn('h-5 w-5 flex-shrink-0 mt-0.5', config.iconClassName)} />
      <div className="flex-1 min-w-0">
        {title && <p className="font-semibold">{title}</p>}
        {description && <p className="text-sm opacity-90">{description}</p>}
      </div>
      {isClosable && (
        <button
          onClick={onClose}
          className="flex-shrink-0 opacity-70 hover:opacity-100 transition-opacity"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
};

export default Toast;
