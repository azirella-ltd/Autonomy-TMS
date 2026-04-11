/**
 * Input Component - Autonomy UI Kit Wrapper
 *
 * Form input components with labels and error states.
 * Provides easy migration from MUI/Chakra Input components.
 */

import React from 'react';
import { cn } from '@azirella-ltd/autonomy-frontend';

export const Input = React.forwardRef(({
  className,
  type = 'text',
  error,
  ...props
}, ref) => {
  return (
    <input
      type={type}
      ref={ref}
      className={cn(
        'flex h-10 w-full rounded-md border bg-background px-3 py-2 text-sm',
        'ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium',
        'placeholder:text-muted-foreground',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
        'disabled:cursor-not-allowed disabled:opacity-50',
        error ? 'border-destructive focus-visible:ring-destructive' : 'border-input',
        className
      )}
      {...props}
    />
  );
});

Input.displayName = 'Input';

export const Label = React.forwardRef(({
  children,
  className,
  required,
  ...props
}, ref) => (
  <label
    ref={ref}
    className={cn(
      'text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 bg-background px-1',
      className
    )}
    {...props}
  >
    {children}
    {required && <span className="text-destructive ml-1">*</span>}
  </label>
));

Label.displayName = 'Label';

export const FormField = ({
  children,
  label,
  error,
  helperText,
  required,
  className,
  ...props
}) => (
  <div className={cn('space-y-2', className)} {...props}>
    {label && (
      <Label required={required}>{label}</Label>
    )}
    {children}
    {(error || helperText) && (
      <p className={cn(
        'text-xs',
        error ? 'text-destructive' : 'text-muted-foreground'
      )}>
        {error || helperText}
      </p>
    )}
  </div>
);

export const Textarea = React.forwardRef(({
  className,
  error,
  ...props
}, ref) => {
  return (
    <textarea
      ref={ref}
      className={cn(
        'flex min-h-[80px] w-full rounded-md border bg-background px-3 py-2 text-sm',
        'ring-offset-background placeholder:text-muted-foreground',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
        'disabled:cursor-not-allowed disabled:opacity-50',
        error ? 'border-destructive focus-visible:ring-destructive' : 'border-input',
        className
      )}
      {...props}
    />
  );
});

Textarea.displayName = 'Textarea';

export default Input;
