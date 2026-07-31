// Dashboard data is invalidated by sync, identity, scope URL, or page lifecycle.
// Avoid time-based expiry so revisiting a pane never causes a surprise reload.
const DEFAULT_TTL_MS = Number.POSITIVE_INFINITY;

type CacheEntry = {
  expiresAt: number;
  value: unknown;
};

const responseCache = new Map<string, CacheEntry>();
const pendingRequests = new Map<string, Promise<unknown>>();

export async function getCachedDashboardJson<T>(
  url: string,
  options: { force?: boolean; ttlMs?: number } = {},
): Promise<T> {
  const now = Date.now();
  const cached = responseCache.get(url);
  if (!options.force && cached && cached.expiresAt > now) {
    return cached.value as T;
  }

  if (!options.force) {
    const pending = pendingRequests.get(url);
    if (pending) return pending as Promise<T>;
  }

  const request = fetch(url)
    .then(async response => {
      if (!response.ok) throw new Error(`${url} failed with HTTP ${response.status}`);
      return response.json() as Promise<T>;
    })
    .then(value => {
      responseCache.set(url, {
        value,
        expiresAt: Date.now() + (options.ttlMs ?? DEFAULT_TTL_MS),
      });
      return value;
    })
    .finally(() => pendingRequests.delete(url));

  pendingRequests.set(url, request);
  return request;
}

export function clearDashboardQueryCache(urlPrefix?: string) {
  if (!urlPrefix) {
    responseCache.clear();
    pendingRequests.clear();
    return;
  }
  for (const url of responseCache.keys()) {
    if (url.startsWith(urlPrefix)) responseCache.delete(url);
  }
}
