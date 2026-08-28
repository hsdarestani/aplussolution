import { useEffect, useState } from 'react';
import { api } from './api';
import './mobile-attendance-clarity.css';

const TZ = 'Europe/Berlin';

type Summary = { entries: number; minutes: number; workers: Set<string> };

function monthKeyFromIso(value?: string) {
  if (!value) return '';
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: TZ,
    year: 'numeric',
    month: '2-digit',
  }).formatToParts(new Date(value));
  const get = (type: string) => parts.find((part) => part.type === type)?.value || '';
  return `${get('year')}-${get('month')}`;
}

function currentBerlinMonthOffset(offset: number) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: TZ,
    year: 'numeric',
    month: '2-digit',
  }).formatToParts(new Date());
  const year = Number(parts.find((part) => part.type === 'year')?.value || new Date().getUTCFullYear());
  const month = Number(parts.find((part) => part.type === 'month')?.value || new Date().getUTCMonth() + 1);
  const date = new Date(Date.UTC(year, month - 1 - offset, 1, 12));
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}`;
}

function entryMinutes(entry: any) {
  if (Number.isFinite(Number(entry?.worked_minutes))) return Math.max(0, Number(entry.worked_minutes));
  if (!entry?.clock_in || !entry?.clock_out) return 0;
  return Math.max(0, Math.round((new Date(entry.clock_out).getTime() - new Date(entry.clock_in).getTime()) / 60000));
}

function hoursLabel(minutes: number) {
  return (minutes / 60).toLocaleString('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 2 });
}

export default function MobileAttendanceClarityEnhancer() {
  const [active, setActive] = useState(false);
  const [role, setRole] = useState('');
  const [history, setHistory] = useState<any[]>([]);

  useEffect(() => {
    const root = document.getElementById('root');
    const sync = () => {
      const mobile = window.matchMedia('(max-width: 900px)').matches;
      setActive(mobile && Boolean(document.querySelector('.mobile-first-app-shell-v1[data-view="time"]')));
    };
    sync();
    const observer = new MutationObserver(sync);
    if (root) observer.observe(root, { subtree: true, childList: true, attributes: true, attributeFilter: ['data-view'] });
    window.addEventListener('resize', sync);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', sync);
    };
  }, []);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    void Promise.all([api('auth/me/'), api('attendance/history/')])
      .then(([me, payload]: any[]) => {
        if (cancelled) return;
        setRole(String(me?.role || ''));
        setHistory(Array.isArray(payload?.history) ? payload.history : []);
      })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, [active]);

  useEffect(() => {
    if (!active || !role) return;
    const manager = role === 'admin' || role === 'manager';
    const summaries = new Map<string, Summary>();
    for (const entry of history) {
      const key = monthKeyFromIso(entry?.clock_in);
      if (!key) continue;
      const summary = summaries.get(key) || { entries: 0, minutes: 0, workers: new Set<string>() };
      summary.entries += 1;
      summary.minutes += entryMinutes(entry);
      if (entry?.worker) summary.workers.add(String(entry.worker));
      summaries.set(key, summary);
    }

    const decorate = () => {
      const root = document.querySelector<HTMLElement>('.wiw-pay-periods');
      if (!root) return false;
      const title = root.querySelector<HTMLElement>('.wiw-mobile-screen-title');
      if (title) title.textContent = manager ? 'Team-Zeiterfassung' : 'Meine Arbeitszeiten';

      let note = root.querySelector<HTMLElement>('.wiw-attendance-role-note');
      if (!note) {
        note = document.createElement('div');
        note.className = 'wiw-attendance-role-note';
        title?.insertAdjacentElement('afterend', note);
      }
      note.innerHTML = manager
        ? '<b>Abrechnungszeiträume</b><span>Einträge, Mitarbeiter und Gesamtstunden pro Monat auf einen Blick.</span>'
        : '<b>Deine Zeiterfassung</b><span>Monate ohne erfasste Arbeitszeit sind deutlich als leer markiert.</span>';

      const rows = Array.from(root.querySelectorAll<HTMLButtonElement>('.wiw-period-row'));
      rows.forEach((row, index) => {
        const summary = summaries.get(currentBerlinMonthOffset(index));
        const hasData = Boolean(summary?.entries);
        row.classList.toggle('has-time', hasData);
        row.classList.toggle('is-empty', !hasData);

        let meta = row.querySelector<HTMLElement>('.wiw-period-meta');
        if (!meta) {
          meta = document.createElement('small');
          meta.className = 'wiw-period-meta';
          const circle = row.querySelector('.wiw-period-circle');
          row.insertBefore(meta, circle || null);
        }
        if (hasData && summary) {
          meta.textContent = manager
            ? `${summary.entries} Einträge · ${summary.workers.size} Mitarbeiter · ${hoursLabel(summary.minutes)} Std.`
            : `${summary.entries} Einträge · ${hoursLabel(summary.minutes)} Std.`;
        } else {
          meta.textContent = manager ? 'Keine Zeiteinträge im Team' : 'Keine Arbeitszeit erfasst';
        }

        const circle = row.querySelector<HTMLElement>('.wiw-period-circle');
        if (circle) {
          circle.classList.toggle('has-data', hasData);
          circle.classList.toggle('empty', !hasData);
          circle.textContent = hasData ? '✓' : '–';
          circle.setAttribute('aria-label', hasData ? 'Zeiten vorhanden' : 'Keine Zeiten vorhanden');
        }
      });
      return true;
    };

    const timers = [0, 80, 250, 700, 1400].map((delay) => window.setTimeout(decorate, delay));
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [active, history, role]);

  return null;
}
