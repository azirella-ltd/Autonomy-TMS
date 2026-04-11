/**
 * ToggleGroup Component - Autonomy UI Kit Wrapper
 *
 * Radix UI ToggleGroup wrapper with styling.
 */

import React, { createContext, useContext } from 'react';
import * as ToggleGroupPrimitive from '@radix-ui/react-toggle-group';
import { cn } from '@azirella-ltd/autonomy-frontend';

const toggleVariants = {
  default: 'bg-transparent',
  outline: 'border border-input bg-transparent hover:bg-accent hover:text-accent-foreground',
};

const toggleSizes = {
  default: 'h-10 px-3',
  sm: 'h-9 px-2.5',
  lg: 'h-11 px-5',
};

const ToggleGroupContext = createContext({
  variant: 'default',
  size: 'default',
});

export const ToggleGroup = React.forwardRef(({
  className,
  variant = 'default',
  size = 'default',
  children,
  ...props
}, ref) => (
  <ToggleGroupPrimitive.Root
    ref={ref}
    className={cn('flex items-center justify-center gap-1', className)}
    {...props}
  >
    <ToggleGroupContext.Provider value={{ variant, size }}>
      {children}
    </ToggleGroupContext.Provider>
  </ToggleGroupPrimitive.Root>
));

ToggleGroup.displayName = 'ToggleGroup';

export const ToggleGroupItem = React.forwardRef(({
  className,
  children,
  variant,
  size,
  ...props
}, ref) => {
  const context = useContext(ToggleGroupContext);
  const itemVariant = variant || context.variant;
  const itemSize = size || context.size;

  return (
    <ToggleGroupPrimitive.Item
      ref={ref}
      className={cn(
        'inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors',
        'hover:bg-muted hover:text-muted-foreground',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
        'disabled:pointer-events-none disabled:opacity-50',
        'data-[state=on]:bg-accent data-[state=on]:text-accent-foreground',
        toggleVariants[itemVariant],
        toggleSizes[itemSize],
        className
      )}
      {...props}
    >
      {children}
    </ToggleGroupPrimitive.Item>
  );
});

ToggleGroupItem.displayName = 'ToggleGroupItem';

export default ToggleGroup;
