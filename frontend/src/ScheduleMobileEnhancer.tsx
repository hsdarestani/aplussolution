import React, { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { IonIcon } from '@ionic/react';
import { calendarOutline, optionsOutline } from 'ionicons/icons';
import './schedule-mobile-enhancer.css';

type FilterKey = 'all' | 'service' | 'hotel' | 'housekeeping';

const FILTERS: Array<[FilterKey, string]> = [
  ['all', 'Alle'],
  ['service', 'Service'],
  ['hotel', 'Hotel'],
  ['housekeeping', 'Housekeeping'],
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

function readCurrentDate() {
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
}

async function moveOneDay(direction: -1 | 1) {
  let buttons = dayButtons();
  const activeIndex = buttons.findIndex((button) => button.classList.contains('active'));
  if (activeIndex < 0) return;

  const nextIndex = activeIndex + direction;
  if (nextIndex >= 0 && nextIndex < buttons.length) {
    buttons[nextIndex]?.click();
    return;
  }

  const nav = Array.from(document.querySelectorAll<HTMLButtonElement>('.sv2-wiw-week-strip button.nav'));
  const weekButton = direction < 0 ? nav[0] : nav[nav.length - 1];
  if (!weekButton) return;
  weekButton.click();
  await waitForUi();
  buttons = dayButtons();
  buttons[direction < 0 ? buttons.length - 1 : 0]?.click();
}

function readFilter(): FilterKey {
  const active = document.querySelector<HTMLButtonElement>('.sv2-service-filter button[aria-pressed="true"]');
  const testId = active?.dataset.testid || '';
  const key = testId.replace('schedule-filter-', '') as FilterKey;
  return FILTERS.some(([candidate]) => candidate === key) ? key : 'all';
}

export default function ScheduleMobileEnhancer() {
  const [active, setActive] = useState(false);
  const [mobile, setMobile] = useState(() => typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches);
  const [calendarOpen, setCalendarOpen] = useState(false);
  const [filterOpen, setFilterOpen] = useState(false);
  const [dateValue, setDateValue] = useState(berlinToday());
  const [filterKey, setFilterKey] = useState<FilterKey>('all');

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
      setCalendarOpen(false);
      setFilterOpen(false);
    }
    return () => document.body.classList.remove('schedule-mobile-enhanced');
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
      void moveOneDay(deltaX < 0 ? 1 : -1);
    };

    const bind = () => {
      const next = document.querySelector<HTMLElement>('.sv2-day-wrap');
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

    bind();
    const observer = new MutationObserver(bind);
    observer.observe(document.body, { subtree: true, childList: true });
    return () => {
      observer.disconnect();
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
  };

  const openFilters = () => {
    setFilterKey(readFilter());
    setFilterOpen(true);
    setCalendarOpen(false);
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
    </>,
    document.body,
  );
}
