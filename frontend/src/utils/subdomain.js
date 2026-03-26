/**
 * Subdomain routing utilities for hybrid multi-tenant routing (Option C).
 *
 * The platform config is fetched once from /api/v1/config/client and cached.
 * When subdomain routing is enabled:
 *   - login.azirella.com → Login portal
 *   - autonomy.azirella.com → Default app (all tenants via JWT)
 *   - {slug}.azirella.com → Vanity subdomain per tenant
 */

let _configCache = null;
let _configPromise = null;

/**
 * Fetch and cache the platform config from the backend.
 * Safe to call multiple times — returns cached result.
 */
export async function getPlatformConfig() {
  if (_configCache) return _configCache;
  if (_configPromise) return _configPromise;

  _configPromise = fetch('/api/v1/config/client')
    .then(r => r.ok ? r.json() : null)
    .catch(() => null);

  _configCache = await _configPromise;
  _configPromise = null;
  return _configCache;
}

/**
 * Check if subdomain routing is enabled (synchronous, uses cache).
 * Returns false if config not yet loaded.
 */
export function isSubdomainRoutingEnabled() {
  return _configCache?.SUBDOMAIN_ROUTING_ENABLED === true;
}

/**
 * Extract the subdomain from the current hostname.
 * Returns null if no subdomain or routing not enabled.
 */
export function getCurrentSubdomain() {
  if (!_configCache?.SUBDOMAIN_ROUTING_ENABLED) return null;

  const host = window.location.hostname;
  const domain = _configCache.APP_DOMAIN;
  const suffix = `.${domain}`;

  if (!host.endsWith(suffix)) return null;
  const prefix = host.slice(0, -suffix.length);
  return prefix || null;
}

/**
 * Build the full URL for a tenant's vanity subdomain.
 * @param {string} slug - Tenant slug (e.g., "acme")
 * @param {string} [path="/"] - Path to append
 * @returns {string} Full URL (e.g., "https://acme.azirella.com/dashboard")
 */
export function buildTenantUrl(slug, path = '/') {
  if (!_configCache) return path; // Fallback to relative path

  const { APP_SCHEME, APP_DOMAIN, APP_PORT } = _configCache;
  const port = APP_PORT ? `:${APP_PORT}` : '';
  return `${APP_SCHEME}://${slug}.${APP_DOMAIN}${port}${path}`;
}

/**
 * Build the login portal URL, optionally with a redirect parameter.
 * @param {string} [redirectUrl] - URL to redirect to after login
 * @returns {string} Login portal URL
 */
export function buildLoginUrl(redirectUrl) {
  if (!_configCache?.SUBDOMAIN_ROUTING_ENABLED) return '/login';

  const { APP_SCHEME, APP_DOMAIN, APP_PORT, LOGIN_SUBDOMAIN } = _configCache;
  const port = APP_PORT ? `:${APP_PORT}` : '';
  const base = `${APP_SCHEME}://${LOGIN_SUBDOMAIN}.${APP_DOMAIN}${port}/login`;

  if (redirectUrl) {
    return `${base}?redirect=${encodeURIComponent(redirectUrl)}`;
  }
  return base;
}

/**
 * After login, redirect to the tenant's vanity subdomain if needed.
 * @param {string} tenantSubdomain - Tenant slug from login response
 * @param {string} [defaultPath="/"] - Path to land on after redirect
 * @returns {boolean} true if redirecting (caller should stop), false if no redirect needed
 */
export function redirectToTenantSubdomain(tenantSubdomain, defaultPath = '/') {
  if (!_configCache?.SUBDOMAIN_ROUTING_ENABLED || !tenantSubdomain) return false;

  const currentHost = window.location.hostname;
  const expectedHost = `${tenantSubdomain}.${_configCache.APP_DOMAIN}`;

  // Already on the correct subdomain
  if (currentHost === expectedHost) return false;

  // Redirect — cookie is set on .azirella.com so it'll carry over
  window.location.href = buildTenantUrl(tenantSubdomain, defaultPath);
  return true;
}
