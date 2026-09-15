import React, { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { IonIcon, IonSpinner } from '@ionic/react';
import {
  appsOutline,
  briefcaseOutline,
  calendarOutline,
  chevronForwardOutline,
  documentTextOutline,
  exitOutline,
  folderOpenOutline,
  homeOutline,
  megaphoneOutline,
  peopleOutline,
  personCircleOutline,
  shieldCheckmarkOutline,
  starOutline,
} from 'ionicons/icons';
import { api, logout, User } from './api';
import './client-portal-v2.css';

const TZ = 'Europe/Berlin';
const unpack = (value: any): any[] => value?.results || value || [];
const dateTime = (value?: string) => value
  ? new Intl.DateTimeFormat('de-DE', { timeZone: TZ, weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
  : '–';

const labels: Record<string, string> = {
  dashboard: 'Start',
  schedule: 'Einsätze',
  orders: 'Aufträge',
  documents: 'Dokumente',
  contracts: 'Verträge & Signatur',
  operations: 'Servicecenter',
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
  ['orders', 'Aufträge', briefcaseOutline, 'Personalbedarf und Aufträge verwalten'],
  ['documents', 'Dokumente', folderOpenOutline, 'Unterlagen öffnen und hochladen'],
  ['contracts', 'Verträge & Signatur', documentTextOutline, 'Verträge ansehen und offene Signaturen erledigen'],
  ['operations', 'Servicecenter', shieldCheckmarkOutline, 'Status, Hinweise und offene Servicepunkte'],
  ['messages', 'Mitteilungen', megaphoneOutline, 'Nachrichten der A+ Disposition'],
  ['profile', 'Profil & Sicherheit', personCircleOutline, 'Kontaktdaten, Passwort und Datenschutz'],
] as const;

function findNavigationTarget(view: string): HTMLElement | undefined {
  const wanted = labels[view];
  if (!wanted) return undefined;
  const items = Array.from(document.querySelectorAll<HTMLElement>('aside ion-item'));
  return items.find((item) => String(item.textContent || '').trim().includes(wanted));
}

function ClientHome({ user, navigate }: { user: User; navigate: (view: string) => void }) {
  const [data, setData] = useState<any>();
  const [orders, setOrders] = useState<any[]>([]);
  const [shifts, setShifts] = useState<any[]>([]);
  const [contracts, setContracts] = useState<any[]>([]);
  const [documents, setDocuments] = useState<any[]>([]);
  const [operations, setOperations] = useState<any>();
  const [company, setCompany] = useState<any>();
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const requests = await Promise.allSettled([
        api('portal/client-dashboard/'),
        api('orders/?ordering=starts_at'),
        api('shifts/?ordering=starts_at'),
        api('contracts/?ordering=-updated_at'),
        api('documents/?ordering=-created_at'),
        api('operations/'),
        api('operations/folders/'),
      ]);
      if (cancelled) return;
      const [dashboardResult, ordersResult, shiftsResult, contractsResult, documentsResult, operationsResult, foldersResult] = requests;
      if (dashboardResult.status === 'fulfilled') setData(dashboardResult.value);
      else setError('Der Kundenbereich konnte nicht vollständig geladen werden.');
      if (ordersResult.status === 'fulfilled') setOrders(unpack(ordersResult.value));
      if (shiftsResult.status === 'fulfilled') setShifts(unpack(shiftsResult.value));
      if (contractsResult.status === 'fulfilled') setContracts(unpack(contractsResult.value));
      if (documentsResult.status === 'fulfilled') setDocuments(unpack(documentsResult.value));
      if (operationsResult.status === 'fulfilled') setOperations(operationsResult.value);
      if (foldersResult.status === 'fulfilled') setCompany(foldersResult.value?.clients?.[0]);
    };
    void load();
    return () => { cancelled = true; };
  }, []);

  const now = Date.now();
  const nextShifts = useMemo(() => shifts
    .filter((shift) => shift?.status !== 'cancelled' && shift?.starts_at && new Date(shift.starts_at).getTime() >= now)
    .sort((left, right) => new Date(left.starts_at).getTime() - new Date(right.starts_at).getTime())
    .slice(0, 3), [shifts, now]);
  const activeOrders = useMemo(() => orders.filter((order) => ['new', 'planning', 'confirmed'].includes(order?.status)), [orders]);
  const actionContracts = useMemo(() => contracts.filter((contract) => ['ready', 'sent'].includes(contract?.status)), [contracts]);
  const recentDocuments = useMemo(() => [...documents]
    .sort((left, right) => new Date(right.created_at || 0).getTime() - new Date(left.created_at || 0).getTime())
    .slice(0, 3), [documents]);

  if (!data && !error) return <div className="client-v2-loader"><IonSpinner/><span>Kundenportal wird geladen …</span></div>;

  const firstName = user.first_name || user.name?.split(' ')[0] || 'Willkommen';
  const nextShift = nextShifts[0];
  const unread = Number(operations?.unread_notifications || 0);
  const openContracts = Number(data?.contracts_to_sign ?? actionContracts.length ?? 0);
  const openOrders = Number(data?.active_orders ?? activeOrders.length ?? 0);
  const upcoming = Number(data?.upcoming_shifts ?? nextShifts.length ?? 0);

  return <div className="client-portal-v2-home" data-testid="client-portal-v2-home">
    <section className="client-v2-welcome">
      <div className="client-v2-welcome-copy">
        <small>KUNDENPORTAL</small>
        <h1>Guten Tag, {firstName}</h1>
        <p>{company?.name ? `${company.name} · ` : ''}Personalbedarf, Einsätze und Unterlagen zentral im Blick.</p>
      </div>
      <button type="button" className="client-v2-message-button" onClick={() => navigate('messages')} aria-label="Mitteilungen öffnen">
        <IonIcon icon={megaphoneOutline}/>{unread > 0 && <b>{unread}</b>}
      </button>
    </section>

    {error && <div className="client-v2-notice">{error} Die verfügbaren Bereiche können trotzdem geöffnet werden.</div>}

    <section className="client-v2-hero">
      <div>
        <small>A+ SOLUTION</small>
        <h2>{nextShift ? 'Der nächste Einsatz ist vorbereitet.' : 'Personal genau dann, wenn du es brauchst.'}</h2>
        <p>{nextShift ? `${nextShift.position_name || 'Einsatz'} · ${dateTime(nextShift.starts_at)} · ${nextShift.location_name || 'Einsatzort'}` : 'Neue Personalaufträge senden, Planung verfolgen und Dokumente sicher abrufen.'}</p>
      </div>
      <button type="button" onClick={() => navigate(nextShift ? 'schedule' : 'orders')}>
        {nextShift ? 'Einsatz ansehen' : 'Personal anfragen'}<IonIcon icon={chevronForwardOutline}/>
      </button>
    </section>

    <section className="client-v2-kpis" aria-label="Kundenportal Übersicht">
      <button type="button" onClick={() => navigate('orders')}><span><IonIcon icon={briefcaseOutline}/></span><b>{openOrders}</b><small>Aktive Aufträge</small></button>
      <button type="button" onClick={() => navigate('schedule')}><span><IonIcon icon={calendarOutline}/></span><b>{upcoming}</b><small>Kommende Einsätze</small></button>
      <button type="button" onClick={() => navigate('contracts')} className={openContracts > 0 ? 'needs-action' : ''}><span><IonIcon icon={documentTextOutline}/></span><b>{openContracts}</b><small>Zu unterzeichnen</small></button>
    </section>

    <section className="client-v2-section client-v2-quick">
      <div className="client-v2-section-head"><div><small>SCHNELLZUGRIFF</small><h2>Was möchtest du erledigen?</h2></div></div>
      <div className="client-v2-action-grid">
        <button type="button" onClick={() => navigate('orders')}><span><IonIcon icon={briefcaseOutline}/></span><div><b>Personal anfragen</b><small>Neuen Auftrag übermitteln</small></div><IonIcon icon={chevronForwardOutline}/></button>
        <button type="button" onClick={() => navigate('documents')}><span><IonIcon icon={folderOpenOutline}/></span><div><b>Dokumente</b><small>Unterlagen öffnen und hochladen</small></div><IonIcon icon={chevronForwardOutline}/></button>
        <button type="button" onClick={() => navigate('operations')}><span><IonIcon icon={shieldCheckmarkOutline}/></span><div><b>Servicecenter</b><small>Status und offene Punkte prüfen</small></div><IonIcon icon={chevronForwardOutline}/></button>
        <button type="button" onClick={() => navigate('messages')}><span><IonIcon icon={megaphoneOutline}/></span><div><b>Mitteilungen</b><small>{unread ? `${unread} ungelesen` : 'Aktuell alles gelesen'}</small></div><IonIcon icon={chevronForwardOutline}/></button>
      </div>
    </section>

    <div className="client-v2-columns">
      <section className="client-v2-section">
        <div className="client-v2-section-head"><div><small>EINSÄTZE</small><h2>Als Nächstes geplant</h2></div><button type="button" onClick={() => navigate('schedule')}>Alle</button></div>
        <div className="client-v2-list">
          {nextShifts.map((shift) => <button type="button" key={shift.id} onClick={() => navigate('schedule')} className="client-v2-list-row">
            <span className="client-v2-date"><b>{new Date(shift.starts_at).toLocaleDateString('de-DE', { day: '2-digit', timeZone: TZ })}</b><small>{new Date(shift.starts_at).toLocaleDateString('de-DE', { month: 'short', timeZone: TZ })}</small></span>
            <div><b>{shift.position_name || 'Einsatz'}</b><small>{dateTime(shift.starts_at)} · {shift.location_name || 'Einsatzort'}</small></div>
            <IonIcon icon={chevronForwardOutline}/>
          </button>)}
          {!nextShifts.length && <div className="client-v2-empty"><IonIcon icon={calendarOutline}/><b>Keine kommenden Einsätze</b><span>Sobald ein Einsatz geplant ist, erscheint er hier.</span></div>}
        </div>
      </section>

      <section className="client-v2-section">
        <div className="client-v2-section-head"><div><small>AKTIONEN</small><h2>Benötigt Aufmerksamkeit</h2></div></div>
        <div className="client-v2-attention">
          <button type="button" onClick={() => navigate('contracts')}><span><IonIcon icon={documentTextOutline}/></span><div><b>Verträge & Signatur</b><small>{openContracts ? `${openContracts} offen` : 'Keine offene Signatur'}</small></div><em>{openContracts || '✓'}</em></button>
          <button type="button" onClick={() => navigate('operations')}><span><IonIcon icon={shieldCheckmarkOutline}/></span><div><b>Servicecenter</b><small>{operations?.open_orders ? `${operations.open_orders} offene Aufträge` : 'Status prüfen'}</small></div><IonIcon icon={chevronForwardOutline}/></button>
          <button type="button" onClick={() => navigate('ratings')}><span><IonIcon icon={peopleOutline}/></span><div><b>Mitarbeiter bewerten</b><small>Nach abgeschlossenem Einsatz</small></div><IonIcon icon={chevronForwardOutline}/></button>
        </div>
      </section>
    </div>

    <section className="client-v2-section client-v2-documents">
      <div className="client-v2-section-head"><div><small>DOKUMENTE</small><h2>Zuletzt bereitgestellt</h2></div><button type="button" onClick={() => navigate('documents')}>Alle öffnen</button></div>
      <div className="client-v2-doc-grid">
        {recentDocuments.map((document) => <button type="button" key={document.id} onClick={() => navigate('documents')}><span><IonIcon icon={documentTextOutline}/></span><div><b>{document.title || 'Dokument'}</b><small>{document.folder || 'Allgemein'} · {document.created_at ? new Date(document.created_at).toLocaleDateString('de-DE', { timeZone: TZ }) : ''}</small></div></button>)}
        {!recentDocuments.length && <div className="client-v2-empty compact"><IonIcon icon={folderOpenOutline}/><span>Noch keine Dokumente bereitgestellt.</span></div>}
      </div>
    </section>
  </div>;
}

function ClientMore({ user, view, close, navigate }: { user: User; view: string; close: () => void; navigate: (view: string) => void }) {
  return <div className="client-v2-more" data-testid="client-v2-more">
    <header><button type="button" onClick={close}>Fertig</button><div><small>KUNDENPORTAL</small><h1>Mehr</h1></div><span className="client-v2-avatar">{user.name?.[0] || 'K'}</span></header>
    <div className="client-v2-more-user"><b>{user.name}</b><span>{user.email}</span></div>
    <div className="client-v2-more-list">
      {more.map(([key, label, icon, description]) => <button type="button" key={key} className={view === key ? 'active' : ''} onClick={() => navigate(key)}>
        <span><IonIcon icon={icon}/></span><div><b>{label}</b><small>{description}</small></div><IonIcon icon={chevronForwardOutline}/>
      </button>)}
    </div>
    <button type="button" className="client-v2-logout" onClick={logout}><IonIcon icon={exitOutline}/>Abmelden</button>
  </div>;
}

export default function ClientPortalV2() {
  const [user, setUser] = useState<User | null>(null);
  const [view, setView] = useState('dashboard');
  const [moreOpen, setMoreOpen] = useState(false);
  const [host, setHost] = useState<HTMLElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!localStorage.getItem('access')) return;
    api('auth/me/').then((current: User) => {
      if (!cancelled && current?.role === 'client') setUser(current);
    }).catch(() => undefined);
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!user) return;
    document.body.classList.add('client-portal-v2-active');
    const sync = () => {
      const shell = document.querySelector<HTMLElement>('.mobile-first-app-shell-v1');
      const nextView = shell?.dataset.view || 'dashboard';
      setView(nextView);
      setHost(document.querySelector<HTMLElement>('.app-main'));
      document.body.classList.toggle('client-portal-v2-dashboard', nextView === 'dashboard');
      if (nextView !== view) setMoreOpen(false);
    };
    sync();
    const root = document.getElementById('root');
    const observer = new MutationObserver(sync);
    if (root) observer.observe(root, { subtree: true, childList: true, attributes: true, attributeFilter: ['data-view'] });
    return () => {
      observer.disconnect();
      document.body.classList.remove('client-portal-v2-active', 'client-portal-v2-dashboard');
    };
  }, [user, view]);

  const navigate = (next: string) => {
    setMoreOpen(false);
    const target = findNavigationTarget(next);
    if (target) {
      target.click();
      return;
    }
    if (next === 'profile') document.querySelector<HTMLElement>('.mobile-avatar')?.click();
  };

  if (!user) return null;

  return <>
    {view === 'dashboard' && host ? createPortal(<ClientHome user={user} navigate={navigate}/>, host) : null}
    <nav className="client-v2-tabbar" aria-label="Kundenportal Navigation" data-testid="client-v2-tabbar" style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))' }}>
      {primary.map(([key, label, icon]) => <button type="button" key={key} className={view === key && !moreOpen ? 'active' : ''} onClick={() => navigate(key)} aria-current={view === key ? 'page' : undefined} aria-label={key === 'ratings' ? 'Mitarbeiter bewerten' : label}><IonIcon icon={icon}/><span>{label}</span></button>)}
      <button type="button" className={moreOpen || !primary.some(([key]) => key === view) ? 'active' : ''} onClick={() => setMoreOpen(true)} aria-label="Weitere Bereiche öffnen"><IonIcon icon={appsOutline}/><span>Mehr</span></button>
    </nav>
    {moreOpen && <ClientMore user={user} view={view} close={() => setMoreOpen(false)} navigate={navigate}/>} 
  </>;
}
