/**
 * Badge/Chip Component - Autonomy UI Kit Wrapper
 *
 * Small status indicators and labels.
 * Provides easy migration from MUI Chip components.
 */

import React from 'react';
import { cn } from '@azirella-ltd/autonomy-frontend';
import { X } from 'lucide-react';

const badgeVariants = {
  default: 'bg-primary text-primary-foreground',
  secondary: 'bg-secondary text-secondary-foreground',
  outline: 'border border-input bg-background text-foreground',
  destructive: 'bg-destructive text-destructive-foreground',
  success: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200',
  warning: 'bg-warning/20 text-warning-foreground',
  info: 'bg-info/20 text-info-foreground',
};

const badgeSizes = {
  sm: 'text-xs px-2 py-0.5',
  default: 'text-xs px-2.5 py-0.5',
  lg: 'text-sm px-3 py-1',
};

export const Badge = ({
  children,
  className,
  variant = 'default',
  size = 'default',
  icon,
  onDelete,
  ...props
}) => {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full font-medium transition-colors',
        badgeVariants[variant],
        badgeSizes[size],
        className
      )}
      {...props}
    >
      {icon && <span className="flex-shrink-0">{icon}</span>}
      {children}
      {onDelete && (
        <button
          onClick={onDelete}
          className="ml-1 rounded-full p-0.5 hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </span>
  );
};

// Alias for MUI Chip compatibility
export const Chip = Badge;

export default Badge;
