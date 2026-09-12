import axios from 'axios';

const LOCAL_API_BASE_URL = 'http://127.0.0.1:5000/api';

function normaliseBaseUrl(value) {
  return String(value || '').trim().replace(/\/+$/, '');
}

function browserIsLocal() {
  return (
    typeof window !== 'undefined' &&
    (window.location.hostname === 'localhost' ||
      window.location.hostname === '127.0.0.1')
  );
}

function resolveApiBaseUrl() {
  // Production deliberately uses a SAME-ORIGIN path. Vercel proxies /api/*
  // to Railway through vercel.json, so an old/mistyped Vercel environment
  // variable can no longer send the browser to localhost or the wrong host.
  if (!browserIsLocal()) {
    return '/api';
  }

  return (
    normaliseBaseUrl(
      import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL
    ) || LOCAL_API_BASE_URL
  );
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
