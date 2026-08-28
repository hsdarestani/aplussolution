import React, { useEffect, useMemo, useState } from 'react';
import { IonIcon } from '@ionic/react';
import {
  addOutline,
  briefcaseOutline,
  calendarOutline,
  chevronBackOutline,
  createOutline,
  informationCircleOutline,
  locationOutline,
  personOutline,
  timeOutline,
  trashOutline,
} from 'ionicons/icons';
import { api } from './api';
import './phase8-mobile-attendance-flow.css';

const TZ = 'Europe/Berlin';
const fmtMonth = (date: Date) => new Intl.DateTimeFormat('de-DE', { month: 'long', timeZone: TZ }).format(date);
const fmtMonthShort = (date: Date) => new Intl.DateTimeFormat('de-DE', { month: 'short', timeZone: TZ }).format(date).replace('.', '');
const fmtDate = (value: string) => new Date(value).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: TZ });
const fmtDay = (value: string) => new Date(value).toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: 'short', timeZone: TZ });
const fmtTime = (value: string) => new Date(value).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', timeZone: TZ });

function firstOfMonth(date: Date) { return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1, 12)); }
function monthStart(offset: number, from = firstOfMonth(new Date())) { return new Date(Date.UTC(from.getUTCFullYear(), from.getUTCMonth() + offset, 1, 12)); }
function key(date: Date) { return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}`; }
function label(start: Date, end: Date) { return `1. ${fmtMonth(start)} – 1. ${fmtMonth(end)} ${end.getUTCFullYear()}`; }
function shortLabel(start: Date, end: Date) { return `${start.getUTCDate()}. ${fmtMonthShort(start)} – ${end.getUTCDate()}. ${fmtMonthShort(end)} ${end.getUTCFullYear()}`; }
function monthDistance(newer: Date, older: Date) { return (newer.getUTCFullYear() - older.getUTCFullYear()) * 12 + (newer.getUTCMonth() - older.getUTCMonth()); }
function entryMinutes(entry: any) {
  if (Number.isFinite(Number(entry?.worked_minutes))) return Math.max(0, Number(entry.worked_minutes));
  if (!entry?.clock_in || !entry?.clock_out) return 0;
  return Math.max(0, Math.round((new Date(entry.clock_out).getTime() - new Date(entry.clock_in).getTime()) / 60000));
}
function hoursNumber(minutes: number) { return (minutes / 60).toFixed(2); }
function workerId(entry: any) { return String(entry?.worker || ''); }
function workerName(entry: any) { return String(entry?.worker_name || 'Mitarbeiter'); }
function initials(name: string) { return name.trim().split(/\s+/).slice(0, 2).map((part) => part[0] || '').join('').toUpperCase() || 'MA'; }
function inputDateTime(value?: string) {
  if (!value) return '';
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: TZ,
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(new Date(value));
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)?.value || '';
  return `${part('year')}-${part('month')}-${part('day')}T${part('hour')}:${part('minute')}`;
}
function addInputMinutes(value: string, minutes: number) {
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/);
  if (!match) return value;
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]), Number(match[4]), Number(match[5]) + minutes));
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}-${String(date.getUTCDate()).padStart(2, '0')}T${String(date.getUTCHours()).padStart(2, '0')}:${String(date.getUTCMinutes()).padStart(2, '0')}`;
}
function defaultInput(period?: { start: Date; end: Date }) {
  const now = new Date();
  const candidate = period && (now < period.start || now >= period.end) ? new Date(period.start.getTime() + 10 * 60 * 60 * 1000) : now;
  const rounded = new Date(candidate);
  rounded.setMinutes(Math.floor(rounded.getMinutes() / 15) * 15, 0, 0);
  return inputDateTime(rounded.toISOString());
}
function dayKey(value: string) {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date(value));
  const values = Object.fromEntries(parts.filter((part) => part.type !== 'literal').map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}
function unpack(payload: any) { return Array.isArray(payload) ? payload : payload?.results || []; }

async function fetchWorkers() {
  const rows: any[] = [];
  for (let page = 1; page <= 20; page += 1) {
    const payload: any = await api(`workers/?ordering=user__last_name&page=${page}`);
    rows.push(...unpack(payload));
    if (Array.isArray(payload) || !payload?.next) break;
  }
  return rows;
}

type EditForm = {
  mode: 'create' | 'edit';
  id?: string;
  worker: string;
  clock_in: string;
  clock_out: string;
  edit_reason: string;
};

export default function Phase8MobileAttendance({ data, showWorker = false }: { data: any; showWorker?: boolean }) {
  const [history, setHistory] = useState<any[]>(() => Array.isArray(data.history) ? data.history : []);
  const [workers, setWorkers] = useState<any[]>([]);
  const [selected, setSelected] = useState<string>();
  const [selectedWorker, setSelectedWorker] = useState<string>();
  const [selectedEntry, setSelectedEntry] = useState<any>();
  const [shiftDetail, setShiftDetail] = useState<any>();
  const [form, setForm] = useState<EditForm>();
  const [historyOpen, setHistoryOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    document.body.classList.add('wiw-attendance-active');
    return () => {
      document.body.classList.remove('wiw-attendance-active');
      document.body.classList.remove('wiw-attendance-drilldown');
    };
  }, []);

  useEffect(() => {
    setHistory(Array.isArray(data.history) ? data.history : []);
  }, [data.history]);

  useEffect(() => {
    if (!showWorker) return;
    let cancelled = false;
    void fetchWorkers().then((rows) => { if (!cancelled) setWorkers(rows); }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [showWorker]);

  useEffect(() => {
    document.body.classList.toggle('wiw-attendance-drilldown', Boolean(selected));
    return () => document.body.classList.remove('wiw-attendance-drilldown');
  }, [selected]);

  useEffect(() => {
    setShiftDetail(undefined);
    setHistoryOpen(false);
    if (!selectedEntry?.shift) return;
    let cancelled = false;
    void api(`shifts/${selectedEntry.shift}/`).then((detail) => { if (!cancelled) setShiftDetail(detail); }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [selectedEntry?.id]);

  const workerMap = useMemo(() => new Map(workers.map((worker: any) => [String(worker.id), worker])), [workers]);
  const periods = useMemo(() => {
    const current = firstOfMonth(new Date());
    const valid = history.map((entry: any) => entry?.clock_in ? new Date(entry.clock_in) : undefined).filter((entry: any) => entry && !Number.isNaN(entry.getTime())) as Date[];
    const earliest = valid.length ? firstOfMonth(new Date(Math.min(...valid.map((item) => item.getTime())))) : monthStart(-12, current);
    const count = Math.max(1, monthDistance(current, earliest) + 1);
    return Array.from({ length: count }, (_, index) => {
      const start = monthStart(-index, current), end = monthStart(1 - index, current);
      return { key: key(start), start, end, label: label(start, end) };
    });
  }, [history]);
  const period = periods.find((item) => item.key === selected);
  const periodEntries = useMemo(() => {
    if (!period) return [];
    return history.filter((entry: any) => {
      const value = new Date(entry.clock_in).getTime();
      return value >= period.start.getTime() && value < period.end.getTime();
    });
  }, [history, period]);
  const periodWorkers = useMemo(() => {
    const grouped = new Map<string, { id: string; name: string; entries: any[] }>();
    for (const entry of periodEntries) {
      const id = workerId(entry);
      if (!grouped.has(id)) grouped.set(id, { id, name: workerName(entry), entries: [] });
      grouped.get(id)!.entries.push(entry);
    }
    return Array.from(grouped.values()).sort((a, b) => a.name.localeCompare(b.name, 'de'));
  }, [periodEntries]);
  const currentWorker = periodWorkers.find((item) => item.id === selectedWorker);
  const workerEntries = useMemo(() => {
    const source = showWorker ? periodEntries.filter((entry: any) => workerId(entry) === selectedWorker) : periodEntries;
    return [...source].sort((a: any, b: any) => new Date(a.clock_in).getTime() - new Date(b.clock_in).getTime());
  }, [periodEntries, selectedWorker, showWorker]);
  const workerMinutes = workerEntries.reduce((sum: number, entry: any) => sum + entryMinutes(entry), 0);
  const groupedDays = useMemo(() => {
    const groups = new Map<string, any[]>();
    for (const entry of workerEntries) {
      const day = dayKey(entry.clock_in);
      if (!groups.has(day)) groups.set(day, []);
      groups.get(day)!.push(entry);
    }
    return Array.from(groups.entries());
  }, [workerEntries]);

  async function refreshHistory() {
    const payload: any = await api('attendance/history/');
    setHistory(Array.isArray(payload?.history) ? payload.history : []);
  }

  function openCreate(worker = '') {
    if (!showWorker) return;
    const start = defaultInput(period);
    setForm({ mode: 'create', worker, clock_in: start, clock_out: addInputMinutes(start, 240), edit_reason: '' });
    setMessage('');
  }

  function openEdit(entry: any) {
    if (!showWorker || entry?.wiw_time_id) return;
    setForm({
      mode: 'edit', id: String(entry.id), worker: workerId(entry), clock_in: inputDateTime(entry.clock_in), clock_out: inputDateTime(entry.clock_out), edit_reason: entry.edit_reason || '',
    });
    setMessage('');
  }

  async function saveForm() {
    if (!form || !showWorker) return;
    if (!form.worker || !form.clock_in || !form.clock_out) { setMessage('Bitte Mitarbeiter, Beginn und Ende vollständig ausfüllen.'); return; }
    if (new Date(form.clock_out).getTime() <= new Date(form.clock_in).getTime()) { setMessage('Das Ende muss nach dem Beginn liegen.'); return; }
    if (form.mode === 'edit' && form.edit_reason.trim().length < 3) { setMessage('Bitte einen kurzen Änderungsgrund angeben.'); return; }
    setBusy(true);
    try {
      const body: any = { worker: form.worker, clock_in: form.clock_in, clock_out: form.clock_out };
      if (form.mode === 'edit') body.edit_reason = form.edit_reason.trim();
      const saved: any = await api(form.mode === 'edit' ? `time-entries/${form.id}/` : 'time-entries/', {
        method: form.mode === 'edit' ? 'PATCH' : 'POST', body: JSON.stringify(body),
      });
      await refreshHistory();
      setForm(undefined);
      setMessage('');
      if (form.mode === 'create') {
        setSelectedWorker(String(saved.worker || form.worker));
      } else {
        setSelectedEntry(saved);
      }
    } catch (error: any) {
      setMessage(error?.message || 'Zeiteintrag konnte nicht gespeichert werden.');
    } finally {
      setBusy(false);
    }
  }

  async function removeEntry(entry: any) {
    if (!showWorker || !entry?.id || entry?.wiw_time_id) return;
    if (!window.confirm('Diesen Zeiteintrag wirklich löschen?')) return;
    setBusy(true);
    try {
      await api(`time-entries/${entry.id}/`, { method: 'DELETE' });
      await refreshHistory();
      setSelectedEntry(undefined);
      setMessage('');
    } catch (error: any) {
      setMessage(error?.message || 'Zeiteintrag konnte nicht gelöscht werden.');
    } finally {
      setBusy(false);
    }
  }

  if (form) {
    const availableWorkers = workers.length ? workers : periodWorkers.map((item) => ({ id: item.id, user_detail: { name: item.name } }));
    return <div className="wiw-attendance-editor" data-testid="phase8-attendance-editor">
      <div className="wiw-attendance-toolbar">
        <button type="button" className="back" aria-label="Zurück" onClick={() => setForm(undefined)}><IonIcon icon={chevronBackOutline} /></button>
        <strong>{form.mode === 'edit' ? 'Zeiteintrag bearbeiten' : 'Zeiteintrag hinzufügen'}</strong>
        <button type="button" className="text-action" disabled={busy} onClick={() => void saveForm()}>{busy ? '…' : 'Speichern'}</button>
      </div>
      <div className="wiw-edit-form">
        {showWorker && <label><span>Mitarbeiter</span><select value={form.worker} disabled={form.mode === 'edit'} onChange={(event) => setForm({ ...form, worker: event.target.value })}><option value="">Bitte auswählen …</option>{availableWorkers.filter((worker: any) => worker.active !== false).map((worker: any) => <option key={worker.id} value={worker.id}>{worker.user_detail?.name || worker.user_detail?.email || worker.employee_number || 'Mitarbeiter'}</option>)}</select></label>}
        <label><span>Beginn</span><input type="datetime-local" value={form.clock_in} onChange={(event) => setForm({ ...form, clock_in: event.target.value })} /></label>
        <label><span>Ende</span><input type="datetime-local" value={form.clock_out} onChange={(event) => setForm({ ...form, clock_out: event.target.value })} /></label>
        {form.mode === 'edit' && <label><span>Änderungsgrund</span><textarea rows={3} placeholder="Warum wird der Eintrag geändert?" value={form.edit_reason} onChange={(event) => setForm({ ...form, edit_reason: event.target.value })} /></label>}
        {message && <div className="wiw-attendance-message">{message}</div>}
      </div>
    </div>;
  }

  if (selectedEntry) {
    const readonly = Boolean(selectedEntry.wiw_time_id);
    const selectedName = workerName(selectedEntry);
    return <div className="wiw-attendance-entry-detail" data-testid="phase8-entry-detail">
      <div className="wiw-attendance-toolbar">
        <button type="button" className="back" aria-label="Zurück" onClick={() => setSelectedEntry(undefined)}><IonIcon icon={chevronBackOutline} /></button>
        <strong>Zeiteintrag</strong>
        <div className="wiw-entry-actions">
          {showWorker && !readonly && <button type="button" aria-label="Zeiteintrag löschen" disabled={busy} onClick={() => void removeEntry(selectedEntry)}><IonIcon icon={trashOutline} /></button>}
          {showWorker && !readonly && <button type="button" aria-label="Zeiteintrag bearbeiten" onClick={() => openEdit(selectedEntry)}><IonIcon icon={createOutline} /></button>}
        </div>
      </div>
      {readonly && <div className="wiw-readonly-banner"><IonIcon icon={informationCircleOutline} /> WIW-Import · historischer Eintrag, schreibgeschützt</div>}
      <div className="wiw-entry-fields">
        <DetailRow icon={personOutline} label="Wer" value={selectedName} />
        <DetailRow icon={calendarOutline} label="Datum" value={fmtDay(selectedEntry.clock_in)} />
        <DetailRow icon={timeOutline} label="Zeit" value={`${fmtTime(selectedEntry.clock_in)} – ${selectedEntry.clock_out ? fmtTime(selectedEntry.clock_out) : 'läuft'}`} />
        <DetailRow icon={briefcaseOutline} label="Dienstplan" value={shiftDetail ? 'A+' : (selectedEntry.wiw_time_id ? 'WIW' : 'Manuell')} />
        <DetailRow icon={briefcaseOutline} label="Position" value={shiftDetail?.position_name || selectedEntry.shift_title || 'Arbeitszeit'} />
        <DetailRow icon={locationOutline} label="Einsatzort" value={shiftDetail?.location_name || 'Nicht hinterlegt'} />
      </div>
      <button className="wiw-entry-history-button" type="button" onClick={() => setHistoryOpen((value) => !value)}>Eintragsverlauf anzeigen</button>
      {historyOpen && <div className="wiw-entry-history">
        <div><span>Quelle</span><strong>{readonly ? 'When I Work Import' : 'A+ Solution'}</strong></div>
        <div><span>Status</span><strong>{selectedEntry.approved ? 'Freigegeben' : 'Nicht freigegeben'}</strong></div>
        {selectedEntry.created_at && <div><span>Erstellt</span><strong>{fmtDate(selectedEntry.created_at)} · {fmtTime(selectedEntry.created_at)}</strong></div>}
        {selectedEntry.updated_at && <div><span>Zuletzt geändert</span><strong>{fmtDate(selectedEntry.updated_at)} · {fmtTime(selectedEntry.updated_at)}</strong></div>}
        {selectedEntry.edit_reason && <div><span>Änderungsgrund</span><strong>{selectedEntry.edit_reason}</strong></div>}
      </div>}
      {message && <div className="wiw-attendance-message floating">{message}</div>}
    </div>;
  }

  if (period && (!showWorker || selectedWorker)) {
    const timesheetName = showWorker ? (currentWorker?.name || workerEntries[0]?.worker_name || 'Mitarbeiter') : '';
    return <div className="wiw-worker-timesheet" data-testid="phase8-worker-timesheet">
      <div className="wiw-attendance-toolbar">
        <button type="button" className="back" aria-label="Zurück" onClick={() => showWorker ? setSelectedWorker(undefined) : setSelected(undefined)}><IonIcon icon={chevronBackOutline} /></button>
        <strong>{shortLabel(period.start, period.end)}{showWorker ? ' · Stundenzettel' : ''}</strong>
        {showWorker ? <button type="button" className="icon-action" aria-label="Zeiteintrag hinzufügen" onClick={() => openCreate(selectedWorker)}><IonIcon icon={addOutline} /></button> : <span />}
      </div>
      {showWorker && <div className="wiw-timesheet-person"><span className="wiw-worker-avatar small">{initials(timesheetName)}</span><strong>{timesheetName}</strong></div>}
      <div className="wiw-timesheet-days">
        {groupedDays.map(([day, entries]) => {
          const dayMinutes = entries.reduce((sum, entry) => sum + entryMinutes(entry), 0);
          return <section key={day}>
            <div className="wiw-timesheet-day-head"><span>{fmtDay(entries[0].clock_in)}</span><strong>{hoursNumber(dayMinutes)}</strong></div>
            {entries.map((entry) => <button type="button" className="wiw-timesheet-entry" key={entry.id} onClick={() => setSelectedEntry(entry)}>
              <span>{fmtTime(entry.clock_in)} – {entry.clock_out ? fmtTime(entry.clock_out) : 'läuft'} {entry.wiw_time_id ? '(WIW)' : ''}</span>
            </button>)}
          </section>;
        })}
        {!workerEntries.length && <div className="wiw-period-empty">Keine Arbeitszeiten in diesem Zeitraum.</div>}
      </div>
      <div className="wiw-timesheet-total"><span>Bezahlte Gesamtstunden</span><strong>{hoursNumber(workerMinutes)}</strong></div>
    </div>;
  }

  if (period && showWorker) {
    return <div className="wiw-period-workers" data-testid="phase8-period-workers">
      <div className="wiw-attendance-toolbar">
        <button type="button" className="back" aria-label="Abrechnungszeiträume" onClick={() => setSelected(undefined)}><IonIcon icon={chevronBackOutline} /></button>
        <strong>{shortLabel(period.start, period.end)}</strong>
        <button type="button" className="icon-action" aria-label="Zeiteintrag hinzufügen" onClick={() => openCreate()}><IonIcon icon={addOutline} /></button>
      </div>
      <div className="wiw-worker-list">
        {periodWorkers.map((item) => {
          const worker = workerMap.get(item.id);
          const avatar = worker?.user_detail?.avatar;
          return <button type="button" className="wiw-worker-row" key={item.id} onClick={() => setSelectedWorker(item.id)}>
            <span className="wiw-worker-avatar">{avatar ? <img src={avatar} alt="" loading="lazy" /> : initials(item.name)}</span>
            <strong>{item.name}</strong>
          </button>;
        })}
        {!periodWorkers.length && <div className="wiw-period-empty">Keine Mitarbeiter mit Arbeitszeiten in diesem Zeitraum.</div>}
      </div>
      {message && <div className="wiw-attendance-message floating">{message}</div>}
    </div>;
  }

  return <div className="wiw-pay-periods" data-testid="phase8-pay-periods">
    <div className="wiw-mobile-screen-title">Abrechnungszeiträume</div>
    {periods.map((item) => <button type="button" className="wiw-period-row" key={item.key} onClick={() => { setSelected(item.key); setSelectedWorker(undefined); setSelectedEntry(undefined); }}>
      <strong>{item.label}</strong>
      <span className="wiw-period-circle" aria-hidden="true" />
    </button>)}
  </div>;
}

function DetailRow({ icon, label, value }: { icon: string; label: string; value: string }) {
  return <div className="wiw-entry-field">
    <IonIcon icon={icon} />
    <div><small>{label}</small><strong>{value}</strong></div>
  </div>;
}
