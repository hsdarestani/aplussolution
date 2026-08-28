import React, { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { api } from './api';
import './desktop-attendance-history.css';

const TZ = 'Europe/Berlin';
const number = (value: unknown) => { const parsed = Number(value); return Number.isFinite(parsed) ? parsed : 0; };
const workerName = (entry: any) => String(entry?.worker_name || entry?.employee_name || 'Mitarbeiter');
const workerId = (entry: any) => String(entry?.worker || entry?.worker_id || workerName(entry));
const monthKey = (value?: string) => {
  if (!value) return '';
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit' }).formatToParts(new Date(value));
  const map = Object.fromEntries(parts.filter(part => part.type !== 'literal').map(part => [part.type, part.value]));
  return `${map.year}-${map.month}`;
};
const monthLabel = (value: string) => {
  const [year, month] = value.split('-').map(Number);
  if (!year || !month) return value;
  return new Intl.DateTimeFormat('de-DE', { timeZone: TZ, month: 'long', year: 'numeric' }).format(new Date(Date.UTC(year, month - 1, 1, 12)));
};
const dateLabel = (value?: string) => value ? new Date(value).toLocaleDateString('de-DE', { timeZone: TZ, weekday: 'short', day: '2-digit', month: '2-digit', year: 'numeric' }) : '–';
const timeLabel = (value?: string) => value ? new Date(value).toLocaleTimeString('de-DE', { timeZone: TZ, hour: '2-digit', minute: '2-digit' }) : '–';
const minutes = (entry: any) => {
  if (Number.isFinite(Number(entry?.worked_minutes))) return Math.max(0, Number(entry.worked_minutes));
  if (!entry?.clock_in || !entry?.clock_out) return 0;
  return Math.max(0, Math.round((new Date(entry.clock_out).getTime() - new Date(entry.clock_in).getTime()) / 60000));
};
const hours = (value: number) => (value / 60).toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function DesktopAttendanceHistoryEnhancer() {
  const [target, setTarget] = useState<Element | null>(null);
  const [rows, setRows] = useState<any[]>([]);
  const [month, setMonth] = useState('');
  const [employee, setEmployee] = useState('all');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const locate = () => {
      if (!window.matchMedia('(min-width: 901px)').matches) { setTarget(null); return; }
      const stats = document.querySelector('.attendance-stats');
      const head = document.querySelector('.attendance-head');
      if (!stats || !head) { setTarget(null); return; }
      let host = document.querySelector('[data-desktop-attendance-history-host]');
      if (!host) {
        host = document.createElement('div');
        host.setAttribute('data-desktop-attendance-history-host', 'true');
        stats.insertAdjacentElement('afterend', host);
      }
      setTarget(host);
    };
    locate();
    const observer = new MutationObserver(locate);
    observer.observe(document.body, { childList: true, subtree: true });
    window.addEventListener('resize', locate);
    return () => { observer.disconnect(); window.removeEventListener('resize', locate); };
  }, []);

  async function load() {
    setLoading(true); setError('');
    try {
      const payload: any = await api('attendance/history/');
      const history = Array.isArray(payload?.history) ? payload.history : Array.isArray(payload) ? payload : [];
      const sorted = [...history].sort((a, b) => new Date(b.clock_in || 0).getTime() - new Date(a.clock_in || 0).getTime());
      setRows(sorted);
      const newest = sorted.map(row => monthKey(row.clock_in)).filter(Boolean).sort().reverse()[0] || 'all';
      setMonth(current => current || newest);
    } catch (reason: any) {
      setError(reason?.message || 'Arbeitszeiten konnten nicht geladen werden.');
    } finally { setLoading(false); }
  }

  useEffect(() => { if (target) void load(); }, [target]);

  const months = useMemo(() => Array.from(new Set(rows.map(row => monthKey(row.clock_in)).filter(Boolean))).sort().reverse(), [rows]);
  const employees = useMemo(() => {
    const map = new Map<string, string>();
    rows.forEach(row => map.set(workerId(row), workerName(row)));
    return Array.from(map.entries()).sort((a, b) => a[1].localeCompare(b[1], 'de'));
  }, [rows]);
  const visible = useMemo(() => {
    const q = query.trim().toLocaleLowerCase('de-DE');
    return rows.filter(row => {
      if (month && month !== 'all' && monthKey(row.clock_in) !== month) return false;
      if (employee !== 'all' && workerId(row) !== employee) return false;
      if (q && !workerName(row).toLocaleLowerCase('de-DE').includes(q) && !String(row.shift_title || row.position_name || row.location_name || '').toLocaleLowerCase('de-DE').includes(q)) return false;
      return true;
    });
  }, [rows, month, employee, query]);
  const totalMinutes = visible.reduce((sum, row) => sum + minutes(row), 0);
  const imported = visible.filter(row => Boolean(row.wiw_time_id)).length;

  if (!target) return null;
  return createPortal(
    <section className="desktop-attendance-history" data-testid="desktop-attendance-history">
      <div className="desktop-attendance-history-head">
        <div>
          <small>ARBEITSZEITEN · SYNCHRONISIERT</small>
          <h2>Alle erfassten Zeiten</h2>
          <p>Auch die aus When I Work übernommenen Arbeitszeiten werden hier auf dem Desktop angezeigt. Importierte WIW-Einträge bleiben schreibgeschützt.</p>
        </div>
        <button type="button" onClick={() => void load()} disabled={loading}>{loading ? 'Lädt …' : 'Aktualisieren'}</button>
      </div>

      <div className="desktop-attendance-history-summary">
        <div><span>Einträge</span><strong>{visible.length}</strong></div>
        <div><span>Gesamtstunden</span><strong>{hours(totalMinutes)} Std.</strong></div>
        <div><span>WIW-Historie</span><strong>{imported}</strong></div>
      </div>

      <div className="desktop-attendance-history-filters">
        <label>Zeitraum<select aria-label="Arbeitszeiten Zeitraum" value={month || 'all'} onChange={event => setMonth(event.target.value)}><option value="all">Alle Monate</option>{months.map(item => <option key={item} value={item}>{monthLabel(item)}</option>)}</select></label>
        <label>Mitarbeiter<select aria-label="Arbeitszeiten Mitarbeiter" value={employee} onChange={event => setEmployee(event.target.value)}><option value="all">Alle Mitarbeiter</option>{employees.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>
        <label className="desktop-attendance-history-search">Suche<input type="search" aria-label="Arbeitszeiten suchen" placeholder="Name, Einsatz, Ort …" value={query} onChange={event => setQuery(event.target.value)} /></label>
      </div>

      {error && <div className="desktop-attendance-history-error">{error}</div>}
      <div className="desktop-attendance-history-table" role="table" aria-label="Erfasste Arbeitszeiten">
        <div className="desktop-attendance-history-row header" role="row"><span>Mitarbeiter</span><span>Datum</span><span>Zeit</span><span>Einsatz</span><span>Stunden</span><span>Quelle</span></div>
        {visible.map(entry => <div className="desktop-attendance-history-row" role="row" key={entry.id}>
          <span className="person"><b>{workerName(entry)}</b><small>{entry.position_name || entry.shift_title || 'Arbeitszeit'}</small></span>
          <span>{dateLabel(entry.clock_in)}</span>
          <span>{timeLabel(entry.clock_in)} – {entry.clock_out ? timeLabel(entry.clock_out) : 'läuft'}</span>
          <span className="assignment">{entry.location_name || entry.shift_title || entry.position_name || '–'}</span>
          <span><b>{hours(minutes(entry))}</b></span>
          <span><em className={entry.wiw_time_id ? 'wiw' : 'aplus'}>{entry.wiw_time_id ? 'WIW' : 'A+'}</em></span>
        </div>)}
        {!visible.length && !loading && !error && <div className="desktop-attendance-history-empty">Für diese Auswahl sind keine Arbeitszeiten vorhanden.</div>}
        {loading && !rows.length && <div className="desktop-attendance-history-empty">Arbeitszeiten werden geladen …</div>}
      </div>
    </section>,
    target,
  );
}
