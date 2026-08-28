import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { IonIcon } from '@ionic/react';
import {
  briefcaseOutline,
  calendarOutline,
  chevronBackOutline,
  chevronForwardOutline,
  colorPaletteOutline,
  locationOutline,
  personOutline,
  timeOutline,
} from 'ionicons/icons';
import { api } from './api';
import './wiw-employee-schedule-mobile.css';

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
function dateKey(input: string) {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date(input));
  const get = (type: string) => parts.find((part) => part.type === type)?.value || '';
  return `${get('year')}-${get('month')}-${get('day')}`;
}
function time(input: string) {
  return new Intl.DateTimeFormat('de-DE', { timeZone: TZ, hour: '2-digit', minute: '2-digit' }).format(new Date(input));
}
function dayLabel(key: string) {
  return new Intl.DateTimeFormat('de-DE', { timeZone: 'UTC', weekday: 'short' }).format(keyDate(key));
}
function fullDate(input: string) {
  return new Intl.DateTimeFormat('de-DE', { timeZone: TZ, weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(input));
}
function hours(shift: any) {
  const gross = Math.max(0, (new Date(shift.ends_at).getTime() - new Date(shift.starts_at).getTime()) / 3600000);
  return Math.max(0, gross - Number(shift.break_minutes || 0) / 60);
}

function DetailRow({ icon, children }: { icon: string; children: React.ReactNode }) {
  return <div className="wiw-employee-detail-row"><IonIcon icon={icon} /><span>{children}</span></div>;
}

type Mode = 'mine' | 'open';

export default function WiwEmployeeScheduleMobile() {
  const [active, setActive] = useState(false);
  const [mobile, setMobile] = useState(() => typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches);
  const [worker, setWorker] = useState<any>();
  const [mode, setMode] = useState<Mode>('mine');
  const [mine, setMine] = useState<any[]>([]);
  const [open, setOpen] = useState<any[]>([]);
  const [anchor, setAnchor] = useState(berlinToday());
  const [selected, setSelected] = useState<any>();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const swipe = useRef<{ x: number; y: number }>();

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
    void api('auth/me/').then((me: any) => {
      if (!cancelled) setWorker(me?.role === 'worker' ? me : null);
    }).catch(() => setWorker(null));
    return () => { cancelled = true; };
  }, [active, mobile]);

  const load = async () => {
    setBusy(true);
    try {
      const [mineData, openData] = await Promise.all([
        api('shifts/mine/?ordering=starts_at'),
        api('shifts/available/?ordering=starts_at'),
      ]);
      setMine(unpack(mineData));
      setOpen(unpack(openData));
      setMessage('');
    } catch (error: any) {
      setMessage(error?.message || 'Dienstplan konnte nicht geladen werden.');
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (!active || !mobile || !worker) return;
    document.body.classList.add('wiw-employee-schedule-active');
    const requested = sessionStorage.getItem('aplus:schedule-entry-filter');
    sessionStorage.removeItem('aplus:schedule-entry-filter');
    setMode(requested === 'open' ? 'open' : 'mine');
    void load();
    return () => document.body.classList.remove('wiw-employee-schedule-active');
  }, [active, mobile, worker?.id]);

  const weekStart = monday(anchor);
  const days = useMemo(() => Array.from({ length: 7 }, (_, index) => addDays(weekStart, index)), [weekStart]);
  const rows = mode === 'mine' ? mine : open;
  const visible = useMemo(() => rows.filter((shift) => days.includes(dateKey(shift.starts_at))), [rows, days]);
  const byDay = useMemo(() => {
    const map: Record<string, any[]> = {};
    days.forEach((day) => { map[day] = []; });
    visible.forEach((shift) => { (map[dateKey(shift.starts_at)] ||= []).push(shift); });
    return map;
  }, [days, visible]);
  const weekHours = useMemo(() => visible.reduce((sum, shift) => sum + hours(shift), 0), [visible]);

  async function claim(shift: any) {
    setBusy(true);
    try {
      const result: any = await api(`shifts/${shift.id}/claim/`, { method: 'POST', body: '{}' });
      setSelected(undefined);
      if (result?.pending_approval) {
        setMessage('Schichtübernahme wurde zur Freigabe gesendet.');
      } else {
        setMode('mine');
        setMessage('Schicht übernommen. Dein Name steht jetzt im Dienstplan.');
      }
      await load();
    } catch (error: any) {
      setMessage(error?.message || 'Schicht konnte nicht übernommen werden.');
    } finally {
      setBusy(false);
    }
  }

  async function requestRelease(shift: any) {
    setBusy(true);
    try {
      await api(`employee/shifts/${shift.id}/release-request/`, { method: 'POST', body: '{}' });
      setMessage('Freigabe angefragt. Die Schicht bleibt dir zugewiesen, bis die Administration zustimmt.');
      await load();
      setSelected((current: any) => current ? { ...current, my_release_request: { status: 'pending' } } : current);
    } catch (error: any) {
      setMessage(error?.message || 'Freigabe konnte nicht angefragt werden.');
    } finally {
      setBusy(false);
    }
  }

  if (!active || !mobile || !worker) return null;
  const host = document.querySelector('.app-main') || document.body;

  const screen = selected ? (
    <div className="wiw-employee-shift-detail" data-testid="wiw-employee-shift-detail">
      <header className="wiw-employee-detail-topbar">
        <button type="button" aria-label="Zurück" onClick={() => setSelected(undefined)}><IonIcon icon={chevronBackOutline} /></button>
        <strong>Schichtdetails</strong>
        <span />
      </header>
      <div className="wiw-employee-detail-list">
        <DetailRow icon={calendarOutline}>{fullDate(selected.starts_at)}</DetailRow>
        <DetailRow icon={timeOutline}>{time(selected.starts_at)} – {time(selected.ends_at)}</DetailRow>
        <DetailRow icon={briefcaseOutline}>{selected.client_name || 'A+'}</DetailRow>
        <DetailRow icon={briefcaseOutline}>{selected.position_name || 'Einsatz'}</DetailRow>
        <DetailRow icon={locationOutline}>{selected.location_name || 'Einsatzort'}</DetailRow>
        <DetailRow icon={personOutline}>{mode === 'mine' ? (worker.name || worker.email || 'Mitarbeiter') : 'OpenShift'}</DetailRow>
        <DetailRow icon={colorPaletteOutline}>Standardfarbe</DetailRow>
      </div>
      <div className="wiw-employee-detail-actions">
        {mode === 'open' ? (
          <button type="button" className="primary" disabled={busy} onClick={() => void claim(selected)}>{busy ? 'Bitte warten …' : 'Schicht übernehmen'}</button>
        ) : selected.my_release_request?.status === 'pending' ? (
          <button type="button" disabled>Freigabe angefragt · wartet auf Administration</button>
        ) : (
          <button type="button" className="release" disabled={busy} onClick={() => void requestRelease(selected)}>{busy ? 'Bitte warten …' : 'Schichtfreigabe anfragen'}</button>
        )}
      </div>
      {message && <div className="wiw-employee-message">{message}</div>}
    </div>
  ) : (
    <div className="wiw-employee-schedule" data-testid="wiw-employee-schedule">
      <div className="wiw-employee-tabs">
        <button type="button" className={mode === 'mine' ? 'active' : ''} onClick={() => setMode('mine')}>Meine Schichten</button>
        <button type="button" className={mode === 'open' ? 'active' : ''} onClick={() => setMode('open')}>OpenShifts <b>{open.length}</b></button>
      </div>

      <div className="wiw-employee-week-strip">
        <button type="button" className="nav" onClick={() => setAnchor(addDays(anchor, -7))}>‹</button>
        {days.map((day) => <button type="button" key={day} className={`${day === anchor ? 'active ' : ''}${day === berlinToday() ? 'today' : ''}`} onClick={() => setAnchor(day)}><small>{dayLabel(day).slice(0, 2)}</small><b>{keyDate(day).getUTCDate()}</b></button>)}
        <button type="button" className="nav" onClick={() => setAnchor(addDays(anchor, 7))}>›</button>
      </div>

      <div className="wiw-employee-week-scroll"
        onTouchStart={(event) => { const touch = event.touches[0]; swipe.current = { x: touch.clientX, y: touch.clientY }; }}
        onTouchEnd={(event) => {
          if (!swipe.current || !event.changedTouches.length) return;
          const touch = event.changedTouches[0];
          const dx = touch.clientX - swipe.current.x;
          const dy = touch.clientY - swipe.current.y;
          swipe.current = undefined;
          if (Math.abs(dx) > 55 && Math.abs(dx) > Math.abs(dy) * 1.2) setAnchor(addDays(anchor, dx < 0 ? 7 : -7));
        }}>
        {days.map((day) => <section className="wiw-employee-day" key={day}>
          <header><strong>{dayLabel(day)}</strong><span>{new Intl.DateTimeFormat('de-DE', { timeZone: 'UTC', day: '2-digit', month: '2-digit' }).format(keyDate(day))}</span><em>{(byDay[day] || []).length}</em></header>
          {(byDay[day] || []).map((shift) => <button type="button" className="wiw-employee-shift-card" key={shift.id} onClick={() => setSelected(shift)}>
            <div><b>{shift.position_name || 'Einsatz'}</b><span>{time(shift.starts_at)}–{time(shift.ends_at)}</span></div>
            <p>{mode === 'mine' ? (worker.name || worker.email || 'Mitarbeiter') : 'OpenShift'}</p>
            <small>{shift.client_name || 'A+'} · {shift.location_name || 'Einsatzort'}</small>
            {shift.my_release_request?.status === 'pending' && <i>Freigabe angefragt</i>}
            <IonIcon icon={chevronForwardOutline} />
          </button>)}
          {!(byDay[day] || []).length && <div className="wiw-employee-day-empty">Keine Schichten</div>}
        </section>)}
      </div>

      <div className="wiw-employee-week-total"><span>Gesamtstunden</span><strong>{weekHours.toFixed(1)}</strong></div>
      {message && <div className="wiw-employee-message sticky">{message}</div>}
    </div>
  );

  return createPortal(screen, host);
}
