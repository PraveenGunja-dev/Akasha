import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { ReactNode } from 'react';

interface User {
  id: number;
  username: string;
  display_name: string;
  role: string;
  email: string;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<{ success: boolean; message: string }>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);
const API = '/akasha/api/auth';

// Storage can be unavailable (private window, blocked site data): every
// access is guarded, and without it the session simply lasts the tab.
const store = {
  get: (k: string) => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k: string, v: string) => { try { localStorage.setItem(k, v); } catch { /* tab-only session */ } },
  del: (k: string) => { try { localStorage.removeItem(k); } catch { /* nothing stored */ } },
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const clear = useCallback(() => {
    setUser(null);
    setToken(null);
    store.del('akasha_user');
    store.del('akasha_token');
  }, []);

  // Restore the session, then confirm it with the server: a token from a
  // signed-out or expired session must not keep the dashboards open.
  useEffect(() => {
    const savedToken = store.get('akasha_token');
    const savedUser = store.get('akasha_user');
    if (!savedToken) { setIsLoading(false); return; }
    if (savedUser) { try { setUser(JSON.parse(savedUser)); } catch { /* re-read below */ } }
    setToken(savedToken);
    fetch(`${API}/me`, { headers: { Authorization: `Bearer ${savedToken}` } })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((d: { user: User }) => { setUser(d.user); store.set('akasha_user', JSON.stringify(d.user)); })
      .catch((status) => { if (status === 401) clear(); })   // offline: keep the local session
      .finally(() => setIsLoading(false));
  }, [clear]);

  const login = async (username: string, password: string): Promise<{ success: boolean; message: string }> => {
    try {
      const res = await fetch(`${API}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) return { success: false, message: data.detail || 'Sign-in failed. Please try again.' };
      setUser(data.user);
      setToken(data.token);
      store.set('akasha_user', JSON.stringify(data.user));
      store.set('akasha_token', data.token);
      return { success: true, message: data.message };
    } catch {
      return { success: false, message: 'Cannot reach the server. Check your connection and try again.' };
    }
  };

  const logout = () => {
    const t = token;
    clear();
    if (t) fetch(`${API}/logout`, { method: 'POST', headers: { Authorization: `Bearer ${t}` } }).catch(() => {});
  };

  return (
    <AuthContext.Provider value={{ user, token, isAuthenticated: !!user && !!token, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within an AuthProvider');
  return context;
}
