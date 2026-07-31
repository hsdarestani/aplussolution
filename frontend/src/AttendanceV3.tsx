import React, { useEffect, useMemo, useState } from 'react';
import {
  IonBadge,
  IonButton,
  IonInput,
  IonModal,
  IonSpinner,
  IonTextarea,
  IonToast,
} from '@ionic/react';
import { api, User } from './api';
import './attendance-v3.css';

const isManager = (user: User) => user.role === 'admin' || user.role === 'manager';
const unpack = (data: any) => (Array.isArray(data) ? data : data?.results || []);

function dateTime(value?: string) {
  if (!value) return '–';
  return new Date(value).toLocaleString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function dateOnly(value?: string) {
  if (!value) return '–';
  return new Date(value).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function toInput(value?: string) {
  if (!value) return '';
  const date = new Date(value);
  const offset = date.getTimezoneOffset();
  return new Date(date.getTime() - offset * 60000).toISOString().slice(0, 16);
}

function durationLabel(start?: string, end?: string, now = Date.now()) {
  if (!start) return '0:00';
  const from = new Date(start).getTime();
  const to = end ? new Date(end).getTime() : now;
  const minutes = Math.max(0, Math.floor((to - from) / 60000));
  return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}`;
}

async function currentPosition() {
  try {
    return await new Promise<GeolocationPosition>((resolve, reject) =>
      navigator.geolocation.getCurrentPosition(resolve, reject, { enableHighAccuracy: true, timeout: 12000 }),
    );
  } catch {
    return undefined;
  }
}

export default function AttendanceV3({ user }: { user: User }) {
  const [data, setData] = useState<any>();
  const [absences, setAbsences] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState('');
  const [now, setNow] = useState(Date.now());
  const [correction, setCorrection] = useState<any>();
  const [absence, setAbsence] = useState<any>();

  const load = async () => {
    const [main, timeOff] = await Promise.all([
      api(isManager(user) ? 'attendance/exceptions/' : 'attendance/home/'),
      api('time-off/'),
    ]);
    setData(main);
    setAbsences(unpack(timeOff));
  };

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  async function clock(kind: 'in' | 'out') {
    setBusy(true);
    try {
      const position = await currentPosition();
      const payload: any = {
        lat: position?.coords.latitude,
        lng: position?.coords.longitude,
      };
      if (kind === 'in' && data?.eligible_shift?.id) payload.shift = data.eligible_shift.id;
      await api(`time-entries/clock_${kind}/`, { method: 'POST', body: JSON.stringify(payload) });
      setToast(kind === 'in' ? 'Arbeitszeit läuft.' : 'Arbeitszeit wurde beendet.');
      await load();
    } catch (error: any) {
      setToast(error.message);
    } finally {
      setBusy(false);
    }
  }

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

  async function approveEntry(id: string) {
    try {
      await api(`time-entries/${id}/approve/`, { method: 'POST', body: '{}' });
      setToast('Zeiteintrag wurde freigegeben.');
      await load();
    } catch (error: any) {
      setToast(error.message);
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

  async function closeLongRunning(id: string) {
    const reason = window.prompt('Warum wird dieser laufende Zeiteintrag beendet?');
    if (!reason) return;
    try {
      await api(`attendance/entries/${id}/close/`, {
        method: 'POST',
        body: JSON.stringify({ reason }),
      });
      setToast('Laufender Zeiteintrag wurde beendet und zur Prüfung markiert.');
      await load();
    } catch (error: any) {
      setToast(error.message);
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

  if (isManager(user)) {
    return (
      <>
        <section className="attendance-head">
          <div>
            <small>ARBEITSZEIT · EXCEPTIONS</small>
            <h1>Nur das, was Aufmerksamkeit braucht.</h1>
            <p>Normale Zeiterfassungen laufen im Hintergrund. Hier landen nur Abweichungen und offene Entscheidungen.</p>
          </div>
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
              <div className="attendance-change"><span>{dateTime(entry.clock_in)} – {dateTime(entry.clock_out)}</span><b>{durationLabel(entry.clock_in, entry.clock_out)} Std.</b></div>
              <IonButton size="small" onClick={() => approveEntry(entry.id)}>Freigeben</IonButton>
            </div>
          )) : <Empty text="Keine abgeschlossenen Zeiten warten auf Freigabe." />}
        </section>

        <section className="attendance-panel danger-panel">
          <div className="attendance-section-head"><div><small>PRIORITÄT 3</small><h2>Ungewöhnlich lange laufende Timer</h2></div></div>
          {data.long_running_entries?.length ? data.long_running_entries.map((entry: any) => (
            <div className="attendance-row" key={entry.id}>
              <div className="attendance-person"><b>{entry.worker_name}</b><small>Start {dateTime(entry.clock_in)}</small></div>
              <div className="running-time">{durationLabel(entry.clock_in, undefined, now)} Std.</div>
              <IonButton size="small" color="danger" onClick={() => closeLongRunning(entry.id)}>Timer beenden</IonButton>
            </div>
          )) : <Empty text="Keine auffällig langen Timer." />}
        </section>

        <AbsencePanel rows={absences} manager onDecision={decideAbsence} />
        <IonToast isOpen={!!toast} message={toast} duration={3500} onDidDismiss={() => setToast('')} />
      </>
    );
  }

  const active = data.active_entry;
  return (
    <>
      <section className="attendance-head worker-attendance-head">
        <div>
          <small>MEINE ARBEITSZEIT</small>
          <h1>{active ? 'Du bist eingestempelt.' : 'Bereit für deinen Einsatz?'}</h1>
          <p>{active ? 'Der Timer läuft nur für dich sichtbar. Beim Ausstempeln wird der Eintrag zur Prüfung gespeichert.' : data.eligible_shift ? `${data.eligible_shift.position_name || 'Einsatz'} · ${data.eligible_shift.location_name}` : 'Aktuell ist keine passende bestätigte Schicht im Zeitfenster.'}</p>
        </div>
        {active ? (
          <div className="live-clock"><small>SEIT {dateTime(active.clock_in)}</small><strong>{durationLabel(active.clock_in, undefined, now)}</strong><span>Std.</span></div>
        ) : null}
      </section>

      <div className="attendance-stats worker-stats">
        <Stat label="Dieser Monat" value={`${Math.floor((data.month_worked_minutes || 0) / 60)}:${String((data.month_worked_minutes || 0) % 60).padStart(2, '0')}`} suffix="Std." />
        <Stat label="Offene Korrekturen" value={data.pending_corrections || 0} />
        <Stat label="Letzte Einträge" value={data.history?.length || 0} />
      </div>

      <section className="clock-card">
        <div>
          <small>{active ? 'AKTIVE ZEITERFASSUNG' : 'NÄCHSTE MÖGLICHE SCHICHT'}</small>
          <h2>{active ? active.shift_title || 'Arbeitszeit läuft' : data.eligible_shift?.position_name || 'Keine Schicht verfügbar'}</h2>
          <p>{active ? `Beginn ${dateTime(active.clock_in)}` : data.eligible_shift ? `${dateTime(data.eligible_shift.starts_at)} · ${data.eligible_shift.location_name}` : 'Clock-in wird erst freigeschaltet, wenn eine deiner bestätigten Schichten im zulässigen Zeitfenster liegt.'}</p>
        </div>
        {active ? (
          <IonButton color="danger" disabled={busy} onClick={() => clock('out')}>Ausstempeln</IonButton>
        ) : (
          <IonButton disabled={busy || !data.eligible_shift} onClick={() => clock('in')}>Einstempeln</IonButton>
        )}
      </section>

      <section className="attendance-panel">
        <div className="attendance-section-head"><div><small>VERLAUF</small><h2>Meine letzten Arbeitszeiten</h2></div></div>
        {data.history?.length ? data.history.map((entry: any) => (
          <div className="attendance-row" key={entry.id}>
            <div className="attendance-person"><b>{dateOnly(entry.clock_in)}</b><small>{entry.shift_title || 'Arbeitszeit'}</small></div>
            <div className="attendance-change"><span>{dateTime(entry.clock_in)} – {dateTime(entry.clock_out)}</span><b>{durationLabel(entry.clock_in, entry.clock_out)} Std.</b></div>
            {pendingByEntry.has(entry.id) ? <IonBadge color="warning">Korrektur offen</IonBadge> : (
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

      <IonToast isOpen={!!toast} message={toast} duration={3500} onDidDismiss={() => setToast('')} />
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
