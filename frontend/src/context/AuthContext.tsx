import { createContext, useContext, useEffect, useState } from 'react';
import type { AccountInfo } from '@azure/msal-browser';
import type { ReactNode } from 'react';
import { configureAuthenticatedFetch } from '../auth/authenticatedFetch';
import {
  clearDevelopmentSession,
  getDevelopmentIdentity,
  startDevelopmentSession,
} from '../auth/developmentIdentity';
import { authMode, entraApiScopes, getMsalInstance, type AuthMode } from '../auth/msal';


export interface User {
  id: string;
  tenant_id: string;
  username: string;
  display_name: string;
  role: 'executive' | 'pmag';
  email: string;
  auth_mode?: AuthMode;
}

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  authMode: AuthMode;
  login: (role?: 'executive' | 'pmag') => Promise<{ success: boolean; message: string }>;
  logout: () => Promise<void>;
  getAccessToken: () => Promise<string | null>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);
async function acquireToken(account?: AccountInfo | null): Promise<string | null> {
  const instance = await getMsalInstance();
  const selectedAccount = account || instance.getActiveAccount() || instance.getAllAccounts()[0];
  if (!selectedAccount) return null;
  instance.setActiveAccount(selectedAccount);
  const result = await instance.acquireTokenSilent({ account: selectedAccount, scopes: entraApiScopes });
  return result.accessToken;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const getAccessToken = async () => {
    if (authMode === 'development') return null;
    try {
      return await acquireToken();
    } catch {
      setUser(null);
      return null;
    }
  };

  useEffect(() => {
    let active = true;
    localStorage.removeItem('akasha_user');
    localStorage.removeItem('akasha_token');
    configureAuthenticatedFetch(getAccessToken, () => setUser(null), getDevelopmentIdentity);
    const restore = async () => {
      try {
        if (authMode === 'development') {
          if (!getDevelopmentIdentity()) return;
          const response = await fetch('/akasha/api/auth/me');
          if (!response.ok) throw new Error('Unable to restore the development identity.');
          if (active) setUser({ ...(await response.json()), auth_mode: 'development' });
          return;
        }
        const instance = await getMsalInstance();
        const redirectResult = await instance.handleRedirectPromise();
        const account = redirectResult?.account || instance.getAllAccounts()[0];
        if (!account) return;
        instance.setActiveAccount(account);
        await acquireToken(account);
        const response = await fetch('/akasha/api/auth/me');
        if (!response.ok) throw new Error('Unable to validate the Akasha account.');
        if (active) setUser(await response.json());
      } catch (error) {
        console.error('Authentication restore failed:', error);
        if (active) setUser(null);
      } finally {
        if (active) setIsLoading(false);
      }
    };
    restore();
    return () => { active = false; };
  }, []);

  const login = async (role: 'executive' | 'pmag' = 'executive'): Promise<{ success: boolean; message: string }> => {
    setIsLoading(true);
    try {
      if (authMode === 'development') {
        startDevelopmentSession(role);
        const response = await fetch('/akasha/api/auth/me');
        if (!response.ok) throw new Error('Development login was rejected by the backend.');
        const developmentUser: User = { ...(await response.json()), auth_mode: 'development' };
        setUser(developmentUser);
        return { success: true, message: `Development access: ${developmentUser.display_name}.` };
      }
      const instance = await getMsalInstance();
      const result = await instance.loginPopup({ scopes: entraApiScopes, prompt: 'select_account' });
      instance.setActiveAccount(result.account);
      await acquireToken(result.account);
      const response = await fetch('/akasha/api/auth/me');
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || 'This account is not authorized for Akasha.');
      }
      const authenticatedUser: User = await response.json();
      setUser(authenticatedUser);
      return { success: true, message: `Welcome, ${authenticatedUser.display_name}.` };
    } catch (error) {
      setUser(null);
      return { success: false, message: error instanceof Error ? error.message : 'Microsoft sign-in failed.' };
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async () => {
    if (authMode === 'development') {
      clearDevelopmentSession();
      setUser(null);
      return;
    }
    const instance = await getMsalInstance();
    const account = instance.getActiveAccount();
    setUser(null);
    await instance.logoutPopup({ account, mainWindowRedirectUri: `${window.location.origin}/akasha/` });
  };

  return <AuthContext.Provider value={{ user, isAuthenticated: Boolean(user), isLoading, authMode, login, logout, getAccessToken }}>{children}</AuthContext.Provider>;
}

// Context and hook intentionally share this module so all existing consumers keep one import path.
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within an AuthProvider');
  return context;
}
