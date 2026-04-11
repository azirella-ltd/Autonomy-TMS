/**
 * ProvisioningBanner — Shows a dismissible banner when the tenant's
 * supply chain config is not fully provisioned.
 *
 * Reads provisioning_status / provisioning_step from AuthContext
 * (populated at login from the backend TokenResponse).
 *
 * System admins never see the banner.
 * Tenant admins see a prominent warning; regular users see a softer info style.
 */

import React from 'react';
import { useAuth } from '../contexts/AuthContext';
import { isSystemAdmin, isTenantAdmin as checkIsTenantAdmin } from '../utils/authUtils';
import { AlertTriangle, Info, X, Settings } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { cn } from '@azirella-ltd/autonomy-frontend';

const ProvisioningBanner = () => {
  const { user, provisioningStatus, provisioningStep, dismissProvisioningBanner } = useAuth();
  const navigate = useNavigate();

  // Never show for system admins
  if (!user || isSystemAdmin(user)) return null;

  // Don't show if provisioning is complete or dismissed
  if (!provisioningStatus || provisioningStatus === 'complete' || provisioningStatus === 'dismissed') {
    return null;
  }

  const isTenantAdm = checkIsTenantAdmin(user);

  // Determine banner content and style based on status
  let message = '';
  let variant = 'info'; // 'info' | 'warning' | 'error'
  let Icon = Info;

  switch (provisioningStatus) {
    case 'not_started':
      message = isTenantAdm
        ? 'Your supply chain configuration has not been provisioned yet. Go to Administration > Supply Chain Config to start provisioning.'
        : 'Supply chain provisioning has not been started. Some features may be unavailable.';
      variant = isTenantAdm ? 'warning' : 'info';
      Icon = isTenantAdm ? AlertTriangle : Info;
      break;

    case 'in_progress':
      message = provisioningStep
        ? `Provisioning is in progress (step: ${provisioningStep}). Some features may be unavailable until complete.`
        : 'Provisioning is in progress. Some features may be unavailable until complete.';
      variant = 'info';
      Icon = Info;
      break;

    case 'failed':
      message = provisioningStep
        ? `Provisioning failed at step: ${provisioningStep}. ${isTenantAdm ? 'Go to Administration > Supply Chain Config to retry.' : 'Contact your administrator.'}`
        : `Provisioning failed. ${isTenantAdm ? 'Go to Administration > Supply Chain Config to retry.' : 'Contact your administrator.'}`;
      variant = 'error';
      Icon = AlertTriangle;
      break;

    default:
      return null;
  }

  const variantStyles = {
    info: 'bg-blue-50 border-blue-200 text-blue-800',
    warning: 'bg-amber-50 border-amber-200 text-amber-800',
    error: 'bg-red-50 border-red-200 text-red-800',
  };

  const iconStyles = {
    info: 'text-blue-500',
    warning: 'text-amber-500',
    error: 'text-red-500',
  };

  return (
    <div
      className={cn(
        'flex items-center gap-3 px-4 py-2.5 border-b text-sm',
        variantStyles[variant],
      )}
    >
      <Icon className={cn('h-4 w-4 flex-shrink-0', iconStyles[variant])} />
      <span className="flex-1">{message}</span>
      {isTenantAdm && (provisioningStatus === 'not_started' || provisioningStatus === 'failed') && (
        <button
          onClick={() => navigate('/admin/supply-chain-config')}
          className={cn(
            'flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium transition-colors',
            variant === 'error'
              ? 'bg-red-100 hover:bg-red-200 text-red-700'
              : 'bg-amber-100 hover:bg-amber-200 text-amber-700',
          )}
        >
          <Settings className="h-3.5 w-3.5" />
          Configure
        </button>
      )}
      <button
        onClick={dismissProvisioningBanner}
        className="flex-shrink-0 p-1 rounded hover:bg-black/5 transition-colors"
        title="Dismiss"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
};

export default ProvisioningBanner;
