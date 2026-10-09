import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import type { ReactNode } from 'react';

/* Sign-in state for the whole app.

   The session lives in an HttpOnly cookie the server sets at sign-in, so no
   token is ever readable from script or kept in localStorage. Every same-origin
   fetch sends it automatically. /auth/me is the source of truth for who is
   signed in and what they can open; the server enforces the same rules on
   every API call, so this context only decides what to show. */

export interface DashboardRef {
  key: string;
  label: string;
  route: string;
  description: string;
}

export interface PortfolioAccess {
  /** True when the user sees every portfolio. */
  all: boolean;
  /** project_mapping clusters the user may select, e.g. "Solar Khavda". */
  clusters: string[];
  /** Portfolio APIs (CPAG packs) the user may open: 'solar' | 'wind' | 'bess'. */
  apis: string[];
}

export interface AuthUser {
  id: number;
  username: string;
  display_name: string;
  email: string;
  role: string;
  role_name: string;
  permissions: string[];
  dashboards: DashboardRef[];
  portfolio_access: PortfolioAccess;
  must_change_password: boolean;
  last_login_at: string | null;
}

interface AuthContextType {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<{ success: boolean; message: string; user?: AuthUser }>;
  logout: () => Promise<void>;
  refresh: () => Promise<AuthUser | null>;
  changePassword: (current: string, next: string) => Promise<{ success: boolean; message: string }>;
  can: (permission: string) => boolean;
  canAny: (permissions: string[]) => boolean;
  /** Where to send this user after sign-in, given where they were heading. */
  homeFor: (u: AuthUser, from?: string | null) => string;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);
const API = '/akasha/api/auth';

/** Route prefix -> the permission(s) that open it. Mirrors App.tsx. */
export const ROUTE_PERMISSIONS: [string, string[]][] = [
  ['/ceo-dashboard', ['dashboard.executive']],
  ['/wind-dashboard', ['dashboard.executive']],
  ['/pmag', ['dashboard.pmag']],
  ['/projects', ['dashboard.projects']],
  ['/tc-ordering', ['dashboard.tc_ordering']],
  ['/tc-stores', ['dashboard.tc_stores']],
  ['/admin', ['users.manage', 'roles.manage', 'audit.view', 'data.edit']],
];

export const ADMIN_PERMISSIONS = ['users.manage', 'roles.manage', 'audit.view'];

function allowedPath(u: AuthUser, path: string): boolean {
  const rule = ROUTE_PERMISSIONS.find(([prefix]) => path === prefix || path.startsWith(prefix + '/') || path.startsWith(prefix + '?'));
  return !rule || rule[1].some(p => u.permissions.includes(p));
}

async function readJson(res: Response): Promise<any> {
  try { return await res.json(); } catch { return {}; }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const userRef = useRef<AuthUser | null>(null);
  userRef.current = user;

  const refresh = useCallback(async (): Promise<AuthUser | null> => {
    try {
      const res = await fetch(`${API}/me`, { credentials: 'same-origin' });
      if (!res.ok) { setUser(null); return null; }
      const d = await readJson(res);
      setUser(d.user);
      return d.user as AuthUser;
    } catch {
      // Offline: keep whatever we had; the next call will tell.
      return userRef.current;
    }
  }, []);

  useEffect(() => { refresh().finally(() => setIsLoading(false)); }, [refresh]);

  // A session can end while a screen is open: it times out, an administrator
  // ends it, or the role changes. Watch every API answer for that, so the user
  // is sent to sign-in instead of looking at screens that silently fail.
  useEffect(() => {
    const original = window.fetch;
    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (url.includes('/akasha/api/')) {
        // The screen this call is for, so the admin console's "Online now"
        // can show where each person is (stored on their session only).
        const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined));
        headers.set('X-Akasha-View', window.location.pathname.replace(/^\/akasha/, '') || '/');
        init = { ...init, headers };
      }
      const res = await original(input, init);
      if (url.includes('/akasha/api/') && !url.includes('/akasha/api/auth/') && userRef.current) {
        if (res.status === 401) setUser(null);
        else if (res.status === 403) {
          res.clone().json().then(b => { if (b?.code === 'password_change_required') refresh(); }).catch(() => {});
        }
      }
      return res;
    };
    return () => { window.fetch = original; };
  }, [refresh]);

  const login = async (username: string, password: string) => {
    try {
      const res = await fetch(`${API}/login`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const data = await readJson(res);
      if (!res.ok) return { success: false, message: data.detail || 'Sign-in failed. Please try again.' };
      setUser(data.user);
      return { success: true, message: data.message, user: data.user as AuthUser };
    } catch {
      return { success: false, message: 'Cannot reach the server. Check your connection and try again.' };
    }
  };

  const logout = async () => {
    try { await fetch(`${API}/logout`, { method: 'POST', credentials: 'same-origin' }); } catch { /* signed out locally */ }
    setUser(null);
  };

  const changePassword = async (current: string, next: string) => {
    try {
      const res = await fetch(`${API}/password`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_password: current, new_password: next }),
      });
      const data = await readJson(res);
      if (!res.ok) return { success: false, message: data.detail || 'Could not change the password.' };
      setUser(data.user);
      return { success: true, message: 'Password changed. Other devices have been signed out.' };
    } catch {
      return { success: false, message: 'Cannot reach the server. Check your connection and try again.' };
    }
  };

  const can = useCallback((p: string) => !!user?.permissions.includes(p), [user]);
  const canAny = useCallback((ps: string[]) => ps.some(p => !!user?.permissions.includes(p)), [user]);

  const homeFor = useCallback((u: AuthUser, from?: string | null) => {
    if (u.must_change_password) return '/account/password';
    if (from && from !== '/' && from !== '/login' && allowedPath(u, from)) return from;
    const adminOnly = u.dashboards.length === 0 && ADMIN_PERMISSIONS.some(p => u.permissions.includes(p));
    if (adminOnly) return '/admin';
    // One dashboard: straight in. Several: let the user choose.
    return u.dashboards.length === 1 ? u.dashboards[0].route : '/workspaces';
  }, []);

  return (
    <AuthContext.Provider value={{
      user, isAuthenticated: !!user, isLoading, login, logout, refresh, changePassword, can, canAny, homeFor,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within an AuthProvider');
  return context;
}
