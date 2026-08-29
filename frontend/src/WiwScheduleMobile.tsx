import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
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
  peopleOutline,
  personOutline,
  timeOutline,
  trashOutline,
} from 'ionicons/icons';
import { api } from './api';
import './wiw-schedule-mobile.css';

type TabKey = 'all' | 'open' | 'filled' | 'draft';
type Choice = { value: string; label: string };
type EditingCard = { shiftId: string; slotId: string; parentCount: number; workerName?: string; isOpen: boolean };
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
  notes: string;
  apply_all: boolean;
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
const WHEEL_ROW = 44;
const POSITION_ORDER = [
  { label: 'Servicekraft', aliases: ['servicekraft', 'servicekrat'] },
  { label: 'Serviceleitung', aliases: ['serviceleitung'] },
  { label: 'Front-Office', aliases: ['frontoffice'] },
  { label: 'Housekeeping', aliases: ['housekeeping', 'houskeeping'] },
  { label: 'Bar-Support', aliases: ['barsupport'] },
];
const SCHEDULE_GROUPS: Choice[] = [
  { value: 'service', label: 'Service' },
  { value: 'front_office', label: 'Front Office' },
  { value: 'housekeeping', label: 'Housekeeping' },
];
const unpack = (value: any): any[] => value?.results || value || [];
const pad = (value: number) => String(value).padStart(2, '0');
const normalize = (value: string) => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]/g, '');

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
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    const index = Math.max(0, items.findIndex((item) => item.value === value));
    if (ref.current) ref.current.scrollTop = index * WHEEL_ROW;
  }, [items, value]);
  const settle = () => {
    if (!ref.current) return;
    const index = Math.max(0, Math.min(items.length - 1, Math.round(ref.current.scrollTop / WHEEL_ROW)));
    ref.current.scrollTo({ top: index * WHEEL_ROW, behavior: 'smooth' });
    onChange(items[index].value);
  };
  return (
    <div
      ref={ref}
      className="wiw-wheel-column"
      onScroll={() => {
        window.clearTimeout(timer.current);
        timer.current = window.setTimeout(settle, 80);
      }}
      onPointerUp={settle}
    >
      {items.map((item) => (
        <button type="button" key={item.value} className={item.value === value ? 'active' : ''} onClick={() => onChange(item.value)}>{item.label}</button>
      ))}
    </div>
  );
}

function TimeFrameWheel({ start, end, onChange }: { start: number; end: number; onChange: (start: number, end: number) => void }) {
  const starts = useMemo(() => Array.from({ length: 96 }, (_, index) => ({ value: index * 15, label: formatMinute(index * 15) })), []);
  const ends = useMemo(() => Array.from({ length: 96 }, (_, index) => {
    const value = start + (index + 1) * 15;
    return { value, label: `${value >= 1440 ? '~' : ''}${formatMinute(value)}` };
  }), [start]);
  const safeEnd = ends.some((item) => item.value === end) ? end : Math.min(start + 360, start + 1440);
  return (
    <div className="wiw-time-wheel" data-testid="wiw-time-wheel">
      <div className="wiw-wheel-highlight" />
      <WheelColumn items={starts} value={start} onChange={(next) => onChange(next, next + 360)} />
      <WheelColumn items={ends} value={safeEnd} onChange={(next) => onChange(start, next)} />
    </div>
  );
}

function Switch({ checked, onChange }: { checked: boolean; onChange: (value: boolean) => void }) {
  return <button type="button" className={`wiw-switch ${checked ? 'on' : ''}`} aria-pressed={checked} onClick={() => onChange(!checked)}><span /></button>;
}

function Row({ icon, label, value, muted, green, onClick, trailing }: { icon: string; label: string; value?: string; muted?: boolean; green?: boolean; onClick?: () => void; trailing?: React.ReactNode }) {
  const Component: any = onClick ? 'button' : 'div';
  return (
    <Component type={onClick ? 'button' : undefined} className={`wiw-form-row ${muted ? 'muted' : ''} ${green ? 'green' : ''}`} onClick={onClick}>
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

function MultiChoiceSheet({ title, choices, selected, limit, onChange, onClose }: { title: string; choices: Choice[]; selected: string[]; limit?: number; onChange: (values: string[]) => void; onClose: () => void }) {
  return (
    <div className="wiw-sheet-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="wiw-choice-sheet">
        <header><b>{title}</b><button type="button" onClick={onClose}>Fertig</button></header>
        <div>{choices.map((choice) => {
          const checked = selected.includes(choice.value);
          return <button type="button" key={choice.value} className={checked ? 'selected' : ''} onClick={() => {
            if (checked) onChange(selected.filter((value) => value !== choice.value));
            else if (!limit || selected.length < limit) onChange([...selected, choice.value]);
          }}><span>{choice.label}</span>{checked ? <IonIcon icon={checkmarkOutline} /> : null}</button>;
        })}</div>
      </section>
    </div>
  );
}

export default function WiwScheduleMobile() {
  const [active, setActive] = useState(false);
  const [mobile, setMobile] = useState(() => typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches);
  const [manager, setManager] = useState(false);
  const [rows, setRows] = useState<any[]>([]);
  const [clients, setClients] = useState<any[]>([]);
  const [locations, setLocations] = useState<any[]>([]);
  const [positions, setPositions] = useState<any[]>([]);
  const [workers, setWorkers] = useState<any[]>([]);
  const [anchor, setAnchor] = useState(berlinToday());
  const [tab, setTab] = useState<TabKey>('all');
  const [query, setQuery] = useState('');
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<EditingCard>();
  const [form, setForm] = useState<FormState>(() => emptyForm(berlinToday()));
  const [timeOpen, setTimeOpen] = useState(false);
  const [dateOpen, setDateOpen] = useState(false);
  const [sheet, setSheet] = useState<'client' | 'position' | 'location' | 'workers' | 'groups' | ''>('');
  const [extrasOpen, setExtrasOpen] = useState(false);
  const swipe = useRef<{ x: number; y: number } | undefined>(undefined);

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
    const sync = () => setActive(Boolean(document.querySelector('.mobile-first-app-shell-v1[data-view="schedule"]')));
    sync();
    const observer = new MutationObserver(sync);
    if (root) observer.observe(root, { subtree: true, childList: true, attributes: true, attributeFilter: ['data-view'] });
    return () => observer.disconnect();
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
      if (!cancelled) setManager(['admin', 'manager'].includes(user?.role));
    }).catch(() => setManager(false));
    return () => { cancelled = true; };
  }, [active, mobile]);

  const load = async () => {
    if (!manager) return;
    setBusy(true);
    try {
      const [shiftData, clientData, locationData, positionData, workerData] = await Promise.all([
        api('shifts/?ordering=starts_at'),
        api('clients/'),
        api('locations/'),
        api('positions/'),
        api('workers/?ordering=user__last_name'),
      ]);
      setRows(unpack(shiftData));
      setClients(unpack(clientData).filter((item: any) => item.active !== false));
      setLocations(unpack(locationData).filter((item: any) => item.active !== false));
      setPositions(unpack(positionData).filter((item: any) => item.active !== false));
      setWorkers(unpack(workerData).filter((item: any) => item.active !== false && !String(item?.user_detail?.email || '').endsWith('@sync.invalid')));
    } catch (error: any) {
      setToast(error.message || 'Dienstplan konnte nicht geladen werden.');
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (!active || !mobile || !manager) return;
    document.body.classList.add('wiw-native-schedule-active');
    const requested = sessionStorage.getItem('aplus:schedule-entry-filter');
    sessionStorage.removeItem('aplus:schedule-entry-filter');
    setTab(requested === 'open' ? 'open' : 'all');
    void load();
    return () => document.body.classList.remove('wiw-native-schedule-active');
  }, [active, mobile, manager]);

  const weekStart = monday(anchor);
  const days = useMemo(() => Array.from({ length: 7 }, (_, index) => addDays(weekStart, index)), [weekStart]);
  const cards = useMemo<CardRow[]>(() => rows.flatMap((shift: any) => activeSlots(shift).map((slot: any) => ({
    key: `${shift.id}:${slot.id}`,
    shift,
    slot,
    worker: slot.worker || undefined,
    isOpen: Boolean(slot.is_open || (slot.status === 'open' && !slot.worker)),
  }))), [rows]);
  const visibleCards = useMemo(() => cards.filter((card) => {
    const shiftDay = dateKeyFromIso(card.shift.starts_at);
    if (tab === 'open') {
      if (!card.isOpen) return false;
      if (card.shift.ends_at && new Date(card.shift.ends_at).getTime() < Date.now()) return false;
    } else if (!days.includes(shiftDay)) return false;
    if (tab === 'filled' && (!card.worker || card.shift.status === 'draft')) return false;
    if (tab === 'draft' && card.shift.status !== 'draft') return false;
    if (query.trim()) {
      const haystack = `${card.shift.position_name || ''} ${card.shift.client_name || ''} ${card.shift.location_name || ''} ${card.worker?.name || ''}`.toLowerCase();
      if (!haystack.includes(query.trim().toLowerCase())) return false;
    }
    return true;
  }), [cards, days, query, tab]);
  const visibleDays = useMemo(() => {
    if (tab !== 'open') return days;
    return Array.from(new Set(visibleCards.map((card) => dateKeyFromIso(card.shift.starts_at)))).sort();
  }, [days, tab, visibleCards]);
  const byDay = useMemo(() => {
    const map: Record<string, CardRow[]> = {};
    visibleDays.forEach((day) => { map[day] = []; });
    visibleCards.forEach((card) => { (map[dateKeyFromIso(card.shift.starts_at)] ||= []).push(card); });
    return map;
  }, [visibleDays, visibleCards]);
  const weekHours = useMemo(() => visibleCards.reduce((sum, card) => {
    const gross = Math.max(0, (new Date(card.shift.ends_at).getTime() - new Date(card.shift.starts_at).getTime()) / 3600000);
    return sum + Math.max(0, gross - Number(card.shift.break_minutes || 0) / 60);
  }, 0), [visibleCards]);

  const positionChoices = useMemo<Choice[]>(() => POSITION_ORDER.flatMap((definition) => {
    const match = positions.find((item: any) => definition.aliases.includes(normalize(item.name)));
    return match ? [{ value: String(match.id), label: definition.label }] : [];
  }), [positions]);
  const clientChoices = useMemo<Choice[]>(() => clients.map((item: any) => ({ value: String(item.id), label: item.name })), [clients]);
  const locationChoices = useMemo<Choice[]>(() => locations.filter((item: any) => !form.client || String(item.client) === form.client).map((item: any) => ({ value: String(item.id), label: item.name })), [locations, form.client]);
  const workerChoices = useMemo<Choice[]>(() => workers.map((item: any) => ({ value: String(item.id), label: item.user_detail?.name || item.user_detail?.email || item.employee_number || 'Mitarbeiter' })), [workers]);

  function openCreate(date = anchor) {
    setEditing(undefined);
    setForm(emptyForm(date));
    setTimeOpen(false);
    setExtrasOpen(false);
    setFormOpen(true);
  }

  function openEdit(card: CardRow) {
    const startDate = dateKeyFromIso(card.shift.starts_at);
    const endDate = dateKeyFromIso(card.shift.ends_at);
    const startMinute = timeMinuteFromIso(card.shift.starts_at);
    const endMinute = timeMinuteFromIso(card.shift.ends_at);
    const dayOffset = Math.round((keyDate(endDate).getTime() - keyDate(startDate).getTime()) / 86400000);
    setEditing({ shiftId: String(card.shift.id), slotId: String(card.slot.id), parentCount: Number(card.shift.required_count || 1), workerName: card.worker?.name, isOpen: card.isOpen });
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
      schedule_groups: Array.isArray(card.shift.schedule_groups) ? card.shift.schedule_groups : [],
      notes: card.shift.notes || '',
      apply_all: false,
    });
    setTimeOpen(false);
    setExtrasOpen(false);
    setFormOpen(true);
  }

  function ensureTime() {
    if (form.startMinute != null && form.endAbsolute != null) return;
    const start = initialTime();
    setForm((current) => ({ ...current, startMinute: start, endAbsolute: start + 360 }));
  }

  async function deleteEditingShift() {
    if (!editing || busy) return;
    const label = editing.workerName ? `Schicht von ${editing.workerName}` : 'OpenShift';
    if (!window.confirm(`${label} wirklich löschen?`)) return;
    setBusy(true);
    try {
      await api(`shifts/${editing.shiftId}/cards/${editing.slotId}/delete/`, { method: 'DELETE' });
      setFormOpen(false);
      setEditing(undefined);
      setToast('Schicht gelöscht.');
      window.dispatchEvent(new Event('aplus:dashboard-invalidated'));
      await load();
    } catch (error: any) {
      setToast(error.message || 'Schicht konnte nicht gelöscht werden.');
    } finally {
      setBusy(false);
    }
  }

  async function copyEditingAsOpenShift() {
    if (!editing || busy || !form.client || !form.location || !form.position || form.startMinute == null || form.endAbsolute == null) return;
    setBusy(true);
    let createdId = '';
    try {
      const payload: any = {
        client: form.client,
        location: form.location,
        position: form.position,
        starts_at: localDateTime(form.date, form.startMinute),
        ends_at: localDateTime(form.date, form.endAbsolute),
        break_minutes: automaticBreak(form.startMinute, form.endAbsolute),
        notes: form.notes || '',
        confirmation_required: form.confirmation_required,
        schedule_groups: form.schedule_groups,
        required_count: 1,
        status: 'published',
      };
      const created: any = await api('shifts/', { method: 'POST', body: JSON.stringify(payload) });
      createdId = String(created.id || '');
      await api(`shifts/${created.id}/assign/`, {
        method: 'POST',
        body: JSON.stringify({ workers: [], publish_remaining: true }),
      });
      createdId = '';
      setFormOpen(false);
      setEditing(undefined);
      setTab('open');
      setToast('Schicht wurde ohne Mitarbeiter als OpenShift kopiert.');
      window.dispatchEvent(new Event('aplus:dashboard-invalidated'));
      await load();
    } catch (error: any) {
      if (createdId) {
        try { await api(`shifts/${createdId}/`, { method: 'DELETE' }); } catch {}
      }
      setToast(error.message || 'Schicht konnte nicht kopiert werden.');
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!form.client || !form.location || !form.position || form.startMinute == null || form.endAbsolute == null) {
      setToast('Bitte Kunde, Zeit, Position und Jobstandort auswählen.');
      return;
    }
    setBusy(true);
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
      };
      if (editing) {
        payload.status = form.publish_now ? 'published' : 'draft';
        payload.apply_all = form.apply_all;
        const edited: any = await api(`shifts/${editing.shiftId}/cards/${editing.slotId}/`, { method: 'PATCH', body: JSON.stringify(payload) });
        if (editing.isOpen && form.workers.length) {
          const targetShiftId = String(edited?.shift?.id || editing.shiftId);
          await api(`shifts/${targetShiftId}/assign/`, {
            method: 'POST',
            body: JSON.stringify({ workers: [form.workers[0]], publish_remaining: form.publish_now }),
          });
          setToast('Mitarbeiter wurde der OpenShift zugewiesen.');
        } else {
          setToast(form.apply_all ? 'Änderungen auf alle Karten angewendet.' : 'Nur diese Schichtkarte wurde geändert.');
        }
      } else {
        payload.required_count = Math.max(1, Number(form.required_count || 1));
        payload.status = form.publish_now ? 'published' : 'draft';
        const created: any = await api('shifts/', { method: 'POST', body: JSON.stringify(payload) });
        await api(`shifts/${created.id}/assign/`, {
          method: 'POST',
          body: JSON.stringify({ workers: form.workers.slice(0, payload.required_count), publish_remaining: form.publish_now }),
        });
        setToast(`${payload.required_count} separate Schichtkarte${payload.required_count === 1 ? '' : 'n'} erstellt.`);
      }
      setFormOpen(false);
      window.dispatchEvent(new Event('aplus:dashboard-invalidated'));
      await load();
    } catch (error: any) {
      setToast(error.message || 'Schicht konnte nicht gespeichert werden.');
    } finally {
      setBusy(false);
    }
  }

  if (!active || !mobile || !manager) return null;
  const host = document.querySelector('.app-main') || document.body;

  return createPortal(
    <div className="wiw-schedule-mobile" data-testid="wiw-native-schedule">
      <div className="wiw-schedule-tools">
        <div className="wiw-tabs" role="tablist">
          {([['all', 'Alle'], ['open', 'OpenShifts'], ['filled', 'Besetzt'], ['draft', 'Entwürfe']] as Array<[TabKey, string]>).map(([key, label]) => <button type="button" role="tab" aria-selected={tab === key} key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>{label}</button>)}
        </div>
        <div className="wiw-search-row"><IonIcon icon={filterOutline} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filtern …" /><button type="button" onClick={() => void load()}>{busy ? '…' : '↻'}</button></div>
      </div>

      {tab !== 'open' ? <div className="wiw-week-strip">
        <button type="button" onClick={() => setAnchor(addDays(anchor, -7))}>‹</button>
        {days.map((day) => {
          const activeDay = day === anchor;
          const label = formatDayHeader(day);
          return <button type="button" key={day} className={`${activeDay ? 'active ' : ''}${day === berlinToday() ? 'today' : ''}`} onClick={() => { setAnchor(day); document.getElementById(`wiw-day-${day}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }}><small>{label.weekday.slice(0, 2)}</small><b>{keyDate(day).getUTCDate()}</b></button>;
        })}
        <button type="button" onClick={() => setAnchor(addDays(anchor, 7))}>›</button>
      </div> : null}

      <div
        className="wiw-week-scroll"
        onTouchStart={(event) => { const touch = event.touches[0]; swipe.current = { x: touch.clientX, y: touch.clientY }; }}
        onTouchEnd={(event) => {
          if (!swipe.current || !event.changedTouches.length) return;
          const touch = event.changedTouches[0];
          const dx = touch.clientX - swipe.current.x;
          const dy = touch.clientY - swipe.current.y;
          swipe.current = undefined;
          if (tab !== 'open' && Math.abs(dx) > 55 && Math.abs(dx) > Math.abs(dy) * 1.2) setAnchor(addDays(anchor, dx < 0 ? 7 : -7));
        }}
      >
        {visibleDays.map((day) => {
          const header = formatDayHeader(day);
          const dayCards = byDay[day] || [];
          return <section className="wiw-day-section" id={`wiw-day-${day}`} key={day}>
            <header><strong>{header.weekday}</strong><span>{header.date}</span><em>{dayCards.length}</em></header>
            {dayCards.map((card) => <button type="button" className="wiw-shift-card" key={card.key} onClick={() => openEdit(card)}>
              <div className="wiw-card-line primary"><b>{card.worker?.name || (card.shift.status === 'draft' ? 'Entwurf' : 'OpenShift')}</b><span>{formatTimeIso(card.shift.starts_at)}–{formatTimeIso(card.shift.ends_at)}</span></div>
              <div className="wiw-card-line secondary"><span className={card.isOpen ? 'open' : ''}>{card.shift.position_name || 'Schicht'}</span><small>{card.shift.client_name || ''}{card.shift.location_name ? ` · ${card.shift.location_name}` : ''}</small></div>
            </button>)}
            {tab !== 'open' && !dayCards.length ? <div className="wiw-day-empty">Keine Schichten</div> : null}
          </section>;
        })}
        {tab === 'open' && !visibleDays.length ? <div className="wiw-day-empty">Keine verfügbaren OpenShifts</div> : null}
      </div>

      {tab !== 'open' ? <div className="wiw-week-total"><span>Gesamtstunden</span><strong>{weekHours.toFixed(1)}</strong></div> : null}
      <button type="button" className="wiw-create-fab" aria-label="Schicht erstellen" onClick={() => openCreate(anchor)}>+</button>

      {formOpen ? <div className="wiw-shift-form-screen" data-testid="wiw-shift-form">
        <header className="wiw-form-topbar"><button type="button" onClick={() => setFormOpen(false)}>Abbrechen</button><strong>{editing ? 'Bearbeite Schicht' : 'Erstelle Schicht'}</strong><button type="button" disabled={busy || !form.client || !form.location || !form.position || form.startMinute == null || form.endAbsolute == null} onClick={() => void save()}>Sichern</button></header>
        <div className="wiw-form-scroll">
          <Row icon={calendarOutline} label={formatDateRow(form.date)} onClick={() => setDateOpen(true)} />
          <div className="wiw-time-row-wrap">
            <Row icon={timeOutline} label={form.startMinute == null || form.endAbsolute == null ? 'Wähle Zeitrahmen' : `${formatMinute(form.startMinute)} ${form.endAbsolute >= 1440 ? '~ ' : '– '}${formatMinute(form.endAbsolute)}`} muted={form.startMinute == null} onClick={() => { ensureTime(); setTimeOpen((value) => !value); }} />
            {timeOpen && form.startMinute != null && form.endAbsolute != null ? <TimeFrameWheel start={form.startMinute} end={form.endAbsolute} onChange={(start, end) => setForm((current) => ({ ...current, startMinute: start, endAbsolute: end }))} /> : null}
          </div>
          <Row icon={calendarOutline} label={form.schedule_groups.length ? form.schedule_groups.map((value) => SCHEDULE_GROUPS.find((item) => item.value === value)?.label || value).join(', ') : 'Wähle Zeitplan'} muted={!form.schedule_groups.length} onClick={() => setSheet('groups')} />

          <div className="wiw-form-separator" />
          <Row icon={briefcaseOutline} label={positionChoices.find((item) => item.value === form.position)?.label || 'Füge Position hinzu'} muted={!form.position} onClick={() => setSheet('position')} />
          <Row icon={locationOutline} label={locationChoices.find((item) => item.value === form.location)?.label || 'Jobstandort'} muted={!form.location} onClick={() => form.client ? setSheet('location') : setSheet('client')} />
          <Row icon={peopleOutline} label={clientChoices.find((item) => item.value === form.client)?.label || 'Kunde auswählen'} muted={!form.client} onClick={() => setSheet('client')} />

          <div className="wiw-form-separator" />
          <Row icon={addCircleOutline} label={`Pause automatisch · ${automaticBreak(form.startMinute, form.endAbsolute)} Min.`} green />

          <div className="wiw-form-separator" />
          <Row icon={personOutline} label="OpenShift" trailing={<Switch checked={form.publish_now} onChange={(value) => setForm((current) => ({ ...current, publish_now: value }))} />} />
          {!editing ? <Row icon={layersOutline} label={`${form.required_count} Schicht${form.required_count === 1 ? '' : 'en'}`} trailing={<div className="wiw-count-stepper"><button type="button" onClick={() => setForm((current) => ({ ...current, required_count: Math.max(current.workers.length || 1, current.required_count - 1) }))}>−</button><b>{form.required_count}</b><button type="button" onClick={() => setForm((current) => ({ ...current, required_count: current.required_count + 1 }))}>+</button></div>} /> : <Row icon={layersOutline} label="1 Schichtkarte" value={editing.workerName || 'OpenShift'} />}
          <Row icon={checkmarkOutline} label="Erfordere Übernahme-Bestätigung" trailing={<Switch checked={form.confirmation_required} onChange={(value) => setForm((current) => ({ ...current, confirmation_required: value }))} />} />
          {(!editing || editing.isOpen) ? <Row icon={peopleOutline} label={editing ? (form.workers.length ? 'Mitarbeiter ändern' : 'Mitarbeiter zuweisen') : (form.workers.length ? `${form.workers.length} Benutzer direkt zugewiesen` : 'Geeignete Benutzer anzeigen')} value={editing && form.workers.length ? workerChoices.find((choice) => choice.value === form.workers[0])?.label : undefined} muted={!form.workers.length} onClick={() => setSheet('workers')} /> : null}

          {editing && editing.parentCount > 1 && !editing.isOpen ? <div className="wiw-bulk-edit-row"><div><b>Alle Karten dieser Schicht mitändern</b><span>Wenn aus, wird nur diese Person / OpenShift-Karte geändert.</span></div><Switch checked={form.apply_all} onChange={(value) => setForm((current) => ({ ...current, apply_all: value }))} /></div> : null}

          <div className="wiw-form-separator" />
          <Row icon={colorPaletteOutline} label="Standardfarbe" />
          <Row icon={documentTextOutline} label={form.notes ? 'Notiz bearbeiten' : 'Füge Notiz hinzu'} onClick={() => setExtrasOpen((value) => !value)} />
          {extrasOpen ? <div className="wiw-extra-options"><label>Notiz<textarea value={form.notes} onChange={(event) => setForm((current) => ({ ...current, notes: event.target.value }))} placeholder="Hinweis für Mitarbeiter …" /></label></div> : null}

          {editing ? <>
            <div className="wiw-form-separator" />
            <Row icon={copyOutline} label="Schicht als OpenShift kopieren" value="Ohne Mitarbeiter" onClick={() => void copyEditingAsOpenShift()} />
            <Row icon={trashOutline} label="Schicht löschen" onClick={() => void deleteEditingShift()} />
          </> : null}
        </div>

        {dateOpen ? <div className="wiw-sheet-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setDateOpen(false); }}><section className="wiw-date-sheet"><header><b>Datum</b><button type="button" onClick={() => setDateOpen(false)}>Fertig</button></header><input type="date" value={form.date} onChange={(event) => setForm((current) => ({ ...current, date: event.target.value }))} /><div><button type="button" onClick={() => setForm((current) => ({ ...current, date: berlinToday() }))}>Heute</button><button type="button" onClick={() => setForm((current) => ({ ...current, date: addDays(berlinToday(), 1) }))}>Morgen</button></div></section></div> : null}
        {sheet === 'client' ? <ChoiceSheet title="Kunde" choices={clientChoices} selected={form.client} onClose={() => setSheet('')} onSelect={(choice) => { setForm((current) => ({ ...current, client: choice.value, location: '' })); setSheet(''); }} /> : null}
        {sheet === 'position' ? <ChoiceSheet title="Position" choices={positionChoices} selected={form.position} onClose={() => setSheet('')} onSelect={(choice) => { setForm((current) => ({ ...current, position: choice.value })); setSheet(''); }} /> : null}
        {sheet === 'location' ? <ChoiceSheet title="Jobstandort" choices={locationChoices} selected={form.location} onClose={() => setSheet('')} onSelect={(choice) => { setForm((current) => ({ ...current, location: choice.value })); setSheet(''); }} /> : null}
        {sheet === 'groups' ? <MultiChoiceSheet title="Zeitplan" choices={SCHEDULE_GROUPS} selected={form.schedule_groups} onClose={() => setSheet('')} onChange={(values) => setForm((current) => ({ ...current, schedule_groups: values }))} /> : null}
        {sheet === 'workers' ? <MultiChoiceSheet title={editing?.isOpen ? 'Mitarbeiter zuweisen' : 'Geeignete Benutzer'} choices={workerChoices} selected={form.workers} limit={editing ? 1 : form.required_count} onClose={() => setSheet('')} onChange={(values) => setForm((current) => ({ ...current, workers: values }))} /> : null}
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
    schedule_groups: [],
    notes: '',
    apply_all: false,
  };
}
