import React, { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { IonIcon, IonSpinner } from '@ionic/react';
import {
  appsOutline,
  briefcaseOutline,
  calendarOutline,
  chevronForwardOutline,
  exitOutline,
  folderOpenOutline,
  homeOutline,
  lockClosedOutline,
  megaphoneOutline,
  personCircleOutline,
  starOutline,
} from 'ionicons/icons';
import { api, logout, User } from './api';
import { ClientDocumentsMobile, type ClientAccess } from './ClientPortalMobileV4';
import './client-portal-v2.css';
import './client-portal-v4.css';
import './client-portal-readonly-guard.css';

const TZ = 'Europe/Berlin';
const unpack = (value: any): any[] => value?.results || value || [];
const dateTime = (value?: string) => value
  ? new Intl.DateTimeFormat('de-DE', { timeZone: TZ, weekday: 'short', day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
  : '–';

const labels: Record<string, string> = {
  dashboard: 'Start',
  schedule: 'Einsätze',
  orders: 'Aufträge',
  documents: 'Dokumente',
  ratings: 'Mitarbeiter bewerten',
  messages: 'Mitteilungen',
  profile: 'Profil',
};

const primary = [
  ['dashboard', 'Dashboard', homeOutline],
  ['schedule', 'Kalender', calendarOutline],
  ['ratings', 'Bewerten', starOutline],
] as const;

const more = [
  ['orders', 'Personal anfragen', briefcaseOutline, 'Neue Personalanfrage und Verlauf'],
  ['documents', 'Dokumente', folderOpenOutline, 'Gemeinsamer Dateiordner'],
  ['messages', 'Mitteilungen', megaphoneOutline, 'Nachrichten der Disposition'],
  ['profile', 'Profil & Sicherheit', personCircleOutline, 'Kontaktdaten und Zugang'],
] as const;

function findNavigationTarget(view: string): HTMLElement | undefined {
  const wanted = labels[view];
  if (!wanted) return undefined;
  const items = Array.from(document.querySelectorAll<HTMLElement>('aside ion-item'));
  return items.find((item) => String(item.textContent || '').trim().includes(wanted));
}

function ClientHome({ user, access, navigate }: { user: User; access: ClientAccess; navigate: (view: string) => void }) {
  const [shifts, setShifts] = useState<any[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    void api('portal/client-shifts/').then((payload) => {
      if (!cancelled) setShifts(unpack(payload));
    }).catch((reason: any) => {
      if (!cancelled) setError(reason?.message || 'Einsätze konnten nicht geladen werden.');
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const now = Date.now();
  const nextShifts = useMemo(() => shifts
    .filter((shift) => shift?.status !== 'cancelled' && shift?.starts_at && new Date(shift.starts_at).getTime() >= now)
    .sort((left, right) => new Date(left.starts_at).getTime() - new Date(right.starts_at).getTime())
    .slice(0, 3), [shifts, now]);
  const firstName = access.first_name || user.first_name || user.name?.split(' ')[0] || 'Willkommen';

  if (loading && !shifts.length) return <div className="client-v2-loader"><IonSpinner/><span>Kundenportal wird geladen …</span></div>;

  if (access.read_only) return <div className="client-portal-v2-home" data-testid="client-portal-v2-home">
    <section className="client-v2-welcome"><div className="client-v2-welcome-copy"><small>KUNDENPORTAL</small><h1>Guten Tag, {firstName}</h1><p>{access.client_name} · eingeschränkter Lesezugang</p></div></section>
    <section className="client-v2-hero">
      <div><small>NUR ANSICHT</small><h2>{access.location_scope_name || 'Evangelische Akademie'}</h2><p>Dieser Zugang kann ausschließlich die freigegebenen Einsätze dieses Standorts öffnen und ansehen.</p></div>
      <button type="button" onClick={() => navigate('schedule')}>Kalender öffnen<IonIcon icon={chevronForwardOutline}/></button>
    </section>
    <div className="client-v4-lock-grid">
      {['Personal anfragen', 'Dokumente', 'Bewertungen', 'Mitteilungen', 'Profil ändern'].map((label) => <div key={label}><IonIcon icon={lockClosedOutline}/><span>{label}</span></div>)}
    </div>
    <section className="client-v2-section" style={{ marginTop: 14 }}><div className="client-v2-section-head"><div><small>EINSÄTZE</small><h2>Freigegebener Dienstplan</h2></div><button type="button" onClick={() => navigate('schedule')}>Kalender</button></div><div className="client-v2-list">{nextShifts.map((shift) => <button type="button" key={shift.id} onClick={() => navigate('schedule')} className="client-v2-list-row"><span className="client-v2-date"><b>{new Date(shift.starts_at).toLocaleDateString('de-DE', { day: '2-digit', timeZone: TZ })}</b><small>{new Date(shift.starts_at).toLocaleDateString('de-DE', { month: 'short', timeZone: TZ })}</small></span><div><b>{shift.location_name}</b><small>{dateTime(shift.starts_at)}</small></div><IonIcon icon={chevronForwardOutline}/></button>)}</div></section>
  </div>;

  return <div className="client-portal-v2-home" data-testid="client-portal-v2-home">
    <section className="client-v2-welcome">
      <div className="client-v2-welcome-copy"><small>KUNDENPORTAL</small><h1>Guten Tag, {firstName}</h1><p>{access.client_name} · Einsätze und Unterlagen zentral im Blick.</p></div>
      <button type="button" className="client-v2-message-button" onClick={() => navigate('messages')} aria-label="Mitteilungen öffnen"><IonIcon icon={megaphoneOutline}/></button>
    </section>
    {error ? <div className="client-v2-notice">{error}</div> : null}

    <section className="client-v2-hero">
      <div><small>PERSONALBEDARF</small><h2>Personal genau dann, wenn du es brauchst.</h2><p>Datum, Uhrzeit, Einsatzort, Anzahl und Notiz senden. Die Disposition prüft die Anfrage vor der Veröffentlichung.</p></div>
      <button type="button" onClick={() => navigate('orders')}>Personal anfragen<IonIcon icon={chevronForwardOutline}/></button>
    </section>

    <section className="client-v2-section" style={{ marginTop: 14 }}>
      <div className="client-v2-section-head"><div><small>EINSÄTZE</small><h2>Als Nächstes geplant</h2></div><button type="button" onClick={() => navigate('schedule')}>Alle</button></div>
      <div className="client-v2-list">
        {nextShifts.map((shift) => <button type="button" key={shift.id} onClick={() => navigate('schedule')} className="client-v2-list-row"><span className="client-v2-date"><b>{new Date(shift.starts_at).toLocaleDateString('de-DE', { day: '2-digit', timeZone: TZ })}</b><small>{new Date(shift.starts_at).toLocaleDateString('de-DE', { month: 'short', timeZone: TZ })}</small></span><div><b>{shift.location_name || 'Einsatz'}</b><small>{dateTime(shift.starts_at)}{shift.notes ? ` · ${shift.notes}` : ''}</small></div><IonIcon icon={chevronForwardOutline}/></button>)}
        {!nextShifts.length ? <div className="client-v2-empty"><IonIcon icon={calendarOutline}/><b>Keine kommenden Einsätze</b><span>Sobald ein Einsatz geplant ist, erscheint er hier.</span></div> : null}
      </div>
    </section>

    <section className="client-v2-section client-v2-documents" style={{ marginTop: 14 }}>
      <div className="client-v2-section-head"><div><small>DOKUMENTE</small><h2>Gemeinsamer Ordner</h2></div><button type="button" onClick={() => navigate('documents')}>Alle öffnen</button></div>
      <div style={{ padding: 10 }}><ClientDocumentsMobile access={access} compact /></div>
    </section>
  </div>;
}

function ClientMore({ user, access, view, close, navigate }: { user: User; access: ClientAccess; view: string; close: () => void; navigate: (view: string) => void }) {
  return <div className="client-v2-more" data-testid="client-v2-more">
    <header><button type="button" onClick={close}>Fertig</button><div><small>KUNDENPORTAL</small><h1>Mehr</h1></div><span className="client-v2-avatar">{access.first_name?.[0] || user.name?.[0] || 'K'}</span></header>
    <div className="client-v2-more-user"><b>{access.account_name || user.name}</b><span>{access.client_name}</span></div>
    <div className="client-v2-more-list">
      {more.map(([key, label, icon, description]) => {
        const locked = access.read_only;
        return <button type="button" key={key} disabled={locked} className={`${view === key ? 'active ' : ''}${locked ? 'is-locked' : ''}`} onClick={() => !locked && navigate(key)}><span><IonIcon icon={locked ? lockClosedOutline : icon}/></span><div><b>{label}</b><small>{locked ? 'Für diesen Zugang gesperrt' : description}</small></div><IonIcon icon={locked ? lockClosedOutline : chevronForwardOutline}/></button>;
      })}
    </div>
    <button type="button" className="client-v2-logout" onClick={logout}><IonIcon icon={exitOutline}/>Abmelden</button>
  </div>;
}

export default function ClientPortalV2() {
  const [user, setUser] = useState<User | null>(null);
  const [access, setAccess] = useState<ClientAccess | null>(null);
  const [view, setView] = useState('dashboard');
  const [moreOpen, setMoreOpen] = useState(false);
  const [host, setHost] = useState<HTMLElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!localStorage.getItem('access')) return;
    void Promise.all([api('auth/me/'), api('portal/client-access/')]).then(([current, portalAccess]: any[]) => {
      if (!cancelled && current?.role === 'client') { setUser(current); setAccess(portalAccess); }
    }).catch(() => undefined);
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!user) return;
    document.body.classList.add('client-portal-v2-active');
    document.body.classList.toggle('client-portal-read-only', Boolean(access?.read_only));
    const sync = () => {
      const shell = document.querySelector<HTMLElement>('.mobile-first-app-shell-v1');
      const nextView = shell?.dataset.view || 'dashboard';
      setView(nextView);
      setHost(document.querySelector<HTMLElement>('.app-main'));
      document.body.classList.toggle('client-portal-v2-dashboard', nextView === 'dashboard');
    };
    sync();
    const root = document.getElementById('root');
    const observer = new MutationObserver(sync);
    if (root) observer.observe(root, { subtree: true, childList: true, attributes: true, attributeFilter: ['data-view'] });
    return () => {
      observer.disconnect();
      document.body.classList.remove('client-portal-v2-active', 'client-portal-v2-dashboard', 'client-portal-read-only');
    };
  }, [user, access?.read_only]);

  useEffect(() => { setMoreOpen(false); }, [view]);

  const navigate = (next: string) => {
    setMoreOpen(false);
    if (access?.read_only && !['dashboard', 'schedule'].includes(next)) return;
    const target = findNavigationTarget(next);
    if (target) { target.click(); return; }
    if (next === 'profile') document.querySelector<HTMLElement>('.mobile-avatar')?.click();
  };

  if (!user || !access) return null;
  return <>
    {view === 'dashboard' && host ? createPortal(<ClientHome user={user} access={access} navigate={navigate}/>, host) : null}
    <nav className="client-v2-tabbar" aria-label="Kundenportal Navigation" data-testid="client-v2-tabbar" style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))' }}>
      {primary.map(([key, label, icon]) => {
        const locked = access.read_only && key === 'ratings';
        return <button type="button" key={key} disabled={locked} className={`${view === key && !moreOpen ? 'active ' : ''}${locked ? 'is-locked' : ''}`} onClick={() => navigate(key)} aria-current={view === key ? 'page' : undefined} aria-label={key === 'ratings' ? 'Mitarbeiter bewerten' : label}><IonIcon icon={locked ? lockClosedOutline : icon}/><span>{label}</span></button>;
      })}
      <button type="button" className={moreOpen || !primary.some(([key]) => key === view) ? 'active' : ''} onClick={() => setMoreOpen(true)} aria-label="Weitere Bereiche öffnen"><IonIcon icon={appsOutline}/><span>Mehr</span></button>
    </nav>
    {moreOpen ? <ClientMore user={user} access={access} view={view} close={() => setMoreOpen(false)} navigate={navigate}/> : null}
  </>;
}
