import React, { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { api } from './api';
import './admin-availability-manager.css';

const BERLIN = 'Europe/Berlin';
const unpack = (value: any): any[] => value?.results || value || [];

type Draft = {
  id?: string;
  worker: string;
  starts_at: string;
  ends_at: string;
  available: boolean;
  note: string;
};

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
    weekday: 'short', day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  }).format(new Date(value));
}

const blankDraft = (): Draft => ({ worker: '', starts_at: '', ends_at: '', available: true, note: '' });

export default function AdminAvailabilityManager() {
  const [active, setActive] = useState(false);
  const [manager, setManager] = useState(false);
  const [open, setOpen] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [rows, setRows] = useState<any[]>([]);
  const [workers, setWorkers] = useState<any[]>([]);
  const [draft, setDraft] = useState<Draft>(blankDraft);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    const root = document.getElementById('root');
    const sync = () => setActive(Boolean(document.querySelector('.mobile-first-app-shell-v1[data-view="operations"]')));
    sync();
    const observer = new MutationObserver(sync);
    if (root) observer.observe(root, { subtree: true, childList: true, attributes: true, attributeFilter: ['data-view'] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    api('auth/me/').then((user: any) => {
      if (!cancelled) setManager(['admin', 'manager'].includes(user?.role));
    }).catch(() => setManager(false));
    return () => { cancelled = true; };
  }, [active]);

  const load = async () => {
    if (!manager) return;
    setBusy(true);
    try {
      const [availabilityData, workerData] = await Promise.all([
        api('operations/availability/'),
        api('workers/?ordering=user__last_name'),
      ]);
      setRows(unpack(availabilityData));
      setWorkers(unpack(workerData).filter((item: any) => item.active !== false && !String(item?.user_detail?.email || '').endsWith('@sync.invalid')));
    } catch (error: any) {
      setMessage(error.message || 'Zeitpläne konnten nicht geladen werden.');
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (open && manager) void load();
  }, [open, manager]);

  const workerName = useMemo(() => new Map(workers.map((worker: any) => [String(worker.id), worker.user_detail?.name || worker.employee_number || 'Mitarbeiter'])), [workers]);

  function create() {
    setDraft(blankDraft());
    setFormOpen(true);
  }

  function edit(item: any) {
    setDraft({
      id: String(item.id),
      worker: String(item.worker || ''),
      starts_at: toInput(item.starts_at),
      ends_at: toInput(item.ends_at),
      available: item.available !== false,
      note: item.note || '',
    });
    setFormOpen(true);
  }

  async function save() {
    if (!draft.worker || !draft.starts_at || !draft.ends_at) {
      setMessage('Bitte Mitarbeiter, Beginn und Ende auswählen.');
      return;
    }
    setBusy(true);
    try {
      await api(draft.id ? `operations/availability/${draft.id}/` : 'operations/availability/', {
        method: draft.id ? 'PATCH' : 'POST',
        body: JSON.stringify({
          worker: draft.worker,
          starts_at: draft.starts_at,
          ends_at: draft.ends_at,
          available: draft.available,
          note: draft.note,
        }),
      });
      setFormOpen(false);
      setMessage(draft.id ? 'Zeitplan wurde geändert.' : 'Zeitplan wurde hinzugefügt.');
      await load();
    } catch (error: any) {
      setMessage(error.message || 'Zeitplan konnte nicht gespeichert werden.');
    } finally {
      setBusy(false);
    }
  }

  async function remove(item: any) {
    if (!window.confirm(`${item.worker_name || workerName.get(String(item.worker)) || 'Mitarbeiter'} · diesen Zeitplan wirklich löschen?`)) return;
    setBusy(true);
    try {
      await api(`operations/availability/${item.id}/`, { method: 'DELETE' });
      setMessage('Zeitplan wurde gelöscht.');
      await load();
    } catch (error: any) {
      setMessage(error.message || 'Zeitplan konnte nicht gelöscht werden.');
    } finally {
      setBusy(false);
    }
  }

  if (!active || !manager || typeof document === 'undefined') return null;

  return createPortal(
    <>
      <button type="button" className="admin-availability-trigger" onClick={() => setOpen(true)}>Mitarbeiter-Zeitpläne</button>
      {open ? <div className="admin-availability-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false); }}>
        <section className="admin-availability-sheet" role="dialog" aria-modal="true" aria-label="Mitarbeiter-Zeitpläne verwalten">
          <header><div><small>ADMIN · ZEITPLAN</small><h2>Mitarbeiter-Zeitpläne</h2><p>Von Mitarbeitern eingetragene Verfügbarkeiten ändern, ergänzen oder löschen.</p></div><button type="button" onClick={() => setOpen(false)}>Fertig</button></header>
          <div className="admin-availability-actions"><button type="button" className="primary" onClick={create}>+ Zeitplan hinzufügen</button><button type="button" onClick={() => void load()} disabled={busy}>{busy ? '…' : 'Aktualisieren'}</button></div>
          <div className="admin-availability-list">
            {rows.map((item) => <article key={item.id}>
              <div className="copy"><b>{item.worker_name || workerName.get(String(item.worker)) || 'Mitarbeiter'}</b><span>{display(item.starts_at)} – {display(item.ends_at)}</span><small>{item.note || 'Kein Hinweis'}</small></div>
              <span className={`status ${item.available !== false ? 'yes' : 'no'}`}>{item.available !== false ? 'Verfügbar' : 'Nicht verfügbar'}</span>
              <div className="row-actions"><button type="button" onClick={() => edit(item)}>Ändern</button><button type="button" className="danger" onClick={() => void remove(item)}>Löschen</button></div>
            </article>)}
            {!rows.length && !busy ? <div className="empty">Noch keine Mitarbeiter-Zeitpläne vorhanden.</div> : null}
          </div>
          {message ? <button type="button" className="admin-availability-message" onClick={() => setMessage('')}>{message}</button> : null}
        </section>
      </div> : null}

      {formOpen ? <div className="admin-availability-backdrop top" onMouseDown={(event) => { if (event.target === event.currentTarget) setFormOpen(false); }}>
        <section className="admin-availability-form" role="dialog" aria-modal="true" aria-label={draft.id ? 'Zeitplan bearbeiten' : 'Zeitplan hinzufügen'}>
          <header><button type="button" onClick={() => setFormOpen(false)}>Abbrechen</button><strong>{draft.id ? 'Zeitplan bearbeiten' : 'Zeitplan hinzufügen'}</strong><button type="button" className="save" disabled={busy} onClick={() => void save()}>Sichern</button></header>
          <label>Mitarbeiter<select value={draft.worker} onChange={(event) => setDraft((current) => ({ ...current, worker: event.target.value }))}><option value="">Mitarbeiter auswählen</option>{workers.map((worker: any) => <option key={worker.id} value={worker.id}>{worker.user_detail?.name || worker.employee_number}</option>)}</select></label>
          <label>Beginn<input type="datetime-local" step="900" value={draft.starts_at} onChange={(event) => setDraft((current) => ({ ...current, starts_at: event.target.value }))} /></label>
          <label>Ende<input type="datetime-local" step="900" value={draft.ends_at} onChange={(event) => setDraft((current) => ({ ...current, ends_at: event.target.value }))} /></label>
          <label className="switch-row"><span>In diesem Zeitraum verfügbar</span><input type="checkbox" checked={draft.available} onChange={(event) => setDraft((current) => ({ ...current, available: event.target.checked }))} /></label>
          <label>Hinweis<textarea value={draft.note} onChange={(event) => setDraft((current) => ({ ...current, note: event.target.value }))} placeholder="Optionaler Hinweis …" /></label>
        </section>
      </div> : null}
    </>,
    document.body,
  );
}
