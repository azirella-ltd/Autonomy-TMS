/**
 * Typography Component - Autonomy UI Kit Wrapper
 *
 * Text styling components.
 * Provides easy migration from MUI Typography.
 */

import React from 'react';
import { cn } from '../../lib/utils/cn';

const typographyVariants = {
  h1: 'text-4xl font-bold tracking-tight',
  h2: 'text-3xl font-bold tracking-tight',
  h3: 'text-2xl font-semibold',
  h4: 'text-xl font-semibold',
  h5: 'text-lg font-semibold',
  h6: 'text-base font-semibold',
  subtitle1: 'text-lg font-medium',
  subtitle2: 'text-base font-medium',
  body1: 'text-base',
  body2: 'text-sm',
  caption: 'text-xs text-muted-foreground',
  overline: 'text-xs uppercase tracking-wider text-muted-foreground',
};

const typographyElements = {
  h1: 'h1',
  h2: 'h2',
  h3: 'h3',
  h4: 'h4',
  h5: 'h5',
  h6: 'h6',
  subtitle1: 'p',
  subtitle2: 'p',
  body1: 'p',
  body2: 'p',
  caption: 'span',
  overline: 'span',
};

export const Typography = ({
  children,
  variant = 'body1',
  component,
  color,
  className,
  gutterBottom,
  noWrap,
  align,
  ...props
}) => {
  const Component = component || typographyElements[variant] || 'p';

  const colorClasses = {
    primary: 'text-primary',
    secondary: 'text-secondary-foreground',
    error: 'text-destructive',
    warning: 'text-warning',
    info: 'text-info',
    success: 'text-emerald-600 dark:text-emerald-400',
    textPrimary: 'text-foreground',
    textSecondary: 'text-muted-foreground',
  };

  const alignClasses = {
    left: 'text-left',
    center: 'text-center',
    right: 'text-right',
    justify: 'text-justify',
  };

  return (
    <Component
      className={cn(
        typographyVariants[variant],
        color && colorClasses[color],
        align && alignClasses[align],
        gutterBottom && 'mb-4',
        noWrap && 'truncate',
        className
      )}
      {...props}
    >
      {children}
    </Component>
  );
};

// Convenience components
export const H1 = (props) => <Typography variant="h1" component="h1" {...props} />;
export const H2 = (props) => <Typography variant="h2" component="h2" {...props} />;
export const H3 = (props) => <Typography variant="h3" component="h3" {...props} />;
export const H4 = (props) => <Typography variant="h4" component="h4" {...props} />;
export const H5 = (props) => <Typography variant="h5" component="h5" {...props} />;
export const H6 = (props) => <Typography variant="h6" component="h6" {...props} />;
export const Text = (props) => <Typography variant="body1" {...props} />;
export const SmallText = (props) => <Typography variant="body2" {...props} />;
export const Caption = (props) => <Typography variant="caption" {...props} />;

export default Typography;
