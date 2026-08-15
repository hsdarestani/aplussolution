import React, { useEffect, useState } from 'react';
import {
  IonAlert,
  IonBadge,
  IonButton,
  IonCheckbox,
  IonIcon,
  IonInput,
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
  cameraOutline,
  checkmarkCircleOutline,
  pauseCircleOutline,
  playCircleOutline,
  refreshOutline,
  settingsOutline,
  tabletPortraitOutline,
  timeOutline,
} from 'ionicons/icons';
import { api, apiAll, User } from './api';
import './attendance-v4.css';

const isManager = (user: User) => ['admin', 'manager'].includes(user.role);
const val = (event: any) => event.detail.value ?? '';
const unpack = (data: any) => (Array.isArray(data) ? data : data?.results || []);

function dateTime(value?: string) {
  if (!value) return '–';
  return new Date(value).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}
function dateOnly(value?: string) {
  if (!value) return '–';
  return new Date(value).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
}
function minutesLabel(minutes = 0) {
  return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}`;
}
function runningMinutes(start?: string, now = Date.now()) {
  if (!start) return 0;
  return Math.max(0, Math.floor((now - new Date(start).getTime()) / 60000));
}
async function currentPosition() {
  try {
    return await new Promise<GeolocationPosition>((resolve, reject) => navigator.geolocation.getCurrentPosition(resolve, reject, { enableHighAccuracy: true, timeout: 12000 }));
  } catch {
    return undefined;
  }
}

const noticeLabels: Record<string, string> = {
  early_clock_in: 'Zu früh eingestempelt',
  late_clock_in: 'Zu spät eingestempelt',
  early_clock_out: 'Zu früh ausgestempelt',
  late_clock_out: 'Zu spät ausgestempelt',
  wrong_location: 'Falscher Standort',
  missed_clock_in: 'Einstempeln fehlt',
  missed_clock_out: 'Ausstempeln fehlt',
  no_show: 'Nicht erschienen',
  not_scheduled: 'Nicht eingeplant',
  photo_missing: 'Foto fehlt',
  break_missed: 'Pause fehlt',
  break_short: 'Pause zu kurz',
  attestation_missing: 'Bestätigung fehlt',
  terminal_denied: 'Terminal abgelehnt',
};

export default function AttendanceV4({ user }: { user: User }) {
  const manager = isManager(user);
  const [data, setData] = useState<any>();
  const [timeOff, setTimeOff] = useState<any[]>([]);
  const [locations, setLocations] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState('');
  const [now, setNow] = useState(Date.now());
  const [correction, setCorrection] = useState<any>();
  const [absence, setAbsence] = useState<any>();
  const [closeTarget, setCloseTarget] = useState<any>();
  const [attest, setAttest] = useState<any>();
  const [policy, setPolicy] = useState<any>();
  const [terminal, setTerminal] = useState<any>();
  const [terminalSecret, setTerminalSecret] = useState<any>();

  async function load() {
    try {
      const [main, absences, locationRows] = await Promise.all([
        api(manager ? 'attendance/exceptions/' : 'attendance/home/'),
        api('time-off/'),
        manager ? apiAll('locations/') : Promise.resolve([]),
      ]);
      setData(main);
      setTimeOff(unpack(absences));
      setLocations(locationRows);
      if (manager) {
        setPolicy((current: any) => current || main.policies?.[0] || null);
      }
    } catch (error: any) {
      setToast(error.message);
    }
  }

  useEffect(() => { void load(); }, []);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  async function mutate(path: string, body: any, success: string, method = 'POST') {
    setBusy(true);
    try {
      const result = await api(path, { method, body: JSON.stringify(body ?? {}) });
      setToast(success);
      await load();
      return result;
    } catch (error: any) {
      setToast(error.message);
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function clock(kind: 'in' | 'out') {
    setBusy(true);
    try {
      const position = await currentPosition();
      const body: any = { lat: position?.coords.latitude, lng: position?.coords.longitude };
      if (kind === 'in' && data?.eligible_shift?.id) body.shift = data.eligible_shift.id;
      const result: any = await api(`time-entries/clock_${kind}/`, { method: 'POST', body: JSON.stringify(body) });
      setToast(kind === 'in' ? 'Arbeitszeit läuft.' : 'Arbeitszeit wurde beendet.');
      if (kind === 'out' && (result.attestation_required?.break || result.attestation_required?.end_of_shift)) {
        setAttest({
          entry: result.id,
          break: result.attestation_required.break,
          end: result.attestation_required.end_of_shift,
          breaks_taken: true,
          shift_ok: true,
          note: '',
        });
      }
      await load();
    } catch (error: any) {
      setToast(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function toggleBreak() {
    const active = data?.active_entry;
    if (!active) return;
    const running = !!active.running_break;
    await mutate(`attendance/breaks/${running ? 'end' : 'start'}/`, {}, running ? 'Pause beendet.' : 'Pause gestartet.');
  }

  async function submitAttestation() {
    if (!attest?.entry) return;
    setBusy(true);
    try {
      if (attest.break) {
        await api(`attendance/entries/${attest.entry}/attestation/`, {
          method: 'POST',
          body: JSON.stringify({ kind: 'break', answers: { breaks_taken: !!attest.breaks_taken }, note: attest.breaks_taken ? '' : attest.note }),
        });
      }
      if (attest.end) {
        await api(`attendance/entries/${attest.entry}/attestation/`, {
          method: 'POST',
          body: JSON.stringify({ kind: 'end_of_shift', answers: { shift_completed_as_planned: !!attest.shift_ok }, note: attest.note }),
        });
      }
      setAttest(undefined);
      setToast('Bestätigung gespeichert.');
      await load();
    } catch (error: any) {
      setToast(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function submitCorrection() {
    if (!correction?.entry?.id) return;
    const result = await mutate(`attendance/entries/${correction.entry.id}/correction/`, {
      clock_in: correction.clock_in,
      clock_out: correction.clock_out,
      reason: correction.reason,
    }, 'Korrekturanfrage wurde gesendet.');
    if (result) setCorrection(undefined);
  }

  async function requestAbsence() {
    const result = await mutate('time-off/', absence, 'Abwesenheitsantrag wurde gesendet.');
    if (result) setAbsence(undefined);
  }
  async function decideAbsence(id: string, status: 'approved' | 'rejected') {
    await mutate(`time-off/${id}/decide/`, { status }, status === 'approved' ? 'Abwesenheit genehmigt.' : 'Abwesenheit abgelehnt.');
  }
  async function decideCorrection(id: string, status: 'approved' | 'rejected') {
    await mutate(`attendance/corrections/${id}/decide/`, { status }, status === 'approved' ? 'Korrektur genehmigt.' : 'Korrektur abgelehnt.');
  }
  async function approveEntry(id: string) {
    await mutate(`time-entries/${id}/approve/`, {}, 'Zeiteintrag freigegeben.');
  }
  async function confirmCloseRunning(reason: string) {
    if (!closeTarget?.id) return;
    const target = closeTarget;
    setCloseTarget(undefined);
    await mutate(`attendance/entries/${target.id}/close/`, { reason }, 'Timer beendet und zur Prüfung markiert.');
  }
  async function noticeAction(id: string, action: 'acknowledge' | 'resolve' | 'dismiss') {
    await mutate(`attendance-notices/${id}/${action}/`, {}, action === 'resolve' ? 'Attendance Notice erledigt.' : action === 'dismiss' ? 'Notice verworfen.' : 'Notice als gesehen markiert.');
  }
  async function scanNotices() {
    const result = await mutate('attendance/notices/scan/', {}, 'Attendance wurde neu geprüft.');
    if (result?.total) setToast(`${result.total} neue Attendance-Hinweise erkannt.`);
  }
  async function savePolicy() {
    if (!policy) return;
    const payload = { ...policy };
    delete payload.id;
    delete payload.created_at;
    delete payload.updated_at;
    delete payload.location_name;
    const result = await mutate(
      policy.id ? `attendance-policies/${policy.id}/` : 'attendance-policies/',
      payload,
      'Attendance Policy gespeichert.',
      policy.id ? 'PATCH' : 'POST',
    );
    if (result) setPolicy(result);
  }
  async function createTerminal() {
    if (!terminal?.name || !terminal?.location) {
      setToast('Name und Einsatzort auswählen.');
      return;
    }
    const result: any = await mutate('attendance-terminals/', terminal, 'Time Clock Terminal angelegt.');
    if (result?.terminal_token) setTerminalSecret({ ...result });
    if (result) setTerminal(undefined);
  }
  async function rotateTerminal(item: any) {
    const result: any = await mutate(`attendance-terminals/${item.id}/rotate-token/`, {}, 'Terminal Secret erneuert.');
    if (result?.terminal_token) setTerminalSecret({ ...item, ...result });
  }

  if (!data) return <div className="attendance-v4-loading"><IonSpinner /></div>;

  if (manager) {
    const notices = data.notices || [];
    const longRunning = data.long_running_entries || [];
    return <div className="attendance-v4">
      <section className="att-v4-hero manager">
        <div>
          <small>ATTENDANCE CONTROL CENTER</small>
          <h1>Arbeitszeit, Abweichungen & Terminals</h1>
          <p>Attendance Notices priorisieren, Pausenregeln steuern und Time Clock Terminals verwalten.</p>
        </div>
        <IonButton fill="outline" disabled={busy} onClick={() => void scanNotices()}><IonIcon slot="start" icon={refreshOutline}/>Jetzt prüfen</IonButton>
      </section>

      <div className="att-v4-stats">
        <Stat label="Attendance Notices" value={data.counts?.attendance_notices || 0} />
        <Stat label="Kritisch" value={data.counts?.critical_notices || 0} danger />
        <Stat label="Korrekturen" value={data.counts?.pending_corrections || 0} />
        <Stat label="Nicht freigegeben" value={data.counts?.unapproved_entries || 0} />
        <Stat label="> 12 Std. aktiv" value={data.counts?.long_running_entries || 0} danger />
      </div>

      <section className="att-v4-panel notice-center">
        <div className="att-v4-section-head"><div><small>ATTENDANCE NOTICES</small><h2>Abweichungen zuerst bearbeiten</h2></div><IonBadge color={notices.some((item: any) => item.severity === 'critical') ? 'danger' : 'medium'}>{notices.length} offen</IonBadge></div>
        {notices.length ? notices.map((item: any) => <article className={`att-notice ${item.severity}`} key={item.id}>
          <div className="att-notice-icon"><IonIcon icon={item.severity === 'critical' ? alertCircleOutline : timeOutline}/></div>
          <div className="att-notice-copy">
            <div><IonBadge color={item.severity === 'critical' ? 'danger' : item.severity === 'warning' ? 'warning' : 'medium'}>{item.severity}</IonBadge><span>{item.worker_name}</span></div>
            <h3>{noticeLabels[item.notice_type] || item.notice_type}</h3>
            <p>{item.shift_title || 'Arbeitszeit'}{item.location_name ? ` · ${item.location_name}` : ''}{item.value_minutes != null ? ` · ${item.value_minutes} Min.` : ''}</p>
            <small>{dateTime(item.detected_at)}</small>
          </div>
          <div className="att-notice-actions">
            {item.status === 'open' && <IonButton size="small" fill="outline" onClick={() => void noticeAction(item.id, 'acknowledge')}>Gesehen</IonButton>}
            <IonButton size="small" onClick={() => void noticeAction(item.id, 'resolve')}>Erledigt</IonButton>
            <IonButton size="small" fill="clear" color="medium" onClick={() => void noticeAction(item.id, 'dismiss')}>Verwerfen</IonButton>
          </div>
        </article>) : <Empty text="Keine offenen Attendance Notices." />}
      </section>

      <div className="att-v4-admin-grid">
        <section className="att-v4-panel">
          <div className="att-v4-section-head"><div><small>REGELN</small><h2>Attendance Policy</h2></div><IonIcon icon={settingsOutline}/></div>
          <IonSelect fill="outline" label="Policy" labelPlacement="floating" value={policy?.id || ''} onIonChange={(event) => {
            const found = data.policies?.find((item: any) => item.id === val(event));
            setPolicy(found || { name: 'Neue Policy', active: true, priority: 0, early_clock_in_mode: 'off', clock_in_location_mode: 'block', clock_out_location_mode: 'block' });
          }}>
            <IonSelectOption value="">Neue Policy</IonSelectOption>
            {data.policies?.map((item: any) => <IonSelectOption key={item.id} value={item.id}>{item.name}{item.location_name ? ` · ${item.location_name}` : ' · Global'}</IonSelectOption>)}
          </IonSelect>
          {policy && <div className="att-policy-form">
            <IonInput fill="outline" label="Name" labelPlacement="floating" value={policy.name} onIonInput={(event) => setPolicy({ ...policy, name: val(event) })}/>
            <IonSelect fill="outline" label="Einsatzort" labelPlacement="floating" value={policy.location || ''} onIonChange={(event) => setPolicy({ ...policy, location: val(event) || null })}>
              <IonSelectOption value="">Global</IonSelectOption>
              {locations.map((item: any) => <IonSelectOption key={item.id} value={item.id}>{item.name}</IonSelectOption>)}
            </IonSelect>
            <IonInput fill="outline" type="number" label="Früh einchecken (Min.)" labelPlacement="floating" value={policy.early_clock_in_minutes} onIonInput={(event) => setPolicy({ ...policy, early_clock_in_minutes: Number(val(event) || 0) })}/>
            <ModeSelect label="Zu frühes Einchecken" value={policy.early_clock_in_mode} onChange={(value) => setPolicy({ ...policy, early_clock_in_mode: value })}/>
            <IonInput fill="outline" type="number" label="Late Grace (Min.)" labelPlacement="floating" value={policy.late_clock_in_grace_minutes} onIonInput={(event) => setPolicy({ ...policy, late_clock_in_grace_minutes: Number(val(event) || 0) })}/>
            <IonInput fill="outline" type="number" label="No-show nach (Min.)" labelPlacement="floating" value={policy.no_show_after_minutes} onIonInput={(event) => setPolicy({ ...policy, no_show_after_minutes: Number(val(event) || 0) })}/>
            <ModeSelect label="Standort beim Einchecken" value={policy.clock_in_location_mode} onChange={(value) => setPolicy({ ...policy, clock_in_location_mode: value })}/>
            <ModeSelect label="Standort beim Auschecken" value={policy.clock_out_location_mode} onChange={(value) => setPolicy({ ...policy, clock_out_location_mode: value })}/>
            <IonInput fill="outline" type="number" label="Pflichtpause ab (Min.)" labelPlacement="floating" value={policy.required_break_after_minutes} onIonInput={(event) => setPolicy({ ...policy, required_break_after_minutes: Number(val(event) || 0) })}/>
            <IonInput fill="outline" type="number" label="Pflichtpause (Min.)" labelPlacement="floating" value={policy.required_break_minutes} onIonInput={(event) => setPolicy({ ...policy, required_break_minutes: Number(val(event) || 0) })}/>
            <Toggle label="Pause bezahlt" checked={!!policy.default_break_paid} onChange={(value) => setPolicy({ ...policy, default_break_paid: value })}/>
            <Toggle label="Fehlende unbezahlte Pause automatisch abziehen" checked={!!policy.auto_deduct_unpaid_breaks} onChange={(value) => setPolicy({ ...policy, auto_deduct_unpaid_breaks: value })}/>
            <Toggle label="Pausenbestätigung beim Ausstempeln" checked={!!policy.break_attestation_required} onChange={(value) => setPolicy({ ...policy, break_attestation_required: value })}/>
            <Toggle label="Schichtende bestätigen" checked={!!policy.end_of_shift_attestation_required} onChange={(value) => setPolicy({ ...policy, end_of_shift_attestation_required: value })}/>
            <Toggle label="Terminal-Foto beim Einstempeln" checked={!!policy.terminal_photo_clock_in} onChange={(value) => setPolicy({ ...policy, terminal_photo_clock_in: value })}/>
            <Toggle label="Terminal-Foto beim Ausstempeln" checked={!!policy.terminal_photo_clock_out} onChange={(value) => setPolicy({ ...policy, terminal_photo_clock_out: value })}/>
            <IonButton disabled={busy} onClick={() => void savePolicy()}>Policy speichern</IonButton>
          </div>}
        </section>

        <section className="att-v4-panel">
          <div className="att-v4-section-head"><div><small>TIME CLOCK TERMINAL</small><h2>Kiosk-Geräte</h2></div><IonButton size="small" onClick={() => setTerminal({ photo_clock_in: false, photo_clock_out: false })}><IonIcon slot="start" icon={tabletPortraitOutline}/>Terminal</IonButton></div>
          <p className="att-help">Mitarbeiter stempeln am festen Gerät mit Personalnummer oder E-Mail. Das Terminal Secret wird nur einmal angezeigt.</p>
          <div className="terminal-list">{data.terminals?.map((item: any) => <article key={item.id}>
            <div><b>{item.name}</b><span>{item.location_name}</span><small>{item.active ? 'Aktiv' : 'Deaktiviert'} · zuletzt {item.last_seen_at ? dateTime(item.last_seen_at) : 'noch nie'}</small></div>
            <div><IonBadge color={item.photo_clock_in || item.photo_clock_out ? 'primary' : 'medium'}><IonIcon icon={cameraOutline}/> Foto {item.photo_clock_in ? 'IN' : ''}{item.photo_clock_out ? ' OUT' : ''}</IonBadge><IonButton size="small" fill="outline" onClick={() => void rotateTerminal(item)}>Secret erneuern</IonButton></div>
          </article>)}</div>
          {!data.terminals?.length && <Empty text="Noch kein Time Clock Terminal eingerichtet." />}
        </section>
      </div>

      <section className="att-v4-panel">
        <div className="att-v4-section-head"><div><small>ZEITPRÜFUNG</small><h2>Korrekturen & offene Zeiten</h2></div></div>
        {data.pending_corrections?.map((item: any) => <Row key={item.id} title={item.worker_name} subtitle={item.reason} meta={`${dateTime(item.original_clock_in)} → ${dateTime(item.requested_clock_in || item.original_clock_in)}`} actions={<><IonButton size="small" onClick={() => void decideCorrection(item.id, 'approved')}>Genehmigen</IonButton><IonButton size="small" fill="outline" color="danger" onClick={() => void decideCorrection(item.id, 'rejected')}>Ablehnen</IonButton></>}/>) }
        {data.unapproved_entries?.map((item: any) => <Row key={item.id} title={item.worker_name} subtitle={item.shift_title} meta={`${dateTime(item.clock_in)} – ${dateTime(item.clock_out)} · ${minutesLabel(item.worked_minutes)} Std.`} actions={<IonButton size="small" onClick={() => void approveEntry(item.id)}>Freigeben</IonButton>}/>) }
        {longRunning.length > 0 && <div className="att-v4-subsection"><h3>Ungewöhnlich lange laufende Timer</h3>{longRunning.map((item: any) => <Row key={item.id} title={item.worker_name} subtitle="Laufender Timer" meta={`${minutesLabel(runningMinutes(item.clock_in, now))} Std. aktiv`} actions={<IonButton size="small" color="danger" onClick={() => setCloseTarget(item)}>Timer beenden</IonButton>}/>)}</div>}
      </section>

      <AbsencePanel rows={timeOff} manager onDecision={decideAbsence}/>

      <IonModal isOpen={!!terminal} onDidDismiss={() => setTerminal(undefined)}><div className="att-v4-modal">
        <small>TIME CLOCK TERMINAL</small><h2>Terminal einrichten</h2>
        <IonInput fill="outline" label="Name" labelPlacement="floating" value={terminal?.name} onIonInput={(event) => setTerminal({ ...terminal, name: val(event) })}/>
        <IonSelect fill="outline" label="Einsatzort" labelPlacement="floating" value={terminal?.location} onIonChange={(event) => setTerminal({ ...terminal, location: val(event) })}>{locations.map((item: any) => <IonSelectOption key={item.id} value={item.id}>{item.name}</IonSelectOption>)}</IonSelect>
        <Toggle label="Foto beim Einstempeln" checked={!!terminal?.photo_clock_in} onChange={(value) => setTerminal({ ...terminal, photo_clock_in: value })}/>
        <Toggle label="Foto beim Ausstempeln" checked={!!terminal?.photo_clock_out} onChange={(value) => setTerminal({ ...terminal, photo_clock_out: value })}/>
        <div className="att-v4-modal-actions"><IonButton fill="outline" onClick={() => setTerminal(undefined)}>Abbrechen</IonButton><IonButton disabled={busy} onClick={() => void createTerminal()}>Anlegen</IonButton></div>
      </div></IonModal>
      <IonModal isOpen={!!terminalSecret} onDidDismiss={() => setTerminalSecret(undefined)}><div className="att-v4-modal secret-modal">
        <small>SECRET · NUR EINMAL SICHTBAR</small><h2>{terminalSecret?.name || 'Terminal'}</h2><p>Terminal URL:</p><code>{`${window.location.origin}/terminal/${terminalSecret?.public_id}`}</code><p>Terminal Secret:</p><code>{terminalSecret?.terminal_token}</code><p>Beides auf dem Kiosk-Gerät hinterlegen.</p><IonButton onClick={() => setTerminalSecret(undefined)}>Verstanden</IonButton>
      </div></IonModal>
      <IonAlert
        isOpen={!!closeTarget}
        header="Laufenden Timer beenden?"
        message={closeTarget ? `${closeTarget.worker_name || 'Mitarbeiter'} · Bitte einen nachvollziehbaren Grund angeben.` : ''}
        inputs={[{ name: 'reason', type: 'textarea', placeholder: 'Grund *' }]}
        buttons={[
          { text: 'Abbrechen', role: 'cancel' },
          { text: 'Timer beenden', role: 'confirm', handler: (values) => {
            const reason = String(values?.reason || '').trim();
            if (!reason) {
              setToast('Bitte einen Grund angeben.');
              return false;
            }
            void confirmCloseRunning(reason);
            return true;
          } },
        ]}
        onDidDismiss={() => setCloseTarget(undefined)}
      />
      <IonToast isOpen={!!toast} message={toast} duration={4500} onDidDismiss={() => setToast('')}/>
    </div>;
  }

  const active = data.active_entry;
  const policyData = data.policy || {};
  const liveMinutes = active ? runningMinutes(active.clock_in, now) - Number(active.break_unpaid_minutes || 0) : 0;
  return <div className="attendance-v4 worker">
    <section className={`att-v4-hero worker ${active ? 'live' : ''}`}>
      <div><small>MEINE ARBEITSZEIT</small><h1>{active ? active.running_break ? 'Du bist in Pause.' : 'Du bist eingestempelt.' : 'Bereit für deinen Einsatz?'}</h1><p>{active ? `${active.shift_title} · Nettozeit wird aus echten Pausen berechnet.` : data.eligible_shift ? `${data.eligible_shift.position_name} · ${data.eligible_shift.location_name}` : 'Aktuell ist keine bestätigte Schicht im zulässigen Zeitfenster.'}</p></div>
      {active && <div className="att-live-clock"><small>NETTO</small><strong>{minutesLabel(Math.max(0, liveMinutes))}</strong><span>Std.</span></div>}
    </section>

    <div className="att-v4-stats worker">
      <Stat label="Dieser Monat" value={minutesLabel(data.month_worked_minutes || 0)} suffix="Std." />
      <Stat label="Unbezahlte Pause" value={`${active?.break_unpaid_minutes || 0} Min.`}/>
      <Stat label="Offene Korrekturen" value={data.pending_corrections || 0}/>
    </div>

    <section className="att-worker-clock-card">
      <div className="att-clock-copy"><small>{active ? 'AKTIVE ZEITERFASSUNG' : 'NÄCHSTE SCHICHT'}</small><h2>{active ? active.shift_title : data.eligible_shift?.position_name || 'Keine Schicht verfügbar'}</h2><p>{active ? `Start ${dateTime(active.clock_in)}${active.planned_break ? ` · geplante ${active.planned_break.paid ? 'bezahlte' : 'unbezahlte'} Pause ${active.planned_break.scheduled_minutes} Min.` : ''}` : data.eligible_shift ? `${dateTime(data.eligible_shift.starts_at)} · ${data.eligible_shift.location_name}` : 'Einstempeln wird freigeschaltet, sobald eine passende Schicht im Zeitfenster liegt.'}</p></div>
      <div className="att-clock-actions">
        {active ? <><IonButton className="break-button" fill={active.running_break ? 'solid' : 'outline'} color={active.running_break ? 'warning' : 'primary'} disabled={busy} onClick={() => void toggleBreak()}><IonIcon slot="start" icon={active.running_break ? playCircleOutline : pauseCircleOutline}/>{active.running_break ? 'Pause beenden' : 'Pause starten'}</IonButton><IonButton color="danger" disabled={busy || !!active.running_break} onClick={() => void clock('out')}>Ausstempeln</IonButton></> : <IonButton disabled={busy || (!data.eligible_shift && !policyData.allow_unscheduled_clock_in)} onClick={() => void clock('in')}>Einstempeln</IonButton>}
      </div>
    </section>

    {active?.breaks?.length > 0 && <section className="att-v4-panel"><div className="att-v4-section-head"><div><small>PAUSEN</small><h2>Heute</h2></div></div><div className="break-timeline">{active.breaks.map((item: any) => <article key={item.id} className={item.status}><IonIcon icon={item.status === 'completed' ? checkmarkCircleOutline : item.status === 'running' ? pauseCircleOutline : timeOutline}/><div><b>{item.paid ? 'Bezahlte' : 'Unbezahlte'} Pause</b><span>{item.status === 'planned' ? `${item.scheduled_minutes} Min. geplant` : item.status === 'running' ? `seit ${dateTime(item.started_at)}` : `${item.actual_minutes} Min. · ${dateTime(item.started_at)}–${dateTime(item.ended_at)}`}</span></div><IonBadge color={item.paid ? 'success' : item.status === 'running' ? 'warning' : 'medium'}>{item.status}</IonBadge></article>)}</div></section>}

    <section className="att-v4-panel"><div className="att-v4-section-head"><div><small>VERLAUF</small><h2>Meine Arbeitszeiten</h2></div></div>{data.history?.length ? data.history.map((entry: any) => <article className="att-history" key={entry.id}><div><b>{dateOnly(entry.clock_in)} · {entry.shift_title}</b><span>{dateTime(entry.clock_in)} – {dateTime(entry.clock_out)}</span><small>{entry.break_unpaid_minutes ? `${entry.break_unpaid_minutes} Min. unbezahlte Pause · ` : ''}{entry.break_paid_minutes ? `${entry.break_paid_minutes} Min. bezahlt · ` : ''}Netto {minutesLabel(entry.worked_minutes)} Std.</small></div><IonButton size="small" fill="outline" onClick={() => setCorrection({ entry, clock_in: entry.clock_in?.slice(0, 16), clock_out: entry.clock_out?.slice(0, 16), reason: '' })}>Korrektur</IonButton></article>) : <Empty text="Noch keine abgeschlossenen Arbeitszeiten." />}</section>

    <AbsencePanel rows={timeOff} onNew={() => setAbsence({})}/>

    <IonModal isOpen={!!attest} onDidDismiss={() => setAttest(undefined)}><div className="att-v4-modal"><small>BESTÄTIGUNG</small><h2>Schicht abschließen</h2>{attest?.break && <label className="att-question"><IonCheckbox checked={!!attest.breaks_taken} onIonChange={(event) => setAttest({ ...attest, breaks_taken: event.detail.checked })}/><span>Ich habe meine vorgesehenen Pausen genommen.</span></label>}{attest?.end && <label className="att-question"><IonCheckbox checked={!!attest.shift_ok} onIonChange={(event) => setAttest({ ...attest, shift_ok: event.detail.checked })}/><span>Die Schicht wurde wie geplant beendet.</span></label>}<IonTextarea fill="outline" label="Hinweis / Grund" labelPlacement="floating" value={attest?.note} onIonInput={(event) => setAttest({ ...attest, note: val(event) })}/><div className="att-v4-modal-actions"><IonButton fill="outline" onClick={() => setAttest(undefined)}>Später</IonButton><IonButton disabled={busy} onClick={() => void submitAttestation()}>Bestätigen</IonButton></div></div></IonModal>

    <IonModal isOpen={!!correction} onDidDismiss={() => setCorrection(undefined)}><div className="att-v4-modal"><small>ARBEITSZEIT KORRIGIEREN</small><h2>Korrektur anfragen</h2><IonInput fill="outline" type="datetime-local" label="Beginn" labelPlacement="floating" value={correction?.clock_in} onIonInput={(event) => setCorrection({ ...correction, clock_in: val(event) })}/><IonInput fill="outline" type="datetime-local" label="Ende" labelPlacement="floating" value={correction?.clock_out} onIonInput={(event) => setCorrection({ ...correction, clock_out: val(event) })}/><IonTextarea fill="outline" label="Grund" labelPlacement="floating" value={correction?.reason} onIonInput={(event) => setCorrection({ ...correction, reason: val(event) })}/><div className="att-v4-modal-actions"><IonButton fill="outline" onClick={() => setCorrection(undefined)}>Abbrechen</IonButton><IonButton disabled={busy} onClick={() => void submitCorrection()}>Anfrage senden</IonButton></div></div></IonModal>
    <IonModal isOpen={absence !== undefined} onDidDismiss={() => setAbsence(undefined)}><div className="att-v4-modal"><small>ABWESENHEIT</small><h2>Antrag senden</h2><IonInput fill="outline" type="date" label="Von" labelPlacement="floating" value={absence?.starts_on} onIonInput={(event) => setAbsence({ ...absence, starts_on: val(event) })}/><IonInput fill="outline" type="date" label="Bis" labelPlacement="floating" value={absence?.ends_on} onIonInput={(event) => setAbsence({ ...absence, ends_on: val(event) })}/><IonTextarea fill="outline" label="Grund / Hinweis" labelPlacement="floating" value={absence?.reason} onIonInput={(event) => setAbsence({ ...absence, reason: val(event) })}/><div className="att-v4-modal-actions"><IonButton fill="outline" onClick={() => setAbsence(undefined)}>Abbrechen</IonButton><IonButton disabled={busy} onClick={() => void requestAbsence()}>Antrag senden</IonButton></div></div></IonModal>
    <IonToast isOpen={!!toast} message={toast} duration={4500} onDidDismiss={() => setToast('')}/>
  </div>;
}

function ModeSelect({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <IonSelect fill="outline" label={label} labelPlacement="floating" value={value} onIonChange={(event) => onChange(String(val(event)))}><IonSelectOption value="off">Aus</IonSelectOption><IonSelectOption value="warn">Hinweis</IonSelectOption><IonSelectOption value="block">Blockieren</IonSelectOption></IonSelect>;
}
function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return <label className="att-toggle"><span>{label}</span><IonToggle checked={checked} onIonChange={(event) => onChange(event.detail.checked)}/></label>;
}
function Stat({ label, value, suffix, danger }: { label: string; value: any; suffix?: string; danger?: boolean }) {
  return <div className={`att-v4-stat ${danger ? 'danger' : ''}`}><small>{label}</small><strong>{value}</strong>{suffix && <span>{suffix}</span>}</div>;
}
function Empty({ text }: { text: string }) {
  return <div className="att-v4-empty">{text}</div>;
}
function Row({ title, subtitle, meta, actions }: { title: string; subtitle?: string; meta?: string; actions?: React.ReactNode }) {
  return <div className="att-v4-row"><div><b>{title}</b><span>{subtitle}</span><small>{meta}</small></div><div>{actions}</div></div>;
}
function AbsencePanel({ rows, manager, onDecision, onNew }: { rows: any[]; manager?: boolean; onDecision?: (id: string, status: 'approved' | 'rejected') => void; onNew?: () => void }) {
  return <section className="att-v4-panel"><div className="att-v4-section-head"><div><small>ABWESENHEIT</small><h2>{manager ? 'Anträge' : 'Meine Abwesenheiten'}</h2></div>{onNew && <IonButton size="small" fill="outline" onClick={onNew}>Neue Abwesenheit</IonButton>}</div>{rows.length ? rows.map((item: any) => <Row key={item.id} title={item.worker_name || 'Mein Antrag'} subtitle={`${dateOnly(item.starts_on)} – ${dateOnly(item.ends_on)} · ${item.reason || 'Ohne Hinweis'}`} meta={item.status} actions={manager && item.status === 'pending' && onDecision ? <><IonButton size="small" onClick={() => onDecision(item.id, 'approved')}>Genehmigen</IonButton><IonButton size="small" fill="outline" color="danger" onClick={() => onDecision(item.id, 'rejected')}>Ablehnen</IonButton></> : <IonBadge color={item.status === 'approved' ? 'success' : item.status === 'rejected' ? 'danger' : 'warning'}>{item.status}</IonBadge>}/>) : <Empty text="Keine Abwesenheitsanträge."/>}</section>;
}
