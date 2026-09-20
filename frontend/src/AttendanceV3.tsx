import React, { useEffect, useMemo, useState } from 'react';
import {
  IonAlert,
  IonBadge,
  IonButton,
  IonInput,
  IonModal,
  IonSpinner,
  IonTextarea,
  IonToast,
} from '@ionic/react';
import { api, apiBlob, User } from './api';
import { saveSchedulePdf } from './saveSchedulePdf';
import Phase8MobileAttendance from './Phase8MobileAttendance';
import './attendance-v3.css';

const isManager = (user: User) => user.role === 'admin' || user.role === 'manager';
const unpack = (data: any) => (Array.isArray(data) ? data : data?.results || []);
const BUSINESS_TIME_ZONE = 'Europe/Berlin';

function dateTime(value?: string) {
  if (!value) return '–';
  return new Date(value).toLocaleString('de-DE', {
    timeZone: BUSINESS_TIME_ZONE,
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function dateOnly(value?: string) {
  if (!value) return '–';
  return new Date(value).toLocaleDateString('de-DE', {
    timeZone: BUSINESS_TIME_ZONE,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

function toInput(value?: string) {
  if (!value) return '';
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: BUSINESS_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(new Date(value));
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)?.value || '';
  return `${part('year')}-${part('month')}-${part('day')}T${part('hour')}:${part('minute')}`;
}

function durationLabel(start?: string, end?: string, now = Date.now()) {
  if (!start) return '0:00';
  const from = new Date(start).getTime();
  const to = end ? new Date(end).getTime() : now;
  const minutes = Math.max(0, Math.floor((to - from) / 60000));
  return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}`;
}

function berlinDateKey(value = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: BUSINESS_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(value);
  const part = (type: string) => parts.find((item) => item.type === type)?.value || '';
  return `${part('year')}-${part('month')}-${part('day')}`;
}

function minuteDurationLabel(value?: number) {
  const minutes = Math.max(0, Number(value || 0));
  return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}`;
}

export default function AttendanceV3({ user }: { user: User }) {
  const [data, setData] = useState<any>();
  const [absences, setAbsences] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState('');
  const [now, setNow] = useState(Date.now());
  const [correction, setCorrection] = useState<any>();
  const [absence, setAbsence] = useState<any>();
  const [closeTarget, setCloseTarget] = useState<any>();
  const [approval, setApproval] = useState<any>();
  const [reportOpen, setReportOpen] = useState(false);
  const [reportWorkers, setReportWorkers] = useState<any[]>([]);
  const [reportBusy, setReportBusy] = useState(false);
  const [reportError, setReportError] = useState('');
  const [report, setReport] = useState<any>(() => {
    const today = berlinDateKey();
    return { date_from: today.slice(0, 8) + '01', date_to: today, workers: [], groups: [] };
  });

  const load = async () => {
    const mobile = typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches;
    const requests: Promise<any>[] = [
      api(isManager(user) ? 'attendance/exceptions/' : 'attendance/home/'),
      api('time-off/'),
    ];
    if (mobile && (isManager(user) || user.role === 'worker')) requests.push(api('attendance/history/'));
    const [main, timeOff, archive] = await Promise.all(requests);
    if (archive) {
      const archiveHistory = Array.isArray(archive?.history) ? archive.history : [];
      const mainHistory = Array.isArray(main?.history) ? main.history : [];
      const merged = new Map<string, any>();
      // Archive first, then the live attendance/home response so a freshly
      // clocked-out native row wins over any stale copy from the archive call.
      [...archiveHistory, ...mainHistory].forEach((entry: any) => {
        if (entry?.id) merged.set(String(entry.id), entry);
      });
      const history = Array.from(merged.values()).sort((a: any, b: any) =>
        new Date(b.clock_in).getTime() - new Date(a.clock_in).getTime(),
      );
      setData({ ...main, history, history_count: archive.count ?? history.length });
    } else {
      setData(main);
    }
    setAbsences(unpack(timeOff));
  };

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  async function submitCorrection() {
    if (!correction?.entry?.id) return;
    setBusy(true);
    try {
      await api(`attendance/entries/${correction.entry.id}/correction/`, {
        method: 'POST',
        body: JSON.stringify({
          clock_in: correction.clock_in,
          clock_out: correction.clock_out,
          reason: correction.reason,
        }),
      });
      setCorrection(undefined);
      setToast('Korrekturanfrage wurde gesendet.');
      await load();
    } catch (error: any) {
      setToast(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function requestAbsence() {
    setBusy(true);
    try {
      await api('time-off/', { method: 'POST', body: JSON.stringify(absence) });
      setAbsence(undefined);
      setToast('Abwesenheitsantrag wurde gesendet.');
      await load();
    } catch (error: any) {
      setToast(error.message);
    } finally {
      setBusy(false);
    }
  }

  function openApproval(entry: any) {
    setApproval({
      entry,
      clock_in: toInput(entry.clock_in),
      clock_out: toInput(entry.clock_out),
      break_minutes: Number(entry.effective_break_minutes ?? entry.break_minutes ?? 0),
      reason: '',
    });
  }

  async function approveEntry() {
    if (!approval?.entry?.id) return;
    setBusy(true);
    try {
      await api(`time-entries/${approval.entry.id}/approve/`, {
        method: 'POST',
        body: JSON.stringify({
          clock_in: approval.clock_in,
          clock_out: approval.clock_out,
          break_minutes: Number(approval.break_minutes || 0),
          reason: String(approval.reason || '').trim(),
        }),
      });
      setApproval(undefined);
      setToast('Zeiteintrag wurde geprüft und freigegeben.');
      await load();
    } catch (error: any) {
      setToast(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function openAttendanceReport() {
    setReportError('');
    setReportOpen(true);
    if (reportWorkers.length) return;
    try {
      const payload = await api('workers/?ordering=user__last_name');
      setReportWorkers(unpack(payload).filter((worker: any) => worker.active !== false && !String(worker?.user_detail?.email || '').endsWith('@sync.invalid')));
    } catch (error: any) {
      setReportError(error?.message || 'Mitarbeiter konnten nicht geladen werden.');
    }
  }

  async function downloadAttendanceReport() {
    if (reportBusy) return;
    if (!report.date_from || !report.date_to || report.date_from > report.date_to) {
      setReportError('Bitte einen gültigen Zeitraum auswählen.');
      return;
    }
    setReportBusy(true);
    setReportError('');
    try {
      const params = new URLSearchParams({ date_from: report.date_from, date_to: report.date_to });
      if (report.workers?.length) params.set('workers', report.workers.join(','));
      if (report.groups?.length) params.set('groups', report.groups.join(','));
      const result = await apiBlob(`reports/attendance.pdf?${params.toString()}`);
      await saveSchedulePdf(result.blob, result.filename, 'Arbeitszeitbericht');
      setReportOpen(false);
      setToast('Arbeitszeit-PDF wurde erstellt.');
    } catch (error: any) {
      setReportError(error?.message || 'Arbeitszeit-PDF konnte nicht erstellt werden.');
    } finally {
      setReportBusy(false);
    }
  }

  async function decideCorrection(id: string, status: 'approved' | 'rejected') {
    try {
      await api(`attendance/corrections/${id}/decide/`, {
        method: 'POST',
        body: JSON.stringify({ status }),
      });
      setToast(status === 'approved' ? 'Korrektur wurde genehmigt.' : 'Korrektur wurde abgelehnt.');
      await load();
    } catch (error: any) {
      setToast(error.message);
    }
  }

  async function closeLongRunning(id: string, reason: string) {
    setBusy(true);
    try {
      await api(`attendance/entries/${id}/close/`, {
        method: 'POST',
        body: JSON.stringify({ reason }),
      });
      setCloseTarget(undefined);
      setToast('Laufender Zeiteintrag wurde beendet und zur Prüfung markiert.');
      await load();
    } catch (error: any) {
      setToast(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function decideAbsence(id: string, status: 'approved' | 'rejected') {
    try {
      await api(`time-off/${id}/decide/`, { method: 'POST', body: JSON.stringify({ status }) });
      setToast(status === 'approved' ? 'Abwesenheit genehmigt.' : 'Abwesenheit abgelehnt.');
      await load();
    } catch (error: any) {
      setToast(error.message);
    }
  }

  const pendingByEntry = useMemo(() => {
    const map = new Map<string, any>();
    (data?.corrections || []).filter((item: any) => item.status === 'pending').forEach((item: any) => map.set(item.entry_id, item));
    return map;
  }, [data]);

  if (!data) return <div className="attendance-loading"><IonSpinner /></div>;

  if ((user.role === 'worker' || isManager(user)) && typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches) {
    return <Phase8MobileAttendance data={data} showWorker={isManager(user)} />;
  }

  if (isManager(user)) {
    return (
      <>
        <section className="attendance-head">
          <div>
            <small>ARBEITSZEIT · EXCEPTIONS</small>
            <h1>Nur das, was Aufmerksamkeit braucht.</h1>
            <p>Normale Zeiterfassungen laufen im Hintergrund. Hier landen nur Abweichungen und offene Entscheidungen.</p>
          </div>
          <IonButton fill="outline" onClick={() => void openAttendanceReport()}>PDF Arbeitszeitbericht</IonButton>
        </section>

        <div className="attendance-stats">
          <Stat label="Korrekturen" value={data.counts?.pending_corrections || 0} />
          <Stat label="Nicht freigegeben" value={data.counts?.unapproved_entries || 0} />
          <Stat label="> 12 Std. aktiv" value={data.counts?.long_running_entries || 0} danger />
          <Stat label="Gesamt offen" value={data.counts?.total || 0} strong />
        </div>

        <section className="attendance-panel">
          <div className="attendance-section-head"><div><small>PRIORITÄT 1</small><h2>Korrekturanfragen</h2></div></div>
          {data.pending_corrections?.length ? data.pending_corrections.map((item: any) => (
            <div className="attendance-row attention" key={item.id}>
              <div className="attendance-person"><b>{item.worker_name}</b><small>{dateOnly(item.created_at)}</small></div>
              <div className="attendance-change">
                <span>{dateTime(item.original_clock_in)} → <b>{dateTime(item.requested_clock_in || item.original_clock_in)}</b></span>
                <span>{dateTime(item.original_clock_out)} → <b>{dateTime(item.requested_clock_out || item.original_clock_out)}</b></span>
                <small>{item.reason}</small>
              </div>
              <div className="attendance-actions">
                <IonButton size="small" onClick={() => decideCorrection(item.id, 'approved')}>Genehmigen</IonButton>
                <IonButton size="small" fill="outline" color="danger" onClick={() => decideCorrection(item.id, 'rejected')}>Ablehnen</IonButton>
              </div>
            </div>
          )) : <Empty text="Keine Korrekturanfragen offen." />}
        </section>

        <section className="attendance-panel">
          <div className="attendance-section-head"><div><small>PRIORITÄT 2</small><h2>Nicht freigegebene Zeiten</h2></div></div>
          {data.unapproved_entries?.length ? data.unapproved_entries.map((entry: any) => (
            <div className="attendance-row" key={entry.id}>
              <div className="attendance-person"><b>{entry.worker_name}</b><small>{entry.shift_title || 'Arbeitszeit'}</small></div>
              <div className="attendance-change">
                <span>{dateTime(entry.clock_in)} – {dateTime(entry.clock_out)}</span>
                <b>{minuteDurationLabel(entry.worked_minutes)} Std. netto</b>
                <small>Pause: {entry.effective_break_minutes ?? entry.break_minutes ?? 0} Min.</small>
              </div>
              <IonButton size="small" onClick={() => openApproval(entry)}>Prüfen & freigeben</IonButton>
            </div>
          )) : <Empty text="Keine abgeschlossenen Zeiten warten auf Freigabe." />}
        </section>

        <section className="attendance-panel danger-panel">
          <div className="attendance-section-head"><div><small>PRIORITÄT 3</small><h2>Ungewöhnlich lange laufende Timer</h2></div></div>
          {data.long_running_entries?.length ? data.long_running_entries.map((entry: any) => (
            <div className="attendance-row" key={entry.id}>
              <div className="attendance-person"><b>{entry.worker_name}</b><small>Start {dateTime(entry.clock_in)}</small></div>
              <div className="running-time">{durationLabel(entry.clock_in, undefined, now)} Std.</div>
              <IonButton size="small" color="danger" disabled={busy} onClick={() => setCloseTarget(entry)}>Timer beenden</IonButton>
            </div>
          )) : <Empty text="Keine auffällig langen Timer." />}
        </section>

        <AbsencePanel rows={absences} manager onDecision={decideAbsence} />
        <IonModal isOpen={!!approval} onDidDismiss={() => setApproval(undefined)}>
          <div className="attendance-modal">
            <small>ARBEITSZEIT PRÜFEN</small>
            <h2>Zeiten bearbeiten & freigeben</h2>
            <p>Beginn, Ende und Pause können vor der Freigabe korrigiert werden. Änderungen werden im Prüfverlauf gespeichert.</p>
            <IonInput fill="outline" type="datetime-local" label="Beginn" labelPlacement="floating" value={approval?.clock_in} onIonInput={(event) => setApproval({ ...approval, clock_in: event.detail.value })} />
            <IonInput fill="outline" type="datetime-local" label="Ende" labelPlacement="floating" value={approval?.clock_out} onIonInput={(event) => setApproval({ ...approval, clock_out: event.detail.value })} />
            <div className="attendance-pause-editor">
              <div><small>PAUSE</small><b>{Number(approval?.break_minutes || 0)} Min.</b></div>
              <div>
                <button type="button" aria-label="Pause um 5 Minuten reduzieren" onClick={() => setApproval({ ...approval, break_minutes: Math.max(0, Number(approval?.break_minutes || 0) - 5) })}>−</button>
                <IonInput type="number" min="0" inputMode="numeric" value={approval?.break_minutes} onIonInput={(event) => setApproval({ ...approval, break_minutes: Math.max(0, Number(event.detail.value || 0)) })} />
                <button type="button" aria-label="Pause um 5 Minuten erhöhen" onClick={() => setApproval({ ...approval, break_minutes: Number(approval?.break_minutes || 0) + 5 })}>+</button>
              </div>
            </div>
            <IonTextarea fill="outline" label="Prüfhinweis (optional)" labelPlacement="floating" value={approval?.reason} onIonInput={(event) => setApproval({ ...approval, reason: event.detail.value })} />
            <div className="attendance-modal-actions"><IonButton fill="outline" onClick={() => setApproval(undefined)}>Abbrechen</IonButton><IonButton disabled={busy} onClick={() => void approveEntry()}>{busy ? 'Wird gespeichert …' : 'Ändern & freigeben'}</IonButton></div>
          </div>
        </IonModal>

        <IonModal isOpen={reportOpen} onDidDismiss={() => setReportOpen(false)}>
          <div className="attendance-modal attendance-report-modal">
            <small>PDF · ARBEITSZEIT</small>
            <h2>Arbeitszeitbericht erstellen</h2>
            <p>Filter wie im Dienstplan-PDF: Zeitraum und Mitarbeiter auswählen, Bereiche optional eingrenzen.</p>
            <div className="attendance-report-dates">
              <IonInput fill="outline" type="date" label="Von" labelPlacement="floating" value={report.date_from} onIonInput={(event) => setReport({ ...report, date_from: event.detail.value })} />
              <IonInput fill="outline" type="date" label="Bis" labelPlacement="floating" value={report.date_to} onIonInput={(event) => setReport({ ...report, date_to: event.detail.value })} />
            </div>
            <div className="attendance-report-filter-block">
              <b>Mitarbeiter</b>
              <div className="attendance-report-chip-grid">
                <button type="button" className={report.workers.length === 0 ? 'active' : ''} onClick={() => setReport({ ...report, workers: [] })}>Alle Mitarbeiter</button>
                {reportWorkers.map((worker: any) => {
                  const id = String(worker.id);
                  const selected = report.workers.includes(id);
                  return <button type="button" key={id} className={selected ? 'active' : ''} onClick={() => setReport((current: any) => ({ ...current, workers: selected ? current.workers.filter((item: string) => item !== id) : [...current.workers, id] }))}>{worker.user_detail?.name || worker.employee_number}</button>;
                })}
              </div>
              <small>Nichts ausgewählt = alle Mitarbeiter</small>
            </div>
            <div className="attendance-report-filter-block">
              <b>Bereiche</b>
              <div className="attendance-report-chip-grid compact">
                {[['service','Service'],['housekeeping','Housekeeping'],['front_office','Front Office']].map(([value,label]) => {
                  const selected = report.groups.includes(value);
                  return <button type="button" key={value} className={selected ? 'active' : ''} onClick={() => setReport((current: any) => ({ ...current, groups: selected ? current.groups.filter((item: string) => item !== value) : [...current.groups, value] }))}>{label}</button>;
                })}
              </div>
              <small>Nichts ausgewählt = alle Bereiche</small>
            </div>
            {reportError ? <div className="attendance-report-error">{reportError}</div> : null}
            <div className="attendance-modal-actions"><IonButton fill="outline" onClick={() => setReportOpen(false)}>Abbrechen</IonButton><IonButton disabled={reportBusy} onClick={() => void downloadAttendanceReport()}>{reportBusy ? 'PDF wird erstellt …' : 'PDF erstellen'}</IonButton></div>
          </div>
        </IonModal>

        <IonAlert
          isOpen={!!closeTarget}
          onDidDismiss={() => setCloseTarget(undefined)}
          header="Laufenden Timer beenden?"
          message={closeTarget ? `${closeTarget.worker_name || 'Dieser Mitarbeiter'} ist seit ${dateTime(closeTarget.clock_in)} eingestempelt. Der Grund wird im Prüfverlauf gespeichert.` : ''}
          inputs={[{ name: 'reason', type: 'textarea', placeholder: 'Grund für das Beenden' }]}
          buttons={[
            { text: 'Abbrechen', role: 'cancel' },
            {
              text: 'Timer beenden',
              role: 'destructive',
              handler: (values) => {
                const reason = String(values?.reason || '').trim();
                if (!reason) {
                  setToast('Bitte einen Grund für das Beenden angeben.');
                  return false;
                }
                if (closeTarget?.id) void closeLongRunning(closeTarget.id, reason);
                return true;
              },
            },
          ]}
        />
        <IonToast isOpen={!!toast} message={toast} duration={1000} onDidDismiss={() => setToast('')} />
      </>
    );
  }

  return (
    <>
      <section className="attendance-head worker-attendance-head">
        <div>
          <small>MEINE ARBEITSZEIT</small>
          <h1>Arbeitszeiten & Korrekturen</h1>
          <p>Die tatsächliche Arbeitszeit für deine zuletzt beendete Schicht trägst du direkt auf der Startseite ein.</p>
        </div>
      </section>

      <div className="attendance-stats worker-stats">
        <Stat label="Dieser Monat" value={`${Math.floor((data.month_worked_minutes || 0) / 60)}:${String((data.month_worked_minutes || 0) % 60).padStart(2, '0')}`} suffix="Std." />
        <Stat label="Offene Korrekturen" value={data.pending_corrections || 0} />
        <Stat label="Letzte Einträge" value={data.history?.length || 0} />
      </div>

      <section className="clock-card">
        <div>
          <small>MANUELLE ZEITERFASSUNG</small>
          <h2>Arbeitszeit nach der Schicht eintragen</h2>
          <p>Die Standort-Zeiterfassung wird Mitarbeitern aktuell nicht angezeigt. Die Eingabe erfolgt über die letzte beendete Schicht auf der Startseite.</p>
        </div>
      </section>

      <section className="attendance-panel">
        <div className="attendance-section-head"><div><small>VERLAUF</small><h2>Meine letzten Arbeitszeiten</h2></div></div>
        {data.history?.length ? data.history.map((entry: any) => (
          <div className="attendance-row" key={entry.id}>
            <div className="attendance-person"><b>{dateOnly(entry.clock_in)}</b><small>{entry.shift_title || 'Arbeitszeit'}</small></div>
            <div className="attendance-change"><span>{dateTime(entry.clock_in)} – {dateTime(entry.clock_out)}</span><b>{durationLabel(entry.clock_in, entry.clock_out)} Std.</b></div>
            {entry.wiw_time_id ? <IonBadge color="medium">WIW-Historie · schreibgeschützt</IonBadge> : pendingByEntry.has(entry.id) ? <IonBadge color="warning">Korrektur offen</IonBadge> : (
              <IonButton size="small" fill="outline" onClick={() => setCorrection({ entry, clock_in: toInput(entry.clock_in), clock_out: toInput(entry.clock_out), reason: '' })}>Korrektur</IonButton>
            )}
          </div>
        )) : <Empty text="Noch keine abgeschlossenen Arbeitszeiten." />}
      </section>

      <section className="attendance-panel">
        <div className="attendance-section-head"><div><small>KORREKTUREN</small><h2>Status meiner Anfragen</h2></div></div>
        {data.corrections?.length ? data.corrections.map((item: any) => (
          <div className="attendance-row" key={item.id}>
            <div className="attendance-person"><b>{dateOnly(item.created_at)}</b><small>{item.reason}</small></div>
            <IonBadge color={item.status === 'approved' ? 'success' : item.status === 'rejected' ? 'danger' : 'warning'}>{item.status === 'approved' ? 'Genehmigt' : item.status === 'rejected' ? 'Abgelehnt' : item.status === 'cancelled' ? 'Zurückgezogen' : 'Offen'}</IonBadge>
          </div>
        )) : <Empty text="Keine Korrekturanfragen." />}
      </section>

      <AbsencePanel rows={absences} onNew={() => setAbsence({})} />

      <IonModal isOpen={!!correction} onDidDismiss={() => setCorrection(undefined)}>
        <div className="attendance-modal">
          <small>ARBEITSZEIT KORRIGIEREN</small>
          <h2>Korrektur anfragen</h2>
          <p>Die Originalzeit bleibt unverändert, bis die Administration deine Anfrage genehmigt.</p>
          <IonInput fill="outline" type="datetime-local" label="Gewünschter Beginn" labelPlacement="floating" value={correction?.clock_in} onIonInput={(e) => setCorrection({ ...correction, clock_in: e.detail.value })} />
          <IonInput fill="outline" type="datetime-local" label="Gewünschtes Ende" labelPlacement="floating" value={correction?.clock_out} onIonInput={(e) => setCorrection({ ...correction, clock_out: e.detail.value })} />
          <IonTextarea fill="outline" label="Warum soll der Eintrag geändert werden?" labelPlacement="floating" value={correction?.reason} onIonInput={(e) => setCorrection({ ...correction, reason: e.detail.value })} />
          <div className="attendance-modal-actions"><IonButton fill="outline" onClick={() => setCorrection(undefined)}>Abbrechen</IonButton><IonButton disabled={busy} onClick={submitCorrection}>Anfrage senden</IonButton></div>
        </div>
      </IonModal>

      <IonModal isOpen={absence !== undefined} onDidDismiss={() => setAbsence(undefined)}>
        <div className="attendance-modal">
          <small>ABWESENHEIT</small><h2>Antrag senden</h2>
          <IonInput fill="outline" type="date" label="Von" labelPlacement="floating" value={absence?.starts_on} onIonInput={(e) => setAbsence({ ...absence, starts_on: e.detail.value })} />
          <IonInput fill="outline" type="date" label="Bis" labelPlacement="floating" value={absence?.ends_on} onIonInput={(e) => setAbsence({ ...absence, ends_on: e.detail.value })} />
          <IonTextarea fill="outline" label="Grund / Hinweis" labelPlacement="floating" value={absence?.reason} onIonInput={(e) => setAbsence({ ...absence, reason: e.detail.value })} />
          <div className="attendance-modal-actions"><IonButton fill="outline" onClick={() => setAbsence(undefined)}>Abbrechen</IonButton><IonButton disabled={busy} onClick={requestAbsence}>Antrag senden</IonButton></div>
        </div>
      </IonModal>

      <IonToast isOpen={!!toast} message={toast} duration={1000} onDidDismiss={() => setToast('')} />
    </>
  );
}

function Stat({ label, value, suffix, danger, strong }: { label: string; value: any; suffix?: string; danger?: boolean; strong?: boolean }) {
  return <div className={`attendance-stat ${danger ? 'danger' : ''} ${strong ? 'strong' : ''}`}><small>{label}</small><b>{value}</b>{suffix && <span>{suffix}</span>}</div>;
}

function Empty({ text }: { text: string }) {
  return <div className="attendance-empty">{text}</div>;
}

function AbsencePanel({ rows, manager, onDecision, onNew }: { rows: any[]; manager?: boolean; onDecision?: (id: string, status: 'approved' | 'rejected') => void; onNew?: () => void }) {
  return (
    <section className="attendance-panel">
      <div className="attendance-section-head"><div><small>ABWESENHEITEN</small><h2>{manager ? 'Offene und aktuelle Anträge' : 'Meine Abwesenheiten'}</h2></div>{onNew && <IonButton size="small" fill="outline" onClick={onNew}>Neue Abwesenheit</IonButton>}</div>
      {rows.length ? rows.map((item: any) => (
        <div className="attendance-row" key={item.id}>
          <div className="attendance-person"><b>{item.worker_name || 'Mein Antrag'}</b><small>{dateOnly(item.starts_on)} – {dateOnly(item.ends_on)}</small></div>
          <div className="attendance-change"><span>{item.reason || 'Ohne Hinweis'}</span></div>
          <IonBadge color={item.status === 'approved' ? 'success' : item.status === 'rejected' ? 'danger' : 'warning'}>{item.status === 'approved' ? 'Genehmigt' : item.status === 'rejected' ? 'Abgelehnt' : 'Offen'}</IonBadge>
          {manager && item.status === 'pending' && onDecision && <div className="attendance-actions"><IonButton size="small" onClick={() => onDecision(item.id, 'approved')}>Genehmigen</IonButton><IonButton size="small" fill="outline" color="danger" onClick={() => onDecision(item.id, 'rejected')}>Ablehnen</IonButton></div>}
        </div>
      )) : <Empty text="Keine Abwesenheitsanträge." />}
    </section>
  );
}
