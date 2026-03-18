/**
 * DisplayPreferencesContext
 *
 * Provides tenant-level display preferences to all UI components.
 * The primary setting is `displayIdentifiers` which controls whether
 * entity names or raw IDs are shown throughout the UI.
 *
 * Loads and caches name lookup maps for ALL entity types in the active config
 * (products, sites, vendors/suppliers, customers, markets, lanes).
 *
 * Usage:
 *   const { formatProduct, formatSite, formatIdentifier } = useDisplayPreferences();
 *
 *   // When both ID and name are available:
 *   <span>{formatProduct(product_id, product_name)}</span>
 *
 *   // When only ID is available — lookup resolves automatically:
 *   <span>{formatProduct(product_id)}</span>
 *   <span>{formatSite(site_id)}</span>
 *   <span>{formatSupplier(vendor_id)}</span>
 *   <span>{formatCustomer(customer_id)}</span>
 *
 *   // Generic — works for any entity:
 *   <span>{formatIdentifier(raw_id, maybe_name)}</span>
 */
import { createContext, useContext, useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { api } from '../services/api';
import { useAuth } from './AuthContext';

const EMPTY = {};

const DisplayPreferencesContext = createContext({
  displayIdentifiers: 'name',
  loading: true,
  formatProduct: (id, name) => name || id || '',
  formatSite: (id, name) => name || id || '',
  formatSupplier: (id, name) => name || id || '',
  formatCustomer: (id, name) => name || id || '',
  formatMarket: (id, name) => name || id || '',
  formatLane: (id, name) => name || id || '',
  formatIdentifier: (id, name) => name || id || '',
  refresh: async () => {},
  loadLookupsForConfig: async () => {},
});

/**
 * Build a resolver function for a specific entity type.
 * When pref is 'id', always returns the raw ID.
 * When pref is 'name', returns provided name or looks up from map.
 */
function makeResolver(pref, lookupMap) {
  return (id, name) => {
    if (pref === 'id') return id != null ? String(id) : name || '';
    if (name) return name;
    if (id != null) {
      const looked = lookupMap[String(id)];
      if (looked) return looked;
    }
    return id != null ? String(id) : '';
  };
}

export function DisplayPreferencesProvider({ children }) {
  const { isAuthenticated, user } = useAuth();
  const [displayIdentifiers, setDisplayIdentifiers] = useState('name');
  const [loading, setLoading] = useState(true);

  // Lookup maps: string(id) → display name
  const [productNames, setProductNames] = useState(EMPTY);
  const [siteNames, setSiteNames] = useState(EMPTY);
  const [supplierNames, setSupplierNames] = useState(EMPTY);
  const [customerNames, setCustomerNames] = useState(EMPTY);
  const [marketNames, setMarketNames] = useState(EMPTY);
  const [laneNames, setLaneNames] = useState(EMPTY);
  const loadedConfigRef = useRef(null);

  // ── Fetch tenant preference ───────────────────────────────────────────
  const fetchPreferences = useCallback(async () => {
    if (!isAuthenticated) return;
    const tenantId = user?.tenant_id;
    if (!tenantId) {
      setDisplayIdentifiers('name');
      setLoading(false);
      return;
    }
    try {
      const res = await api.get('/tenant-preferences');
      setDisplayIdentifiers(res.data.display_identifiers || 'name');
    } catch (err) {
      console.warn('Failed to load display preferences, defaulting to name:', err?.message);
      setDisplayIdentifiers('name');
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated, user?.tenant_id]);

  useEffect(() => { fetchPreferences(); }, [fetchPreferences]);

  // ── Load ALL entity lookups for a config ──────────────────────────────
  const loadLookupsForConfig = useCallback(async (configId) => {
    if (!configId || !isAuthenticated) return;
    if (loadedConfigRef.current === configId) return;
    loadedConfigRef.current = configId;

    // Fire all lookups in parallel — individual failures don't block others
    const safe = (promise) => promise.catch(() => ({ data: [] }));
    try {
      const [productsRes, sitesRes, suppliersRes, customersRes, marketsRes, lanesRes] = await Promise.all([
        safe(api.get(`/supply-chain-config/${configId}/products`)),
        safe(api.get(`/supply-chain-config/${configId}/sites`)),
        safe(api.get(`/suppliers?config_id=${configId}&limit=500`)),
        safe(api.get(`/suppliers?config_id=${configId}&tpartner_type=customer&limit=500`)),
        safe(api.get(`/supply-chain-config/${configId}/markets`)),
        safe(api.get(`/supply-chain-config/${configId}/transportation-lanes`)),
      ]);

      // Products: id → short name from description
      const pMap = {};
      for (const p of (productsRes.data || [])) {
        const desc = p.description || '';
        const shortName = desc.includes('[') ? desc.split('[')[0].trim() : desc;
        pMap[String(p.id)] = shortName || String(p.id);
      }
      setProductNames(pMap);

      // Sites: id → name (also map name→name for when data uses name as key)
      const sMap = {};
      for (const s of (sitesRes.data || [])) {
        sMap[String(s.id)] = s.name || String(s.id);
        if (s.name) sMap[s.name] = s.name;
      }
      setSiteNames(sMap);

      // Suppliers/vendors (TradingPartner with type='vendor')
      const vMap = {};
      const suppliers = Array.isArray(suppliersRes.data) ? suppliersRes.data
        : (suppliersRes.data?.items || suppliersRes.data?.suppliers || []);
      for (const v of suppliers) {
        if (v.tpartner_type === 'vendor' || !v.tpartner_type) {
          vMap[String(v.id)] = v.company_name || v.name || String(v.id);
        }
      }
      setSupplierNames(vMap);

      // Customers (TradingPartner with type='customer')
      const cMap = {};
      const customers = Array.isArray(customersRes.data) ? customersRes.data
        : (customersRes.data?.items || customersRes.data?.suppliers || []);
      for (const c of customers) {
        cMap[String(c.id)] = c.company_name || c.name || String(c.id);
      }
      setCustomerNames(cMap);

      // Markets
      const mMap = {};
      for (const m of (marketsRes.data || [])) {
        mMap[String(m.id)] = m.name || String(m.id);
      }
      setMarketNames(mMap);

      // Lanes: id → "source → destination" label
      const lMap = {};
      for (const l of (lanesRes.data || [])) {
        const src = sMap[String(l.source_id)] || sMap[l.source_name] || l.source_name || l.source_id;
        const dst = sMap[String(l.destination_id)] || sMap[l.destination_name] || l.destination_name || l.destination_id;
        lMap[String(l.id)] = `${src} \u2192 ${dst}`;
      }
      setLaneNames(lMap);
    } catch (err) {
      console.warn('Failed to load identifier lookups:', err?.message);
    }
  }, [isAuthenticated]);

  // Auto-load when user's default config is available
  useEffect(() => {
    const defaultConfig = user?.default_config_id;
    if (defaultConfig && isAuthenticated) {
      loadLookupsForConfig(defaultConfig);
    }
  }, [user?.default_config_id, isAuthenticated, loadLookupsForConfig]);

  // ── Resolver functions ────────────────────────────────────────────────
  const formatIdentifier = useCallback(
    (id, name) => {
      if (displayIdentifiers === 'id') return id != null ? String(id) : name || '';
      return name || (id != null ? String(id) : '');
    },
    [displayIdentifiers]
  );

  const formatProduct = useMemo(
    () => makeResolver(displayIdentifiers, productNames),
    [displayIdentifiers, productNames]
  );
  const formatSite = useMemo(
    () => makeResolver(displayIdentifiers, siteNames),
    [displayIdentifiers, siteNames]
  );
  const formatSupplier = useMemo(
    () => makeResolver(displayIdentifiers, supplierNames),
    [displayIdentifiers, supplierNames]
  );
  const formatCustomer = useMemo(
    () => makeResolver(displayIdentifiers, customerNames),
    [displayIdentifiers, customerNames]
  );
  const formatMarket = useMemo(
    () => makeResolver(displayIdentifiers, marketNames),
    [displayIdentifiers, marketNames]
  );
  const formatLane = useMemo(
    () => makeResolver(displayIdentifiers, laneNames),
    [displayIdentifiers, laneNames]
  );

  const value = useMemo(
    () => ({
      displayIdentifiers,
      loading,
      formatProduct,
      formatSite,
      formatSupplier,
      formatCustomer,
      formatMarket,
      formatLane,
      formatIdentifier,
      refresh: fetchPreferences,
      loadLookupsForConfig,
    }),
    [
      displayIdentifiers, loading,
      formatProduct, formatSite, formatSupplier, formatCustomer, formatMarket, formatLane,
      formatIdentifier, fetchPreferences, loadLookupsForConfig,
    ]
  );

  return (
    <DisplayPreferencesContext.Provider value={value}>
      {children}
    </DisplayPreferencesContext.Provider>
  );
}

export function useDisplayPreferences() {
  return useContext(DisplayPreferencesContext);
}

export default DisplayPreferencesContext;
