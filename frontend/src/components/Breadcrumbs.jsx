/**
 * Breadcrumb Navigation Component
 *
 * Shows current location path with clickable navigation.
 * Automatically generates breadcrumbs from current route.
 *
 * Migrated to Autonomy UI Kit
 */

import React, { useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Home, ChevronRight } from 'lucide-react';
import { Typography } from './common';
import { cn } from '@azirella-ltd/autonomy-frontend';

// Route path to label mapping
const ROUTE_LABELS = {
  // Main sections
  dashboard: 'Dashboard',
  analytics: 'Analytics',
  insights: 'Insights',
  scenarios: 'Scenarios',
  admin: 'Administration',
  planning: 'Planning',
  visibility: 'Visibility',
  execution: 'Execution',
  system: 'System',

  // Planning pages
  demand: 'Demand Planning',
  'demand-collaboration': 'Demand Collaboration',
  supply: 'Supply Planning',
  'supply-plan': 'Supply Planning',
  board: 'Planning Board',
  mps: 'Master Production Scheduling',
  mrp: 'Material Requirements Planning',
  capacity: 'Capacity Planning',
  sourcing: 'Sourcing Allocation',
  recommendations: 'Recommended Actions',
  'production-orders': 'Production Orders',
  'purchase-orders': 'Purchase Orders',
  'transfer-orders': 'Transfer Orders',
  orders: 'Order Tracking',
  suppliers: 'Supplier Management',
  'inventory-projection': 'ATP/CTP Projection',
  'monte-carlo': 'Stochastic Planning',
  'kpi-monitoring': 'KPI Monitoring',
  'shipment-tracking': 'Shipment Tracking',
  'lot-sizing': 'Lot Sizing Analysis',
  'capacity-check': 'Capacity Check',
  'atp-ctp': 'Order Promising (ATP/CTP)',
  'po-creation': 'PO Creation',
  'inventory-rebalancing': 'Inventory Rebalancing',
  'vendor-lead-times': 'Vendor Lead Times',
  'production-processes': 'Production Processes',
  'resource-capacity': 'Resource Capacity',
  collaboration: 'Collaboration Hub',
  'project-orders': 'Project Orders',
  'maintenance-orders': 'Maintenance Orders',
  'turnaround-orders': 'Turnaround Orders',

  // Analytics pages
  'sc-analytics': 'Supply Chain Analytics',
  risk: 'Risk Analysis',
  'inventory-optimization': 'Inventory Optimization',
  'capacity-optimization': 'Capacity Optimization',
  'network-optimization': 'Network Optimization',
  'kpi-configuration': 'Performance Metrics',

  // Visibility pages
  ntier: 'N-Tier Visibility',
  'material-visibility': 'Material Visibility',

  // Execution pages
  'service-orders': 'Service Orders',

  // Supply Chain Design
  'supply-chain-configs': 'Network Configs',

  // Admin pages
  monitoring: 'System Monitoring',
  governance: 'Governance',
  groups: 'Customers',
  customers: 'Customers',
  users: 'User Management',
  'role-management': 'Role Management',
  powell: 'Decision Cascade',
  trm: 'Execution Agents',
  gnn: 'S&OP Agent',
  rl: 'Reinforcement Learning',
  'model-setup': 'Agent Configuration',
  'system-config': 'System Config',

  // Game pages
  new: 'Create Scenario',
  report: 'Scenario Report',
  visualizations: 'Visualizations',

  // Other
  scenarioUsers: 'Users',
  settings: 'Settings',
  'ai-assistant': 'AI Assistant',
  production: 'Production',
  group: 'Organization',
  customer: 'Organization',
  tenant: 'Organization',
  tenants: 'Organizations',
};

const Breadcrumbs = () => {
  const location = useLocation();
  const navigate = useNavigate();

  const breadcrumbs = useMemo(() => {
    const pathnames = location.pathname.split('/').filter((x) => x);

    // Don't show breadcrumbs on home/dashboard
    if (pathnames.length === 0 || (pathnames.length === 1 && pathnames[0] === 'dashboard')) {
      return [];
    }

    const crumbs = [
      {
        label: 'Home',
        path: '/dashboard',
        icon: <Home className="mr-1 h-4 w-4" />,
      },
    ];

    let currentPath = '';
    pathnames.forEach((pathname, index) => {
      currentPath += `/${pathname}`;

      // Skip IDs and dynamic segments (anything that looks like a number or UUID)
      if (/^\d+$/.test(pathname) || /^[a-f0-9-]{36}$/i.test(pathname)) {
        return;
      }

      // Get label from mapping or use pathname
      const label = ROUTE_LABELS[pathname] ||
        pathname.split('-').map(word =>
          word.charAt(0).toUpperCase() + word.slice(1)
        ).join(' ');

      crumbs.push({
        label,
        path: currentPath,
        isLast: index === pathnames.length - 1,
      });
    });

    return crumbs;
  }, [location.pathname]);

  // Don't render if no breadcrumbs
  if (breadcrumbs.length === 0) {
    return null;
  }

  const handleClick = (event, path) => {
    event.preventDefault();
    navigate(path);
  };

  return (
    <nav className="mb-4" aria-label="breadcrumb">
      <ol className="flex items-center flex-wrap gap-1">
        {breadcrumbs.map((crumb, index) => {
          const isLast = index === breadcrumbs.length - 1;

          return (
            <li key={crumb.path} className="flex items-center">
              {index > 0 && (
                <ChevronRight className="mx-1 h-4 w-4 text-muted-foreground" />
              )}
              {isLast ? (
                <Typography
                  variant="body2"
                  component="span"
                  className={cn(
                    'flex items-center font-semibold text-foreground'
                  )}
                >
                  {crumb.icon}
                  {crumb.label}
                </Typography>
              ) : (
                <a
                  href={crumb.path}
                  onClick={(e) => handleClick(e, crumb.path)}
                  className={cn(
                    'flex items-center text-sm text-muted-foreground',
                    'cursor-pointer hover:text-primary transition-colors'
                  )}
                >
                  {crumb.icon}
                  {crumb.label}
                </a>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
};

export default Breadcrumbs;
