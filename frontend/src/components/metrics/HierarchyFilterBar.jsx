/**
 * HierarchyFilterBar — Breadcrumb navigation + drill-down chips
 *
 * Three rows: Geography, Product, Time
 * Each row shows: breadcrumb trail (clickable to navigate up) + children chips (clickable to drill down)
 */

import React from 'react';
import {
  ChevronRight,
  MapPin,
  Package,
  Calendar,
} from 'lucide-react';
import { cn } from '../../lib/utils/cn';
import { Card, CardContent, Badge } from '../common';

const DIMENSION_CONFIG = {
  site: { label: 'Geography', icon: MapPin, color: 'text-blue-600' },
  product: { label: 'Product', icon: Package, color: 'text-green-600' },
  time: { label: 'Time', icon: Calendar, color: 'text-amber-600' },
};

const BreadcrumbTrail = ({ dimension, crumbs, onBreadcrumbClick }) => {
  const config = DIMENSION_CONFIG[dimension];
  const Icon = config.icon;

  return (
    <div className="flex items-center gap-1.5 min-w-0">
      <Icon className={cn('h-4 w-4 flex-shrink-0', config.color)} />
      <span className="text-xs font-medium text-muted-foreground flex-shrink-0 w-16">
        {config.label}:
      </span>
      <div className="flex items-center gap-1 min-w-0 flex-wrap">
        {crumbs.map((crumb, i) => (
          <React.Fragment key={`${crumb.level}-${crumb.key}`}>
            {i > 0 && <ChevronRight className="h-3 w-3 text-muted-foreground flex-shrink-0" />}
            {crumb.is_current ? (
              <Badge variant="default" className="text-xs px-2 py-0.5">
                {crumb.label}
              </Badge>
            ) : (
              <button
                onClick={() => onBreadcrumbClick(dimension, crumb.level, crumb.key)}
                className="text-xs text-primary hover:underline cursor-pointer"
              >
                {crumb.label}
              </button>
            )}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
};

const DrillDownChips = ({ dimension, children, onDrillDown }) => {
  if (!children || children.length === 0) return null;

  return (
    <div className="flex items-center gap-1.5 flex-wrap ml-[5.5rem]">
      <span className="text-xs text-muted-foreground">Drill into:</span>
      {children.map((child) => (
        <button
          key={child.key}
          onClick={() => onDrillDown(dimension, child.level, child.key)}
          className={cn(
            'text-xs px-2 py-0.5 rounded-full border',
            'bg-muted/50 hover:bg-primary/10 hover:border-primary/30',
            'transition-colors cursor-pointer',
          )}
        >
          {child.label}
        </button>
      ))}
    </div>
  );
};

const HierarchyFilterBar = ({
  breadcrumbs,
  children,
  onDrillDown,
  onBreadcrumbClick,
}) => {
  if (!breadcrumbs) return null;

  return (
    <Card className="mb-4">
      <CardContent className="py-3 space-y-2">
        {['site', 'product', 'time'].map((dim) => (
          <div key={dim}>
            <BreadcrumbTrail
              dimension={dim}
              crumbs={breadcrumbs[dim] || []}
              onBreadcrumbClick={onBreadcrumbClick}
            />
            <DrillDownChips
              dimension={dim}
              children={children?.[dim] || []}
              onDrillDown={onDrillDown}
            />
          </div>
        ))}
      </CardContent>
    </Card>
  );
};

export default HierarchyFilterBar;
