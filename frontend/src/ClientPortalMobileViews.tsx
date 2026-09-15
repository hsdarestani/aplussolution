import React, { useEffect, useMemo, useState } from 'react';
import { IonIcon, IonSpinner } from '@ionic/react';
import {
  briefcaseOutline,
  calendarOutline,
  chevronBackOutline,
  locationOutline,
  personOutline,
  star,
  starOutline,
  timeOutline,
} from 'ionicons/icons';
import { api } from './api';
import { schedulePalette } from './scheduleClientPalette';
import './wiw-schedule-mobile.css';

const TZ = 'Europe/Berlin';
const unpack = (value: any): any[] => value?.results || value || [];
const pad = (value: number) => String(value).padStart(2, '0');

function berlinToday() {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
  const get = (type: string) => parts.find((part) => part.type === type)?.value || '';
  return `${get('year')}-${get('month')}-${get('day')}`;
}
function keyDate(key: string) {
  const [year, month, day] = key.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1, day, 12));
}
function keyFromDate(date: Date) {
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}`;
}
function addDays(key: string, amount: number) {
  const date = keyDate(key);
  date.setUTCDate(date.getUTCDate() + amount);
  return keyFromDate(date);
}
function monday(key: string) {
  const date = keyDate(key);
  const weekday = date.getUTCDay();
  date.setUTCDate(date.getUTCDate() + (weekday === 0 ? -6 : 1 - weekday));
  return keyFromDate(date);
}
function dateKey(input?: string) {
  if (!input) return '';
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date(input));
  const get = (type: string) => parts.find((part) => part.type === type)?.value || '';
  return `${get('year')}-${get('month')}-${get('day')}`;
}
function time(input?: string) {
  return input ? new Intl.DateTimeFormat('de-DE', { timeZone: TZ, hour: '2-digit', minute: '2-digit' }).format(new Date(input)) : '–';
}
function fullDate(input?: string) {
  return input ? new Intl.DateTimeFormat('de-DE', { timeZone: TZ, weekday: 'long', day: '2-digit', month: '2-digit', year: 'numeric' }).format(new Date(input)) : '–';
}
function dayLabel(key: string) {
  return new Intl.DateTimeFormat('de-DE', { timeZone: 'UTC', weekday: 'short' }).format(keyDate(key));
}
function formatDayHeader(key: string) {
  return {
    weekday: new Intl.DateTimeFormat('de-DE', { timeZone: 'UTC', weekday: 'short' }).format(keyDate(key)),
    date: new Intl.DateTimeFormat('de-DE', { timeZone: 'UTC', day: '2-digit', month: '2-digit', year: 'numeric' }).format(keyDate(key)),
  };
}
function hours(shift: any) {
  if (!shift?.starts_at || !shift?.ends_at) return 0;
  const gross = Math.max(0, (new Date(shift.ends_at).getTime() - new Date(shift.starts_at).getTime()) / 3600000);
  return Math.max(0, gross - Number(shift.break_minutes || 0) / 60);
}
function shortPersonName(value?: string) {
  const parts = String(value || '').trim().split(/\s+/).filter(Boolean);
  if (parts.length <= 1) return parts[0] || '';
  return `${parts[0]} ${parts.slice(1).map((part) => `${part.charAt(0)}.`).join(' ')}`;
}
function workerInitials(value?: string) {
  const parts = String(value || '').trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return 'MA';
  return `${parts[0]?.[0] || ''}${parts.length > 1 ? parts[parts.length - 1]?.[0] || '' : ''}`.toLocaleUpperCase('de-DE') || 'MA';
}
function normalizeWorker(worker: any) {
  if (!worker) return undefined;
  const name = worker.name || worker.user_detail?.name || worker.worker_name || worker.email || 'Mitarbeiter';
  return {
    ...worker,
    name,
    avatar: worker.avatar || worker.photo_url || worker.photo || worker.image || worker.user_detail?.avatar || undefined,
  };
}
function activeSlots(shift: any) {
  if (Array.isArray(shift?.slot_cards) && shift.slot_cards.length) return shift.slot_cards;
  const assigned = Array.isArray(shift?.assigned_workers) ? shift.assigned_workers : [];
  const cards: any[] = assigned.map((worker: any, index: number) => ({
    id: worker.slot_id || `assigned-${index}`,
    status: 'claimed',
    worker: normalizeWorker(worker),
    is_open: false,
  }));
  const fallbackNames = Array.isArray(shift?.worker_names) ? shift.worker_names : [];
  fallbackNames.forEach((name: string, index: number) => cards.push({ id: `named-${index}`, status: 'claimed', worker: { name }, is_open: false }));
  if (!cards.length && (shift?.worker_name || shift?.assigned_worker_name)) {
    cards.push({ id: 'named-worker', status: 'claimed', worker: { name: shift.worker_name || shift.assigned_worker_name }, is_open: false });
  }
  const open = Math.max(0, Number(shift?.open_count || 0));
  for (let index = 0; index < open; index += 1) cards.push({ id: `open-${index}`, status: 'open', worker: null, is_open: true });
  if (!cards.length) cards.push({ id: `shift-${shift?.id}`, status: shift?.status === 'draft' ? 'open' : 'claimed', worker: null, is_open: false });
  return cards;
}
function shiftCardStyle(shift: any) {
  const palette = schedulePalette(shift?.client_name, shift?.position_name, shift?.color_hue);
  return {
    '--wiw-client-hue': String(palette.hue),
    '--wiw-card-accent': palette.accent,
    '--wiw-card-open-bg': palette.openBackground,
    '--wiw-card-filled-bg': palette.filledBackground,
    '--wiw-card-open-text': palette.openText,
    '--wiw-card-filled-text': palette.filledText,
    '--wiw-card-open-muted': palette.openMuted,
    '--wiw-card-filled-muted': palette.filledMuted,
  } as React.CSSProperties;
}

function WorkerAvatar({ worker }: { worker?: any }) {
  const normalized = normalizeWorker(worker);
  if (!normalized) return <span className="wiw-worker-avatar-shell" aria-hidden="true"><span className="wiw-worker-avatar wiw-worker-avatar-fallback">–</span></span>;
  return <span className="wiw-worker-avatar-shell" aria-hidden="true">
    <span className="wiw-worker-avatar wiw-worker-avatar-fallback">{workerInitials(normalized.name)}</span>
    {normalized.avatar ? <img className="wiw-worker-avatar wiw-worker-avatar-image" src={normalized.avatar} alt="" onError={(event) => event.currentTarget.remove()} /> : null}
  </span>;
}

type ClientCard = { key: string; shift: any; slot: any; worker?: any; isOpen: boolean };
type ScheduleFilter = 'all' | 'filled' | 'open';

export function ClientScheduleMobile() {
  const [rows, setRows] = useState<any[]>([]);
  const [anchor, setAnchor] = useState(berlinToday());
  const [filter, setFilter] = useState<ScheduleFilter>('all');
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<ClientCard>();
  const [touch, setTouch] = useState<{ x: number; y: number }>();

  const load = async () => {
    setBusy(true);
    setError('');
    try {
      const result = await api('shifts/?ordering=starts_at');
      setRows(unpack(result));
    } catch (reason: any) {
      setError(reason?.message || 'Einsätze konnten nicht geladen werden.');
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => { void load(); }, []);

  const weekStart = monday(anchor);
  const days = useMemo(() => Array.from({ length: 7 }, (_, index) => addDays(weekStart, index)), [weekStart]);
  const cards = useMemo<ClientCard[]>(() => rows.flatMap((shift) => activeSlots(shift).map((slot: any, index: number) => ({
    key: `${shift.id}:${slot.id || index}`,
    shift,
    slot,
    worker: normalizeWorker(slot.worker),
    isOpen: Boolean(slot.is_open || (slot.status === 'open' && !slot.worker)),
  }))), [rows]);
  const visible = useMemo(() => cards.filter((card) => {
    if (!days.includes(dateKey(card.shift.starts_at))) return false;
    if (card.shift.status === 'cancelled') return false;
    if (filter === 'filled' && (card.isOpen || !card.worker)) return false;
    if (filter === 'open' && !card.isOpen) return false;
    return true;
  }), [cards, days, filter]);
  const byDay = useMemo(() => {
    const map: Record<string, ClientCard[]> = Object.fromEntries(days.map((day) => [day, []]));
    visible.forEach((card) => (map[dateKey(card.shift.starts_at)] ||= []).push(card));
    Object.values(map).forEach((items) => items.sort((left, right) => new Date(left.shift.starts_at).getTime() - new Date(right.shift.starts_at).getTime()));
    return map;
  }, [days, visible]);
  const totalHours = useMemo(() => visible.reduce((sum, card) => sum + hours(card.shift), 0), [visible]);

  if (selected) {
    const workerName = selected.worker?.name || (selected.isOpen ? 'Noch offen' : 'Noch nicht zugewiesen');
    return <section className="client-v2-custom-screen client-v3-shift-detail" data-testid="client-v3-shift-detail">
      <header className="client-v3-detail-head"><button type="button" onClick={() => setSelected(undefined)} aria-label="Zurück"><IonIcon icon={chevronBackOutline}/></button><div><small>KUNDENPORTAL</small><b>Einsatzdetails</b></div><span/></header>
      <div className="client-v3-detail-hero" style={shiftCardStyle(selected.shift)}><WorkerAvatar worker={selected.worker}/><div><small>{selected.shift.position_name || 'Einsatz'}</small><h2>{workerName}</h2><p>{selected.shift.location_name || 'Einsatzort'}</p></div></div>
      <div className="client-v3-detail-list">
        <div><IonIcon icon={calendarOutline}/><span><small>Datum</small><b>{fullDate(selected.shift.starts_at)}</b></span></div>
        <div><IonIcon icon={timeOutline}/><span><small>Zeit</small><b>{time(selected.shift.starts_at)} – {time(selected.shift.ends_at)}</b></span></div>
        <div><IonIcon icon={briefcaseOutline}/><span><small>Position</small><b>{selected.shift.position_name || 'Einsatz'}</b></span></div>
        <div><IonIcon icon={locationOutline}/><span><small>Einsatzort</small><b>{selected.shift.location_name || '–'}</b></span></div>
        <div><IonIcon icon={personOutline}/><span><small>Mitarbeiter</small><b>{workerName}</b></span></div>
      </div>
    </section>;
  }

  return <section className="client-v2-custom-screen client-v3-schedule wiw-schedule-mobile" data-testid="client-v3-schedule">
    <div className="client-v3-schedule-tabs wiw-schedule-tools">
      <div className="wiw-tabs" role="tablist" aria-label="Einsatzfilter">
        <button type="button" role="tab" aria-selected={filter === 'all'} className={filter === 'all' ? 'active' : ''} onClick={() => setFilter('all')}>Alle</button>
        <button type="button" role="tab" aria-selected={filter === 'filled'} className={filter === 'filled' ? 'active' : ''} onClick={() => setFilter('filled')}>Besetzt</button>
        <button type="button" role="tab" aria-selected={filter === 'open'} className={filter === 'open' ? 'active' : ''} onClick={() => setFilter('open')}>Offen</button>
      </div>
    </div>
    <div className="wiw-week-strip client-v3-week-strip" data-testid="client-v3-week-strip">
      <button type="button" aria-label="Vorherige Woche" onClick={() => setAnchor(addDays(anchor, -7))}>‹</button>
      {days.map((day) => <button type="button" key={day} className={`${day === anchor ? 'active ' : ''}${day === berlinToday() ? 'today' : ''}`} onClick={() => setAnchor(day)}><small>{dayLabel(day).slice(0, 2)}</small><b>{keyDate(day).getUTCDate()}</b></button>)}
      <button type="button" aria-label="Nächste Woche" onClick={() => setAnchor(addDays(anchor, 7))}>›</button>
    </div>
    {error ? <div className="client-v3-state error"><b>{error}</b><button type="button" onClick={() => void load()}>Erneut versuchen</button></div> : null}
    {busy && !rows.length ? <div className="client-v3-state"><IonSpinner/><span>Einsätze werden geladen …</span></div> : null}
    {!busy || rows.length ? <div className="wiw-week-scroll client-v3-week-scroll" data-testid="client-v3-schedule-days"
      onTouchStart={(event) => { const point = event.touches[0]; setTouch({ x: point.clientX, y: point.clientY }); }}
      onTouchEnd={(event) => {
        if (!touch || !event.changedTouches.length) return;
        const point = event.changedTouches[0];
        const dx = point.clientX - touch.x;
        const dy = point.clientY - touch.y;
        setTouch(undefined);
        if (Math.abs(dx) > 55 && Math.abs(dx) > Math.abs(dy) * 1.2) setAnchor(addDays(anchor, dx < 0 ? 7 : -7));
      }}>
      {days.map((day) => {
        const header = formatDayHeader(day);
        const dayCards = byDay[day] || [];
        return <section className="wiw-day-section wiw-day-visual" key={day}>
          <header><span className="wiw-day-header-spacer"/><div className="wiw-day-heading"><strong>{header.weekday}</strong><span>{header.date}</span></div><em>{dayCards.length}</em></header>
          {dayCards.map((card) => {
            const workerName = card.worker?.name ? shortPersonName(card.worker.name) : (card.isOpen ? 'Offen' : 'Noch nicht zugewiesen');
            return <button type="button" key={card.key} className={`wiw-shift-card ${card.isOpen ? 'is-open' : 'is-filled'} client-v3-shift-card`} style={shiftCardStyle(card.shift)} onClick={() => setSelected(card)}>
              <div className="wiw-card-line primary"><span className="wiw-card-person"><WorkerAvatar worker={card.worker}/><b>{workerName}</b></span><span>{time(card.shift.starts_at)}–{time(card.shift.ends_at)}</span></div>
              <div className="wiw-card-line secondary"><span className={card.isOpen ? 'open' : ''}>{card.shift.position_name || 'Einsatz'}</span><small>{card.shift.location_name || 'Einsatzort'}</small></div>
            </button>;
          })}
          {!dayCards.length ? <div className="wiw-day-empty">Keine Einsätze</div> : null}
        </section>;
      })}
    </div> : null}
    <div className="wiw-week-total client-v3-week-total"><span>Gesamtstunden</span><strong>{totalHours.toFixed(1)}</strong></div>
  </section>;
}

type RatingForm = { worker: string; shift: string; score: number; punctuality: number; quality: number; teamwork: number; comment: string };
const emptyRating = (): RatingForm => ({ worker: '', shift: '', score: 5, punctuality: 5, quality: 5, teamwork: 5, comment: '' });

function RatingStars({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  return <div className="client-v3-stars" role="radiogroup" aria-label="Sterne">
    {[1, 2, 3, 4, 5].map((score) => <button type="button" key={score} aria-label={`${score} Sterne`} aria-checked={value === score} role="radio" onClick={() => onChange(score)}><IonIcon icon={score <= value ? star : starOutline}/></button>)}
  </div>;
}

export function ClientRatingsMobile() {
  const [rows, setRows] = useState<any[]>([]);
  const [candidates, setCandidates] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<RatingForm>(emptyRating());
  const [busy, setBusy] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  const load = async () => {
    setBusy(true);
    try {
      const [ratingData, candidateData] = await Promise.all([api('ratings/'), api('portal/rating-candidates/')]);
      setRows(unpack(ratingData));
      setCandidates(unpack(candidateData));
    } catch (reason: any) {
      setMessage(reason?.message || 'Bewertungen konnten nicht geladen werden.');
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => { void load(); }, []);

  const shifts = useMemo(() => {
    const map = new Map<string, any>();
    candidates.forEach((candidate) => {
      if (!map.has(candidate.shift_id)) map.set(candidate.shift_id, candidate);
    });
    return Array.from(map.values()).sort((a, b) => new Date(b.starts_at).getTime() - new Date(a.starts_at).getTime());
  }, [candidates]);
  const workers = useMemo(() => candidates.filter((candidate) => !form.shift || candidate.shift_id === form.shift), [candidates, form.shift]);

  const submit = async () => {
    if (!form.shift || !form.worker) {
      setMessage('Bitte zuerst Einsatz und Mitarbeiter auswählen.');
      return;
    }
    setSaving(true);
    setMessage('');
    try {
      await api('ratings/', { method: 'POST', body: JSON.stringify(form) });
      setOpen(false);
      setForm(emptyRating());
      setMessage('Bewertung wurde gespeichert.');
      await load();
    } catch (reason: any) {
      setMessage(reason?.message || 'Bewertung konnte nicht gespeichert werden.');
    } finally {
      setSaving(false);
    }
  };

  return <section className="client-v2-custom-screen client-v3-ratings" data-testid="client-v3-ratings">
    <div className="client-v3-page-intro"><div><small>KUNDENPORTAL</small><h1>Mitarbeiter bewerten</h1><p>Feedback zu abgeschlossenen Einsätzen – schnell, klar und direkt.</p></div><span><IonIcon icon={starOutline}/></span></div>
    <button type="button" className="client-v3-primary-action" onClick={() => { setForm(emptyRating()); setOpen(true); }}><IonIcon icon={starOutline}/><span><b>Neue Bewertung</b><small>Abgeschlossenen Einsatz auswählen</small></span></button>
    {message ? <div className="client-v3-inline-message">{message}</div> : null}
    <div className="client-v3-rating-list">
      {busy ? <div className="client-v3-state"><IonSpinner/><span>Bewertungen werden geladen …</span></div> : null}
      {!busy && !rows.length ? <div className="client-v3-rating-empty"><span><IonIcon icon={starOutline}/></span><h2>Noch keine Bewertungen</h2><p>Nach einem abgeschlossenen Einsatz kannst du hier direkt Feedback geben.</p></div> : null}
      {rows.map((rating) => <article key={rating.id} className="client-v3-rating-card"><div className="client-v3-rating-avatar">{workerInitials(rating.worker_name)}</div><div><b>{rating.worker_name || 'Mitarbeiter'}</b><small>{rating.created_at ? new Date(rating.created_at).toLocaleDateString('de-DE', { timeZone: TZ }) : ''}{rating.comment ? ` · ${rating.comment}` : ''}</small></div><strong><IonIcon icon={star}/>{Number(rating.score || 0).toFixed(1)}</strong></article>)}
    </div>

    {open ? <div className="client-v3-sheet-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !saving) setOpen(false); }}>
      <section className="client-v3-rating-sheet" role="dialog" aria-modal="true" aria-labelledby="client-rating-title">
        <div className="client-v3-sheet-handle"/>
        <header><div><small>FEEDBACK</small><h2 id="client-rating-title">Einsatz bewerten</h2></div><button type="button" disabled={saving} onClick={() => setOpen(false)}>Fertig</button></header>
        <label><span>Einsatz</span><select aria-label="Einsatz" value={form.shift} onChange={(event) => setForm({ ...form, shift: event.target.value, worker: '' })}><option value="">Einsatz auswählen</option>{shifts.map((candidate) => <option value={candidate.shift_id} key={candidate.shift_id}>{candidate.position_name || 'Einsatz'} · {fullDate(candidate.starts_at)} · {time(candidate.starts_at)}</option>)}</select></label>
        <label><span>Mitarbeiter</span><select aria-label="Mitarbeiter" value={form.worker} disabled={!form.shift} onChange={(event) => setForm({ ...form, worker: event.target.value })}><option value="">Mitarbeiter auswählen</option>{workers.map((candidate) => <option value={candidate.worker_id} key={`${candidate.shift_id}:${candidate.worker_id}`}>{candidate.worker_name}</option>)}</select></label>
        {([
          ['score', 'Gesamtbewertung'],
          ['punctuality', 'Pünktlichkeit'],
          ['quality', 'Qualität'],
          ['teamwork', 'Teamarbeit'],
        ] as const).map(([key, label]) => <div className="client-v3-rating-metric" key={key}><div><b>{label}</b><small>{form[key]}/5</small></div><RatingStars value={form[key]} onChange={(score) => setForm({ ...form, [key]: score })}/></div>)}
        <label><span>Kommentar <small>optional</small></span><textarea value={form.comment} onChange={(event) => setForm({ ...form, comment: event.target.value })} placeholder="Kurzes Feedback zum Einsatz …"/></label>
        <button type="button" className="client-v3-save-rating" disabled={saving || !form.shift || !form.worker} onClick={() => void submit()}>{saving ? <IonSpinner/> : <><IonIcon icon={star}/><span>Bewertung speichern</span></>}</button>
      </section>
    </div> : null}
  </section>;
}
