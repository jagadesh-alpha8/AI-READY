import React, { createContext, useContext, useState, useEffect } from 'react';
import { ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY } from '../api/client';
import * as authApi from '../api/auth';
import type { User } from '../types';

export type { User };

interface AuthContextType {
  user: User | null;
  token: string | null;
  login: (email: string, password?: string) => Promise<void>;
  logout: () => void;
  loading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(localStorage.getItem(ACCESS_TOKEN_KEY));
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    if (token) {
      authApi
        .getCurrentUser()
        .then((res) => setUser(res.data))
        .catch(() => clearSession())
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const login = async (email: string, password = 'Password123!') => {
    const response = await authApi.login(email, password);
    const { access_token, refresh_token, user: userData } = response.data;
    localStorage.setItem(ACCESS_TOKEN_KEY, access_token);
    localStorage.setItem(REFRESH_TOKEN_KEY, refresh_token);
    setToken(access_token);
    setUser(userData);
  };

  const clearSession = () => {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    setToken(null);
    setUser(null);
  };

  const logout = () => {
    const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
    // Best-effort: blacklist the refresh token server-side, but don't let a
    // network failure block signing the user out locally. Clearing the
    // session only *after* this settles (not before) matters: axios's
    // interceptors run on a microtask, so clearing the access token first
    // would race it out from under the outgoing request's Authorization
    // header, and the logout call would 401 before it ever reaches the
    // blacklist logic.
    const request = refreshToken ? authApi.logout(refreshToken).catch(() => {}) : Promise.resolve();
    request.finally(() => clearSession());
  };

  return (
    <AuthContext.Provider value={{ user, token, login, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
