/**
 * ConfigModeSwitcher
 *
 * Navbar widget for tenant admins to switch between production and learning
 * supply chain configs within their tenant.  Calls PUT /users/me/active-config
 * which updates users.default_config_id, then refreshes ActiveConfigContext so
 * all planning pages react immediately.
 *
 * Visibility: tenant admins only (isTenantAdmin check).
 */

import { useState, useEffect } from 'react';
import { useActiveConfig } from '../contexts/ActiveConfigContext';
import { useAuth } from '../contexts/AuthContext';
import { isTenantAdmin } from '../utils/authUtils';
import simulationApi from '../services/api';

export default function ConfigModeSwitcher() {
  const { activeConfig, configMode, refresh } = useActiveConfig();
  const { user } = useAuth();
  const [configs, setConfigs] = useState([]);
  const [open, setOpen] = useState(false);
  const [switching, setSwitching] = useState(false);

  const isAdmin = isTenantAdmin(user);

  // Load all configs for this tenant on mount (hook must come before any conditional return)
  useEffect(() => {
    if (!isAdmin) return;
    simulationApi
      .get('/supply-chain-config/')
      .then((r) => setConfigs(r.data || []))
      .catch(() => {});
  }, [isAdmin]);

  // Only visible to tenant admins
  if (!isAdmin) return null;

  const handleSelect = async (configId) => {
    if (switching) return;
    setSwitching(true);
    try {
      await simulationApi.put('/users/me/active-config', { config_id: configId });
      await refresh();
    } catch (err) {
      console.error('Failed to switch active config:', err);
    } finally {
      setSwitching(false);
      setOpen(false);
    }
  };

  const productionConfigs = configs.filter((c) => c.mode === 'production');
  const learningConfigs = configs.filter((c) => c.mode === 'learning');

  const modeColor =
    configMode === 'learning'
      ? 'bg-amber-100 text-amber-800 border-amber-300'
      : 'bg-blue-100 text-blue-800 border-blue-300';
  const modeLabel = configMode === 'learning' ? 'Learning' : 'Production';

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        disabled={switching}
        className={`flex items-center gap-2 px-3 py-1.5 rounded-md border text-sm font-medium transition-opacity ${modeColor} ${switching ? 'opacity-60 cursor-not-allowed' : 'hover:opacity-90'}`}
      >
        <span className="max-w-[140px] truncate">
          {activeConfig?.name ?? 'Select Config'}
        </span>
        <span className="opacity-60 text-xs shrink-0">{modeLabel}</span>
        <span className="shrink-0">▾</span>
      </button>

      {open && (
        <>
          {/* Backdrop to close on click-outside */}
          <div
            className="fixed inset-0 z-40"
            onClick={() => setOpen(false)}
          />
          <div className="absolute top-full mt-1 right-0 z-50 bg-white border rounded-lg shadow-lg min-w-[240px]">
            {productionConfigs.length > 0 && (
              <>
                <div className="px-3 py-1.5 text-xs font-semibold text-blue-700 bg-blue-50 border-b rounded-t-lg">
                  Production
                </div>
                {productionConfigs.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => handleSelect(c.id)}
                    className={`w-full text-left px-3 py-2 text-sm hover:bg-gray-50 transition-colors ${
                      activeConfig?.id === c.id ? 'font-semibold text-blue-700' : 'text-gray-800'
                    }`}
                  >
                    {c.name}
                  </button>
                ))}
              </>
            )}
            {learningConfigs.length > 0 && (
              <>
                <div
                  className={`px-3 py-1.5 text-xs font-semibold text-amber-700 bg-amber-50 border-t border-b ${
                    productionConfigs.length === 0 ? 'rounded-t-lg' : ''
                  }`}
                >
                  Learning
                </div>
                {learningConfigs.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => handleSelect(c.id)}
                    className={`w-full text-left px-3 py-2 text-sm hover:bg-gray-50 transition-colors ${
                      activeConfig?.id === c.id ? 'font-semibold text-amber-700' : 'text-gray-800'
                    }`}
                  >
                    {c.name}
                  </button>
                ))}
              </>
            )}
            {productionConfigs.length === 0 && learningConfigs.length === 0 && (
              <div className="px-3 py-3 text-sm text-gray-500 text-center">
                No configs available
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
