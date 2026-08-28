import React, { useEffect, useMemo, useState } from 'react';
import {
  IonApp,
  IonBadge,
  IonButton,
  IonCard,
  IonCardContent,
  IonContent,
  IonHeader,
  IonIcon,
  IonInput,
  IonItem,
  IonLabel,
  IonList,
  IonModal,
  IonPage,
  IonSelect,
  IonSelectOption,
  IonSpinner,
  IonTextarea,
  IonTitle,
  IonToast,
  IonToggle,
  IonToolbar,
} from '@ionic/react';
import {
  addOutline,
  appsOutline,
  briefcaseOutline,
  businessOutline,
  calendarOutline,
  megaphoneOutline,
  sendOutline,
  checkmarkOutline,
  cloudUploadOutline,
  createOutline,
  documentTextOutline,
  exitOutline,
  homeOutline,
  locationOutline,
  peopleOutline,
  personAddOutline,
  refreshOutline,
  settingsOutline,
  starOutline,
  stopwatchOutline,
  trashOutline,
} from 'ionicons/icons';
import { api, consumeOAuth, login, logout, me, socialUrl, User } from './api';
import Operations from './Operations';
import ScheduleV2 from './ScheduleV2';
import AttendanceV3 from './AttendanceV3';
import ActivationPage from './ActivationPage';
import EmployeeHome from './EmployeeHome';
import AdminHomeV4 from './AdminHomeV4';
import GlobalSearch from './GlobalSearch';
import ListToolbar from './ListToolbar';
import DocumentCenterV5 from './DocumentCenterV5';
import AktePage from './AktePage';
import Settings from './Settings';
import { akteHref, openAkte } from './entityNavigation';

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
  | 'operations'
  | 'settings'
  | 'akte';

const icons: Record<string, string> = {
  dashboard: homeOutline,
  schedule: calendarOutline,
  time: stopwatchOutline,
  contracts: documentTextOutline,
  documents: cloudUploadOutline,
  orders: briefcaseOutline,
  people: peopleOutline,
  messages: megaphoneOutline,
  ranking: starOutline,
  ratings: starOutline,
  profile: peopleOutline,
  operations: refreshOutline,
  settings: settingsOutline,
};

const nav: Record<string, [View, string][]> = {
  // Familiar workflow order inspired by the structure Ashkan and the team already know:
  // Übersicht -> Dienstplan -> Zeiterfassung -> Lohn/Dokumente -> Mitteilungen -> Anfragen -> Stammdaten.
  // A+ specific modules remain available afterwards instead of changing the learned daily workflow.
  admin: [
    ['dashboard', 'Übersicht'],
    ['schedule', 'Dienstplan'],
    ['time', 'Zeiterfassung'],
    ['documents', 'Lohn & Dokumente'],
    ['messages', 'Mitteilungen'],
    ['operations', 'Anfragen, Berichte & Verwaltung'],
    ['people', 'Personal & Kunden'],
    ['settings', 'Einstellungen'],
    ['contracts', 'Verträge & ANÜ'],
  ],
  manager: [
    ['dashboard', 'Übersicht'],
    ['schedule', 'Dienstplan'],
    ['time', 'Zeiterfassung'],
    ['documents', 'Lohn & Dokumente'],
    ['messages', 'Mitteilungen'],
    ['operations', 'Anfragen, Berichte & Verwaltung'],
    ['people', 'Personal & Kunden'],
    ['settings', 'Einstellungen'],
    ['contracts', 'Verträge & ANÜ'],
  ],
  worker: [
    ['dashboard', 'Start'],
    ['schedule', 'Mein Dienstplan'],
    ['time', 'Zeiterfassung'],
    ['messages', 'Mitteilungen'],
    ['operations', 'Anfragen'],
    ['documents', 'Dokumente'],
    ['contracts', 'Meine Verträge'],
    ['ranking', 'Ranking'],
  ],
  client: [
    ['dashboard', 'Start'],
    ['operations', 'Servicecenter'],
    ['orders', 'Aufträge'],
    ['schedule', 'Einsätze'],
    ['contracts', 'Verträge & Signatur'],
    ['documents', 'Dokumente'],
    ['ratings', 'Mitarbeiter bewerten'],
    ['messages', 'Mitteilungen'],
  ],
};

const unpack = (data: any): any[] => data?.results || data || [];
const value = (event: any) => event.detail.value ?? '';
const isManager = (user: User) => ['admin', 'manager'].includes(user.role);
const BUSINESS_TIME_ZONE = 'Europe/Berlin';
const dateTime = (input?: string) =>
  input ? new Date(input).toLocaleString('de-DE', { timeZone: BUSINESS_TIME_ZONE }) : '–';
const dateOnly = (input?: string) => (input ? new Date(input).toLocaleDateString('de-DE') : '–');
const statusText: Record<string, string> = {
  draft: 'Entwurf',
  published: 'Veröffentlicht',
  confirmed: 'Bestätigt',
  completed: 'Abgeschlossen',
  cancelled: 'Storniert',
  new: 'Neu',
  planning: 'In Planung',
  done: 'Abgeschlossen',
  pending: 'Offen',
  approved: 'Genehmigt',
  rejected: 'Abgelehnt',
  ready: 'Prüfbereit',
  sent: 'Versendet',
  signed: 'Unterzeichnet',
  expired: 'Abgelaufen',
};

function Login({ done }: { done: (user: User) => void }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit() {
    setBusy(true);
    setError('');
    try {
      done(await login(email, password));
    } catch (reason: any) {
      setError(reason.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <IonPage>
      <IonContent fullscreen className="login">
        <div className="login-grid">
          <section className="brand">
            <div className="logo">A+</div>
            <small>A+ SOLUTION GMBH</small>
            <h1>
              Menschen. Einsätze.
              <br />
              Alles in einer App.
            </h1>
            <p>Dienstplanung, Arbeitszeiten, Verträge und Dokumente für Mitarbeiter und Kunden.</p>
          </section>
          <section className="login-card">
            <h2>Willkommen zurück</h2>
            <p>Melde dich in deinem Portal an.</p>
            {error && <div className="error">{error}</div>}
            <IonInput
              fill="outline"
              label="E-Mail-Adresse"
              labelPlacement="floating"
              value={email}
              onIonInput={(event) => setEmail(String(value(event)))}
            />
            <IonInput
              fill="outline"
              type="password"
              label="Passwort"
              labelPlacement="floating"
              value={password}
              onIonInput={(event) => setPassword(String(value(event)))}
            />
            <IonButton expand="block" size="large" onClick={submit}>
              {busy ? <IonSpinner /> : 'Anmelden'}
            </IonButton>
            <div className="or">oder</div>
            <IonButton expand="block" fill="outline" href={socialUrl('google')}>
              Mit Google anmelden
            </IonButton>
            <IonButton expand="block" className="apple" href={socialUrl('apple')}>
              Mit Apple anmelden
            </IonButton>
            <small>Mit der Anmeldung akzeptierst du Datenschutz und Nutzungsbedingungen.</small>
          </section>
        </div>
      </IonContent>
    </IonPage>
  );
}

function Header({ title, appShell = false }: { title: string; appShell?: boolean }) {
  return (
    <IonHeader className={appShell ? 'app-header' : ''}>
      <IonToolbar>
        <IonTitle>{title}</IonTitle>
      </IonToolbar>
    </IonHeader>
  );
}

function Title({
  title,
  text,
  action,
}: {
  title: string;
  text?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="title">
      <div>
        <h1>{title}</h1>
        {text && <p>{text}</p>}
      </div>
      {action}
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="empty">{children}</div>;
}

function Loader() {
  return (
    <div className="loader">
      <IonSpinner />
      <p>Daten werden geladen …</p>
    </div>
  );
}

function FormModal({
  open,
  title,
  onClose,
  onSave,
  busy,
  saveLabel = 'Speichern',
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  onSave: () => void;
  busy?: boolean;
  saveLabel?: string;
  children: React.ReactNode;
}) {
  return (
    <IonModal isOpen={open} onDidDismiss={onClose}>
      <IonContent className="ion-padding form">
        <div className="modal-head">
          <div>
            <small>A+ WORKFORCE</small>
            <h2>{title}</h2>
          </div>
          <IonButton fill="clear" onClick={onClose}>
            Schließen
          </IonButton>
        </div>
        <div className="form-grid">{children}</div>
        <div className="modal-actions">
          <IonButton fill="outline" onClick={onClose}>
            Abbrechen
          </IonButton>
          <IonButton disabled={busy} onClick={onSave}>
            {busy ? <IonSpinner name="dots" /> : saveLabel}
          </IonButton>
        </div>
      </IonContent>
    </IonModal>
  );
}

function CredentialNotice({
  data,
  close,
}: {
  data: any;
  close: () => void;
}) {
  if (!data) return null;
  const rows = [...(data.temporary_credentials || data.credentials || [])];
  if (data.email && data.password) rows.push(data);
  return (
    <IonModal isOpen={!!data} onDidDismiss={close}>
      <IonContent className="ion-padding">
        <div className="modal-head">
          <div>
            <small>ZUGANGSDATEN</small>
            <h2>Temporäre Zugangsdaten</h2>
          </div>
          <IonButton fill="clear" onClick={close}>
            Fertig
          </IonButton>
        </div>
        <p className="notice">
          Diese Passwörter werden nur jetzt angezeigt. Bitte sicher an die jeweilige Person übermitteln.
        </p>
        <div className="panel">
          {rows.length ? (
            rows.map((row: any) => (
              <div className="credential" key={`${row.email}-${row.password}`}>
                <div>
                  <b>{row.email}</b>
                  <code>{row.password}</code>
                </div>
                <IonButton
                  fill="outline"
                  size="small"
                  onClick={() => navigator.clipboard?.writeText(`${row.email}\n${row.password}`)}
                >
                  Kopieren
                </IonButton>
              </div>
            ))
          ) : (
            <Empty>Der Datensatz wurde ohne neues Benutzerkonto erstellt.</Empty>
          )}
        </div>
      </IonContent>
    </IonModal>
  );
}

function Dashboard({
  user,
  navigate,
}: {
  user: User;
  navigate: (view: View) => void;
}) {
  const [data, setData] = useState<any>();
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState('');
  const [credentials, setCredentials] = useState<any>();

  const load = () => api(user.role === 'client' ? 'portal/client-dashboard/' : 'dashboard/').then(setData);
  useEffect(() => {
    void load();
  }, []);

  async function createDemo() {
    if (!window.confirm('Demodaten mit drei Mitarbeitern, einem Kunden und mehreren Einsätzen erstellen?')) return;
    setBusy(true);
    try {
      const result: any = await api('setup/demo/', { method: 'POST', body: '{}' });
      setToast(result.detail);
      if (result.temporary_credentials?.length) setCredentials(result);
      await load();
    } catch (reason: any) {
      setToast(reason.message);
    } finally {
      setBusy(false);
    }
  }

  if (!data) return <Loader />;

  const cards =
    user.role === 'worker'
      ? [
          ['Monatsstunden', `${Math.floor((data.worked_minutes || 0) / 60)} Std.`],
          ['Ranking', `${data.ranking_points || 0} P.`],
          ['Offene Schichten', data.open_shifts],
          ['Nächste Einsätze', data.next_shifts?.length || 0],
        ]
      : user.role === 'client'
        ? [
            ['Aktive Aufträge', data.active_orders],
            ['Kommende Einsätze', data.upcoming_shifts],
            ['Zu unterzeichnen', data.contracts_to_sign],
          ]
        : [
            ['Mitarbeiter', data.workers],
            ['Kunden', data.clients],
            ['Offene Schichten', data.open_shifts],
            ['Abwesenheiten', data.pending_time_off],
            ['Vertragsfristen', data.contracts_due],
          ];

  const emptySystem = isManager(user) && !data.workers && !data.clients;

  return (
    <>
      <Title title={`Guten Tag, ${user.first_name || user.name}`} text="Hier ist dein aktueller Überblick." />
      <div className="hero">
        <small>A+ WORKFORCE</small>
        <h2>
          {user.role === 'worker'
            ? 'Deine nächste Schicht auf einen Blick.'
            : user.role === 'client'
              ? 'Personal genau dann, wenn du es brauchst.'
              : 'Alles unter Kontrolle – von der Anfrage bis zur Abrechnung.'}
        </h2>
        <span>● System aktiv</span>
      </div>
      {isManager(user) && (
        <div className="button-group priority-actions">
          <IonButton fill="outline" onClick={() => navigate('schedule')}><IonIcon slot="start" icon={calendarOutline} />Dienstplan</IonButton>
          <IonButton fill="outline" onClick={() => navigate('time')}><IonIcon slot="start" icon={stopwatchOutline} />Zeiterfassung</IonButton>
          <IonButton fill="outline" onClick={() => navigate('people')}><IonIcon slot="start" icon={peopleOutline} />Personal</IonButton>
          <IonButton fill="clear" href="?view=operations#arbeitszeitkonto">Arbeitszeit & Lohn</IonButton>
        </div>
      )}
      <div className="stats">
        {cards.map((entry: any[]) => (
          <IonCard key={entry[0]}>
            <IonCardContent>
              <small>{entry[0]}</small>
              <strong>{entry[1] ?? 0}</strong>
            </IonCardContent>
          </IonCard>
        ))}
      </div>

      {emptySystem && (
        <section className="setup-card">
          <div className="setup-copy">
            <small>ERSTE SCHRITTE</small>
            <h2>Das System ist bereit – jetzt Stammdaten anlegen.</h2>
            <p>
              Lege zuerst Mitarbeiter und Kunden an. Danach kannst du Einsatzorte, Aufträge,
              Schichten, Verträge und Dokumente direkt miteinander verbinden.
            </p>
          </div>
          <div className="setup-actions">
            <IonButton onClick={() => navigate('people')}>
              <IonIcon slot="start" icon={personAddOutline} />
              Stammdaten anlegen
            </IonButton>
            <IonButton fill="outline" disabled={busy} onClick={createDemo}>
              <IonIcon slot="start" icon={refreshOutline} />
              Demodaten erstellen
            </IonButton>
          </div>
        </section>
      )}

      {isManager(user) && data.upcoming_shifts?.length > 0 && (
        <div className="panel">
          <div className="section-head">
            <div>
              <h3>Nächste Einsätze</h3>
              <p>Die nächsten geplanten Schichten im Unternehmen.</p>
            </div>
            <IonButton fill="clear" onClick={() => navigate('schedule')}>
              Alle anzeigen
            </IonButton>
          </div>
          {data.upcoming_shifts.map((shift: any) => (
            <div className="row" key={shift.id}>
              <div className="date">
                <b>{new Date(shift.starts_at).getDate()}</b>
                <span>{new Date(shift.starts_at).toLocaleString('de-DE', { month: 'short' })}</span>
              </div>
              <div className="grow">
                <b>{shift.position_name || 'Einsatz'}</b>
                <p>
                  {shift.client_name} · {shift.location_name} · {dateTime(shift.starts_at)}
                </p>
              </div>
              <IonBadge>{shift.worker_name || 'OpenShift'}</IonBadge>
            </div>
          ))}
        </div>
      )}

      <CredentialNotice data={credentials} close={() => setCredentials(undefined)} />
      <IonToast isOpen={!!toast} message={toast} duration={3500} onDidDismiss={() => setToast('')} />
    </>
  );
}

function People({ user }: { user: User }) {
  const [workers, setWorkers] = useState<any[]>([]);
  const [clients, setClients] = useState<any[]>([]);
  const [locations, setLocations] = useState<any[]>([]);
  const [positions, setPositions] = useState<any[]>([]);
  const [modal, setModal] = useState('');
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState('');
  const [credentials, setCredentials] = useState<any>();
  const [csvFile, setCsvFile] = useState<File>();
  const [csvType, setCsvType] = useState('workers');
  const [listQuery, setListQuery] = useState('');
  const [listSort, setListSort] = useState('name');
  const [peopleKind, setPeopleKind] = useState<'workers' | 'clients'>(() => new URLSearchParams(window.location.search).get('people_kind') === 'clients' ? 'clients' : 'workers');

  const [workerForm, setWorkerForm] = useState<any>({
    employment_type: 'minijob',
    extra_allowance: 0,
  });
  const [clientForm, setClientForm] = useState<any>({});
  const [locationForm, setLocationForm] = useState<any>({ geofence_radius_m: 250 });
  const [positionForm, setPositionForm] = useState<any>({ color: '#155eef' });

  const load = async () => {
    const search = listQuery.trim() ? `&search=${encodeURIComponent(listQuery.trim())}` : '';
    const workerOrdering = listSort === 'number' ? 'employee_number' : 'user__last_name';
    const clientOrdering = listSort === 'number' ? 'customer_number' : 'name';
    const [workerData, clientData, locationData, positionData] = await Promise.all([
      api(`workers/?ordering=${workerOrdering}${search}`),
      api(`clients/?ordering=${clientOrdering}${search}`),
      api('locations/'),
      api('positions/'),
    ]);
    setWorkers(unpack(workerData));
    setClients(unpack(clientData));
    setLocations(unpack(locationData));
    setPositions(unpack(positionData));
  };

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), listQuery ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [listQuery, listSort]);

  async function submit(path: string, payload: any, done: () => void) {
    setBusy(true);
    try {
      const result: any = await api(path, { method: 'POST', body: JSON.stringify(payload) });
      if (result.temporary_password) {
        setCredentials({
          credentials: [
            {
              email: payload.email || payload.contact_email,
              password: result.temporary_password,
            },
          ],
        });
      }
      done();
      setModal('');
      await load();
      setToast('Datensatz wurde gespeichert.');
    } catch (reason: any) {
      setToast(reason.message);
    } finally {
      setBusy(false);
    }
  }

  async function archive(kind: 'workers' | 'clients', id: string) {
    if (!window.confirm('Diesen Datensatz deaktivieren?')) return;
    try {
      await api(`${kind}/${id}/archive/`, { method: 'POST', body: '{}' });
      await load();
      setToast('Datensatz wurde deaktiviert.');
    } catch (reason: any) {
      setToast(reason.message);
    }
  }

  async function remove(kind: 'locations' | 'positions', id: string) {
    if (!window.confirm('Diesen Stammdatensatz wirklich löschen?')) return;
    try {
      await api(`${kind}/${id}/`, { method: 'DELETE' });
      await load();
      setToast('Datensatz wurde gelöscht.');
    } catch (reason: any) {
      setToast(reason.message);
    }
  }

  async function importCsv() {
    if (!csvFile) return;
    setBusy(true);
    const form = new FormData();
    form.append('file', csvFile);
    try {
      const result: any = await api(`${csvType}/import_csv/`, { method: 'POST', body: form });
      setToast(`${result.created} Datensätze importiert. ${result.errors?.length || 0} Fehler.`);
      if (result.credentials?.length) setCredentials(result);
      setModal('');
      setCsvFile(undefined);
      await load();
    } catch (reason: any) {
      setToast(reason.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Title
        title="Personal & Kunden"
        text="Mitarbeiter- und Kundenprofile zentral verwalten."
        action={
          isManager(user) ? (
            <div className="button-group">
              <IonButton onClick={() => setModal('worker')}>
                <IonIcon slot="start" icon={personAddOutline} />
                Mitarbeiter
              </IonButton>
              <IonButton fill="outline" onClick={() => setModal('client')}>
                <IonIcon slot="start" icon={businessOutline} />
                Kunde
              </IonButton>
            </div>
          ) : undefined
        }
      />

      <div className="people-kind-filter" data-testid="people-kind-filter" role="group" aria-label="Akte filtern">
        <button type="button" className={peopleKind === 'workers' ? 'active' : ''} aria-pressed={peopleKind === 'workers'} onClick={() => { setPeopleKind('workers'); const url = new URL(window.location.href); url.searchParams.set('people_kind', 'workers'); window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}`); }}><IonIcon icon={peopleOutline}/>Mitarbeiter <span>{workers.filter((worker) => worker.active).length}</span></button>
        <button type="button" className={peopleKind === 'clients' ? 'active' : ''} aria-pressed={peopleKind === 'clients'} onClick={() => { setPeopleKind('clients'); const url = new URL(window.location.href); url.searchParams.set('people_kind', 'clients'); window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}`); }}><IonIcon icon={businessOutline}/>Kunden <span>{clients.filter((client) => client.active).length}</span></button>
      </div>

      <ListToolbar
        query={listQuery}
        onQuery={setListQuery}
        placeholder={peopleKind === 'workers' ? 'Mitarbeiter suchen …' : 'Kunden suchen …'}
        sort={listSort}
        onSort={setListSort}
        sortOptions={[{ value: 'name', label: 'Nach Name' }, { value: 'number', label: 'Nach Nummer' }]}
        count={peopleKind === 'workers' ? workers.length : clients.filter((client) => client.active).length}
      />

      <div className="columns people-directory-columns">
        {peopleKind === 'workers' ? <div className="panel" data-testid="people-workers-list">
          <div className="section-head"><div><h3>Mitarbeiter</h3><p>{workers.filter((worker) => worker.active).length} aktive Profile</p></div></div>
          {workers.length ? workers.map((worker) => <div className={`row ${worker.active ? '' : 'muted-row'}`} key={worker.id}>
            <div className="avatar">{worker.user_detail?.name?.[0] || 'M'}</div>
            <div className="grow"><a className="entity-name-link" href={akteHref('worker', worker.id)} onClick={(event) => { event.preventDefault(); openAkte('worker', worker.id); }}>{worker.user_detail?.name || worker.user_detail?.email}</a><p>{worker.employee_number} · {worker.employment_type} · {worker.user_detail?.email}</p></div>
            <strong>{worker.ranking_points} P.</strong>
            {isManager(user) && worker.active && <IonButton fill="clear" color="danger" onClick={() => archive('workers', worker.id)}>Deaktivieren</IonButton>}
          </div>) : <Empty>Noch keine Mitarbeiter. Über „Mitarbeiter“ legst du das erste Profil an.</Empty>}
        </div> : <div className="panel" data-testid="people-clients-list">
          <div className="section-head"><div><h3>Kunden</h3><p>{clients.filter((client) => client.active).length} aktive Unternehmen</p></div></div>
          {clients.filter((client) => client.active).length ? clients.filter((client) => client.active).map((client) => <div className="row" key={client.id}>
            <div className="avatar">{client.name?.[0] || 'K'}</div>
            <div className="grow"><a className="entity-name-link" href={akteHref('client', client.id)} onClick={(event) => { event.preventDefault(); openAkte('client', client.id); }}>{client.name}</a><p>{client.customer_number}{client.contacts_detail?.[0]?.email ? ` · ${client.contacts_detail[0].email}` : ''}</p></div>
            {isManager(user) && client.active && <IonButton fill="clear" color="danger" onClick={() => archive('clients', client.id)}>Deaktivieren</IonButton>}
          </div>) : <Empty>Noch keine Kundenunternehmen angelegt.</Empty>}
        </div>}
      </div>

      <FormModal
        open={modal === 'worker'}
        title="Neuen Mitarbeiter anlegen"
        onClose={() => setModal('')}
        onSave={() =>
          submit('workers/onboard/', workerForm, () =>
            setWorkerForm({ employment_type: 'minijob', extra_allowance: 0 }),
          )
        }
        busy={busy}
      >
        <IonInput
          fill="outline"
          label="Vorname"
          labelPlacement="floating"
          value={workerForm.first_name}
          onIonInput={(event) => setWorkerForm({ ...workerForm, first_name: value(event) })}
        />
        <IonInput
          fill="outline"
          label="Nachname"
          labelPlacement="floating"
          value={workerForm.last_name}
          onIonInput={(event) => setWorkerForm({ ...workerForm, last_name: value(event) })}
        />
        <IonInput
          fill="outline"
          type="email"
          label="E-Mail-Adresse *"
          labelPlacement="floating"
          value={workerForm.email}
          onIonInput={(event) => setWorkerForm({ ...workerForm, email: value(event) })}
        />
        <IonInput
          fill="outline"
          label="Telefon"
          labelPlacement="floating"
          value={workerForm.phone}
          onIonInput={(event) => setWorkerForm({ ...workerForm, phone: value(event) })}
        />
        <IonInput
          fill="outline"
          label="Personalnummer (automatisch, wenn leer)"
          labelPlacement="floating"
          value={workerForm.employee_number}
          onIonInput={(event) => setWorkerForm({ ...workerForm, employee_number: value(event) })}
        />
        <IonSelect
          fill="outline"
          label="Beschäftigungsart"
          labelPlacement="floating"
          value={workerForm.employment_type}
          onIonChange={(event) => setWorkerForm({ ...workerForm, employment_type: value(event) })}
        >
          <IonSelectOption value="minijob">Minijob</IonSelectOption>
          <IonSelectOption value="teilzeit">Teilzeit</IonSelectOption>
          <IonSelectOption value="vollzeit">Vollzeit</IonSelectOption>
          <IonSelectOption value="student">Studentische Aushilfe</IonSelectOption>
        </IonSelect>
        <IonInput
          fill="outline"
          type="number"
          label="Monatsstunden"
          labelPlacement="floating"
          value={workerForm.monthly_hours}
          onIonInput={(event) => setWorkerForm({ ...workerForm, monthly_hours: value(event) })}
        />
        <IonInput
          fill="outline"
          type="number"
          label="Stundenlohn (€)"
          labelPlacement="floating"
          value={workerForm.tariff_hourly_rate}
          onIonInput={(event) => setWorkerForm({ ...workerForm, tariff_hourly_rate: value(event) })}
        />
        <IonInput
          fill="outline"
          type="number"
          label="Übertarifliche Zulage (€)"
          labelPlacement="floating"
          value={workerForm.extra_allowance}
          onIonInput={(event) => setWorkerForm({ ...workerForm, extra_allowance: value(event) })}
        />
        <IonInput
          fill="outline"
          type="password"
          label="Temporäres Passwort (automatisch, wenn leer)"
          labelPlacement="floating"
          value={workerForm.password}
          onIonInput={(event) => setWorkerForm({ ...workerForm, password: value(event) })}
        />
      </FormModal>

      <FormModal
        open={modal === 'client'}
        title="Neuen Kunden anlegen"
        onClose={() => setModal('')}
        onSave={() => submit('clients/onboard/', clientForm, () => setClientForm({ contract_visibility_enabled: true }))}
        busy={busy}
      >
        <IonInput
          fill="outline"
          label="Firmenname *"
          labelPlacement="floating"
          value={clientForm.name}
          onIonInput={(event) => setClientForm({ ...clientForm, name: value(event) })}
        />
        <IonInput
          fill="outline"
          label="Kundennummer (automatisch, wenn leer)"
          labelPlacement="floating"
          value={clientForm.customer_number}
          onIonInput={(event) => setClientForm({ ...clientForm, customer_number: value(event) })}
        />
        <IonTextarea
          fill="outline"
          label="Adresse"
          labelPlacement="floating"
          value={clientForm.address}
          onIonInput={(event) => setClientForm({ ...clientForm, address: value(event) })}
        />
        <IonInput
          fill="outline"
          label="USt-IdNr."
          labelPlacement="floating"
          value={clientForm.vat_id}
          onIonInput={(event) => setClientForm({ ...clientForm, vat_id: value(event) })}
        />
        <IonItem lines="none" className="toggle-field">
          <IonLabel>Vertragsunterlagen im Kundenportal sichtbar</IonLabel>
          <IonToggle checked={clientForm.contract_visibility_enabled !== false} onIonChange={(event) => setClientForm({ ...clientForm, contract_visibility_enabled: event.detail.checked })} />
        </IonItem>
        <div className="form-divider">Portal-Zugang für Ansprechpartner</div>
        <IonInput
          fill="outline"
          label="Vorname"
          labelPlacement="floating"
          value={clientForm.contact_first_name}
          onIonInput={(event) => setClientForm({ ...clientForm, contact_first_name: value(event) })}
        />
        <IonInput
          fill="outline"
          label="Nachname"
          labelPlacement="floating"
          value={clientForm.contact_last_name}
          onIonInput={(event) => setClientForm({ ...clientForm, contact_last_name: value(event) })}
        />
        <IonInput
          fill="outline"
          type="email"
          label="Kontakt-E-Mail"
          labelPlacement="floating"
          value={clientForm.contact_email}
          onIonInput={(event) => setClientForm({ ...clientForm, contact_email: value(event) })}
        />
        <IonInput
          fill="outline"
          label="Telefon"
          labelPlacement="floating"
          value={clientForm.contact_phone}
          onIonInput={(event) => setClientForm({ ...clientForm, contact_phone: value(event) })}
        />
        <IonTextarea
          fill="outline"
          label="Interne Notizen"
          labelPlacement="floating"
          value={clientForm.notes}
          onIonInput={(event) => setClientForm({ ...clientForm, notes: value(event) })}
        />
      </FormModal>

      <FormModal
        open={modal === 'location'}
        title="Einsatzort anlegen"
        onClose={() => setModal('')}
        onSave={() =>
          submit(
            'locations/',
            { ...locationForm, client: locationForm.client || null },
            () => setLocationForm({ geofence_radius_m: 250 }),
          )
        }
        busy={busy}
      >
        <IonSelect
          fill="outline"
          label="Kunde"
          labelPlacement="floating"
          value={locationForm.client}
          onIonChange={(event) => setLocationForm({ ...locationForm, client: value(event) })}
        >
          <IonSelectOption value="">Ohne feste Zuordnung</IonSelectOption>
          {clients.filter((client) => client.active).map((client) => (
            <IonSelectOption value={client.id} key={client.id}>
              {client.name}
            </IonSelectOption>
          ))}
        </IonSelect>
        <IonInput
          fill="outline"
          label="Bezeichnung *"
          labelPlacement="floating"
          value={locationForm.name}
          onIonInput={(event) => setLocationForm({ ...locationForm, name: value(event) })}
        />
        <IonTextarea
          fill="outline"
          label="Adresse *"
          labelPlacement="floating"
          value={locationForm.address}
          onIonInput={(event) => setLocationForm({ ...locationForm, address: value(event) })}
        />
        <IonInput
          fill="outline"
          type="number"
          label="Geofence-Radius in Metern"
          labelPlacement="floating"
          value={locationForm.geofence_radius_m}
          onIonInput={(event) => setLocationForm({ ...locationForm, geofence_radius_m: value(event) })}
        />
      </FormModal>

      <FormModal
        open={modal === 'position'}
        title="Position anlegen"
        onClose={() => setModal('')}
        onSave={() => submit('positions/', positionForm, () => setPositionForm({ color: '#155eef' }))}
        busy={busy}
      >
        <IonInput
          fill="outline"
          label="Bezeichnung *"
          labelPlacement="floating"
          value={positionForm.name}
          onIonInput={(event) => setPositionForm({ ...positionForm, name: value(event) })}
        />
        <IonInput
          fill="outline"
          {...({ type: 'color' } as any)}
          label="Farbe"
          labelPlacement="floating"
          value={positionForm.color}
          onIonInput={(event) => setPositionForm({ ...positionForm, color: value(event) })}
        />
      </FormModal>

      <FormModal
        open={modal === 'csv'}
        title="Stammdaten aus CSV importieren"
        onClose={() => setModal('')}
        onSave={importCsv}
        busy={busy}
        saveLabel="Importieren"
      >
        <IonSelect
          fill="outline"
          label="Datentyp"
          labelPlacement="floating"
          value={csvType}
          onIonChange={(event) => setCsvType(String(value(event)))}
        >
          <IonSelectOption value="workers">Mitarbeiter</IonSelectOption>
          <IonSelectOption value="clients">Kunden</IonSelectOption>
        </IonSelect>
        <label className="file-field">
          <span>CSV-Datei auswählen</span>
          <input type="file" accept=".csv,text/csv" onChange={(event) => setCsvFile(event.target.files?.[0])} />
          <b>{csvFile?.name || 'Keine Datei ausgewählt'}</b>
        </label>
        <div className="csv-help">
          <b>Mitarbeiter-Spalten:</b> first_name, last_name, email, phone, employee_number,
          employment_type, monthly_hours, tariff_hourly_rate, extra_allowance
          <br />
          <b>Kunden-Spalten:</b> name, customer_number, address, vat_id, contact_first_name,
          contact_last_name, contact_email, contact_phone
        </div>
      </FormModal>

      <CredentialNotice data={credentials} close={() => setCredentials(undefined)} />
      <IonToast isOpen={!!toast} message={toast} duration={4000} onDidDismiss={() => setToast('')} />
    </>
  );
}

function Schedule({ user }: { user: User }) {
  const [rows, setRows] = useState<any[]>([]);
  const [workers, setWorkers] = useState<any[]>([]);
  const [clients, setClients] = useState<any[]>([]);
  const [locations, setLocations] = useState<any[]>([]);
  const [positions, setPositions] = useState<any[]>([]);
  const [orders, setOrders] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState('');
  const [form, setForm] = useState<any>({
    break_minutes: 0,
    required_count: 1,
    status: 'draft',
    is_open: false,
  });

  const load = async () => {
    const shiftData = await api('shifts/?ordering=starts_at');
    setRows(unpack(shiftData));
    if (isManager(user)) {
      const [workerData, clientData, locationData, positionData, orderData] = await Promise.all([
        api('workers/'),
        api('clients/'),
        api('locations/'),
        api('positions/'),
        api('orders/'),
      ]);
      setWorkers(unpack(workerData).filter((worker: any) => worker.active));
      setClients(unpack(clientData).filter((client: any) => client.active));
      setLocations(unpack(locationData).filter((location: any) => location.active));
      setPositions(unpack(positionData).filter((position: any) => position.active));
      setOrders(unpack(orderData));
    }
  };

  useEffect(() => {
    void load();
  }, []);

  function newShift() {
    setEditing(undefined);
    setForm({ break_minutes: 0, required_count: 1, status: 'draft', is_open: false });
    setOpen(true);
  }

  function editShift(shift: any) {
    setEditing(shift.id);
    setForm({
      ...shift,
      starts_at: shift.starts_at?.slice(0, 16),
      ends_at: shift.ends_at?.slice(0, 16),
    });
    setOpen(true);
  }

  async function save() {
    setBusy(true);
    const payload = {
      ...form,
      worker: form.worker || null,
      order: form.order || null,
      status: form.is_open ? 'published' : form.worker ? 'confirmed' : form.status || 'draft',
    };
    try {
      await api(editing ? `shifts/${editing}/` : 'shifts/', {
        method: editing ? 'PATCH' : 'POST',
        body: JSON.stringify(payload),
      });
      setOpen(false);
      setToast(editing ? 'Schicht wurde aktualisiert.' : 'Schicht wurde angelegt.');
      await load();
    } catch (reason: any) {
      setToast(reason.message);
    } finally {
      setBusy(false);
    }
  }

  async function claim(id: string) {
    try {
      await api(`shifts/${id}/claim/`, { method: 'POST', body: '{}' });
      setToast('Schicht wurde übernommen.');
      await load();
    } catch (reason: any) {
      setToast(reason.message);
    }
  }

  async function publish(id: string) {
    try {
      await api(`shifts/${id}/publish/`, { method: 'POST', body: '{}' });
      setToast('Schicht wurde veröffentlicht.');
      await load();
    } catch (reason: any) {
      setToast(reason.message);
    }
  }

  async function assign(shiftId: string, workerId: string) {
    try {
      await api(`shifts/${shiftId}/assign/`, {
        method: 'POST',
        body: JSON.stringify({ worker: workerId }),
      });
      setToast('Mitarbeiter wurde zugeteilt.');
      await load();
    } catch (reason: any) {
      setToast(reason.message);
    }
  }

  async function remove(id: string) {
    if (!window.confirm('Diese Schicht löschen?')) return;
    try {
      await api(`shifts/${id}/`, { method: 'DELETE' });
      await load();
      setToast('Schicht wurde gelöscht.');
    } catch (reason: any) {
      setToast(reason.message);
    }
  }

  const grouped = useMemo(() => {
    const result: Record<string, any[]> = {};
    rows.forEach((shift) => {
      const key = new Date(shift.starts_at).toLocaleDateString('de-DE', {
        weekday: 'long',
        day: '2-digit',
        month: 'long',
      });
      result[key] = [...(result[key] || []), shift];
    });
    return result;
  }, [rows]);

  return (
    <>
      <Title
        title={user.role === 'worker' ? 'Mein Dienstplan' : 'Dienstplanung'}
        text={
          isManager(user)
            ? 'Schichten erstellen, veröffentlichen und Mitarbeiter per Drag & Drop zuteilen.'
            : 'Deine bestätigten Einsätze und verfügbare OpenShifts.'
        }
        action={
          isManager(user) ? (
            <IonButton onClick={newShift}>
              <IonIcon slot="start" icon={addOutline} />
              Neue Schicht
            </IonButton>
          ) : undefined
        }
      />

      <div className={isManager(user) ? 'schedule-layout' : ''}>
        {isManager(user) && (
          <aside className="worker-pool">
            <h3>Mitarbeiter-Pool</h3>
            <p>Person auf eine Schicht ziehen.</p>
            {workers.map((worker) => (
              <div
                className="worker-card"
                draggable
                key={worker.id}
                onDragStart={(event) => event.dataTransfer.setData('worker', worker.id)}
              >
                <div className="avatar">{worker.user_detail?.name?.[0] || 'M'}</div>
                <div>
                  <b>{worker.user_detail?.name}</b>
                  <small>{worker.employee_number}</small>
                </div>
              </div>
            ))}
          </aside>
        )}

        <div className="schedule-days">
          {Object.entries(grouped).map(([day, shifts]) => (
            <section className="day-block" key={day}>
              <h3>{day}</h3>
              {(shifts as any[]).map((shift) => (
                <div
                  className={`shift-card ${shift.is_open ? 'open-shift' : ''}`}
                  key={shift.id}
                  onDragOver={(event) => event.preventDefault()}
                  onDrop={(event) => {
                    event.preventDefault();
                    const workerId = event.dataTransfer.getData('worker');
                    if (workerId) void assign(shift.id, workerId);
                  }}
                >
                  <div className="shift-time">
                    <b>
                      {new Date(shift.starts_at).toLocaleTimeString('de-DE', {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </b>
                    <span>
                      bis{' '}
                      {new Date(shift.ends_at).toLocaleTimeString('de-DE', {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                  </div>
                  <div className="grow">
                    <b>{shift.position_name || 'Einsatz'}</b>
                    <p>
                      {shift.client_name} · {shift.location_name}
                    </p>
                    <small>
                      {shift.worker_name || 'Noch nicht besetzt'} · {shift.break_minutes} Min. Pause
                    </small>
                  </div>
                  <IonBadge>{statusText[shift.status] || shift.status}</IonBadge>
                  {user.role === 'worker' && shift.is_open && (
                    <IonButton size="small" onClick={() => claim(shift.id)}>
                      Übernehmen
                    </IonButton>
                  )}
                  {isManager(user) && (
                    <div className="row-actions">
                      {shift.status === 'draft' && (
                        <IonButton fill="clear" size="small" onClick={() => publish(shift.id)}>
                          Veröffentlichen
                        </IonButton>
                      )}
                      <IonButton fill="clear" size="small" onClick={() => editShift(shift)}>
                        <IonIcon icon={createOutline} />
                      </IonButton>
                      <IonButton fill="clear" color="danger" size="small" onClick={() => remove(shift.id)}>
                        <IonIcon icon={trashOutline} />
                      </IonButton>
                    </div>
                  )}
                </div>
              ))}
            </section>
          ))}
          {!rows.length && <div className="panel"><Empty>Keine Einsätze vorhanden.</Empty></div>}
        </div>
      </div>

      <FormModal
        open={open}
        title={editing ? 'Schicht bearbeiten' : 'Neue Schicht'}
        onClose={() => setOpen(false)}
        onSave={save}
        busy={busy}
      >
        <IonSelect
          fill="outline"
          label="Kunde *"
          labelPlacement="floating"
          value={form.client}
          onIonChange={(event) => setForm({ ...form, client: value(event) })}
        >
          {clients.map((client) => (
            <IonSelectOption value={client.id} key={client.id}>
              {client.name}
            </IonSelectOption>
          ))}
        </IonSelect>
        <IonSelect
          fill="outline"
          label="Einsatzort *"
          labelPlacement="floating"
          value={form.location}
          onIonChange={(event) => setForm({ ...form, location: value(event) })}
        >
          {locations
            .filter((location) => !form.client || !location.client || location.client === form.client)
            .map((location) => (
              <IonSelectOption value={location.id} key={location.id}>
                {location.name}
              </IonSelectOption>
            ))}
        </IonSelect>
        <IonSelect
          fill="outline"
          label="Position *"
          labelPlacement="floating"
          value={form.position}
          onIonChange={(event) => setForm({ ...form, position: value(event) })}
        >
          {positions.map((position) => (
            <IonSelectOption value={position.id} key={position.id}>
              {position.name}
            </IonSelectOption>
          ))}
        </IonSelect>
        <IonSelect
          fill="outline"
          label="Auftrag"
          labelPlacement="floating"
          value={form.order}
          onIonChange={(event) => setForm({ ...form, order: value(event) })}
        >
          <IonSelectOption value="">Ohne Auftrag</IonSelectOption>
          {orders.map((order) => (
            <IonSelectOption value={order.id} key={order.id}>
              {order.title}
            </IonSelectOption>
          ))}
        </IonSelect>
        <IonInput
          fill="outline"
          type="datetime-local"
          label="Beginn *"
          labelPlacement="floating"
          value={form.starts_at}
          onIonInput={(event) => setForm({ ...form, starts_at: value(event) })}
        />
        <IonInput
          fill="outline"
          type="datetime-local"
          label="Ende *"
          labelPlacement="floating"
          value={form.ends_at}
          onIonInput={(event) => setForm({ ...form, ends_at: value(event) })}
        />
        <IonInput
          fill="outline"
          type="number"
          label="Pause in Minuten"
          labelPlacement="floating"
          value={form.break_minutes}
          onIonInput={(event) => setForm({ ...form, break_minutes: value(event) })}
        />
        <IonSelect
          fill="outline"
          label="Mitarbeiter"
          labelPlacement="floating"
          value={form.worker}
          onIonChange={(event) => setForm({ ...form, worker: value(event), is_open: false })}
        >
          <IonSelectOption value="">Noch nicht zuweisen</IonSelectOption>
          {workers.map((worker) => (
            <IonSelectOption value={worker.id} key={worker.id}>
              {worker.user_detail?.name}
            </IonSelectOption>
          ))}
        </IonSelect>
        <IonItem lines="none" className="toggle-field">
          <IonLabel>Als OpenShift veröffentlichen</IonLabel>
          <IonToggle
            checked={!!form.is_open}
            onIonChange={(event) => setForm({ ...form, is_open: event.detail.checked, worker: '' })}
          />
        </IonItem>
        <IonTextarea
          fill="outline"
          label="Hinweise"
          labelPlacement="floating"
          value={form.notes}
          onIonInput={(event) => setForm({ ...form, notes: value(event) })}
        />
      </FormModal>

      <IonToast isOpen={!!toast} message={toast} duration={3500} onDidDismiss={() => setToast('')} />
    </>
  );
}

function Time({ user }: { user: User }) {
  const [rows, setRows] = useState<any[]>([]);
  const [timeOff, setTimeOff] = useState<any[]>([]);
  const [workers, setWorkers] = useState<any[]>([]);
  const [shifts, setShifts] = useState<any[]>([]);
  const [modal, setModal] = useState('');
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState('');
  const [absence, setAbsence] = useState<any>({});
  const [manual, setManual] = useState<any>({});

  const load = async () => {
    const [entryData, absenceData] = await Promise.all([api('time-entries/'), api('time-off/')]);
    setRows(unpack(entryData));
    setTimeOff(unpack(absenceData));
    if (isManager(user)) {
      const [workerData, shiftData] = await Promise.all([api('workers/'), api('shifts/')]);
      setWorkers(unpack(workerData).filter((worker: any) => worker.active));
      setShifts(unpack(shiftData));
    }
  };

  useEffect(() => {
    void load();
  }, []);

  async function clock(kind: 'in' | 'out') {
    setBusy(true);
    try {
      let position: any = {};
      try {
        position = await new Promise((resolve, reject) =>
          navigator.geolocation.getCurrentPosition(resolve, reject),
        );
      } catch {
        position = {};
      }
      await api(`time-entries/clock_${kind}/`, {
        method: 'POST',
        body: JSON.stringify({
          lat: position.coords?.latitude,
          lng: position.coords?.longitude,
        }),
      });
      setToast(kind === 'in' ? 'Arbeitszeit wurde gestartet.' : 'Arbeitszeit wurde beendet.');
      await load();
    } catch (reason: any) {
      setToast(reason.message);
    } finally {
      setBusy(false);
    }
  }

  async function approve(id: string) {
    try {
      await api(`time-entries/${id}/approve/`, { method: 'POST', body: '{}' });
      await load();
      setToast('Arbeitszeit wurde freigegeben.');
    } catch (reason: any) {
      setToast(reason.message);
    }
  }

  async function decide(id: string, decision: string) {
    try {
      await api(`time-off/${id}/decide/`, {
        method: 'POST',
        body: JSON.stringify({ status: decision }),
      });
      await load();
      setToast(decision === 'approved' ? 'Abwesenheit genehmigt.' : 'Abwesenheit abgelehnt.');
    } catch (reason: any) {
      setToast(reason.message);
    }
  }

  async function requestAbsence() {
    setBusy(true);
    try {
      await api('time-off/', { method: 'POST', body: JSON.stringify(absence) });
      setModal('');
      setAbsence({});
      await load();
      setToast('Abwesenheitsantrag wurde gesendet.');
    } catch (reason: any) {
      setToast(reason.message);
    } finally {
      setBusy(false);
    }
  }

  async function createManual() {
    setBusy(true);
    try {
      await api('time-entries/', {
        method: 'POST',
        body: JSON.stringify({ ...manual, shift: manual.shift || null }),
      });
      setModal('');
      setManual({});
      await load();
      setToast('Arbeitszeit wurde erfasst.');
    } catch (reason: any) {
      setToast(reason.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Title
        title="Arbeitszeit & Abwesenheiten"
        text="Arbeitszeiten, Pausen, Freigaben und Urlaubsanträge."
        action={
          user.role === 'worker' ? (
            <div className="button-group">
              <IonButton disabled={busy} onClick={() => clock('in')}>
                Einstempeln
              </IonButton>
              <IonButton fill="outline" disabled={busy} onClick={() => clock('out')}>
                Ausstempeln
              </IonButton>
              <IonButton fill="outline" onClick={() => setModal('absence')}>
                Abwesenheit
              </IonButton>
            </div>
          ) : (
            <IonButton onClick={() => setModal('manual')}>
              <IonIcon slot="start" icon={addOutline} />
              Zeit erfassen
            </IonButton>
          )
        }
      />

      <div className="columns">
        <div className="panel">
          <div className="section-head">
            <div>
              <h3>Zeiterfassungen</h3>
              <p>{rows.filter((entry) => !entry.approved).length} noch nicht freigegeben</p>
            </div>
          </div>
          {rows.map((entry) => (
            <div className="row" key={entry.id}>
              <IonIcon icon={stopwatchOutline} />
              <div className="grow">
                <b>{entry.worker_name || dateOnly(entry.clock_in)}</b>
                <p>
                  {dateTime(entry.clock_in)} – {entry.clock_out ? dateTime(entry.clock_out) : 'läuft'}
                </p>
                {entry.shift_title && <small>{entry.shift_title}</small>}
              </div>
              <strong>
                {Math.floor((entry.worked_minutes || 0) / 60)}:
                {String((entry.worked_minutes || 0) % 60).padStart(2, '0')} Std.
              </strong>
              <IonBadge color={entry.approved ? 'success' : 'warning'}>
                {entry.approved ? 'Freigegeben' : 'Offen'}
              </IonBadge>
              {isManager(user) && !entry.approved && entry.clock_out && (
                <IonButton size="small" onClick={() => approve(entry.id)}>
                  Freigeben
                </IonButton>
              )}
            </div>
          ))}
          {!rows.length && <Empty>Noch keine Arbeitszeiten.</Empty>}
        </div>

        <div className="panel">
          <div className="section-head">
            <div>
              <h3>Abwesenheiten</h3>
              <p>Urlaub, Krankheit und sonstige Anträge.</p>
            </div>
          </div>
          {timeOff.map((request) => (
            <div className="row" key={request.id}>
              <div className="grow">
                <b>{request.worker_name || 'Mein Antrag'}</b>
                <p>
                  {dateOnly(request.starts_on)} – {dateOnly(request.ends_on)}
                </p>
                <small>{request.reason || 'Ohne Begründung'}</small>
              </div>
              <IonBadge>{statusText[request.status] || request.status}</IonBadge>
              {isManager(user) && request.status === 'pending' && (
                <div className="row-actions">
                  <IonButton size="small" color="success" onClick={() => decide(request.id, 'approved')}>
                    <IonIcon icon={checkmarkOutline} />
                  </IonButton>
                  <IonButton size="small" color="danger" onClick={() => decide(request.id, 'rejected')}>
                    Ablehnen
                  </IonButton>
                </div>
              )}
            </div>
          ))}
          {!timeOff.length && <Empty>Noch keine Abwesenheiten.</Empty>}
        </div>
      </div>

      <FormModal
        open={modal === 'absence'}
        title="Abwesenheit beantragen"
        onClose={() => setModal('')}
        onSave={requestAbsence}
        busy={busy}
        saveLabel="Antrag senden"
      >
        <IonInput
          fill="outline"
          type="date"
          label="Von *"
          labelPlacement="floating"
          value={absence.starts_on}
          onIonInput={(event) => setAbsence({ ...absence, starts_on: value(event) })}
        />
        <IonInput
          fill="outline"
          type="date"
          label="Bis *"
          labelPlacement="floating"
          value={absence.ends_on}
          onIonInput={(event) => setAbsence({ ...absence, ends_on: value(event) })}
        />
        <IonTextarea
          fill="outline"
          label="Grund / Hinweis"
          labelPlacement="floating"
          value={absence.reason}
          onIonInput={(event) => setAbsence({ ...absence, reason: value(event) })}
        />
      </FormModal>

      <FormModal
        open={modal === 'manual'}
        title="Arbeitszeit manuell erfassen"
        onClose={() => setModal('')}
        onSave={createManual}
        busy={busy}
      >
        <IonSelect
          fill="outline"
          label="Mitarbeiter *"
          labelPlacement="floating"
          value={manual.worker}
          onIonChange={(event) => setManual({ ...manual, worker: value(event) })}
        >
          {workers.map((worker) => (
            <IonSelectOption value={worker.id} key={worker.id}>
              {worker.user_detail?.name}
            </IonSelectOption>
          ))}
        </IonSelect>
        <IonSelect
          fill="outline"
          label="Schicht"
          labelPlacement="floating"
          value={manual.shift}
          onIonChange={(event) => setManual({ ...manual, shift: value(event) })}
        >
          <IonSelectOption value="">Ohne Schicht</IonSelectOption>
          {shifts.map((shift) => (
            <IonSelectOption value={shift.id} key={shift.id}>
              {shift.position_name} · {dateTime(shift.starts_at)}
            </IonSelectOption>
          ))}
        </IonSelect>
        <IonInput
          fill="outline"
          type="datetime-local"
          label="Beginn *"
          labelPlacement="floating"
          value={manual.clock_in}
          onIonInput={(event) => setManual({ ...manual, clock_in: value(event) })}
        />
        <IonInput
          fill="outline"
          type="datetime-local"
          label="Ende"
          labelPlacement="floating"
          value={manual.clock_out}
          onIonInput={(event) => setManual({ ...manual, clock_out: value(event) })}
        />
        <IonTextarea
          fill="outline"
          label="Korrekturgrund"
          labelPlacement="floating"
          value={manual.edit_reason}
          onIonInput={(event) => setManual({ ...manual, edit_reason: value(event) })}
        />
      </FormModal>

      <IonToast isOpen={!!toast} message={toast} duration={3500} onDidDismiss={() => setToast('')} />
    </>
  );
}

function Contracts({ user }: { user: User }) {
  const [rows, setRows] = useState<any[]>([]);
  const [templates, setTemplates] = useState<any[]>([]);
  const [workers, setWorkers] = useState<any[]>([]);
  const [clients, setClients] = useState<any[]>([]);
  const [modal, setModal] = useState('');
  const [selected, setSelected] = useState<any>();
  const [form, setForm] = useState<any>({});
  const [name, setName] = useState('');
  const [signature, setSignature] = useState('');
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState('');
  const [listQuery, setListQuery] = useState('');
  const [listStatus, setListStatus] = useState('');
  const [listSort, setListSort] = useState('-updated_at');

  const load = async () => {
    const params = new URLSearchParams();
    if (listQuery.trim()) params.set('search', listQuery.trim());
    if (listStatus) params.set('status', listStatus);
    params.set('ordering', listSort);
    const contractData = await api(`contracts/?${params.toString()}`);
    setRows(unpack(contractData));
    if (isManager(user)) {
      const [templateData, workerData, clientData] = await Promise.all([
        api('contract-templates/'),
        api('workers/?ordering=user__last_name'),
        api('clients/?ordering=name'),
      ]);
      setTemplates(unpack(templateData).filter((template: any) => template.active));
      setWorkers(unpack(workerData).filter((worker: any) => worker.active));
      setClients(unpack(clientData).filter((client: any) => client.active));
    }
  };

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), listQuery ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [listQuery, listStatus, listSort]);

  const selectedTemplate = templates.find((item) => item.id === form.template);
  const variableFields = (selectedTemplate?.schema?.fields || []).filter((item: any) =>
    !item.source || String(item.source).startsWith('contract.variables.'),
  );

  async function create() {
    setBusy(true);
    const variables = { ...(form.variables || {}) };
    try {
      await api('contracts/', {
        method: 'POST',
        body: JSON.stringify({
          template: form.template,
          worker: form.worker || null,
          client: form.client || null,
          title: form.title,
          starts_on: form.starts_on || null,
          ends_on: form.ends_on || null,
          reminder_date: form.reminder_date || null,
          status: 'draft',
          variables,
        }),
      });
      setModal('');
      setForm({});
      await load();
      setToast('Vertrag wurde als Entwurf angelegt.');
    } catch (reason: any) {
      setToast(reason.message);
    } finally {
      setBusy(false);
    }
  }

  async function contractAction(id: string, type: 'generate_pdf' | 'send') {
    try {
      await api(`contracts/${id}/${type}/`, { method: 'POST', body: '{}' });
      await load();
      setToast(type === 'send' ? 'Vertrag wurde versendet.' : 'PDF wurde erstellt.');
    } catch (reason: any) {
      setToast(reason.message);
    }
  }

  async function remove(id: string) {
    if (!window.confirm('Diesen Vertragsentwurf löschen?')) return;
    try {
      await api(`contracts/${id}/`, { method: 'DELETE' });
      await load();
      setToast('Vertrag wurde gelöscht.');
    } catch (reason: any) {
      setToast(reason.message);
    }
  }

  async function cancelContract(id: string) {
    const reason = window.prompt('Warum wird dieser Vertrag storniert?');
    if (!reason) return;
    try {
      await api(`contracts/${id}/cancel/`, { method: 'POST', body: JSON.stringify({ reason }) });
      await load();
      setToast('Vertrag wurde storniert und bleibt in der Akte erhalten.');
    } catch (reason: any) {
      setToast(reason.message);
    }
  }

  async function sign() {
    if (!selected) return;
    setBusy(true);
    try {
      await api(`contracts/${selected.id}/sign/`, {
        method: 'POST',
        body: JSON.stringify({ name, signature }),
      });
      setSelected(undefined);
      setName('');
      setSignature('');
      await load();
      setToast('Vertrag wurde verbindlich unterzeichnet.');
    } catch (reason: any) {
      setToast(reason.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Title
        title="Verträge"
        text="Erstellen, prüfen, als PDF erzeugen, versenden und digital unterzeichnen."
        action={
          isManager(user) ? (
            <IonButton onClick={() => setModal('contract')}>
              <IonIcon slot="start" icon={addOutline} />
              Neuer Vertrag
            </IonButton>
          ) : undefined
        }
      />
      {isManager(user) && <DocumentCenterV5 onChanged={load} />}
      <ListToolbar
        query={listQuery}
        onQuery={setListQuery}
        placeholder="Vertrag, Mitarbeiter oder Kunde suchen …"
        status={listStatus}
        onStatus={setListStatus}
        statusOptions={[{ value: 'draft', label: 'Entwurf' }, { value: 'ready', label: 'Prüfbereit' }, { value: 'sent', label: 'Versendet' }, { value: 'signed', label: 'Unterzeichnet' }, { value: 'expired', label: 'Abgelaufen' }, { value: 'cancelled', label: 'Storniert' }]}
        sort={listSort}
        onSort={setListSort}
        sortOptions={[{ value: '-updated_at', label: 'Zuletzt geändert' }, { value: 'ends_on', label: 'Vertragsende zuerst' }, { value: '-created_at', label: 'Neueste zuerst' }]}
        count={rows.length}
      />
      <div className="panel">
        {rows.map((contract) => (
          <div className="row contract-row" id={`contract-${contract.id}`} key={contract.id}>
            <IonIcon icon={documentTextOutline} />
            <div className="grow">
              <b>{contract.title}</b>
              <p>
                {contract.template_name} · {contract.worker_name || contract.client_name || 'Ohne Zuordnung'}
              </p>
              <small>
                {contract.starts_on ? `ab ${dateOnly(contract.starts_on)}` : ''}
                {contract.ends_on ? ` · bis ${dateOnly(contract.ends_on)}` : ' · unbefristet'}
              </small>
            </div>
            <IonBadge>{statusText[contract.status] || contract.status}</IonBadge>
            {contract.pdf && (
              <IonButton fill="clear" href={contract.pdf} target="_blank">
                PDF
              </IonButton>
            )}
            {isManager(user) && (
              <div className="row-actions">
                {contract.readiness?.generation_allowed && (
                  <IonButton size="small" fill="outline" onClick={() => contractAction(contract.id, 'generate_pdf')}>
                    PDF erstellen
                  </IonButton>
                )}
                {contract.status === 'draft' && contract.readiness && !contract.readiness.generation_allowed && (
                  <IonButton
                    size="small"
                    fill="outline"
                    disabled
                    title={(contract.readiness.blocking_issues || []).map((issue: any) => issue.label).join(' · ') || 'Dokument ist noch nicht erzeugbar.'}
                  >
                    PDF nicht bereit
                  </IonButton>
                )}
                {contract.readiness?.send_allowed && (
                  <IonButton size="small" onClick={() => contractAction(contract.id, 'send')}>
                    <IonIcon slot="start" icon={sendOutline} />
                    Versenden
                  </IonButton>
                )}
                {contract.status === 'draft' && (
                  <IonButton fill="clear" color="danger" onClick={() => remove(contract.id)}>
                    <IonIcon icon={trashOutline} />
                  </IonButton>
                )}
                {['ready', 'sent'].includes(contract.status) && !contract.signatures?.length && (
                  <IonButton size="small" fill="clear" color="danger" onClick={() => cancelContract(contract.id)}>
                    Stornieren
                  </IonButton>
                )}
              </div>
            )}
            {(['client', 'worker'].includes(user.role) || isManager(user)) && ['ready', 'sent'].includes(contract.status) && contract.readiness?.pending_signature_roles?.includes(isManager(user) ? 'employer' : user.role === 'worker' ? 'employee' : 'client') && (
              <IonButton size="small" onClick={() => setSelected(contract)}>
                {isManager(user) ? 'Als Arbeitgeber unterschreiben' : 'Unterschreiben'}
              </IonButton>
            )}
          </div>
        ))}
        {!rows.length && <Empty>Noch keine Verträge.</Empty>}
      </div>

      <FormModal
        open={modal === 'contract'}
        title="Vertrag erstellen"
        onClose={() => setModal('')}
        onSave={create}
        busy={busy}
      >
        <IonSelect
          fill="outline"
          label="Vorlage *"
          labelPlacement="floating"
          value={form.template}
          onIonChange={(event) => { const id = value(event); const template = templates.find((item) => item.id === id); setForm({ ...form, template: id, title: form.title || template?.name || '', variables: {} }); }}
        >
          {templates.map((template) => (
            <IonSelectOption value={template.id} key={template.id}>
              {template.name} · Version {template.version}
            </IonSelectOption>
          ))}
        </IonSelect>
        <IonInput
          fill="outline"
          label="Vertragstitel *"
          labelPlacement="floating"
          value={form.title}
          onIonInput={(event) => setForm({ ...form, title: value(event) })}
        />
        <IonSelect
          fill="outline"
          label="Mitarbeiter"
          labelPlacement="floating"
          value={form.worker}
          onIonChange={(event) => setForm({ ...form, worker: value(event) })}
        >
          <IonSelectOption value="">Keine Zuordnung</IonSelectOption>
          {workers.map((worker) => (
            <IonSelectOption value={worker.id} key={worker.id}>
              {worker.user_detail?.name}
            </IonSelectOption>
          ))}
        </IonSelect>
        <IonSelect
          fill="outline"
          label="Kunde"
          labelPlacement="floating"
          value={form.client}
          onIonChange={(event) => setForm({ ...form, client: value(event) })}
        >
          <IonSelectOption value="">Keine Zuordnung</IonSelectOption>
          {clients.map((client) => (
            <IonSelectOption value={client.id} key={client.id}>
              {client.name}
            </IonSelectOption>
          ))}
        </IonSelect>
        <IonInput
          fill="outline"
          type="date"
          label="Vertragsbeginn"
          labelPlacement="floating"
          value={form.starts_on}
          onIonInput={(event) => setForm({ ...form, starts_on: value(event) })}
        />
        <IonInput
          fill="outline"
          type="date"
          label="Vertragsende"
          labelPlacement="floating"
          value={form.ends_on}
          onIonInput={(event) => setForm({ ...form, ends_on: value(event) })}
        />
        <IonInput
          fill="outline"
          type="date"
          label="Erinnerungsdatum"
          labelPlacement="floating"
          value={form.reminder_date}
          onIonInput={(event) => setForm({ ...form, reminder_date: value(event) })}
        />
        {!!variableFields.length && <div className="form-divider">Dokumentspezifische Angaben</div>}
        {variableFields.map((field: any) => {
          const current = form.variables?.[field.name] ?? '';
          const updateVariable = (next: any) => setForm({ ...form, variables: { ...(form.variables || {}), [field.name]: next } });
          if (field.type === 'boolean') {
            return <IonItem lines="none" className="toggle-field" key={field.name}><IonLabel>{field.label}{field.required ? ' *' : ''}</IonLabel><IonToggle checked={!!current} onIonChange={(event) => updateVariable(event.detail.checked)} /></IonItem>;
          }
          if (field.type === 'choice') {
            return <IonSelect fill="outline" label={`${field.label}${field.required ? ' *' : ''}`} labelPlacement="floating" value={current} onIonChange={(event) => updateVariable(value(event))} key={field.name}>{(field.choices || []).map((choice: string) => <IonSelectOption value={choice} key={choice}>{choice}</IonSelectOption>)}</IonSelect>;
          }
          return <IonInput fill="outline" type={field.type === 'date' ? 'date' : ['number', 'money'].includes(field.type) ? 'number' : 'text'} label={`${field.label}${field.required ? ' *' : ''}`} labelPlacement="floating" value={current} onIonInput={(event) => updateVariable(value(event))} key={field.name} />;
        })}
      </FormModal>

      <FormModal
        open={!!selected}
        title="Vertrag unterzeichnen"
        onClose={() => setSelected(undefined)}
        onSave={sign}
        busy={busy}
        saveLabel="Verbindlich unterzeichnen"
      >
        <div className="notice full">{selected?.title}</div>
        <IonInput
          fill="outline"
          label="Vollständiger Name"
          labelPlacement="floating"
          value={name}
          onIonInput={(event) => setName(String(value(event)))}
        />
        <IonTextarea
          fill="outline"
          label="Signatur (Name handschriftlich eingeben)"
          labelPlacement="floating"
          value={signature}
          onIonInput={(event) => setSignature(String(value(event)))}
        />
      </FormModal>

      <IonToast isOpen={!!toast} message={toast} duration={3500} onDidDismiss={() => setToast('')} />
    </>
  );
}

function Documents({ user }: { user: User }) {
  const [rows, setRows] = useState<any[]>([]);
  const [payroll, setPayroll] = useState<any[]>([]);
  const [workers, setWorkers] = useState<any[]>([]);
  const [clients, setClients] = useState<any[]>([]);
  const [modal, setModal] = useState('');
  const [file, setFile] = useState<File>();
  const [payrollFile, setPayrollFile] = useState<File>();
  const [form, setForm] = useState<any>({ folder: 'general', visibility: isManager(user) ? 'shared' : user.role === 'worker' ? 'worker' : 'client' });
  const [payrollForm, setPayrollForm] = useState<any>({});
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState('');
  const [listQuery, setListQuery] = useState('');
  const [listFolder, setListFolder] = useState('');
  const [listSort, setListSort] = useState('-created_at');

  const load = async () => {
    const params = new URLSearchParams();
    if (listQuery.trim()) params.set('search', listQuery.trim());
    if (listFolder) params.set('folder', listFolder);
    params.set('ordering', listSort);
    const [documentData, payrollData] = await Promise.all([api(`documents/?${params.toString()}`), api('payroll/')]);
    setRows(unpack(documentData));
    setPayroll(unpack(payrollData));
    if (isManager(user)) {
      const [workerData, clientData] = await Promise.all([api('workers/?ordering=user__last_name'), api('clients/?ordering=name')]);
      setWorkers(unpack(workerData).filter((worker: any) => worker.active));
      setClients(unpack(clientData).filter((client: any) => client.active));
    }
  };

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), listQuery ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [listQuery, listFolder, listSort]);

  async function upload() {
    if (!file) return;
    setBusy(true);
    const data = new FormData();
    data.append('file', file);
    data.append('title', form.title || file.name);
    data.append('folder', form.folder);
    data.append('visibility', form.visibility);
    if (form.worker) data.append('worker', form.worker);
    if (form.client) data.append('client', form.client);
    try {
      await api('documents/', { method: 'POST', body: data });
      setModal('');
      setFile(undefined);
      setForm({ folder: 'general', visibility: isManager(user) ? 'shared' : user.role === 'worker' ? 'worker' : 'client' });
      await load();
      setToast('Dokument wurde hochgeladen.');
    } catch (reason: any) {
      setToast(reason.message);
    } finally {
      setBusy(false);
    }
  }

  async function uploadPayroll() {
    if (!payrollFile) return;
    setBusy(true);
    const data = new FormData();
    data.append('document', payrollFile);
    data.append('worker', payrollForm.worker);
    data.append('period', payrollForm.period);
    if (payrollForm.gross_amount) data.append('gross_amount', payrollForm.gross_amount);
    if (payrollForm.net_amount) data.append('net_amount', payrollForm.net_amount);
    try {
      await api('payroll/', { method: 'POST', body: data });
      setModal('');
      setPayrollFile(undefined);
      setPayrollForm({});
      await load();
      setToast('Lohnabrechnung wurde hochgeladen.');
    } catch (reason: any) {
      setToast(reason.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    if (!window.confirm('Dieses Dokument löschen?')) return;
    try {
      await api(`documents/${id}/`, { method: 'DELETE' });
      await load();
      setToast('Dokument wurde gelöscht.');
    } catch (reason: any) {
      setToast(reason.message);
    }
  }

  return (
    <>
      <Title
        title="Dokumente"
        text="Dokumente und Lohnabrechnungen sicher zuordnen und bereitstellen."
        action={
          <div className="button-group">
            <IonButton onClick={() => setModal('document')}>
              <IonIcon slot="start" icon={cloudUploadOutline} />
              Dokument
            </IonButton>
            {isManager(user) && (
              <IonButton fill="outline" onClick={() => setModal('payroll')}>
                Lohnabrechnung
              </IonButton>
            )}
          </div>
        }
      />

      <ListToolbar
        query={listQuery}
        onQuery={setListQuery}
        placeholder="Dokument, Mitarbeiter oder Kunde suchen …"
        status={listFolder}
        onStatus={setListFolder}
        statusOptions={[{ value: 'general', label: 'Allgemein' }, { value: 'contracts', label: 'Verträge' }, { value: 'payroll', label: 'Lohnabrechnungen' }, { value: 'certificates', label: 'Nachweise' }, { value: 'orders', label: 'Aufträge' }]}
        sort={listSort}
        onSort={setListSort}
        sortOptions={[{ value: '-created_at', label: 'Neueste zuerst' }, { value: 'title', label: 'Titel A–Z' }, { value: 'folder', label: 'Nach Ordner' }]}
        count={rows.length}
      />
      <div className="columns">
        <div className="panel">
          <h3>Dokumente</h3>
          {rows.map((document) => (
            <div className="row" key={document.id}>
              <IonIcon icon={documentTextOutline} />
              <div className="grow">
                <b>{document.title}</b>
                <p>
                  {document.worker_name || document.client_name || 'Allgemein'} · {document.folder} ·{' '}
                  {dateOnly(document.created_at)}
                </p>
              </div>
              <IonBadge>{document.visibility}</IonBadge>
              <IonButton fill="clear" href={document.file} target="_blank">
                Öffnen
              </IonButton>
              {isManager(user) && (
                <IonButton fill="clear" color="danger" onClick={() => remove(document.id)}>
                  <IonIcon icon={trashOutline} />
                </IonButton>
              )}
            </div>
          ))}
          {!rows.length && <Empty>Noch keine Dokumente.</Empty>}
        </div>

        <div className="panel">
          <h3>Lohnabrechnungen</h3>
          {payroll.map((statement) => (
            <div className="row" key={statement.id}>
              <IonIcon icon={documentTextOutline} />
              <div className="grow">
                <b>{statement.worker_name || 'Lohnabrechnung'}</b>
                <p>Abrechnungsmonat {dateOnly(statement.period)}</p>
              </div>
              <IonButton fill="clear" href={statement.document} target="_blank">
                Öffnen
              </IonButton>
            </div>
          ))}
          {!payroll.length && <Empty>Noch keine Lohnabrechnungen.</Empty>}
        </div>
      </div>

      <FormModal
        open={modal === 'document'}
        title="Dokument hochladen"
        onClose={() => setModal('')}
        onSave={upload}
        busy={busy}
        saveLabel="Hochladen"
      >
        <label className="file-field">
          <span>Datei auswählen *</span>
          <input type="file" onChange={(event) => setFile(event.target.files?.[0])} />
          <b>{file?.name || 'Keine Datei ausgewählt'}</b>
        </label>
        <IonInput
          fill="outline"
          label="Titel"
          labelPlacement="floating"
          value={form.title}
          onIonInput={(event) => setForm({ ...form, title: value(event) })}
        />
        <IonSelect
          fill="outline"
          label="Ordner"
          labelPlacement="floating"
          value={form.folder}
          onIonChange={(event) => setForm({ ...form, folder: value(event) })}
        >
          <IonSelectOption value="general">Allgemein</IonSelectOption>
          <IonSelectOption value="contracts">Verträge</IonSelectOption>
          <IonSelectOption value="payroll">Lohnabrechnungen</IonSelectOption>
          <IonSelectOption value="certificates">Nachweise</IonSelectOption>
          <IonSelectOption value="orders">Aufträge</IonSelectOption>
        </IonSelect>
        <IonSelect
          fill="outline"
          label="Sichtbarkeit"
          labelPlacement="floating"
          disabled={!isManager(user)}
          value={form.visibility}
          onIonChange={(event) => setForm({ ...form, visibility: value(event) })}
        >
          <IonSelectOption value="admin">Nur Administration</IonSelectOption>
          <IonSelectOption value="worker">Mitarbeiter</IonSelectOption>
          <IonSelectOption value="client">Kunde</IonSelectOption>
          <IonSelectOption value="shared">Geteilt</IonSelectOption>
        </IonSelect>
        {isManager(user) && (
          <>
            <IonSelect
              fill="outline"
              label="Mitarbeiter"
              labelPlacement="floating"
              value={form.worker}
              onIonChange={(event) => setForm({ ...form, worker: value(event), client: '' })}
            >
              <IonSelectOption value="">Keine Zuordnung</IonSelectOption>
              {workers.map((worker) => (
                <IonSelectOption value={worker.id} key={worker.id}>
                  {worker.user_detail?.name}
                </IonSelectOption>
              ))}
            </IonSelect>
            <IonSelect
              fill="outline"
              label="Kunde"
              labelPlacement="floating"
              value={form.client}
              onIonChange={(event) => setForm({ ...form, client: value(event), worker: '' })}
            >
              <IonSelectOption value="">Keine Zuordnung</IonSelectOption>
              {clients.map((client) => (
                <IonSelectOption value={client.id} key={client.id}>
                  {client.name}
                </IonSelectOption>
              ))}
            </IonSelect>
          </>
        )}
      </FormModal>

      <FormModal
        open={modal === 'payroll'}
        title="Lohnabrechnung hochladen"
        onClose={() => setModal('')}
        onSave={uploadPayroll}
        busy={busy}
        saveLabel="Hochladen"
      >
        <IonSelect
          fill="outline"
          label="Mitarbeiter *"
          labelPlacement="floating"
          value={payrollForm.worker}
          onIonChange={(event) => setPayrollForm({ ...payrollForm, worker: value(event) })}
        >
          {workers.map((worker) => (
            <IonSelectOption value={worker.id} key={worker.id}>
              {worker.user_detail?.name}
            </IonSelectOption>
          ))}
        </IonSelect>
        <IonInput
          fill="outline"
          type="date"
          label="Abrechnungsmonat (erster Tag) *"
          labelPlacement="floating"
          value={payrollForm.period}
          onIonInput={(event) => setPayrollForm({ ...payrollForm, period: value(event) })}
        />
        <IonInput
          fill="outline"
          type="number"
          label="Brutto (€)"
          labelPlacement="floating"
          value={payrollForm.gross_amount}
          onIonInput={(event) => setPayrollForm({ ...payrollForm, gross_amount: value(event) })}
        />
        <IonInput
          fill="outline"
          type="number"
          label="Netto (€)"
          labelPlacement="floating"
          value={payrollForm.net_amount}
          onIonInput={(event) => setPayrollForm({ ...payrollForm, net_amount: value(event) })}
        />
        <label className="file-field">
          <span>PDF auswählen *</span>
          <input
            type="file"
            accept=".pdf,application/pdf"
            onChange={(event) => setPayrollFile(event.target.files?.[0])}
          />
          <b>{payrollFile?.name || 'Keine Datei ausgewählt'}</b>
        </label>
      </FormModal>

      <IonToast isOpen={!!toast} message={toast} duration={3500} onDidDismiss={() => setToast('')} />
    </>
  );
}

function Orders({ user }: { user: User }) {
  const [rows, setRows] = useState<any[]>([]);
  const [clients, setClients] = useState<any[]>([]);
  const [locations, setLocations] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<any>({ requested_staff: 1, status: 'new' });
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState('');
  const [listQuery, setListQuery] = useState('');
  const [listStatus, setListStatus] = useState('');
  const [listSort, setListSort] = useState('-starts_at');
  const [aiOpen, setAiOpen] = useState(false);
  const [orderText, setOrderText] = useState('');
  const [parsedOrder, setParsedOrder] = useState<any>();

  const load = async () => {
    const params = new URLSearchParams();
    if (listQuery.trim()) params.set('search', listQuery.trim());
    if (listStatus) params.set('status', listStatus);
    params.set('ordering', listSort);
    const orderData = await api(`orders/?${params.toString()}`);
    setRows(unpack(orderData));
    if (isManager(user)) {
      const [clientData, locationData] = await Promise.all([api('clients/?ordering=name'), api('locations/')]);
      setClients(unpack(clientData).filter((client: any) => client.active));
      setLocations(unpack(locationData).filter((location: any) => location.active));
    } else if (user.role === 'client') {
      const locationData = await api('locations/');
      setLocations(unpack(locationData).filter((location: any) => location.active));
    }
  };

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), listQuery ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [listQuery, listStatus, listSort]);

  async function create() {
    setBusy(true);
    try {
      const payload = {
        ...form,
        location: form.location || null,
      };
      if (user.role === 'client') delete payload.client;
      await api('orders/', { method: 'POST', body: JSON.stringify(payload) });
      setOpen(false);
      setForm({ requested_staff: 1, status: 'new' });
      await load();
      setToast('Auftrag wurde übermittelt.');
    } catch (reason: any) {
      setToast(reason.message);
    } finally {
      setBusy(false);
    }
  }

  async function setStatus(id: string, statusValue: string) {
    try {
      await api(`orders/${id}/`, {
        method: 'PATCH',
        body: JSON.stringify({ status: statusValue }),
      });
      await load();
      setToast('Auftragsstatus wurde aktualisiert.');
    } catch (reason: any) {
      setToast(reason.message);
    }
  }

  async function remove(id: string) {
    if (!window.confirm('Diesen Auftrag löschen?')) return;
    try {
      await api(`orders/${id}/`, { method: 'DELETE' });
      await load();
      setToast('Auftrag wurde gelöscht.');
    } catch (reason: any) {
      setToast(reason.message);
    }
  }

  async function parseAiOrder() {
    if (!orderText.trim()) {
      setToast('Bitte zuerst den Text der Kundenanfrage einfügen.');
      return;
    }
    setBusy(true);
    try {
      const result: any = await api('automation/orders/parse/', {
        method: 'POST',
        body: JSON.stringify({ text: orderText }),
      });
      setParsedOrder(result);
      setToast(`${result.shifts?.length || 0} Schicht(en) erkannt. Bitte kurz prüfen.`);
    } catch (reason: any) {
      setToast(reason.message);
    } finally {
      setBusy(false);
    }
  }

  async function approveAiOrder() {
    if (!parsedOrder) return void parseAiOrder();
    setBusy(true);
    try {
      const result: any = await api('automation/orders/approve/', {
        method: 'POST',
        body: JSON.stringify({ parsed: parsedOrder, raw_text: orderText }),
      });
      setAiOpen(false);
      setOrderText('');
      setParsedOrder(undefined);
      await load();
      setToast(`${result.created_count || 0} Personalplatz/-plätze als OpenShift in A+ Workforce erstellt.`);
    } catch (reason: any) {
      setToast(reason.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Title
        title={isManager(user) ? 'Auftragseingang & AI' : 'Aufträge'}
        text={isManager(user) ? 'Kundenanfragen einlesen, mit AI prüfen und direkt als OpenShifts disponieren.' : 'Veranstaltungen und Personalbedarf direkt übermitteln.'}
        action={
          <div className="button-group">
            {isManager(user) && (
              <IonButton onClick={() => { setParsedOrder(undefined); setAiOpen(true); }}>
                <IonIcon slot="start" icon={briefcaseOutline} />
                Anfrage mit AI einlesen
              </IonButton>
            )}
            <IonButton fill={isManager(user) ? 'outline' : 'solid'} onClick={() => setOpen(true)}>
              <IonIcon slot="start" icon={addOutline} />
              Neuer Auftrag
            </IonButton>
          </div>
        }
      />
      {isManager(user) && (
        <div className="notice">
          <b>Schnellster Ablauf:</b> Kundenmail kopieren → AI analysiert Datum, Zeiten, Anzahl, Position und Einsatzort → kurz prüfen → OpenShifts erstellen.
        </div>
      )}
      <ListToolbar
        query={listQuery}
        onQuery={setListQuery}
        placeholder="Auftrag, Kunde oder Einsatzort suchen …"
        status={listStatus}
        onStatus={setListStatus}
        statusOptions={[{ value: 'new', label: 'Neu' }, { value: 'planning', label: 'In Planung' }, { value: 'confirmed', label: 'Bestätigt' }, { value: 'done', label: 'Abgeschlossen' }, { value: 'cancelled', label: 'Storniert' }]}
        sort={listSort}
        onSort={setListSort}
        sortOptions={[{ value: '-starts_at', label: 'Neueste Einsätze' }, { value: 'starts_at', label: 'Nächste Einsätze' }, { value: '-created_at', label: 'Zuletzt angelegt' }, { value: '-requested_staff', label: 'Größter Bedarf' }]}
        count={rows.length}
      />
      <div className="panel">
        {rows.map((order) => (
          <div className="row" key={order.id}>
            <IonIcon icon={briefcaseOutline} />
            <div className="grow">
              <b>{order.title}</b>
              <p>
                {order.client_name} · {order.requested_staff} Personen · {dateTime(order.starts_at)}
              </p>
              <small>{order.location_name || order.description}</small>
            </div>
            <IonBadge>{statusText[order.status] || order.status}</IonBadge>
            {isManager(user) && (
              <div className="row-actions">
                <IonSelect
                  interface="popover"
                  value={order.status}
                  onIonChange={(event) => setStatus(order.id, String(value(event)))}
                  className="inline-select"
                >
                  <IonSelectOption value="new">Neu</IonSelectOption>
                  <IonSelectOption value="planning">In Planung</IonSelectOption>
                  <IonSelectOption value="confirmed">Bestätigt</IonSelectOption>
                  <IonSelectOption value="done">Abgeschlossen</IonSelectOption>
                  <IonSelectOption value="cancelled">Storniert</IonSelectOption>
                </IonSelect>
                <IonButton fill="clear" color="danger" onClick={() => remove(order.id)}>
                  <IonIcon icon={trashOutline} />
                </IonButton>
              </div>
            )}
          </div>
        ))}
        {!rows.length && <Empty>Noch keine Aufträge.</Empty>}
      </div>

      <FormModal
        open={aiOpen}
        title="Kundenanfrage mit AI einlesen"
        onClose={() => { setAiOpen(false); setParsedOrder(undefined); }}
        onSave={parsedOrder ? approveAiOrder : parseAiOrder}
        busy={busy}
        saveLabel={parsedOrder ? 'Prüfen & OpenShifts erstellen' : 'Mit AI analysieren'}
      >
        <IonTextarea
          className="full"
          autoGrow
          fill="outline"
          label="Text aus Kunden-E-Mail / Anfrage"
          labelPlacement="floating"
          value={orderText}
          onIonInput={(event) => { setOrderText(String(value(event))); setParsedOrder(undefined); }}
        />
        {parsedOrder && (
          <div className="notice full">
            <b>{parsedOrder.request_id || 'Auftrag erkannt'}</b>
            <p>Bitte diese erkannten Schichten vor dem Erstellen kurz prüfen:</p>
            {parsedOrder.shifts?.map((item: any, index: number) => (
              <div key={index}>
                {item.date} · {item.start_time}–{item.end_time} · {item.count}× {item.role} · {item.site_text || item.location_text}
              </div>
            ))}
          </div>
        )}
      </FormModal>

      <FormModal
        open={open}
        title="Neuer Personalauftrag"
        onClose={() => setOpen(false)}
        onSave={create}
        busy={busy}
        saveLabel="Auftrag senden"
      >
        {isManager(user) && (
          <IonSelect
            fill="outline"
            label="Kunde *"
            labelPlacement="floating"
            value={form.client}
            onIonChange={(event) => setForm({ ...form, client: value(event) })}
          >
            {clients.map((client) => (
              <IonSelectOption value={client.id} key={client.id}>
                {client.name}
              </IonSelectOption>
            ))}
          </IonSelect>
        )}
        <IonInput
          fill="outline"
          label="Veranstaltung / Titel *"
          labelPlacement="floating"
          value={form.title}
          onIonInput={(event) => setForm({ ...form, title: value(event) })}
        />
        <IonTextarea
          fill="outline"
          label="Funktionen und Hinweise"
          labelPlacement="floating"
          value={form.description}
          onIonInput={(event) => setForm({ ...form, description: value(event) })}
        />
        <IonSelect
          fill="outline"
          label="Einsatzort"
          labelPlacement="floating"
          value={form.location}
          onIonChange={(event) => setForm({ ...form, location: value(event) })}
        >
          <IonSelectOption value="">Noch offen</IonSelectOption>
          {locations
            .filter((location) => !form.client || !location.client || location.client === form.client)
            .map((location) => (
              <IonSelectOption value={location.id} key={location.id}>
                {location.name}
              </IonSelectOption>
            ))}
        </IonSelect>
        <IonInput
          fill="outline"
          type="datetime-local"
          label="Beginn *"
          labelPlacement="floating"
          value={form.starts_at}
          onIonInput={(event) => setForm({ ...form, starts_at: value(event) })}
        />
        <IonInput
          fill="outline"
          type="datetime-local"
          label="Ende *"
          labelPlacement="floating"
          value={form.ends_at}
          onIonInput={(event) => setForm({ ...form, ends_at: value(event) })}
        />
        <IonInput
          fill="outline"
          type="number"
          label="Anzahl Mitarbeiter"
          labelPlacement="floating"
          value={form.requested_staff}
          onIonInput={(event) => setForm({ ...form, requested_staff: value(event) })}
        />
      </FormModal>

      <IonToast isOpen={!!toast} message={toast} duration={3500} onDidDismiss={() => setToast('')} />
    </>
  );
}

function Announcements({ user }: { user: User }) {
  const [rows, setRows] = useState<any[]>([]);
  const [users, setUsers] = useState<any[]>([]);
  const [selected, setSelected] = useState<string>();
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState<any>({ title: '', body: '', recipients: [], all_recipients: true, attachment: null });
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState('');

  const manager = isManager(user);
  const recipientCandidates = useMemo(
    () => users.filter((person: any) => person.is_active !== false && ['worker', 'client'].includes(person.role) && !String(person.email || '').endsWith('@sync.invalid')),
    [users],
  );

  const load = async () => {
    try {
      if (manager) {
        const [announcementData, userData] = await Promise.all([api('announcements/'), api('users/')]);
        const list = unpack(announcementData);
        setRows(list);
        setUsers(unpack(userData));
        setSelected((current) => current && list.some((item: any) => item.id === current) ? current : list[0]?.id);
      } else {
        const announcementData = await api('announcements/');
        const list = unpack(announcementData);
        setRows(list);
        setSelected((current) => current && list.some((item: any) => item.id === current) ? current : list[0]?.id);
      }
    } catch (reason: any) {
      setToast(reason.message);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  async function sendAnnouncement() {
    if (!form.body?.trim() && !form.attachment) {
      setToast('Bitte Text oder einen Anhang hinzufügen.');
      return;
    }
    if (!form.all_recipients && !(form.recipients || []).length) {
      setToast('Bitte mindestens einen Empfänger auswählen.');
      return;
    }
    setBusy(true);
    try {
      const payload = new FormData();
      payload.append('title', form.title?.trim() || 'Mitteilung');
      payload.append('body', form.body || '');
      payload.append('all_recipients', form.all_recipients ? 'true' : 'false');
      (form.recipients || []).forEach((id: string) => payload.append('recipient_ids', id));
      if (form.attachment) payload.append('attachment', form.attachment);
      const result: any = await api('announcements/', { method: 'POST', body: payload });
      setModal(false);
      setForm({ title: '', body: '', recipients: [], all_recipients: true, attachment: null });
      await load();
      setSelected(result.id);
      setToast(`Mitteilung an ${result.recipient_count || 0} Empfänger versendet. Push wurde ausgelöst.`);
    } catch (reason: any) {
      setToast(reason.message);
    } finally {
      setBusy(false);
    }
  }

  async function choose(item: any) {
    setSelected(item.id);
    if (!manager && !item.is_read) {
      try {
        await api(`announcements/${item.id}/read/`, { method: 'POST', body: '{}' });
        setRows((current) => current.map((row) => row.id === item.id ? { ...row, is_read: true } : row));
      } catch {
        // Reading the Mitteilung is still possible if the acknowledgement request is temporarily offline.
      }
    }
  }

  const active = rows.find((row) => row.id === selected);

  return (
    <>
      <Title
        title="Mitteilungen"
        text={manager ? 'Einweg-Mitteilungen an Mitarbeiter und Kunden – inklusive Datei, Push und Versandhistorie.' : 'Mitteilungen der A+ Solution Administration. Antworten sind nicht erforderlich.'}
        action={manager ? (
          <IonButton data-testid="announcement-create" onClick={() => setModal(true)}>
            <IonIcon slot="start" icon={addOutline} />
            Neue Mitteilung
          </IonButton>
        ) : undefined}
      />

      <div className="columns" data-testid="announcements-view">
        <div className="panel">
          <div className="section-head"><div><h3>{manager ? 'Versandhistorie' : 'Posteingang'}</h3><p>{rows.length} Mitteilungen</p></div></div>
          {rows.map((item) => (
            <button type="button" className={`row announcement-row ${item.id === selected ? 'active' : ''}`} key={item.id} onClick={() => void choose(item)}>
              <IonIcon icon={megaphoneOutline} />
              <div className="grow">
                <b>{item.title || 'Mitteilung'}</b>
                <p>{String(item.body || 'Mit Anhang').slice(0, 100)}</p>
                <small>{dateTime(item.sent_at)} · {item.created_by_name}</small>
              </div>
              {manager ? <IonBadge>{item.recipient_count} Empfänger</IonBadge> : !item.is_read ? <IonBadge color="primary">Neu</IonBadge> : <IonBadge color="medium">Gelesen</IonBadge>}
            </button>
          ))}
          {!rows.length && <Empty>Noch keine Mitteilungen.</Empty>}
        </div>

        <div className="panel">
          {active ? (
            <div data-testid="announcement-detail">
              <div className="section-head">
                <div><small>MITTEILUNG</small><h3>{active.title || 'Mitteilung'}</h3><p>{dateTime(active.sent_at)} · {active.created_by_name}</p></div>
                {manager && <IonBadge color="success">{active.read_count}/{active.recipient_count} gelesen</IonBadge>}
              </div>
              <p style={{ whiteSpace: 'pre-wrap', lineHeight: 1.65 }}>{active.body || 'Diese Mitteilung enthält einen Anhang.'}</p>
              {active.attachment && <p><a href={active.attachment} target="_blank" rel="noreferrer">Anhang öffnen / herunterladen</a></p>}
              {manager && active.recipients_detail?.length > 0 && (
                <div className="panel subtle-panel">
                  <b>Empfänger</b>
                  <p>{active.recipients_detail.map((person: any) => `${person.name}${person.read_at ? ' ✓' : ''}`).join(' · ')}</p>
                </div>
              )}
              {!manager && <small>Diese Mitteilung ist einseitig. Bei organisatorischen Rückfragen bitte die Disposition über den vorgesehenen Kontaktweg erreichen.</small>}
            </div>
          ) : <Empty>Mitteilung auswählen.</Empty>}
        </div>
      </div>

      {manager && <FormModal open={modal} title="Neue Mitteilung" onClose={() => setModal(false)} onSave={sendAnnouncement} busy={busy} saveLabel="Versenden">
        <IonInput fill="outline" label="Titel" labelPlacement="floating" value={form.title} onIonInput={(event) => setForm({ ...form, title: value(event) })} />
        <IonTextarea fill="outline" autoGrow label="Text" labelPlacement="floating" value={form.body} onIonInput={(event) => setForm({ ...form, body: value(event) })} />
        <label className="field-check">Alle Mitarbeiter & Kunden <IonToggle checked={!!form.all_recipients} onIonChange={(event) => setForm({ ...form, all_recipients: event.detail.checked })} /></label>
        {!form.all_recipients && <IonSelect multiple fill="outline" label="Empfänger" labelPlacement="floating" value={form.recipients} onIonChange={(event) => setForm({ ...form, recipients: value(event) })}>
          {recipientCandidates.map((person: any) => <IonSelectOption value={person.id} key={person.id}>{person.name || person.email} · {person.role === 'worker' ? 'Mitarbeiter' : 'Kunde'}</IonSelectOption>)}
        </IonSelect>}
        <label className="file-field">Bild / Datei (optional, max. 20 MB)<input type="file" accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.csv,.txt" onChange={(event) => setForm({ ...form, attachment: event.target.files?.[0] || null })} /></label>
        <small>Beim Versand wird für jeden Empfänger automatisch eine In-App Notification erstellt und – falls auf dem Gerät eingerichtet – per Push zugestellt.</small>
      </FormModal>}

      <IonToast isOpen={!!toast} message={toast} duration={3500} onDidDismiss={() => setToast('')} />
    </>
  );
}

function Ranking() {
  const [workers, setWorkers] = useState<any[]>([]);
  useEffect(() => {
    api('employee/ranking/').then((data) =>
      setWorkers(
        unpack(data)
          .filter((worker: any) => worker.active)
          .sort((a: any, b: any) => b.ranking_points - a.ranking_points),
      ),
    );
  }, []);

  return (
    <>
      <Title title="A+ Ranking" text="Punkte aus Bewertungen, Pünktlichkeit und Engagement." />
      <div className="ranking">
        {workers.map((worker, index) => (
          <div className={`rank-card rank-${index + 1}`} key={worker.id}>
            <strong>#{index + 1}</strong>
            <div className="avatar">{worker.user_detail?.name?.[0] || 'M'}</div>
            <div className="grow">
              <b>{worker.user_detail?.name}</b>
              <p>{worker.employee_number}</p>
            </div>
            <span>{worker.ranking_points} Punkte</span>
          </div>
        ))}
        {!workers.length && <div className="panel"><Empty>Noch keine Ranking-Daten.</Empty></div>}
      </div>
    </>
  );
}

function Ratings({ user }: { user: User }) {
  const [rows, setRows] = useState<any[]>([]);
  const [workers, setWorkers] = useState<any[]>([]);
  const [shifts, setShifts] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<any>({
    score: 5,
    punctuality: 5,
    quality: 5,
    teamwork: 5,
  });
  const [toast, setToast] = useState('');

  const load = async () => {
    if (user.role === 'client') {
      const [ratingData, candidateData] = await Promise.all([
        api('ratings/'),
        api('portal/rating-candidates/'),
      ]);
      const candidates = unpack(candidateData);
      const workerMap = new Map<string, any>();
      const shiftMap = new Map<string, any>();
      candidates.forEach((candidate: any) => {
        const current = workerMap.get(candidate.worker_id) || {
          id: candidate.worker_id,
          active: true,
          user_detail: { name: candidate.worker_name },
          shift_ids: [],
        };
        if (!current.shift_ids.includes(candidate.shift_id)) current.shift_ids.push(candidate.shift_id);
        workerMap.set(candidate.worker_id, current);
        if (!shiftMap.has(candidate.shift_id)) {
          shiftMap.set(candidate.shift_id, {
            id: candidate.shift_id,
            position_name: candidate.position_name,
            location_name: candidate.location_name,
            starts_at: candidate.starts_at,
            ends_at: candidate.ends_at,
          });
        }
      });
      setRows(unpack(ratingData));
      setWorkers(Array.from(workerMap.values()));
      setShifts(Array.from(shiftMap.values()));
      return;
    }
    const [ratingData, workerData, shiftData] = await Promise.all([
      api('ratings/'),
      api('workers/'),
      api('shifts/'),
    ]);
    setRows(unpack(ratingData));
    setWorkers(unpack(workerData).filter((worker: any) => worker.active));
    setShifts(unpack(shiftData));
  };

  useEffect(() => {
    void load();
  }, []);

  async function create() {
    try {
      await api('ratings/', {
        method: 'POST',
        body: JSON.stringify({ ...form, shift: form.shift || null }),
      });
      setOpen(false);
      setForm({ score: 5, punctuality: 5, quality: 5, teamwork: 5 });
      await load();
      setToast('Bewertung wurde gespeichert.');
    } catch (reason: any) {
      setToast(reason.message);
    }
  }

  return (
    <>
      <Title
        title="Mitarbeiter bewerten"
        text="Qualität, Pünktlichkeit und Teamarbeit nach dem Einsatz bewerten."
        action={
          user.role === 'client' ? (
            <IonButton onClick={() => setOpen(true)}>
              <IonIcon slot="start" icon={starOutline} />
              Neue Bewertung
            </IonButton>
          ) : undefined
        }
      />
      <div className="panel">
        {rows.map((rating) => (
          <div className="row" key={rating.id}>
            <IonIcon icon={starOutline} />
            <div className="grow">
              <b>{rating.worker_name}</b>
              <p>{rating.client_name} · {dateOnly(rating.created_at)}</p>
              <small>{rating.comment}</small>
            </div>
            <strong>{rating.score}/5</strong>
          </div>
        ))}
        {!rows.length && <Empty>Noch keine Bewertungen.</Empty>}
      </div>

      <FormModal
        open={open}
        title="Einsatz bewerten"
        onClose={() => setOpen(false)}
        onSave={create}
      >
        <IonSelect
          fill="outline"
          label="Mitarbeiter *"
          labelPlacement="floating"
          value={form.worker}
          onIonChange={(event) => setForm({ ...form, worker: value(event) })}
        >
          {workers.filter((worker) => !form.shift || worker.shift_ids?.includes(form.shift)).map((worker) => (
            <IonSelectOption value={worker.id} key={worker.id}>
              {worker.user_detail?.name}
            </IonSelectOption>
          ))}
        </IonSelect>
        <IonSelect
          fill="outline"
          label="Einsatz *"
          labelPlacement="floating"
          value={form.shift}
          onIonChange={(event) => setForm({ ...form, shift: value(event), worker: '' })}
        >
          <IonSelectOption value="" disabled>Einsatz auswählen</IonSelectOption>
          {shifts.map((shift) => (
            <IonSelectOption value={shift.id} key={shift.id}>
              {shift.position_name} · {dateTime(shift.starts_at)}
            </IonSelectOption>
          ))}
        </IonSelect>
        {[
          ['score', 'Gesamtbewertung'],
          ['punctuality', 'Pünktlichkeit'],
          ['quality', 'Qualität'],
          ['teamwork', 'Teamarbeit'],
        ].map(([key, label]) => (
          <IonSelect
            fill="outline"
            label={label}
            labelPlacement="floating"
            value={form[key]}
            key={key}
            onIonChange={(event) => setForm({ ...form, [key]: value(event) })}
          >
            {[5, 4, 3, 2, 1].map((score) => (
              <IonSelectOption value={score} key={score}>
                {score} Sterne
              </IonSelectOption>
            ))}
          </IonSelect>
        ))}
        <IonTextarea
          fill="outline"
          label="Kommentar"
          labelPlacement="floating"
          value={form.comment}
          onIonInput={(event) => setForm({ ...form, comment: value(event) })}
        />
      </FormModal>

      <IonToast isOpen={!!toast} message={toast} duration={3500} onDidDismiss={() => setToast('')} />
    </>
  );
}

function Profile({ user }: { user: User }) {
  const [toast, setToast] = useState('');
  const [passwords, setPasswords] = useState<any>({});

  async function requestDeletion() {
    try {
      const result: any = await api('auth/account-deletion/', { method: 'POST', body: '{}' });
      setToast(result.detail);
    } catch (reason: any) {
      setToast(reason.message);
    }
  }

  async function changePassword() {
    try {
      const result: any = await api('auth/change-password/', {
        method: 'POST',
        body: JSON.stringify(passwords),
      });
      setToast(result.detail);
      setTimeout(logout, 1500);
    } catch (reason: any) {
      setToast(reason.message);
    }
  }

  return (
    <>
      <Title title="Mein Profil" text="Kontaktdaten, Sicherheit und Datenschutz." />
      <div className="profile-grid">
        <div className="panel profile">
          <div className="avatar big">{user.name[0]}</div>
          <h2>{user.name}</h2>
          <p>{user.email}</p>
          <IonBadge>{user.role}</IonBadge>
          <IonButton fill="outline" color="danger" onClick={requestDeletion}>
            Kontolöschung anfragen
          </IonButton>
        </div>
        <div className="panel form">
          <h3>Passwort ändern</h3>
          <IonInput
            fill="outline"
            type="password"
            label="Aktuelles Passwort"
            labelPlacement="floating"
            value={passwords.current_password}
            onIonInput={(event) => setPasswords({ ...passwords, current_password: value(event) })}
          />
          <IonInput
            fill="outline"
            type="password"
            label="Neues Passwort (mind. 10 Zeichen)"
            labelPlacement="floating"
            value={passwords.new_password}
            onIonInput={(event) => setPasswords({ ...passwords, new_password: value(event) })}
          />
          <IonButton onClick={changePassword}>Passwort aktualisieren</IonButton>
        </div>
      </div>
      <IonToast isOpen={!!toast} message={toast} duration={4000} onDidDismiss={() => setToast('')} />
    </>
  );
}

function Legal({ deletePage = false }: { deletePage?: boolean }) {
  return (
    <IonApp>
      <IonPage>
        <Header title="A+ Solution" />
        <IonContent>
          <main className="legal">
            <h1>{deletePage ? 'Kontolöschung beantragen' : 'Datenschutzinformation'}</h1>
            {deletePage ? (
              <>
                <p>
                  Angemeldete Nutzer können die Löschung unter „Mein Profil“ beantragen. Ohne App kann
                  die Anfrage unter Angabe der registrierten E-Mail-Adresse über die offiziellen
                  Kontaktdaten von A+ Solution GmbH gestellt werden.
                </p>
                <p>
                  Daten werden gelöscht oder anonymisiert, soweit keine gesetzlichen
                  Aufbewahrungspflichten oder laufenden Vertragsansprüche entgegenstehen.
                </p>
              </>
            ) : (
              <>
                <p>
                  A+ Solution GmbH verarbeitet Kontaktdaten, Einsatz-, Zeit-, Vertrags- und
                  Dokumentendaten für Personaldienstleistungen und den Betrieb dieses Portals.
                  Zugriffe werden rollenbasiert gesteuert und protokolliert.
                </p>
                <p>
                  Die rechtlich finale Fassung wird vor Store-Veröffentlichung mit Impressum,
                  Rechtsgrundlagen, Empfängern, Fristen und Betroffenenrechten ergänzt.
                </p>
              </>
            )}
          </main>
        </IonContent>
      </IonPage>
    </IonApp>
  );
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [view, setView] = useState<View>('dashboard');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    consumeOAuth();
    const lost = () => setUser(null);
    window.addEventListener('auth-lost', lost);
    if (localStorage.getItem('access')) {
      me()
        .then(setUser)
        .catch(() => setUser(null))
        .finally(() => setReady(true));
    } else {
      setReady(true);
    }
    return () => window.removeEventListener('auth-lost', lost);
  }, []);

  if (location.pathname === '/aktivieren') return <IonApp><ActivationPage /></IonApp>;
  if (location.pathname === '/datenschutz') return <Legal />;
  if (location.pathname === '/konto-loeschen') return <Legal deletePage />;
  if (!ready)
    return (
      <IonApp>
        <Loader />
      </IonApp>
    );
  if (!user) return <IonApp><Login done={setUser} /></IonApp>;

  const items = nav[user.role] || nav.worker;
  const primaryViews: View[] = ['dashboard', 'schedule', 'time'];
  const mobilePrimaryItems = items.filter(([key]) => primaryViews.includes(key));
  const mobileMoreItems = items.filter(([key]) => !primaryViews.includes(key));
  const currentLabel = view === 'profile' ? 'Profil' : view === 'akte' ? 'Digitale Akte' : items.find(([key]) => key === view)?.[1] || 'A+ Solution';
  const roleLabel: Record<string, string> = {
    admin: 'Administration',
    manager: 'Management',
    worker: 'Mitarbeiter',
    client: 'Kundenportal',
  };
  const mobileLabels: Partial<Record<View, string>> = {
    dashboard: 'Dashboard',
    orders: 'Aufträge',
    schedule: 'Dienstplan',
    time: 'Zeiterfassung',
    people: 'Personal',
    settings: 'Setup',
    messages: 'Mitteilungen',
  };
  const navigateTo = (next: View) => {
    setView(next);
    setMobileMenuOpen(false);
    window.requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
  };

  let content: React.ReactNode = user.role === 'worker' ? <EmployeeHome user={user} navigate={navigateTo} /> : isManager(user) ? <AdminHomeV4 navigate={navigateTo} /> : <Dashboard user={user} navigate={navigateTo} />;

  if (view === 'schedule') content = <ScheduleV2 user={user} />;
  else if (view === 'time') content = <AttendanceV3 user={user} />;
  else if (view === 'contracts') content = <Contracts user={user} />;
  else if (view === 'documents') content = <Documents user={user} />;
  else if (view === 'orders') content = <Orders user={user} />;
  else if (view === 'people') content = <People user={user} />;
  else if (view === 'settings') content = <Settings user={user} />;
  else if (view === 'messages') content = <Announcements user={user} />;
  else if (view === 'ranking') content = <Ranking />;
  else if (view === 'ratings') content = <Ratings user={user} />;
  else if (view === 'profile') content = <Profile user={user} />;
  else if (view === 'operations') content = <Operations user={user} />;
  else if (view === 'akte') content = <AktePage user={user} />;

  return (
    <IonApp className="mobile-first-app-shell-v1">
      <IonPage>
        <Header title="A+ Solution" appShell />
        <IonContent className="app-content">
          <div className="app">
            <header className="mobile-appbar">
              <button className="mobile-brand" type="button" onClick={() => navigateTo('dashboard')} aria-label="Zur Startseite">
                <span>A+</span>
                <small>Solution</small>
              </button>
              <div className="mobile-page-title">
                <small>{roleLabel[user.role] || user.role}</small>
                <strong>{currentLabel}</strong>
              </div>
              <button className="mobile-avatar" type="button" onClick={() => navigateTo('profile')} aria-label="Profil öffnen">
                {user.name[0]}
              </button>
            </header>

            <aside>
              <div className="menu-logo">
                A+<span>Solution</span>
              </div>
              <div className="user">
                <div className="avatar">{user.name[0]}</div>
                <div>
                  <b>{user.name}</b>
                  <small>{roleLabel[user.role] || user.role}</small>
                </div>
              </div>
              <IonList lines="none">
                {items.map((item) => (
                  <IonItem
                    button
                    detail={false}
                    key={item[0]}
                    className={view === item[0] ? 'active' : ''}
                    onClick={() => navigateTo(item[0])}
                  >
                    <IonIcon slot="start" icon={icons[item[0]]} />
                    <IonLabel>{item[1]}</IonLabel>
                  </IonItem>
                ))}
                <IonItem
                  button
                  detail={false}
                  className={view === 'profile' ? 'active' : ''}
                  onClick={() => navigateTo('profile')}
                >
                  <IonIcon slot="start" icon={peopleOutline} />
                  <IonLabel>Profil</IonLabel>
                </IonItem>
              </IonList>
              <IonButton fill="clear" onClick={logout}>
                <IonIcon slot="start" icon={exitOutline} />
                Abmelden
              </IonButton>
            </aside>

            <main className="app-main">{isManager(user) && <GlobalSearch onNavigate={navigateTo} />}{content}</main>
          </div>
        </IonContent>

        <nav className="mobile-tabbar" aria-label="Hauptnavigation">
          {mobilePrimaryItems.map(([key, label]) => (
            <button
              type="button"
              key={key}
              className={view === key ? 'active' : ''}
              onClick={() => navigateTo(key)}
              aria-current={view === key ? 'page' : undefined}
            >
              <IonIcon icon={icons[key]} />
              <span>{mobileLabels[key] || label}</span>
            </button>
          ))}
          <button
            type="button"
            className={!primaryViews.includes(view) ? 'active' : ''}
            onClick={() => setMobileMenuOpen(true)}
            aria-label="Weitere Bereiche öffnen"
          >
            <IonIcon icon={appsOutline} />
            <span>Mehr</span>
          </button>
        </nav>

        <IonModal
          isOpen={mobileMenuOpen}
          onDidDismiss={() => setMobileMenuOpen(false)}
          initialBreakpoint={0.72}
          breakpoints={[0, 0.72, 1]}
          className="mobile-menu-modal"
        >
          <IonContent>
            <div className="mobile-menu-sheet">
              <div className="mobile-menu-handle" />
              <div className="mobile-menu-user">
                <div className="avatar">{user.name[0]}</div>
                <div>
                  <strong>{user.name}</strong>
                  <small>{user.email}</small>
                </div>
              </div>
              <div className="mobile-menu-heading">
                <div>
                  <small>A+ WORKFORCE</small>
                  <h2>Weitere Bereiche</h2>
                </div>
                <button type="button" onClick={() => setMobileMenuOpen(false)}>Fertig</button>
              </div>
              <div className="mobile-menu-grid">
                {mobileMoreItems.map(([key, label]) => (
                  <button
                    type="button"
                    key={key}
                    className={view === key ? 'active' : ''}
                    onClick={() => navigateTo(key)}
                  >
                    <span className="mobile-menu-icon"><IonIcon icon={icons[key]} /></span>
                    <strong>{label}</strong>
                  </button>
                ))}
                <button type="button" className={view === 'profile' ? 'active' : ''} onClick={() => navigateTo('profile')}>
                  <span className="mobile-menu-icon"><IonIcon icon={peopleOutline} /></span>
                  <strong>Profil</strong>
                </button>
              </div>
              <button className="mobile-logout" type="button" onClick={logout}>
                <IonIcon icon={exitOutline} />
                Abmelden
              </button>
            </div>
          </IonContent>
        </IonModal>
      </IonPage>
    </IonApp>
  );
}
