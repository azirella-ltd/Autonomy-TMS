/**
 * PageLayout Component - Autonomy UI Kit
 *
 * Standard page layout wrapper providing consistent spacing,
 * page titles, and Helmet integration for document titles.
 *
 * Migrated to Autonomy UI Kit
 */

import React from 'react';
import { Helmet } from 'react-helmet-async';
import { H1, H2 } from './common';
import { cn } from '../lib/utils/cn';

const maxWidthClasses = {
  'container.sm': 'max-w-2xl',
  'container.md': 'max-w-4xl',
  'container.lg': 'max-w-6xl',
  'container.xl': 'max-w-7xl',
  full: 'max-w-full',
};

const PageLayout = ({ title, children, maxW = 'container.lg', className, ...rest }) => {
  const maxWidthClass = maxWidthClasses[maxW] || 'max-w-6xl';

  return (
    <>
      <Helmet>
        <title>{title ? `${title} | Autonomy` : 'Autonomy'}</title>
      </Helmet>
      <main
        className={cn(
          maxWidthClass,
          'mx-auto px-4 py-8 font-sans',
          className
        )}
        {...rest}
      >
        {title && (
          <div className="mb-8">
            <div className="h-2" />
            <H1 className="font-bold text-foreground">
              {title}
            </H1>
          </div>
        )}
        {children}
      </main>
    </>
  );
};

export const PageSection = ({ title, children, className, ...rest }) => (
  <div className={cn('mb-8', className)} {...rest}>
    {title && (
      <H2 className="text-2xl font-semibold mt-5 mb-3 leading-tight text-gray-700 dark:text-gray-300">
        {title}
      </H2>
    )}
    {children}
  </div>
);

export default PageLayout;
