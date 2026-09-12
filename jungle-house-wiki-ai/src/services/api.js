import axios from 'axios';

const PRODUCTION_API_BASE_URL =
  'https://group3jungle-house-production.up.railway.app/api';
const LOCAL_API_BASE_URL = 'http://127.0.0.1:5000/api';

function normaliseBaseUrl(value) {
  return String(value || '').trim().replace(/\/+$/, '');
}

function isLocalUrl(value) {
  try {
    const parsed = new URL(value);
    return parsed.hostname === '127.0.0.1' || parsed.hostname === 'localhost';
  } catch {
    return false;
  }
}

function resolveApiBaseUrl() {
  const configured = normaliseBaseUrl(
    import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL
  );

  // Local development may intentionally use Flask on port 5000.
  const browserIsLocal =
    typeof window !== 'undefined' &&
    (window.location.hostname === 'localhost' ||
      window.location.hostname === '127.0.0.1');

  if (browserIsLocal) {
    return configured || LOCAL_API_BASE_URL;
  }

  // Safety guard for production builds: never let a Vercel deployment try
  // to call the visitor's own 127.0.0.1/localhost because that becomes an
  // Axios "Network Error" in the browser.
  if (!configured || isLocalUrl(configured)) {
    return PRODUCTION_API_BASE_URL;
  }

  return configured;
}

export const API_BASE_URL = resolveApiBaseUrl();

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json',
  },
});

export default api;
