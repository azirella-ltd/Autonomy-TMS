/**
 * Tabs Component - Autonomy UI Kit Wrapper
 *
 * Radix UI Tabs wrapper with styling.
 */

import React from 'react';
import * as TabsPrimitive from '@radix-ui/react-tabs';
import { cn } from '@azirella-ltd/autonomy-frontend';

export const Tabs = React.forwardRef(({
  className,
  ...props
}, ref) => (
  <TabsPrimitive.Root
    ref={ref}
    className={cn('w-full', className)}
    {...props}
  />
));

Tabs.displayName = 'Tabs';

export const TabsList = React.forwardRef(({
  className,
  ...props
}, ref) => (
  <TabsPrimitive.List
    ref={ref}
    className={cn(
      'inline-flex h-10 items-center justify-center rounded-md bg-muted p-1 text-muted-foreground',
      className
    )}
    {...props}
  />
));

TabsList.displayName = 'TabsList';

export const TabsTrigger = React.forwardRef(({
  className,
  ...props
}, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={cn(
      'inline-flex items-center justify-center whitespace-nowrap rounded-sm px-3 py-1.5 text-sm font-medium ring-offset-background transition-all',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
      'disabled:pointer-events-none disabled:opacity-50',
      'data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-sm',
      className
    )}
    {...props}
  />
));

TabsTrigger.displayName = 'TabsTrigger';

export const TabsContent = React.forwardRef(({
  className,
  ...props
}, ref) => (
  <TabsPrimitive.Content
    ref={ref}
    className={cn(
      'mt-2 ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
      className
    )}
    {...props}
  />
));

TabsContent.displayName = 'TabsContent';

// Legacy aliases for backward compatibility
export const Tab = TabsTrigger;
export const TabPanel = TabsContent;

export default Tabs;
