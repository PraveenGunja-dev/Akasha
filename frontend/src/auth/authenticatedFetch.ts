type TokenProvider = () => Promise<string | null>;
type DevelopmentIdentityProvider = () => { userId: string; role: 'executive' | 'pmag' } | null;

let tokenProvider: TokenProvider = async () => null;
let unauthorizedHandler: (() => void) | null = null;
let developmentIdentityProvider: DevelopmentIdentityProvider = () => null;
let installed = false;

export function configureAuthenticatedFetch(
  provider: TokenProvider,
  onUnauthorized: () => void,
  getDevelopmentIdentity: DevelopmentIdentityProvider = () => null,
) {
  tokenProvider = provider;
  unauthorizedHandler = onUnauthorized;
  developmentIdentityProvider = getDevelopmentIdentity;
}

function isAkashaApiRequest(input: RequestInfo | URL): boolean {
  const rawUrl = input instanceof Request ? input.url : String(input);
  const url = new URL(rawUrl, window.location.origin);
  return url.origin === window.location.origin
    && (url.pathname.startsWith('/akasha/api/') || url.pathname.startsWith('/api/'));
}

export function installAuthenticatedFetch() {
  if (installed) return;
  installed = true;
  const nativeFetch = window.fetch.bind(window);

  window.fetch = async (input: RequestInfo | URL, init: RequestInit = {}) => {
    if (!isAkashaApiRequest(input)) return nativeFetch(input, init);

    const headers = new Headers(input instanceof Request ? input.headers : undefined);
    new Headers(init.headers).forEach((value, key) => headers.set(key, value));
    if (!headers.has('Authorization')) {
      const token = await tokenProvider();
      if (token) headers.set('Authorization', `Bearer ${token}`);
    }
    const developmentIdentity = developmentIdentityProvider();
    if (!headers.has('Authorization') && developmentIdentity) {
      headers.set('X-Akasha-Dev-User', developmentIdentity.userId);
      headers.set('X-Akasha-Dev-Role', developmentIdentity.role);
    }
    const response = await nativeFetch(input, { ...init, headers });
    if (response.status === 401) unauthorizedHandler?.();
    return response;
  };
}
