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

function showOAuthError(message: string) {
  const existing = document.getElementById('oauth-error-banner');
  if (existing) existing.remove();
  const banner = document.createElement('div');
  banner.id = 'oauth-error-banner';
  banner.setAttribute('role', 'alert');
  banner.style.cssText = [
    'position:fixed',
    'z-index:2147483647',
    'left:16px',
    'right:16px',
    'top:16px',
    'max-width:720px',
    'margin:0 auto',
    'padding:14px 16px',
    'border-radius:12px',
    'background:#fff',
    'color:#8b1e1e',
    'border:1px solid #efb7b7',
    'box-shadow:0 12px 36px rgba(0,0,0,.18)',
    'font:600 14px/1.45 system-ui,-apple-system,sans-serif',
  ].join(';');
  banner.textContent = `Google/Apple Login: ${message}`;
  document.body.appendChild(banner);
}

export function consumeOAuth() {
  const params = new URLSearchParams(location.search);
  const access = params.get('access');
  const refresh = params.get('refresh');
  const oauthError = params.get('oauth_error') || params.get('error');

  if (access && refresh) {
    localStorage.setItem('access', access);
    localStorage.setItem('refresh', refresh);
    history.replaceState({}, '', '/');
    return true;
  }

  if (oauthError) {
    // Navigation-triggered alert() is unreliable on mobile browsers. Render a
    // persistent DOM banner instead, then remove sensitive/noisy query text.
    history.replaceState({}, '', '/');
    window.setTimeout(() => showOAuthError(oauthError), 0);
  }
  return false;
}

export function logout() {
  localStorage.clear();
  location.href = '/';
}
