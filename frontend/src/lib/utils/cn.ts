/**
 * Class Name Utility (cn)
 *
 * Combines clsx and tailwind-merge for optimal Tailwind CSS class management.
 * - clsx: Conditionally constructs className strings
 * - tailwind-merge: Intelligently merges Tailwind classes (later classes override earlier ones)
 *
 * Usage:
 * ```tsx
 * import { cn } from '@/lib/utils';
 *
 * // Basic usage
 * <div className={cn("text-base", "text-lg")} /> // Result: "text-lg"
 *
 * // Conditional classes
 * <div className={cn(
 *   "base-class",
 *   isActive && "active-class",
 *   error ? "error-class" : "success-class"
 * )} />
 *
 * // Merging with conflicts
 * <div className={cn("p-4 bg-red-500", "p-6")} /> // Result: "p-6 bg-red-500"
 * ```
 */

import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Get the computed color value from a CSS variable
 * @param variable - CSS variable name (e.g., 'primary', 'border', 'muted-foreground')
 * @returns The computed color value as a string
 */
// Cache resolved colors to avoid recomputation
const colorCache = new Map<string, string>();

export function getCSSVariable(variable: string): string {
  if (typeof window === 'undefined') return '#000000';
  if (colorCache.has(variable)) return colorCache.get(variable)!;

  const raw = getComputedStyle(document.documentElement)
    .getPropertyValue(`--${variable}`)
    .trim();

  if (!raw) {
    colorCache.set(variable, '#000000');
    return '#000000';
  }

  try {
    // Normalize to a computed color the browser understands (usually rgb(...))
    const probe = document.createElement('span');
    probe.style.color = raw; // supports oklch(), hsl(), rgb(), hex
    document.body.appendChild(probe);
    const computed = getComputedStyle(probe).color; // e.g., rgb(…)
    document.body.removeChild(probe);

    const result = computed || raw;
    colorCache.set(variable, result);
    return result;
  } catch {
    colorCache.set(variable, raw);
    return raw;
  }
}

/**
 * Get chart colors object for use in Recharts components
 */
export function getChartColors() {
  return {
    border: getCSSVariable('border'),
    mutedForeground: getCSSVariable('muted-foreground'),
    primary: getCSSVariable('primary'),
    destructive: getCSSVariable('destructive'),
    accent: getCSSVariable('accent'),
    warning: getCSSVariable('warning'),
    info: getCSSVariable('info'),
    chart1: getCSSVariable('chart-1'),
    chart2: getCSSVariable('chart-2'),
    chart3: getCSSVariable('chart-3'),
    chart4: getCSSVariable('chart-4'),
    chart5: getCSSVariable('chart-5'),
  };
}
