type View =
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
  | 'operations';

const VIEW_LABELS: Record<View, string[]> = {
  dashboard: ['Übersicht', 'Start'],
  schedule: ['Dienstplanung', 'Mein Dienstplan', 'Einsätze'],
  time: ['Zeiterfassung', 'Arbeitszeitkonto'],
  contracts: ['Verträge', 'Meine Verträge', 'Verträge & Signatur'],
  documents: ['Dokumente', 'Dokumente & Lohn'],
  orders: ['Aufträge'],
  people: ['Personal & Kunden'],
  messages: ['Nachrichten'],
  ranking: ['Ranking'],
  ratings: ['Mitarbeiter bewerten'],
  profile: ['Profil'],
  operations: ['Steuerzentrale', 'Verfügbarkeit & Tausch', 'Servicecenter'],
};

const ALL_VIEWS = new Set<View>(Object.keys(VIEW_LABELS) as View[]);
const LABEL_TO_VIEW = new Map<string, View>(
  Object.entries(VIEW_LABELS).flatMap(([view, labels]) =>
    labels.map((label) => [label, view as View] as const),
  ),
);

function itemLabel(item: Element) {
  return item.querySelector('ion-label')?.textContent?.trim() || '';
}

function sidebarItems() {
  return Array.from(document.querySelectorAll<HTMLElement>('aside ion-item'));
}

function findItem(view: View) {
  const labels = VIEW_LABELS[view];
  return sidebarItems().find((item) => labels.includes(itemLabel(item)));
}

function activeView(): View | null {
  const active = document.querySelector('aside ion-item.active');
  return active ? LABEL_TO_VIEW.get(itemLabel(active)) || null : null;
}

function requestedView(): { raw: string | null; view: View | null } {
  const raw = new URLSearchParams(window.location.search).get('view');
  return {
    raw,
    view: raw && ALL_VIEWS.has(raw as View) ? (raw as View) : null,
  };
}

function urlForView(view: View) {
  const url = new URL(window.location.href);
  if (view === 'dashboard') url.searchParams.delete('view');
  else url.searchParams.set('view', view);
  return `${url.pathname}${url.search}${url.hash}`;
}

/**
 * App.tsx still owns the in-memory view while the shell is being decomposed.
 * This adapter makes that view durable browser state without rewriting the
 * legacy monolith: URL deep links drive the existing navigation, and every
 * App navigation is reflected back into history via the active sidebar item.
 */
export function installViewHistory() {
  if (window.location.pathname !== '/') return () => undefined;

  let applyingFromHistory: View | null = null;
  let observedAside: Element | null = null;
  let asideObserver: MutationObserver | null = null;

  const syncUrlFromApp = () => {
    const active = activeView();
    if (!active) return;

    if (applyingFromHistory) {
      if (active === applyingFromHistory) applyingFromHistory = null;
      return;
    }

    const requested = requestedView();
    const canonicalUrl = urlForView(active);
    const currentUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`;
    const urlAlreadyMatches =
      requested.view === active &&
      !(active === 'dashboard' && requested.raw !== null) &&
      currentUrl === canonicalUrl;

    if (!urlAlreadyMatches) {
      window.history.pushState({ view: active }, '', canonicalUrl);
    }
  };

  const applyLocationToApp = () => {
    if (window.location.pathname !== '/') return;

    const requested = requestedView();
    const desired = requested.raw === null ? 'dashboard' : requested.view;

    if (!desired) {
      applyingFromHistory = null;
      window.history.replaceState({ view: 'dashboard' }, '', urlForView('dashboard'));
      const dashboard = findItem('dashboard');
      if (dashboard && activeView() !== 'dashboard') {
        applyingFromHistory = 'dashboard';
        dashboard.click();
      }
      return;
    }

    const target = findItem(desired);
    if (!target) {
      // The requested view exists globally but is not available for this role.
      applyingFromHistory = null;
      window.history.replaceState({ view: 'dashboard' }, '', urlForView('dashboard'));
      const dashboard = findItem('dashboard');
      if (dashboard && activeView() !== 'dashboard') {
        applyingFromHistory = 'dashboard';
        dashboard.click();
      }
      return;
    }

    if (desired === 'dashboard' && requested.raw !== null) {
      window.history.replaceState({ view: 'dashboard' }, '', urlForView('dashboard'));
    }

    if (activeView() !== desired) {
      applyingFromHistory = desired;
      target.click();
    }
  };

  const attachToShell = () => {
    const aside = document.querySelector('aside');
    if (!aside || aside === observedAside) return;

    asideObserver?.disconnect();
    observedAside = aside;
    asideObserver = new MutationObserver(syncUrlFromApp);
    asideObserver.observe(aside, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ['class'],
    });

    queueMicrotask(applyLocationToApp);
  };

  const shellObserver = new MutationObserver(attachToShell);
  shellObserver.observe(document.body, { childList: true, subtree: true });
  window.addEventListener('popstate', applyLocationToApp);
  attachToShell();

  return () => {
    window.removeEventListener('popstate', applyLocationToApp);
    shellObserver.disconnect();
    asideObserver?.disconnect();
  };
}
