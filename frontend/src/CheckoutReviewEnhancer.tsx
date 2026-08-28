import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { api } from './api';
import './checkout-review-enhancer.css';

const BERLIN = 'Europe/Berlin';

function toInput(value?: string) {
  if (!value) return '';
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: BERLIN,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(new Date(value));
  const get = (type: string) => parts.find((part) => part.type === type)?.value || '';
  return `${get('year')}-${get('month')}-${get('day')}T${get('hour')}:${get('minute')}`;
}

function display(value?: string) {
  if (!value) return '–';
  return new Intl.DateTimeFormat('de-DE', {
    timeZone: BERLIN,
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  }).format(new Date(value));
}

function minusMinutes(value: string, minutes: number) {
  if (!value) return value;
  const [date, time] = value.split('T');
  const [year, month, day] = date.split('-').map(Number);
  const [hour, minute] = time.split(':').map(Number);
  const next = new Date(Date.UTC(year, month - 1, day, hour, minute) - minutes * 60000);
  return `${next.getUTCFullYear()}-${String(next.getUTCMonth() + 1).padStart(2, '0')}-${String(next.getUTCDate()).padStart(2, '0')}T${String(next.getUTCHours()).padStart(2, '0')}:${String(next.getUTCMinutes()).padStart(2, '0')}`;
}

export default function CheckoutReviewEnhancer() {
  const [active, setActive] = useState(false);
  const [manager, setManager] = useState(false);
  const [rows, setRows] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string>();
  const [message, setMessage] = useState('');

  useEffect(() => {
    const root = document.getElementById('root');
    const sync = () => setActive(Boolean(document.querySelector('.mobile-first-app-shell-v1[data-view="time"]')));
    sync();
    const observer = new MutationObserver(sync);
    if (root) observer.observe(root, { subtree: true, childList: true, attributes: true, attributeFilter: ['data-view'] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!active) {
      setManager(false);
      setRows([]);
      setOpen(false);
      return;
    }
    let cancelled = false;
    api('auth/me/').then((user: any) => {
      if (cancelled) return;
      const allowed = ['admin', 'manager'].includes(user?.role);
      setManager(allowed);
      if (!allowed) {
        setRows([]);
        setOpen(false);
      }
    }).catch(() => {
      if (!cancelled) {
        setManager(false);
        setRows([]);
        setOpen(false);
      }
    });
    return () => { cancelled = true; };
  }, [active]);

  const load = async () => {
    if (!active || !manager) return;
    try {
      const data: any = await api('attendance/exceptions/');
      const all = Array.isArray(data?.unapproved_entries) ? data.unapproved_entries : [];
      const outside = all.filter((entry: any) => String(entry.edit_reason || '').startsWith('OUTSIDE_GEOFENCE:'));
      setRows(outside);
      setDrafts((current) => {
        const next = { ...current };
        outside.forEach((entry: any) => { if (!next[entry.id]) next[entry.id] = toInput(entry.clock_out); });
        return next;
      });
    } catch {
      setRows([]);
      setOpen(false);
    }
  };

  useEffect(() => { if (active && manager) void load(); }, [active, manager]);

  async function approve(entry: any) {
    setBusy(entry.id);
    try {
      await api(`time-entries/${entry.id}/approve/`, {
        method: 'POST',
        body: JSON.stringify({
          clock_out: drafts[entry.id] || toInput(entry.clock_out),
          reason: 'Check-out außerhalb des Einsatzortes geprüft.',
        }),
      });
      setMessage('Check-out-Zeit angepasst und freigegeben.');
      await load();
    } catch (error: any) {
      setMessage(error.message || 'Freigabe fehlgeschlagen.');
    } finally {
      setBusy(undefined);
    }
  }

  const count = rows.length;
  const host = typeof document !== 'undefined' ? document.body : null;
  if (!active || !manager || !count || !host) return null;

  return createPortal(
    <>
      <button type="button" className="checkout-review-trigger" onClick={() => setOpen(true)}>{count} Check-out{count === 1 ? '' : 's'} prüfen</button>
      {open ? <div className="checkout-review-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false); }}>
        <section className="checkout-review-sheet" role="dialog" aria-modal="true" aria-label="Check-outs außerhalb des Einsatzortes prüfen">
          <header><div><small>ADMIN · PRÜFUNG</small><h2>Check-out außerhalb Standort</h2></div><button type="button" onClick={() => setOpen(false)}>Fertig</button></header>
          <p className="checkout-review-intro">Der Mitarbeiter konnte ausstempeln. Diese Zeiten warten nur noch auf deine Prüfung. Du kannst die Zeit vor der Freigabe korrigieren.</p>
          <div className="checkout-review-list">
            {rows.map((entry) => <article key={entry.id}>
              <div className="checkout-review-person"><b>{entry.worker_name || 'Mitarbeiter'}</b><span>{entry.shift_title || 'Schicht'}</span></div>
              <div className="checkout-review-times"><small>Check-in {display(entry.clock_in)}</small><label>Check-out<input type="datetime-local" step="900" value={drafts[entry.id] || ''} onChange={(event) => setDrafts((current) => ({ ...current, [entry.id]: event.target.value }))} /></label></div>
              <div className="checkout-review-actions"><button type="button" onClick={() => setDrafts((current) => ({ ...current, [entry.id]: minusMinutes(current[entry.id] || toInput(entry.clock_out), 15) }))}>−15 Min.</button><button type="button" className="primary" disabled={busy === entry.id} onClick={() => void approve(entry)}>{busy === entry.id ? '…' : 'Anpassen & freigeben'}</button></div>
            </article>)}
          </div>
          {message ? <button type="button" className="checkout-review-message" onClick={() => setMessage('')}>{message}</button> : null}
        </section>
      </div> : null}
    </>,
    host,
  );
}
