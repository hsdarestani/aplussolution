import React, { useState } from 'react';
import { Capacitor } from '@capacitor/core';
import { apiBlob } from './api';
import { saveSchedulePdf } from './saveSchedulePdf';
import './weekly-stundenzettel.css';

export function previousBerlinWeek(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Berlin', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now);
  const part = (type: string) => Number(parts.find((item) => item.type === type)?.value);
  const day = new Date(Date.UTC(part('year'), part('month') - 1, part('day')));
  day.setUTCDate(day.getUTCDate() - (day.getUTCDay() + 6) % 7 - 7);
  day.setUTCDate(day.getUTCDate() + 3);
  const year = day.getUTCFullYear();
  const week = Math.ceil(((day.getTime() - Date.UTC(year, 0, 1)) / 86400000 + 1) / 7);
  return `${year}-W${String(week).padStart(2, '0')}`;
}

export default function WeeklyStundenzettel() {
  const [week, setWeek] = useState(() => previousBerlinWeek());
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState('');
  if (Capacitor.isNativePlatform()) return null;
  async function download(group: string) {
    if (!/^\d{4}-W\d{2}$/.test(week)) { setMessage('Bitte eine Kalenderwoche wählen.'); return; }
    setBusy(group); setMessage('');
    try {
      const { blob, filename } = await apiBlob(`reports/stundenzettel.pdf?${new URLSearchParams({ week, group })}`);
      await saveSchedulePdf(blob, filename);
      setMessage('PDF wurde heruntergeladen.');
    } catch (error: any) { setMessage(error?.message || 'PDF konnte nicht erstellt werden. Bitte erneut versuchen.'); }
    finally { setBusy(''); }
  }
  return <section className="weekly-stundenzettel" aria-label="Stundenzettel exportieren">
    <div><small>WOCHENEXPORT</small><h2>Stundenzettel</h2><p>Housekeeping und Front Office im gewohnten Formular. Alle zugewiesenen Schichten je Hotel. Beginn, Ende und Stunden stammen aus den vom Mitarbeiter erfassten Zeiten (IST, wie eingetragen), ohne Pausenabzug. Ohne erfasste Endzeit bleiben die Zeitfelder leer; Dienstplanzeiten werden nicht als Arbeitszeit übernommen. Das PDF bleibt bearbeitbar.</p></div>
    <div className="weekly-stundenzettel-actions">
      <label>Kalenderwoche<input type="week" required value={week} disabled={Boolean(busy)} onChange={(event) => { setWeek(event.target.value); setMessage(''); }} /></label>
      <button type="button" disabled={Boolean(busy) || !week} onClick={() => void download('housekeeping')}>{busy === 'housekeeping' ? 'PDF wird erstellt …' : 'Housekeeping · PDF'}</button>
      <button type="button" disabled={Boolean(busy) || !week} onClick={() => void download('front_office')}>{busy === 'front_office' ? 'PDF wird erstellt …' : 'Front Office · PDF'}</button>
    </div>{message && <p role="status">{message}</p>}
  </section>;
}
