/**
 * Slider Component - Autonomy UI Kit Wrapper
 *
 * Range slider with Tailwind styling.
 * Provides easy migration from Chakra UI Slider.
 */

import React from 'react';
import { cn } from '../../lib/utils/cn';

export const Slider = React.forwardRef(({
  value,
  min = 0,
  max = 100,
  step = 1,
  onChange,
  disabled,
  className,
  showValue,
  colorScheme = 'primary',
  isReadOnly,
  ...props
}, ref) => {
  const percentage = ((value - min) / (max - min)) * 100;

  const colorSchemes = {
    primary: 'bg-primary',
    blue: 'bg-blue-500',
    green: 'bg-green-500',
    purple: 'bg-purple-500',
    orange: 'bg-orange-500',
  };

  return (
    <div className={cn('relative w-full', className)}>
      <div className="relative h-2 w-full rounded-full bg-muted">
        <div
          className={cn('absolute h-full rounded-full', colorSchemes[colorScheme])}
          style={{ width: `${percentage}%` }}
        />
        <input
          ref={ref}
          type="range"
          value={value}
          min={min}
          max={max}
          step={step}
          onChange={(e) => !isReadOnly && onChange?.(Number(e.target.value))}
          disabled={disabled || isReadOnly}
          className={cn(
            'absolute inset-0 w-full h-full opacity-0 cursor-pointer',
            (disabled || isReadOnly) && 'cursor-default'
          )}
          {...props}
        />
        <div
          className={cn(
            'absolute top-1/2 -translate-y-1/2 -translate-x-1/2',
            'h-5 w-5 rounded-full border-2 border-primary bg-background shadow',
            'transition-transform',
            !disabled && !isReadOnly && 'hover:scale-110',
            (disabled || isReadOnly) && 'opacity-70'
          )}
          style={{ left: `${percentage}%` }}
        >
          {showValue && (
            <span className="absolute -top-6 left-1/2 -translate-x-1/2 text-xs font-medium">
              {value}
            </span>
          )}
        </div>
      </div>
    </div>
  );
});

Slider.displayName = 'Slider';

export const SliderTrack = ({ children, className }) => (
  <div className={cn('relative h-2 w-full rounded-full bg-muted', className)}>
    {children}
  </div>
);

export const SliderFilledTrack = ({ className, percentage }) => (
  <div
    className={cn('absolute h-full rounded-full bg-primary', className)}
    style={{ width: `${percentage}%` }}
  />
);

export const SliderThumb = ({ children, className, percentage }) => (
  <div
    className={cn(
      'absolute top-1/2 -translate-y-1/2 -translate-x-1/2',
      'h-5 w-5 rounded-full border-2 border-primary bg-background shadow',
      'flex items-center justify-center',
      className
    )}
    style={{ left: `${percentage}%` }}
  >
    {children}
  </div>
);

export default Slider;
