import { Capacitor } from '@capacitor/core';

const PRODUCTION_API = 'https://solution.smarbiz.sbs/api';
const DEVELOPMENT_API = 'http://localhost:8000/api';
const DEFAULT_API = Capacitor.isNativePlatform() ? PRODUCTION_API : DEVELOPMENT_API;
const API = (import.meta.env.VITE_API_URL || DEFAULT_API).replace(/\/$/, '');

export type User = {
  id: string;
  email: string;
  name: string;
  first_name: string;
  last_name: string;
  role: 'admin' | 'manager' | 'worker' | 'client';
  phone: string;
};

const accessToken = () => localStorage.getItem('access') || '';
const refreshToken = () => localStorage.getItem('refresh') || '';
let refreshPromise: Promise<string | null> | null = null;

async function request(url: string, options: RequestInit): Promise<Response> {
  try {
    return await fetch(url, options);
  } catch {
    throw new Error('Verbindung zum A+ Server konnte nicht hergestellt werden. Bitte Internetverbindung prüfen und erneut versuchen.');
  }
}

async function refreshAccessToken(): Promise<string | null> {
  if (!refreshToken()) return null;
  if (!refreshPromise) {
    refreshPromise = request(`${API}/auth/refresh/`, {
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
  const response = await request(`${API}/${normalizedPath}`, {
    ...options,
    headers: headers(options),
  });
  if (response.status === 401 && retry && !normalizedPath.startsWith('auth/login') && !normalizedPath.startsWith('auth/refresh')) {
    const token = await refreshAccessToken();
    if (token) {
      const retried = await request(`${API}/${normalizedPath}`, { ...options, headers: headers(options, token) });
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

export async function login(email: string, password: string) {
  const data: any = await api('auth/login/', {
    method: 'POST',
    body: JSON.stringify({ email: email.trim().toLowerCase(), password }),
  });
  localStorage.setItem('access', data.access);
  localStorage.setItem('refresh', data.refresh);
  return data.user as User;
}

export const me = () => api<User>('auth/me/');
// Do not send a user-controlled target URL. The backend already knows the canonical
// application callback URL. Keeping the OAuth start URL free of nested URLs also
// avoids edge/WAF false positives on the production domain.
export const socialUrl = (provider: 'google' | 'apple') => `${API}/auth/oauth/${provider}/start/`;

export function consumeOAuth() {
  const params = new URLSearchParams(location.search);
  const access = params.get('access');
  const refresh = params.get('refresh');
  const oauthError = params.get('error');

  if (access && refresh) {
    localStorage.setItem('access', access);
    localStorage.setItem('refresh', refresh);
    history.replaceState({}, '', '/');
    return true;
  }

  if (oauthError) {
    // The backend redirects failed social sign-ins back to the SPA. Previously the
    // query parameter was silently ignored, making a real OAuth error look like a
    // no-op. Surface it immediately and clean the URL so a refresh does not repeat it.
    history.replaceState({}, '', '/');
    window.setTimeout(() => window.alert(`Google/Apple Login: ${oauthError}`), 0);
  }

  return false;
}

export function logout() {
  localStorage.clear();
  location.href = '/';
}
