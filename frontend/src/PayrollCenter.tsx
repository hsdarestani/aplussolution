import React, { useEffect, useMemo, useState } from 'react';
import {
  IonBadge,
  IonButton,
  IonIcon,
  IonInput,
  IonModal,
  IonSelect,
  IonSelectOption,
  IonSpinner,
  IonTextarea,
  IonToast,
} from '@ionic/react';
import {
  checkmarkCircleOutline,
  closeCircleOutline,
  cloudDownloadOutline,
  documentTextOutline,
  lockClosedOutline,
  refreshOutline,
  syncOutline,
  warningOutline,
} from 'ionicons/icons';
import { api, apiAll, apiDownload, User } from './api';
import './payroll-center.css';

const isManager = (user: User) => ['admin', 'manager'].includes(user.role);
const eventValue = (event: any) => event.detail.value ?? '';
const hours = (minutes = 0) => (Number(minutes || 0) / 60).toFixed(2).replace('.', ',');
const money = (value: any, currency = 'EUR') => new Intl.NumberFormat('de-DE', { style: 'currency', currency }).format(Number(value || 0));
const dateOnly = (value?: string) => value ? new Date(`${value}T12:00:00`).toLocaleDateString('de-DE') : '–';
const dateTime = (value?: string) => value ? new Date(value).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '–';

const periodLabels: Record<string, string> = { open: 'Offen', review: 'In Prüfung', closed: 'Geschlossen', locked: 'Gesperrt' };
const sheetLabels: Record<string, string> = { open: 'Offen', submitted: 'Eingereicht', approved: 'Freigegeben', reopened: 'Wieder geöffnet', locked: 'Gesperrt' };
const exceptionLabels: Record<string, string> = {
  missing_entry: 'Zeiteintrag fehlt', running_entry: 'Timer läuft noch', unapproved_entry: 'Zeiteintrag nicht freigegeben',
  rejected_entry: 'Zeiteintrag abgelehnt', pending_correction: 'Korrekturanfrage offen', attendance_notice: 'Attendance-Hinweis offen',
};

export default function PayrollCenter({ user }: { user: User }) {
  const manager = isManager(user);
  const [periods, setPeriods] = useState<any[]>([]);
  const [selectedPeriodId, setSelectedPeriodId] = useState('');
  const [timesheets, setTimesheets] = useState<any[]>([]);
  const [selectedSheetId, setSelectedSheetId] = useState('');
  const [periodForm, setPeriodForm] = useState<any>();
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState('');

  const selectedPeriod = periods.find((item) => item.id === selectedPeriodId);
  const selectedSheet = timesheets.find((item) => item.id === selectedSheetId) || timesheets[0];

  async function loadPeriods(preferred?: string) {
    if (!manager) return;
    const rows = await apiAll<any>('pay-periods/?ordering=-starts_on');
    setPeriods(rows);
    const wanted = preferred || selectedPeriodId || rows[0]?.id || '';
    setSelectedPeriodId(wanted);
    return wanted;
  }

  async function loadTimesheets(periodId?: string, preferredSheet?: string) {
    const path = manager && periodId ? `timesheets/?pay_period=${periodId}` : 'timesheets/';
    const rows = await apiAll<any>(path);
    setTimesheets(rows);
    const wanted = preferredSheet || selectedSheetId || rows[0]?.id || '';
    setSelectedSheetId(rows.some((item) => item.id === wanted) ? wanted : rows[0]?.id || '');
  }

  async function load() {
    try {
      if (manager) {
        const periodId = await loadPeriods();
        if (periodId) await loadTimesheets(periodId);
        else setTimesheets([]);
      } else {
        await loadTimesheets();
      }
    } catch (error: any) {
      setToast(error.message);
    }
  }

  useEffect(() => { void load(); }, []);
  useEffect(() => {
    if (manager && selectedPeriodId) void loadTimesheets(selectedPeriodId);
  }, [selectedPeriodId]);

  async function mutate(path: string, body: any = {}, success = 'Gespeichert.') {
    setBusy(true);
    try {
      const result: any = await api(path, { method: 'POST', body: JSON.stringify(body) });
      setToast(success);
      if (manager) {
        const periodId = await loadPeriods(selectedPeriodId);
        if (periodId) await loadTimesheets(periodId, selectedSheetId);
      } else {
        await loadTimesheets(undefined, selectedSheetId);
      }
      return result;
    } catch (error: any) {
      setToast(error.message);
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function createPeriod() {
    if (!periodForm?.name || !periodForm?.starts_on || !periodForm?.ends_on) {
      setToast('Name, Start und Ende sind erforderlich.');
      return;
    }
    setBusy(true);
    try {
      const result: any = await api('pay-periods/', { method: 'POST', body: JSON.stringify({ ...periodForm, currency: 'EUR' }) });
      setPeriodForm(undefined);
      await loadPeriods(result.id);
      await loadTimesheets(result.id);
      setToast('Pay Period wurde angelegt.');
    } catch (error: any) { setToast(error.message); }
    finally { setBusy(false); }
  }

  async function periodAction(action: 'sync' | 'close' | 'reopen' | 'lock' | 'unlock') {
    if (!selectedPeriod) return;
    let reason = '';
    if (['reopen', 'unlock'].includes(action)) {
      reason = window.prompt(action === 'unlock' ? 'Grund für das Entsperren:' : 'Grund für das Wiederöffnen:') || '';
      if (!reason) return;
    }
    const labels: Record<string, string> = {
      sync: 'Timesheets wurden aus Attendance synchronisiert.', close: 'Pay Period wurde geschlossen.',
      reopen: 'Pay Period wurde wieder geöffnet.', lock: 'Pay Period wurde final gesperrt.', unlock: 'Pay Period wurde entsperrt.',
    };
    await mutate(`pay-periods/${selectedPeriod.id}/${action}/`, reason ? { reason } : {}, labels[action]);
  }

  async function reviewEntry(id: string, decision: 'approved' | 'rejected') {
    let note = '';
    if (decision === 'rejected') {
      note = window.prompt('Grund für die Ablehnung:') || '';
      if (!note) return;
    }
    await mutate(`timesheet-entries/${id}/review/`, { decision, note }, decision === 'approved' ? 'Zeiteintrag freigegeben.' : 'Zeiteintrag abgelehnt.');
  }

  async function timesheetAction(action: 'submit' | 'approve' | 'unapprove' | 'approve-all-entries') {
    if (!selectedSheet) return;
    let body: any = {};
    if (action === 'unapprove') {
      const reason = window.prompt('Warum wird das Timesheet wieder geöffnet?') || '';
      if (!reason) return;
      body = { reason };
    }
    await mutate(`timesheets/${selectedSheet.id}/${action}/`, body,
      action === 'submit' ? 'Timesheet wurde eingereicht.' : action === 'approve' ? 'Timesheet wurde freigegeben.' : action === 'unapprove' ? 'Timesheet wurde wieder geöffnet.' : 'Alle Einträge wurden freigegeben.');
  }

  async function exceptionAction(id: string, action: 'resolve' | 'dismiss') {
    const note = window.prompt(action === 'dismiss' ? 'Begründung für das Verwerfen:' : 'Lösung / Notiz:') || '';
    if (!note) return;
    await mutate(`timesheet-exceptions/${id}/${action}/`, { note }, action === 'resolve' ? 'Ausnahme erledigt.' : 'Ausnahme verworfen.');
  }

  async function download(format: 'csv' | 'xlsx') {
    if (!selectedPeriod) return;
    try { await apiDownload(`pay-periods/${selectedPeriod.id}/export-${format}/`, `pay-period.${format}`); }
    catch (error: any) { setToast(error.message); }
  }

  if (!manager) return <WorkerPayroll timesheets={timesheets} selected={selectedSheet} setSelected={setSelectedSheetId} busy={busy} submit={() => void timesheetAction('submit')} />;

  const openExceptions = selectedSheet?.exceptions?.filter((item: any) => item.status === 'open') || [];
  const approvedSheets = selectedPeriod?.approved_count || 0;
  return <div className="payroll-center">
    <section className="payroll-hero">
      <div><small>PAY PERIODS & TIMESHEETS</small><h1>Abrechnung kontrolliert abschließen</h1><p>Attendance synchronisieren, Ausnahmen prüfen, Zeiten freigeben und den Abrechnungszeitraum revisionssicher schließen.</p></div>
      <IonButton onClick={() => setPeriodForm({})}>Neuer Pay Period</IonButton>
    </section>

    <section className="payroll-period-bar">
      <IonSelect fill="outline" label="Abrechnungszeitraum" labelPlacement="floating" value={selectedPeriodId} onIonChange={(e) => setSelectedPeriodId(String(eventValue(e)))}>
        {periods.map((period) => <IonSelectOption key={period.id} value={period.id}>{period.name} · {dateOnly(period.starts_on)}–{dateOnly(period.ends_on)}</IonSelectOption>)}
      </IonSelect>
      {selectedPeriod && <div className="period-actions">
        <IonBadge color={selectedPeriod.status === 'locked' ? 'dark' : selectedPeriod.status === 'closed' ? 'success' : selectedPeriod.blocking_count ? 'danger' : 'primary'}>{periodLabels[selectedPeriod.status] || selectedPeriod.status}</IonBadge>
        {!['closed', 'locked'].includes(selectedPeriod.status) && <IonButton fill="outline" disabled={busy} onClick={() => void periodAction('sync')}><IonIcon slot="start" icon={syncOutline}/>Sync</IonButton>}
        {!['closed', 'locked'].includes(selectedPeriod.status) && <IonButton disabled={busy} onClick={() => void periodAction('close')}>Schließen</IonButton>}
        {selectedPeriod.status === 'closed' && <><IonButton fill="outline" onClick={() => void periodAction('reopen')}>Wieder öffnen</IonButton><IonButton onClick={() => void periodAction('lock')}><IonIcon slot="start" icon={lockClosedOutline}/>Final sperren</IonButton></>}
        {selectedPeriod.status === 'locked' && user.role === 'admin' && <IonButton fill="outline" color="warning" onClick={() => void periodAction('unlock')}>Entsperren</IonButton>}
        <IonButton fill="clear" onClick={() => void download('csv')}><IonIcon slot="start" icon={cloudDownloadOutline}/>CSV</IonButton>
        <IonButton fill="clear" onClick={() => void download('xlsx')}><IonIcon slot="start" icon={cloudDownloadOutline}/>XLSX</IonButton>
      </div>}
    </section>

    {!selectedPeriod ? <div className="payroll-empty">Noch kein Pay Period vorhanden.</div> : <>
      <div className="payroll-stats">
        <Stat label="Timesheets" value={selectedPeriod.timesheet_count || 0}/>
        <Stat label="Freigegeben" value={`${approvedSheets}/${selectedPeriod.timesheet_count || 0}`}/>
        <Stat label="Blocker" value={selectedPeriod.blocking_count || 0} danger={selectedPeriod.blocking_count > 0}/>
        <Stat label="Netto Stunden" value={hours(selectedPeriod.net_minutes)}/>
        <Stat label="Brutto Schätzung" value={money(selectedPeriod.gross_estimate, selectedPeriod.currency)}/>
      </div>

      <div className="payroll-workspace">
        <aside className="timesheet-list">
          <div className="payroll-section-head"><div><small>MITARBEITER</small><h2>Timesheets</h2></div><IonIcon icon={documentTextOutline}/></div>
          {timesheets.map((sheet) => <button key={sheet.id} className={selectedSheet?.id === sheet.id ? 'active' : ''} onClick={() => setSelectedSheetId(sheet.id)}>
            <span><b>{sheet.worker_name}</b><small>{sheet.employee_number} · {hours(sheet.net_minutes)} Std.</small></span>
            <span className="sheet-state"><IonBadge color={sheet.blocking_exception_count ? 'danger' : sheet.status === 'approved' || sheet.status === 'locked' ? 'success' : 'medium'}>{sheet.blocking_exception_count ? `${sheet.blocking_exception_count} Blocker` : sheetLabels[sheet.status] || sheet.status}</IonBadge></span>
          </button>)}
          {!timesheets.length && <div className="payroll-empty compact">Noch keine Timesheets. „Sync“ starten.</div>}
        </aside>

        <main className="timesheet-detail">
          {!selectedSheet ? <div className="payroll-empty">Timesheet auswählen.</div> : <>
            <header className="timesheet-head">
              <div><small>{selectedSheet.employee_number}</small><h2>{selectedSheet.worker_name}</h2><p>Revision {selectedSheet.revision} · {selectedSheet.entry_count} Zeiteinträge · {selectedSheet.exception_count} offene Ausnahmen</p></div>
              <div><IonBadge color={selectedSheet.status === 'approved' || selectedSheet.status === 'locked' ? 'success' : 'medium'}>{sheetLabels[selectedSheet.status] || selectedSheet.status}</IonBadge></div>
            </header>
            <div className="sheet-totals"><Stat label="Netto" value={`${hours(selectedSheet.net_minutes)} Std.`}/><Stat label="Unbez. Pause" value={`${selectedSheet.unpaid_break_minutes} Min.`}/><Stat label="Brutto Schätzung" value={money(selectedSheet.gross_estimate, selectedPeriod.currency)}/></div>

            <section className="timesheet-actions">
              {!['closed', 'locked'].includes(selectedPeriod.status) && <>
                <IonButton fill="outline" disabled={busy || !selectedSheet.entries?.length} onClick={() => void timesheetAction('approve-all-entries')}>Alle Einträge freigeben</IonButton>
                {selectedSheet.status !== 'approved' && <IonButton disabled={busy || selectedSheet.blocking_exception_count > 0} onClick={() => void timesheetAction('approve')}>Timesheet freigeben</IonButton>}
                {selectedSheet.status === 'approved' && <IonButton fill="outline" onClick={() => void timesheetAction('unapprove')}>Freigabe zurücknehmen</IonButton>}
              </>}
            </section>

            {openExceptions.length > 0 && <section className="exception-box"><div className="payroll-section-head"><div><small>AUSNAHMEN</small><h3>Vor Abschluss prüfen</h3></div><IonBadge color="danger">{openExceptions.length}</IonBadge></div>{openExceptions.map((item: any) => <article key={item.id} className={item.severity}><IonIcon icon={warningOutline}/><div><b>{exceptionLabels[item.exception_type] || item.exception_type}</b><span>{item.shift_title || item.details?.reason || 'Prüfung erforderlich'}</span></div>{!['closed','locked'].includes(selectedPeriod.status) && <div><IonButton size="small" fill="outline" onClick={() => void exceptionAction(item.id, 'resolve')}>Erledigt</IonButton><IonButton size="small" fill="clear" color="medium" onClick={() => void exceptionAction(item.id, 'dismiss')}>Verwerfen</IonButton></div>}</article>)}</section>}

            <section className="entry-table"><div className="payroll-section-head"><div><small>ZEITEINTRÄGE</small><h3>Entry Review</h3></div></div>{selectedSheet.entries?.map((entry: any) => <article key={entry.id}>
              <div className="entry-time"><b>{dateTime(entry.clock_in)} – {dateTime(entry.clock_out)}</b><span>{entry.shift_title}{entry.location_name ? ` · ${entry.location_name}` : ''}</span></div>
              <div><small>Netto</small><b>{hours(entry.net_minutes)} Std.</b></div>
              <div><small>Pause</small><b>{entry.unpaid_break_minutes} Min.</b></div>
              <div><small>Betrag</small><b>{money(entry.amount_estimate, selectedPeriod.currency)}</b></div>
              <div className="entry-review"><IonBadge color={entry.review_status === 'approved' ? 'success' : entry.review_status === 'rejected' ? 'danger' : 'warning'}>{entry.review_status}</IonBadge>{!entry.locked && !['closed','locked'].includes(selectedPeriod.status) && <><IonButton size="small" fill="clear" color="success" aria-label="Zeiteintrag freigeben" onClick={() => void reviewEntry(entry.id, 'approved')}><IonIcon icon={checkmarkCircleOutline}/></IonButton><IonButton size="small" fill="clear" color="danger" aria-label="Zeiteintrag ablehnen" onClick={() => void reviewEntry(entry.id, 'rejected')}><IonIcon icon={closeCircleOutline}/></IonButton></>}</div>
            </article>)}{!selectedSheet.entries?.length && <div className="payroll-empty compact">Keine Zeiteinträge in diesem Zeitraum.</div>}</section>
          </>}
        </main>
      </div>
    </>}

    <IonModal isOpen={!!periodForm} onDidDismiss={() => setPeriodForm(undefined)}><div className="payroll-modal"><small>PAY PERIOD</small><h2>Abrechnungszeitraum anlegen</h2><IonInput fill="outline" label="Name" labelPlacement="floating" value={periodForm?.name || ''} onIonInput={(e) => setPeriodForm({ ...periodForm, name: eventValue(e) })}/><IonInput fill="outline" type="date" label="Von" labelPlacement="floating" value={periodForm?.starts_on || ''} onIonInput={(e) => setPeriodForm({ ...periodForm, starts_on: eventValue(e) })}/><IonInput fill="outline" type="date" label="Bis" labelPlacement="floating" value={periodForm?.ends_on || ''} onIonInput={(e) => setPeriodForm({ ...periodForm, ends_on: eventValue(e) })}/><IonTextarea fill="outline" label="Notiz" labelPlacement="floating" value={periodForm?.notes || ''} onIonInput={(e) => setPeriodForm({ ...periodForm, notes: eventValue(e) })}/><div><IonButton fill="outline" onClick={() => setPeriodForm(undefined)}>Abbrechen</IonButton><IonButton disabled={busy} onClick={() => void createPeriod()}>{busy ? <IonSpinner/> : 'Anlegen'}</IonButton></div></div></IonModal>
    <IonToast isOpen={!!toast} message={toast} duration={4500} onDidDismiss={() => setToast('')}/>
  </div>;
}

function WorkerPayroll({ timesheets, selected, setSelected, busy, submit }: { timesheets: any[]; selected: any; setSelected: (id: string) => void; busy: boolean; submit: () => void }) {
  return <div className="payroll-center worker-payroll"><section className="payroll-hero"><div><small>MEINE TIMESHEETS</small><h1>Arbeitszeiten für die Abrechnung</h1><p>Prüfe deine zusammengefassten Zeiten, Pausen und offene Hinweise bevor du dein Timesheet einreichst.</p></div></section>
    {!timesheets.length ? <div className="payroll-empty">Noch kein Timesheet für dich vorhanden.</div> : <div className="worker-payroll-layout"><aside className="timesheet-list">{timesheets.map((sheet) => <button key={sheet.id} className={selected?.id === sheet.id ? 'active' : ''} onClick={() => setSelected(sheet.id)}><span><b>{sheet.period_name}</b><small>{hours(sheet.net_minutes)} Std. · {sheet.entry_count} Einträge</small></span><IonBadge color={sheet.status === 'approved' || sheet.status === 'locked' ? 'success' : 'medium'}>{sheetLabels[sheet.status] || sheet.status}</IonBadge></button>)}</aside>{selected && <main className="timesheet-detail"><header className="timesheet-head"><div><small>ABRECHNUNGSZEITRAUM</small><h2>{selected.period_name}</h2><p>{hours(selected.net_minutes)} Netto-Stunden · {selected.unpaid_break_minutes} Min. unbezahlte Pause</p></div><IonBadge>{sheetLabels[selected.status] || selected.status}</IonBadge></header>{selected.status === 'open' || selected.status === 'reopened' ? <IonButton disabled={busy || selected.blocking_exception_count > 0} onClick={submit}>Timesheet einreichen</IonButton> : null}{selected.blocking_exception_count > 0 && <div className="worker-payroll-warning"><IonIcon icon={warningOutline}/>Es gibt noch {selected.blocking_exception_count} blockierende Punkte. Bitte Administration kontaktieren.</div>}<section className="entry-table">{selected.entries?.map((entry: any) => <article key={entry.id}><div className="entry-time"><b>{dateTime(entry.clock_in)} – {dateTime(entry.clock_out)}</b><span>{entry.shift_title}</span></div><div><small>Netto</small><b>{hours(entry.net_minutes)} Std.</b></div><div><small>Pause</small><b>{entry.unpaid_break_minutes} Min.</b></div><div><IonBadge color={entry.review_status === 'approved' ? 'success' : 'warning'}>{entry.review_status}</IonBadge></div></article>)}</section></main>}</div>}
  </div>;
}

function Stat({ label, value, danger = false }: { label: string; value: any; danger?: boolean }) {
  return <div className={`payroll-stat ${danger ? 'danger' : ''}`}><small>{label}</small><strong>{value}</strong></div>;
}
