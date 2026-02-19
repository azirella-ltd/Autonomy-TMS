/**
 * PageLayout Component - Autonomy UI Kit Version
 *
 * Main page layout wrapper using Tailwind CSS and shadcn design tokens.
 * Provides consistent page structure with title and section components.
 */

import React from 'react';
import { Helmet } from 'react-helmet-async';
import { cn } from '../lib/utils/cn';

const PageLayout = ({
  title,
  description,
  children,
  maxWidth = 'max-w-7xl',
  className,
  ...rest
}) => {
  return (
    <>
      <Helmet>
        <title>{title ? `${title} | Autonomy` : 'Autonomy'}</title>
      </Helmet>
      <main
        className={cn(
          maxWidth,
          'mx-auto px-4 sm:px-6 lg:px-8 py-8',
          className
        )}
        {...rest}
      >
        {title && (
          <div className="mb-8">
            <h1 className="text-3xl font-bold tracking-tight text-foreground">
              {title}
            </h1>
            {description && (
              <p className="mt-2 text-muted-foreground">
                {description}
              </p>
            )}
          </div>
        )}
        {children}
      </main>
    </>
  );
};

export const PageSection = ({
  title,
  description,
  children,
  className,
  ...rest
}) => (
  <section className={cn('mb-8', className)} {...rest}>
    {title && (
      <div className="mb-4">
        <h2 className="text-xl font-semibold text-foreground">
          {title}
        </h2>
        {description && (
          <p className="mt-1 text-sm text-muted-foreground">
            {description}
          </p>
        )}
      </div>
    )}
    {children}
  </section>
);

export const PageHeader = ({
  title,
  description,
  actions,
  className,
}) => (
  <div className={cn('mb-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between', className)}>
    <div>
      <h1 className="text-3xl font-bold tracking-tight text-foreground">
        {title}
      </h1>
      {description && (
        <p className="mt-2 text-muted-foreground">
          {description}
        </p>
      )}
    </div>
    {actions && (
      <div className="flex items-center gap-2">
        {actions}
      </div>
    )}
  </div>
);

export default PageLayout;
