import { useCallback, useEffect, useState } from 'react';

export type View =
  | 'dashboard'
  | 'schedule'
  | 'time'
  | 'contracts'
  | 'documents'
  | 'orders'
  | 'people'
  | 'messages'
  | 'ranking'
  | 'ratings'
  | 'profile'
  | 'operations'
  | 'settings'
  | 'akte';

const ROLE_VIEWS: Record<string, ReadonlySet<View>> = {
  admin: new Set<View>([
    'dashboard',
    'schedule',
    'time',
    'contracts',
    'documents',
    'orders',
    'people',
    'messages',
    'operations',
    'settings',
    'akte',
  ]),
  manager: new Set<View>([
    'dashboard',
    'schedule',
    'time',
    'contracts',
    'documents',
    'orders',
    'people',
    'messages',
    'operations',
    'settings',
    'akte',
  ]),
  worker: new Set<View>([
    'dashboard',
    'schedule',
    'time',
    'operations',
    'contracts',
    'documents',
    'messages',
    'ranking',
    'akte',
  ]),
  client: new Set<View>([
    'dashboard',
    'operations',
    'orders',
    'schedule',
    'contracts',
    'documents',
    'ratings',
    'messages',
    'akte',
  ]),
};

const KNOWN_VIEWS = new Set<View>([
  'dashboard',
  'schedule',
  'time',
  'contracts',
  'documents',
  'orders',
  'people',
  'messages',
  'ranking',
  'ratings',
  'profile',
  'operations',
  'settings',
  'akte',
]);

function requestedView() {
  return new URLSearchParams(window.location.search).get('view');
}

function canonicalUrl(view: View) {
  const url = new URL(window.location.href);
  if (view === 'dashboard') url.searchParams.delete('view');
  else url.searchParams.set('view', view);
  if (view !== 'akte') {
    url.searchParams.delete('akte_kind');
    url.searchParams.delete('akte_id');
  }
  return `${url.pathname}${url.search}${url.hash}`;
}

function safeView(role?: string | null): View {
  if (window.location.pathname !== '/') return 'dashboard';

  const requested = requestedView();
  if (!requested || requested === 'dashboard') return 'dashboard';
  if (requested === 'profile') return 'profile';
  if (!KNOWN_VIEWS.has(requested as View)) return 'dashboard';
  if (!role || !ROLE_VIEWS[role]?.has(requested as View)) return 'dashboard';
  return requested as View;
}

/**
 * Browser-history adapter for the legacy App shell.
 *
 * App.tsx still owns all rendering and navigation decisions. Vite replaces its
 * single `useState<View>('dashboard')` declaration with this hook at transform
 * time, giving the existing `setView(...)` calls durable URL state without a
 * risky rewrite of the large shell.
 */
export function useViewRouting(role?: string | null) {
  const [view, setViewState] = useState<View>('dashboard');

  useEffect(() => {
    if (!role || window.location.pathname !== '/') return;

    const applyLocation = () => {
      const requested = requestedView();
      const next = safeView(role);
      setViewState(next);

      // Unknown, forbidden and explicit dashboard URLs are canonicalized to
      // the clean start URL. This is the role guard for direct links.
      if (requested && next === 'dashboard') {
        window.history.replaceState({ view: next }, '', canonicalUrl(next));
      }
    };

    applyLocation();
    window.addEventListener('popstate', applyLocation);
    return () => window.removeEventListener('popstate', applyLocation);
  }, [role]);

  const setView = useCallback(
    (next: View) => {
      const allowed =
        next === 'profile' ||
        next === 'dashboard' ||
        (!!role && ROLE_VIEWS[role]?.has(next));
      const safe = allowed ? next : 'dashboard';

      // Keep history writes outside the React state updater. StrictMode may
      // invoke updater functions more than once during development.
      if (window.location.pathname === '/' && view !== safe) {
        window.history.pushState({ view: safe }, '', canonicalUrl(safe));
      }
      setViewState(safe);
    },
    [role, view],
  );

  return [view, setView] as const;
}
