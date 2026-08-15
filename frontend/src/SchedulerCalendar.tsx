import React, { useMemo } from 'react';
import { IonBadge, IonButton } from '@ionic/react';

export type CalendarMode = 'day' | 'week' | 'twoWeeks' | 'month';

function startOfDay(value: Date) {
  const d = new Date(value);
  d.setHours(0, 0, 0, 0);
  return d;
}

function startOfWeek(value: Date) {
  const d = startOfDay(value);
  const weekday = (d.getDay() + 6) % 7;
  d.setDate(d.getDate() - weekday);
  return d;
}

function addDays(value: Date, count: number) {
  const d = new Date(value);
  d.setDate(d.getDate() + count);
  return d;
}

function dateKey(value: Date | string) {
  const d = typeof value === 'string' ? new Date(value) : value;
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function rangeFor(mode: CalendarMode, anchor: Date) {
  if (mode === 'day') return [startOfDay(anchor)];
  if (mode === 'week') {
    const start = startOfWeek(anchor);
    return Array.from({ length: 7 }, (_, index) => addDays(start, index));
  }
  if (mode === 'twoWeeks') {
    const start = startOfWeek(anchor);
    return Array.from({ length: 14 }, (_, index) => addDays(start, index));
  }
  const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
  const start = startOfWeek(first);
  const last = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0);
  const endWeek = startOfWeek(last);
  const cellCount = Math.max(35, Math.min(42, Math.round((addDays(endWeek, 7).getTime() - start.getTime()) / 86400000)));
  return Array.from({ length: cellCount }, (_, index) => addDays(start, index));
}

function time(value: string) {
  return new Date(value).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
}

export function rangeLabel(mode: CalendarMode, anchor: Date) {
  const days = rangeFor(mode, anchor);
  const first = days[0];
  const last = days[days.length - 1];
  if (mode === 'day') return first.toLocaleDateString('de-DE', { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' });
  if (mode === 'month') return anchor.toLocaleDateString('de-DE', { month: 'long', year: 'numeric' });
  return `${first.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })} – ${last.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })}`;
}

export function moveAnchor(mode: CalendarMode, anchor: Date, direction: number) {
  const next = new Date(anchor);
  if (mode === 'day') next.setDate(next.getDate() + direction);
  else if (mode === 'week') next.setDate(next.getDate() + 7 * direction);
  else if (mode === 'twoWeeks') next.setDate(next.getDate() + 14 * direction);
  else next.setMonth(next.getMonth() + direction);
  return next;
}

export default function SchedulerCalendar({
  rows,
  mode,
  anchor,
  onMove,
  onInspect,
  selected,
  onToggleSelect,
}: {
  rows: any[];
  mode: CalendarMode;
  anchor: Date;
  onMove: (shift: any, targetDay: Date) => Promise<void> | void;
  onInspect: (shift: any) => void;
  selected: Set<string>;
  onToggleSelect: (id: string) => void;
}) {
  const days = useMemo(() => rangeFor(mode, anchor), [mode, anchor.getTime()]);
  const rowsByDay = useMemo(() => {
    const map = new Map<string, any[]>();
    for (const row of rows) {
      const key = dateKey(row.starts_at);
      const list = map.get(key) || [];
      list.push(row);
      map.set(key, list);
    }
    for (const list of map.values()) list.sort((a, b) => new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime());
    return map;
  }, [rows]);

  function dropped(event: React.DragEvent, day: Date) {
    event.preventDefault();
    const id = event.dataTransfer.getData('text/shift-id');
    const shift = rows.find((row) => row.id === id);
    if (shift) void onMove(shift, day);
  }

  return (
    <div className={`scheduler-calendar mode-${mode}`}>
      <div className="scheduler-calendar-grid" style={{ gridTemplateColumns: mode === 'day' ? 'minmax(320px,1fr)' : `repeat(${mode === 'month' ? 7 : days.length}, minmax(${mode === 'twoWeeks' ? 150 : 170}px,1fr))` }}>
        {days.map((day) => {
          const key = dateKey(day);
          const dayRows = rowsByDay.get(key) || [];
          const outsideMonth = mode === 'month' && day.getMonth() !== anchor.getMonth();
          const today = key === dateKey(new Date());
          const required = dayRows.reduce((sum, row) => sum + Number(row.required_count || 1), 0);
          const filled = dayRows.reduce((sum, row) => sum + Number(row.filled_count || 0), 0);
          return (
            <section
              className={`scheduler-day ${outsideMonth ? 'outside' : ''} ${today ? 'today' : ''}`}
              key={key}
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => dropped(event, day)}
            >
              <header>
                <div><small>{day.toLocaleDateString('de-DE', { weekday: 'short' })}</small><b>{day.getDate()}</b></div>
                {required > 0 && <IonBadge color={filled >= required ? 'success' : 'warning'}>{filled}/{required}</IonBadge>}
              </header>
              <div className="scheduler-day-shifts">
                {dayRows.map((shift) => (
                  <article
                    key={shift.id}
                    className={`scheduler-shift ${shift.status} ${selected.has(shift.id) ? 'selected' : ''}`}
                    draggable
                    onDragStart={(event) => {
                      event.dataTransfer.effectAllowed = 'move';
                      event.dataTransfer.setData('text/shift-id', shift.id);
                    }}
                  >
                    <button className="scheduler-select" aria-label="Auswählen" onClick={(event) => { event.stopPropagation(); onToggleSelect(shift.id); }}>
                      {selected.has(shift.id) ? '✓' : '○'}
                    </button>
                    <button className="scheduler-shift-main" onClick={() => onInspect(shift)}>
                      <span>{time(shift.starts_at)}–{time(shift.ends_at)}</span>
                      <b>{shift.position_name}</b>
                      <small>{shift.client_name}</small>
                      <em>{shift.location_name}</em>
                    </button>
                    <div className="scheduler-shift-foot">
                      <span>{shift.filled_count || 0}/{shift.required_count || 1} besetzt</span>
                      {Number(shift.open_count || 0) > 0 && <span>{shift.open_count} offen</span>}
                    </div>
                  </article>
                ))}
                {!dayRows.length && <div className="scheduler-drop-hint">Schicht hierher ziehen</div>}
              </div>
            </section>
          );
        })}
      </div>
      <div className="scheduler-calendar-help">Drag & Drop verschiebt eine Schicht auf den Zielday und behält Uhrzeit und Dauer bei. Harte Planungsregeln werden serverseitig erneut geprüft.</div>
    </div>
  );
}
