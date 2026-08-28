import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { IonIcon } from '@ionic/react';
import { calendarOutline, optionsOutline } from 'ionicons/icons';
import './schedule-mobile-enhancer.css';

type FilterKey = 'all' | 'service' | 'hotel' | 'housekeeping';
type PositionChoice = { value: any; label: string };

const FILTERS: Array<[FilterKey, string]> = [
  ['all', 'Alle'],
  ['service', 'Service'],
  ['hotel', 'Hotel'],
  ['housekeeping', 'Housekeeping'],
];

const POSITION_ORDER = [
  { label: 'Servicekraft', aliases: ['servicekraft', 'servicekrat'] },
  { label: 'Serviceleitung', aliases: ['serviceleitung'] },
  { label: 'Front-Office', aliases: ['frontoffice'] },
  { label: 'Housekeeping', aliases: ['housekeeping', 'houskeeping'] },
  { label: 'Bar-Support', aliases: ['barsupport'] },
];

const GERMAN_MONTHS: Record<string, number> = {
  januar: 1,
  februar: 2,
  märz: 3,
  april: 4,
  mai: 5,
  juni: 6,
  juli: 7,
  august: 8,
  september: 9,
  oktober: 10,
  november: 11,
  dezember: 12,
};

const pad = (value: number) => String(value).padStart(2, '0');
const waitForUi = () => new Promise<void>((resolve) => window.setTimeout(resolve, 45));
const normalizePosition = (value: string) => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('de-DE').replace(/[^a-z0-9]/g, '');

function berlinToday() {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Europe/Berlin',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.filter((part) => part.type !== 'literal').map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function dateFromKey(key: string) {
  const [year, month, day] = key.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1, day, 12));
}

function keyFromDate(date: Date) {
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}`;
}

function mondayKey(key: string) {
  const date = dateFromKey(key);
  const weekday = date.getUTCDay();
  date.setUTCDate(date.getUTCDate() + (weekday === 0 ? -6 : 1 - weekday));
  return keyFromDate(date);
}

function addWallClockHours(input: string, hours: number) {
  const match = String(input || '').match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
  if (!match) return '';
  const value = Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]), Number(match[4]), Number(match[5]));
  const next = new Date(value + hours * 3600000);
  return `${next.getUTCFullYear()}-${pad(next.getUTCMonth() + 1)}-${pad(next.getUTCDate())}T${pad(next.getUTCHours())}:${pad(next.getUTCMinutes())}`;
}

function readCurrentDate() {
  const weekActive = document.querySelector<HTMLButtonElement>('.sv2-wiw-week-strip button.active:not(.nav)');
  const weekButtons = dayButtons();
  const activeIndex = weekButtons.indexOf(weekActive as HTMLButtonElement);
  if (activeIndex >= 0) {
    const currentHeader = document.querySelectorAll<HTMLElement>('.sv2-week-day > header')[activeIndex];
    const label = currentHeader?.textContent?.trim() || '';
    const match = label.match(/(\d{1,2})\.(\d{1,2})/);
    if (match) {
      const current = dateFromKey(berlinToday());
      const year = current.getUTCFullYear();
      return `${year}-${pad(Number(match[2]))}-${pad(Number(match[1]))}`;
    }
  }
  const label = document.querySelector<HTMLElement>('.sv2-single-day > header h2')?.textContent?.trim() || '';
  const match = label.match(/(\d{1,2})\.\s+([A-Za-zÄÖÜäöüß]+)\s+(\d{4})/);
  if (!match) return berlinToday();
  const month = GERMAN_MONTHS[match[2].normalize('NFC').toLocaleLowerCase('de-DE')];
  if (!month) return berlinToday();
  return `${match[3]}-${pad(month)}-${pad(Number(match[1]))}`;
}

function dayButtons() {
  return Array.from(document.querySelectorAll<HTMLButtonElement>('.sv2-wiw-week-strip button:not(.nav)'));
}

function forceWeekView() {
  document.querySelector<HTMLButtonElement>('[data-testid="schedule-view-week"]')?.click();
}

async function moveToDate(targetKey: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(targetKey)) return;
  const currentKey = readCurrentDate();
  const currentMonday = dateFromKey(mondayKey(currentKey));
  const targetMonday = dateFromKey(mondayKey(targetKey));
  const weekDiff = Math.round((targetMonday.getTime() - currentMonday.getTime()) / (7 * 86400000));
  const steps = Math.min(Math.abs(weekDiff), 520);

  for (let index = 0; index < steps; index += 1) {
    const nav = Array.from(document.querySelectorAll<HTMLButtonElement>('.sv2-wiw-week-strip button.nav'));
    const button = weekDiff < 0 ? nav[0] : nav[nav.length - 1];
    if (!button) break;
    button.click();
    await waitForUi();
  }

  const target = dateFromKey(targetKey);
  const weekday = target.getUTCDay();
  const mondayIndex = weekday === 0 ? 6 : weekday - 1;
  const buttons = dayButtons();
  buttons[mondayIndex]?.click();
  await waitForUi();
  forceWeekView();
  await waitForUi();
  document.querySelectorAll<HTMLElement>('.sv2-week-day')[mondayIndex]?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function moveOneWeek(direction: -1 | 1) {
  const nav = Array.from(document.querySelectorAll<HTMLButtonElement>('.sv2-wiw-week-strip button.nav'));
  const button = direction < 0 ? nav[0] : nav[nav.length - 1];
  if (!button) return;
  button.click();
  await waitForUi();
  forceWeekView();
}

function readFilter(): FilterKey {
  const active = document.querySelector<HTMLButtonElement>('.sv2-service-filter button[aria-pressed="true"]');
  const testId = active?.dataset.testid || '';
  const key = testId.replace('schedule-filter-', '') as FilterKey;
  return FILTERS.some(([candidate]) => candidate === key) ? key : 'all';
}

function emitIonValue(element: HTMLElement | null, next: string) {
  if (!element || !next) return;
  try { (element as any).value = next; } catch { /* best effort */ }
  element.setAttribute('value', next);
  element.dispatchEvent(new CustomEvent('ionInput', { detail: { value: next }, bubbles: true, composed: true }));
  element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: next }, bubbles: true, composed: true }));
}

function positionChoices(select: HTMLElement): PositionChoice[] {
  const options = Array.from(select.querySelectorAll<HTMLElement>('ion-select-option'));
  return POSITION_ORDER.flatMap((definition) => {
    const match = options.find((option) => definition.aliases.includes(normalizePosition(option.textContent || '')));
    if (!match) return [];
    const value = (match as any).value ?? match.getAttribute('value');
    return value == null ? [] : [{ value, label: definition.label }];
  });
}

export default function ScheduleMobileEnhancer() {
  const [active, setActive] = useState(false);
  const [mobile, setMobile] = useState(() => typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches);
  const [calendarOpen, setCalendarOpen] = useState(false);
  const [filterOpen, setFilterOpen] = useState(false);
  const [positionOpen, setPositionOpen] = useState(false);
  const [positionOptions, setPositionOptions] = useState<PositionChoice[]>([]);
  const [dateValue, setDateValue] = useState(berlinToday());
  const [filterKey, setFilterKey] = useState<FilterKey>('all');
  const initializedRef = useRef(false);
  const positionTargetRef = useRef<HTMLElement | null>(null);
  const lastStartValueRef = useRef<string | null>(null);

  useEffect(() => {
    const root = document.getElementById('root');
    const sync = () => setActive(Boolean(document.querySelector('.mobile-first-app-shell-v1[data-view="schedule"]')));
    sync();
    const observer = new MutationObserver(sync);
    if (root) observer.observe(root, { subtree: true, childList: true, attributes: true, attributeFilter: ['data-view'] });
    window.addEventListener('popstate', sync);
    return () => {
      observer.disconnect();
      window.removeEventListener('popstate', sync);
    };
  }, []);

  useEffect(() => {
    const query = window.matchMedia('(max-width: 900px)');
    const sync = () => setMobile(query.matches);
    sync();
    query.addEventListener?.('change', sync);
    return () => query.removeEventListener?.('change', sync);
  }, []);

  useEffect(() => {
    const enabled = active && mobile;
    document.body.classList.toggle('schedule-mobile-enhanced', enabled);
    if (!enabled) {
      initializedRef.current = false;
      lastStartValueRef.current = null;
      setCalendarOpen(false);
      setFilterOpen(false);
      setPositionOpen(false);
      positionTargetRef.current = null;
    }
    return () => document.body.classList.remove('schedule-mobile-enhanced');
  }, [active, mobile]);

  useEffect(() => {
    if (!active || !mobile || initializedRef.current) return;
    const timer = window.setTimeout(() => {
      if (initializedRef.current) return;
      document.querySelector<HTMLElement>('.sv2 > ion-segment ion-segment-button[value="all"]')?.click();
      document.querySelector<HTMLButtonElement>('[data-testid="schedule-filter-all"]')?.click();
      forceWeekView();
      setFilterKey('all');
      initializedRef.current = true;
    }, 90);
    return () => window.clearTimeout(timer);
  }, [active, mobile]);

  useEffect(() => {
    if (!active || !mobile) return;

    const enhanceControls = () => {
      document.querySelectorAll<HTMLElement>('.sv2-modal ion-select:not([multiple])').forEach((select) => {
        try { (select as any).interface = 'popover'; } catch { /* best effort */ }
        select.setAttribute('interface', 'popover');
      });
      document.querySelectorAll<HTMLElement>('.sv2-modal ion-input[type="datetime-local"]').forEach((input) => {
        input.dataset.aplusPickerKind = 'datetime-local';
        input.setAttribute('readonly', '');
        input.setAttribute('inputmode', 'none');
        input.setAttribute('step', '900');
        try { (input as any).readonly = true; } catch { /* best effort */ }
        const shadowInput = input.shadowRoot?.querySelector('input') as HTMLInputElement | null;
        if (shadowInput) {
          shadowInput.readOnly = true;
          shadowInput.inputMode = 'none';
        }
      });
    };

    enhanceControls();
    const observer = new MutationObserver(enhanceControls);
    observer.observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['type', 'label'] });

    const onPositionClick = (event: Event) => {
      const select = event.composedPath().find((node) => node instanceof HTMLElement && node.matches('ion-select[label^="Position"]')) as HTMLElement | undefined;
      if (!select || !select.closest('.sv2-modal')) return;
      const choices = positionChoices(select);
      if (!choices.length) return;
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation?.();
      positionTargetRef.current = select;
      setPositionOptions(choices);
      setPositionOpen(true);
      setCalendarOpen(false);
      setFilterOpen(false);
    };
    document.addEventListener('click', onPositionClick, true);

    const interval = window.setInterval(() => {
      const start = document.querySelector<HTMLElement>('.sv2-modal ion-input[aria-label^="Beginn"]');
      if (!start) {
        lastStartValueRef.current = null;
        return;
      }
      const current = String((start as any).value || start.getAttribute('value') || '');
      if (lastStartValueRef.current === null) {
        lastStartValueRef.current = current;
        return;
      }
      if (!current || current === lastStartValueRef.current) return;
      lastStartValueRef.current = current;
      const nextEnd = addWallClockHours(current, 6);
      const end = document.querySelector<HTMLElement>('.sv2-modal ion-input[aria-label^="Ende"]');
      emitIonValue(end, nextEnd);
    }, 120);

    return () => {
      observer.disconnect();
      document.removeEventListener('click', onPositionClick, true);
      window.clearInterval(interval);
    };
  }, [active, mobile]);

  useEffect(() => {
    if (!active || !mobile) return;
    let bound: HTMLElement | null = null;
    let startX: number | null = null;
    let startY: number | null = null;

    const onStart = (event: TouchEvent) => {
      if (event.touches.length !== 1) return;
      const target = event.target as HTMLElement | null;
      if (target?.closest('button,a,input,textarea,select,ion-button,ion-input,ion-select')) return;
      startX = event.touches[0].clientX;
      startY = event.touches[0].clientY;
    };

    const onEnd = (event: TouchEvent) => {
      if (startX == null || startY == null || !event.changedTouches.length) return;
      const deltaX = event.changedTouches[0].clientX - startX;
      const deltaY = event.changedTouches[0].clientY - startY;
      startX = null;
      startY = null;
      if (Math.abs(deltaX) < 55 || Math.abs(deltaX) < Math.abs(deltaY) * 1.2) return;
      event.preventDefault();
      event.stopPropagation();
      void moveOneWeek(deltaX < 0 ? 1 : -1);
    };

    const bind = () => {
      const next = document.querySelector<HTMLElement>('.sv2-week-wrap') || document.querySelector<HTMLElement>('.sv2-day-wrap');
      if (next === bound) return;
      if (bound) {
        bound.removeEventListener('touchstart', onStart);
        bound.removeEventListener('touchend', onEnd);
      }
      bound = next;
      if (bound) {
        bound.addEventListener('touchstart', onStart, { passive: true });
        bound.addEventListener('touchend', onEnd, { passive: false });
      }
    };

    const keepWeekAfterDayTap = (event: Event) => {
      const button = (event.target as HTMLElement | null)?.closest<HTMLButtonElement>('.sv2-wiw-week-strip button:not(.nav)');
      if (!button) return;
      const buttons = dayButtons();
      const index = buttons.indexOf(button);
      window.setTimeout(() => {
        forceWeekView();
        window.setTimeout(() => document.querySelectorAll<HTMLElement>('.sv2-week-day')[index]?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 45);
      }, 0);
    };

    bind();
    document.addEventListener('click', keepWeekAfterDayTap);
    const observer = new MutationObserver(bind);
    observer.observe(document.body, { subtree: true, childList: true });
    return () => {
      observer.disconnect();
      document.removeEventListener('click', keepWeekAfterDayTap);
      if (bound) {
        bound.removeEventListener('touchstart', onStart);
        bound.removeEventListener('touchend', onEnd);
      }
    };
  }, [active, mobile]);

  const filterLabel = useMemo(() => FILTERS.find(([key]) => key === filterKey)?.[1] || 'Alle', [filterKey]);

  if (!active || !mobile || typeof document === 'undefined') return null;

  const openCalendar = () => {
    setDateValue(readCurrentDate());
    setCalendarOpen(true);
    setFilterOpen(false);
    setPositionOpen(false);
  };

  const openFilters = () => {
    setFilterKey(readFilter());
    setFilterOpen(true);
    setCalendarOpen(false);
    setPositionOpen(false);
  };

  const applyFilter = (key: FilterKey) => {
    document.querySelector<HTMLButtonElement>(`.sv2-service-filter [data-testid="schedule-filter-${key}"]`)?.click();
    setFilterKey(key);
    setFilterOpen(false);
  };

  const applyDate = () => {
    setCalendarOpen(false);
    void moveToDate(dateValue);
  };

  const applyPosition = (choice: PositionChoice) => {
    const target = positionTargetRef.current;
    if (target) {
      try { (target as any).value = choice.value; } catch { /* best effort */ }
      target.dispatchEvent(new CustomEvent('ionChange', { detail: { value: choice.value }, bubbles: true, composed: true }));
    }
    setPositionOpen(false);
  };

  return createPortal(
    <>
      <div className="schedule-mobile-actions" aria-label="Dienstplan Schnellaktionen">
        <button type="button" className="schedule-mobile-action" aria-label="Datum auswählen" title="Kalender" onClick={openCalendar}>
          <IonIcon icon={calendarOutline} />
        </button>
        <button type="button" className={`schedule-mobile-action ${filterKey !== 'all' ? 'is-filtered' : ''}`} aria-label={`Dienstplan filtern, aktuell ${filterLabel}`} title="Filter" onClick={openFilters}>
          <IonIcon icon={optionsOutline} />
          {filterKey !== 'all' ? <span className="schedule-filter-dot" /> : null}
        </button>
      </div>

      {calendarOpen ? (
        <div className="schedule-mobile-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setCalendarOpen(false); }}>
          <section className="schedule-mobile-sheet" role="dialog" aria-modal="true" aria-label="Datum auswählen">
            <div className="schedule-mobile-sheet-handle" />
            <header><div><small>DIENSTPLAN</small><h2>Datum auswählen</h2></div></header>
            <label className="schedule-mobile-date-field">
              <span>Datum</span>
              <input type="date" value={dateValue} onChange={(event) => setDateValue(event.target.value)} />
            </label>
            <div className="schedule-mobile-sheet-actions">
              <button type="button" className="secondary" onClick={() => setDateValue(berlinToday())}>Heute</button>
              <button type="button" className="secondary" onClick={() => setCalendarOpen(false)}>Abbrechen</button>
              <button type="button" className="primary" onClick={applyDate}>Anzeigen</button>
            </div>
          </section>
        </div>
      ) : null}

      {filterOpen ? (
        <div className="schedule-mobile-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setFilterOpen(false); }}>
          <section className="schedule-mobile-sheet" role="dialog" aria-modal="true" aria-label="Dienstplan filtern">
            <div className="schedule-mobile-sheet-handle" />
            <header><div><small>DIENSTPLAN</small><h2>Bereich filtern</h2></div></header>
            <div className="schedule-mobile-filter-list">
              {FILTERS.map(([key, label]) => (
                <button type="button" key={key} className={filterKey === key ? 'active' : ''} aria-pressed={filterKey === key} onClick={() => applyFilter(key)}>
                  <span>{label}</span><span className="schedule-mobile-check">{filterKey === key ? '✓' : ''}</span>
                </button>
              ))}
            </div>
            <div className="schedule-mobile-sheet-actions single">
              <button type="button" className="secondary" onClick={() => setFilterOpen(false)}>Schließen</button>
            </div>
          </section>
        </div>
      ) : null}

      {positionOpen ? (
        <div className="schedule-mobile-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setPositionOpen(false); }}>
          <section className="schedule-mobile-sheet" role="dialog" aria-modal="true" aria-label="Position auswählen">
            <div className="schedule-mobile-sheet-handle" />
            <header><div><small>SCHICHT</small><h2>Position auswählen</h2></div></header>
            <div className="schedule-mobile-filter-list schedule-position-list">
              {positionOptions.map((choice) => (
                <button type="button" key={String(choice.value)} onClick={() => applyPosition(choice)}>
                  <span>{choice.label}</span><span className="schedule-mobile-check">›</span>
                </button>
              ))}
            </div>
          </section>
        </div>
      ) : null}
    </>,
    document.body,
  );
}
