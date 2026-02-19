/**
 * Card Component - Autonomy UI Kit Wrapper
 *
 * A simplified card component that wraps shadcn's Card with common patterns.
 * Provides easy migration from MUI Card/Paper components.
 */

import React from 'react';
import { cn } from '../../lib/utils/cn';

export const Card = ({
  children,
  className,
  variant = 'default',
  padding = 'default',
  ...props
}) => {
  const variants = {
    default: 'bg-card border border-border',
    elevated: 'bg-card shadow-lg',
    outlined: 'bg-transparent border border-border',
    ghost: 'bg-transparent',
  };

  const paddings = {
    none: '',
    sm: 'p-4',
    default: 'p-6',
    lg: 'p-8',
  };

  return (
    <div
      className={cn(
        'rounded-lg',
        variants[variant],
        paddings[padding],
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
};

export const CardHeader = ({ children, className, ...props }) => (
  <div
    className={cn('flex flex-col space-y-1.5 pb-4', className)}
    {...props}
  >
    {children}
  </div>
);

export const CardTitle = ({ children, className, as: Component = 'h3', ...props }) => (
  <Component
    className={cn('text-xl font-semibold leading-none tracking-tight text-card-foreground', className)}
    {...props}
  >
    {children}
  </Component>
);

export const CardDescription = ({ children, className, ...props }) => (
  <p
    className={cn('text-sm text-muted-foreground', className)}
    {...props}
  >
    {children}
  </p>
);

export const CardContent = ({ children, className, ...props }) => (
  <div className={cn('', className)} {...props}>
    {children}
  </div>
);

export const CardFooter = ({ children, className, ...props }) => (
  <div
    className={cn('flex items-center pt-4', className)}
    {...props}
  >
    {children}
  </div>
);

export default Card;
