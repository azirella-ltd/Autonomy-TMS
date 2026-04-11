/**
 * Loading Component - Autonomy UI Kit Wrapper
 *
 * Loading spinners and skeleton loaders.
 * Provides easy migration from MUI CircularProgress.
 */

import React from 'react';
import { cn } from '@azirella-ltd/autonomy-frontend';
import { Loader2 } from 'lucide-react';

export const Spinner = ({
  className,
  size = 'default',
  ...props
}) => {
  const sizes = {
    sm: 'h-4 w-4',
    default: 'h-6 w-6',
    lg: 'h-8 w-8',
    xl: 'h-12 w-12',
  };

  return (
    <Loader2
      role="progressbar"
      aria-label="Loading"
      className={cn(
        'animate-spin text-primary',
        sizes[size],
        className
      )}
      {...props}
    />
  );
};

export const LoadingOverlay = ({
  children,
  loading,
  text = 'Loading...',
  className,
}) => {
  if (!loading) return children;

  return (
    <div className={cn('relative', className)}>
      {children}
      <div className="absolute inset-0 flex flex-col items-center justify-center bg-background/80 backdrop-blur-sm z-10">
        <Spinner size="lg" />
        {text && (
          <p className="mt-3 text-sm text-muted-foreground">{text}</p>
        )}
      </div>
    </div>
  );
};

export const FullPageLoader = ({
  text = 'Loading...',
}) => (
  <div className="min-h-screen flex flex-col items-center justify-center bg-background">
    <Spinner size="xl" />
    {text && (
      <p className="mt-4 text-muted-foreground">{text}</p>
    )}
  </div>
);

export const Skeleton = ({
  className,
  ...props
}) => (
  <div
    className={cn('animate-pulse rounded-md bg-muted', className)}
    {...props}
  />
);

// Alias for MUI compatibility
export const CircularProgress = Spinner;

export default Spinner;
