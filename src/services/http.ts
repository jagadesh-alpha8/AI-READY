import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { ACCESS_TOKEN_KEY, API_BASE_URL, REFRESH_TOKEN_KEY } from '../config/env';
import { storage } from '../utils/storage';

/**
 * The one HTTP client. Same contract as the existing frontend's client (backend/docs/API_CONTRACT.md):
 * JWT bearer from POST /auth/login, silent refresh through POST /auth/refresh on a 401.
 */
export const http = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

/** Fired when the session can no longer be refreshed; AuthContext listens and signs out. */
export const SESSION_EXPIRED_EVENT = 'aircampus:session-expired';

export const tokens = {
  access: () => storage.get(ACCESS_TOKEN_KEY),
  refresh: () => storage.get(REFRESH_TOKEN_KEY),
  set(access: string, refresh?: string) {
    storage.set(ACCESS_TOKEN_KEY, access);
    if (refresh) storage.set(REFRESH_TOKEN_KEY, refresh);
  },
  clear() {
    storage.remove(ACCESS_TOKEN_KEY);
    storage.remove(REFRESH_TOKEN_KEY);
  },
};

http.interceptors.request.use((config) => {
  const token = tokens.access();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  // FormData sets its own multipart boundary.
  if (config.data instanceof FormData) delete config.headers['Content-Type'];
  return config;
});

// Interceptor-free client for the refresh call, so it can never recurse into the 401 handler.
const refreshClient = axios.create({ baseURL: API_BASE_URL });
let refreshInFlight: Promise<string | null> | null = null;

function refreshAccessToken(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;
  const refresh = tokens.refresh();
  if (!refresh) return Promise.resolve(null);
  refreshInFlight = refreshClient
    .post<{ access: string }>('/auth/refresh', { refresh })
    .then((res) => {
      tokens.set(res.data.access);
      return res.data.access;
    })
    .catch(() => null)
    .finally(() => {
      refreshInFlight = null;
    });
  return refreshInFlight;
}

type RetriableConfig = InternalAxiosRequestConfig & { _retried?: boolean };

http.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as RetriableConfig | undefined;
    const isAuthCall = original?.url === '/auth/login' || original?.url === '/auth/refresh';
    if (error.response?.status !== 401 || !original || isAuthCall || original._retried) {
      return Promise.reject(error);
    }
    original._retried = true;
    const access = await refreshAccessToken();
    if (!access) {
      tokens.clear();
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
      return Promise.reject(error);
    }
    original.headers.Authorization = `Bearer ${access}`;
    return http(original);
  },
);

/** Save a blob response (authenticated downloads: a plain link would not carry the bearer token). */
export function saveBlob(data: Blob, filename: string) {
  const url = URL.createObjectURL(data);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
