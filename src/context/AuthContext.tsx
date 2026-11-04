import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import * as authApi from '../services/auth';
import { SESSION_EXPIRED_EVENT, tokens } from '../services/http';
import type { User } from '../types/api';

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(!!tokens.access());

  useEffect(() => {
    if (!tokens.access()) return;
    authApi
      .getCurrentUser()
      .then((res) => setUser(res.data))
      .catch(() => {
        tokens.clear();
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const onExpired = () => setUser(null);
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await authApi.login(email, password);
    tokens.set(res.data.access_token, res.data.refresh_token);
    setUser(res.data.user);
  }, []);

  const logout = useCallback(async () => {
    const refresh = tokens.refresh();
    // Blacklist the refresh token first (it needs the access token), then clear locally whatever happens.
    if (refresh) await authApi.logout(refresh).catch(() => undefined);
    tokens.clear();
    setUser(null);
  }, []);

  const value = useMemo(() => ({ user, loading, login, logout }), [user, loading, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
