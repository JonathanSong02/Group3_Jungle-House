import axios from 'axios';

const api = axios.create({
  baseURL:
    import.meta.env.VITE_API_URL ||
    'https://group3jungle-house-production.up.railway.app/api',
  timeout: 15000,
});

export default api;