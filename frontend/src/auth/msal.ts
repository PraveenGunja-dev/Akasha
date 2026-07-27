import { PublicClientApplication, type Configuration } from '@azure/msal-browser';


const clientId = import.meta.env.VITE_ENTRA_CLIENT_ID?.trim();
const tenantId = import.meta.env.VITE_ENTRA_TENANT_ID?.trim();

export type AuthMode = 'development' | 'entra';
export const authMode: AuthMode = import.meta.env.VITE_AUTH_MODE === 'entra'
  ? 'entra'
  : 'development';

export const entraApiScopes = [
  import.meta.env.VITE_ENTRA_API_SCOPE?.trim() || `api://${clientId || 'missing-client-id'}/access_as_user`,
];

let instancePromise: Promise<PublicClientApplication> | null = null;

export function getMsalInstance(): Promise<PublicClientApplication> {
  if (!clientId || !tenantId) {
    return Promise.reject(new Error('Microsoft Entra frontend configuration is missing.'));
  }
  if (!instancePromise) {
    const config: Configuration = {
      auth: {
        clientId,
        authority: `https://login.microsoftonline.com/${tenantId}`,
        redirectUri: `${window.location.origin}/akasha/`,
        postLogoutRedirectUri: `${window.location.origin}/akasha/`,
      },
      cache: { cacheLocation: 'sessionStorage' },
    };
    const instance = new PublicClientApplication(config);
    instancePromise = instance.initialize().then(() => instance);
  }
  return instancePromise;
}
