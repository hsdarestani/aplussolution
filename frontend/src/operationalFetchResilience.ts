const PATCH_FLAG = Symbol.for('aplus.operational-fetch-resilience');
const CACHE_PREFIX = 'aplus:ops-cache:';

type FallbackFactory = () => unknown;

type OptionalEndpoint = {
  matches: (url: URL) => boolean;
  fallback: FallbackFactory;
};

const optionalEndpoints: OptionalEndpoint[] = [
  { matches: (url) => url.pathname.endsWith('/api/operations/folders/'), fallback: () => ({ workers: [], clients: [] }) },
  { matches: (url) => url.pathname.endsWith('/api/integrations/wiw/status/'), fallback: () => ({ configured: false, migration_only: true, latest_sync: null }) },
  { matches: (url) => url.pathname.endsWith('/api/document-catalog/'), fallback: () => ({ count: 8, documents: [], complete: false, recovery: {} }) },
  { matches: (url) => url.pathname.endsWith('/api/automation/orders/packages/'), fallback: () => [] },
  { matches: (url) => url.pathname.endsWith('/api/working-time/settings/'), fallback: () => ({ employees: [] }) },
  { matches: (url) => url.pathname.endsWith('/api/working-time/records/'), fallback: () => [] },
  {
    matches: (url) => url.pathname.endsWith('/api/shifts/') && url.searchParams.get('status') === 'draft',
    fallback: () => ({ results: [] }),
  },
];

function endpointFor(url: URL) {
  return optionalEndpoints.find((entry) => entry.matches(url));
}

function cacheKey(url: URL) {
  return `${CACHE_PREFIX}${url.pathname}${url.search}`;
}

function syntheticJson(data: unknown) {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
      'X-Aplus-Degraded': '1',
    },
  });
}

function cachedValue(url: URL): unknown | undefined {
  try {
    const raw = sessionStorage.getItem(cacheKey(url));
    return raw == null ? undefined : JSON.parse(raw);
  } catch {
    return undefined;
  }
}

async function cacheSuccessfulJson(url: URL, response: Response) {
  try {
    const clone = response.clone();
    const body = await clone.text();
    if (!body) return;
    JSON.parse(body);
    sessionStorage.setItem(cacheKey(url), body);
  } catch {
    // Cache failures must never affect the real response.
  }
}

function announce(type: 'aplus-api-degraded' | 'aplus-api-recovered', url: URL, cached = false) {
  window.dispatchEvent(new CustomEvent(type, {
    detail: { path: `${url.pathname}${url.search}`, cached },
  }));
}

export function installOperationalFetchResilience() {
  const marker = window as Window & Record<PropertyKey, unknown>;
  if (marker[PATCH_FLAG]) return;
  const originalFetch = window.fetch.bind(window);
  const degradedPaths = new Set<string>();

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const method = String(init?.method || (input instanceof Request ? input.method : 'GET')).toUpperCase();
    const rawUrl = input instanceof Request ? input.url : String(input);
    let url: URL;
    try {
      url = new URL(rawUrl, window.location.origin);
    } catch {
      return originalFetch(input, init);
    }
    const endpoint = method === 'GET' ? endpointFor(url) : undefined;
    if (!endpoint) return originalFetch(input, init);

    const path = `${url.pathname}${url.search}`;
    try {
      const response = await originalFetch(input, init);
      if (response.ok) {
        await cacheSuccessfulJson(url, response);
        if (degradedPaths.delete(path)) announce('aplus-api-recovered', url);
        return response;
      }
      // Authentication/permission failures must keep their normal behavior so the
      // token refresh and role guards in api.ts still work correctly.
      if (response.status === 401 || response.status === 403 || response.status === 404) return response;
    } catch {
      // Network failures for non-critical Steuerzentrale data fall through to a
      // cached or neutral response. The UI receives a visible degraded-state event.
    }

    const cached = cachedValue(url);
    degradedPaths.add(path);
    announce('aplus-api-degraded', url, cached !== undefined);
    return syntheticJson(cached !== undefined ? cached : endpoint.fallback());
  };

  Object.defineProperty(marker, PATCH_FLAG, {
    configurable: false,
    enumerable: false,
    writable: false,
    value: true,
  });
}
