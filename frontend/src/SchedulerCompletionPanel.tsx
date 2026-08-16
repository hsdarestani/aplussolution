import React, { useEffect, useMemo, useState } from 'react';
import {
  IonBadge,
  IonButton,
  IonCheckbox,
  IonInput,
  IonModal,
  IonSegment,
  IonSegmentButton,
  IonSelect,
  IonSelectOption,
  IonSpinner,
  IonTextarea,
  IonToggle,
} from '@ionic/react';
import { api, apiAll, User } from './api';
import './scheduler-completion.css';

const value = (event: any) => event.detail?.value ?? '';
const dateKey = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
const tomorrow = (input: string) => {
  const d = new Date(`${input}T12:00:00`);
  d.setDate(d.getDate() + 1);
  return dateKey(d);
};

export type SchedulerDisplay = {
  color_mode: 'shift' | 'position' | 'location';
  timezone_mode: 'workplace' | 'schedule' | 'local';
  local_timezone: string;
  workplace_timezone?: string;
};

type Props = {
  open: boolean;
  onClose: () => void;
  user: User;
  rows: any[];
  locations: any[];
  positions: any[];
  workers: any[];
  display: SchedulerDisplay;
  onDisplayChange: (display: SchedulerDisplay) => void;
  onChanged: () => void | Promise<void>;
};

const blankAnnotation = () => ({
  kind: 'announcement', title: '', message: '', starts_on: dateKey(new Date()), ends_on: dateKey(new Date()),
  location: '', schedule: '', business_closed_action: 'leave',
});
const blankTaskList = () => ({ title: '', work_date: dateKey(new Date()), notes: '', location: '', schedule: '' });

export default function SchedulerCompletionPanel({ open, onClose, user, rows, locations, positions, workers, display, onDisplayChange, onChanged }: Props) {
  const manager = ['admin', 'manager'].includes(user.role);
  const [tab, setTab] = useState(manager ? 'annotations' : 'overview');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [annotations, setAnnotations] = useState<any[]>([]);
  const [taskLists, setTaskLists] = useState<any[]>([]);
  const [confirmations, setConfirmations] = useState<any[]>([]);
  const [settings, setSettings] = useState<any>({ allow_overlapping_open_shifts: false, require_shift_confirmation: true, can_manage: false });
  const [schedules, setSchedules] = useState<any[]>([]);
  const [colors, setColors] = useState<any[]>([]);
  const [annotationForm, setAnnotationForm] = useState<any>(blankAnnotation());
  const [taskListForm, setTaskListForm] = useState<any>(blankTaskList());
  const [taskForm, setTaskForm] = useState<any>({ task_list: '', title: '', assignee: '', position: '' });
  const [copyForm, setCopyForm] = useState<any>({ source_start: dateKey(new Date()), source_end: dateKey(new Date()), target_start: dateKey(new Date(Date.now() + 86400000)) });
  const [colorForm, setColorForm] = useState<any>({ target_type: 'shift', target_id: '', color: '#2457E6' });

  async function load() {
    setBusy(true); setError('');
    try {
      const requests: Promise<any>[] = [
        api('scheduling/completion-snapshot/'),
        api('scheduling/completion-settings/'),
        api('scheduling/display-preferences/'),
      ];
      if (manager) requests.push(apiAll('schedule-groups/'), apiAll('scheduler-colors/'));
      else requests.push(api('scheduling/confirmations/'));
      const result = await Promise.all(requests);
      const snapshot = result[0] || {};
      setAnnotations(snapshot.annotations || []);
      setTaskLists(snapshot.task_lists || []);
      setSettings(result[1] || {});
      onDisplayChange({ ...display, ...(result[2] || {}) });
      if (manager) {
        setSchedules(result[3] || []);
        setColors(result[4] || []);
      } else {
        setConfirmations(result[3]?.results || []);
      }
    } catch (reason: any) {
      setError(reason.message || 'Planungsdaten konnten nicht geladen werden.');
    } finally { setBusy(false); }
  }

  useEffect(() => { if (open) void load(); }, [open]);

  async function saveAnnotation() {
    if (!annotationForm.title || !annotationForm.starts_on || !annotationForm.ends_on) { setError('Titel und Zeitraum sind erforderlich.'); return; }
    setBusy(true); setError('');
    try {
      const payload = { ...annotationForm, location: annotationForm.location || null, schedule: annotationForm.schedule || null };
      const row: any = await api('schedule-annotations/', { method: 'POST', body: JSON.stringify(payload) });
      setAnnotations((current) => [...current, row].sort((a, b) => String(a.starts_on).localeCompare(String(b.starts_on))));
      setAnnotationForm(blankAnnotation());
      setNotice(row.business_closed_result?.changed ? `${row.business_closed_result.changed} Schicht(en) wurden angepasst.` : 'Annotation gespeichert.');
      await onChanged();
    } catch (reason: any) { setError(reason.message); }
    finally { setBusy(false); }
  }

  async function archiveAnnotation(id: string) {
    if (!window.confirm('Annotation wirklich entfernen?')) return;
    setBusy(true);
    try {
      await api(`schedule-annotations/${id}/`, { method: 'DELETE' });
      setAnnotations((current) => current.filter((item) => item.id !== id));
      setNotice('Annotation entfernt.');
    } catch (reason: any) { setError(reason.message); }
    finally { setBusy(false); }
  }

  async function createTaskList() {
    if (!taskListForm.title || !taskListForm.work_date) { setError('Titel und Datum sind erforderlich.'); return; }
    setBusy(true); setError('');
    try {
      const row: any = await api('schedule-task-lists/', { method: 'POST', body: JSON.stringify({ ...taskListForm, location: taskListForm.location || null, schedule: taskListForm.schedule || null }) });
      setTaskLists((current) => [...current, row]);
      setTaskForm((current: any) => ({ ...current, task_list: row.id }));
      setTaskListForm(blankTaskList());
      setNotice('Task List angelegt.');
    } catch (reason: any) { setError(reason.message); }
    finally { setBusy(false); }
  }

  async function createTask() {
    if (!taskForm.task_list || !taskForm.title) { setError('Task List und Aufgabe sind erforderlich.'); return; }
    setBusy(true); setError('');
    try {
      await api('schedule-tasks/', { method: 'POST', body: JSON.stringify({ ...taskForm, assignee: taskForm.assignee || null, position: taskForm.position || null }) });
      setTaskForm((current: any) => ({ ...current, title: '', assignee: '', position: '' }));
      setNotice('Aufgabe hinzugefügt.');
      await load();
    } catch (reason: any) { setError(reason.message); }
    finally { setBusy(false); }
  }

  async function completeTask(task: any, completed: boolean) {
    setBusy(true);
    try {
      await api(`schedule-tasks/${task.id}/complete/`, { method: 'POST', body: JSON.stringify({ completed }) });
      await load();
    } catch (reason: any) { setError(reason.message); }
    finally { setBusy(false); }
  }

  async function confirmShift(slot: string) {
    setBusy(true);
    try {
      await api(`scheduling/confirmations/${slot}/confirm/`, { method: 'POST', body: '{}' });
      setConfirmations((current) => current.filter((item) => item.slot !== slot));
      setNotice('Schicht bestätigt.');
      await onChanged();
    } catch (reason: any) { setError(reason.message); }
    finally { setBusy(false); }
  }

  async function saveSettings(next: any) {
    setBusy(true); setError('');
    try {
      const updated: any = await api('scheduling/completion-settings/', { method: 'PATCH', body: JSON.stringify(next) });
      setSettings(updated);
      setNotice('Scheduler-Einstellungen gespeichert.');
      await onChanged();
    } catch (reason: any) { setError(reason.message); }
    finally { setBusy(false); }
  }

  async function saveDisplay(next: Partial<SchedulerDisplay>) {
    const merged = { ...display, ...next } as SchedulerDisplay;
    onDisplayChange(merged);
    try {
      const result: any = await api('scheduling/display-preferences/', { method: 'PATCH', body: JSON.stringify(next) });
      onDisplayChange({ ...merged, ...result });
    } catch (reason: any) { setError(reason.message); }
  }

  async function copyRange() {
    if (!copyForm.source_start || !copyForm.source_end || !copyForm.target_start) return;
    setBusy(true); setError('');
    try {
      const result: any = await api('scheduling/copy-range/', {
        method: 'POST',
        body: JSON.stringify({ source_start: copyForm.source_start, source_end: tomorrow(copyForm.source_end), target_start: copyForm.target_start }),
      });
      setNotice(`${result.created?.length || 0} Schicht(en) kopiert${result.warnings?.length ? ` · ${result.warnings.length} Besetzungswarnung(en)` : ''}.`);
      await onChanged();
    } catch (reason: any) { setError(reason.message); }
    finally { setBusy(false); }
  }

  async function saveColor() {
    if (!colorForm.target_id) { setError('Bitte Schicht, Position oder Einsatzort auswählen.'); return; }
    setBusy(true); setError('');
    try {
      if (colorForm.target_type === 'position') {
        await api(`positions/${colorForm.target_id}/`, { method: 'PATCH', body: JSON.stringify({ color: colorForm.color }) });
      } else {
        const existing = colors.find((item) => item.target_type === colorForm.target_type && item.target_id === colorForm.target_id);
        const path = existing ? `scheduler-colors/${existing.id}/` : 'scheduler-colors/';
        const method = existing ? 'PATCH' : 'POST';
        const row: any = await api(path, { method, body: JSON.stringify(colorForm) });
        setColors((current) => [row, ...current.filter((item) => item.id !== row.id)]);
      }
      setNotice('Farbe gespeichert.');
      await onChanged();
    } catch (reason: any) { setError(reason.message); }
    finally { setBusy(false); }
  }

  const activeTargetOptions = useMemo(() => {
    if (colorForm.target_type === 'shift') return rows.map((row) => ({ id: row.id, name: `${new Date(row.starts_at).toLocaleDateString('de-DE')} · ${row.position_name} · ${row.location_name}` }));
    if (colorForm.target_type === 'position') return positions.map((row) => ({ id: row.id, name: row.name }));
    return locations.map((row) => ({ id: row.id, name: row.name }));
  }, [colorForm.target_type, rows, positions, locations]);

  return <IonModal isOpen={open} onDidDismiss={onClose} className="scheduler-completion-modal">
    <div className="scheduler-completion" data-testid="scheduler-completion-panel">
      <header>
        <div><small>A+ WORKFORCE · SCHEDULER COMPLETION</small><h2>{manager ? 'Plan-Extras' : 'Planinfos'}</h2><p>Annotations, Aufgaben, Bestätigungen, Farben und Zeitzonen.</p></div>
        <IonButton fill="clear" onClick={onClose}>Schließen</IonButton>
      </header>
      <IonSegment scrollable value={tab} onIonChange={(event) => setTab(String(value(event)))}>
        {!manager && <IonSegmentButton value="overview">Übersicht <IonBadge>{confirmations.length}</IonBadge></IonSegmentButton>}
        <IonSegmentButton value="annotations">Annotations</IonSegmentButton>
        <IonSegmentButton value="tasks">Task Lists</IonSegmentButton>
        {manager && <IonSegmentButton value="copy">Kopieren</IonSegmentButton>}
        <IonSegmentButton value="display">Ansicht</IonSegmentButton>
        {manager && <IonSegmentButton value="settings">Regeln</IonSegmentButton>}
      </IonSegment>
      {busy && <div className="sc-busy"><IonSpinner name="dots"/> Daten werden aktualisiert …</div>}
      {error && <div className="sc-message error">{error}</div>}
      {notice && <div className="sc-message success">{notice}</div>}

      {tab === 'overview' && !manager && <main className="sc-page">
        <section className="sc-card"><h3>Schichten bestätigen</h3>{confirmations.map((item) => <article className="sc-row" key={item.id}><div><b>{item.position}</b><small>{new Date(item.starts_at).toLocaleString('de-DE')} · {item.location}</small></div><IonButton size="small" onClick={() => void confirmShift(item.slot)}>Bestätigen</IonButton></article>)}{!confirmations.length && <p className="sc-empty">Keine offene Schichtbestätigung.</p>}</section>
        <section className="sc-card"><h3>Aktuelle Hinweise</h3>{annotations.map((item) => <article className="sc-row" key={item.id}><div><b>{item.title}</b><small>{item.starts_on}–{item.ends_on} · {item.location_name || item.schedule_name || 'Betriebsweit'}</small><p>{item.message}</p></div></article>)}{!annotations.length && <p className="sc-empty">Keine aktuellen Hinweise.</p>}</section>
      </main>}

      {tab === 'annotations' && <main className="sc-page two-col">
        {manager && <section className="sc-card"><h3>Annotation anlegen</h3><IonSelect label="Typ" labelPlacement="stacked" fill="outline" value={annotationForm.kind} onIonChange={(event) => setAnnotationForm({...annotationForm,kind:value(event)})}><IonSelectOption value="announcement">Ankündigung</IonSelectOption><IonSelectOption value="business_closed">Betrieb geschlossen</IonSelectOption><IonSelectOption value="block_time_off">Keine Abwesenheit zulassen</IonSelectOption></IonSelect><IonInput label="Titel" labelPlacement="stacked" fill="outline" value={annotationForm.title} onIonInput={(event) => setAnnotationForm({...annotationForm,title:(event.target as HTMLIonInputElement).value||''})}/><IonTextarea label="Nachricht" labelPlacement="stacked" fill="outline" value={annotationForm.message} onIonInput={(event) => setAnnotationForm({...annotationForm,message:(event.target as HTMLIonTextareaElement).value||''})}/><div className="sc-grid"><IonInput type="date" label="Von" labelPlacement="stacked" fill="outline" value={annotationForm.starts_on} onIonInput={(event) => setAnnotationForm({...annotationForm,starts_on:(event.target as HTMLIonInputElement).value||''})}/><IonInput type="date" label="Bis" labelPlacement="stacked" fill="outline" value={annotationForm.ends_on} onIonInput={(event) => setAnnotationForm({...annotationForm,ends_on:(event.target as HTMLIonInputElement).value||''})}/></div><IonSelect label="Dienstplan" labelPlacement="stacked" fill="outline" value={annotationForm.schedule} onIonChange={(event) => setAnnotationForm({...annotationForm,schedule:value(event)})}><IonSelectOption value="">Betriebsweit</IonSelectOption>{schedules.map((item) => <IonSelectOption key={item.id} value={item.id}>{item.name}</IonSelectOption>)}</IonSelect><IonSelect label="Einsatzort" labelPlacement="stacked" fill="outline" value={annotationForm.location} onIonChange={(event) => setAnnotationForm({...annotationForm,location:value(event)})}><IonSelectOption value="">Alle</IonSelectOption>{locations.map((item) => <IonSelectOption key={item.id} value={item.id}>{item.name}</IonSelectOption>)}</IonSelect>{annotationForm.kind === 'business_closed' && <IonSelect label="Vorhandene Schichten" labelPlacement="stacked" fill="outline" value={annotationForm.business_closed_action} onIonChange={(event) => setAnnotationForm({...annotationForm,business_closed_action:value(event)})}><IonSelectOption value="leave">Unverändert lassen</IonSelectOption><IonSelectOption value="unpublish">Unbelegte zurückziehen</IonSelectOption><IonSelectOption value="open">Belegte als OpenShift freigeben</IonSelectOption><IonSelectOption value="delete">Zukünftige löschen</IonSelectOption></IonSelect>}<IonButton disabled={busy} onClick={() => void saveAnnotation()}>Annotation speichern</IonButton></section>}
        <section className="sc-card"><h3>Hinweise im Plan</h3>{annotations.map((item) => <article className={`sc-row annotation ${item.kind}`} key={item.id}><div><b>{item.title}</b><small>{item.starts_on}–{item.ends_on} · {item.location_name || item.schedule_name || 'Betriebsweit'}</small><p>{item.message}</p></div>{manager && <IonButton size="small" fill="clear" color="danger" onClick={() => void archiveAnnotation(item.id)}>Entfernen</IonButton>}</article>)}{!annotations.length && <p className="sc-empty">Keine Annotation vorhanden.</p>}</section>
      </main>}

      {tab === 'tasks' && <main className="sc-page two-col">
        {manager && <div><section className="sc-card"><h3>Task List anlegen</h3><IonInput label="Titel" labelPlacement="stacked" fill="outline" value={taskListForm.title} onIonInput={(event) => setTaskListForm({...taskListForm,title:(event.target as HTMLIonInputElement).value||''})}/><IonInput type="date" label="Datum" labelPlacement="stacked" fill="outline" value={taskListForm.work_date} onIonInput={(event) => setTaskListForm({...taskListForm,work_date:(event.target as HTMLIonInputElement).value||''})}/><IonSelect label="Einsatzort" labelPlacement="stacked" fill="outline" value={taskListForm.location} onIonChange={(event) => setTaskListForm({...taskListForm,location:value(event)})}><IonSelectOption value="">Alle</IonSelectOption>{locations.map((item) => <IonSelectOption key={item.id} value={item.id}>{item.name}</IonSelectOption>)}</IonSelect><IonTextarea label="Hinweis" labelPlacement="stacked" fill="outline" value={taskListForm.notes} onIonInput={(event) => setTaskListForm({...taskListForm,notes:(event.target as HTMLIonTextareaElement).value||''})}/><IonButton onClick={() => void createTaskList()}>Task List speichern</IonButton></section><section className="sc-card"><h3>Aufgabe hinzufügen</h3><IonSelect label="Task List" labelPlacement="stacked" fill="outline" value={taskForm.task_list} onIonChange={(event) => setTaskForm({...taskForm,task_list:value(event)})}>{taskLists.map((item) => <IonSelectOption value={item.id} key={item.id}>{item.work_date} · {item.title}</IonSelectOption>)}</IonSelect><IonInput label="Aufgabe" labelPlacement="stacked" fill="outline" value={taskForm.title} onIonInput={(event) => setTaskForm({...taskForm,title:(event.target as HTMLIonInputElement).value||''})}/><IonSelect label="Position (optional)" labelPlacement="stacked" fill="outline" value={taskForm.position} onIonChange={(event) => setTaskForm({...taskForm,position:value(event)})}><IonSelectOption value="">Alle</IonSelectOption>{positions.map((item) => <IonSelectOption value={item.id} key={item.id}>{item.name}</IonSelectOption>)}</IonSelect><IonSelect label="Mitarbeiter (optional)" labelPlacement="stacked" fill="outline" value={taskForm.assignee} onIonChange={(event) => setTaskForm({...taskForm,assignee:value(event)})}><IonSelectOption value="">Nicht persönlich zuweisen</IonSelectOption>{workers.filter((item) => item.active !== false).map((item) => <IonSelectOption value={item.id} key={item.id}>{item.user_detail?.name || item.user_detail?.email}</IonSelectOption>)}</IonSelect><IonButton onClick={() => void createTask()}>Aufgabe hinzufügen</IonButton></section></div>}
        <section className="sc-card"><h3>Task Lists</h3>{taskLists.map((list) => <article className="task-list" key={list.id}><div className="task-list-head"><div><b>{list.title}</b><small>{list.work_date} · {list.location_name || list.schedule_name || 'Betriebsweit'}</small></div><IonBadge color={list.completed_count === list.task_count && list.task_count ? 'success' : 'medium'}>{list.completed_count}/{list.task_count}</IonBadge></div>{list.notes && <p>{list.notes}</p>}<div className="task-items">{(list.tasks || []).map((task:any) => <label key={task.id}><IonCheckbox checked={!!task.completed_at} disabled={busy} onIonChange={(event) => void completeTask(task, !!event.detail.checked)}/><span className={task.completed_at?'done':''}>{task.title}<small>{task.assignee_name || task.position_name || ''}</small></span></label>)}</div></article>)}{!taskLists.length && <p className="sc-empty">Keine Task Lists.</p>}</section>
      </main>}

      {tab === 'copy' && manager && <main className="sc-page"><section className="sc-card compact"><h3>Tag oder Zeitraum kopieren</h3><p>Der Zielplan wird als Entwurf erzeugt; bestehende Zielschichten werden übersprungen. Besetzungen werden nur kopiert, wenn die aktuellen Regeln weiterhin erfüllt sind.</p><div className="sc-grid three"><IonInput type="date" label="Quelle von" labelPlacement="stacked" fill="outline" value={copyForm.source_start} onIonInput={(event) => setCopyForm({...copyForm,source_start:(event.target as HTMLIonInputElement).value||''})}/><IonInput type="date" label="Quelle bis" labelPlacement="stacked" fill="outline" value={copyForm.source_end} onIonInput={(event) => setCopyForm({...copyForm,source_end:(event.target as HTMLIonInputElement).value||''})}/><IonInput type="date" label="Zielbeginn" labelPlacement="stacked" fill="outline" value={copyForm.target_start} onIonInput={(event) => setCopyForm({...copyForm,target_start:(event.target as HTMLIonInputElement).value||''})}/></div><IonButton onClick={() => void copyRange()}>Zeitraum kopieren</IonButton></section></main>}

      {tab === 'display' && <main className="sc-page two-col"><section className="sc-card"><h3>Farbcodierung</h3><IonSelect label="Schichten einfärben nach" labelPlacement="stacked" fill="outline" value={display.color_mode} onIonChange={(event) => void saveDisplay({color_mode:value(event)})}><IonSelectOption value="shift">Schichtfarbe</IonSelectOption><IonSelectOption value="position">Position</IonSelectOption><IonSelectOption value="location">Einsatzort / Job Site</IonSelectOption></IonSelect>{manager && <><IonSelect label="Farbziel" labelPlacement="stacked" fill="outline" value={colorForm.target_type} onIonChange={(event) => setColorForm({...colorForm,target_type:value(event),target_id:''})}><IonSelectOption value="shift">Einzelne Schicht</IonSelectOption><IonSelectOption value="position">Position</IonSelectOption><IonSelectOption value="location">Einsatzort / Job Site</IonSelectOption></IonSelect><IonSelect label="Element" labelPlacement="stacked" fill="outline" value={colorForm.target_id} onIonChange={(event) => setColorForm({...colorForm,target_id:value(event)})}>{activeTargetOptions.map((item) => <IonSelectOption key={item.id} value={item.id}>{item.name}</IonSelectOption>)}</IonSelect><div className="sc-color-row"><input type="color" value={colorForm.color} onChange={(event) => setColorForm({...colorForm,color:event.target.value})}/><IonInput fill="outline" label="HEX" labelPlacement="floating" value={colorForm.color} onIonInput={(event) => setColorForm({...colorForm,color:String((event.target as HTMLIonInputElement).value||'')})}/><IonButton onClick={() => void saveColor()}>Farbe speichern</IonButton></div></>}</section><section className="sc-card"><h3>Zeitzone</h3><IonSelect label="Zeiten anzeigen in" labelPlacement="stacked" fill="outline" value={display.timezone_mode} onIonChange={(event) => void saveDisplay({timezone_mode:value(event)})}><IonSelectOption value="workplace">Betriebszeitzone</IonSelectOption><IonSelectOption value="schedule">Zeitzone des Einsatzorts</IonSelectOption><IonSelectOption value="local">Lokale Zeitzone</IonSelectOption></IonSelect><IonInput label="Lokale IANA-Zeitzone" labelPlacement="stacked" fill="outline" value={display.local_timezone} onIonInput={(event) => onDisplayChange({...display,local_timezone:String((event.target as HTMLIonInputElement).value||'')})}/><IonButton fill="outline" onClick={() => void saveDisplay({local_timezone:display.local_timezone})}>Lokale Zeitzone speichern</IonButton><p className="sc-hint">Betrieb: {display.workplace_timezone || 'Europe/Berlin'} · Beispiel lokale Zone: Europe/Berlin, America/New_York.</p></section></main>}

      {tab === 'settings' && manager && <main className="sc-page"><section className="sc-card compact"><h3>Premium Scheduler Regeln</h3><label className="sc-toggle"><div><b>Überlappende OpenShifts erlauben</b><small>Nur bei Selbstübernahme durch Mitarbeiter. Manuelle Disposition, Auto-Assign und Tausch bleiben streng.</small></div><IonToggle checked={!!settings.allow_overlapping_open_shifts} onIonChange={(event) => void saveSettings({allow_overlapping_open_shifts:event.detail.checked})}/></label><label className="sc-toggle"><div><b>Schichtbestätigung verlangen</b><small>Neu veröffentlichte, zugewiesene Schichten erscheinen beim Mitarbeiter als „Bestätigen“.</small></div><IonToggle checked={!!settings.require_shift_confirmation} onIonChange={(event) => void saveSettings({require_shift_confirmation:event.detail.checked})}/></label></section></main>}
    </div>
  </IonModal>;
}
