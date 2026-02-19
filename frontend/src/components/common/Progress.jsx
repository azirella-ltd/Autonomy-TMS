/**
 * Progress Component
 *
 * A simple horizontal progress bar with customizable appearance.
 *
 * Props:
 * - value: Progress value (0-100)
 * - max: Maximum value (default 100)
 * - className: Additional CSS classes
 * - showLabel: Whether to show percentage label
 * - size: Size variant ('sm', 'md', 'lg')
 */

import React from 'react';
import { cn } from '../../lib/utils/cn';

const sizeClasses = {
  sm: 'h-1.5',
  md: 'h-2.5',
  lg: 'h-4',
};

const Progress = ({
  value = 0,
  max = 100,
  className,
  showLabel = false,
  size = 'md',
  ...props
}) => {
  const percentage = Math.min(Math.max((value / max) * 100, 0), 100);

  return (
    <div
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={max}
      className={cn(
        'relative w-full overflow-hidden rounded-full bg-secondary',
        sizeClasses[size],
        className
      )}
      {...props}
    >
      <div
        className="h-full w-full flex-1 bg-primary transition-all duration-300 ease-in-out"
        style={{ transform: `translateX(-${100 - percentage}%)` }}
      />
      {showLabel && (
        <span className="absolute inset-0 flex items-center justify-center text-xs font-medium">
          {Math.round(percentage)}%
        </span>
      )}
    </div>
  );
};

export { Progress };
