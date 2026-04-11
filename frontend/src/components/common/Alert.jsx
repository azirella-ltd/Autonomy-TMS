/**
 * Alert Component - Autonomy UI Kit Wrapper
 *
 * Displays important messages with different severity levels.
 * Provides easy migration from MUI/Chakra Alert components.
 */

import React from 'react';
import { cn } from '@azirella-ltd/autonomy-frontend';
import {
  AlertCircle,
  CheckCircle2,
  Info,
  AlertTriangle,
  X,
} from 'lucide-react';

const alertVariants = {
  default: 'bg-background border-border text-foreground',
  info: 'bg-info/10 border-info/30 text-info-foreground',
  success: 'bg-emerald-50 border-emerald-200 text-emerald-800 dark:bg-emerald-950 dark:border-emerald-800 dark:text-emerald-200',
  warning: 'bg-warning/10 border-warning/30 text-warning-foreground',
  error: 'bg-destructive/10 border-destructive/30 text-destructive',
  destructive: 'bg-destructive/10 border-destructive/30 text-destructive',
};

const alertIcons = {
  default: Info,
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  error: AlertCircle,
  destructive: AlertCircle,
};

export const Alert = ({
  children,
  className,
  variant = 'default',
  title,
  icon,
  onClose,
  ...props
}) => {
  const Icon = icon || alertIcons[variant];

  return (
    <div
      role="alert"
      className={cn(
        'relative flex gap-3 rounded-lg border p-4',
        alertVariants[variant],
        className
      )}
      {...props}
    >
      {Icon && (
        <Icon className="h-5 w-5 flex-shrink-0 mt-0.5" />
      )}
      <div className="flex-1">
        {title && (
          <h5 className="font-medium mb-1">{title}</h5>
        )}
        <div className="text-sm">{children}</div>
      </div>
      {onClose && (
        <button
          onClick={onClose}
          className="absolute top-3 right-3 p-1 rounded-md hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
};

export const AlertTitle = ({ children, className, ...props }) => (
  <h5
    className={cn('font-medium leading-none tracking-tight mb-1', className)}
    {...props}
  >
    {children}
  </h5>
);

export const AlertDescription = ({ children, className, ...props }) => (
  <div
    className={cn('text-sm [&_p]:leading-relaxed', className)}
    {...props}
  >
    {children}
  </div>
);

export default Alert;
