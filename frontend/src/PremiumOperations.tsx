import React, { useEffect, useMemo, useState } from 'react';
import {
  IonBadge,
  IonButton,
  IonInput,
  IonItem,
  IonLabel,
  IonSelect,
  IonSelectOption,
  IonTextarea,
  IonToggle,
} from '@ionic/react';
import { api, User } from './api';
import './premium-operations.css';

const unpack = (value: any): any[] => value?.results || value || [];
const isoDate = (date = new Date()) => date.toISOString().slice(0, 10);
const addDays = (days: number) => {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return isoDate(date);
};

export default function PremiumOperations({ user }: { user: User }) {
  const manager = ['admin', 'manager'].includes(user.role);
  const admin = user.role === 'admin';
  const worker = user.role === 'worker';
  const [policy, setPolicy] = useState<any>();
  const [pickup, setPickup] = useState<any[]>([]);
  const [tasks, setTasks] = useState<any[]>([]);
  const [taskLists, setTaskLists] = useState<any[]>([]);
  const [locations, setLocations] = useState<any[]>([]);
  const [reports, setReports] = useState<any[]>([]);
  const [apiKeys, setApiKeys] = useState<any[]>([]);
  const [webhooks, setWebhooks] = useState<any[]>([]);
  const [saml, setSaml] = useState<any>({ enabled: false });
  const [mine, setMine] = useState<any[]>([]);
  const [autoRange, setAutoRange] = useState({ start: isoDate(), end: addDays(14), location_id: '' });
  const [autoResult, setAutoResult] = useState<any>();
  const [newTask, setNewTask] = useState({ name: '', items: '', location_id: '' });
  const [calloutShift, setCalloutShift] = useState('');
  const [calloutReason, setCalloutReason] = useState('');
  const [webhookUrl, setWebhookUrl] = useState('');
  const [issuedKey, setIssuedKey] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const base: Promise<any>[] = [api('auth/saml/status/'), api('premium/task-runs/')];
      const [samlData, taskData] = await Promise.all(base);
      setSaml(samlData);
      setTasks(unpack(taskData));
      if (worker) {
        const shifts = await api('shifts/mine/?ordering=starts_at');
        setMine(unpack(shifts).filter((item: any) => new Date(item.ends_at) >= new Date()));
      }
      if (manager) {
        const [p, approvals, lists, locs, reportDefs] = await Promise.all([
          api('premium/scheduling-policy/'),
          api('premium/pickup-requests/'),
          api('premium/task-lists/'),
          api('locations/?ordering=name'),
          api('premium/reports/'),
        ]);
        setPolicy(p);
        setPickup(unpack(approvals));
        setTaskLists(unpack(lists));
        setLocations(unpack(locs));
        setReports(unpack(reportDefs));
      }
      if (admin) {
        const [keys, hooks] = await Promise.all([api('premium/api-keys/'), api('premium/webhooks/')]);
        setApiKeys(unpack(keys));
        setWebhooks(unpack(hooks));
      }
    } catch (error: any) {
      setMessage(error.message || 'Premium-Daten konnten nicht geladen werden.');
    }
  };

  useEffect(() => { load(); }, [user.role]);

  const run = async (fn: () => Promise<any>, success: string) => {
    setBusy(true);
    try {
      const result = await fn();
      setMessage(success);
      await load();
      return result;
    } catch (error: any) {
      setMessage(error.message || 'Aktion fehlgeschlagen.');
    } finally {
      setBusy(false);
    }
  };

  const savePolicy = () => run(
    () => api('premium/scheduling-policy/', { method: 'PATCH', body: JSON.stringify(policy) }),
    'Planungsregeln gespeichert.',
  );

  const autoSchedule = async (apply: boolean) => {
    const result = await run(
      () => api('premium/auto-schedule/', {
        method: 'POST',
        body: JSON.stringify({ ...autoRange, apply }),
      }),
      apply ? 'Automatische Planung angewendet.' : 'Planungsvorschlag berechnet.',
    );
    if (result) setAutoResult(result);
  };

  const decidePickup = (id: string, status: 'approved' | 'rejected') => run(
    () => api(`premium/pickup-requests/${id}/decide/`, { method: 'POST', body: JSON.stringify({ status }) }),
    status === 'approved' ? 'Schichtübernahme genehmigt.' : 'Schichtübernahme abgelehnt.',
  );

  const createTaskList = () => {
    const items = newTask.items.split('\n').map((title) => title.trim()).filter(Boolean).map((title) => ({ title, required: true }));
    if (!newTask.name || !items.length) return setMessage('Name und mindestens eine Aufgabe eingeben.');
    return run(
      () => api('premium/task-lists/', {
        method: 'POST',
        body: JSON.stringify({ name: newTask.name, kind: 'shift', location_id: newTask.location_id || null, items }),
      }),
      'Aufgabenliste erstellt.',
    );
  };

  const completeTask = (runId: string, itemId: string) => run(
    () => api(`premium/task-runs/${runId}/complete/`, { method: 'POST', body: JSON.stringify({ item_id: itemId }) }),
    'Aufgabe erledigt.',
  );

  const callout = () => {
    if (!calloutShift) return setMessage('Bitte eine Schicht auswählen.');
    return run(
      () => api('premium/callouts/', { method: 'POST', body: JSON.stringify({ shift_id: calloutShift, reason: calloutReason }) }),
      'Ausfall gemeldet; die Kapazität ist wieder offen.',
    );
  };

  const createStandardReports = async () => {
    const desired = [
      ['Schichtbericht', 'shifts'],
      ['Zeiterfassung', 'times'],
      ['Schichtverlauf', 'shift_history'],
      ['Abwesenheiten', 'time_off'],
      ['Personalkosten & Forecast', 'labor'],
    ];
    setBusy(true);
    try {
      for (const [name, kind] of desired) {
        if (!reports.some((item) => item.kind === kind)) {
          await api('premium/reports/', { method: 'POST', body: JSON.stringify({ name, kind, shared: true }) });
        }
      }
      setMessage('Standardberichte sind verfügbar.');
      await load();
    } catch (error: any) {
      setMessage(error.message || 'Berichte konnten nicht angelegt werden.');
    } finally {
      setBusy(false);
    }
  };

  const issueApiKey = async () => {
    const result = await run(
      () => api('premium/api-keys/', { method: 'POST', body: JSON.stringify({ name: 'Operations API', scopes: ['users:read', 'shifts:read', 'shifts:write', 'times:read', 'time_off:read', 'time_off:write', 'tasks:read'] }) }),
      'API-Key erstellt. Jetzt sicher kopieren.',
    );
    if (result?.key) setIssuedKey(result.key);
  };

  const createWebhook = () => {
    if (!webhookUrl) return setMessage('Webhook-URL eingeben.');
    return run(
      () => api('premium/webhooks/', { method: 'POST', body: JSON.stringify({ name: 'Operations Webhook', endpoint_url: webhookUrl, events: ['shifts.*', 'times.*', 'time_off.*', 'callouts.*', 'tasks.*'] }) }),
      'Webhook erstellt.',
    );
  };

  const pendingRequiredTasks = useMemo(
    () => tasks.reduce((sum, run) => sum + (run.items || []).filter((item: any) => item.required && !item.completed).length, 0),
    [tasks],
  );

  if (!manager && !worker) return null;

  return (
    <section className="operations-panel premium-ops" data-testid="premium-operations-panel">
      <div className="premium-head">
        <div>
          <small>WIW PREMIUM PARITY</small>
          <h3>{worker ? 'Meine Premium-Funktionen' : 'Premium Workforce Steuerung'}</h3>
          <p>{worker ? 'Aufgaben und kurzfristige Ausfälle direkt aus der App bearbeiten.' : 'Auto Scheduling, Regeln, Forecast, Tasks, Reports, API, Webhooks und Enterprise SSO.'}</p>
        </div>
        <div className="premium-badges">
          {manager && <IonBadge color="success">Native</IonBadge>}
          {admin && <IonBadge color={saml.enabled ? 'success' : 'medium'}>SAML {saml.enabled ? 'aktiv' : 'bereit'}</IonBadge>}
          {worker && <IonBadge color={pendingRequiredTasks ? 'warning' : 'success'}>{pendingRequiredTasks} Aufgaben offen</IonBadge>}
        </div>
      </div>

      {message && <div className="premium-message">{message}</div>}

      {manager && policy && (
        <details open className="premium-box">
          <summary>Planungsregeln & Auto Scheduling</summary>
          <div className="premium-toggle-grid">
            {[
              ['auto_schedule_enabled', 'Auto Scheduling'],
              ['pickup_approval_required', 'OpenShift-Übernahme freigeben'],
              ['labor_sharing_enabled', 'Labor Sharing zwischen Einsatzorten'],
              ['allow_overlapping_open_shifts', 'Überlappende OpenShifts'],
              ['allow_multiple_shifts_per_day', 'Mehrere Schichten pro Tag'],
              ['timezone_toggle_enabled', 'Zeitzonenumschaltung'],
            ].map(([key, label]) => (
              <IonItem lines="none" key={key}>
                <IonLabel>{label}</IonLabel>
                <IonToggle checked={!!policy[key]} onIonChange={(event) => setPolicy({ ...policy, [key]: event.detail.checked })} />
              </IonItem>
            ))}
          </div>
          <div className="premium-fields">
            <IonInput type="number" fill="outline" label="Ruhezeit zwischen Tagen" labelPlacement="floating" value={policy.min_hours_between_days} onIonInput={(event) => setPolicy({ ...policy, min_hours_between_days: event.detail.value })} />
            <IonInput type="number" fill="outline" label="Max. Std./Tag" labelPlacement="floating" value={policy.max_hours_per_day} onIonInput={(event) => setPolicy({ ...policy, max_hours_per_day: event.detail.value })} />
            <IonInput type="number" fill="outline" label="Max. Std./Woche" labelPlacement="floating" value={policy.max_hours_per_week} onIonInput={(event) => setPolicy({ ...policy, max_hours_per_week: event.detail.value })} />
            <IonInput type="number" fill="outline" label="Max. Tage in Folge" labelPlacement="floating" value={policy.max_days_in_row} onIonInput={(event) => setPolicy({ ...policy, max_days_in_row: event.detail.value })} />
          </div>
          <div className="premium-actions"><IonButton disabled={busy} onClick={savePolicy}>Regeln speichern</IonButton></div>
          <div className="premium-fields auto-range">
            <IonInput type="date" fill="outline" label="Von" labelPlacement="floating" value={autoRange.start} onIonInput={(event) => setAutoRange({ ...autoRange, start: String(event.detail.value || '') })} />
            <IonInput type="date" fill="outline" label="Bis" labelPlacement="floating" value={autoRange.end} onIonInput={(event) => setAutoRange({ ...autoRange, end: String(event.detail.value || '') })} />
            <IonSelect fill="outline" label="Einsatzort" labelPlacement="floating" value={autoRange.location_id} onIonChange={(event) => setAutoRange({ ...autoRange, location_id: event.detail.value })}>
              <IonSelectOption value="">Alle Einsatzorte</IonSelectOption>
              {locations.map((location) => <IonSelectOption key={location.id} value={location.id}>{location.name}</IonSelectOption>)}
            </IonSelect>
          </div>
          <div className="premium-actions">
            <IonButton fill="outline" disabled={busy} onClick={() => autoSchedule(false)}>Vorschau</IonButton>
            <IonButton disabled={busy} onClick={() => autoSchedule(true)}>Automatisch besetzen</IonButton>
          </div>
          {autoResult && <div className="premium-result"><b>{autoResult.assigned}</b> besetzt · <b>{autoResult.unfilled}</b> offen</div>}
        </details>
      )}

      {manager && pickup.length > 0 && (
        <details open className="premium-box">
          <summary>Offene Übernahmeanfragen <IonBadge color="warning">{pickup.length}</IonBadge></summary>
          {pickup.map((item) => (
            <div className="premium-row" key={item.id}>
              <div><b>{item.worker}</b><span>{new Date(item.starts_at).toLocaleString('de-DE')} · {item.location} · {item.position}</span></div>
              <div><IonButton size="small" color="success" onClick={() => decidePickup(item.id, 'approved')}>Genehmigen</IonButton><IonButton size="small" fill="outline" color="danger" onClick={() => decidePickup(item.id, 'rejected')}>Ablehnen</IonButton></div>
            </div>
          ))}
        </details>
      )}

      {manager && (
        <details className="premium-box">
          <summary>Task Lists & Custom Reports</summary>
          <div className="premium-fields">
            <IonInput fill="outline" label="Name der Aufgabenliste" labelPlacement="floating" value={newTask.name} onIonInput={(event) => setNewTask({ ...newTask, name: String(event.detail.value || '') })} />
            <IonSelect fill="outline" label="Einsatzort optional" labelPlacement="floating" value={newTask.location_id} onIonChange={(event) => setNewTask({ ...newTask, location_id: event.detail.value })}>
              <IonSelectOption value="">Alle</IonSelectOption>
              {locations.map((location) => <IonSelectOption key={location.id} value={location.id}>{location.name}</IonSelectOption>)}
            </IonSelect>
            <IonTextarea className="premium-wide" fill="outline" autoGrow label="Eine Aufgabe pro Zeile" labelPlacement="floating" value={newTask.items} onIonInput={(event) => setNewTask({ ...newTask, items: String(event.detail.value || '') })} />
          </div>
          <div className="premium-actions"><IonButton fill="outline" onClick={createTaskList}>Task List erstellen</IonButton><IonButton fill="outline" onClick={createStandardReports}>Standardberichte anlegen</IonButton></div>
          <div className="premium-result">{taskLists.length} Aufgabenlisten · {reports.length} gespeicherte Berichte</div>
        </details>
      )}

      {worker && (
        <>
          <details open className="premium-box">
            <summary>Meine Schichtaufgaben</summary>
            {!tasks.length && <p className="premium-muted">Keine Aufgaben zugewiesen.</p>}
            {tasks.map((run) => (
              <div className="premium-task-run" key={run.id}>
                <b>{run.name}</b><small>{run.location} · {new Date(run.run_date).toLocaleDateString('de-DE')}</small>
                {(run.items || []).map((item: any) => (
                  <button key={item.id} className={`premium-task ${item.completed ? 'done' : ''}`} disabled={item.completed || busy} onClick={() => completeTask(run.id, item.id)}>
                    <span>{item.completed ? '✓' : '○'}</span>{item.title}{item.required && !item.completed ? ' *' : ''}
                  </button>
                ))}
              </div>
            ))}
          </details>
          <details className="premium-box">
            <summary>Ausfall innerhalb 24 Stunden melden</summary>
            <IonSelect fill="outline" label="Meine Schicht" labelPlacement="floating" value={calloutShift} onIonChange={(event) => setCalloutShift(event.detail.value)}>
              {mine.map((shift) => <IonSelectOption key={shift.id} value={shift.id}>{new Date(shift.starts_at).toLocaleString('de-DE')} · {shift.location_name || shift.location?.name || shift.position_name}</IonSelectOption>)}
            </IonSelect>
            <IonTextarea fill="outline" label="Grund / Hinweis" labelPlacement="floating" value={calloutReason} onIonInput={(event) => setCalloutReason(String(event.detail.value || ''))} />
            <div className="premium-actions"><IonButton color="warning" disabled={busy} onClick={callout}>Ausfall melden</IonButton></div>
          </details>
        </>
      )}

      {admin && (
        <details className="premium-box">
          <summary>API, Webhooks & Enterprise SSO</summary>
          <div className="premium-enterprise">
            <div><b>Public API</b><span>{apiKeys.length} aktive/gespeicherte Keys</span><IonButton size="small" fill="outline" onClick={issueApiKey}>Neuen API-Key</IonButton></div>
            <div><b>SAML 2.0 / SSO</b><span>{saml.enabled ? 'IdP ist konfiguriert' : 'Code aktiv, IdP-Credentials fehlen'}</span><IonBadge color={saml.enabled ? 'success' : 'medium'}>{saml.enabled ? 'Aktiv' : 'Konfigurieren'}</IonBadge></div>
          </div>
          {issuedKey && <div className="premium-key"><b>Nur jetzt sichtbar:</b><code>{issuedKey}</code></div>}
          <div className="premium-fields">
            <IonInput className="premium-wide" fill="outline" type="url" label="Webhook HTTPS URL" labelPlacement="floating" value={webhookUrl} onIonInput={(event) => setWebhookUrl(String(event.detail.value || ''))} />
          </div>
          <div className="premium-actions"><IonButton fill="outline" onClick={createWebhook}>Webhook anlegen</IonButton></div>
          <div className="premium-result">{webhooks.length} Webhook-Abos · signierte HMAC-Auslieferung mit Retry</div>
        </details>
      )}
    </section>
  );
}
