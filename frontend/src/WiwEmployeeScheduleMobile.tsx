import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { IonIcon } from '@ionic/react';
import {
  briefcaseOutline,
  calendarOutline,
  chevronBackOutline,
  colorPaletteOutline,
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
const clientKey = (shift: any) => String(shift?.client || shift?.client_name || 'ohne-kunde');

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
function formatDayHeader(key: string) {
  const weekday = dayLabel(key);
  const date = new Intl.DateTimeFormat('de-DE', { timeZone: 'UTC', day: '2-digit', month: '2-digit', year: 'numeric' }).format(keyDate(key));
  return { weekday, date };
}
function fullDate(input: string) {
  return new Intl.DateTimeFormat('de-DE', { timeZone: TZ, weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(input));
}
function hours(shift: any) {
  const gross = Math.max(0, (new Date(shift.ends_at).getTime() - new Date(shift.starts_at).getTime()) / 3600000);
  return Math.max(0, gross - Number(shift.break_minutes || 0) / 60);
}
function shortPersonName(value: string) {
  const parts = String(value || '').trim().split(/\s+/).filter(Boolean);
  if (parts.length <= 1) return parts[0] || '';
  return parts[0] + ' ' + parts.slice(1).map((part) => part.charAt(0) + '.').join(' ');
}
function assignedNames(shift: any) {
  const names = (shift?.assigned_workers || [])
    .map((assigned: any) => shortPersonName(assigned?.name || ''))
    .filter(Boolean);
  return names.join(', ');
}
function isOwnShift(shift: any) {
  return Boolean((shift?.assigned_workers || []).some((assigned: any) => assigned?.is_me));
}
function firstAssignedWorker(shift: any) {
  const assigned = Array.isArray(shift?.assigned_workers) ? shift.assigned_workers[0] : undefined;
  if (!assigned) return undefined;
  return {
    ...assigned,
    avatar: assigned.avatar || assigned.photo_url || assigned.photo || assigned.image || undefined,
  };
}
function workerInitials(value?: string) {
  const parts = String(value || '').trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return 'MA';
  const first = parts[0]?.[0] || '';
  const last = parts.length > 1 ? parts[parts.length - 1]?.[0] || '' : '';
  return `${first}${last}`.toLocaleUpperCase('de-DE') || 'MA';
}
function WorkerAvatar({ worker }: { worker?: any }) {
  if (!worker) return null;
  return <span className="wiw-worker-avatar-shell" aria-hidden="true">
    <span className="wiw-worker-avatar wiw-worker-avatar-fallback">{workerInitials(worker.name)}</span>
    {worker.avatar ? <img className="wiw-worker-avatar wiw-worker-avatar-image" src={worker.avatar} alt="" onError={(event) => event.currentTarget.remove()} /> : null}
  </span>;
}
function positionShortLabel(name?: string) {
  const key = normalize(String(name || ''));
  if (key.includes('serviceleitung')) return 'SL';
  if (key.includes('servicekraft') || key.includes('servicekrat')) return 'SK';
  if (key.includes('frontoffice') || key.includes('rezeption') || key.includes('reception')) return 'FO';
  if (key.includes('housekeeping') || key.includes('houskeeping') || key.includes('zimmer')) return 'HK';
  if (key.includes('bar')) return 'Bar';
  return String(name || 'Schicht');
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

function DetailRow({ icon, children }: { icon: string; children: React.ReactNode }) {
  return <div className="wiw-employee-detail-row"><IonIcon icon={icon} /><span>{children}</span></div>;
}

type Mode = 'mine' | 'open';

export default function WiwEmployeeScheduleMobile() {
  const [active, setActive] = useState(false);
  const [mobile, setMobile] = useState(() => typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches);
  const [worker, setWorker] = useState<any>();
  const [mode, setMode] = useState<Mode>('mine');
  const [serviceSchedule, setServiceSchedule] = useState(false);
  const [mine, setMine] = useState<any[]>([]);
  const [open, setOpen] = useState<any[]>([]);
  const [anchor, setAnchor] = useState(berlinToday());
  const [selected, setSelected] = useState<any>();
  const [releaseTarget, setReleaseTarget] = useState<any>();
  const [releaseCandidates, setReleaseCandidates] = useState<any[]>([]);
  const [requestedWorkerId, setRequestedWorkerId] = useState('');
  const [releaseLoading, setReleaseLoading] = useState(false);
  const [releaseError, setReleaseError] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const swipe = useRef<{ x: number; y: number } | undefined>(undefined);

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

  const load = async (): Promise<{ mine: any[]; open: any[] }> => {
    setBusy(true);
    try {
      const [mineData, openData] = await Promise.all([
        api('employee/schedule/?ordering=starts_at'),
        api('shifts/available/?ordering=starts_at'),
      ]);
      const nextMine = Array.isArray(mineData?.shifts) ? mineData.shifts : unpack(mineData);
      const nextOpen = unpack(openData);
      setServiceSchedule(Boolean(mineData?.service_schedule));
      setMine(nextMine);
      setOpen(nextOpen);
      setMessage('');
      return { mine: nextMine, open: nextOpen };
    } catch (error: any) {
      setMessage(error?.message || 'Dienstplan konnte nicht geladen werden.');
      return { mine: [], open: [] };
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (!active || !mobile || !worker) return;
    document.body.classList.add('wiw-employee-schedule-active');

    const legacyHooks = Array.from(document.querySelectorAll<HTMLElement>(
      '.sv2 [data-testid="phase8-week-strip"], .sv2 [data-testid="schedule-day-view"], .sv2 [data-testid="phase8-week-total"]',
    ));
    const legacySegments = Array.from(document.querySelectorAll<HTMLElement>('.sv2 ion-segment-button[value="mine"]'));
    legacyHooks.forEach((element) => element.removeAttribute('data-testid'));
    legacySegments.forEach((element) => element.removeAttribute('value'));

    const requested = sessionStorage.getItem('aplus:schedule-entry-filter');
    sessionStorage.removeItem('aplus:schedule-entry-filter');
    setMode(requested === 'open' ? 'open' : 'mine');
    void load();

    return () => {
      document.body.classList.remove('wiw-employee-schedule-active');
      legacyHooks[0]?.setAttribute('data-testid', 'phase8-week-strip');
      legacyHooks[1]?.setAttribute('data-testid', 'schedule-day-view');
      legacyHooks[2]?.setAttribute('data-testid', 'phase8-week-total');
      legacySegments.forEach((element) => element.setAttribute('value', 'mine'));
    };
  }, [active, mobile, worker?.id]);

  const weekStart = monday(anchor);
  const days = useMemo(() => Array.from({ length: 7 }, (_, index) => addDays(weekStart, index)), [weekStart]);
  const rows = mode === 'mine' ? mine : open;
  const visible = useMemo(() => {
    if (mode === 'open') {
      const now = Date.now();
      return rows
        .filter((shift) => !shift?.ends_at || new Date(shift.ends_at).getTime() >= now)
        .sort((left, right) => new Date(left.starts_at).getTime() - new Date(right.starts_at).getTime());
    }
    return rows.filter((shift) => days.includes(dateKey(shift.starts_at)));
  }, [rows, days, mode]);
  const visibleDays = useMemo(() => mode === 'open'
    ? Array.from(new Set(visible.map((shift) => dateKey(shift.starts_at)))).sort()
    : days,
  [mode, visible, days]);
  const byDay = useMemo(() => {
    const map: Record<string, any[]> = {};
    visibleDays.forEach((day) => { map[day] = []; });
    visible.forEach((shift) => { (map[dateKey(shift.starts_at)] ||= []).push(shift); });
    Object.values(map).forEach((items) => items.sort((left, right) => {
      const clientOrder = String(left.client_name || '').localeCompare(String(right.client_name || ''), 'de');
      if (clientOrder) return clientOrder;
      return new Date(left.starts_at).getTime() - new Date(right.starts_at).getTime();
    }));
    return map;
  }, [visibleDays, visible]);
  const weekHours = useMemo(
    () => visible.filter(isOwnShift).reduce((sum, shift) => sum + hours(shift), 0),
    [visible],
  );

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

  async function openReleaseChooser(shift: any) {
    setReleaseTarget(shift);
    setReleaseCandidates([]);
    setRequestedWorkerId('');
    setReleaseError('');
    setReleaseLoading(true);
    try {
      const result: any = await api(`employee/shifts/${shift.id}/release-candidates/`);
      setReleaseCandidates(result?.candidates || []);
    } catch (error: any) {
      setReleaseError(error?.message || 'Mitarbeiter konnten nicht geladen werden.');
    } finally {
      setReleaseLoading(false);
    }
  }

  function closeReleaseChooser() {
    if (busy) return;
    setReleaseTarget(undefined);
    setReleaseCandidates([]);
    setRequestedWorkerId('');
    setReleaseError('');
  }

  async function requestRelease(shift: any) {
    setBusy(true);
    setReleaseError('');
    try {
      const result: any = await api(`employee/shifts/${shift.id}/release-request/`, {
        method: 'POST',
        body: JSON.stringify({ requested_worker: requestedWorkerId || null }),
      });
      const requestedName = result?.requested_worker;
      setMessage(requestedName
        ? `Freigabe angefragt. Gewünschte Übernahme: ${requestedName}. Die Schicht bleibt dir zugewiesen, bis die Administration zustimmt.`
        : 'Freigabe angefragt. Die Schicht bleibt dir zugewiesen, bis die Administration zustimmt.');
      setReleaseTarget(undefined);
      setReleaseCandidates([]);
      setRequestedWorkerId('');
      await load();
      setSelected((current: any) => current ? {
        ...current,
        my_release_request: {
          status: 'pending',
          requested_worker: requestedName || null,
        },
      } : current);
    } catch (error: any) {
      setReleaseError(error?.message || 'Freigabe konnte nicht angefragt werden.');
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
        <DetailRow icon={personOutline}>{mode === 'mine' ? (assignedNames(selected) || worker.name || worker.email || 'Mitarbeiter') : 'OpenShift'}</DetailRow>
        <DetailRow icon={colorPaletteOutline}>Standardfarbe</DetailRow>
      </div>
      <div className="wiw-employee-detail-actions">
        {mode === 'open' ? (
          <button type="button" className="primary" disabled={busy} onClick={() => void claim(selected)}>{busy ? 'Bitte warten …' : 'Schicht übernehmen'}</button>
        ) : !isOwnShift(selected) ? (
          <button type="button" disabled>Nur sichtbar · Service Zeitplan</button>
        ) : selected.my_release_request?.status === 'pending' ? (
          <button type="button" disabled>
            {selected.my_release_request?.requested_worker
              ? `Freigabe angefragt · Wunsch: ${selected.my_release_request.requested_worker}`
              : 'Freigabe angefragt · wartet auf Administration'}
          </button>
        ) : (
          <button type="button" className="release" disabled={busy} onClick={() => void openReleaseChooser(selected)}>{busy ? 'Bitte warten …' : 'Freigeben'}</button>
        )}
      </div>
      {message && <div className="wiw-employee-message">{message}</div>}
    </div>
  ) : (
    <div className={`wiw-employee-schedule wiw-schedule-mobile wiw-employee-admin-parity ${mode === 'open' ? 'is-open-list' : ''}`} data-testid="wiw-employee-schedule">
      <div className="wiw-schedule-tools">
        <div className="wiw-tabs" role="tablist">
          <button type="button" role="tab" aria-selected={mode === 'mine'} className={mode === 'mine' ? 'active' : ''} onClick={() => setMode('mine')}>{serviceSchedule ? 'Service Zeitplan' : 'Meine Schichten'}</button>
          <button type="button" role="tab" aria-selected={mode === 'open'} className={mode === 'open' ? 'active' : ''} onClick={() => setMode('open')}>OpenShifts</button>
        </div>
      </div>

      {mode !== 'open' ? <div className="wiw-week-strip" data-testid="phase8-week-strip" style={{ top: 42 }}>
        <button type="button" aria-label="Vorherige Woche" onClick={() => setAnchor(addDays(anchor, -7))}>‹</button>
        {days.map((day) => <button type="button" key={day} className={`${day === anchor ? 'active ' : ''}${day === berlinToday() ? 'today' : ''}`} onClick={() => setAnchor(day)}><small>{dayLabel(day).slice(0, 2)}</small><b>{keyDate(day).getUTCDate()}</b></button>)}
        <button type="button" aria-label="Nächste Woche" onClick={() => setAnchor(addDays(anchor, 7))}>›</button>
      </div> : null}

      <div
        className="wiw-week-scroll"
        data-testid="schedule-day-view"
        style={mode === 'mine' ? { paddingBottom: 'calc(124px + env(safe-area-inset-bottom))' } : undefined}
        onTouchStart={(event) => {
          if (mode === 'open') return;
          const touch = event.touches[0];
          swipe.current = { x: touch.clientX, y: touch.clientY };
        }}
        onTouchEnd={(event) => {
          if (mode === 'open' || !swipe.current || !event.changedTouches.length) return;
          const touch = event.changedTouches[0];
          const dx = touch.clientX - swipe.current.x;
          const dy = touch.clientY - swipe.current.y;
          swipe.current = undefined;
          if (Math.abs(dx) > 55 && Math.abs(dx) > Math.abs(dy) * 1.2) setAnchor(addDays(anchor, dx < 0 ? 7 : -7));
        }}
      >
        {visibleDays.map((day) => {
          const header = formatDayHeader(day);
          const dayShifts = byDay[day] || [];
          return <section className="wiw-day-section wiw-day-visual" id={`wiw-employee-day-${day}`} key={day}>
            <header><span className="wiw-day-header-spacer"/><div className="wiw-day-heading"><strong>{header.weekday}</strong><span>{header.date}</span></div><em>{dayShifts.length}</em></header>
            {dayShifts.map((shift, index) => {
              const assigned = firstAssignedWorker(shift);
              const workerName = assigned?.name ? shortPersonName(assigned.name) : assignedNames(shift);
              const openShift = mode === 'open';
              return <React.Fragment key={String(shift.id)}>
                {index > 0 && clientKey(dayShifts[index - 1]) !== clientKey(shift) ? <div className="wiw-client-divider" aria-hidden="true" /> : null}
                <button type="button" className={`wiw-shift-card ${openShift ? 'is-open' : 'is-filled'}${!openShift && !isOwnShift(shift) ? ' peer-shift' : ''}`} style={shiftCardStyle(shift)} onClick={() => setSelected(shift)}>
                  <div className="wiw-card-line primary">
                    <span className="wiw-card-person"><WorkerAvatar worker={openShift ? undefined : assigned} /><b>{openShift ? 'OpenShift' : (workerName || worker.name || worker.email || 'Mitarbeiter')}{openShift ? <span className="wiw-open-alert">!</span> : null}</b></span>
                    <span>{time(shift.starts_at)}–{time(shift.ends_at)}</span>
                  </div>
                  <div className="wiw-card-line secondary"><span className={openShift ? 'open' : ''}>{positionShortLabel(shift.position_name)}</span><small>{shift.location_name || 'Einsatzort'}</small></div>
                </button>
              </React.Fragment>;
            })}
            {mode !== 'open' && !dayShifts.length ? <div className="wiw-day-empty">Keine Schichten</div> : null}
          </section>;
        })}
        {mode === 'open' && !visibleDays.length ? <div className="wiw-day-empty">{busy ? 'OpenShifts werden geladen …' : 'Keine verfügbaren OpenShifts'}</div> : null}
      </div>

      {mode !== 'open' ? <div className="wiw-week-total" data-testid="phase8-week-total" style={{ position: 'fixed', left: 0, right: 0, bottom: 'calc(58px + env(safe-area-inset-bottom))', zIndex: 120, height: 54, minHeight: 54, padding: '0 18px', margin: 0 }}><span>{serviceSchedule ? 'Eigene Gesamtstunden' : 'Gesamtstunden'}</span><strong>{weekHours.toFixed(1)}</strong></div> : null}
      {message && <div className="wiw-employee-message sticky">{message}</div>}
    </div>
  );

  return <>
    {createPortal(screen, host)}
    {releaseTarget ? createPortal(<div className="wiw-release-backdrop" role="presentation" onClick={closeReleaseChooser}>
      <section className="wiw-release-sheet" role="dialog" aria-modal="true" aria-labelledby="wiw-release-title" onClick={(event) => event.stopPropagation()}>
        <div className="wiw-release-handle" />
        <header>
          <div>
            <small>FREIGABE</small>
            <h2 id="wiw-release-title">Schicht freigeben</h2>
          </div>
          <button type="button" aria-label="Schließen" disabled={busy} onClick={closeReleaseChooser}>×</button>
        </header>
        <div className="wiw-release-shift-summary">
          <strong>{releaseTarget.position_name || 'Einsatz'}</strong>
          <span>{fullDate(releaseTarget.starts_at)} · {time(releaseTarget.starts_at)}–{time(releaseTarget.ends_at)}</span>
          <small>{releaseTarget.client_name || 'A+'} · {releaseTarget.location_name || 'Einsatzort'}</small>
        </div>
        <div className="wiw-release-copy">
          <strong>Wer soll die Schicht übernehmen?</strong>
          <p>Du kannst einen anderen verfügbaren Mitarbeiter vorschlagen. Die Schicht bleibt bis zur Genehmigung durch die Administration weiterhin dir zugewiesen.</p>
        </div>
        {releaseLoading ? <div className="wiw-release-loading">Verfügbare Mitarbeiter werden geprüft …</div> : <div className="wiw-release-candidates">
          <button type="button" className={!requestedWorkerId ? 'selected' : ''} onClick={() => setRequestedWorkerId('')}>
            <span><b>Ohne Wunsch</b><small>Nach Genehmigung als OpenShift freigeben</small></span>
            <i>{!requestedWorkerId ? '✓' : ''}</i>
          </button>
          {releaseCandidates.map((candidate) => <button type="button" key={candidate.id} className={requestedWorkerId === candidate.id ? 'selected' : ''} onClick={() => setRequestedWorkerId(candidate.id)}>
            <span><b>{candidate.name}</b><small>{candidate.employee_number || 'Mitarbeiter'}</small></span>
            <i>{requestedWorkerId === candidate.id ? '✓' : ''}</i>
          </button>)}
          {!releaseCandidates.length && !releaseLoading && <div className="wiw-release-no-candidates">Für diese Schicht ist aktuell kein anderer Mitarbeiter nach den Planungsregeln verfügbar.</div>}
        </div>}
        <small className="wiw-release-rule-note">Es werden nur aktive Mitarbeiter angezeigt, die diese Schicht aktuell ohne Überschneidung oder Planungsregel-Verstoß übernehmen könnten. Bei der Genehmigung wird das erneut geprüft.</small>
        {releaseError && <div className="wiw-release-error">{releaseError}</div>}
        <div className="wiw-release-actions">
          <button type="button" disabled={busy} onClick={closeReleaseChooser}>Abbrechen</button>
          <button type="button" className="primary" disabled={busy || releaseLoading} onClick={() => void requestRelease(releaseTarget)}>{busy ? 'Wird gesendet …' : 'Freigabe anfragen'}</button>
        </div>
      </section>
    </div>, document.body) : null}
  </>;
}
