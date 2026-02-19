/**
 * Table Component - Autonomy UI Kit Wrapper
 *
 * Styled table components using Tailwind CSS.
 * Provides easy migration from MUI/Chakra Table components.
 */

import React from 'react';
import { cn } from '../../lib/utils/cn';

export const Table = React.forwardRef(({
  children,
  className,
  ...props
}, ref) => (
  <div className="relative w-full overflow-auto">
    <table
      ref={ref}
      className={cn('w-full caption-bottom text-sm', className)}
      {...props}
    >
      {children}
    </table>
  </div>
));
Table.displayName = 'Table';

export const TableHeader = React.forwardRef(({
  children,
  className,
  ...props
}, ref) => (
  <thead ref={ref} className={cn('[&_tr]:border-b', className)} {...props}>
    {children}
  </thead>
));
TableHeader.displayName = 'TableHeader';

export const TableBody = React.forwardRef(({
  children,
  className,
  ...props
}, ref) => (
  <tbody
    ref={ref}
    className={cn('[&_tr:last-child]:border-0', className)}
    {...props}
  >
    {children}
  </tbody>
));
TableBody.displayName = 'TableBody';

export const TableFooter = React.forwardRef(({
  children,
  className,
  ...props
}, ref) => (
  <tfoot
    ref={ref}
    className={cn('border-t bg-muted/50 font-medium [&>tr]:last:border-b-0', className)}
    {...props}
  >
    {children}
  </tfoot>
));
TableFooter.displayName = 'TableFooter';

export const TableRow = React.forwardRef(({
  children,
  className,
  selected,
  hoverable = true,
  ...props
}, ref) => (
  <tr
    ref={ref}
    className={cn(
      'border-b transition-colors',
      hoverable && 'hover:bg-muted/50',
      selected && 'bg-muted',
      className
    )}
    {...props}
  >
    {children}
  </tr>
));
TableRow.displayName = 'TableRow';

export const TableHead = React.forwardRef(({
  children,
  className,
  ...props
}, ref) => (
  <th
    ref={ref}
    className={cn(
      'h-12 px-4 text-left align-middle font-semibold text-muted-foreground',
      'bg-muted/30 uppercase text-xs tracking-wider',
      '[&:has([role=checkbox])]:pr-0',
      className
    )}
    {...props}
  >
    {children}
  </th>
));
TableHead.displayName = 'TableHead';

export const TableCell = React.forwardRef(({
  children,
  className,
  ...props
}, ref) => (
  <td
    ref={ref}
    className={cn(
      'p-4 align-middle [&:has([role=checkbox])]:pr-0',
      className
    )}
    {...props}
  >
    {children}
  </td>
));
TableCell.displayName = 'TableCell';

export const TableCaption = React.forwardRef(({
  children,
  className,
  ...props
}, ref) => (
  <caption
    ref={ref}
    className={cn('mt-4 text-sm text-muted-foreground', className)}
    {...props}
  >
    {children}
  </caption>
));
TableCaption.displayName = 'TableCaption';

// Container variant for styled table card
export const TableContainer = ({
  children,
  className,
  title,
  actions,
  ...props
}) => (
  <div
    className={cn(
      'rounded-lg border bg-card shadow-sm overflow-hidden',
      className
    )}
    {...props}
  >
    {(title || actions) && (
      <div className="flex items-center justify-between px-4 py-3 border-b bg-muted/30">
        {title && (
          <h3 className="font-semibold text-card-foreground">{title}</h3>
        )}
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
    )}
    {children}
  </div>
);

export default Table;
