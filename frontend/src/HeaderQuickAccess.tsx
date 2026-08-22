import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { IonIcon } from '@ionic/react';
import {
  briefcaseOutline,
  calendarOutline,
  checkmarkDoneOutline,
  closeOutline,
  documentTextOutline,
  folderOpenOutline,
  locationOutline,
  notificationsOutline,
  peopleOutline,
  receiptOutline,
  searchOutline,
} from 'ionicons/icons';
import { api, me, type User } from './api';

type ApiPage<T> = T[] | { count?: number; next?: string | null; results?: T[] };

type NotificationRow = {
  id: string;
  title?: string;
  body?: string;
  action_url?: string;
  created_at?: string;
  read_at?: string | null;
};

type WorkerRow = {
  id: string;
  employee_number?: string;
  user_detail?: { name?: string; email?: string; first_name?: string; last_name?: string };
};

type ClientRow = {
  id: string;
  name?: string;
  customer_number?: string;
  address?: string;
};

type AkteData = {
  kind: 'worker' | 'client';
  title: string;
  number?: string;
  profile?: any;
  summary?: Record<string, number>;
  contracts?: any[];
  document_folders?: Array<{ key: string; label: string; count: number; items: any[] }>;
  payroll?: any[];
  shifts?: any[];
  orders?: any[];
  locations?: any[];
};

type PersonChoice = {
  id: string;
  kind: 'worker' | 'client';
  title: string;
  subtitle: string;
};

function pageRows<T>(payload: ApiPage<T>): T[] {
  if (Array.isArray(payload)) return payload;
  return Array.isArray(payload?.results) ? payload.results : [];
}

async function fetchAllPages<T>(path: string): Promise<T[]> {
  const rows: T[] = [];
  for (let page = 1; page <= 40; page += 1) {
    const separator = path.includes('?') ? '&' : '?';
    const payload = await api<ApiPage<T>>(`${path}${separator}page=${page}`);
    rows.push(...pageRows(payload));
    if (Array.isArray(payload) || !payload.next) break;
  }
  return rows;
}

function formatDate(value?: string) {
  if (!value) return '';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    timeZone: 'Europe/Berlin',
    hour: value.includes('T') ? '2-digit' : undefined,
    minute: value.includes('T') ? '2-digit' : undefined,
  }).format(parsed);
}

function navigateAction(actionUrl?: string) {
  if (!actionUrl) return;
  const route = actionUrl.replace(/^\/+/, '').split(/[?#]/)[0];
  const viewMap: Record<string, string> = {
    messages: 'messages',
    contracts: 'contracts',
    documents: 'documents',
    schedule: 'schedule',
    shifts: 'schedule',
    orders: 'orders',
    people: 'people',
    operations: 'operations',
  };
  const view = viewMap[route];
  if (view) {
    const url = new URL(window.location.href);
    url.pathname = '/';
    url.searchParams.set('view', view);
    window.history.pushState({ view }, '', `${url.pathname}${url.search}${url.hash}`);
    window.dispatchEvent(new PopStateEvent('popstate'));
    return;
  }
  window.location.href = actionUrl;
}

function FileLink({ href, children }: { href?: string; children: React.ReactNode }) {
  if (!href) return <span className="hq-muted">Keine Datei</span>;
  return (
    <a className="hq-file-link" href={href} target="_blank" rel="noreferrer">
      {children}
    </a>
  );
}

function SummaryIcon({ name }: { name: string }) {
  const lower = name.toLowerCase();
  const icon = lower.includes('contract')
    ? documentTextOutline
    : lower.includes('document')
      ? folderOpenOutline
      : lower.includes('payroll')
        ? receiptOutline
        : lower.includes('order')
          ? briefcaseOutline
          : lower.includes('location')
            ? locationOutline
            : calendarOutline;
  return <IonIcon icon={icon} />;
}

function AkteContent({ data }: { data: AkteData }) {
  const summary = Object.entries(data.summary || {});
  const email = data.kind === 'worker'
    ? data.profile?.user_detail?.email
    : data.profile?.contacts_detail?.[0]?.email;
  const address = data.kind === 'worker'
    ? undefined
    : data.profile?.address;

  return (
    <div className="hq-akte-content">
      <div className="hq-akte-hero">
        <div className="hq-akte-avatar"><IonIcon icon={data.kind === 'worker' ? peopleOutline : briefcaseOutline} /></div>
        <div>
          <strong>{data.title}</strong>
          <div>{data.number || 'Ohne Nummer'}{email ? ` · ${email}` : ''}</div>
          {address ? <small>{address}</small> : null}
        </div>
      </div>

      <div className="hq-summary-grid">
        {summary.map(([key, value]) => (
          <div className="hq-summary-card" key={key}>
            <SummaryIcon name={key} />
            <strong>{value}</strong>
            <span>{({ contracts: 'Verträge', documents: 'Dokumente', payroll: 'Lohn', shifts: 'Einsätze', orders: 'Aufträge', locations: 'Standorte' } as Record<string, string>)[key] || key}</span>
          </div>
        ))}
      </div>

      <section className="hq-akte-section">
        <h3><IonIcon icon={documentTextOutline} /> Verträge</h3>
        {(data.contracts || []).length ? (data.contracts || []).map((contract) => (
          <div className="hq-row" key={contract.id}>
            <div>
              <strong>{contract.title || contract.template_name || 'Vertrag'}</strong>
              <span>{contract.status || '—'}{contract.starts_on ? ` · ab ${formatDate(contract.starts_on)}` : ''}</span>
            </div>
            <FileLink href={contract.pdf}>PDF</FileLink>
          </div>
        )) : <div className="hq-empty">Noch keine Verträge.</div>}
      </section>

      <section className="hq-akte-section">
        <h3><IonIcon icon={folderOpenOutline} /> Dokumente</h3>
        {(data.document_folders || []).length ? (data.document_folders || []).map((folder) => (
          <details className="hq-folder" key={folder.key} open>
            <summary>{folder.label} <span>{folder.count}</span></summary>
            {folder.items.map((document) => (
              <div className="hq-row hq-row-nested" key={document.id}>
                <div>
                  <strong>{document.title || document.name || 'Dokument'}</strong>
                  <span>{formatDate(document.created_at)}</span>
                </div>
                <FileLink href={document.file}>Öffnen</FileLink>
              </div>
            ))}
          </details>
        )) : <div className="hq-empty">Noch keine Dokumente.</div>}
      </section>

      {data.kind === 'worker' ? (
        <section className="hq-akte-section">
          <h3><IonIcon icon={receiptOutline} /> Lohnabrechnungen</h3>
          {(data.payroll || []).length ? (data.payroll || []).map((payroll) => (
            <div className="hq-row" key={payroll.id}>
              <div><strong>{payroll.period || 'Lohnabrechnung'}</strong><span>{formatDate(payroll.created_at)}</span></div>
              <FileLink href={payroll.document}>Öffnen</FileLink>
            </div>
          )) : <div className="hq-empty">Noch keine Lohnabrechnungen.</div>}
        </section>
      ) : (
        <>
          <section className="hq-akte-section">
            <h3><IonIcon icon={briefcaseOutline} /> Aufträge</h3>
            {(data.orders || []).length ? (data.orders || []).map((order) => (
              <div className="hq-row" key={order.id}>
                <div><strong>{order.title || 'Auftrag'}</strong><span>{order.status || '—'}{order.starts_at ? ` · ${formatDate(order.starts_at)}` : ''}</span></div>
              </div>
            )) : <div className="hq-empty">Noch keine Aufträge.</div>}
          </section>
          <section className="hq-akte-section">
            <h3><IonIcon icon={locationOutline} /> Standorte</h3>
            {(data.locations || []).length ? (data.locations || []).map((location) => (
              <div className="hq-row" key={location.id}>
                <div><strong>{location.name || 'Standort'}</strong><span>{location.address || 'Keine Anschrift'}</span></div>
              </div>
            )) : <div className="hq-empty">Noch keine Standorte.</div>}
          </section>
        </>
      )}

      <section className="hq-akte-section">
        <h3><IonIcon icon={calendarOutline} /> Einsätze</h3>
        {(data.shifts || []).length ? (data.shifts || []).map((shift) => (
          <div className="hq-row" key={shift.id}>
            <div>
              <strong>{shift.position_name || shift.location_name || 'Einsatz'}</strong>
              <span>{formatDate(shift.starts_at)}{shift.client_name ? ` · ${shift.client_name}` : ''}{shift.worker_name ? ` · ${shift.worker_name}` : ''}</span>
            </div>
          </div>
        )) : <div className="hq-empty">Noch keine Einsätze.</div>}
      </section>
    </div>
  );
}

export default function HeaderQuickAccess() {
  const tokenRef = useRef('');
  const [user, setUser] = useState<User | null>(null);
  const [notifications, setNotifications] = useState<NotificationRow[]>([]);
  const [panel, setPanel] = useState<'notifications' | 'akten' | null>(null);
  const [workers, setWorkers] = useState<WorkerRow[]>([]);
  const [clients, setClients] = useState<ClientRow[]>([]);
  const [peopleLoading, setPeopleLoading] = useState(false);
  const [akteLoading, setAkteLoading] = useState(false);
  const [akte, setAkte] = useState<AkteData | null>(null);
  const [query, setQuery] = useState('');
  const [error, setError] = useState('');

  const loadNotifications = useCallback(async () => {
    if (!localStorage.getItem('access')) return;
    try {
      const payload = await api<ApiPage<NotificationRow>>('notifications/?page=1');
      setNotifications(pageRows(payload));
    } catch {
      // Header shortcuts must never block the main application.
    }
  }, []);

  useEffect(() => {
    let disposed = false;
    const syncSession = async () => {
      const token = localStorage.getItem('access') || '';
      if (token === tokenRef.current) return;
      tokenRef.current = token;
      if (!token) {
        if (!disposed) {
          setUser(null);
          setNotifications([]);
          setPanel(null);
        }
        return;
      }
      try {
        const current = await me();
        if (!disposed) setUser(current);
        void loadNotifications();
      } catch {
        if (!disposed) setUser(null);
      }
    };

    void syncSession();
    const sessionTimer = window.setInterval(syncSession, 1500);
    const notificationTimer = window.setInterval(loadNotifications, 45000);
    const onFocus = () => void loadNotifications();
    window.addEventListener('focus', onFocus);
    return () => {
      disposed = true;
      window.clearInterval(sessionTimer);
      window.clearInterval(notificationTimer);
      window.removeEventListener('focus', onFocus);
    };
  }, [loadNotifications]);

  const unread = notifications.filter((item) => !item.read_at).length;
  const isManager = user?.role === 'admin' || user?.role === 'manager';

  const people = useMemo<PersonChoice[]>(() => {
    const workerChoices = workers.map((worker) => ({
      id: worker.id,
      kind: 'worker' as const,
      title: worker.user_detail?.name || worker.user_detail?.email || 'Mitarbeiter',
      subtitle: worker.employee_number || worker.user_detail?.email || '',
    }));
    const clientChoices = clients.map((client) => ({
      id: client.id,
      kind: 'client' as const,
      title: client.name || 'Kunde',
      subtitle: client.customer_number || client.address || '',
    }));
    const needle = query.trim().toLocaleLowerCase('de-DE');
    const combined = [...workerChoices, ...clientChoices].sort((a, b) => a.title.localeCompare(b.title, 'de'));
    return needle ? combined.filter((row) => `${row.title} ${row.subtitle}`.toLocaleLowerCase('de-DE').includes(needle)) : combined;
  }, [workers, clients, query]);

  const openAkten = async () => {
    setPanel('akten');
    setAkte(null);
    setError('');
    if (workers.length || clients.length || peopleLoading) return;
    setPeopleLoading(true);
    try {
      const [workerRows, clientRows] = await Promise.all([
        fetchAllPages<WorkerRow>('workers/'),
        fetchAllPages<ClientRow>('clients/'),
      ]);
      setWorkers(workerRows);
      setClients(clientRows);
    } catch (reason: any) {
      setError(reason?.message || 'Akten konnten nicht geladen werden.');
    } finally {
      setPeopleLoading(false);
    }
  };

  const openAkte = async (choice: PersonChoice) => {
    setPanel(null);
    const url = new URL(window.location.href);
    url.pathname = '/';
    url.searchParams.set('view', 'akte');
    url.searchParams.set('akte_kind', choice.kind);
    url.searchParams.set('akte_id', choice.id);
    window.history.pushState({ view: 'akte' }, '', `${url.pathname}${url.search}${url.hash}`);
    window.dispatchEvent(new PopStateEvent('popstate'));
  };

  const readAll = async () => {
    try {
      await api('operations/notifications/read-all/', { method: 'POST', body: '{}' });
      setNotifications((rows) => rows.map((row) => ({ ...row, read_at: row.read_at || new Date().toISOString() })));
    } catch (reason: any) {
      setError(reason?.message || 'Benachrichtigungen konnten nicht aktualisiert werden.');
    }
  };

  const openNotification = async (row: NotificationRow) => {
    if (!row.read_at) {
      try {
        await api(`notifications/${row.id}/read/`, { method: 'POST', body: '{}' });
        setNotifications((items) => items.map((item) => item.id === row.id ? { ...item, read_at: new Date().toISOString() } : item));
      } catch {
        // Navigation is still more useful than blocking on a read receipt.
      }
    }
    setPanel(null);
    navigateAction(row.action_url);
  };

  if (!user || typeof document === 'undefined') return null;

  return createPortal(
    <>
      <div className="header-quick-access" aria-label="Schnellzugriff">
        {isManager ? (
          <button type="button" className="hq-icon-button" onClick={() => void openAkten()} aria-label="Mitarbeiter- und Kundenakten" title="Akten">
            <IonIcon icon={folderOpenOutline} />
          </button>
        ) : null}
        <button type="button" className="hq-icon-button" onClick={() => { setPanel('notifications'); setError(''); void loadNotifications(); }} aria-label={`Benachrichtigungen${unread ? `, ${unread} ungelesen` : ''}`} title="Benachrichtigungen">
          <IonIcon icon={notificationsOutline} />
          {unread > 0 ? <span className="hq-unread-badge">{unread > 99 ? '99+' : unread}</span> : null}
        </button>
      </div>

      {panel ? (
        <div className="hq-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setPanel(null); }}>
          <aside className="hq-sheet" role="dialog" aria-modal="true" aria-label={panel === 'notifications' ? 'Benachrichtigungen' : 'Akten'}>
            <header className="hq-sheet-header">
              <div>
                <span className="hq-eyebrow">Schnellzugriff</span>
                <h2>{panel === 'notifications' ? 'Benachrichtigungen' : akte ? 'Digitale Akte' : 'Mitarbeiter & Kunden'}</h2>
              </div>
              <button type="button" className="hq-close" onClick={() => setPanel(null)} aria-label="Schließen"><IonIcon icon={closeOutline} /></button>
            </header>

            {error ? <div className="hq-error" role="alert">{error}</div> : null}

            {panel === 'notifications' ? (
              <div className="hq-panel-body">
                <div className="hq-panel-toolbar">
                  <span>{unread ? `${unread} ungelesen` : 'Alles gelesen'}</span>
                  {unread ? <button type="button" onClick={() => void readAll()}><IonIcon icon={checkmarkDoneOutline} /> Alle gelesen</button> : null}
                </div>
                <div className="hq-notification-list">
                  {notifications.length ? notifications.map((row) => (
                    <button type="button" className={`hq-notification ${row.read_at ? '' : 'is-unread'}`} key={row.id} onClick={() => void openNotification(row)}>
                      <span className="hq-notification-dot" />
                      <span className="hq-notification-copy">
                        <strong>{row.title || 'Benachrichtigung'}</strong>
                        {row.body ? <span>{row.body}</span> : null}
                        <small>{formatDate(row.created_at)}</small>
                      </span>
                    </button>
                  )) : <div className="hq-empty hq-empty-large">Keine Benachrichtigungen.</div>}
                </div>
              </div>
            ) : (
              <div className="hq-panel-body">
                {akte ? (
                  <>
                    <button type="button" className="hq-back-button" onClick={() => { setAkte(null); setError(''); }}>← Alle Akten</button>
                    {akteLoading ? <div className="hq-loading">Akte wird geladen …</div> : <AkteContent data={akte} />}
                  </>
                ) : (
                  <>
                    <label className="hq-search">
                      <IonIcon icon={searchOutline} />
                      <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Name, Personal- oder Kundennummer …" autoFocus />
                    </label>
                    <div className="hq-kind-hint"><span><IonIcon icon={peopleOutline} /> Mitarbeiter</span><span><IonIcon icon={briefcaseOutline} /> Kunden</span></div>
                    {peopleLoading ? <div className="hq-loading">Akten werden geladen …</div> : (
                      <div className="hq-people-list">
                        {people.map((choice) => (
                          <button type="button" className="hq-person" key={`${choice.kind}-${choice.id}`} onClick={() => void openAkte(choice)}>
                            <span className={`hq-person-icon ${choice.kind}`}><IonIcon icon={choice.kind === 'worker' ? peopleOutline : briefcaseOutline} /></span>
                            <span><strong>{choice.title}</strong><small>{choice.subtitle || (choice.kind === 'worker' ? 'Mitarbeiter' : 'Kunde')}</small></span>
                            <IonIcon icon={folderOpenOutline} />
                          </button>
                        ))}
                        {!people.length && !peopleLoading ? <div className="hq-empty hq-empty-large">Keine passende Akte gefunden.</div> : null}
                      </div>
                    )}
                  </>
                )}
              </div>
            )}
          </aside>
        </div>
      ) : null}
    </>,
    document.body,
  );
}
