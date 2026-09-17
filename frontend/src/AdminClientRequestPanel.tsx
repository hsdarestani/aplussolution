import React, { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { IonIcon, IonSpinner } from '@ionic/react';
import { briefcaseOutline, calendarOutline, checkmarkCircleOutline, closeOutline, createOutline, personOutline, timeOutline } from 'ionicons/icons';
import { api, User } from './api';
import './client-portal-v4.css';

const TZ = 'Europe/Berlin';

function dateTime(value?: string) {
  if (!value) return '–';
  return new Intl.DateTimeFormat('de-DE', { timeZone: TZ, day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value));
}
function inputDateTime(value?: string) {
  if (!value) return '';
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(new Date(value));
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)?.value || '';
  return `${part('year')}-${part('month')}-${part('day')}T${part('hour')}:${part('minute')}`;
}
function focusIntoView(event: React.FocusEvent<HTMLElement>) {
  const target = event.target as HTMLElement;
  window.setTimeout(() => target.scrollIntoView({ behavior: 'smooth', block: 'center' }), 260);
}

function AdminModal({ title, close, children, footer }: { title: string; close: () => void; children: React.ReactNode; footer: React.ReactNode }) {
  useEffect(() => {
    document.body.classList.add('client-portal-modal-open');
    return () => document.body.classList.remove('client-portal-modal-open');
  }, []);
  return <div className="client-v4-modal" onFocusCapture={focusIntoView}>
    <header><button type="button" onClick={close}><IonIcon icon={closeOutline}/></button><strong>{title}</strong><span/></header>
    <div className="client-v4-modal-scroll">{children}</div>
    <div className="client-v4-modal-footer">{footer}</div>
  </div>;
}

export default function AdminClientRequestPanel() {
  const [user, setUser] = useState<User | null>(null);
  const [view, setView] = useState('');
  const [host, setHost] = useState<HTMLElement | null>(null);
  const [mount, setMount] = useState<HTMLElement | null>(null);
  const [orders, setOrders] = useState<any>({ pending: [], history: [], positions: [], locations: [] });
  const [shiftRequests, setShiftRequests] = useState<any>({ pending: [], history: [] });
  const [editing, setEditing] = useState<any>();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [mobile, setMobile] = useState(() => window.matchMedia('(max-width: 900px)').matches);

  useEffect(() => {
    if (!localStorage.getItem('access')) return;
    let cancelled = false;
    void api('auth/me/').then((current: User) => {
      if (!cancelled && ['admin', 'manager'].includes(current?.role || '')) setUser(current);
    }).catch(() => undefined);
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const media = window.matchMedia('(max-width: 900px)');
    const syncMobile = () => setMobile(media.matches);
    media.addEventListener?.('change', syncMobile);
    const sync = () => {
      const shell = document.querySelector<HTMLElement>('.mobile-first-app-shell-v1');
      setView(shell?.dataset.view || '');
      setHost(document.querySelector<HTMLElement>('.app-main'));
    };
    sync();
    const root = document.getElementById('root');
    const observer = new MutationObserver(sync);
    if (root) observer.observe(root, { subtree: true, childList: true, attributes: true, attributeFilter: ['data-view'] });
    return () => { media.removeEventListener?.('change', syncMobile); observer.disconnect(); };
  }, []);

  useEffect(() => {
    if (!user || !mobile || view !== 'operations' || !host) { setMount(null); return; }
    const node = document.createElement('div');
    node.className = 'client-admin-request-host';
    node.dataset.clientRequests = '1';
    host.prepend(node);
    setMount(node);
    return () => node.remove();
  }, [user, mobile, view, host]);

  const load = async () => {
    if (!user) return;
    setBusy(true);
    try {
      const [orderData, shiftData] = await Promise.all([
        api('portal/admin/client-requests/'),
        api('portal/admin/shift-change-requests/'),
      ]);
      setOrders(orderData || { pending: [], history: [], positions: [], locations: [] });
      setShiftRequests(shiftData || { pending: [], history: [] });
    } catch (error: any) {
      setMessage(error?.message || 'Kundenanfragen konnten nicht geladen werden.');
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => { if (mount) void load(); }, [mount]);

  const pendingCount = Number(orders.pending?.length || 0) + Number(shiftRequests.pending?.length || 0);
  const relevantLocations = useMemo(() => (orders.locations || []).filter((item: any) => !editing?.client_id || item.client_id === editing.client_id), [orders.locations, editing?.client_id]);

  function openOrder(row: any) {
    const functionValue = Array.isArray(row.functions) ? row.functions[0] : '';
    setEditing({ ...row, starts_at: inputDateTime(row.starts_at), ends_at: inputDateTime(row.ends_at), position: functionValue || '' });
    setMessage('');
  }

  async function decideOrder(decision: 'approve' | 'reject') {
    if (!editing) return;
    setBusy(true);
    try {
      await api(`portal/admin/client-requests/${editing.id}/decision/`, {
        method: 'POST',
        body: JSON.stringify({
          decision,
          title: editing.title,
          description: editing.description,
          location: editing.location,
          position: editing.position,
          starts_at: editing.starts_at ? new Date(editing.starts_at).toISOString() : null,
          ends_at: editing.ends_at ? new Date(editing.ends_at).toISOString() : null,
          requested_staff: editing.requested_staff,
        }),
      });
      setEditing(undefined);
      setMessage(decision === 'approve' ? 'Anfrage bestätigt und als OpenShift veröffentlicht.' : 'Anfrage abgelehnt.');
      await load();
    } catch (error: any) {
      setMessage(error?.message || 'Entscheidung konnte nicht gespeichert werden.');
    } finally {
      setBusy(false);
    }
  }

  async function decideShiftRequest(row: any, decision: 'approve' | 'reject') {
    setBusy(true);
    try {
      await api(`portal/admin/shift-change-requests/${row.id}/decision/`, { method: 'POST', body: JSON.stringify({ decision }) });
      setMessage(decision === 'approve' ? 'Schichtanfrage genehmigt und angewendet.' : 'Schichtanfrage abgelehnt.');
      await load();
    } catch (error: any) {
      setMessage(error?.message || 'Entscheidung konnte nicht gespeichert werden.');
    } finally {
      setBusy(false);
    }
  }

  if (!mount) return null;
  return createPortal(<>
    <section className="client-admin-request-panel">
      <header><div><small>KUNDENPORTAL</small><b>Offene Kundenanfragen</b></div><span>{pendingCount}</span></header>
      {message ? <div className="client-v4-message" style={{ margin: 10 }}>{message}</div> : null}
      {busy && !pendingCount ? <div className="client-v4-loading"><IonSpinner/> Lädt …</div> : null}
      {(orders.pending || []).map((row: any) => <div className="client-admin-request-row" key={row.id}>
        <div><b><IonIcon icon={briefcaseOutline}/> {row.client_name} · {row.created_by_name}</b><span>{dateTime(row.starts_at)} – {dateTime(row.ends_at)} · {row.location_name || 'Ort offen'}</span><small>{row.requested_staff} Mitarbeiter · {row.description || 'Keine Notiz'} · eingereicht {dateTime(row.created_at)}</small></div>
        <div className="client-admin-request-actions"><button className="primary" type="button" onClick={() => openOrder(row)}><IonIcon icon={createOutline}/> Prüfen / bearbeiten</button></div>
      </div>)}
      {(shiftRequests.pending || []).map((row: any) => <div className="client-admin-request-row" key={row.id}>
        <div><b><IonIcon icon={calendarOutline}/> {row.request_type === 'cancel' ? 'Stornierung' : 'Zeitänderung'} · {row.client_name}</b><span>{row.requested_by_name} · {row.requested_by_email} · {dateTime(row.created_at)}</span><small>{row.shift.location_name} · bisher {dateTime(row.original_snapshot?.starts_at)}{row.requested_starts_at ? ` → neu ${dateTime(row.requested_starts_at)} – ${dateTime(row.requested_ends_at)}` : ''}{row.note ? ` · ${row.note}` : ''}</small></div>
        <div className="client-admin-request-actions"><button className="primary" disabled={busy} type="button" onClick={() => void decideShiftRequest(row, 'approve')}><IonIcon icon={checkmarkCircleOutline}/> Genehmigen</button><button className="danger" disabled={busy} type="button" onClick={() => void decideShiftRequest(row, 'reject')}>Ablehnen</button></div>
      </div>)}
      {!busy && !pendingCount ? <div className="client-v4-empty">Keine offenen Kundenanfragen.</div> : null}
      {(shiftRequests.history || []).length ? <details style={{ borderTop: '1px solid #edf1f3' }}><summary style={{ padding: '11px 13px', fontSize: 10, fontWeight: 800, color: '#607988' }}>Schichtanfragen · Verlauf</summary>{shiftRequests.history.slice(0, 20).map((row: any) => <div className="client-admin-request-row" key={row.id}><div><b>{row.status === 'approved' ? '✓ Genehmigt' : '✕ Abgelehnt'} · {row.requested_by_name}</b><span>{row.requested_by_email} · angefragt {dateTime(row.created_at)} · entschieden {dateTime(row.decided_at)}</span><small>{row.shift.location_name} · {row.request_type === 'cancel' ? 'Stornierung' : 'Zeitänderung'}</small></div></div>)}</details> : null}
    </section>

    {editing ? <AdminModal title="Kundenanfrage prüfen" close={() => setEditing(undefined)} footer={<div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}><button className="client-v4-save danger" disabled={busy} type="button" onClick={() => void decideOrder('reject')}>Ablehnen</button><button className="client-v4-save" disabled={busy} type="button" onClick={() => void decideOrder('approve')}>Freigeben & veröffentlichen</button></div>}>
      <div className="client-v4-form">
        <div className="client-v4-lock-card"><IonIcon icon={personOutline}/><div><b>{editing.client_name}</b><small>{editing.created_by_name} · {editing.created_by_email} · {dateTime(editing.created_at)}</small></div></div>
        <label><span>Titel</span><input value={editing.title || ''} onChange={(event) => setEditing({ ...editing, title: event.target.value })}/></label>
        <label><span>Einsatzort</span><select value={editing.location || ''} onChange={(event) => setEditing({ ...editing, location: event.target.value })}><option value="">Bitte auswählen …</option>{relevantLocations.map((item: any) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label><span>Funktion</span><select value={editing.position || ''} onChange={(event) => setEditing({ ...editing, position: event.target.value })}><option value="">Bitte auswählen …</option>{(orders.positions || []).map((item: any) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label><span>Beginn</span><input type="datetime-local" value={editing.starts_at || ''} onChange={(event) => setEditing({ ...editing, starts_at: event.target.value })}/></label>
        <label><span>Ende</span><input type="datetime-local" value={editing.ends_at || ''} onChange={(event) => setEditing({ ...editing, ends_at: event.target.value })}/></label>
        <label><span>Anzahl Mitarbeiter</span><input type="number" min="1" value={editing.requested_staff || 1} onChange={(event) => setEditing({ ...editing, requested_staff: event.target.value })}/></label>
        <label><span>Notiz</span><textarea rows={7} value={editing.description || ''} onChange={(event) => setEditing({ ...editing, description: event.target.value })}/></label>
      </div>
      {message ? <div className="client-v4-message">{message}</div> : null}
    </AdminModal> : null}
  </>, mount);
}
