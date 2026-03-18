/**
 * HierarchyAggregationBar — Reusable hierarchy filter for analytics pages
 *
 * Three dimensions:
 *   Geography: All → Region → State → City → Site
 *   Product:   All → Category → Family → Product
 *   Time:      Date range picker (start/end)
 *
 * Each dimension shows the current level as a breadcrumb and the available
 * children as clickable chips to drill down. Clicking a breadcrumb navigates up.
 *
 * Props:
 *   sites       - Array of site objects (with geography.region, geography.state_prov, geography.city)
 *   products    - Array of product objects (with category, family)
 *   value       - Current selection: { geo: {level, key}, product: {level, key}, timeStart, timeEnd }
 *   onChange     - Callback: (newValue) => void
 */

import React, { useMemo } from 'react';
import { MapPin, Package, Calendar, ChevronRight, X } from 'lucide-react';
import { cn } from '../../lib/utils/cn';
import { Card, CardContent, Badge } from '../common';

const GEO_LEVELS = ['all', 'region', 'state', 'city', 'site'];
const PRODUCT_LEVELS = ['all', 'category', 'family', 'product'];

// Extract unique values at each geo level, filtered by current selection
function geoChildren(sites, level, parentKey) {
  let filtered = sites;
  if (level === 'region') {
    // No parent filter needed for region
  } else if (level === 'state') {
    filtered = sites.filter(s => (s.geography?.region || 'Other') === parentKey);
  } else if (level === 'city') {
    filtered = sites.filter(s => (s.geography?.state_prov) === parentKey);
  } else if (level === 'site') {
    filtered = sites.filter(s => (s.geography?.city) === parentKey);
  }

  if (level === 'region') {
    return [...new Set(filtered.map(s => s.geography?.region || 'Other'))].filter(Boolean).sort();
  } else if (level === 'state') {
    return [...new Set(filtered.map(s => s.geography?.state_prov).filter(Boolean))].sort();
  } else if (level === 'city') {
    return [...new Set(filtered.map(s => s.geography?.city).filter(Boolean))].sort();
  } else if (level === 'site') {
    return filtered.map(s => s.name).filter(Boolean).sort();
  }
  return [];
}

function productChildren(products, level, parentKey) {
  let filtered = products;
  if (level === 'category') {
    // No filter
  } else if (level === 'family') {
    filtered = products.filter(p => (p.category || 'Other') === parentKey);
  } else if (level === 'product') {
    filtered = products.filter(p => (p.family || 'Other') === parentKey);
  }

  if (level === 'category') {
    return [...new Set(filtered.map(p => p.category).filter(Boolean))].sort();
  } else if (level === 'family') {
    return [...new Set(filtered.map(p => p.family).filter(Boolean))].sort();
  } else if (level === 'product') {
    return filtered.map(p => p.description?.split('[')[0]?.trim() || p.name || p.id).sort();
  }
  return [];
}

// Build breadcrumb trail for a dimension
function geoBreadcrumbs(value) {
  const crumbs = [{ level: 'all', key: null, label: 'All Geographies' }];
  if (value.level === 'all') return crumbs;
  if (value.level === 'region' || value.level === 'state' || value.level === 'city' || value.level === 'site') {
    if (value.regionKey) crumbs.push({ level: 'region', key: value.regionKey, label: value.regionKey });
  }
  if (value.level === 'state' || value.level === 'city' || value.level === 'site') {
    if (value.stateKey) crumbs.push({ level: 'state', key: value.stateKey, label: value.stateKey });
  }
  if (value.level === 'city' || value.level === 'site') {
    if (value.cityKey) crumbs.push({ level: 'city', key: value.cityKey, label: value.cityKey });
  }
  if (value.level === 'site') {
    if (value.siteKey) crumbs.push({ level: 'site', key: value.siteKey, label: value.siteKey });
  }
  return crumbs;
}

function productBreadcrumbs(value) {
  const crumbs = [{ level: 'all', key: null, label: 'All Products' }];
  if (value.level === 'all') return crumbs;
  if (value.categoryKey) crumbs.push({ level: 'category', key: value.categoryKey, label: value.categoryKey });
  if (value.level === 'family' || value.level === 'product') {
    if (value.familyKey) crumbs.push({ level: 'family', key: value.familyKey, label: value.familyKey });
  }
  if (value.level === 'product') {
    if (value.productKey) crumbs.push({ level: 'product', key: value.productKey, label: value.productKey });
  }
  return crumbs;
}

const DimensionRow = ({ icon: Icon, color, label, breadcrumbs, children, currentLevel, onCrumbClick, onChildClick }) => (
  <div>
    <div className="flex items-center gap-1.5 min-w-0">
      <Icon className={cn('h-4 w-4 flex-shrink-0', color)} />
      <span className="text-xs font-medium text-muted-foreground flex-shrink-0 w-16">{label}:</span>
      <div className="flex items-center gap-1 min-w-0 flex-wrap">
        {breadcrumbs.map((crumb, i) => (
          <React.Fragment key={`${crumb.level}-${crumb.key}`}>
            {i > 0 && <ChevronRight className="h-3 w-3 text-muted-foreground flex-shrink-0" />}
            {crumb.level === currentLevel ? (
              <Badge variant="default" className="text-xs px-2 py-0.5">{crumb.label}</Badge>
            ) : (
              <button
                onClick={() => onCrumbClick(crumb.level, crumb.key)}
                className="text-xs text-primary hover:underline cursor-pointer"
              >
                {crumb.label}
              </button>
            )}
          </React.Fragment>
        ))}
      </div>
    </div>
    {children && children.length > 0 && (
      <div className="flex items-center gap-1.5 flex-wrap ml-[5.5rem] mt-0.5">
        <span className="text-xs text-muted-foreground">Drill into:</span>
        {children.slice(0, 15).map((child) => (
          <button
            key={child}
            onClick={() => onChildClick(child)}
            className={cn(
              'text-xs px-2 py-0.5 rounded-full border',
              'bg-muted/50 hover:bg-primary/10 hover:border-primary/30',
              'transition-colors cursor-pointer',
            )}
          >
            {child}
          </button>
        ))}
        {children.length > 15 && (
          <span className="text-[10px] text-muted-foreground">+{children.length - 15} more</span>
        )}
      </div>
    )}
  </div>
);

// Default time range: last 12 months
const defaultTimeStart = () => {
  const d = new Date();
  d.setMonth(d.getMonth() - 12);
  return d.toISOString().slice(0, 10);
};
const defaultTimeEnd = () => new Date().toISOString().slice(0, 10);

export const DEFAULT_HIERARCHY_VALUE = {
  geo: { level: 'all', regionKey: null, stateKey: null, cityKey: null, siteKey: null },
  product: { level: 'all', categoryKey: null, familyKey: null, productKey: null },
  timeStart: defaultTimeStart(),
  timeEnd: defaultTimeEnd(),
};

const HierarchyAggregationBar = ({ sites = [], products = [], value = DEFAULT_HIERARCHY_VALUE, onChange }) => {
  const geo = value.geo || DEFAULT_HIERARCHY_VALUE.geo;
  const prod = value.product || DEFAULT_HIERARCHY_VALUE.product;

  // Compute children for current geo level
  const geoChildList = useMemo(() => {
    const nextLevel = GEO_LEVELS[GEO_LEVELS.indexOf(geo.level) + 1];
    if (!nextLevel) return [];
    const parentKey = geo.level === 'all' ? null
      : geo.level === 'region' ? geo.regionKey
      : geo.level === 'state' ? geo.stateKey
      : geo.cityKey;
    return geoChildren(sites, nextLevel, parentKey);
  }, [sites, geo]);

  const prodChildList = useMemo(() => {
    const nextLevel = PRODUCT_LEVELS[PRODUCT_LEVELS.indexOf(prod.level) + 1];
    if (!nextLevel) return [];
    const parentKey = prod.level === 'all' ? null
      : prod.level === 'category' ? prod.categoryKey
      : prod.familyKey;
    return productChildren(products, nextLevel, parentKey);
  }, [products, prod]);

  const handleGeoCrumb = (level) => {
    const newGeo = { level, regionKey: null, stateKey: null, cityKey: null, siteKey: null };
    if (level !== 'all' && geo.regionKey) newGeo.regionKey = geo.regionKey;
    if ((level === 'state' || level === 'city' || level === 'site') && geo.stateKey) newGeo.stateKey = geo.stateKey;
    if ((level === 'city' || level === 'site') && geo.cityKey) newGeo.cityKey = geo.cityKey;
    onChange({ ...value, geo: newGeo });
  };

  const handleGeoDrill = (childKey) => {
    const nextLevel = GEO_LEVELS[GEO_LEVELS.indexOf(geo.level) + 1];
    const newGeo = { ...geo, level: nextLevel };
    if (nextLevel === 'region') newGeo.regionKey = childKey;
    else if (nextLevel === 'state') newGeo.stateKey = childKey;
    else if (nextLevel === 'city') newGeo.cityKey = childKey;
    else if (nextLevel === 'site') newGeo.siteKey = childKey;
    onChange({ ...value, geo: newGeo });
  };

  const handleProdCrumb = (level) => {
    const newProd = { level, categoryKey: null, familyKey: null, productKey: null };
    if (level !== 'all' && prod.categoryKey) newProd.categoryKey = prod.categoryKey;
    if ((level === 'family' || level === 'product') && prod.familyKey) newProd.familyKey = prod.familyKey;
    onChange({ ...value, product: newProd });
  };

  const handleProdDrill = (childKey) => {
    const nextLevel = PRODUCT_LEVELS[PRODUCT_LEVELS.indexOf(prod.level) + 1];
    const newProd = { ...prod, level: nextLevel };
    if (nextLevel === 'category') newProd.categoryKey = childKey;
    else if (nextLevel === 'family') newProd.familyKey = childKey;
    else if (nextLevel === 'product') newProd.productKey = childKey;
    onChange({ ...value, product: newProd });
  };

  const isFiltered = geo.level !== 'all' || prod.level !== 'all';

  return (
    <Card className="mb-4">
      <CardContent className="py-3 space-y-2">
        <DimensionRow
          icon={MapPin}
          color="text-blue-600"
          label="Geography"
          breadcrumbs={geoBreadcrumbs(geo)}
          children={geoChildList}
          currentLevel={geo.level}
          onCrumbClick={handleGeoCrumb}
          onChildClick={handleGeoDrill}
        />
        <DimensionRow
          icon={Package}
          color="text-green-600"
          label="Product"
          breadcrumbs={productBreadcrumbs(prod)}
          children={prodChildList}
          currentLevel={prod.level}
          onCrumbClick={handleProdCrumb}
          onChildClick={handleProdDrill}
        />
        <div className="flex items-center gap-1.5">
          <Calendar className="h-4 w-4 text-amber-600 flex-shrink-0" />
          <span className="text-xs font-medium text-muted-foreground flex-shrink-0 w-16">Time:</span>
          <input
            type="date"
            className="text-xs border rounded px-2 py-0.5 bg-background"
            value={value.timeStart || ''}
            onChange={(e) => onChange({ ...value, timeStart: e.target.value })}
          />
          <span className="text-xs text-muted-foreground">to</span>
          <input
            type="date"
            className="text-xs border rounded px-2 py-0.5 bg-background"
            value={value.timeEnd || ''}
            onChange={(e) => onChange({ ...value, timeEnd: e.target.value })}
          />
          {isFiltered && (
            <button
              className="ml-2 flex items-center gap-0.5 text-[10px] text-primary hover:underline"
              onClick={() => onChange(DEFAULT_HIERARCHY_VALUE)}
            >
              <X className="h-3 w-3" /> Reset all
            </button>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default HierarchyAggregationBar;
