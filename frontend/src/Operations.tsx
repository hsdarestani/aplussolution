import React, { useEffect, useMemo, useState } from 'react';
import {
  IonBadge,
  IonButton,
  IonCard,
  IonCardContent,
  IonIcon,
  IonInput,
  IonItem,
  IonLabel,
  IonModal,
  IonSelect,
  IonSelectOption,
  IonSpinner,
  IonTextarea,
  IonToast,
  IonToggle,
} from '@ionic/react';
import {
  alertCircleOutline,
  calendarOutline,
  checkmarkCircleOutline,
  cloudDownloadOutline,
  copyOutline,
  documentTextOutline,
  notificationsOutline,
  peopleOutline,
  refreshOutline,
  swapHorizontalOutline,
  trashOutline,
  warningOutline,
} from 'ionicons/icons';
import { api, User } from './api';
import './operations.css';

const unpack = (data: any): any[] => data?.results || data || [];
const value = (event: any) => event.detail.value ?? '';
const dateTime = (input?: string) => (input ? new Date(input).toLocaleString('de-DE') : '–');
const dateOnly = (input?: string) => (input ? new Date(input).toLocaleDateString('de-DE') : '–');
const isManager = (user: User) => ['admin', 'manager'].includes(user.role);
const API = String(import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '');

function Title({ title, text, action }: { title: string; text: string; action?: React.ReactNode }) {
  return (
    <div className="title">
      <div>
        <h1>{title}</h1>
        <p>{text}</p>
      </div>
      {action}
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="empty">{children}</div>;
}

function Modal({
  open,
  title,
  close,
  save,
  busy,
  saveLabel = 'Speichern',
  children,
}: {
  open: boolean;
  title: string;
  close: () => void;
  save: () => void;
  busy?: boolean;
  saveLabel?: string;
  children: React.ReactNode;
}) {
  return (
    <IonModal isOpen={open} onDidDismiss={close}>
      <div className="operations-modal">
        <div className="operations-modal-head">
          <div>
            <small>A+ WORKFORCE</small>
            <h2>{title}</h2>
          </div>
          <IonButton fill="clear" onClick={close}>Schließen</IonButton>
        </div>
        <div className="operations-form">{children}</div>
        <div className="operations-modal-actions">
          <IonButton fill="outline" onClick={close}>Abbrechen</IonButton>
          <IonButton disabled={busy} onClick={save}>
            {busy ? <IonSpinner name="dots" /> : saveLabel}
          </IonButton>
        </div>
      </div>
    </IonModal>
  );
}

function FindingList({ items, empty }: { items: any[]; empty: string }) {
  if (!items?.length) return <Empty>{empty}</Empty>;
  return (
    <div>
      {items.map((item, index) => (
        <div className="operations-row" key={item.shift || item.order || item.worker || index}>
          <IonIcon icon={item.severity === 'error' ? alertCircleOutline : warningOutline} />
          <div className="operations-grow">
            <b>{item.worker_name || item.title || item.client_name || 'Hinweis'}</b>
            <p>{item.message}</p>
            {item.starts_at && <small>{dateTime(item.starts_at)}</small>}
          </div>
          {item.gap != null && <IonBadge color="warning">{item.gap} offen</IonBadge>}
          {item.difference_minutes != null && (
            <IonBadge color="warning">+{Math.round(item.difference_minutes / 60)} Std.</IonBadge>
          )}
        </div>
      ))}
    </div>
  );
}

function Readiness({ data }: { data: any }) {
  if (!data) return null;
  const rows = [
    ['Google Login', data.google_login],
    ['Apple Login', data.apple_login],
    ['E-Mail-Versand', data.email_delivery],
    ['Firmendaten', data.company_legal_data],
    ['AÜG-Angaben', data.aueg_data],
    ['8 finale Vertragsvorlagen', data.final_contract_set_complete],
    ['Android-Signierung', data.android_signing_configured],
    ['iOS-Signierung', data.ios_signing_configured],
    ['Store-API-Zugänge', data.store_api_credentials_configured],
  ];
  return (
    <div className="readiness-list">
      {rows.map(([label, ready]) => (
        <div className="readiness-item" key={String(label)}>
          <IonIcon icon={ready ? checkmarkCircleOutline : alertCircleOutline} />
          <span>{label}</span>
          <IonBadge color={ready ? 'success' : 'warning'}>{ready ? 'Bereit' : 'Fehlt'}</IonBadge>
        </div>
      ))}
      <div className="template-counts">
        {Object.entries(data.contract_templates || {}).map(([kind, count]) => (
          <span key={kind}>{kind}: <b>{String(count)}</b></span>
        ))}
      </div>
    </div>
  );
}

function Notifications({ rows, readAll }: { rows: any[]; readAll: () => void }) {
  return (
    <section className="operations-panel">
      <div className="operations-head">
        <div>
          <h3>Benachrichtigungen</h3>
          <p>Verträge, Schichten, Tausch und Systemhinweise.</p>
        </div>
        {!!rows?.length && <IonButton fill="outline" size="small" onClick={readAll}>Alle gelesen</IonButton>}
      </div>
      {rows?.map((notification) => (
        <div className={`operations-row ${notification.read_at ? '' : 'unread'}`} key={notification.id}>
          <IonIcon icon={notificationsOutline} />
          <div className="operations-grow">
            <b>{notification.title}</b>
            <p>{notification.body}</p>
            <small>{dateTime(notification.created_at)}</small>
          </div>
          {!notification.read_at && <IonBadge>Neu</IonBadge>}
        </div>
      ))}
      {!rows?.length && <Empty>Keine Benachrichtigungen vorhanden.</Empty>}
    </section>
  );
}

export default function Operations({ user }: { user: User }) {
  const [data, setData] = useState<any>();
  const [folders, setFolders] = useState<any>({ workers: [], clients: [] });
  const [draftShifts, setDraftShifts] = useState<any[]>([]);
  const [modal, setModal] = useState('');
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState('');
  const [availability, setAvailability] = useState<any>({ available: true });
  const [swap, setSwap] = useState<any>({});
  const [copyWeek, setCopyWeek] = useState<any>({});
  const [report, setReport] = useState<any>({ month: new Date().toISOString().slice(0, 7) });
  const [templateFile, setTemplateFile] = useState<File>();

  const load = async () => {
    const overview = await api('operations/');
    setData(overview);
    const folderData = await api('operations/folders/');
    setFolders(folderData);
    if (isManager(user)) {
      const shifts = await api('shifts/?status=draft&ordering=starts_at');
      setDraftShifts(unpack(shifts));
    }
  };

  useEffect(() => {
    void load();
  }, []);

  async function run(path: string, payload: any = {}, success = 'Gespeichert.') {
    setBusy(true);
    try {
      const result: any = await api(path, { method: 'POST', body: JSON.stringify(payload) });
      setToast(result.detail || success);
      setModal('');
      await load();
      return result;
    } catch (reason: any) {
      setToast(reason.message);
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function createAvailability() {
    const result = await run('operations/availability/', availability, 'Verfügbarkeit wurde gespeichert.');
    if (result) setAvailability({ available: true });
  }

  async function deleteAvailability(id: string) {
    if (!window.confirm('Diesen Verfügbarkeitseintrag löschen?')) return;
    try {
      await api(`operations/availability/${id}/`, { method: 'DELETE' });
      setToast('Eintrag wurde gelöscht.');
      await load();
    } catch (reason: any) {
      setToast(reason.message);
    }
  }

  async function createSwap() {
    const result = await run('operations/swaps/', swap, 'Tauschanfrage wurde gesendet.');
    if (result) setSwap({});
  }

  async function decideSwap(id: string, status: string) {
    await run(`operations/swaps/${id}/decide/`, { status }, 'Tauschanfrage wurde aktualisiert.');
  }

  async function copyScheduleWeek() {
    const result = await run('operations/copy-week/', copyWeek, 'Woche wurde kopiert.');
    if (result) {
      setToast(`${result.created?.length || 0} Schichten kopiert. ${result.warnings?.length || 0} Warnungen.`);
      setCopyWeek({});
    }
  }

  async function publishDrafts() {
    if (!draftShifts.length) {
      setToast('Keine Entwürfe vorhanden.');
      return;
    }
    await run('operations/bulk-publish/', { ids: draftShifts.map((shift) => shift.id) }, 'Entwürfe wurden veröffentlicht.');
  }

  async function readAll() {
    await run('operations/notifications/read-all/', {}, 'Benachrichtigungen wurden als gelesen markiert.');
  }

  async function importTemplates() {
    if (!templateFile) return;
    setBusy(true);
    const form = new FormData();
    form.append('file', templateFile);
    try {
      const result: any = await api('operations/templates/import/', { method: 'POST', body: form });
      setToast(`${result.created} Vorlage(n) erstellt, ${result.updated} aktualisiert, ${result.errors?.length || 0} Fehler.`);
      setTemplateFile(undefined);
      setModal('');
      await load();
    } catch (reason: any) {
      setToast(reason.message);
    } finally {
      setBusy(false);
    }
  }

  async function download(path: string, filename: string) {
    setBusy(true);
    try {
      const access = localStorage.getItem('access');
      const response = await fetch(`${API}/${path}`, {
        headers: access ? { Authorization: `Bearer ${access}` } : {},
      });
      if (!response.ok) throw new Error('Export konnte nicht erstellt werden.');
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      URL.revokeObjectURL(url);
      setToast('Export wurde erstellt.');
    } catch (reason: any) {
      setToast(reason.message);
    } finally {
      setBusy(false);
    }
  }

  const riskTotal = useMemo(() => {
    if (!data) return 0;
    return (data.conflicts?.length || 0)
      + (data.unavailable_assignments?.length || 0)
      + (data.coverage_gaps?.length || 0)
      + (data.overtime_risks?.length || 0);
  }, [data]);

  if (!data) {
    return <div className="loader"><IonSpinner /><p>Steuerzentrale wird geladen …</p></div>;
  }

  const pageTitle = isManager(user)
    ? 'Steuerzentrale'
    : user.role === 'worker'
      ? 'Verfügbarkeit & Tausch'
      : 'Servicecenter';
  const pageText = isManager(user)
    ? 'Planungsqualität, Berichte, Akten, Erinnerungen und Release-Bereitschaft.'
    : user.role === 'worker'
      ? 'Verfügbarkeiten pflegen, Schichten tauschen und Benachrichtigungen verfolgen.'
      : 'Einsatzabdeckung, Vertragsfristen, Dokumente und Benachrichtigungen.';

  return (
    <>
      <Title
        title={pageTitle}
        text={pageText}
        action={<IonButton fill="outline" disabled={busy} onClick={() => load()}><IonIcon slot="start" icon={refreshOutline} />Aktualisieren</IonButton>}
      />

      {isManager(user) && (
        <>
          <div className="operations-stats">
            <IonCard><IonCardContent><small>Planungsrisiken</small><strong>{riskTotal}</strong></IonCardContent></IonCard>
            <IonCard><IonCardContent><small>Offene Tauschanfragen</small><strong>{data.pending_swaps || 0}</strong></IonCardContent></IonCard>
            <IonCard><IonCardContent><small>Ungeprüfte Zeiten</small><strong>{data.unapproved_time_entries || 0}</strong></IonCardContent></IonCard>
            <IonCard><IonCardContent><small>Verträge ≤ 30 Tage</small><strong>{data.contracts_due_30 || 0}</strong></IonCardContent></IonCard>
            <IonCard><IonCardContent><small>Geplante Lohnkosten</small><strong>{Number(data.estimated_monthly_labor_cost || 0).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}</strong></IonCardContent></IonCard>
          </div>

          <div className="operations-grid two">
            <section className="operations-panel">
              <div className="operations-head"><div><h3>Schichtkonflikte</h3><p>Überschneidungen derselben Person.</p></div><IonBadge color={data.conflicts?.length ? 'danger' : 'success'}>{data.conflicts?.length || 0}</IonBadge></div>
              <FindingList items={data.conflicts || []} empty="Keine Schichtüberschneidungen gefunden." />
            </section>
            <section className="operations-panel">
              <div className="operations-head"><div><h3>Verfügbarkeit</h3><p>Zuweisungen trotz Nichtverfügbarkeit.</p></div><IonBadge color={data.unavailable_assignments?.length ? 'warning' : 'success'}>{data.unavailable_assignments?.length || 0}</IonBadge></div>
              <FindingList items={data.unavailable_assignments || []} empty="Alle Zuweisungen passen zu den Verfügbarkeiten." />
            </section>
            <section className="operations-panel">
              <div className="operations-head"><div><h3>Personalabdeckung</h3><p>Aufträge mit unbesetzten Positionen.</p></div><IonBadge color={data.coverage_gaps?.length ? 'warning' : 'success'}>{data.coverage_gaps?.length || 0}</IonBadge></div>
              <FindingList items={data.coverage_gaps || []} empty="Alle Aufträge sind vollständig besetzt." />
            </section>
            <section className="operations-panel">
              <div className="operations-head"><div><h3>Stundenrisiken</h3><p>Geplante Stunden über Monatsziel.</p></div><IonBadge color={data.overtime_risks?.length ? 'warning' : 'success'}>{data.overtime_risks?.length || 0}</IonBadge></div>
              <FindingList items={data.overtime_risks || []} empty="Keine Überschreitung der Monatsstunden." />
            </section>
          </div>

          <div className="operations-grid two">
            <section className="operations-panel">
              <div className="operations-head"><div><h3>Planungswerkzeuge</h3><p>Woche kopieren und Entwürfe gesammelt veröffentlichen.</p></div><IonIcon icon={calendarOutline} /></div>
              <div className="operations-actions">
                <IonButton onClick={() => setModal('copy-week')}><IonIcon slot="start" icon={copyOutline} />Woche kopieren</IonButton>
                <IonButton fill="outline" onClick={publishDrafts}>Alle {draftShifts.length} Entwürfe veröffentlichen</IonButton>
              </div>
              <div className="operations-note">Beim Kopieren werden kollidierende Zuweisungen automatisch als OpenShift angelegt.</div>
            </section>
            <section className="operations-panel">
              <div className="operations-head"><div><h3>Berichte & Exporte</h3><p>CSV für Planung, Stunden und Lohnvorbereitung.</p></div><IonIcon icon={cloudDownloadOutline} /></div>
              <div className="report-fields">
                <IonInput fill="outline" type="month" label="Monat" labelPlacement="floating" value={report.month} onIonInput={(event) => setReport({ ...report, month: value(event) })} />
                <IonInput fill="outline" type="date" label="Von" labelPlacement="floating" value={report.date_from} onIonInput={(event) => setReport({ ...report, date_from: value(event) })} />
                <IonInput fill="outline" type="date" label="Bis" labelPlacement="floating" value={report.date_to} onIonInput={(event) => setReport({ ...report, date_to: value(event) })} />
              </div>
              <div className="operations-actions">
                <IonButton fill="outline" onClick={() => download(`reports/timesheets.csv?month=${report.month}`, `zeiterfassung-${report.month}.csv`)}>Zeiterfassung</IonButton>
                <IonButton fill="outline" onClick={() => download(`reports/payroll-estimate.csv?month=${report.month}`, `lohn-schaetzung-${report.month}.csv`)}>Lohnschätzung</IonButton>
                <IonButton fill="outline" onClick={() => download(`reports/schedule.csv?date_from=${report.date_from || ''}&date_to=${report.date_to || ''}`, 'dienstplan.csv')}>Dienstplan</IonButton>
              </div>
            </section>
          </div>

          <div className="operations-grid two">
            <section className="operations-panel">
              <div className="operations-head"><div><h3>Produktionsbereitschaft</h3><p>Externe Credentials und finale Inhalte.</p></div><IonIcon icon={checkmarkCircleOutline} /></div>
              <Readiness data={data.readiness} />
              <IonButton fill="outline" onClick={() => setModal('templates')}><IonIcon slot="start" icon={documentTextOutline} />Vertragsvorlagen importieren</IonButton>
            </section>
            <section className="operations-panel">
              <div className="operations-head"><div><h3>Digitale Akten</h3><p>Vollständigkeit je Mitarbeiter und Kunde.</p></div><IonIcon icon={peopleOutline} /></div>
              <div className="folder-scroll">
                {folders.workers?.map((folder: any) => (
                  <div className="folder-card" key={folder.id}><b>{folder.name}</b><small>{folder.employee_number}</small><span>{folder.documents} Dokumente · {folder.contracts} Verträge · {folder.payroll} Lohn</span></div>
                ))}
                {folders.clients?.map((folder: any) => (
                  <div className="folder-card" key={folder.id}><b>{folder.name}</b><small>{folder.customer_number}</small><span>{folder.documents} Dokumente · {folder.contracts} Verträge · {folder.orders} Aufträge</span></div>
                ))}
                {!folders.workers?.length && !folders.clients?.length && <Empty>Keine Akten vorhanden.</Empty>}
              </div>
            </section>
          </div>
        </>
      )}

      {user.role === 'worker' && (
        <div className="operations-grid two">
          <section className="operations-panel">
            <div className="operations-head"><div><h3>Meine Verfügbarkeit</h3><p>Verfügbar oder gesperrt für einen Zeitraum.</p></div><IonButton size="small" onClick={() => setModal('availability')}>Eintragen</IonButton></div>
            {data.availabilities?.map((item: any) => (
              <div className="operations-row" key={item.id}>
                <IonIcon icon={calendarOutline} />
                <div className="operations-grow"><b>{item.available ? 'Verfügbar' : 'Nicht verfügbar'}</b><p>{dateTime(item.starts_at)} – {dateTime(item.ends_at)}</p><small>{item.note}</small></div>
                <IonBadge color={item.available ? 'success' : 'medium'}>{item.available ? 'Ja' : 'Gesperrt'}</IonBadge>
                <IonButton fill="clear" color="danger" onClick={() => deleteAvailability(item.id)}><IonIcon icon={trashOutline} /></IonButton>
              </div>
            ))}
            {!data.availabilities?.length && <Empty>Noch keine Verfügbarkeiten eingetragen.</Empty>}
          </section>
          <section className="operations-panel">
            <div className="operations-head"><div><h3>Schichttausch</h3><p>Eigene Schicht zur Übernahme anbieten.</p></div><IonButton size="small" onClick={() => setModal('swap')}>Tausch anfragen</IonButton></div>
            {data.swaps?.map((item: any) => (
              <div className="operations-row" key={item.id}>
                <IonIcon icon={swapHorizontalOutline} />
                <div className="operations-grow"><b>{item.shift_title}</b><p>{dateTime(item.shift_starts_at)} · {item.offered_to_name || 'Offene Anfrage'}</p><small>{item.note}</small></div>
                <IonBadge>{item.status}</IonBadge>
                {item.status === 'pending' && item.requested_by === user.worker_profile_id && <IonButton fill="clear" color="danger" onClick={() => decideSwap(item.id, 'cancelled')}>Stornieren</IonButton>}
                {item.status === 'pending' && item.offered_to_name && <div className="swap-actions"><IonButton size="small" color="success" onClick={() => decideSwap(item.id, 'approved')}>Annehmen</IonButton><IonButton size="small" color="danger" onClick={() => decideSwap(item.id, 'rejected')}>Ablehnen</IonButton></div>}
              </div>
            ))}
            {!data.swaps?.length && <Empty>Noch keine Tauschanfragen.</Empty>}
          </section>
        </div>
      )}

      {user.role === 'client' && (
        <div className="operations-grid two">
          <section className="operations-panel">
            <div className="operations-head"><div><h3>Einsatzabdeckung</h3><p>Offener Personalbedarf deiner Aufträge.</p></div><IonBadge color={data.coverage_gaps?.length ? 'warning' : 'success'}>{data.coverage_gaps?.length || 0}</IonBadge></div>
            <FindingList items={data.coverage_gaps || []} empty="Alle kommenden Aufträge sind abgedeckt." />
          </section>
          <section className="operations-panel client-summary">
            <div><small>Offene Aufträge</small><strong>{data.open_orders || 0}</strong></div>
            <div><small>Vertragsfristen</small><strong>{data.contracts_due || 0}</strong></div>
            <div><small>Dokumente</small><strong>{data.documents || 0}</strong></div>
          </section>
        </div>
      )}

      <Notifications rows={data.notifications || []} readAll={readAll} />

      <Modal open={modal === 'availability'} title="Verfügbarkeit eintragen" close={() => setModal('')} save={createAvailability} busy={busy}>
        <IonInput fill="outline" type="datetime-local" label="Beginn" labelPlacement="floating" value={availability.starts_at} onIonInput={(event) => setAvailability({ ...availability, starts_at: value(event) })} />
        <IonInput fill="outline" type="datetime-local" label="Ende" labelPlacement="floating" value={availability.ends_at} onIonInput={(event) => setAvailability({ ...availability, ends_at: value(event) })} />
        <IonItem lines="none" className="operations-toggle"><IonLabel>In diesem Zeitraum verfügbar</IonLabel><IonToggle checked={availability.available !== false} onIonChange={(event) => setAvailability({ ...availability, available: event.detail.checked })} /></IonItem>
        <IonTextarea fill="outline" label="Hinweis" labelPlacement="floating" value={availability.note} onIonInput={(event) => setAvailability({ ...availability, note: value(event) })} />
      </Modal>

      <Modal open={modal === 'swap'} title="Schichttausch anfragen" close={() => setModal('')} save={createSwap} busy={busy} saveLabel="Anfrage senden">
        <IonSelect fill="outline" label="Eigene Schicht" labelPlacement="floating" value={swap.shift} onIonChange={(event) => setSwap({ ...swap, shift: value(event) })}>
          {data.upcoming_shifts?.map((shift: any) => <IonSelectOption value={shift.id} key={shift.id}>{shift.position_name} · {dateTime(shift.starts_at)}</IonSelectOption>)}
        </IonSelect>
        <IonSelect fill="outline" label="Anbieten an" labelPlacement="floating" value={swap.offered_to} onIonChange={(event) => setSwap({ ...swap, offered_to: value(event) })}>
          <IonSelectOption value="">Offene Anfrage an Disposition</IonSelectOption>
          {data.swap_candidates?.map((candidate: any) => <IonSelectOption value={candidate.id} key={candidate.id}>{candidate.name}</IonSelectOption>)}
        </IonSelect>
        <IonTextarea fill="outline" label="Hinweis" labelPlacement="floating" value={swap.note} onIonInput={(event) => setSwap({ ...swap, note: value(event) })} />
      </Modal>

      <Modal open={modal === 'copy-week'} title="Dienstplanwoche kopieren" close={() => setModal('')} save={copyScheduleWeek} busy={busy} saveLabel="Woche kopieren">
        <IonInput fill="outline" type="date" label="Datum in der Quellwoche" labelPlacement="floating" value={copyWeek.source_start} onIonInput={(event) => setCopyWeek({ ...copyWeek, source_start: value(event) })} />
        <IonInput fill="outline" type="date" label="Datum in der Zielwoche" labelPlacement="floating" value={copyWeek.target_start} onIonInput={(event) => setCopyWeek({ ...copyWeek, target_start: value(event) })} />
        <div className="operations-note full">Die Zielwoche wird immer Montag bis Sonntag berechnet. Neue Schichten starten als Entwurf.</div>
      </Modal>

      <Modal open={modal === 'templates'} title="Vertragsvorlagen importieren" close={() => setModal('')} save={importTemplates} busy={busy} saveLabel="JSON importieren">
        <label className="operations-file full"><span>JSON-Datei mit einer oder mehreren Vorlagen</span><input type="file" accept=".json,application/json" onChange={(event) => setTemplateFile(event.target.files?.[0])} /><b>{templateFile?.name || 'Keine Datei ausgewählt'}</b></label>
        <div className="operations-note full">Pflichtfelder: name, kind, version, schema und html_template. Bestehende Kombinationen aus Name und Version werden aktualisiert.</div>
      </Modal>

      <IonToast isOpen={!!toast} message={toast} duration={4500} onDidDismiss={() => setToast('')} />
    </>
  );
}
