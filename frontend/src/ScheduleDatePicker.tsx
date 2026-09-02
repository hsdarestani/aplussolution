import React, { useState } from 'react';

function dateKey(date: Date) {
  return [date.getUTCFullYear(), String(date.getUTCMonth() + 1).padStart(2, '0'), String(date.getUTCDate()).padStart(2, '0')].join('-');
}

export default function ScheduleDatePicker({ title = 'Schichtdatum', value, onSelect, onClose }: {
  title?: string; value: string; onSelect: (date: string) => void; onClose: () => void;
}) {
  const [month, setMonth] = useState(() => new Date(value.slice(0, 7) + '-01T12:00:00Z'));
  const first = new Date(month);
  first.setUTCDate(1 - ((first.getUTCDay() + 6) % 7));
  const days = Array.from({ length: 42 }, (_, index) => {
    const day = new Date(first);
    day.setUTCDate(day.getUTCDate() + index);
    return day;
  });
  function move(amount: number) {
    const next = new Date(month);
    next.setUTCMonth(next.getUTCMonth() + amount);
    setMonth(next);
  }
  return <div className="wiw-sheet-backdrop wiw-calendar-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <section role="dialog" aria-modal="true" aria-label={title} className="wiw-calendar-sheet" onKeyDown={event => { if (event.key === 'Escape') onClose(); }}>
      <header><b>{title}</b><button type="button" onClick={onClose}>Abbrechen</button></header>
      <nav><button type="button" aria-label="Vorheriger Monat" onClick={() => move(-1)}>‹</button><strong>{new Intl.DateTimeFormat('de-DE', { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(month)}</strong><button type="button" aria-label="Nächster Monat" onClick={() => move(1)}>›</button></nav>
      <div className="wiw-calendar-grid">
        {['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'].map(day => <small key={day}>{day}</small>)}
        {days.map(day => {
          const key = dateKey(day);
          return <button type="button" key={key} aria-label={key} aria-pressed={key === value} autoFocus={key === value} className={key === value ? 'selected' : day.getUTCMonth() !== month.getUTCMonth() ? 'outside' : ''} onClick={() => onSelect(key)}>{day.getUTCDate()}</button>;
        })}
      </div>
    </section>
  </div>;
}
