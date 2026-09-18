import axios from 'axios';

function normaliseBaseUrl(value) {
  return String(value || '').trim().replace(/\/+$/, '');
}

function localBrowserHostname() {
  if (typeof window === 'undefined') return null;
  const hostname = window.location.hostname;
  return hostname === 'localhost' || hostname === '127.0.0.1' ? hostname : null;
}

function resolveApiBaseUrl() {
  // Production always uses the Vercel same-origin /api proxy to Railway.
  const hostname = localBrowserHostname();
  if (!hostname) return '/api';

  const configuredUrl = normaliseBaseUrl(
    import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL
  );

  // An explicitly configured same-origin /api proxy is supported in Vite.
  if (configuredUrl === '/api' || configuredUrl.startsWith('/api/')) {
    return configuredUrl;
  }

  // Only allow a local API override on the SAME hostname as Vite. This avoids
  // sending local test logins to a Railway production URL and avoids the
  // localhost/127.0.0.1 cookie mismatch (SameSite=Lax).
  if (configuredUrl) {
    try {
      const configured = new URL(configuredUrl);
      if (
        ['http:', 'https:'].includes(configured.protocol) &&
        configured.hostname === hostname
      ) {
        return configuredUrl;
      }
    } catch {
      // An invalid override cannot redirect development authentication.
    }
  }

  return `http://${hostname}:5000/api`;
}

export const API_BASE_URL = resolveApiBaseUrl();

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
  // Flask uses a signed, HttpOnly session cookie. Include it with API requests.
  withCredentials: true,
  // Do not force Content-Type: uploads need Axios/the browser to create the
  // multipart/form-data boundary when the payload is FormData.
});

// Never use localStorage for the authenticated user, cookie or CSRF token.
// Flask's /auth/csrf, /auth/login and /auth/me return the CSRF token in JSON.
let csrfToken = null;
let csrfBootstrapPromise = null;

function requestPath(config) {
  return String(config?.url || '').split('?')[0].replace(/\/+$/, '');
}

function rememberAuthResponse(response) {
  const path = requestPath(response.config);

  if (
    path.endsWith('/auth/csrf') ||
    path.endsWith('/auth/login') ||
    path.endsWith('/auth/me')
  ) {
    const nextToken = response.data?.csrf_token;
    if (typeof nextToken === 'string' && nextToken) {
      // A successful login issues a new session AND a new token.
      csrfToken = nextToken;
    } else if (path.endsWith('/auth/login') || path.endsWith('/auth/me')) {
      // Do not keep a token from a previous authenticated session.
      csrfToken = null;
    }
  } else if (path.endsWith('/auth/logout')) {
    csrfToken = null;
  }

  return response;
}

// Register/login/forgot-password/reset-password ALSO require CSRF in the
// updated backend. Bootstrap a token without requiring authentication first.
// Sharing this promise prevents simultaneous requests from racing to create
// multiple independent CSRF initialization requests.
async function ensureCsrfToken() {
  if (csrfToken) return csrfToken;

  if (!csrfBootstrapPromise) {
    csrfBootstrapPromise = api.get('/auth/csrf')
      .then((response) => {
        const token = response.data?.csrf_token;
        if (typeof token !== 'string' || !token) {
          throw new Error('Unable to initialize the security token. Please refresh the page and try again.');
        }
        csrfToken = token;
        return token;
      })
      .finally(() => {
        csrfBootstrapPromise = null;
      });
  }

  return csrfBootstrapPromise;
}

api.interceptors.request.use(async (config) => {
  const method = String(config.method || 'get').toUpperCase();
  if (!['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    return config;
  }

  // Do not silently send a write without its token. This covers both public
  // auth mutations and private endpoints, including logout and file uploads.
  const token = await ensureCsrfToken();
  if (typeof config.headers?.set === 'function') {
    config.headers.set('X-CSRF-Token', token);
  } else {
    config.headers = { ...config.headers, 'X-CSRF-Token': token };
  }
  return config;
});

api.interceptors.response.use(rememberAuthResponse, (error) => {
  const code = error.response?.data?.code;
  if (
    error.response?.status === 401 ||
    code === 'SESSION_EXPIRED' ||
    code === 'AUTH_REQUIRED' ||
    code === 'ACCOUNT_INACTIVE' ||
    code === 'CSRF_INVALID'
  ) {
    // Never retry failed writes automatically (they may not be idempotent).
    // A later request can obtain a fresh CSRF token from GET /auth/csrf.
    csrfToken = null;
  }
  return Promise.reject(error);
});

export default api;
