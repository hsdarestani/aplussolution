const API = (import.meta.env.VITE_API_URL || 'http://localhost:8000/api').replace(/\/$/, '');

export type User = {
  id: string;
  email: string;
  name: string;
  first_name: string;
  last_name: string;
  role: 'admin' | 'manager' | 'worker' | 'client';
  phone: string;
  capabilities?: string[];
  access_scope?: {
    mode: 'all' | 'scoped' | 'self';
    role?: string;
    wage_visibility?: 'none' | 'scoped' | 'all';
    can_share_labor?: boolean;
    schedules?: string[];
    locations?: string[];
    workers?: string[];
  };
};

const accessToken = () => localStorage.getItem('access') || '';
const refreshToken = () => localStorage.getItem('refresh') || '';
let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (!refreshToken()) return null;
  if (!refreshPromise) {
    refreshPromise = fetch(`${API}/auth/refresh/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh: refreshToken() }),
    })
      .then(async (response) => {
        if (!response.ok) return null;
        const data = await response.json();
        if (!data.access) return null;
        localStorage.setItem('access', data.access);
        if (data.refresh) localStorage.setItem('refresh', data.refresh);
        return data.access as string;
      })
      .catch(() => null)
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

function headers(options: RequestInit, tokenOverride?: string) {
  const isForm = typeof FormData !== 'undefined' && options.body instanceof FormData;
  const token = tokenOverride ?? accessToken();
  return {
    ...(isForm ? {} : { 'Content-Type': 'application/json' }),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  };
}

async function parseError(response: Response) {
  let message = 'Ein Fehler ist aufgetreten.';
  try {
    const body = await response.json();
    message = body.detail || body.message || JSON.stringify(body);
  } catch {
    // Keep the generic localized message for non-JSON responses.
  }
  return message;
}

export async function api<T = any>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const normalizedPath = path.replace(/^\//, '');
  const response = await fetch(`${API}/${normalizedPath}`, {
    ...options,
    headers: headers(options),
  });
  if (response.status === 401 && retry && !normalizedPath.startsWith('auth/login') && !normalizedPath.startsWith('auth/refresh')) {
    const token = await refreshAccessToken();
    if (token) {
      const retried = await fetch(`${API}/${normalizedPath}`, { ...options, headers: headers(options, token) });
      if (retried.ok) return retried.status === 204 ? ({} as T) : retried.json();
      throw new Error(await parseError(retried));
    }
    localStorage.removeItem('access');
    localStorage.removeItem('refresh');
    window.dispatchEvent(new Event('auth-lost'));
  }
  if (!response.ok) throw new Error(await parseError(response));
  return response.status === 204 ? ({} as T) : response.json();
}

export async function apiAll<T = any>(path: string): Promise<T[]> {
  const rows: T[] = [];
  let page = 1;
  while (page <= 200) {
    const separator = path.includes('?') ? '&' : '?';
    const data: any = await api(`${path}${separator}page=${page}`);
    if (Array.isArray(data)) return data as T[];
    rows.push(...(data?.results || []));
    if (!data?.next) break;
    page += 1;
  }
  return rows;
}

export async function apiDownload(path: string, fallbackFilename = 'download') {
  const normalizedPath = path.replace(/^\//, '');
  async function request(token?: string) {
    return fetch(`${API}/${normalizedPath}`, { headers: headers({}, token) });
  }
  let response = await request();
  if (response.status === 401) {
    const token = await refreshAccessToken();
    if (token) response = await request(token);
  }
  if (!response.ok) throw new Error(await parseError(response));
  const blob = await response.blob();
  const disposition = response.headers.get('Content-Disposition') || '';
  const match = disposition.match(/filename="?([^";]+)"?/i);
  const filename = match?.[1] || fallbackFilename;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export async function login(email: string, password: string) {
  const data: any = await api('auth/login/', { method: 'POST', body: JSON.stringify({ email, password }) });
  localStorage.setItem('access', data.access);
  localStorage.setItem('refresh', data.refresh);
  return data.user as User;
}

export const me = () => api<User>('auth/me/');
export const socialUrl = (provider: 'google' | 'apple') => `${API}/auth/oauth/${provider}/start/?target=${encodeURIComponent(`${window.location.origin}/auth/callback`)}`;

export function consumeOAuth() {
  const params = new URLSearchParams(location.search);
  const access = params.get('access');
  const refresh = params.get('refresh');
  if (access && refresh) {
    localStorage.setItem('access', access);
    localStorage.setItem('refresh', refresh);
    history.replaceState({}, '', '/');
    return true;
  }
  return false;
}

export function logout() {
  localStorage.clear();
  location.href = '/';
}