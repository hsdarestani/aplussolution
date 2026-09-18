import React from 'react';
import './german-time-field.css';

const HOURS = Array.from({ length: 24 }, (_, index) => String(index).padStart(2, '0'));
const MINUTES = Array.from({ length: 60 }, (_, index) => String(index).padStart(2, '0'));

export default function GermanTimeField({
  label,
  value,
  onChange,
  disabled,
}: {
  label: string;
  value?: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const [hourRaw = '00', minuteRaw = '00'] = String(value || '00:00').split(':');
  const hour = HOURS.includes(hourRaw) ? hourRaw : '00';
  const minute = MINUTES.includes(minuteRaw) ? minuteRaw : '00';

  return (
    <label className="german-time-field">
      <span>{label}</span>
      <div className="german-time-selects">
        <select aria-label={`${label} Stunde`} value={hour} disabled={disabled} onChange={(event) => onChange(`${event.target.value}:${minute}`)}>
          {HOURS.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
        <b>:</b>
        <select aria-label={`${label} Minute`} value={minute} disabled={disabled} onChange={(event) => onChange(`${hour}:${event.target.value}`)}>
          {MINUTES.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
      </div>
    </label>
  );
}
