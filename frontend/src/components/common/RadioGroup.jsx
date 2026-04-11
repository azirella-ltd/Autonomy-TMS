/**
 * RadioGroup Component - Autonomy UI Kit Wrapper
 *
 * Radix UI RadioGroup wrapper with styling.
 */

import React from 'react';
import * as RadioGroupPrimitive from '@radix-ui/react-radio-group';
import { cn } from '@azirella-ltd/autonomy-frontend';
import { Circle } from 'lucide-react';

export const RadioGroup = React.forwardRef(({
  className,
  ...props
}, ref) => (
  <RadioGroupPrimitive.Root
    className={cn('grid gap-2', className)}
    {...props}
    ref={ref}
  />
));

RadioGroup.displayName = 'RadioGroup';

export const RadioGroupItem = React.forwardRef(({
  className,
  ...props
}, ref) => (
  <RadioGroupPrimitive.Item
    ref={ref}
    className={cn(
      'aspect-square h-4 w-4 rounded-full border border-primary text-primary ring-offset-background',
      'focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
      'disabled:cursor-not-allowed disabled:opacity-50',
      className
    )}
    {...props}
  >
    <RadioGroupPrimitive.Indicator className="flex items-center justify-center">
      <Circle className="h-2.5 w-2.5 fill-current text-current" />
    </RadioGroupPrimitive.Indicator>
  </RadioGroupPrimitive.Item>
));

RadioGroupItem.displayName = 'RadioGroupItem';

export default RadioGroup;
