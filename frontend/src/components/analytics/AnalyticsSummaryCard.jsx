import React from 'react';
import { Card, CardContent } from '../common';

// Tailwind color map for accent colors
const colorMap = {
  success: { bg: 'bg-green-500/15', text: 'text-green-500', border: 'border-t-green-500' },
  warning: { bg: 'bg-amber-500/15', text: 'text-amber-500', border: 'border-t-amber-500' },
  error: { bg: 'bg-red-500/15', text: 'text-red-500', border: 'border-t-red-500' },
  info: { bg: 'bg-blue-500/15', text: 'text-blue-500', border: 'border-t-blue-500' },
  primary: { bg: 'bg-primary/15', text: 'text-primary', border: 'border-t-primary' },
};

/**
 * Reusable summary card component for analytics metrics
 *
 * @param {string} title - Card title
 * @param {string|number} value - Main metric value
 * @param {string} subtitle - Optional subtitle/description
 * @param {React.Component} icon - Optional lucide-react icon component
 * @param {string} color - Card accent color (success, warning, error, info, primary)
 */
const AnalyticsSummaryCard = ({
  title,
  value,
  subtitle,
  icon: Icon,
  color = 'primary'
}) => {
  const colors = colorMap[color] || colorMap.primary;

  return (
    <Card className={`h-full relative overflow-visible border-t-4 ${colors.border}`}>
      <CardContent className="pt-4">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <span className="text-xs uppercase tracking-wide text-muted-foreground font-medium mb-1 block">
              {title}
            </span>
            <span className={`text-3xl font-semibold block ${subtitle ? 'mb-1' : ''}`}>
              {value}
            </span>
            {subtitle && (
              <span className="text-sm text-muted-foreground">
                {subtitle}
              </span>
            )}
          </div>
          {Icon && (
            <div className={`flex items-center justify-center w-12 h-12 rounded-full ${colors.bg} ${colors.text} ml-4`}>
              <Icon className="h-7 w-7" />
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default AnalyticsSummaryCard;
