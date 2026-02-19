import { buildLoginRedirectPath } from './authUtils';

// Save the original fetch
const nativeFetch = window.fetch;

// Override the global fetch with safer defaults (no token leakage, minimal logging)
window.fetch = async function(input, init = {}) {
  const url = typeof input === 'string' ? input : input.url;
  const options = typeof input === 'string' ? init : input;
  const headers = new Headers(options.headers || {});
  const isAuth = /\/api\/v1\/auth\//.test(url);

  // Ensure cookies are sent for API calls. We default to 'include' so that
  // cross-origin requests (e.g. different ports during local development)
  // still include authentication cookies.
  const credentials = options.credentials || 'include';

  try {
    const response = await nativeFetch(input, { ...options, headers, credentials });

    // Redirect to login on 401 for non-auth endpoints
    // Avoid redirect loops if we're already on the login page
    const isLoginPage = window.location.pathname.startsWith('/login');
    if (response.status === 401 && !isAuth && !isLoginPage) {
      const loginPath = buildLoginRedirectPath({
        pathname: window.location.pathname,
        search: window.location.search,
      });
      window.location.replace(loginPath);
      return new Response(null, { status: 401, statusText: 'Unauthorized' });
    }

    return response;
  } catch (error) {
    // Keep logging minimal to avoid leaking sensitive data
    console.error('[Fetch Error]', error?.message || error);
    throw error;
  }
};

export default window.fetch;
