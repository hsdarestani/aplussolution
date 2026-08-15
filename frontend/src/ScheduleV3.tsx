import React, { useEffect, useMemo, useState } from 'react';
import {
  IonAlert,
  IonBadge,
  IonButton,
  IonIcon,
  IonInput,
  IonLabel,
  IonModal,
  IonSearchbar,
  IonSegment,
  IonSegmentButton,
  IonSelect,
  IonSelectOption,
  IonSpinner,
  IonTextarea,
  IonToast,
  IonToggle,
} from '@ionic/react';
import {
  addOutline,
  analyticsOutline,
  checkmarkCircleOutline,
  chevronBackOutline,
  chevronForwardOutline,
  downloadOutline,
  locationOutline,
  optionsOutline,
  peopleOutline,
  printOutline,
  refreshOutline,
  timeOutline,
} from 'ionicons/icons';
import { api, apiAll, apiDownload, User } from './api';
import ForecastToolsPanel from './ForecastToolsPanel';
import SchedulerAdminPanel from './SchedulerAdminPanel';
import SchedulerCalendar, { CalendarMode, moveAnchor, rangeLabel } from './SchedulerCalendar';
import SchedulerGroupedGrid from './SchedulerGroupedGrid';
import './schedule-v2.css';

const val = (event: any) => event.detail.value ?? '';
const isManager = (user: User) => ['admin', 'manager'].includes(user.role);
const tm = (input: string) => new Date(input).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
const dateKey = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
type DisplayMode = 'list' | CalendarMode;
type ViewBy = 'coverage' | 'positions' | 'users';

function viewBounds(mode: DisplayMode, anchor: Date) {
  const start = new Date(anchor);
  start.setHours(0, 0, 0, 0);
  if (mode === 'day') return [start, new Date(start.getTime() + 86400000)];
  if (mode === 'week' || mode === 'twoWeeks') {
    const weekday = (start.getDay() + 6) % 7;
    start.setDate(start.getDate() - weekday);
    const end = new Date(start);
    end.setDate(end.getDate() + (mode === 'week' ? 7 : 14));
    return [start, end];
  }
  if (mode === 'month') return [new Date(anchor.getFullYear(), anchor.getMonth(), 1), new Date(anchor.getFullYear(), anchor.getMonth() + 1, 1)];
  const first = new Date(anchor);
  first.setDate(first.getDate() - 30);
  const last = new Date(anchor);
  last.setDate(last.getDate() + 60);
  return [first, last];
}

export default function ScheduleV3({ user }: { user: User }) {
  const manager = isManager(user);
  const workerView = user.role === 'worker';
  const clientView = user.role === 'client';
  const [rows, setRows] = useState<any[]>([]);
  const [workers, setWorkers] = useState<any[]>([]);
  const [clients, setClients] = useState<any[]>([]);
  const [locations, setLocations] = useState<any[]>([]);
  const [positions, setPositions] = useState<any[]>([]);
  const [orders, setOrders] = useState<any[]>([]);
  const [tags, setTags] = useState<any[]>([]);
  const [tab, setTab] = useState(workerView ? 'available' : 'open');
  const [search, setSearch] = useState('');
  const [modal, setModal] = useState(false);
  const [editing, setEditing] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState('');
  const [form, setForm] = useState<any>({ required_count: 1, break_minutes: 0, publish_now: true });
  const [releaseTarget, setReleaseTarget] = useState<any>();
  const [adminOpen, setAdminOpen] = useState(false);
  const [forecastOpen, setForecastOpen] = useState(false);
  const [eligibility, setEligibility] = useState<any>();
  const [eligibilityTarget, setEligibilityTarget] = useState<any>();
  const [displayMode, setDisplayMode] = useState<DisplayMode>('week');
  const [viewBy, setViewBy] = useState<ViewBy>('coverage');
  const [anchor, setAnchor] = useState(new Date());
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [filterPosition, setFilterPosition] = useState('');
  const [filterLocation, setFilterLocation] = useState('');
  const [filterWorker, setFilterWorker] = useState('');
  const [filterTag, setFilterTag] = useState('');

  async function load() {
    if (workerView) {
      const endpoint = tab === 'mine' ? 'shifts/mine/' : 'shifts/available/';
      setRows(await apiAll(`${endpoint}?ordering=starts_at`));
      return;
    }
    if (clientView) {
      setRows(await apiAll('shifts/?ordering=starts_at'));
      return;
    }
    const [shiftRows, workerRows, clientRows, locationRows, positionRows, orderRows, tagRows] = await Promise.all([
      apiAll('shifts/?ordering=starts_at'),
      apiAll('workers/'),
      apiAll('clients/'),
      apiAll('locations/'),
      apiAll('positions/'),
      apiAll('orders/'),
      apiAll('skill-tags/'),
    ]);
    setRows(shiftRows);
    setWorkers(workerRows);
    setClients(clientRows);
    setLocations(locationRows);
    setPositions(positionRows);
    setOrders(orderRows);
    setTags(tagRows);
  }

  useEffect(() => { void load(); }, [tab]);

  const visible = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase('de');
    return rows.filter((row: any) => {
      if (manager) {
        if (tab === 'draft' && row.status !== 'draft') return false;
        if (tab === 'filled' && (row.status === 'draft' || Number(row.open_count || 0) !== 0)) return false;
        if (tab === 'open' && (row.status === 'draft' || Number(row.open_count || 0) <= 0)) return false;
      }
      if (filterPosition && String(row.position) !== filterPosition) return false;
      if (filterLocation && String(row.location) !== filterLocation) return false;
      if (filterWorker && !(row.assignments || []).some((item: any) => String(item.worker) === filterWorker)) return false;
      if (filterTag && !(row.required_tags || []).some((item: any) => String(item.id) === filterTag)) return false;
      if (needle) {
        const haystack = [
          row.client_name, row.location_name, row.position_name, row.order_title, row.notes,
          ...(row.assignments || []).map((item: any) => item.worker_name),
          ...(row.required_tags || []).map((item: any) => item.name),
        ].filter(Boolean).join(' ').toLocaleLowerCase('de');
        if (!haystack.includes(needle)) return false;
      }
      return true;
    });
  }, [rows, manager, tab, filterPosition, filterLocation, filterWorker, filterTag, search]);

  async function act(path: string, message: string, body: any = {}) {
    setBusy(true);
    try {
      await api(path, { method: 'POST', body: JSON.stringify(body) });
      setToast(message);
      await load();
    } catch (error: any) {
      setToast(error.message);
    } finally {
      setBusy(false);
    }
  }

  function create() {
    setEditing(undefined);
    setForm({ required_count: 1, break_minutes: 0, publish_now: true });
    setModal(true);
  }

  function edit(row: any) {
    setEditing(row.id);
    setForm({
      ...row,
      starts_at: row.starts_at?.slice(0, 16),
      ends_at: row.ends_at?.slice(0, 16),
      publish_now: row.status !== 'draft',
    });
    setModal(true);
  }

  async function save() {
    setBusy(true);
    try {
      const payload: any = {
        client: form.client,
        location: form.location,
        position: form.position,
        order: form.order || null,
        starts_at: form.starts_at,
        ends_at: form.ends_at,
        break_minutes: Number(form.break_minutes || 0),
        required_count: Number(form.required_count || 1),
        notes: form.notes || '',
        status: form.publish_now ? 'published' : 'draft',
      };
      await api(editing ? `shifts/${editing}/` : 'shifts/', { method: editing ? 'PATCH' : 'POST', body: JSON.stringify(payload) });
      setModal(false);
      setToast('Personalbedarf gespeichert.');
      await load();
    } catch (error: any) {
      setToast(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function inspectEligibility(shift: any) {
    setEligibilityTarget(shift);
    setEligibility(undefined);
    try {
      setEligibility(await api(`scheduling/eligibility/?shift=${shift.id}`));
    } catch (error: any) {
      setToast(error.message);
      setEligibilityTarget(undefined);
    }
  }

  async function autoAssign(shift: any) {
    await act('scheduling/auto-assign/', 'Auto-Assign abgeschlossen.', { shift: shift.id });
    if (eligibilityTarget?.id === shift.id) void inspectEligibility(shift);
  }

  async function assignWorker(workerId: string) {
    if (!eligibilityTarget) return;
    await act('scheduling/assign/', 'Mitarbeiter eingeplant.', { shift: eligibilityTarget.id, worker: workerId });
    void inspectEligibility(eligibilityTarget);
  }

  async function moveShift(shift: any, targetDay: Date) {
    const sourceStart = new Date(shift.starts_at);
    const sourceEnd = new Date(shift.ends_at);
    const duration = sourceEnd.getTime() - sourceStart.getTime();
    const targetStart = new Date(targetDay);
    targetStart.setHours(sourceStart.getHours(), sourceStart.getMinutes(), sourceStart.getSeconds(), 0);
    const targetEnd = new Date(targetStart.getTime() + duration);
    setBusy(true);
    try {
      await api(`shifts/${shift.id}/`, { method: 'PATCH', body: JSON.stringify({ starts_at: targetStart.toISOString(), ends_at: targetEnd.toISOString() }) });
      setToast('Schicht verschoben und Planungsregeln erneut geprüft.');
      await load();
    } catch (error: any) {
      setToast(error.message);
    } finally {
      setBusy(false);
    }
  }

  function toggleSelect(id: string) {
    setSelected((current) => {
      const next = new Set(current);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  async function bulk(action: 'publish' | 'unpublish' | 'cancel' | 'delete_drafts') {
    if (!selected.size) return;
    if ((action === 'cancel' || action === 'delete_drafts') && !window.confirm(`${selected.size} Schicht(en) wirklich bearbeiten?`)) return;
    setBusy(true);
    try {
      const result: any = await api('scheduling/bulk-action/', { method: 'POST', body: JSON.stringify({ ids: [...selected], action }) });
      setToast(`${result.changed} Schicht(en) aktualisiert${result.skipped?.length ? `, ${result.skipped.length} übersprungen` : ''}.`);
      setSelected(new Set());
      await load();
    } catch (error: any) {
      setToast(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function copyWeek() {
    const target = window.prompt('Zielwoche (JJJJ-MM-TT)', dateKey(new Date(anchor.getFullYear(), anchor.getMonth(), anchor.getDate() + 7)));
    if (!target) return;
    await act('operations/copy-week/', 'Woche wurde als Entwurf kopiert.', { source_start: dateKey(anchor), target_start: target });
  }

  async function clearVisible() {
    const [start, end] = viewBounds(displayMode, anchor);
    if (!window.confirm('Unbelegte Entwürfe im sichtbaren Zeitraum wirklich löschen?')) return;
    await act('scheduling/clear-range/', 'Entwürfe im Zeitraum wurden entfernt.', { starts_at: start.toISOString(), ends_at: end.toISOString(), location: filterLocation || undefined });
  }

  async function exportVisible() {
    const [start, end] = viewBounds(displayMode, anchor);
    const dateTo = new Date(end);
    dateTo.setDate(dateTo.getDate() - 1);
    try {
      await apiDownload(`reports/schedule.csv?date_from=${dateKey(start)}&date_to=${dateKey(dateTo)}`, 'dienstplan.csv');
    } catch (error: any) {
      setToast(error.message);
    }
  }

  const eyebrow = workerView ? 'MEINE ARBEIT' : clientView ? 'KUNDENPORTAL' : 'PERSONALPLANUNG';
  const title = workerView ? 'Schichten' : clientView ? 'Einsätze' : 'Personalbedarf & Schichten';
  const intro = workerView
    ? 'Freie Einsätze finden und eigene Schichten verwalten.'
    : clientView
      ? 'Geplante Einsätze und aktueller Besetzungsstatus für Ihre Aufträge.'
      : 'Kundenbedarf planen, Regeln prüfen, qualifiziert besetzen und als OpenShift veröffentlichen.';
  const calendarMode: CalendarMode = displayMode === 'list' ? 'week' : displayMode;

  return <div className="sv2">
    <div className="sv2-title">
      <div><small>{eyebrow}</small><h1>{title}</h1><p>{intro}</p></div>
      {manager && <div className="sv2-title-actions">
        <IonButton fill="outline" onClick={() => setForecastOpen(true)}><IonIcon slot="start" icon={analyticsOutline}/>Forecast Tools</IonButton>
        <IonButton fill="outline" onClick={() => setAdminOpen(true)}><IonIcon slot="start" icon={optionsOutline}/>Regeln & Qualifikationen</IonButton>
        <IonButton onClick={create}><IonIcon slot="start" icon={addOutline}/>Personalbedarf</IonButton>
      </div>}
    </div>

    <div className="sv2-search">
      <IonSearchbar value={search} debounce={250} placeholder="Kunde, Ort, Position, Mitarbeiter, Tag oder Auftrag suchen …" onIonInput={(event) => setSearch(String(val(event)))}/>
      <IonButton fill="outline" onClick={() => void load()}><IonIcon slot="icon-only" icon={refreshOutline}/></IonButton>
    </div>

    {workerView ? <IonSegment scrollable value={tab} onIonChange={(event) => setTab(String(val(event)))}>
      <IonSegmentButton value="available"><IonLabel>Verfügbare Schichten</IonLabel></IonSegmentButton>
      <IonSegmentButton value="mine"><IonLabel>Meine Schichten</IonLabel></IonSegmentButton>
    </IonSegment> : manager ? <IonSegment scrollable value={tab} onIonChange={(event) => setTab(String(val(event)))}>
      <IonSegmentButton value="open"><IonLabel>Offen</IonLabel></IonSegmentButton>
      <IonSegmentButton value="filled"><IonLabel>Voll besetzt</IonLabel></IonSegmentButton>
      <IonSegmentButton value="draft"><IonLabel>Entwürfe</IonLabel></IonSegmentButton>
      <IonSegmentButton value="all"><IonLabel>Alle</IonLabel></IonSegmentButton>
    </IonSegment> : null}

    {manager && <div className="scheduler-toolbar">
      <div className="scheduler-toolbar-row">
        <div className="scheduler-view-switch">
          {([['list','Liste'],['day','Tag'],['week','Woche'],['twoWeeks','2 Wochen'],['month','Monat']] as [DisplayMode,string][]).map(([mode,label]) => <button className={displayMode===mode?'active':''} key={mode} onClick={() => setDisplayMode(mode)}>{label}</button>)}
        </div>
        {displayMode !== 'list' && <div className="scheduler-view-switch scheduler-group-switch">
          {([['coverage','Coverage'],['positions','Positionen'],['users','Mitarbeiter']] as [ViewBy,string][]).map(([mode,label]) => <button className={viewBy===mode?'active':''} key={mode} onClick={() => setViewBy(mode)}>{label}</button>)}
        </div>}
      </div>
      <div className="scheduler-filter-grid">
        <IonSelect fill="outline" label="Position" labelPlacement="floating" value={filterPosition} onIonChange={(event) => setFilterPosition(String(val(event)||''))}><IonSelectOption value="">Alle Positionen</IonSelectOption>{positions.map((item) => <IonSelectOption key={item.id} value={item.id}>{item.name}</IonSelectOption>)}</IonSelect>
        <IonSelect fill="outline" label="Einsatzort" labelPlacement="floating" value={filterLocation} onIonChange={(event) => setFilterLocation(String(val(event)||''))}><IonSelectOption value="">Alle Einsatzorte</IonSelectOption>{locations.map((item) => <IonSelectOption key={item.id} value={item.id}>{item.name}</IonSelectOption>)}</IonSelect>
        <IonSelect fill="outline" label="Mitarbeiter" labelPlacement="floating" value={filterWorker} onIonChange={(event) => setFilterWorker(String(val(event)||''))}><IonSelectOption value="">Alle Mitarbeiter</IonSelectOption>{workers.filter((item) => item.active !== false).map((item) => <IonSelectOption key={item.id} value={item.id}>{item.user_detail?.name || item.user_detail?.email}</IonSelectOption>)}</IonSelect>
        <IonSelect fill="outline" label="Tag / Qualifikation" labelPlacement="floating" value={filterTag} onIonChange={(event) => setFilterTag(String(val(event)||''))}><IonSelectOption value="">Alle Tags</IonSelectOption>{tags.map((item) => <IonSelectOption key={item.id} value={item.id}>{item.name}</IonSelectOption>)}</IonSelect>
        {(filterPosition || filterLocation || filterWorker || filterTag) && <IonButton fill="clear" onClick={() => { setFilterPosition(''); setFilterLocation(''); setFilterWorker(''); setFilterTag(''); }}>Filter zurücksetzen</IonButton>}
      </div>
      {displayMode !== 'list' && <div className="scheduler-period">
        <IonButton fill="clear" size="small" onClick={() => setAnchor(moveAnchor(calendarMode, anchor, -1))}><IonIcon icon={chevronBackOutline}/></IonButton>
        <button onClick={() => setAnchor(new Date())}>Heute</button>
        <b>{rangeLabel(calendarMode, anchor)}</b>
        <IonButton fill="clear" size="small" onClick={() => setAnchor(moveAnchor(calendarMode, anchor, 1))}><IonIcon icon={chevronForwardOutline}/></IonButton>
      </div>}
      <div className="scheduler-tool-actions">
        <IonButton size="small" fill="outline" onClick={() => void copyWeek()}>Woche kopieren</IonButton>
        <IonButton size="small" fill="outline" onClick={() => void exportVisible()}><IonIcon slot="start" icon={downloadOutline}/>Export</IonButton>
        <IonButton size="small" fill="outline" onClick={() => window.print()}><IonIcon slot="start" icon={printOutline}/>Drucken</IonButton>
        {displayMode !== 'list' && <IonButton size="small" fill="clear" color="danger" onClick={() => void clearVisible()}>Entwürfe leeren</IonButton>}
      </div>
      {!!selected.size && <div className="scheduler-bulk">
        <b>{selected.size} ausgewählt</b>
        <IonButton size="small" onClick={() => void bulk('publish')}>Veröffentlichen</IonButton>
        <IonButton size="small" fill="outline" onClick={() => void bulk('unpublish')}>Zurückziehen</IonButton>
        <IonButton size="small" fill="outline" color="danger" onClick={() => void bulk('cancel')}>Stornieren</IonButton>
        <IonButton size="small" fill="clear" color="danger" onClick={() => void bulk('delete_drafts')}>Entwürfe löschen</IonButton>
        <IonButton size="small" fill="clear" onClick={() => setSelected(new Set())}>Auswahl aufheben</IonButton>
      </div>}
    </div>}

    {manager && displayMode !== 'list'
      ? viewBy === 'coverage'
        ? <SchedulerCalendar rows={visible} mode={calendarMode} anchor={anchor} onMove={moveShift} onInspect={inspectEligibility} selected={selected} onToggleSelect={toggleSelect}/>
        : <SchedulerGroupedGrid rows={visible} mode={calendarMode} anchor={anchor} groupBy={viewBy} onMove={moveShift} onInspect={inspectEligibility} selected={selected} onToggleSelect={toggleSelect}/>
      : <div className="sv2-list">{visible.map((row: any) => {
        const mine = workerView && tab === 'mine';
        return <article className={`sv2-card ${mine?'mine':''} ${selected.has(row.id)?'selected':''}`} key={row.id}>
          {manager && <button className="sv2-select" onClick={() => toggleSelect(row.id)} aria-label="Auswählen">{selected.has(row.id)?'✓':'○'}</button>}
          <div className="sv2-date"><b>{new Date(row.starts_at).getDate()}</b><span>{new Date(row.starts_at).toLocaleString('de-DE',{month:'short'})}</span></div>
          <div className="sv2-body">
            <small>{row.client_name}</small><h3>{row.position_name}</h3>
            <p><IonIcon icon={timeOutline}/> {tm(row.starts_at)}–{tm(row.ends_at)} · {row.break_minutes||0} Min.</p>
            <p><IonIcon icon={locationOutline}/> {row.location_name}</p>
            {manager && row.assignments?.length ? <p><IonIcon icon={peopleOutline}/> {row.assignments.map((item:any) => item.worker_name).join(', ')}</p> : null}
            {!!row.required_tags?.length && <div className="sv2-tags">{row.required_tags.map((item:any) => <IonBadge key={item.id} color="medium">{item.name}</IonBadge>)}</div>}
            <div className="sv2-meter"><span style={{width:`${Math.min(100,(Number(row.filled_count||0)/Number(row.required_count||1))*100)}%`}}/></div>
            <em>{row.filled_count||0}/{row.required_count||1} besetzt · {row.open_count||0} frei</em>
          </div>
          <div className="sv2-side">
            <IonBadge color={row.status==='draft'?'medium':row.open_count>0?'primary':'success'}>{row.status==='draft'?'Entwurf':row.open_count>0?'Offen':'Voll'}</IonBadge>
            {workerView && !mine && row.open_count>0 && <IonButton disabled={busy} onClick={() => void act(`shifts/${row.id}/claim/`,'Schicht übernommen.')}><IonIcon slot="start" icon={checkmarkCircleOutline}/>Übernehmen</IonButton>}
            {workerView && mine && <IonButton fill="outline" color="medium" disabled={busy} onClick={() => setReleaseTarget(row)}>Freigeben</IonButton>}
            {manager && row.status==='draft' && <IonButton size="small" onClick={() => void act(`shifts/${row.id}/publish/`,'OpenShift veröffentlicht.')}>Veröffentlichen</IonButton>}
            {manager && row.status==='published' && Number(row.filled_count||0)===0 && <IonButton size="small" fill="outline" onClick={() => void act(`shifts/${row.id}/unpublish/`,'Schicht zurück in Entwurf gesetzt.')}>Zurückziehen</IonButton>}
            {manager && row.status!=='draft' && Number(row.open_count||0)>0 && <><IonButton size="small" disabled={busy} onClick={() => void autoAssign(row)}><IonIcon slot="start" icon={peopleOutline}/>Auto-Assign</IonButton><IonButton size="small" fill="outline" onClick={() => void inspectEligibility(row)}>Besetzung prüfen</IonButton></>}
            {manager && <IonButton size="small" fill="clear" onClick={() => edit(row)}>Bearbeiten</IonButton>}
          </div>
        </article>;
      })}{!visible.length && <div className="sv2-empty"><h3>Keine passenden Einsätze</h3><p>Suche oder Filter ändern.</p></div>}</div>}

    <IonModal isOpen={modal} onDidDismiss={() => setModal(false)}><div className="sv2-modal">
      <div className="sv2-modal-head"><h2>{editing?'Personalbedarf bearbeiten':'Personalbedarf anlegen'}</h2><IonButton fill="clear" onClick={() => setModal(false)}>Schließen</IonButton></div>
      <div className="sv2-form">
        <IonSelect fill="outline" label="Kunde *" labelPlacement="floating" value={form.client} onIonChange={(event) => setForm({...form,client:val(event)})}>{clients.map((item) => <IonSelectOption key={item.id} value={item.id}>{item.name}</IonSelectOption>)}</IonSelect>
        <IonSelect fill="outline" label="Auftrag" labelPlacement="floating" value={form.order} onIonChange={(event) => setForm({...form,order:val(event)})}><IonSelectOption value="">Ohne Auftrag</IonSelectOption>{orders.filter((item) => !form.client || item.client === form.client).map((item) => <IonSelectOption key={item.id} value={item.id}>{item.title}</IonSelectOption>)}</IonSelect>
        <IonSelect fill="outline" label="Einsatzort *" labelPlacement="floating" value={form.location} onIonChange={(event) => setForm({...form,location:val(event)})}>{locations.filter((item) => !form.client || !item.client || item.client === form.client).map((item) => <IonSelectOption key={item.id} value={item.id}>{item.name}</IonSelectOption>)}</IonSelect>
        <IonSelect fill="outline" label="Position *" labelPlacement="floating" value={form.position} onIonChange={(event) => setForm({...form,position:val(event)})}>{positions.map((item) => <IonSelectOption key={item.id} value={item.id}>{item.name}</IonSelectOption>)}</IonSelect>
        <IonInput fill="outline" type="datetime-local" label="Beginn *" labelPlacement="floating" value={form.starts_at} onIonInput={(event) => setForm({...form,starts_at:val(event)})}/>
        <IonInput fill="outline" type="datetime-local" label="Ende *" labelPlacement="floating" value={form.ends_at} onIonInput={(event) => setForm({...form,ends_at:val(event)})}/>
        <IonInput fill="outline" type="number" min="1" label="Benötigte Mitarbeiter *" labelPlacement="floating" value={form.required_count} onIonInput={(event) => setForm({...form,required_count:val(event)})}/>
        <IonInput fill="outline" type="number" min="0" label="Pause (Min.)" labelPlacement="floating" value={form.break_minutes} onIonInput={(event) => setForm({...form,break_minutes:val(event)})}/>
        <IonTextarea className="full" fill="outline" label="Hinweise für Mitarbeiter" labelPlacement="floating" value={form.notes} onIonInput={(event) => setForm({...form,notes:val(event)})}/>
        <label className="sv2-toggle full">Direkt als OpenShift veröffentlichen <IonToggle checked={!!form.publish_now} onIonChange={(event) => setForm({...form,publish_now:event.detail.checked})}/></label>
      </div>
      <div className="sv2-modal-actions"><IonButton fill="outline" onClick={() => setModal(false)}>Abbrechen</IonButton><IonButton disabled={busy} onClick={() => void save()}>Speichern</IonButton></div>
    </div></IonModal>

    <IonModal isOpen={!!eligibilityTarget} onDidDismiss={() => {setEligibilityTarget(undefined);setEligibility(undefined);}}><div className="sv2-modal eligibility-modal">
      <div className="sv2-modal-head"><div><small>BESCHÄFTIGUNGSREGELN</small><h2>Besetzung prüfen</h2><p>{eligibilityTarget?.position_name} · {eligibilityTarget?.location_name}</p></div><IonButton fill="clear" onClick={() => {setEligibilityTarget(undefined);setEligibility(undefined);}}>Schließen</IonButton></div>
      {!eligibility ? <div className="eligibility-loading"><IonSpinner/><p>Qualifikationen und Planungsregeln werden geprüft …</p></div> : <>
        <div className="eligibility-summary"><span>Regelwerk <b>{eligibility.policy?.name}</b></span><span><b>{eligibility.eligible_count}</b> Mitarbeiter einplanbar</span>{Number(eligibilityTarget?.open_count||0)>0 && <IonButton disabled={busy} onClick={() => void autoAssign(eligibilityTarget)}>Offene Plätze automatisch besetzen</IonButton>}</div>
        <div className="eligibility-list">{eligibility.workers?.map((row:any) => <article key={row.worker} className={row.eligible?'eligible':'blocked'}><div><b>{row.worker_name}</b><small>Score {row.score} · projiziert {Math.round((row.projected_week_minutes||0)/60*10)/10} Std./Woche</small></div><IonBadge color={row.eligible?'success':'danger'}>{row.eligible?'Einplanbar':'Blockiert'}</IonBadge><div className="eligibility-issues">{row.blockers?.map((issue:any) => <p className="block" key={issue.code+issue.message}>● {issue.message}</p>)}{row.warnings?.map((issue:any) => <p className="warn" key={issue.code+issue.message}>△ {issue.message}</p>)}</div>{row.eligible && Number(eligibilityTarget?.open_count||0)>0 && <IonButton size="small" fill="outline" disabled={busy} onClick={() => void assignWorker(row.worker)}>Manuell einplanen</IonButton>}</article>)}</div>
      </>}
    </div></IonModal>

    {manager && <><ForecastToolsPanel open={forecastOpen} onClose={() => setForecastOpen(false)} positions={positions}/><SchedulerAdminPanel open={adminOpen} onClose={() => setAdminOpen(false)} workers={workers} clients={clients} locations={locations} positions={positions}/></>}
    <IonAlert isOpen={!!releaseTarget} onDidDismiss={() => setReleaseTarget(undefined)} header="Schicht freigeben?" message={releaseTarget?`${releaseTarget.position_name || 'Diese Schicht'} wird wieder für andere Mitarbeiter verfügbar.`:''} buttons={[{text:'Abbrechen',role:'cancel'},{text:'Freigeben',role:'destructive',handler:() => {const id=releaseTarget?.id;setReleaseTarget(undefined);if(id)void act(`shifts/${id}/release/`,'Schicht freigegeben.');}}]}/>
    <IonToast isOpen={!!toast} message={toast} duration={3500} onDidDismiss={() => setToast('')}/>
  </div>;
}
