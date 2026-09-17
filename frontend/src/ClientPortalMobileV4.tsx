import React, { useEffect, useMemo, useRef, useState } from 'react';
import { IonIcon, IonSpinner } from '@ionic/react';
import {
  addOutline,
  briefcaseOutline,
  calendarOutline,
  cameraOutline,
  checkmarkCircleOutline,
  chevronBackOutline,
  closeCircleOutline,
  cloudUploadOutline,
  documentTextOutline,
  folderOpenOutline,
  lockClosedOutline,
  locationOutline,
  personOutline,
  starOutline,
  timeOutline,
} from 'ionicons/icons';
import { api } from './api';
import './client-portal-v4.css';

type ClientAccess = {
  client_id: string;
  client_name: string;
  account_name: string;
  first_name: string;
  read_only: boolean;
  location_scope_id?: string | null;
  location_scope_name?: string | null;
  capabilities?: Record<string, boolean>;
};

const TZ = 'Europe/Berlin';
const unpack = (payload: any): any[] => Array.isArray(payload) ? payload : payload?.results || [];
const pad = (value: number) => String(value).padStart(2, '0');

function berlinParts(value?: string) {
  if (!value) return { date: '–', time: '–', compact: '–' };
  const date = new Date(value);
  const dateText = new Intl.DateTimeFormat('de-DE', { timeZone: TZ, day: '2-digit', month: '2-digit', year: '2-digit' }).format(date);
  const timeText = new Intl.DateTimeFormat('de-DE', { timeZone: TZ, hour: '2-digit', minute: '2-digit' }).format(date);
  const weekday = new Intl.DateTimeFormat('de-DE', { timeZone: TZ, weekday: 'short' }).format(date);
  return { date: dateText, time: timeText, compact: `${weekday} ${dateText}` };
}

function inputDateTime(value?: string) {
  if (!value) return '';
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: TZ,
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(new Date(value));
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)?.value || '';
  return `${part('year')}-${part('month')}-${part('day')}T${part('hour')}:${part('minute')}`;
}

function toIso(value: string) {
  return value ? new Date(value).toISOString() : '';
}

function focusIntoView(event: React.FocusEvent<HTMLElement>) {
  const target = event.target as HTMLElement;
  window.setTimeout(() => target.scrollIntoView({ behavior: 'smooth', block: 'center' }), 260);
}

function Modal({ title, onClose, children, footer }: { title: string; onClose: () => void; children: React.ReactNode; footer?: React.ReactNode }) {
  useEffect(() => {
    document.body.classList.add('client-portal-modal-open');
    return () => document.body.classList.remove('client-portal-modal-open');
  }, []);
  return <div className="client-v4-modal" role="dialog" aria-modal="true" onFocusCapture={focusIntoView}>
    <header>
      <button type="button" onClick={onClose} aria-label="Schließen"><IonIcon icon={chevronBackOutline} /></button>
      <strong>{title}</strong>
      <span />
    </header>
    <div className="client-v4-modal-scroll">{children}</div>
    {footer ? <div className="client-v4-modal-footer">{footer}</div> : null}
  </div>;
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="client-v4-empty">{children}</div>;
}

function ScreenTitle({ eyebrow, title, text, icon }: { eyebrow: string; title: string; text?: string; icon: string }) {
  return <div className="client-v4-title">
    <div><small>{eyebrow}</small><h1>{title}</h1>{text ? <p>{text}</p> : null}</div>
    <span><IonIcon icon={icon} /></span>
  </div>;
}

export function RestrictedClientGate({ access }: { access: ClientAccess }) {
  const locked = ['Personal anfragen', 'Dokumente', 'Bewertungen', 'Mitteilungen', 'Profil ändern'];
  return <div className="client-v2-custom-screen client-v4-screen client-v4-restricted">
    <ScreenTitle eyebrow="EINGESCHRÄNKTER ZUGANG" title={access.account_name || 'Evangelische Akademie'} text={`Nur Einsätze am Standort ${access.location_scope_name || 'Evangelische Akademie'} sind freigegeben.`} icon={lockClosedOutline} />
    <div className="client-v4-lock-card">
      <IonIcon icon={calendarOutline} />
      <div><b>Dienstplan ist lesbar</b><small>Schichten können geöffnet und angesehen werden. Änderungen oder andere Aktionen sind deaktiviert.</small></div>
    </div>
    <div className="client-v4-lock-grid">
      {locked.map((label) => <div key={label}><IonIcon icon={lockClosedOutline} /><span>{label}</span></div>)}
    </div>
  </div>;
}

export function ClientDocumentsMobile({ access, compact = false }: { access: ClientAccess; compact?: boolean }) {
  const [rows, setRows] = useState<any[]>([]);
  const [busy, setBusy] = useState(true);
  const [message, setMessage] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    setBusy(true);
    try {
      const data = await api('portal/client-documents/');
      setRows(unpack(data));
    } catch (error: any) {
      setMessage(error?.message || 'Dokumente konnten nicht geladen werden.');
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => { void load(); }, []);

  async function upload(file?: File) {
    if (!file) return;
    const body = new FormData();
    body.append('file', file);
    body.append('title', file.name);
    setBusy(true);
    try {
      await api('portal/client-documents/', { method: 'POST', body });
      setMessage('Dokument wurde hochgeladen.');
      if (fileRef.current) fileRef.current.value = '';
      await load();
    } catch (error: any) {
      setMessage(error?.message || 'Upload fehlgeschlagen.');
      setBusy(false);
    }
  }

  if (access.read_only) return <RestrictedClientGate access={access} />;
  return <div className={`client-v2-custom-screen client-v4-screen client-v4-documents ${compact ? 'is-compact' : ''}`}>
    {!compact ? <ScreenTitle eyebrow="DATEIEN" title="Dokumente" text="Wie ein gemeinsamer Ordner – öffnen, herunterladen oder direkt vom Handy hochladen." icon={folderOpenOutline} /> : null}
    <div className="client-v4-upload-card">
      <div><IonIcon icon={cloudUploadOutline} /><span><b>Datei hochladen</b><small>PDF, Office-Datei oder Foto</small></span></div>
      <button type="button" disabled={busy} onClick={() => fileRef.current?.click()}><IonIcon icon={cameraOutline} /> Foto / Datei</button>
      <input
        ref={fileRef}
        hidden
        type="file"
        accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.csv,.txt"
        capture="environment"
        onChange={(event) => void upload(event.target.files?.[0])}
      />
    </div>
    {message ? <div className="client-v4-message">{message}</div> : null}
    {busy && !rows.length ? <div className="client-v4-loading"><IonSpinner /> Lädt …</div> : null}
    <div className="client-v4-file-list">
      {rows.map((row) => <a href={row.file} target="_blank" rel="noreferrer" key={row.id}>
        <span className="file-icon"><IonIcon icon={documentTextOutline} /></span>
        <span className="file-copy"><b>{row.title}</b><small>{row.uploaded_by_name} · {berlinParts(row.created_at).date} {berlinParts(row.created_at).time}</small></span>
        <span className="file-open">Öffnen</span>
      </a>)}
      {!busy && !rows.length ? <Empty>Noch keine Dokumente.</Empty> : null}
    </div>
  </div>;
}

export function ClientOrdersMobile({ access }: { access: ClientAccess }) {
  const [rows, setRows] = useState<any[]>([]);
  const [metadata, setMetadata] = useState<any>({ locations: [], positions: [] });
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [form, setForm] = useState<any>({ title: 'Personalanfrage', requested_staff: 1, description: '' });

  const load = async () => {
    try {
      const [orders, meta] = await Promise.all([api('orders/?ordering=-created_at'), api('portal/client-order-metadata/')]);
      setRows(unpack(orders));
      setMetadata(meta || { locations: [], positions: [] });
    } catch (error: any) {
      setMessage(error?.message || 'Anfragen konnten nicht geladen werden.');
    }
  };
  useEffect(() => { if (!access.read_only) void load(); }, [access.read_only]);

  async function submit() {
    if (!form.location || !form.position || !form.starts_at || !form.ends_at) {
      setMessage('Bitte Einsatzort, Funktion, Beginn und Ende vollständig angeben.');
      return;
    }
    setBusy(true);
    try {
      await api('orders/', {
        method: 'POST',
        body: JSON.stringify({
          title: String(form.title || 'Personalanfrage').trim(),
          description: String(form.description || '').trim(),
          location: form.location,
          starts_at: toIso(form.starts_at),
          ends_at: toIso(form.ends_at),
          requested_staff: Math.max(1, Number(form.requested_staff || 1)),
          functions: [form.position],
          status: 'new',
        }),
      });
      setOpen(false);
      setForm({ title: 'Personalanfrage', requested_staff: 1, description: '' });
      setMessage('Anfrage gesendet. Die Disposition wurde benachrichtigt.');
      await load();
    } catch (error: any) {
      setMessage(error?.message || 'Anfrage konnte nicht gesendet werden.');
    } finally {
      setBusy(false);
    }
  }

  if (access.read_only) return <RestrictedClientGate access={access} />;
  const status: Record<string, string> = { new: 'Neu', planning: 'In Prüfung', confirmed: 'Bestätigt', done: 'Abgeschlossen', cancelled: 'Abgelehnt / storniert' };
  return <div className="client-v2-custom-screen client-v4-screen client-v4-orders">
    <ScreenTitle eyebrow="PERSONAL" title="Personal anfragen" text="Bedarf absenden. Die Disposition prüft ihn und veröffentlicht ihn nach Freigabe direkt als OpenShift." icon={briefcaseOutline} />
    <button className="client-v4-primary" type="button" onClick={() => { setMessage(''); setOpen(true); }}><IonIcon icon={addOutline} /><span><b>Neuer Auftrag</b><small>Datum, Zeit, Ort und Personalbedarf</small></span></button>
    {message ? <div className="client-v4-message">{message}</div> : null}
    <section className="client-v4-section">
      <header><div><small>VERLAUF</small><h2>Personalanfragen</h2></div></header>
      {rows.map((row) => <div className="client-v4-order-row" key={row.id}>
        <div><b>{row.title}</b><span>{berlinParts(row.starts_at).date} · {berlinParts(row.starts_at).time}–{berlinParts(row.ends_at).time}</span><small>{row.location_name || row.description}</small></div>
        <em className={`status-${row.status}`}>{status[row.status] || row.status}</em>
      </div>)}
      {!rows.length ? <Empty>Noch keine Personalanfragen.</Empty> : null}
    </section>

    {open ? <Modal title="Neuer Auftrag" onClose={() => setOpen(false)} footer={<button className="client-v4-save" type="button" disabled={busy} onClick={() => void submit()}>{busy ? 'Wird gesendet …' : 'Anfrage senden'}</button>}>
      <div className="client-v4-form">
        <label><span>Titel</span><input value={form.title || ''} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label>
        <label><span>Einsatzort *</span><select value={form.location || ''} onChange={(event) => setForm({ ...form, location: event.target.value })}><option value="">Bitte auswählen …</option>{(metadata.locations || []).map((item: any) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
        <label><span>Funktion *</span><select value={form.position || ''} onChange={(event) => setForm({ ...form, position: event.target.value })}><option value="">Bitte auswählen …</option>{(metadata.positions || []).map((item: any) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
        <div className="client-v4-form-grid">
          <label><span>Beginn *</span><input type="datetime-local" value={form.starts_at || ''} onChange={(event) => setForm({ ...form, starts_at: event.target.value })} /></label>
          <label><span>Ende *</span><input type="datetime-local" value={form.ends_at || ''} onChange={(event) => setForm({ ...form, ends_at: event.target.value })} /></label>
        </div>
        <label><span>Anzahl Mitarbeiter *</span><input type="number" min="1" max="99" inputMode="numeric" value={form.requested_staff || 1} onChange={(event) => setForm({ ...form, requested_staff: event.target.value })} /></label>
        <label className="client-v4-note"><span>Notiz</span><textarea rows={7} placeholder="Alles, was die Disposition für diesen Einsatz wissen soll …" value={form.description || ''} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
      </div>
      {message ? <div className="client-v4-message">{message}</div> : null}
    </Modal> : null}
  </div>;
}

function firstOfWeek(value: string) {
  const date = new Date(`${value}T12:00:00Z`);
  const weekday = date.getUTCDay();
  date.setUTCDate(date.getUTCDate() + (weekday === 0 ? -6 : 1 - weekday));
  return date;
}
function dateKey(date: Date) { return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}`; }
function addDay(date: Date, amount: number) { const next = new Date(date); next.setUTCDate(next.getUTCDate() + amount); return next; }
function todayKey() {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
  const part = (type: string) => parts.find((item) => item.type === type)?.value || '';
  return `${part('year')}-${part('month')}-${part('day')}`;
}
function isoDay(value?: string) {
  if (!value) return '';
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date(value));
  const part = (type: string) => parts.find((item) => item.type === type)?.value || '';
  return `${part('year')}-${part('month')}-${part('day')}`;
}

export function ClientScheduleMobileV4({ access }: { access: ClientAccess }) {
  const [rows, setRows] = useState<any[]>([]);
  const [anchor, setAnchor] = useState(todayKey());
  const [selected, setSelected] = useState<any>();
  const [modal, setModal] = useState<'change' | 'cancel' | ''>('');
  const [form, setForm] = useState<any>({});
  const [busy, setBusy] = useState(true);
  const [message, setMessage] = useState('');

  const load = async () => {
    setBusy(true);
    try {
      const data = await api('portal/client-shifts/');
      setRows(unpack(data));
    } catch (error: any) {
      setMessage(error?.message || 'Dienstplan konnte nicht geladen werden.');
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => { void load(); }, []);

  const weekStart = firstOfWeek(anchor);
  const days = Array.from({ length: 7 }, (_, index) => addDay(weekStart, index));
  const dayKeys = days.map(dateKey);
  const visible = rows.filter((shift) => dayKeys.includes(isoDay(shift.starts_at)) && shift.status !== 'cancelled');
  const byDay = useMemo(() => {
    const map: Record<string, any[]> = Object.fromEntries(dayKeys.map((day) => [day, []]));
    visible.forEach((shift) => (map[isoDay(shift.starts_at)] ||= []).push(shift));
    Object.values(map).forEach((items) => items.sort((a, b) => new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime()));
    return map;
  }, [rows, anchor]);

  async function submitRequest(type: 'change' | 'cancel') {
    setBusy(true);
    try {
      const payload: any = { shift: selected.id, request_type: type, note: form.note || '' };
      if (type === 'change') {
        payload.starts_at = toIso(form.starts_at);
        payload.ends_at = toIso(form.ends_at);
      }
      await api('portal/shift-change-requests/', { method: 'POST', body: JSON.stringify(payload) });
      setModal('');
      setMessage('Anfrage wurde an die Disposition gesendet.');
    } catch (error: any) {
      setMessage(error?.message || 'Anfrage konnte nicht gesendet werden.');
    } finally {
      setBusy(false);
    }
  }

  if (selected) {
    const workers = Array.isArray(selected.assigned_workers) ? selected.assigned_workers : [];
    return <div className="client-v2-custom-screen client-v4-screen client-v4-shift-detail">
      <header className="client-v4-detail-head"><button type="button" onClick={() => setSelected(undefined)}><IonIcon icon={chevronBackOutline} /></button><strong>Einsatzdetails</strong><span /></header>
      <div className="client-v4-detail-card">
        <div><IonIcon icon={calendarOutline} /><span><small>Datum</small><b>{berlinParts(selected.starts_at).compact}</b></span></div>
        <div><IonIcon icon={timeOutline} /><span><small>Zeit</small><b>{berlinParts(selected.starts_at).time} – {berlinParts(selected.ends_at).time}</b></span></div>
        <div><IonIcon icon={locationOutline} /><span><small>Einsatzort</small><b>{selected.location_name}</b></span></div>
        <div><IonIcon icon={personOutline} /><span><small>Personal</small><b>{workers.length ? workers.map((worker: any) => worker.name).join(', ') : `${selected.filled_count || 0}/${selected.required_count || 1} besetzt`}</b></span></div>
        <div className="notes"><IonIcon icon={documentTextOutline} /><span><small>Notiz</small><b>{selected.notes || 'Keine Notiz hinterlegt.'}</b></span></div>
      </div>
      {message ? <div className="client-v4-message">{message}</div> : null}
      {!access.read_only ? <div className="client-v4-shift-actions">
        <button type="button" onClick={() => { setForm({ starts_at: inputDateTime(selected.starts_at), ends_at: inputDateTime(selected.ends_at), note: '' }); setModal('change'); }}><IonIcon icon={timeOutline} /><span><b>Zeit / Datum ändern</b><small>Anfrage an die Disposition</small></span></button>
        <button type="button" className="danger" onClick={() => { setForm({ note: '' }); setModal('cancel'); }}><IonIcon icon={closeCircleOutline} /><span><b>Stornierung anfragen</b><small>Wird erst nach Freigabe wirksam</small></span></button>
      </div> : <div className="client-v4-lock-card"><IonIcon icon={lockClosedOutline} /><div><b>Nur Ansicht</b><small>Dieser Zugang darf keine Änderungen oder Aktionen ausführen.</small></div></div>}

      {modal === 'change' ? <Modal title="Schichtänderung anfragen" onClose={() => setModal('')} footer={<button className="client-v4-save" disabled={busy} type="button" onClick={() => void submitRequest('change')}>Änderung senden</button>}>
        <div className="client-v4-form"><label><span>Neuer Beginn</span><input type="datetime-local" value={form.starts_at || ''} onChange={(event) => setForm({ ...form, starts_at: event.target.value })} /></label><label><span>Neues Ende</span><input type="datetime-local" value={form.ends_at || ''} onChange={(event) => setForm({ ...form, ends_at: event.target.value })} /></label><label><span>Notiz an die Disposition</span><textarea rows={6} value={form.note || ''} onChange={(event) => setForm({ ...form, note: event.target.value })} /></label></div>
      </Modal> : null}
      {modal === 'cancel' ? <Modal title="Stornierung anfragen" onClose={() => setModal('')} footer={<button className="client-v4-save danger" disabled={busy} type="button" onClick={() => void submitRequest('cancel')}>Stornierung senden</button>}>
        <div className="client-v4-confirm"><IonIcon icon={closeCircleOutline} /><h2>Diese Schicht stornieren?</h2><p>Es passiert noch nichts automatisch. Die Disposition erhält die Anfrage und entscheidet darüber.</p><label><span>Grund / Notiz</span><textarea rows={6} value={form.note || ''} onChange={(event) => setForm({ ...form, note: event.target.value })} /></label></div>
      </Modal> : null}
    </div>;
  }

  return <div className="client-v2-custom-screen client-v4-screen client-v4-schedule">
    <div className="client-v4-weekbar">
      <button type="button" onClick={() => setAnchor(dateKey(addDay(weekStart, -7)))}>‹</button>
      {days.map((day) => {
        const key = dateKey(day);
        const weekday = new Intl.DateTimeFormat('de-DE', { timeZone: 'UTC', weekday: 'short' }).format(day).slice(0, 2);
        return <button type="button" className={`${key === anchor ? 'active ' : ''}${key === todayKey() ? 'today' : ''}`} key={key} onClick={() => setAnchor(key)}><small>{weekday}</small><b>{day.getUTCDate()}</b></button>;
      })}
      <button type="button" onClick={() => setAnchor(dateKey(addDay(weekStart, 7)))}>›</button>
    </div>
    {access.read_only ? <div className="client-v4-scope-note"><IonIcon icon={lockClosedOutline} /> Nur {access.location_scope_name || 'freigegebener Standort'} · Ansicht</div> : null}
    {message ? <div className="client-v4-message">{message}</div> : null}
    {busy && !rows.length ? <div className="client-v4-loading"><IonSpinner /> Dienstplan wird geladen …</div> : null}
    <div className="client-v4-days">
      {days.map((day) => {
        const key = dateKey(day);
        const shifts = byDay[key] || [];
        const header = new Intl.DateTimeFormat('de-DE', { timeZone: 'UTC', weekday: 'long', day: '2-digit', month: '2-digit' }).format(day);
        return <section key={key}><header>{header}</header>{shifts.map((shift) => <button type="button" className="client-v4-shift-row" key={shift.id} onClick={() => { setMessage(''); setSelected(shift); }}><span className="shift-time">{berlinParts(shift.starts_at).time}<small>{berlinParts(shift.ends_at).time}</small></span><span className="shift-copy"><b>{shift.location_name}</b><small>{shift.notes || `${shift.filled_count || 0}/${shift.required_count || 1} besetzt`}</small></span><span className="shift-chevron">›</span></button>)}{!shifts.length ? <div className="client-v4-day-empty">Keine Einsätze</div> : null}</section>;
      })}
    </div>
  </div>;
}

export function ClientRatingsMobileV4({ access }: { access: ClientAccess }) {
  const [candidates, setCandidates] = useState<any[]>([]);
  const [selectedShift, setSelectedShift] = useState<string>('');
  const [selectedWorker, setSelectedWorker] = useState<any>();
  const [form, setForm] = useState<any>({ score: 5, punctuality: 5, quality: 5, teamwork: 5, comment: '' });
  const [busy, setBusy] = useState(true);
  const [message, setMessage] = useState('');

  const load = async () => {
    setBusy(true);
    try {
      const data = await api('portal/rating-candidates/');
      setCandidates(unpack(data));
    } catch (error: any) {
      setMessage(error?.message || 'Bewertungen konnten nicht geladen werden.');
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => { if (!access.read_only) void load(); }, [access.read_only]);

  const shifts = useMemo(() => {
    const map = new Map<string, any>();
    candidates.forEach((row) => {
      if (!map.has(row.shift_id)) map.set(row.shift_id, { id: row.shift_id, starts_at: row.starts_at, ends_at: row.ends_at, location_name: row.location_name, notes: row.notes || '', workers: [] });
      map.get(row.shift_id).workers.push(row);
    });
    return Array.from(map.values()).sort((a, b) => new Date(b.starts_at).getTime() - new Date(a.starts_at).getTime());
  }, [candidates]);
  const shift = shifts.find((item) => item.id === selectedShift);

  async function save() {
    if (!selectedWorker || !selectedShift) return;
    setBusy(true);
    try {
      await api('ratings/', { method: 'POST', body: JSON.stringify({ ...form, shift: selectedShift, worker: selectedWorker.worker_id }) });
      setSelectedWorker(undefined);
      setForm({ score: 5, punctuality: 5, quality: 5, teamwork: 5, comment: '' });
      setMessage('Bewertung gespeichert.');
      await load();
    } catch (error: any) {
      setMessage(error?.message || 'Bewertung konnte nicht gespeichert werden.');
      setBusy(false);
    }
  }

  if (access.read_only) return <RestrictedClientGate access={access} />;
  if (selectedShift && shift) {
    return <div className="client-v2-custom-screen client-v4-screen client-v4-ratings">
      <header className="client-v4-detail-head"><button type="button" onClick={() => setSelectedShift('')}><IonIcon icon={chevronBackOutline} /></button><strong>Mitarbeiter bewerten</strong><span /></header>
      <div className="client-v4-selected-shift"><IonIcon icon={calendarOutline} /><div><b>{berlinParts(shift.starts_at).date} · {berlinParts(shift.starts_at).time}–{berlinParts(shift.ends_at).time}</b><small>{shift.location_name}{shift.notes ? ` · ${shift.notes}` : ''}</small></div></div>
      {message ? <div className="client-v4-message">{message}</div> : null}
      <section className="client-v4-section"><header><div><small>MITARBEITER</small><h2>Einzeln bewerten</h2></div><span>{shift.workers.length}</span></header>{shift.workers.map((worker: any) => <button type="button" className="client-v4-worker-row" key={worker.worker_id} onClick={() => { setMessage(''); setSelectedWorker(worker); }}><span className="worker-avatar">{String(worker.worker_name || 'M').split(/\s+/).map((item: string) => item[0]).slice(0, 2).join('').toUpperCase()}</span><span><b>{worker.worker_name}</b><small>Bewertung öffnen</small></span><IonIcon icon={starOutline} /></button>)}</section>
      {selectedWorker ? <Modal title={selectedWorker.worker_name} onClose={() => setSelectedWorker(undefined)} footer={<button className="client-v4-save" disabled={busy} type="button" onClick={() => void save()}>Bewertung speichern</button>}>
        <div className="client-v4-rating-form">
          {([['score', 'Gesamt'], ['punctuality', 'Pünktlichkeit'], ['quality', 'Qualität'], ['teamwork', 'Teamarbeit']] as const).map(([key, label]) => <div className="client-v4-score" key={key}><span>{label}</span><div>{[1, 2, 3, 4, 5].map((score) => <button type="button" className={Number(form[key]) >= score ? 'active' : ''} key={score} onClick={() => setForm({ ...form, [key]: score })}><IonIcon icon={starOutline} /></button>)}</div></div>)}
          <label><span>Kommentar</span><textarea rows={6} value={form.comment || ''} onChange={(event) => setForm({ ...form, comment: event.target.value })} /></label>
        </div>
      </Modal> : null}
    </div>;
  }

  return <div className="client-v2-custom-screen client-v4-screen client-v4-ratings">
    <ScreenTitle eyebrow="BEWERTUNGEN" title="Einsatz auswählen" text="Erst den Einsatz wählen, danach die eingesetzten Mitarbeiter einzeln bewerten." icon={starOutline} />
    {message ? <div className="client-v4-message">{message}</div> : null}
    {busy && !shifts.length ? <div className="client-v4-loading"><IonSpinner /> Einsätze werden geladen …</div> : null}
    <div className="client-v4-rating-shifts">
      {shifts.map((item) => <button type="button" key={item.id} onClick={() => { setMessage(''); setSelectedShift(item.id); }}><span><b>{berlinParts(item.starts_at).date} · {berlinParts(item.starts_at).time}–{berlinParts(item.ends_at).time}</b><small>{item.location_name}{item.notes ? ` · ${item.notes}` : ''}</small></span><em>{item.workers.length} MA</em></button>)}
      {!busy && !shifts.length ? <Empty>Aktuell gibt es keine noch offenen Bewertungen.</Empty> : null}
    </div>
  </div>;
}

export type { ClientAccess };
