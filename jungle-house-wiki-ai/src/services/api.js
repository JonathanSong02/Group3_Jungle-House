import axios from 'axios';

const api = axios.create({
  baseURL: 'https://group3jungle-house-production.up.railway.app/api',
  timeout: 10000,
});

export default api;