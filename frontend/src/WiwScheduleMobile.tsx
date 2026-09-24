// SEP14_WEEK_SWIPE_STABILITY
// SEP14_WEEK_SWIPE_HANDOFF
// SEP14_PREVIEW_PARITY
// MODERN_WEEK_CACHE_NAVIGATION
import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal, flushSync } from 'react-dom';
import { Capacitor } from '@capacitor/core';
import { Haptics, ImpactStyle } from '@capacitor/haptics';
import { IonIcon } from '@ionic/react';
import {
  addCircleOutline,
  briefcaseOutline,
  calendarOutline,
  checkmarkOutline,
  chevronForwardOutline,
  colorPaletteOutline,
  copyOutline,
  documentTextOutline,
  filterOutline,
  layersOutline,
  locationOutline,
  notificationsOutline,
  peopleOutline,
  personOutline,
  timeOutline,
  trashOutline,
} from 'ionicons/icons';
import { api, apiBlob } from './api';
import ScheduleDatePicker from './ScheduleDatePicker';
import { saveSchedulePdf } from './saveSchedulePdf';
import { isHotelClientName, schedulePalette } from './scheduleClientPalette';
import './wiw-schedule-mobile.css';

type TabKey = 'all' | 'open' | 'filled' | 'draft';
type Choice = { value: string; label: string };
type ColorChoice = { value: string; label: string; hue: number | null };
type EditingCard = { shiftId: string; slotId: string; parentCount: number; workerName?: string; workerId?: string; isOpen: boolean; timeEntries?: any[] };
type FormState = {
  client: string;
  date: string;
  startMinute: number | null;
  endAbsolute: number | null;
  position: string;
  location: string;
  required_count: number;
  publish_now: boolean;
  confirmation_required: boolean;
  workers: string[];
  schedule_groups: string[];
  color_hue: number | null;
  notes: string;
  apply_all: boolean;
};
type PdfState = {
  dateFrom: string;
  dateTo: string;
  workers: string[];
  clients: string[];
  groups: string[];
};

type CardRow = {
  key: string;
  shift: any;
  slot: any;
  worker?: any;
  isOpen: boolean;
};

const BERLIN = 'Europe/Berlin';
const QUARTER = 15;
const WHEEL_ROW = 32;
const META_CACHE_KEY = 'aplus:wiw-mobile-meta:v5';
const WEEK_CACHE_PREFIX = 'aplus:wiw-mobile-week:v4:';
const POSITION_ORDER = [
  { label: 'Servicekraft', aliases: ['servicekraft', 'servicekrat'] },
  { label: 'Serviceleitung', aliases: ['serviceleitung'] },
  { label: 'Bar', aliases: ['bar', 'barsupport'] },
  { label: 'Front-Office', aliases: ['frontoffice'] },
  { label: 'Housekeeping', aliases: ['housekeeping', 'houskeeping'] },
];
const SCHEDULE_GROUPS: Choice[] = [
  { value: 'service', label: 'Service' },
  { value: 'front_office', label: 'Front Office' },
  { value: 'housekeeping', label: 'Housekeeping' },
];
const WORKER_PICKER_NAMES = [
  'Tooba Amjad',
  'Shahrzad Bagheri',
  'Michelle Brettschneider',
  'Michele Corrado',
  'Loreen Gawlitza',
  'Katerina Gentsou',
  'Yohannes Kiffle',
  'Ksenia Marszalek',
  'Arina Martynko',
  'Claire Odinius',
  'Ilhan Omerovic',
  'Ilayda Tarhan',
  'Francesco Trulli',
  'Akeel Zafar',
  'Izabella Somodo',
  'Musa Jamali',
  'Max Najmudinov',
];
const CLIENT_ORDER = ['marthasfinest','stadthausammarkt','hotelspenerhaus','hofelcatering','restauranthirschgarten','messe','ommia','citybeach','hofgut'];
const HOTEL_TIME_PRESETS = [
  { key: 'early', label: 'Frühdienst', start: 6 * 60 + 30, end: 15 * 60 },
  { key: 'late', label: 'Spätdienst', start: 14 * 60 + 45, end: 22 * 60 + 45 },
  { key: 'night', label: 'Nachtdienst', start: 22 * 60 + 30, end: 24 * 60 + 6 * 60 + 30 },
];
const clientRank = (name?: string) => { const key = normalize(String(name || '')); const index = CLIENT_ORDER.findIndex((item) => key.includes(item) || item.includes(key)); return index < 0 ? CLIENT_ORDER.length : index; };
const sortClients = (items: any[]) => [...items].sort((a, b) => clientRank(a?.name) - clientRank(b?.name) || String(a?.name || '').localeCompare(String(b?.name || ''), 'de'));
const COLOR_CHOICES: ColorChoice[] = [
  { value: 'auto', label: 'Kundenfarbe · automatisch', hue: null },
  { value: 'navy', label: 'Navy', hue: 205 },
  { value: 'blue', label: 'Blau', hue: 220 },
  { value: 'teal', label: 'Türkis', hue: 180 },
  { value: 'green', label: 'Grün', hue: 120 },
  { value: 'yellow', label: 'Gelb', hue: 48 },
  { value: 'orange', label: 'Orange', hue: 28 },
  { value: 'red', label: 'Rot', hue: 0 },
  { value: 'pink', label: 'Pink', hue: 330 },
  { value: 'violet', label: 'Violett', hue: 275 },
];
const unpack = (value: any): any[] => value?.results || value || [];
const pad = (value: number) => String(value).padStart(2, '0');
const normalize = (value: string) => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]/g, '');
const clientKey = (item: any) => String(item?.client || item?.client_name || 'ohne-kunde');
const allowedWorkerNames = new Set(WORKER_PICKER_NAMES.map(normalize));

function cardWorkerInitials(worker?: any) {
  const source = String(worker?.name || worker?.employee_number || '').trim();
  const parts = source.split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] || '') + (parts.length > 1 ? parts[parts.length - 1]?.[0] || '' : '')).toUpperCase() || 'MA';
}

function cardWorkerShortName(value?: string) {
  const parts = String(value || '').trim().split(/\s+/).filter(Boolean);
  if (parts.length <= 1) return parts[0] || '';
  const last = parts[parts.length - 1];
  return `${parts[0]} ${(last[0] || '').toLocaleUpperCase('de-DE')}.`;
}

function cardPositionShortLabel(name?: string) {
  const key = normalize(String(name || ''));
  if (key.includes('serviceleitung')) return 'SL';
  if (key.includes('servicekraft') || key.includes('servicekrat')) return 'SK';
  if (key.includes('frontoffice') || key.includes('rezeption') || key.includes('reception')) return 'FO';
  if (key.includes('housekeeping') || key.includes('houskeeping') || key.includes('zimmer')) return 'HK';
  if (key.includes('bar')) return 'Bar';
  return String(name || 'Schicht');
}

function adminInputDateTime(value?: string) {
  if (!value) return '';
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: BERLIN,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(new Date(value));
  const get = (type: string) => parts.find((part) => part.type === type)?.value || '';
  return `${get('year')}-${get('month')}-${get('day')}T${get('hour')}:${get('minute')}`;
}
function adminLogStamp(value?: string) {
  return value ? new Intl.DateTimeFormat('de-DE', {
    timeZone: BERLIN, day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  }).format(new Date(value)) : '–';
}
function adminWorkedLabel(value?: number) {
  const minutes = Math.max(0, Number(value || 0));
  return `${Math.floor(minutes / 60)}:${pad(minutes % 60)} Std.`;
}
function adminTimeSource(source?: string) {
  if (source === 'wiw') return 'WIW';
  if (source === 'employee_manual') return 'Mitarbeiter · manuell';
  if (source === 'location') return 'Standort-Erfassung';
  return 'Administration';
}
function adminAuditLabel(action?: string) {
  return ({
    'time.admin_shift_created': 'Admin · angelegt',
    'time.admin_shift_updated': 'Admin · bearbeitet',
    'time.shift_reported': 'Mitarbeiter · gemeldet',
    'time.approved': 'Admin · freigegeben',
    'time.clock_in': 'Check-in',
    'time.clock_out': 'Check-out',
    'timeentry.created': 'Eintrag angelegt',
    'timeentry.updated': 'Eintrag bearbeitet',
  } as Record<string, string>)[String(action || '')] || String(action || '');
}

function CardWorkerAvatar({ worker, open, draft }: { worker?: any; open?: boolean; draft?: boolean }) {
  const fallback = draft ? 'E' : open ? 'OS' : cardWorkerInitials(worker);
  return <span className={`wiw-card-avatar ${open ? 'is-open' : ''}`} aria-hidden="true">
    <span>{fallback}</span>
    {worker?.avatar ? <img src={worker.avatar} alt="" loading="eager" decoding="async" onError={(event) => event.currentTarget.remove()} /> : null}
  </span>;
}

function previewShiftCardStyle(shift: any) {
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

function sortPreviewCards(left: CardRow, right: CardRow) {
  let order = clientRank(left.shift.client_name) - clientRank(right.shift.client_name);
  if (order) return order;
  order = String(left.shift.client_name || '').localeCompare(String(right.shift.client_name || ''), 'de');
  if (order) return order;
  return new Date(left.shift.starts_at).getTime() - new Date(right.shift.starts_at).getTime();
}

function AdjacentWeekPreview({ weekStart, groupFilter, query, side }: { weekStart: string; groupFilter: string[]; query: string; side: 'prev' | 'next' }) {
  const [shifts, setShifts] = useState<any[]>(() => {
    const cached = safeSessionGet(`${WEEK_CACHE_PREFIX}${weekStart}`);
    if (!cached) return [];
    try {
      const parsed = JSON.parse(cached);
      return Array.isArray(parsed) ? parsed : Array.isArray(parsed?.shifts) ? parsed.shifts : [];
    } catch {
      return [];
    }
  });

  useEffect(() => {
    let alive = true;
    const cached = safeSessionGet(`${WEEK_CACHE_PREFIX}${weekStart}`);
    if (cached) {
      try {
        const parsed = JSON.parse(cached);
        const next = Array.isArray(parsed) ? parsed : Array.isArray(parsed?.shifts) ? parsed.shifts : [];
        if (next.length) setShifts(next);
      } catch { /* optional cache */ }
    }
    void api(`admin/mobile-schedule/?date_from=${encodeURIComponent(weekStart)}&date_to=${encodeURIComponent(addDays(weekStart, 6))}`)
      .then((result: any) => {
        if (!alive) return;
        const next = Array.isArray(result?.shifts) ? result.shifts : [];
        setShifts(next);
        safeSessionSet(`${WEEK_CACHE_PREFIX}${weekStart}`, JSON.stringify(next));
      })
      .catch(() => undefined);
    return () => { alive = false; };
  }, [weekStart]);

  const previewDays = useMemo(() => Array.from({ length: 7 }, (_, index) => addDays(weekStart, index)), [weekStart]);
  const previewByDay = useMemo(() => {
    const map: Record<string, CardRow[]> = Object.fromEntries(previewDays.map((day) => [day, []]));
    const q = query.trim().toLocaleLowerCase('de-DE');
    shifts.forEach((shift: any) => {
      if (shift?.source === 'wiw-live') return;
      if (groupFilter.length && !shiftGroups(shift).some((group: string) => groupFilter.includes(group))) return;
      if (!groupFilter.length) return;
      activeSlots(shift).forEach((slot: any, index: number) => {
        const card: CardRow = {
          key: `${shift.id}:${slot.id || index}`,
          shift,
          slot,
          worker: slot.worker || undefined,
          isOpen: Boolean(slot.is_open || (slot.status === 'open' && !slot.worker)),
        };
        const haystack = `${shift.position_name || ''} ${shift.client_name || ''} ${shift.location_name || ''} ${card.worker?.name || ''}`.toLocaleLowerCase('de-DE');
        if (q && !haystack.includes(q)) return;
        const day = dateKeyFromIso(shift.starts_at);
        if (map[day]) map[day].push(card);
      });
    });
    Object.values(map).forEach((cards) => cards.sort(sortPreviewCards));
    return map;
  }, [previewDays, shifts, groupFilter, query]);

  return <div className={`wiw-week-pane wiw-week-preview wiw-week-pane-${side}`} aria-hidden="true">
    {previewDays.map((day) => {
      const header = formatDayHeader(day);
      const dayCards = previewByDay[day] || [];
      return <section className="wiw-day-section wiw-day-visual" key={day}>
        <header><span className="wiw-day-header-spacer"/><div className="wiw-day-heading"><strong>{header.weekday}</strong><span>{header.date}</span></div><em>{dayCards.length}<small> · {dayCards.reduce((sum, card) => { const gross = Math.max(0, (new Date(card.shift.ends_at).getTime() - new Date(card.shift.starts_at).getTime()) / 3600000); return sum + Math.max(0, gross - Number(card.shift.break_minutes || 0) / 60); }, 0).toFixed(1)} Std.</small></em></header>
        {dayCards.map((card, index) => <React.Fragment key={card.key}>{index > 0 && clientKey(dayCards[index - 1].shift) !== clientKey(card.shift) ? <div className="wiw-client-divider" aria-hidden="true" /> : null}<button type="button" tabIndex={-1} className={`wiw-shift-card ${card.shift.status === 'draft' ? 'is-draft' : card.isOpen ? 'is-open' : 'is-filled'}`} style={previewShiftCardStyle(card.shift)}>
          <div className="wiw-card-main">
            <CardWorkerAvatar worker={card.worker} open={card.isOpen} draft={card.shift.status === 'draft'} />
            <span className="wiw-card-copy"><b>{cardWorkerShortName(card.worker?.name) || (card.shift.status === 'draft' ? 'Entwurf' : 'OpenShift')}</b><small>{cardPositionShortLabel(card.shift.position_name)}</small></span>
            <span className="wiw-card-meta"><b>{formatTimeIso(card.shift.starts_at)}–{formatTimeIso(card.shift.ends_at)}</b><small>{card.shift.location_name || 'Einsatzort'}</small></span>
          </div>
        </button></React.Fragment>)}
        {!dayCards.length ? <div className="wiw-day-empty">Keine Schichten</div> : null}
      </section>;
    })}
  </div>;
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
function berlinToday() {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: BERLIN, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
  const get = (type: string) => parts.find((part) => part.type === type)?.value || '';
  return `${get('year')}-${get('month')}-${get('day')}`;
}
function dateKeyFromIso(input: string) {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: BERLIN, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date(input));
  const get = (type: string) => parts.find((part) => part.type === type)?.value || '';
  return `${get('year')}-${get('month')}-${get('day')}`;
}
function timeMinuteFromIso(input: string) {
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone: BERLIN, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(new Date(input));
  const hour = Number(parts.find((part) => part.type === 'hour')?.value || 0);
  const minute = Number(parts.find((part) => part.type === 'minute')?.value || 0);
  return hour * 60 + minute;
}
function formatMinute(value: number) {
  const normalized = ((value % 1440) + 1440) % 1440;
  return `${pad(Math.floor(normalized / 60))}:${pad(normalized % 60)}`;
}
function formatDateRow(key: string) {
  return new Intl.DateTimeFormat('de-DE', { timeZone: 'UTC', weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' }).format(keyDate(key));
}
function formatDayHeader(key: string) {
  const weekday = new Intl.DateTimeFormat('de-DE', { timeZone: 'UTC', weekday: 'short' }).format(keyDate(key));
  const date = new Intl.DateTimeFormat('de-DE', { timeZone: 'UTC', day: '2-digit', month: '2-digit', year: 'numeric' }).format(keyDate(key));
  return { weekday, date };
}
function formatTimeIso(input: string) {
  return new Intl.DateTimeFormat('de-DE', { timeZone: BERLIN, hour: '2-digit', minute: '2-digit' }).format(new Date(input));
}
function automaticBreak(start: number | null, end: number | null) {
  if (start == null || end == null) return 0;
  const hours = (end - start) / 60;
  if (hours >= 11) return 60;
  if (hours >= 9) return 45;
  if (hours >= 6) return 30;
  return 0;
}
function localDateTime(key: string, absoluteMinute: number) {
  const dayOffset = Math.floor(absoluteMinute / 1440);
  const time = ((absoluteMinute % 1440) + 1440) % 1440;
  return `${addDays(key, dayOffset)}T${formatMinute(time)}`;
}
function initialTime() {
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone: BERLIN, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(new Date());
  const hour = Number(parts.find((part) => part.type === 'hour')?.value || 9);
  const minute = Number(parts.find((part) => part.type === 'minute')?.value || 0);
  return Math.min(1425, Math.ceil((hour * 60 + minute) / QUARTER) * QUARTER);
}
function positionGroup(name?: string) {
  const key = normalize(String(name || ''));
  if (key.includes('frontoffice') || key.includes('rezeption') || key.includes('reception')) return 'front_office';
  if (key.includes('housekeeping') || key.includes('houskeeping') || key.includes('zimmer')) return 'housekeeping';
  return 'service';
}
function shiftGroups(shift: any): string[] {
  const groups = Array.isArray(shift?.schedule_groups) ? shift.schedule_groups.filter((value: string) => SCHEDULE_GROUPS.some((item) => item.value === value)) : [];
  return groups.length ? groups : [positionGroup(shift?.position_name)];
}
function hapticTick() {
  const fallback = () => {
    try { navigator.vibrate?.(5); } catch { /* best effort */ }
  };
  if (Capacitor.isNativePlatform()) {
    void Haptics.impact({ style: ImpactStyle.Light }).catch(fallback);
  } else {
    fallback();
  }
}
function safeSessionGet(key: string) {
  try { return sessionStorage.getItem(key); } catch { return null; }
}
function safeSessionSet(key: string, value: string) {
  try { sessionStorage.setItem(key, value); } catch { /* cache is optional */ }
}

function activeSlots(shift: any) {
  if (Array.isArray(shift.slot_cards) && shift.slot_cards.length) return shift.slot_cards;
  const assigned = Array.isArray(shift.assigned_workers) ? shift.assigned_workers : [];
  const cards: any[] = assigned.map((worker: any, index: number) => ({
    id: worker.slot_id || `assigned-${index}`,
    status: 'claimed',
    worker,
    is_open: false,
  }));
  const open = Math.max(0, Number(shift.open_count || 0));
  for (let index = 0; index < open; index += 1) cards.push({ id: `open-${index}`, status: 'open', worker: null, is_open: true });
  return cards.length ? cards : [{ id: `shift-${shift.id}`, status: shift.status === 'draft' ? 'open' : 'claimed', worker: assigned[0] || null, is_open: Number(shift.open_count || 0) > 0 }];
}

function WheelColumn({ items, value, onChange }: { items: Array<{ value: number; label: string }>; value: number; onChange: (value: number) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const settleTimer = useRef<number | undefined>(undefined);
  const frame = useRef<number | undefined>(undefined);
  const userScrolling = useRef(false);
  const programmatic = useRef(false);
  const latestValue = useRef(value);
  const lastTickIndex = useRef(-1);

  useEffect(() => { latestValue.current = value; }, [value]);
  useEffect(() => {
    if (!ref.current || userScrolling.current) return;
    const index = Math.max(0, items.findIndex((item) => item.value === value));
    lastTickIndex.current = index;
    const target = index * WHEEL_ROW;
    if (Math.abs(ref.current.scrollTop - target) > 1) ref.current.scrollTop = target;
  }, [items, value]);
  useEffect(() => () => {
    window.clearTimeout(settleTimer.current);
    if (frame.current) window.cancelAnimationFrame(frame.current);
  }, []);

  const indexAtScroll = () => {
    if (!ref.current || !items.length) return 0;
    return Math.max(0, Math.min(items.length - 1, Math.round(ref.current.scrollTop / WHEEL_ROW)));
  };

  const emitTick = () => {
    frame.current = undefined;
    const index = indexAtScroll();
    if (index === lastTickIndex.current) return;
    lastTickIndex.current = index;
    hapticTick();
    const next = items[index]?.value;
    if (next == null || next === latestValue.current) return;
    latestValue.current = next;
    onChange(next);
  };

  const settle = () => {
    if (!ref.current || !items.length) return;
    const index = indexAtScroll();
    const target = index * WHEEL_ROW;
    const next = items[index].value;
    lastTickIndex.current = index;
    if (next !== latestValue.current) {
      latestValue.current = next;
      onChange(next);
      hapticTick();
    }
    programmatic.current = true;
    ref.current.scrollTo({ top: target, behavior: 'smooth' });
    window.setTimeout(() => {
      programmatic.current = false;
      userScrolling.current = false;
    }, 90);
  };

  return (
    <div
      ref={ref}
      className="wiw-wheel-column"
      onScroll={() => {
        if (programmatic.current) return;
        userScrolling.current = true;
        if (!frame.current) frame.current = window.requestAnimationFrame(emitTick);
        window.clearTimeout(settleTimer.current);
        settleTimer.current = window.setTimeout(settle, 55);
      }}
    >
      {items.map((item) => (
        <button type="button" key={item.value} className={item.value === value ? 'active' : ''} onClick={() => {
          const index = items.findIndex((candidate) => candidate.value === item.value);
          latestValue.current = item.value;
          lastTickIndex.current = index;
          onChange(item.value);
          hapticTick();
          programmatic.current = true;
          ref.current?.scrollTo({ top: index * WHEEL_ROW, behavior: 'smooth' });
          window.setTimeout(() => { programmatic.current = false; userScrolling.current = false; }, 90);
        }}>{item.label}</button>
      ))}
    </div>
  );
}

function TimeFrameWheel({ start, end, onChange }: { start: number; end: number; onChange: (start: number, end: number) => void }) {
  const times = useMemo(() => Array.from({ length: 96 }, (_, index) => ({
    value: index * 15,
    label: formatMinute(index * 15),
  })), []);
  const endMinute = ((end % 1440) + 1440) % 1440;

  const selectEnd = (next: number) => {
    const currentDayOffset = Math.max(0, Math.floor(end / 1440));
    let nextAbsolute = next + currentDayOffset * 1440;
    // An earlier visible end time means the following day. Equal times stay
    // invalid instead of silently turning into a 24-hour shift.
    if (nextAbsolute < start && currentDayOffset === 0) nextAbsolute += 1440;
    onChange(start, nextAbsolute);
  };

  return (
    <div className="wiw-time-wheel" data-testid="wiw-time-wheel">
      <div className="wiw-wheel-highlight" />
      <WheelColumn items={times} value={start} onChange={(next) => onChange(next, end)} />
      <WheelColumn items={times} value={endMinute} onChange={selectEnd} />
    </div>
  );
}

function Switch({ checked, onChange }: { checked: boolean; onChange: (value: boolean) => void }) {
  return <button type="button" className={`wiw-switch ${checked ? 'on' : ''}`} aria-pressed={checked} onClick={() => onChange(!checked)}><span /></button>;
}

function Row({ field, icon, label, value, muted, green, onClick, trailing, colorManaged, emphasizeValue }: { field?: string; icon: string; label: string; value?: string; muted?: boolean; green?: boolean; onClick?: () => void; trailing?: React.ReactNode; colorManaged?: boolean; emphasizeValue?: boolean }) {
  const Component: any = onClick ? 'button' : 'div';
  return (
    <Component data-field={field} type={onClick ? 'button' : undefined} data-color-managed={colorManaged ? 'true' : undefined} className={`wiw-form-row ${muted ? 'muted' : ''} ${green ? 'green' : ''} ${emphasizeValue ? 'employee-emphasis' : ''}`} onClick={onClick}>
      <IonIcon icon={icon} />
      <div className="wiw-form-row-copy"><span>{label}</span>{value ? <b>{value}</b> : null}</div>
      {trailing ?? (onClick ? <IonIcon className="wiw-row-chevron" icon={chevronForwardOutline} /> : null)}
    </Component>
  );
}

function ChoiceSheet({ title, choices, selected, onSelect, onClose }: { title: string; choices: Choice[]; selected?: string; onSelect: (choice: Choice) => void; onClose: () => void }) {
  return (
    <div className="wiw-sheet-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="wiw-choice-sheet">
        <header><b>{title}</b><button type="button" onClick={onClose}>Fertig</button></header>
        <div>{choices.map((choice) => <button type="button" key={choice.value} className={selected === choice.value ? 'selected' : ''} onClick={() => onSelect(choice)}><span>{choice.label}</span>{selected === choice.value ? <IonIcon icon={checkmarkOutline} /> : null}</button>)}</div>
      </section>
    </div>
  );
}

function ColorSheet({ selected, autoHue, onSelect, onClose }: { selected: number | null; autoHue: number; onSelect: (hue: number | null) => void; onClose: () => void }) {
  return (
    <div className="wiw-sheet-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="wiw-choice-sheet wiw-color-sheet">
        <header><b>Standardfarbe</b><button type="button" onClick={onClose}>Fertig</button></header>
        <div>{COLOR_CHOICES.map((choice) => {
          const active = choice.hue === selected;
          const hue = choice.hue ?? autoHue;
          return <button type="button" key={choice.value} className={active ? 'selected' : ''} onClick={() => onSelect(choice.hue)}>
            <span className="wiw-color-choice"><i style={{ '--wiw-color-hue': String(hue) } as React.CSSProperties} /><span>{choice.label}</span></span>
            {active ? <IonIcon icon={checkmarkOutline} /> : null}
          </button>;
        })}</div>
      </section>
    </div>
  );
}

function MultiChoiceSheet({ title, choices, selected, limit, onChange, onClose }: { title: string; choices: Choice[]; selected: string[]; limit?: number; onChange: (values: string[]) => void; onClose: () => void }) {
  return (
    <div className="wiw-sheet-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="wiw-choice-sheet">
        <header><b>{title}</b><button type="button" onClick={onClose}>Fertig</button></header>
        <div>{choices.map((choice) => {
          const checked = selected.includes(choice.value);
          return <button type="button" key={choice.value} className={checked ? 'selected' : ''} onClick={() => {
            if (checked) onChange(selected.filter((value) => value !== choice.value));
            else if (limit === 1) onChange([choice.value]);
            else if (!limit || selected.length < limit) onChange([...selected, choice.value]);
          }}><span>{choice.label}</span>{checked ? <IonIcon icon={checkmarkOutline} /> : null}</button>;
        })}</div>
      </section>
    </div>
  );
}

function currentManagerScheduleShell() {
  if (typeof document === 'undefined') return null;
  return document.querySelector<HTMLElement>('.mobile-first-app-shell-v1[data-view="schedule"]');
}

export default function WiwScheduleMobile() {
  const initialShell = currentManagerScheduleShell();
  const initialRole = initialShell?.dataset.role || '';
  const [active, setActive] = useState(() => Boolean(initialShell));
  const [mobile, setMobile] = useState(() => typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches);
  const [manager, setManager] = useState(() => ['admin', 'manager'].includes(initialRole));
  const [isAdmin, setIsAdmin] = useState(() => initialRole === 'admin');
  const [rows, setRows] = useState<any[]>([]);
  const [clients, setClients] = useState<any[]>([]);
  const [locations, setLocations] = useState<any[]>([]);
  const [positions, setPositions] = useState<any[]>([]);
  const [workers, setWorkers] = useState<any[]>([]);
  const [anchor, setAnchor] = useState(berlinToday());
  const [tab, setTab] = useState<TabKey>('all');
  const [query, setQuery] = useState('');
  const [groupFilter, setGroupFilter] = useState<string[]>(SCHEDULE_GROUPS.map((item) => item.value));
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<EditingCard>();
  const [timeEditor, setTimeEditor] = useState<any>();
  const [timeEditorDateOpen, setTimeEditorDateOpen] = useState(false);
  const [timeLogOpen, setTimeLogOpen] = useState(false);
  const [timeBusy, setTimeBusy] = useState(false);
  const [copying, setCopying] = useState(false);
  const [recentCopyShiftId, setRecentCopyShiftId] = useState('');
  const [form, setForm] = useState<FormState>(() => emptyForm(berlinToday()));
  const [timeOpen, setTimeOpen] = useState(false);
  const [sheet, setSheet] = useState<'client' | 'position' | 'location' | 'workers' | 'groups' | 'color' | ''>('');
  const [pdfOpen, setPdfOpen] = useState(false);
  const [pdfBusy, setPdfBusy] = useState(false);
  const [pdf, setPdf] = useState<PdfState>(() => ({ dateFrom: monday(berlinToday()), dateTo: addDays(monday(berlinToday()), 6), workers: [], clients: [], groups: [] }));
  const swipe = useRef<{ x: number; y: number } | undefined>(undefined);
  const swipeFrame = useRef<number | undefined>(undefined);
  const swipeTravel = useRef(0);
  const swipeAxis = useRef<'horizontal' | 'vertical' | null>(null);
  const swipeScrollElement = useRef<HTMLElement | null>(null);
  const swipeScrollTop = useRef(0);
  const localRowsRef = useRef<any[]>([]);
  const liveRowsRef = useRef<any[]>([]);
  const loadSequence = useRef(0);
  const [dateOpen, setDateOpen] = useState(false);
  const [pdfError, setPdfError] = useState('');
  const [pdfDateField, setPdfDateField] = useState<'dateFrom' | 'dateTo' | ''>('');
  const formScreenRef = useRef<HTMLDivElement>(null);
  const formScrollRef = useRef<HTMLDivElement>(null);
  const noteRef = useRef<HTMLTextAreaElement>(null);

  const weekStart = monday(anchor);
  const days = useMemo(() => Array.from({ length: 7 }, (_, index) => addDays(weekStart, index)), [weekStart]);

  const publishRows = () => setRows([...localRowsRef.current, ...liveRowsRef.current]);

  const restoreMetadataCache = () => {
    const raw = safeSessionGet(META_CACHE_KEY);
    if (!raw) return;
    try {
      const cached = JSON.parse(raw);
      if (Array.isArray(cached.clients)) setClients(cached.clients);
      if (Array.isArray(cached.locations)) setLocations(cached.locations);
      if (Array.isArray(cached.positions)) setPositions(cached.positions);
      if (Array.isArray(cached.workers)) setWorkers(cached.workers);
    } catch { /* optional cache */ }
  };

  const loadMetadata = async () => {
    try {
      const [clientData, locationData, positionData, workerData] = await Promise.all([
        api('clients/?ordering=name'),
        api('locations/'),
        api('positions/'),
        api('workers/?ordering=user__last_name'),
      ]);
      const next = {
        clients: sortClients(unpack(clientData).filter((item: any) => item.active !== false)),
        locations: unpack(locationData).filter((item: any) => item.active !== false),
        positions: unpack(positionData).filter((item: any) => item.active !== false),
        workers: unpack(workerData).filter((item: any) => item.active !== false && !String(item?.user_detail?.email || '').endsWith('@sync.invalid')),
      };
      setClients(next.clients);
      setLocations(next.locations);
      setPositions(next.positions);
      setWorkers(next.workers);
      safeSessionSet(META_CACHE_KEY, JSON.stringify(next));
    } catch (error) {
      console.warn('Dienstplan Stammdaten refresh failed', error);
    }
  };

  const prefetchScheduleWeek = async (targetWeek: string) => {
    if (!manager) return;
    const cacheKey = `${WEEK_CACHE_PREFIX}${targetWeek}`;
    if (safeSessionGet(cacheKey)) return;
    try {
      const scheduleData: any = await api(`admin/mobile-schedule/?date_from=${encodeURIComponent(targetWeek)}&date_to=${encodeURIComponent(addDays(targetWeek, 6))}`);
      const nextRows = Array.isArray(scheduleData?.shifts) ? scheduleData.shifts : [];
      safeSessionSet(cacheKey, JSON.stringify(nextRows));
    } catch (error) {
      console.warn('Dienstplan background prefetch failed', error);
    }
  };

  const loadScheduleWeek = async (targetWeek: string, showBusy = true) => {
    if (!manager) return;
    const sequence = ++loadSequence.current;
    const cacheKey = `${WEEK_CACHE_PREFIX}${targetWeek}`;
    const cached = safeSessionGet(cacheKey);
    if (cached) {
      try {
        const cachedRows = JSON.parse(cached);
        if (Array.isArray(cachedRows)) {
          localRowsRef.current = cachedRows;
          publishRows();
        }
      } catch { /* optional cache */ }
    }
    if (showBusy && !cached) setBusy(true);
    try {
      const scheduleData: any = await api(`admin/mobile-schedule/?date_from=${encodeURIComponent(targetWeek)}&date_to=${encodeURIComponent(addDays(targetWeek, 6))}`);
      if (sequence !== loadSequence.current) return;
      const nextLocal = Array.isArray(scheduleData?.shifts) ? scheduleData.shifts : [];
      localRowsRef.current = nextLocal;
      safeSessionSet(cacheKey, JSON.stringify(nextLocal));
      publishRows();
      setBusy(false);
      void prefetchScheduleWeek(addDays(targetWeek, -7));
      void prefetchScheduleWeek(addDays(targetWeek, 7));

      void api('admin/mobile-dashboard/').then((dashboardData: any) => {
        if (sequence !== loadSequence.current) return;
        liveRowsRef.current = Array.isArray(dashboardData?.open_shift_rows) ? dashboardData.open_shift_rows : [];
        publishRows();
      }).catch((error) => console.warn('OpenShift live rows refresh failed', error));
    } catch (error: any) {
      if (sequence === loadSequence.current) setToast(error.message || 'Dienstplan konnte nicht geladen werden.');
    } finally {
      if (sequence === loadSequence.current) setBusy(false);
    }
  };

  const load = async (targetWeek = weekStart) => {
    await loadScheduleWeek(targetWeek, true);
    void loadMetadata();
  };

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(''), 1300);
    return () => window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    if (!recentCopyShiftId) return;
    const timer = window.setTimeout(() => setRecentCopyShiftId(''), 1150);
    return () => window.clearTimeout(timer);
  }, [recentCopyShiftId]);

  useEffect(() => {
    const handler = (event: Event) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest('[aria-label="OpenShifts verfügbar"]')) {
        sessionStorage.setItem('aplus:schedule-entry-filter', 'open');
      }
    };
    document.addEventListener('click', handler, true);
    return () => document.removeEventListener('click', handler, true);
  }, []);

  useEffect(() => {
    const root = document.getElementById('root');
    const sync = () => {
      const appShell = document.querySelector<HTMLElement>('.mobile-first-app-shell-v1');
      // During resume React can briefly replace descendants. Do not tear down
      // the compact Dienstplan just because the app shell is momentarily absent.
      if (!appShell) return;
      const role = appShell.dataset.role || '';
      const enabled = appShell.dataset.view === 'schedule' && ['admin', 'manager'].includes(role);
      setActive(enabled);
      setManager(['admin', 'manager'].includes(role));
      setIsAdmin(role === 'admin');
      const mobileNow = window.matchMedia('(max-width: 900px)').matches;
      document.body.classList.toggle('wiw-native-schedule-active', enabled && mobileNow);
    };
    sync();
    const observer = new MutationObserver(sync);
    if (root) observer.observe(root, { subtree: true, childList: true, attributes: true, attributeFilter: ['data-view', 'data-role'] });
    const watchdog = window.setInterval(sync, 1000);
    const onVisible = () => { if (!document.hidden) sync(); };
    window.addEventListener('focus', sync);
    window.addEventListener('pageshow', sync);
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      observer.disconnect();
      window.clearInterval(watchdog);
      window.removeEventListener('focus', sync);
      window.removeEventListener('pageshow', sync);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, []);

  useEffect(() => {
    const media = window.matchMedia('(max-width: 900px)');
    const sync = () => setMobile(media.matches);
    sync();
    media.addEventListener?.('change', sync);
    return () => media.removeEventListener?.('change', sync);
  }, []);

  useEffect(() => {
    if (!active || !mobile) return;
    let cancelled = false;
    api('auth/me/').then((user: any) => {
      if (!cancelled) {
        setManager(['admin', 'manager'].includes(user?.role));
        setIsAdmin(user?.role === 'admin');
      }
    }).catch((error) => {
      // The app shell already carries the authenticated role. A temporary
      // resume/network failure must never demote a manager and reveal the old
      // ScheduleV2 fallback underneath the WIW mobile schedule.
      console.warn('Dienstplan role revalidation deferred', error);
    });
    return () => { cancelled = true; };
  }, [active, mobile]);

  useLayoutEffect(() => {
    if (!active || !mobile || !manager) {
      const shell = currentManagerScheduleShell();
      const role = shell?.dataset.role || '';
      if (!shell || !['admin', 'manager'].includes(role) || !window.matchMedia('(max-width: 900px)').matches) {
        document.body.classList.remove('wiw-native-schedule-active');
      }
      return;
    }
    document.body.classList.add('wiw-native-schedule-active');
    const requested = sessionStorage.getItem('aplus:schedule-entry-filter');
    sessionStorage.removeItem('aplus:schedule-entry-filter');
    setTab(requested === 'open' ? 'open' : 'all');
    restoreMetadataCache();
    void loadMetadata();
    return () => {
      // Resume refreshes must not uncover the legacy scheduler between React
      // cleanup and the next effect. Only remove the guard after the app really
      // left the manager/admin mobile schedule.
      const shell = currentManagerScheduleShell();
      const role = shell?.dataset.role || '';
      const shouldStay = Boolean(shell && ['admin', 'manager'].includes(role) && window.matchMedia('(max-width: 900px)').matches);
      if (!shouldStay) document.body.classList.remove('wiw-native-schedule-active');
    };
  }, [active, mobile, manager]);

  useEffect(() => {
    if (!active || !mobile || !manager) return;
    void loadScheduleWeek(weekStart, true);
  }, [active, mobile, manager, weekStart]);

  useEffect(() => {
    if (!active || !mobile || !manager) return;
    const refreshAfterResume = () => {
      document.body.classList.add('wiw-native-schedule-active');
      void loadScheduleWeek(weekStart, false);
      void loadMetadata();
    };
    window.addEventListener('aplus-app-resume', refreshAfterResume);
    window.addEventListener('pageshow', refreshAfterResume);
    return () => {
      window.removeEventListener('aplus-app-resume', refreshAfterResume);
      window.removeEventListener('pageshow', refreshAfterResume);
    };
  }, [active, mobile, manager, weekStart]);

  useEffect(() => {
    if (!formOpen) return;
    const viewport = window.visualViewport;
    const syncInset = () => {
      const height = viewport?.height ?? window.innerHeight;
      const offsetTop = viewport?.offsetTop ?? 0;
      const inset = Math.max(0, window.innerHeight - height - offsetTop);
      formScreenRef.current?.style.setProperty('--wiw-keyboard-inset', `${Math.round(inset)}px`);
    };
    syncInset();
    viewport?.addEventListener('resize', syncInset);
    viewport?.addEventListener('scroll', syncInset);
    return () => {
      viewport?.removeEventListener('resize', syncInset);
      viewport?.removeEventListener('scroll', syncInset);
    };
  }, [formOpen]);

  const cards = useMemo<CardRow[]>(() => rows.flatMap((shift: any) => activeSlots(shift).map((slot: any) => ({
    key: `${shift.id}:${slot.id}`,
    shift,
    slot,
    worker: slot.worker || undefined,
    isOpen: Boolean(slot.is_open || (slot.status === 'open' && !slot.worker)),
  }))), [rows]);
  const shiftCardStyle = (shift: any) => {
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
  };
  const selectedClientName = clients.find((item: any) => String(item.id) === form.client)?.name || '';
  const selectedPositionName = positions.find((item: any) => String(item.id) === form.position)?.name || '';
  const formPalette = schedulePalette(selectedClientName, selectedPositionName, form.color_hue);
  const formAutoHue = 215;
  const liveLocalShiftIds = useMemo(() => new Set(rows.filter((row: any) => row?.source === 'wiw-live' && row?.local_shift_id).map((row: any) => String(row.local_shift_id))), [rows]);
  const visibleCards = useMemo(() => cards.filter((card) => {
    const shiftDay = dateKeyFromIso(card.shift.starts_at);
    if (tab === 'open') {
      if (card.shift.source !== 'wiw-live' && liveLocalShiftIds.has(String(card.shift.id))) return false;
      if (!card.isOpen) return false;
      if (!['published', 'confirmed'].includes(String(card.shift.status || ''))) return false;
      if (card.shift.ends_at && new Date(card.shift.ends_at).getTime() < Date.now()) return false;
    } else {
      if (card.shift.source === 'wiw-live') return false;
      if (!days.includes(shiftDay)) return false;
    }
    if (tab === 'filled' && (!card.worker || card.shift.status === 'draft')) return false;
    if (tab === 'draft' && card.shift.status !== 'draft') return false;
    const cardGroups = shiftGroups(card.shift);
    if (groupFilter.length && !cardGroups.some((group) => groupFilter.includes(group))) return false;
    if (!groupFilter.length) return false;
    if (query.trim()) {
      const haystack = `${card.shift.position_name || ''} ${card.shift.client_name || ''} ${card.shift.location_name || ''} ${card.worker?.name || ''}`.toLowerCase();
      if (!haystack.includes(query.trim().toLowerCase())) return false;
    }
    return true;
  }), [cards, days, groupFilter, liveLocalShiftIds, query, tab]);
  const visibleDays = useMemo(() => {
    if (tab !== 'open') return days;
    return Array.from(new Set(visibleCards.map((card) => dateKeyFromIso(card.shift.starts_at)))).sort();
  }, [days, tab, visibleCards]);
  const byDay = useMemo(() => {
    const map: Record<string, CardRow[]> = {};
    visibleDays.forEach((day) => { map[day] = []; });
    visibleCards.forEach((card) => { (map[dateKeyFromIso(card.shift.starts_at)] ||= []).push(card); });
    Object.values(map).forEach((dayCards) => {
      dayCards.sort((left, right) => {
        const groupOrder = clientRank(left.shift.client_name) - clientRank(right.shift.client_name);
        if (groupOrder) return groupOrder;
        const nameOrder = String(left.shift.client_name || '').localeCompare(String(right.shift.client_name || ''), 'de');
        if (nameOrder) return nameOrder;
        return new Date(left.shift.starts_at).getTime() - new Date(right.shift.starts_at).getTime();
      });
    });
    return map;
  }, [visibleDays, visibleCards]);
  const weekHours = useMemo(() => visibleCards.reduce((sum, card) => {
    const gross = Math.max(0, (new Date(card.shift.ends_at).getTime() - new Date(card.shift.starts_at).getTime()) / 3600000);
    return sum + Math.max(0, gross - Number(card.shift.break_minutes || 0) / 60);
  }, 0), [visibleCards]);

  const positionChoices = useMemo<Choice[]>(() => {
    const selectedGroups = form.schedule_groups || [];
    return POSITION_ORDER.flatMap((definition) => {
      const match = positions.find((item: any) => definition.aliases.includes(normalize(item.name)));
      if (!match) return [];
      const group = positionGroup(match.name);
      if (selectedGroups.length && !selectedGroups.includes(group)) return [];
      return [{ value: String(match.id), label: definition.label }];
    });
  }, [positions, form.schedule_groups]);
  const clientChoices = useMemo<Choice[]>(() => clients.map((item: any) => ({ value: String(item.id), label: item.name })), [clients]);
  const locationChoices = useMemo<Choice[]>(() => locations.filter((item: any) => !form.client || String(item.client) === form.client).map((item: any) => ({ value: String(item.id), label: item.name })), [locations, form.client]);
  const workerChoices = useMemo<Choice[]>(() => workers
    .map((item: any) => ({ value: String(item.id), label: item.user_detail?.name || item.user_detail?.email || item.employee_number || 'Mitarbeiter' }))
    .filter((item: Choice) => allowedWorkerNames.has(normalize(item.label)))
    .sort((a: Choice, b: Choice) => a.label.localeCompare(b.label, 'de', { sensitivity: 'base' })), [workers]);
  const selectedWorkerNames = form.workers.map((workerId) => workerChoices.find((choice) => choice.value === workerId)?.label).filter(Boolean).join(', ');
  const pdfHasHotel = useMemo(() => pdf.clients.some((clientId) => isHotelClientName(clients.find((item: any) => String(item.id) === clientId)?.name)), [clients, pdf.clients]);
  const editingTimeEntries = useMemo(() => {
    if (!editing?.workerId) return [] as any[];
    return (editing.timeEntries || []).filter((entry: any) => String(entry.worker) === String(editing.workerId));
  }, [editing]);
  const editingTimeEntry = editingTimeEntries.find((entry: any) => !entry.wiw_time_id) || editingTimeEntries[0];

  function openCreate(date = anchor) {
    setEditing(undefined);
    setTimeEditor(undefined);
    setTimeLogOpen(false);
    setTimeLogOpen(false);
    setCopying(false);
    setForm(emptyForm(date));
    setTimeOpen(false);
    setDateOpen(false);
    setFormOpen(true);
  }

  function openEdit(card: CardRow) {
    setCopying(false);
    const startDate = dateKeyFromIso(card.shift.starts_at);
    const endDate = dateKeyFromIso(card.shift.ends_at);
    const startMinute = timeMinuteFromIso(card.shift.starts_at);
    const endMinute = timeMinuteFromIso(card.shift.ends_at);
    const dayOffset = Math.round((keyDate(endDate).getTime() - keyDate(startDate).getTime()) / 86400000);
    setEditing({
      shiftId: String(card.shift.id),
      slotId: String(card.slot.id),
      parentCount: Number(card.shift.required_count || 1),
      workerName: card.worker?.name,
      workerId: card.worker?.id ? String(card.worker.id) : '',
      isOpen: card.isOpen,
      timeEntries: Array.isArray(card.shift.admin_time_entries) ? card.shift.admin_time_entries : [],
    });
    setTimeEditor(undefined);
    setForm({
      client: String(card.shift.client || ''),
      date: startDate,
      startMinute,
      endAbsolute: endMinute + Math.max(0, dayOffset) * 1440,
      position: String(card.shift.position || ''),
      location: String(card.shift.location || ''),
      required_count: 1,
      publish_now: card.shift.status !== 'draft',
      confirmation_required: Boolean(card.shift.confirmation_required),
      workers: card.worker?.id ? [String(card.worker.id)] : [],
      schedule_groups: Array.isArray(card.shift.schedule_groups) && card.shift.schedule_groups.length ? card.shift.schedule_groups : [positionGroup(card.shift.position_name)],
      color_hue: card.shift.color_hue == null ? null : Number(card.shift.color_hue),
      notes: card.shift.notes || '',
      apply_all: false,
    });
    setTimeOpen(false);
    setDateOpen(false);
    setFormOpen(true);
  }

  function ensureTime() {
    if (form.startMinute != null && form.endAbsolute != null) return;
    const start = initialTime();
    setForm((current) => ({ ...current, startMinute: start, endAbsolute: start + 360 }));
  }

  function openAdminTimeEditor() {
    if (!isAdmin || !editing?.workerId) return;
    if (editingTimeEntry?.wiw_time_id) {
      setToast('WIW-Arbeitszeit ist historisch und schreibgeschützt.');
      return;
    }
    const fallbackStart = form.startMinute == null ? '' : localDateTime(form.date, form.startMinute);
    const fallbackEnd = form.endAbsolute == null ? '' : localDateTime(form.date, form.endAbsolute);
    const startIso = editingTimeEntry?.clock_in || fallbackStart;
    const endIso = editingTimeEntry?.clock_out || fallbackEnd;
    const date = startIso ? dateKeyFromIso(startIso) : form.date;
    const startMinute = startIso ? timeMinuteFromIso(startIso) : Number(form.startMinute || 0);
    const endDate = endIso ? dateKeyFromIso(endIso) : date;
    const endMinute = endIso ? timeMinuteFromIso(endIso) : Number(form.endAbsolute || startMinute + 360);
    const dayOffset = Math.max(0, Math.round((keyDate(endDate).getTime() - keyDate(date).getTime()) / 86400000));
    const endAbsolute = endMinute + dayOffset * 1440;
    setTimeEditorDateOpen(false);
    setTimeEditor({
      entry: editingTimeEntry,
      date,
      startMinute,
      endAbsolute: endAbsolute > startMinute ? endAbsolute : startMinute + 15,
      break_minutes: Number(editingTimeEntry?.break_minutes ?? automaticBreak(form.startMinute, form.endAbsolute)),
      reason: '',
      timeOpen: true,
    });
  }

  function applyAdminTimeEntries(shiftId: string, entries: any[]) {
    const patch = (items: any[]) => items.map((shift: any) => String(shift.id) === String(shiftId) ? { ...shift, admin_time_entries: entries } : shift);
    localRowsRef.current = patch(localRowsRef.current);
    liveRowsRef.current = patch(liveRowsRef.current);
    publishRows();
    setEditing((current) => current && String(current.shiftId) === String(shiftId) ? { ...current, timeEntries: entries } : current);
  }

  async function saveAdminTime() {
    if (!isAdmin || !editing?.workerId || !timeEditor) return;
    if (!timeEditor.date || timeEditor.startMinute == null || timeEditor.endAbsolute == null) {
      setToast('Bitte Datum, Beginn und Ende vollständig angeben.');
      return;
    }
    if (Number(timeEditor.endAbsolute) <= Number(timeEditor.startMinute)) {
      setToast('Arbeitsende muss nach dem Arbeitsbeginn liegen.');
      return;
    }
    setTimeBusy(true);
    const wasExisting = Boolean(timeEditor.entry);
    try {
      await api('time-entries/set-for-shift/', {
        method: 'POST',
        body: JSON.stringify({
          shift: editing.shiftId,
          worker: editing.workerId,
          clock_in: localDateTime(timeEditor.date, Number(timeEditor.startMinute)),
          clock_out: localDateTime(timeEditor.date, Number(timeEditor.endAbsolute)),
          break_minutes: Math.max(0, Number(timeEditor.break_minutes || 0)),
          reason: String(timeEditor.reason || '').trim(),
        }),
      });
      const detail: any = await api(`shifts/${editing.shiftId}/`);
      const entries = Array.isArray(detail?.admin_time_entries) ? detail.admin_time_entries : [];
      applyAdminTimeEntries(editing.shiftId, entries);
      setTimeEditor(undefined);
      setToast(wasExisting ? 'Arbeitszeit wurde bearbeitet.' : 'Arbeitszeit wurde eingetragen.');
    } catch (error: any) {
      setToast(error.message || 'Arbeitszeit konnte nicht gespeichert werden.');
    } finally {
      setTimeBusy(false);
    }
  }

  async function sendManualReminder() {
    if (!editing || !editing.workerName || busy) return;
    setBusy(true);
    try {
      const result: any = await api(`shifts/${editing.shiftId}/cards/${editing.slotId}/remind/`, { method: 'POST', body: '{}' });
      setToast(`Erinnerung an ${result?.worker || editing.workerName} gesendet.`);
    } catch (error: any) {
      setToast(error.message || 'Erinnerung konnte nicht gesendet werden.');
    } finally {
      setBusy(false);
    }
  }

  async function deleteEditingShift() {
    if (!editing || busy) return;
    const label = editing.workerName ? `Schicht von ${editing.workerName}` : 'OpenShift';
    if (!window.confirm(`${label} wirklich löschen?`)) return;
    const notifyWorker = editing.workerName
      ? window.confirm(`Soll ${editing.workerName} eine Push-Benachrichtigung über die Löschung erhalten?\n\nOK = Push senden\nAbbrechen = ohne Push löschen`)
      : false;
    setBusy(true);
    try {
      await api(`shifts/${editing.shiftId}/cards/${editing.slotId}/delete/?notify_worker=${notifyWorker ? '1' : '0'}`, { method: 'DELETE' });
      setFormOpen(false);
      setEditing(undefined);
      setToast(notifyWorker ? 'Schicht gelöscht · Mitarbeiter wurde informiert.' : 'Schicht gelöscht · ohne Mitarbeiter-Push.');
      window.dispatchEvent(new Event('aplus:dashboard-invalidated'));
      await load();
    } catch (error: any) {
      setToast(error.message || 'Schicht konnte nicht gelöscht werden.');
    } finally {
      setBusy(false);
    }
  }

  function prepareCopyAsOpenShift() {
    if (!editing || busy) return;
    setEditing(undefined);
    setCopying(true);
    setTimeOpen(false);
    noteRef.current?.blur();
    formScrollRef.current?.scrollTo({ top: 0 });
    const screen = formScreenRef.current;
    if (screen && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      screen.animate([
        { transform: 'translateY(100%)', opacity: 0.4 },
        { transform: 'translateY(0)', opacity: 1 },
      ], { duration: 520, easing: 'cubic-bezier(.16,.82,.24,1)' });
    }
    setForm((current) => ({
      ...current,
      required_count: 1,
      publish_now: true,
      workers: [],
      apply_all: false,
    }));
    setToast('Kopie bereit. Änderungen vornehmen und dann sichern.');
  }

  async function save() {
    const savingCopy = copying;
    if (!form.client || !form.location || !form.position || form.startMinute == null || form.endAbsolute == null) {
      setToast('Bitte Kunde, Zeit, Position und Jobstandort auswählen.');
      return;
    }
    if (Number(form.endAbsolute) <= Number(form.startMinute)) {
      setToast('Das Ende muss nach dem Beginn liegen.');
      return;
    }
    setBusy(true);
    let createdShiftId = '';
    try {
      const payload: any = {
        client: form.client,
        location: form.location,
        position: form.position,
        starts_at: localDateTime(form.date, form.startMinute),
        ends_at: localDateTime(form.date, form.endAbsolute),
        notes: form.notes || '',
        confirmation_required: form.confirmation_required,
        schedule_groups: form.schedule_groups,
        color_hue: form.color_hue,
      };
      if (editing) {
        payload.status = form.publish_now ? 'published' : 'draft';
        payload.apply_all = form.apply_all;
        const edited: any = await api(`shifts/${editing.shiftId}/cards/${editing.slotId}/`, { method: 'PATCH', body: JSON.stringify(payload) });
        const targetShiftId = String(edited?.shift?.id || editing.shiftId);
        const nextWorkerId = String(form.workers[0] || '');
        const workerChanged = String(editing.workerId || '') !== nextWorkerId;
        if (workerChanged) {
          await api(`shifts/${targetShiftId}/assign/`, {
            method: 'POST',
            body: JSON.stringify({ workers: nextWorkerId ? [nextWorkerId] : [], publish_remaining: form.publish_now }),
          });
        }
        setToast(workerChanged
          ? (nextWorkerId ? 'Schicht gespeichert · Mitarbeiter geändert.' : 'Schicht gespeichert · als OpenShift freigegeben.')
          : (form.apply_all ? 'Änderungen auf alle Karten angewendet.' : 'Schicht gespeichert.'));
      } else {
        payload.required_count = Math.max(1, Number(form.required_count || 1));
        const selectedWorkers = form.workers.slice(0, payload.required_count);
        // With direct assignments, create as draft first so workers do not receive
        // an OpenShift push before the assignment is applied. If OpenShift is off
        // and nobody is assigned, the shift stays draft and is invisible to workers.
        payload.status = selectedWorkers.length ? 'draft' : (form.publish_now ? 'published' : 'draft');
        const created: any = await api('shifts/', { method: 'POST', body: JSON.stringify(payload) });
        createdShiftId = String(created?.id || '');
        if (selectedWorkers.length) {
          await api(`shifts/${created.id}/assign/`, {
            method: 'POST',
            body: JSON.stringify({ workers: selectedWorkers, publish_remaining: form.publish_now }),
          });
        }
        setToast(`${payload.required_count} separate Schichtkarte${payload.required_count === 1 ? '' : 'n'} erstellt.`);
      }
      if (savingCopy) {
        setTab('all');
        if (createdShiftId) setRecentCopyShiftId(createdShiftId);
      }
      const targetWeek = monday(form.date);
      setAnchor(form.date);
      setCopying(false);
      setFormOpen(false);
        window.dispatchEvent(new Event('aplus:dashboard-invalidated'));
      await loadScheduleWeek(targetWeek, false);
    } catch (error: any) {
      setToast(error.message || 'Schicht konnte nicht gespeichert werden.');
    } finally {
      setBusy(false);
    }
  }

  function changeWeek(delta: number, swipeTrack?: HTMLElement) {
    const nextAnchor = addDays(anchor, delta);
    const nextWeek = monday(nextAnchor);
    let cachedRows: any[] | undefined;
    const cached = safeSessionGet(`${WEEK_CACHE_PREFIX}${nextWeek}`);
    if (cached) {
      try {
        const parsed = JSON.parse(cached);
        if (Array.isArray(parsed)) cachedRows = parsed;
      } catch { /* optional cache */ }
    }

    const apply = () => {
      if (cachedRows) {
        localRowsRef.current = cachedRows;
        setRows([...cachedRows, ...liveRowsRef.current]);
      }
      setAnchor(nextAnchor);
    };

    if (swipeTrack) {
      const savedTop = swipeScrollElement.current?.scrollTop ?? swipeScrollTop.current;
      swipeTrack.style.transition = 'none';
      flushSync(apply);
      swipeTrack.style.setProperty('--wiw-swipe-x', '0px');
      swipeTrack.classList.remove('is-dragging', 'is-settling');
      void swipeTrack.offsetWidth;
      swipeTrack.style.transition = '';
      const restore = () => {
        if (swipeScrollElement.current) swipeScrollElement.current.scrollTop = savedTop;
        else window.scrollTo({ top: savedTop, left: window.scrollX, behavior: 'auto' });
      };
      restore();
      window.requestAnimationFrame(() => window.requestAnimationFrame(restore));
    } else {
      apply();
    }
  }

  function toggleGroupFilter(value: string) {
    setGroupFilter((current) => current.includes(value) ? current.filter((item) => item !== value) : [...current, value]);
  }

  function openPdfExport() {
    setPdf({ dateFrom: weekStart, dateTo: addDays(weekStart, 6), workers: [], clients: [], groups: [] });
    setPdfError('');
    setPdfDateField('');
    setPdfOpen(true);
  }

  async function downloadPdf() {
    if (pdfBusy) return;
    if (!pdf.dateFrom || !pdf.dateTo || pdf.dateFrom > pdf.dateTo) {
      setPdfError('Bitte einen gültigen Zeitraum auswählen.');
      return;
    }
    setPdfError('');
    setPdfBusy(true);
    try {
      const params = new URLSearchParams({ date_from: pdf.dateFrom, date_to: pdf.dateTo });
      if (pdf.workers.length) params.set('workers', pdf.workers.join(','));
      if (pdf.clients.length) params.set('clients', pdf.clients.join(','));
      if (pdf.groups.length) params.set('groups', pdf.groups.join(','));
      const result = await apiBlob(`reports/schedule.pdf?${params.toString()}`);
      await saveSchedulePdf(result.blob, result.filename);
      setPdfOpen(false);
      setToast('Dienstplan-PDF erstellt.');
    } catch (error: any) {
      setPdfError(error?.message || 'PDF konnte nicht erstellt werden.');
    } finally {
      setPdfBusy(false);
    }
  }

  if (!active || !mobile || !manager) return null;
  const host = document.querySelector('.app-main') || document.body;

  return createPortal(
    <div className="wiw-schedule-mobile" data-testid="wiw-native-schedule">
      <div className="wiw-schedule-tools">
        <div className="wiw-tabs" role="tablist">
          {([['all', 'Alle'], ['open', 'OpenShifts']] as Array<[TabKey, string]>).map(([key, label]) => <button type="button" role="tab" aria-selected={tab === key} key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>{label}</button>)}
          <button type="button" className="wiw-pdf-button" onClick={openPdfExport}><IonIcon icon={documentTextOutline} />PDF</button>
        </div>
        <div className="wiw-group-filters" aria-label="Bereiche filtern">
          {SCHEDULE_GROUPS.map((choice) => <button type="button" key={choice.value} className={groupFilter.includes(choice.value) ? 'active' : ''} aria-pressed={groupFilter.includes(choice.value)} onClick={() => toggleGroupFilter(choice.value)}>{choice.label}</button>)}
        </div>
        <div className="wiw-search-row"><IonIcon icon={filterOutline} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filtern …" /><button type="button" onClick={() => void load()}>{busy ? '…' : '↻'}</button></div>
      </div>

      {tab !== 'open' ? <div className="wiw-week-strip">
        <button type="button" onClick={() => changeWeek(-7)}>‹</button>
        {days.map((day) => {
          const activeDay = day === anchor;
          const label = formatDayHeader(day);
          return <button type="button" key={day} className={`${activeDay ? 'active ' : ''}${day === berlinToday() ? 'today' : ''}`} onClick={() => { setAnchor(day); document.getElementById(`wiw-day-${day}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }}><small>{label.weekday.slice(0, 2)}</small><b>{keyDate(day).getUTCDate()}</b></button>;
        })}
        <button type="button" onClick={() => changeWeek(7)}>›</button>
      </div> : null}

      {tab !== 'open' ? <div className="wiw-week-swipe-viewport">
        <div
          className="wiw-week-swipe-track"
          onTouchStart={(event) => {
            const touch = event.touches[0];
            swipe.current = { x: touch.clientX, y: touch.clientY };
            swipeTravel.current = 0;
            swipeAxis.current = null;
            swipeScrollElement.current = null;
            swipeScrollTop.current = window.scrollY;
            event.currentTarget.classList.remove('is-dragging', 'is-settling');
            event.currentTarget.style.setProperty('--wiw-swipe-x', '0px');
            const ionContent = document.querySelector('ion-content.app-content') as any;
            void ionContent?.getScrollElement?.().then((element: HTMLElement) => {
              swipeScrollElement.current = element;
              swipeScrollTop.current = element.scrollTop;
            }).catch(() => {
              swipeScrollElement.current = null;
              swipeScrollTop.current = window.scrollY;
            });
          }}
          onTouchMove={(event) => {
            if (!swipe.current || !event.touches.length) return;
            const touch = event.touches[0];
            const dx = touch.clientX - swipe.current.x;
            const dy = touch.clientY - swipe.current.y;
            if (!swipeAxis.current && (Math.abs(dx) > 7 || Math.abs(dy) > 7)) {
              swipeAxis.current = Math.abs(dx) > Math.abs(dy) * 1.12 ? 'horizontal' : 'vertical';
            }
            if (swipeAxis.current !== 'horizontal') return;
            if (event.cancelable) event.preventDefault();
            const width = event.currentTarget.parentElement?.clientWidth || window.innerWidth;
            swipeTravel.current = Math.max(-width, Math.min(width, dx));
            event.currentTarget.classList.add('is-dragging');
            if (swipeFrame.current) return;
            const target = event.currentTarget;
            swipeFrame.current = window.requestAnimationFrame(() => {
              swipeFrame.current = undefined;
              target.style.setProperty('--wiw-swipe-x', `${swipeTravel.current}px`);
            });
          }}
          onTouchEnd={(event) => {
            if (swipeFrame.current) window.cancelAnimationFrame(swipeFrame.current);
            swipeFrame.current = undefined;
            if (!swipe.current || !event.changedTouches.length) return;
            const touch = event.changedTouches[0];
            const dx = touch.clientX - swipe.current.x;
            const dy = touch.clientY - swipe.current.y;
            const axis = swipeAxis.current;
            swipe.current = undefined;
            swipeAxis.current = null;
            const target = event.currentTarget;
            target.classList.remove('is-dragging');
            target.classList.add('is-settling');
            if (axis === 'horizontal' && Math.abs(dx) > 44 && Math.abs(dx) > Math.abs(dy) * 1.12) {
              const width = target.parentElement?.clientWidth || window.innerWidth;
              target.style.setProperty('--wiw-swipe-x', `${dx < 0 ? -width : width}px`);
              window.setTimeout(() => changeWeek(dx < 0 ? 7 : -7, target), 180);
              return;
            }
            target.style.setProperty('--wiw-swipe-x', '0px');
            window.setTimeout(() => target.classList.remove('is-settling'), 180);
          }}
          onTouchCancel={(event) => {
            if (swipeFrame.current) window.cancelAnimationFrame(swipeFrame.current);
            swipeFrame.current = undefined;
            swipe.current = undefined;
            swipeAxis.current = null;
            event.currentTarget.classList.remove('is-dragging');
            event.currentTarget.classList.add('is-settling');
            event.currentTarget.style.setProperty('--wiw-swipe-x', '0px');
            window.setTimeout(() => event.currentTarget.classList.remove('is-settling'), 180);
          }}
        >
          <AdjacentWeekPreview weekStart={addDays(weekStart, -7)} groupFilter={groupFilter} query={query} side="prev" />
          <div key={weekStart} className="wiw-week-scroll wiw-week-pane wiw-week-pane-center">
            {visibleDays.map((day) => {
              const header = formatDayHeader(day);
              const dayCards = byDay[day] || [];
              return <section className="wiw-day-section wiw-day-visual" id={`wiw-day-${day}`} key={day}>
                <header><span className="wiw-day-header-spacer"/><div className="wiw-day-heading"><strong>{header.weekday}</strong><span>{header.date}</span></div><em>{dayCards.length}<small> · {dayCards.reduce((sum, card) => { const gross = Math.max(0, (new Date(card.shift.ends_at).getTime() - new Date(card.shift.starts_at).getTime()) / 3600000); return sum + Math.max(0, gross - Number(card.shift.break_minutes || 0) / 60); }, 0).toFixed(1)} Std.</small></em></header>
                {dayCards.map((card, index) => <React.Fragment key={card.key}>{index > 0 && clientKey(dayCards[index - 1].shift) !== clientKey(card.shift) ? <div className="wiw-client-divider" aria-hidden="true" /> : null}<button type="button" className={`wiw-shift-card ${card.shift.status === 'draft' ? 'is-draft' : card.isOpen ? 'is-open' : 'is-filled'} ${recentCopyShiftId && String(card.shift.id) === recentCopyShiftId ? 'is-copy-entering' : ''}`} style={shiftCardStyle(card.shift)} onClick={() => card.shift.read_only ? setToast('WIW OpenShift · schreibgeschützt') : openEdit(card)}>
                  <div className="wiw-card-main">
                    <CardWorkerAvatar worker={card.worker} open={card.isOpen} draft={card.shift.status === 'draft'} />
                    <span className="wiw-card-copy"><b>{cardWorkerShortName(card.worker?.name) || (card.shift.status === 'draft' ? 'Entwurf' : 'OpenShift')}{card.isOpen && card.shift.status !== 'draft' ? <span className="wiw-open-alert">!</span> : null}</b><small>{cardPositionShortLabel(card.shift.position_name)}</small></span>
                    <span className="wiw-card-meta"><b>{formatTimeIso(card.shift.starts_at)}–{formatTimeIso(card.shift.ends_at)}</b><small>{card.shift.location_name || 'Einsatzort'}</small></span>
                  </div>
                </button></React.Fragment>)}
                {!dayCards.length ? <div className="wiw-day-empty">Keine Schichten</div> : null}
              </section>;
            })}
          </div>
          <AdjacentWeekPreview weekStart={addDays(weekStart, 7)} groupFilter={groupFilter} query={query} side="next" />
        </div>
      </div> : <div className="wiw-week-scroll">
        {visibleDays.map((day) => {
          const header = formatDayHeader(day);
          const dayCards = byDay[day] || [];
          return <section className="wiw-day-section wiw-day-visual" id={`wiw-day-${day}`} key={day}>
            <header><span className="wiw-day-header-spacer"/><div className="wiw-day-heading"><strong>{header.weekday}</strong><span>{header.date}</span></div><em>{dayCards.length}<small> · {dayCards.reduce((sum, card) => { const gross = Math.max(0, (new Date(card.shift.ends_at).getTime() - new Date(card.shift.starts_at).getTime()) / 3600000); return sum + Math.max(0, gross - Number(card.shift.break_minutes || 0) / 60); }, 0).toFixed(1)} Std.</small></em></header>
            {dayCards.map((card, index) => <React.Fragment key={card.key}>{index > 0 && clientKey(dayCards[index - 1].shift) !== clientKey(card.shift) ? <div className="wiw-client-divider" aria-hidden="true" /> : null}<button type="button" className={`wiw-shift-card ${card.shift.status === 'draft' ? 'is-draft' : card.isOpen ? 'is-open' : 'is-filled'}`} style={shiftCardStyle(card.shift)} onClick={() => card.shift.read_only ? setToast('WIW OpenShift · schreibgeschützt') : openEdit(card)}>
              <div className="wiw-card-main"><CardWorkerAvatar worker={card.worker} open={card.isOpen} draft={card.shift.status === 'draft'} /><span className="wiw-card-copy"><b>{cardWorkerShortName(card.worker?.name) || 'OpenShift'}</b><small>{cardPositionShortLabel(card.shift.position_name)}</small></span><span className="wiw-card-meta"><b>{formatTimeIso(card.shift.starts_at)}–{formatTimeIso(card.shift.ends_at)}</b><small>{card.shift.location_name || 'Einsatzort'}</small></span></div>
            </button></React.Fragment>)}
          </section>;
        })}
        {!visibleDays.length ? <div className="wiw-day-empty">Keine verfügbaren OpenShifts</div> : null}
      </div>}

      {tab !== 'open' ? <div className="wiw-week-total"><span>Gesamtstunden</span><strong>{weekHours.toFixed(1)}</strong></div> : null}
      <button type="button" className="wiw-create-fab" aria-label="Schicht anlegen" onClick={() => openCreate(anchor)}>+</button>

      {formOpen ? <div ref={formScreenRef} className="wiw-shift-form-screen" data-testid="wiw-shift-form">
        <header className="wiw-form-topbar"><button type="button" onClick={() => { noteRef.current?.blur(); setTimeEditorDateOpen(false); setTimeEditor(undefined); setTimeLogOpen(false); setFormOpen(false); }}>Abbrechen</button><strong>{copying ? 'Kopie bearbeiten' : editing ? 'Bearbeite Schicht' : 'Erstelle Schicht'}</strong><button type="button" disabled={busy || !form.client || !form.location || !form.position || form.startMinute == null || form.endAbsolute == null || (form.startMinute != null && form.endAbsolute != null && form.endAbsolute <= form.startMinute)} onClick={() => void save()}>Sichern</button></header>
        {dateOpen ? <ScheduleDatePicker value={form.date} onSelect={(date) => { setForm((current) => ({ ...current, date })); setDateOpen(false); }} onClose={() => setDateOpen(false)} /> : null}
        <div ref={formScrollRef} className="wiw-form-scroll">
          <Row icon={calendarOutline} label={formatDateRow(form.date)} field="date" onClick={() => setDateOpen(true)} />
          {isHotelClientName(selectedClientName) ? <div className="wiw-hotel-presets">{HOTEL_TIME_PRESETS.map((preset) => <button type="button" key={preset.key} onClick={() => setForm((current) => ({ ...current, startMinute: preset.start, endAbsolute: preset.end }))}><b>{preset.label}</b><small>{formatMinute(preset.start)}–{formatMinute(preset.end)}</small></button>)}</div> : null}
          <div className="wiw-time-row-wrap">
            <Row
              icon={timeOutline}
              label={form.startMinute == null || form.endAbsolute == null ? 'Wähle Zeitrahmen' : `${formatMinute(form.startMinute)} ${form.endAbsolute >= 1440 ? '~ ' : '– '}${formatMinute(form.endAbsolute)}`}
              muted={form.startMinute == null}
              onClick={() => { ensureTime(); setTimeOpen((value) => !value); }}
              trailing={<span className="wiw-time-pause-tail"><small>Pause: {automaticBreak(form.startMinute, form.endAbsolute)} Min</small><IonIcon className="wiw-row-chevron" icon={chevronForwardOutline} /></span>}
            />
            {timeOpen && form.startMinute != null && form.endAbsolute != null ? <TimeFrameWheel start={form.startMinute} end={form.endAbsolute} onChange={(start, end) => setForm((current) => ({ ...current, startMinute: start, endAbsolute: end }))} /> : null}
          </div>
          <Row icon={calendarOutline} label={form.schedule_groups.length ? form.schedule_groups.map((value) => SCHEDULE_GROUPS.find((item) => item.value === value)?.label || value).join(', ') : 'Wähle Zeitplan'} muted={!form.schedule_groups.length} onClick={() => setSheet('groups')} />

          <div className="wiw-form-separator" />
          <Row icon={briefcaseOutline} label={positionChoices.find((item) => item.value === form.position)?.label || 'Füge Position hinzu'} muted={!form.position} onClick={() => setSheet('position')} />
          <Row field="client" icon={peopleOutline} label={clientChoices.find((item) => item.value === form.client)?.label || 'Kunde auswählen'} muted={!form.client} onClick={() => setSheet('client')} />
          <Row field="location" icon={locationOutline} label={locationChoices.find((item) => item.value === form.location)?.label || 'Jobstandort'} muted={!form.location} onClick={() => form.client ? setSheet('location') : setSheet('client')} />

          <div className="wiw-form-separator" />
          <Row icon={personOutline} label="OpenShift" value={form.publish_now ? 'Für passende Mitarbeiter sichtbar' : 'Aus · ohne Zuweisung nur als Entwurf'} trailing={<Switch checked={form.publish_now} onChange={(value) => setForm((current) => ({ ...current, publish_now: value }))} />} />
          {!editing ? <Row icon={layersOutline} label={`${form.required_count} Schicht${form.required_count === 1 ? '' : 'en'}`} trailing={<div className="wiw-count-stepper"><button type="button" onClick={() => setForm((current) => ({ ...current, required_count: Math.max(current.workers.length || 1, current.required_count - 1) }))}>−</button><b>{form.required_count}</b><button type="button" onClick={() => setForm((current) => ({ ...current, required_count: current.required_count + 1 }))}>+</button></div>} /> : <Row icon={layersOutline} label="1 Schichtkarte" value={editing.workerName || 'OpenShift'} emphasizeValue={Boolean(editing.workerName)} />}
          <Row icon={checkmarkOutline} label="Erfordere Übernahme-Bestätigung" trailing={<Switch checked={form.confirmation_required} onChange={(value) => setForm((current) => ({ ...current, confirmation_required: value }))} />} />
          <Row icon={peopleOutline} label={editing ? (form.workers.length ? 'Mitarbeiter ändern' : 'Mitarbeiter zuweisen') : (form.workers.length ? `${form.workers.length} Benutzer direkt zugewiesen` : 'Geeignete Benutzer anzeigen')} value={selectedWorkerNames || undefined} emphasizeValue={Boolean(selectedWorkerNames)} muted={!form.workers.length} onClick={() => setSheet('workers')} />

          {isAdmin && editing?.workerId ? <>
            <Row
              field="admin-time"
              icon={timeOutline}
              label="Arbeitszeit"
              value={editingTimeEntry ? (editingTimeEntry.wiw_time_id ? 'WIW · schreibgeschützt' : 'Zeit bearbeiten') : 'Zeit eintragen'}
              emphasizeValue
              onClick={openAdminTimeEditor}
            />
            <Row
              field="admin-time-log"
              icon={documentTextOutline}
              label="Zeitlog"
              value={editingTimeEntries.length ? `${editingTimeEntries.length} Eintrag${editingTimeEntries.length === 1 ? '' : 'e'} · Anzeigen` : 'Anzeigen'}
              emphasizeValue={Boolean(editingTimeEntries.length)}
              onClick={() => setTimeLogOpen(true)}
            />
          </> : null}

          {editing && editing.parentCount > 1 && !editing.isOpen ? <div className="wiw-bulk-edit-row"><div><b>Alle Karten dieser Schicht mitändern</b><span>Wenn aus, wird nur diese Person / OpenShift-Karte geändert.</span></div><Switch checked={form.apply_all} onChange={(value) => setForm((current) => ({ ...current, apply_all: value }))} /></div> : null}

          <div className="wiw-form-separator" />
          <Row
            icon={colorPaletteOutline}
            label="Standardfarbe"
            colorManaged
            onClick={() => setSheet('color')}
            trailing={<span className="wiw-color-row-tail"><i style={form.color_hue == null ? ({ background: formPalette.accent } as React.CSSProperties) : ({ '--wiw-color-hue': String(form.color_hue ?? formAutoHue) } as React.CSSProperties)} /><b>{form.color_hue == null ? 'Kundenfarbe · automatisch' : (COLOR_CHOICES.find((choice) => choice.hue === form.color_hue)?.label || 'Individuell')}</b><IonIcon className="wiw-row-chevron" icon={chevronForwardOutline} /></span>}
          />
          <div className="wiw-note-editor">
            <div className="wiw-note-editor-toolbar">
              <span className="wiw-note-editor-title"><IonIcon icon={documentTextOutline} /><span>Notiz</span></span>
              <button type="button" onClick={() => { noteRef.current?.blur(); setToast('Notiz übernommen.'); }}>Fertig</button>
            </div>
            <textarea
              ref={noteRef}
              aria-label="Notiz"
              value={form.notes}
              onFocus={() => window.setTimeout(() => noteRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 120)}
              onChange={(event) => setForm((current) => ({ ...current, notes: event.target.value }))}
              placeholder="Hinweis für Mitarbeiter …"
            />
          </div>

          {editing ? <>
            <div className="wiw-form-separator" />
            {editing.workerName ? <Row icon={notificationsOutline} label="Erinnerung senden" value={editing.workerName} emphasizeValue onClick={() => void sendManualReminder()} /> : null}
            <Row icon={copyOutline} label="Schicht kopieren" onClick={prepareCopyAsOpenShift} />
            <Row icon={trashOutline} label="Schicht löschen" onClick={() => void deleteEditingShift()} />
          </> : null}
        </div>

        {sheet === 'client' ? <ChoiceSheet title="Kunde" choices={clientChoices} selected={form.client} onClose={() => setSheet('')} onSelect={(choice) => { const nextName = clients.find((item: any) => String(item.id) === choice.value)?.name; const matchingLocations = locations.filter((item: any) => String(item.client) === choice.value); const uniqueLocation = matchingLocations.length === 1 ? String(matchingLocations[0].id) : ''; setForm((current) => ({ ...current, client: choice.value, location: uniqueLocation, schedule_groups: current.schedule_groups.length ? current.schedule_groups : (isHotelClientName(nextName) ? ['front_office', 'housekeeping'] : ['service']) })); setSheet(matchingLocations.length > 1 ? 'location' : ''); }} /> : null}
        {sheet === 'position' ? <ChoiceSheet title="Position" choices={positionChoices} selected={form.position} onClose={() => setSheet('')} onSelect={(choice) => { setForm((current) => ({ ...current, position: choice.value })); setSheet(''); }} /> : null}
        {sheet === 'location' ? <ChoiceSheet title="Jobstandort" choices={locationChoices} selected={form.location} onClose={() => setSheet('')} onSelect={(choice) => { setForm((current) => ({ ...current, location: choice.value })); setSheet(''); }} /> : null}
        {sheet === 'groups' ? <MultiChoiceSheet title="Zeitplan" choices={SCHEDULE_GROUPS} selected={form.schedule_groups} onClose={() => setSheet('')} onChange={(values) => setForm((current) => { const currentPosition = positions.find((item: any) => String(item.id) === current.position); const keepPosition = !current.position || !values.length || values.includes(positionGroup(currentPosition?.name)); return { ...current, schedule_groups: values, position: keepPosition ? current.position : '' }; })} /> : null}
        {sheet === 'color' ? <ColorSheet selected={form.color_hue} autoHue={formAutoHue} onClose={() => setSheet('')} onSelect={(hue) => setForm((current) => ({ ...current, color_hue: hue }))} /> : null}
        {sheet === 'workers' ? <MultiChoiceSheet title={editing ? 'Mitarbeiter auswählen / ändern' : 'Geeignete Benutzer'} choices={workerChoices} selected={form.workers} limit={editing ? 1 : form.required_count} onClose={() => setSheet('')} onChange={(values) => setForm((current) => ({ ...current, workers: values, apply_all: editing ? false : current.apply_all }))} /> : null}
      </div> : null}

      {timeEditor ? <div className="wiw-sheet-backdrop wiw-admin-time-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !timeBusy) { setTimeEditorDateOpen(false); setTimeEditor(undefined); } }}>
        <section className="wiw-admin-time-sheet" role="dialog" aria-modal="true" aria-label="Arbeitszeit bearbeiten">
          <header><div><small>ARBEITSZEIT · NUR ADMIN</small><b>{timeEditor.entry ? 'Zeit bearbeiten' : 'Zeit eintragen'}</b><span>{editing?.workerName || 'Mitarbeiter'}</span></div><button type="button" disabled={timeBusy} onClick={() => { setTimeEditorDateOpen(false); setTimeEditor(undefined); }}>Abbrechen</button></header>
          <div className="wiw-admin-time-fields">
            <div className="wiw-admin-time-picker-block">
              <span>Datum</span>
              <button type="button" className="wiw-admin-picker-button" onClick={() => setTimeEditorDateOpen(true)}>
                <IonIcon icon={calendarOutline}/><b>{formatDateRow(timeEditor.date)}</b><IonIcon icon={chevronForwardOutline}/>
              </button>
            </div>
            <div className="wiw-admin-time-picker-block">
              <span>Arbeitszeit</span>
              <button type="button" className="wiw-admin-picker-button" onClick={() => setTimeEditor((current: any) => ({ ...current, timeOpen: !current.timeOpen }))}>
                <IonIcon icon={timeOutline}/><b>{formatMinute(Number(timeEditor.startMinute || 0))} – {Number(timeEditor.endAbsolute || 0) >= 1440 ? '~ ' : ''}{formatMinute(Number(timeEditor.endAbsolute || 0))}</b><IonIcon icon={chevronForwardOutline}/>
              </button>
              {timeEditor.timeOpen ? <TimeFrameWheel
                start={Number(timeEditor.startMinute || 0)}
                end={Number(timeEditor.endAbsolute || 15)}
                onChange={(start, end) => setTimeEditor((current: any) => ({ ...current, startMinute: start, endAbsolute: end }))}
              /> : null}
            </div>
            <div className="wiw-admin-time-picker-block">
              <span>Pause</span>
              <div className="wiw-admin-pause-row">
                {[0,15,30,45,60].map((minutes) => <button type="button" key={minutes} className={Number(timeEditor.break_minutes || 0) === minutes ? 'active' : ''} onClick={() => setTimeEditor((current: any) => ({ ...current, break_minutes: minutes }))}>{minutes} Min.</button>)}
              </div>
              <label className="wiw-admin-pause-custom">Andere Minuten<input type="number" min="0" step="5" inputMode="numeric" value={timeEditor.break_minutes ?? 0} onChange={(event) => setTimeEditor((current: any) => ({ ...current, break_minutes: Math.max(0, Number(event.target.value || 0)) }))} /></label>
            </div>
            <label className="wide">Notiz / Änderungsgrund<textarea value={timeEditor.reason || ''} onChange={(event) => setTimeEditor((current: any) => ({ ...current, reason: event.target.value }))} placeholder="z. B. Korrektur laut Einsatzleitung" /></label>
          </div>
          <footer><button type="button" disabled={timeBusy} onClick={() => { setTimeEditorDateOpen(false); setTimeEditor(undefined); }}>Abbrechen</button><button type="button" className="primary" disabled={timeBusy || !timeEditor.date || timeEditor.startMinute == null || timeEditor.endAbsolute == null} onClick={() => void saveAdminTime()}>{timeBusy ? 'Wird gespeichert …' : 'Arbeitszeit speichern'}</button></footer>
        </section>
      </div> : null}

      {timeEditor && timeEditorDateOpen ? <ScheduleDatePicker
        title="Arbeitstag"
        value={timeEditor.date}
        onSelect={(date) => { setTimeEditor((current: any) => ({ ...current, date })); setTimeEditorDateOpen(false); }}
        onClose={() => setTimeEditorDateOpen(false)}
      /> : null}

      {timeLogOpen && isAdmin && editing?.workerId ? <div className="wiw-sheet-backdrop wiw-admin-time-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setTimeLogOpen(false); }}>
        <section className="wiw-admin-log-sheet" role="dialog" aria-modal="true" aria-label="Zeitlog">
          <header><div><small>ZEITLOG · NUR ADMIN</small><b>Arbeitszeit-Verlauf</b><span>{editing.workerName || 'Mitarbeiter'}</span></div><button type="button" onClick={() => setTimeLogOpen(false)}>Fertig</button></header>
          <div className="wiw-admin-log-scroll" data-testid="wiw-admin-time-log">
            {editingTimeEntries.length ? editingTimeEntries.map((entry: any) => <div className="wiw-admin-time-log-entry" key={entry.id}>
              <div className="wiw-admin-time-log-main"><strong>{adminLogStamp(entry.clock_in)}–{entry.clock_out ? adminLogStamp(entry.clock_out) : 'offen'}</strong><span>Pause {entry.break_minutes || 0} Min. · {adminWorkedLabel(entry.worked_minutes)}</span></div>
              <small>{adminTimeSource(entry.source)} · {entry.approved ? 'freigegeben' : 'offen'}{entry.approved_by_name ? ` · ${entry.approved_by_name}` : ''}</small>
              <small>Erstellt {adminLogStamp(entry.created_at)} · geändert {adminLogStamp(entry.updated_at)}</small>
              {entry.edit_reason ? <small className="wiw-admin-time-log-reason">{String(entry.edit_reason).replace(/\n/g, ' · ')}</small> : null}
              {(entry.logs || []).slice(0, 8).map((log: any, index: number) => <small className="wiw-admin-time-audit" key={`${entry.id}-${index}`}>{adminLogStamp(log.created_at)} · {adminAuditLabel(log.action)} · {log.actor}{log.metadata?.reason ? ` · ${log.metadata.reason}` : ''}</small>)}
            </div>) : <div className="wiw-admin-time-empty">Noch kein Zeiteintrag für diese Schichtkarte.</div>}
          </div>
        </section>
      </div> : null}

      {pdfOpen && pdfDateField ? <ScheduleDatePicker title="PDF Zeitraum" value={pdf[pdfDateField]} onSelect={(date) => { setPdf((current) => ({ ...current, [pdfDateField]: date })); setPdfDateField(''); }} onClose={() => setPdfDateField('')} /> : null}
      {pdfOpen ? <div className="wiw-sheet-backdrop wiw-pdf-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !pdfBusy) setPdfOpen(false); }}>
        <section className="wiw-pdf-sheet">
          <header><div><b>Dienstplan als PDF</b><small>Filter auswählen und exportieren</small></div><button type="button" disabled={pdfBusy} onClick={() => void downloadPdf()}>{pdfBusy ? 'Erstellen…' : 'Fertig'}</button></header>
          <div className="wiw-pdf-scroll">
            <div className="wiw-pdf-dates"><label>Von<button type="button" aria-label="PDF Startdatum" onClick={() => setPdfDateField('dateFrom')}>{formatDateRow(pdf.dateFrom)}</button></label><label>Bis<button type="button" aria-label="PDF Enddatum" onClick={() => setPdfDateField('dateTo')}>{formatDateRow(pdf.dateTo)}</button></label></div>
            <div className="wiw-pdf-filter-block"><b>Mitarbeiter</b><div className="wiw-pdf-chip-grid"><button type="button" aria-pressed={pdf.workers.length === 0} className={pdf.workers.length === 0 ? 'active' : ''} onClick={() => setPdf((current) => ({ ...current, workers: [] }))}>Alle Mitarbeiter</button>{workerChoices.map((choice) => <button type="button" key={choice.value} className={pdf.workers.includes(choice.value) ? 'active' : ''} onClick={() => setPdf((current) => ({ ...current, workers: current.workers.includes(choice.value) ? current.workers.filter((item) => item !== choice.value) : [...current.workers, choice.value] }))}>{choice.label}</button>)}</div><small>Nichts ausgewählt = alle Mitarbeiter</small></div>
            <div className="wiw-pdf-filter-block"><b>Kunden</b><div className="wiw-pdf-chip-grid"><button type="button" aria-pressed={pdf.clients.length === 0} className={pdf.clients.length === 0 ? 'active' : ''} onClick={() => setPdf((current) => ({ ...current, clients: [] }))}>Alle Kunden</button>{clientChoices.map((choice) => <button type="button" key={choice.value} className={pdf.clients.includes(choice.value) ? 'active' : ''} onClick={() => setPdf((current) => ({ ...current, clients: current.clients.includes(choice.value) ? current.clients.filter((item) => item !== choice.value) : [...current.clients, choice.value] }))}>{choice.label}</button>)}</div><small>Nichts ausgewählt = alle Kunden</small></div>
            <div className="wiw-pdf-filter-block"><b>{pdfHasHotel ? 'Hotel-Bereich / Zeitplan' : 'Zeitplan'}</b><div className="wiw-pdf-chip-grid compact">{SCHEDULE_GROUPS.map((choice) => <button type="button" key={choice.value} className={pdf.groups.includes(choice.value) ? 'active' : ''} onClick={() => setPdf((current) => ({ ...current, groups: current.groups.includes(choice.value) ? current.groups.filter((item) => item !== choice.value) : [...current.groups, choice.value] }))}>{choice.label}</button>)}</div><small>Nichts ausgewählt = alle Bereiche</small></div>
          </div>
          {pdfError ? <p className="wiw-pdf-error" role="alert">{pdfError}</p> : null}
          <footer><button type="button" disabled={pdfBusy} onClick={() => setPdfOpen(false)}>Abbrechen</button><button type="button" className="primary" disabled={pdfBusy || !pdf.dateFrom || !pdf.dateTo} onClick={() => void downloadPdf()}>{pdfBusy ? 'PDF wird erstellt…' : 'PDF erstellen'}</button></footer>
        </section>
      </div> : null}

      {toast ? <button type="button" className="wiw-toast" onClick={() => setToast('')}>{toast}</button> : null}
    </div>,
    host,
  );
}

function emptyForm(date: string): FormState {
  return {
    client: '',
    date,
    startMinute: null,
    endAbsolute: null,
    position: '',
    location: '',
    required_count: 1,
    publish_now: true,
    confirmation_required: false,
    workers: [],
    schedule_groups: ['service'],
    color_hue: null,
    notes: '',
    apply_all: false,
  };
}
