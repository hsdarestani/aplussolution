import React, { useEffect, useMemo, useRef, useState } from 'react';
import { IonIcon, IonSpinner } from '@ionic/react';
import {
  briefcaseOutline,
  calendarOutline,
  chevronBackOutline,
  locationOutline,
  personOutline,
  timeOutline,
} from 'ionicons/icons';
import { api } from './api';
import { schedulePalette } from './scheduleClientPalette';
import './wiw-schedule-mobile.css';
import './wiw-employee-schedule-mobile.css';

const TZ = 'Europe/Berlin';
const unpack = (value: any): any[] => value?.results || value || [];
const pad = (value: number) => String(value).padStart(2, '0');
const normalize = (value: string) => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]/g, '');

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
  return input ? new Intl.DateTimeFormat('de-DE', { timeZone: TZ, weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(input)) : '–';
}
function dayLabel(key: string) {
  return new Intl.DateTimeFormat('de-DE', { timeZone: 'UTC', weekday: 'short' }).format(keyDate(key));
}
function formatDayHeader(key: string) {
  return {
    weekday: dayLabel(key),
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
  const first = parts[0]?.[0] || '';
  const last = parts.length > 1 ? parts[parts.length - 1]?.[0] || '' : '';
  return `${first}${last}`.toLocaleUpperCase('de-DE') || 'MA';
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
function WorkerAvatar({ worker }: { worker?: any }) {
  const normalized = normalizeWorker(worker);
  if (!normalized) return null;
  return <span className="wiw-worker-avatar-shell" aria-hidden="true">
    <span className="wiw-worker-avatar wiw-worker-avatar-fallback">{workerInitials(normalized.name)}</span>
    {normalized.avatar ? <img className="wiw-worker-avatar wiw-worker-avatar-image" src={normalized.avatar} alt="" onError={(event) => event.currentTarget.remove()} /> : null}
  </span>;
}
function positionShortLabel(name?: string) {
  const key = normalize(String(name || ''));
  if (key.includes('serviceleitung')) return 'SL';
  if (key.includes('servicekraft') || key.includes('servicekrat')) return 'SK';
  if (key.includes('frontoffice') || key.includes('rezeption') || key.includes('reception')) return 'FO';
  if (key.includes('housekeeping') || key.includes('houskeeping') || key.includes('zimmer')) return 'HK';
  if (key.includes('bar')) return 'Bar';
  return String(name || 'Einsatz');
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
  if (!cards.length && (shift?.worker_name || shift?.assigned_worker_name)) cards.push({ id: 'named-worker', status: 'claimed', worker: { name: shift.worker_name || shift.assigned_worker_name }, is_open: false });
  const open = Math.max(0, Number(shift?.open_count || 0));
  for (let index = 0; index < open; index += 1) cards.push({ id: `open-${index}`, status: 'open', worker: null, is_open: true });
  if (!cards.length) cards.push({ id: `shift-${shift?.id}`, status: 'claimed', worker: null, is_open: false });
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

type ClientCard = { key: string; shift: any; slot: any; worker?: any; isOpen: boolean };

function DetailRow({ icon, children }: { icon: string; children: React.ReactNode }) {
  return <div className="wiw-employee-detail-row"><IonIcon icon={icon} /><span>{children}</span></div>;
}

export default function ClientScheduleWorkforceMobile() {
  const [rows, setRows] = useState<any[]>([]);
  const [anchor, setAnchor] = useState(berlinToday());
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<ClientCard>();
  const [weekDirection, setWeekDirection] = useState<'next' | 'prev' | ''>('');
  const swipe = useRef<{ x: number; y: number } | undefined>(undefined);
  const swipeTravel = useRef(0);
  const swipeFrame = useRef<number | undefined>(undefined);
  const directionTimer = useRef<number | undefined>(undefined);

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
  useEffect(() => () => {
    if (swipeFrame.current) window.cancelAnimationFrame(swipeFrame.current);
    if (directionTimer.current) window.clearTimeout(directionTimer.current);
  }, []);

  const weekStart = monday(anchor);
  const days = useMemo(() => Array.from({ length: 7 }, (_, index) => addDays(weekStart, index)), [weekStart]);
  const cards = useMemo<ClientCard[]>(() => rows.flatMap((shift) => activeSlots(shift).map((slot: any, index: number) => ({
    key: `${shift.id}:${slot.id || index}`,
    shift,
    slot,
    worker: normalizeWorker(slot.worker),
    isOpen: Boolean(slot.is_open || (slot.status === 'open' && !slot.worker)),
  }))), [rows]);
  const visible = useMemo(() => cards.filter((card) => days.includes(dateKey(card.shift.starts_at)) && card.shift.status !== 'cancelled'), [cards, days]);
  const byDay = useMemo(() => {
    const map: Record<string, ClientCard[]> = Object.fromEntries(days.map((day) => [day, []]));
    visible.forEach((card) => (map[dateKey(card.shift.starts_at)] ||= []).push(card));
    Object.values(map).forEach((items) => items.sort((left, right) => new Date(left.shift.starts_at).getTime() - new Date(right.shift.starts_at).getTime()));
    return map;
  }, [days, visible]);
  const totalHours = useMemo(() => visible.reduce((sum, card) => sum + hours(card.shift), 0), [visible]);

  function changeWeek(delta: number) {
    if (directionTimer.current) window.clearTimeout(directionTimer.current);
    setWeekDirection(delta > 0 ? 'next' : 'prev');
    setAnchor((current) => addDays(current, delta));
    directionTimer.current = window.setTimeout(() => setWeekDirection(''), 430);
  }

  if (selected) {
    const workerName = selected.worker?.name || (selected.isOpen ? 'OpenShift' : 'Noch nicht zugewiesen');
    return <div className="client-v2-custom-screen wiw-employee-shift-detail" data-testid="client-v3-shift-detail">
      <header className="wiw-employee-detail-topbar">
        <button type="button" aria-label="Zurück" onClick={() => setSelected(undefined)}><IonIcon icon={chevronBackOutline} /></button>
        <strong>Einsatzdetails</strong>
        <span />
      </header>
      <div className="wiw-employee-detail-list">
        <DetailRow icon={calendarOutline}>{fullDate(selected.shift.starts_at)}</DetailRow>
        <DetailRow icon={timeOutline}>{time(selected.shift.starts_at)} – {time(selected.shift.ends_at)}</DetailRow>
        <DetailRow icon={briefcaseOutline}>{selected.shift.position_name || 'Einsatz'}</DetailRow>
        <DetailRow icon={locationOutline}>{selected.shift.location_name || 'Einsatzort'}</DetailRow>
        <DetailRow icon={personOutline}>{workerName}</DetailRow>
      </div>
    </div>;
  }

  return <div className="client-v2-custom-screen wiw-employee-schedule wiw-schedule-mobile wiw-employee-admin-parity" data-testid="client-v3-schedule">
    <div className="wiw-week-strip" data-testid="phase8-week-strip">
      <button type="button" aria-label="Vorherige Woche" onClick={() => changeWeek(-7)}>‹</button>
      {days.map((day) => <button type="button" key={day} className={`${day === anchor ? 'active ' : ''}${day === berlinToday() ? 'today' : ''}`} onClick={() => setAnchor(day)}><small>{dayLabel(day).slice(0, 2)}</small><b>{keyDate(day).getUTCDate()}</b></button>)}
      <button type="button" aria-label="Nächste Woche" onClick={() => changeWeek(7)}>›</button>
    </div>

    {error ? <div className="wiw-employee-message"><b>{error}</b> <button type="button" onClick={() => void load()}>Erneut versuchen</button></div> : null}
    {busy && !rows.length ? <div className="wiw-day-empty"><IonSpinner /> Einsätze werden geladen …</div> : null}

    {!busy || rows.length ? <div
      key={weekStart}
      className={`wiw-week-scroll ${weekDirection ? `wiw-week-turn-${weekDirection}` : ''}`}
      data-testid="schedule-day-view"
      data-layout="list"
      style={{ paddingBottom: 'calc(124px + env(safe-area-inset-bottom))' }}
      onTouchStart={(event) => {
        const point = event.touches[0];
        swipe.current = { x: point.clientX, y: point.clientY };
        swipeTravel.current = 0;
        event.currentTarget.classList.add('is-swipe-dragging');
      }}
      onTouchMove={(event) => {
        if (!swipe.current || !event.touches.length) return;
        const point = event.touches[0];
        const dx = point.clientX - swipe.current.x;
        const dy = point.clientY - swipe.current.y;
        if (Math.abs(dx) < Math.abs(dy) * 1.08) return;
        swipeTravel.current = Math.max(-105, Math.min(105, dx * .5));
        if (swipeFrame.current) return;
        const target = event.currentTarget;
        swipeFrame.current = window.requestAnimationFrame(() => {
          swipeFrame.current = undefined;
          target.style.transform = `translate3d(${swipeTravel.current}px,0,0)`;
          target.style.opacity = String(Math.max(.72, 1 - Math.abs(swipeTravel.current) / 430));
        });
      }}
      onTouchEnd={(event) => {
        if (swipeFrame.current) window.cancelAnimationFrame(swipeFrame.current);
        swipeFrame.current = undefined;
        event.currentTarget.classList.remove('is-swipe-dragging');
        event.currentTarget.style.transform = '';
        event.currentTarget.style.opacity = '';
        if (!swipe.current || !event.changedTouches.length) return;
        const point = event.changedTouches[0];
        const dx = point.clientX - swipe.current.x;
        const dy = point.clientY - swipe.current.y;
        swipe.current = undefined;
        if (Math.abs(dx) > 44 && Math.abs(dx) > Math.abs(dy) * 1.12) changeWeek(dx < 0 ? 7 : -7);
      }}
      onTouchCancel={(event) => {
        if (swipeFrame.current) window.cancelAnimationFrame(swipeFrame.current);
        swipeFrame.current = undefined;
        swipe.current = undefined;
        event.currentTarget.classList.remove('is-swipe-dragging');
        event.currentTarget.style.transform = '';
        event.currentTarget.style.opacity = '';
      }}
    >
      {days.map((day) => {
        const header = formatDayHeader(day);
        const dayCards = byDay[day] || [];
        return <section className="wiw-day-section wiw-day-visual" id={`wiw-client-day-${day}`} key={day}>
          <header><span className="wiw-day-header-spacer"/><div className="wiw-day-heading"><strong>{header.weekday}</strong><span>{header.date}</span></div><em>{dayCards.length}</em></header>
          {dayCards.map((card) => {
            const workerName = card.worker?.name ? shortPersonName(card.worker.name) : (card.isOpen ? 'OpenShift' : 'Noch nicht zugewiesen');
            return <button type="button" key={card.key} className={`wiw-shift-card ${card.isOpen ? 'is-open' : 'is-filled'}`} style={shiftCardStyle(card.shift)} onClick={() => setSelected(card)}>
              <div className="wiw-card-line primary">
                <span className="wiw-card-person"><WorkerAvatar worker={card.worker} /><b>{workerName}{card.isOpen ? <span className="wiw-open-alert">!</span> : null}</b></span>
                <span>{time(card.shift.starts_at)}–{time(card.shift.ends_at)}</span>
              </div>
              <div className="wiw-card-line secondary"><span className={card.isOpen ? 'open' : ''}>{positionShortLabel(card.shift.position_name)}</span><small>{card.shift.location_name || 'Einsatzort'}</small></div>
            </button>;
          })}
          {!dayCards.length ? <div className="wiw-day-empty">Keine Einsätze</div> : null}
        </section>;
      })}
    </div> : null}

    <div className="wiw-week-total" data-testid="phase8-week-total" style={{ position: 'fixed', left: 0, right: 0, bottom: 'calc(58px + env(safe-area-inset-bottom))', zIndex: 120, height: 54, minHeight: 54, padding: '0 18px', margin: 0 }}>
      <span>Gesamtstunden</span><strong>{totalHours.toFixed(1)}</strong>
    </div>
  </div>;
}
