import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { api } from './api';
import './shift-release-approval-panel.css';

const unpack = (value: any): any[] => value?.results || value || [];
const fmt = (input: string) => new Date(input).toLocaleString('de-DE', {
  timeZone: 'Europe/Berlin',
  weekday: 'short',
  day: '2-digit',
  month: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
});

export default function ShiftReleaseApprovalPanel() {
  const [active, setActive] = useState(false);
  const [manager, setManager] = useState(false);
  const [rows, setRows] = useState<any[]>([]);
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState('');

  useEffect(() => {
    const root = document.getElementById('root');
    const sync = () => setActive(Boolean(document.querySelector('.mobile-first-app-shell-v1[data-view="operations"]')));
    sync();
    const observer = new MutationObserver(sync);
    if (root) observer.observe(root, { subtree: true, childList: true, attributes: true, attributeFilter: ['data-view'] });
    return () => observer.disconnect();
  }, []);

  const load = async () => {
    try {
      const data = await api('premium/release-requests/');
      setRows(unpack(data));
    } catch (error: any) {
      setMessage(error?.message || 'Schichtfreigaben konnten nicht geladen werden.');
    }
  };

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    void api('auth/me/').then((me: any) => {
      const allowed = ['admin', 'manager'].includes(me?.role);
      if (cancelled) return;
      setManager(allowed);
      if (allowed) void load();
    }).catch(() => setManager(false));
    return () => { cancelled = true; };
  }, [active]);

  async function decide(row: any, status: 'approved' | 'rejected') {
    setBusy(row.id);
    setMessage('');
    try {
      const result: any = await api(`premium/release-requests/${row.id}/decide/`, { method: 'POST', body: JSON.stringify({ status }) });
      if (status === 'approved') {
        setMessage(result?.transferred_to
          ? `Schicht wurde an ${row.requested_worker} übertragen.`
          : 'Schicht wurde freigegeben und wieder als OpenShift verfügbar.');
      } else {
        setMessage('Freigabe wurde abgelehnt; die Schicht bleibt zugewiesen.');
      }
      await load();
    } catch (error: any) {
      setMessage(error?.message || 'Entscheidung konnte nicht gespeichert werden.');
    } finally {
      setBusy('');
    }
  }

  if (!active || !manager) return null;
  const host = document.querySelector('.app-main') || document.body;

  return createPortal(
    <section className="shift-release-approval-panel" data-testid="shift-release-approvals">
      <header>
        <div><small>SCHICHTFREIGABEN</small><h2>Freigabe durch Administration</h2><p>Mitarbeiter können angenommene Schichten nicht selbst zurückgeben. Hier wird jede Anfrage bestätigt oder abgelehnt.</p></div>
        <b>{rows.length}</b>
      </header>
      {rows.map((row) => <div className="shift-release-approval-row" key={row.id}>
        <div>
          <strong>{row.worker}</strong>
          <span>{fmt(row.starts_at)} · {row.client || 'A+ Solution'} · {row.position} · {row.location}</span>
          <span><b>Gewünschte Übernahme:</b> {row.requested_worker || 'Kein Mitarbeiter ausgewählt – als OpenShift freigeben'}</span>
        </div>
        <div className="shift-release-approval-actions">
          <button type="button" className="approve" disabled={busy === row.id} onClick={() => void decide(row, 'approved')}>Genehmigen</button>
          <button type="button" disabled={busy === row.id} onClick={() => void decide(row, 'rejected')}>Ablehnen</button>
        </div>
      </div>)}
      {!rows.length && <div className="shift-release-empty">Keine offenen Schichtfreigaben.</div>}
      {message && <div className="shift-release-message">{message}</div>}
    </section>,
    host,
  );
}
