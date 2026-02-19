import axios from 'axios';

const normaliseBaseUrl = (value) => {
  if (!value) {
    return undefined;
  }

  const trimmed = value.trim();
  if (!trimmed) {
    return undefined;
  }

  if (trimmed === '/') {
    return '/';
  }

  // Collapse duplicate trailing slashes but keep a single leading slash for relative paths.
  return trimmed.replace(/\/+$/, '');
};

const rawBaseUrl =
  normaliseBaseUrl(process.env.REACT_APP_API_URL) ||
  normaliseBaseUrl(process.env.REACT_APP_API_BASE_URL) ||
  normaliseBaseUrl(process.env.VITE_API_BASE_URL) ||
  '/api';

const api = axios.create({
  baseURL: rawBaseUrl,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add a response interceptor
api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error);
    return Promise.reject(error);
  }
);

export const testConnection = async () => {
  try {
    const response = await api.get('/health');
    return response.data;
  } catch (error) {
    console.error('Connection test failed:', error);
    throw error;
  }
};

export default api;
