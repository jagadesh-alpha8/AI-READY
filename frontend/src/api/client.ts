import axios from 'axios';

export const ACCESS_TOKEN_KEY = 'aios_token';
export const REFRESH_TOKEN_KEY = 'aios_refresh_token';

const api = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(ACCESS_TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

function clearSessionAndRedirect() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  if (window.location.pathname !== '/login') {
    window.location.href = '/login';
  }
}

// Silent-refresh-on-401: a plain (interceptor-free) axios instance is used
// for the refresh call itself so it never recurses back into this same
// response interceptor, and so a stale access token from the request
// interceptor above never gets attached to it.
const refreshClient = axios.create({ baseURL: '/api/v1' });

let refreshInFlight: Promise<string | null> | null = null;

function refreshAccessToken(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;

  const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
  if (!refreshToken) return Promise.resolve(null);

  refreshInFlight = refreshClient
    .post('/auth/refresh', { refresh: refreshToken })
    .then((res) => {
      const newAccessToken = res.data.access as string;
      localStorage.setItem(ACCESS_TOKEN_KEY, newAccessToken);
      return newAccessToken;
    })
    .catch(() => null)
    .finally(() => {
      refreshInFlight = null;
    });

  return refreshInFlight;
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    const isAuthCall = originalRequest?.url === '/auth/login' || originalRequest?.url === '/auth/refresh';

    if (error.response?.status !== 401 || isAuthCall || originalRequest?._retried) {
      return Promise.reject(error);
    }

    originalRequest._retried = true;
    const newAccessToken = await refreshAccessToken();
    if (!newAccessToken) {
      clearSessionAndRedirect();
      return Promise.reject(error);
    }

    originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
    return api(originalRequest);
  },
);

export default api;
