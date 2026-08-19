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

function currentCoordinates(): Promise<{ latitude: number; longitude: number; accuracy: number }> {
  if (typeof navigator === 'undefined' || !navigator.geolocation) {
    return Promise.reject(new Error('Dieses Gerät unterstützt keine Standortbestimmung.'));
  }
  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(
      (position) => resolve({
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
        accuracy: position.coords.accuracy,
      }),
      (error) => {
        if (error.code === error.PERMISSION_DENIED) {
          reject(new Error('Standortzugriff wurde nicht erlaubt. Bitte die Standortfreigabe für A+ Solution aktivieren.'));
          return;
        }
        if (error.code === error.TIMEOUT) {
          reject(new Error('Der aktuelle Standort konnte nicht rechtzeitig bestimmt werden. Bitte GPS aktivieren und erneut versuchen.'));
          return;
        }
        reject(new Error('Der aktuelle Standort konnte nicht bestimmt werden. Bitte GPS und Standortdienste prüfen.'));
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    );
  });
}

async function prepareOptions(normalizedPath: string, options: RequestInit): Promise<RequestInit> {
  const method = String(options.method || 'GET').toUpperCase();
  if (normalizedPath !== 'locations/' || method !== 'POST' || typeof options.body !== 'string') return options;

  let payload: any;
  try {
    payload = JSON.parse(options.body);
  } catch {
    return options;
  }

  if (payload.latitude != null && payload.longitude != null) return options;

  const useCurrentLocation = window.confirm(
    'GPS-Geofence einrichten?\n\nOK: aktuellen Standort dieses Geräts als Mittelpunkt verwenden.\nAbbrechen: Einsatzort ohne GPS-Geofence speichern.',
  );
  if (!useCurrentLocation) return options;

  const coords = await currentCoordinates();
  payload.latitude = coords.latitude.toFixed(6);
  payload.longitude = coords.longitude.toFixed(6);
  payload.geofence_radius_m = Number(payload.geofence_radius_m || 250);

  return {
    ...options,
    body: JSON.stringify(payload),
  };
}

export async function api<T = any>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const normalizedPath = path.replace(/^\//, '');
  const preparedOptions = await prepareOptions(normalizedPath, options);
  const response = await request(`${API}/${normalizedPath}`, {
    ...preparedOptions,
    headers: headers(preparedOptions),
  });
  if (response.status === 401 && retry && !normalizedPath.startsWith('auth/login') && !normalizedPath.startsWith('auth/refresh')) {
    const token = await refreshAccessToken();
    if (token) {
      const retried = await request(`${API}/${normalizedPath}`, { ...preparedOptions, headers: headers(preparedOptions, token) });
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

export async function me() {
  try {
    const user = await api<User>('auth/me/');
    sessionStorage.removeItem('oauth-login-pending');
    return user;
  } catch (reason: any) {
    if (sessionStorage.getItem('oauth-login-pending')) {
      sessionStorage.removeItem('oauth-login-pending');
      window.setTimeout(() => showOAuthError(`OAuth completed, but portal session failed: ${reason?.message || 'Unknown error'}`), 0);
    }
    throw reason;
  }
}

// Do not send a user-controlled target URL. The backend already knows the canonical
// application callback URL. Keeping the OAuth start URL free of nested URLs also
// avoids edge/WAF false positives on the production domain.
export const socialUrl = (provider: 'google' | 'apple') => `${API}/auth/oauth/${provider}/start/`;

export function consumeOAuth() {
  const params = new URLSearchParams(location.search);
  const access = params.get('access');
  const refresh = params.get('refresh');
  const oauthError = params.get('oauth_error') || params.get('error');

  if (access && refresh) {
    localStorage.setItem('access', access);
    localStorage.setItem('refresh', refresh);
    sessionStorage.setItem('oauth-login-pending', '1');
    history.replaceState({}, '', '/');
    return true;
  }

  if (oauthError) {
    sessionStorage.removeItem('oauth-login-pending');
    history.replaceState({}, '', '/');
    window.setTimeout(() => showOAuthError(oauthError), 0);
  }
  return false;
}

export function logout() {
  localStorage.clear();
  sessionStorage.removeItem('oauth-login-pending');
  location.href = '/';
}
