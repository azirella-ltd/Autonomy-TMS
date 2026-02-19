// /frontend/src/config/api.ts
// Single source of truth for the API base URL used by axios.

// Defaults suitable for production (proxy on 8088)
const DEFAULT_ORIGIN = '';
const DEFAULT_BASE_PATH = '/api/v1';

// Helper: safely read env for CRA and Vite
const readEnv = (key: string): string | undefined => {
  // CRA style
  if (typeof process !== 'undefined' && process.env) {
    const cra = process.env[`REACT_APP_${key}`];
    if (cra !== undefined) return cra;
  }
  // Vite style
  if (typeof import.meta !== 'undefined' && (import.meta as any).env) {
    const vite = (import.meta as any).env[`VITE_${key}`];
    if (vite !== undefined) return vite;
  }
  return undefined;
};

// Prefer explicit BASE_URL if provided (absolute or relative)
const explicitBaseUrl = readEnv('API_BASE_URL');

// Otherwise, allow providing ORIGIN and BASE_PATH separately
const origin = (readEnv('API_ORIGIN') || DEFAULT_ORIGIN).replace(/\/+$/, '');
const basePathRaw = readEnv('API_BASE_PATH') || DEFAULT_BASE_PATH;
const basePath = basePathRaw.startsWith('/') ? basePathRaw : `/${basePathRaw}`;

// Export final base URL
// - If explicitBaseUrl is set, use it as-is (supports relative '/api/v1' or absolute 'http://host:port/api/v1')
// - Else, construct from origin + basePath (defaults to http://localhost:8000/api/v1)
export const API_BASE_URL: string = explicitBaseUrl ?? `${origin}${basePath}`;

// Convenience named exports (optional)
export const API_ORIGIN: string = origin;
export const API_BASE_PATH: string = basePath;
