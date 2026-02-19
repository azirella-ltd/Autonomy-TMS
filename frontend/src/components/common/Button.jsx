/**
 * Button Component - Autonomy UI Kit Wrapper
 *
 * A simplified button component using Tailwind CSS.
 * Provides easy migration from MUI/Chakra Button components.
 */

import React from 'react';
import { cn } from '../../lib/utils/cn';
import { Loader2 } from 'lucide-react';

const buttonVariants = {
  default: 'bg-primary text-primary-foreground hover:bg-primary-hover shadow-sm',
  destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/90 shadow-sm',
  outline: 'border border-input bg-background hover:bg-accent hover:text-accent-foreground',
  secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
  ghost: 'hover:bg-accent hover:text-accent-foreground',
  link: 'text-primary underline-offset-4 hover:underline',
};

const buttonSizes = {
  default: 'h-10 px-4 py-2',
  sm: 'h-9 px-3 text-sm',
  lg: 'h-11 px-8 text-base',
  icon: 'h-10 w-10',
};

export const Button = React.forwardRef(({
  children,
  className,
  variant = 'default',
  size = 'default',
  loading = false,
  disabled = false,
  leftIcon,
  rightIcon,
  fullWidth = false,
  as: Component = 'button',
  ...props
}, ref) => {
  const isDisabled = disabled || loading;

  return (
    <Component
      ref={ref}
      className={cn(
        'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
        'disabled:pointer-events-none disabled:opacity-50',
        buttonVariants[variant],
        buttonSizes[size],
        fullWidth && 'w-full',
        className
      )}
      disabled={isDisabled}
      {...props}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {!loading && leftIcon && <span className="mr-1">{leftIcon}</span>}
      {children}
      {!loading && rightIcon && <span className="ml-1">{rightIcon}</span>}
    </Component>
  );
});

Button.displayName = 'Button';

export const IconButton = React.forwardRef(({
  children,
  className,
  variant = 'ghost',
  size = 'icon',
  ...props
}, ref) => (
  <Button
    ref={ref}
    variant={variant}
    size={size}
    className={cn('p-0', className)}
    {...props}
  >
    {children}
  </Button>
));

IconButton.displayName = 'IconButton';

export default Button;
