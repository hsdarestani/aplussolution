import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { api } from './api';
import './admin-schedule-tools.css';

const BERLIN = 'Europe/Berlin';
const unpack = (value: any): any[] => value?.results || value || [];

type Card = { key: string; shift: any; slot?: any; worker?: any; open: boolean };

function formatWindow(shift: any) {
  const start = new Date(shift.starts_at);
  const end = new Date(shift.ends_at);
  const day = new Intl.DateTimeFormat('de-DE', { timeZone: BERLIN, weekday: 'short', day: '2-digit', month: '2-digit', year: 'numeric' }).format(start);
  const time = (value: Date) => new Intl.DateTimeFormat('de-DE', { timeZone: BERLIN, hour: '2-digit', minute: '2-digit' }).format(value);
  return `${day} · ${time(start)}–${time(end)}`;
}

function cardsForShift(shift: any): Card[] {
  if (Array.isArray(shift.slot_cards) && shift.slot_cards.length) {
    return shift.slot_cards
      .filter((slot: any) => slot.status !== 'cancelled')
      .map((slot: any) => ({
        key: `${shift.id}:${slot.id}`,
        shift,
        slot,
        worker: slot.worker,
        open: Boolean(slot.is_open || (slot.status === 'open' && !slot.worker)),
      }));
  }
  const assigned = Array.isArray(shift.assigned_workers) ? shift.assigned_workers : [];
  if (assigned.length) return assigned.map((worker: any, index: number) => ({ key: `${shift.id}:legacy:${index}`, shift, worker, open: false }));
  return [{ key: `${shift.id}:legacy`, shift, open: true }];
}

export default function AdminScheduleTools() {
  const [active, setActive] = useState(false);
  const [manager, setManager] = useState(false);
  const [mobile, setMobile] = useState(() => typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches);
  const [host, setHost] = useState<Element | null>(null);
  const [createMenuOpen, setCreateMenuOpen] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);
  const [manageOpen, setManageOpen] = useState(false);
  const [orderText, setOrderText] = useState('');
  const [parsed, setParsed] = useState<any>();
  const [shifts, setShifts] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const bypassFab = useRef(false);

  useEffect(() => {
    const root = document.getElementById('root');
    const sync = () => setActive(Boolean(document.querySelector('.mobile-first-app-shell-v1[data-view="schedule"]')));
    sync();
    const observer = new MutationObserver(sync);
    if (root) observer.observe(root, { subtree: true, childList: true, attributes: true, attributeFilter: ['data-view'] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const media = window.matchMedia('(max-width: 900px)');
    const sync = () => setMobile(media.matches);
    sync();
    media.addEventListener?.('change', sync);
    return () => media.removeEventListener?.('change', sync);
  }, []);

  useEffect(() => {
    if (!active) {
      setManager(false);
      return;
    }
    let cancelled = false;
    api('auth/me/').then((user: any) => {
      if (!cancelled) setManager(['admin', 'manager'].includes(user?.role));
    }).catch(() => setManager(false));
    return () => { cancelled = true; };
  }, [active]);

  useEffect(() => {
    if (!active || !manager) {
      setHost(null);
      return;
    }
    const sync = () => {
      if (mobile) {
        setHost(document.body);
        return;
      }
      setHost(document.querySelector('.sv2 .sv2-title'));
    };
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { subtree: true, childList: true });
    return () => observer.disconnect();
  }, [active, manager, mobile]);

  // Keep the main mobile screen visually identical to WIW: one floating + button.
  // Intercept that native-looking FAB and offer our extra Manual/AI choices in a
  // compact bottom sheet. Manual then continues into the existing WIW-style form.
  useEffect(() => {
    if (!active || !manager || !mobile) return;
    const interceptFab = (event: MouseEvent) => {
      const target = event.target as Element | null;
      const fab = target?.closest?.('.wiw-create-fab');
      if (!fab) return;
      if (bypassFab.current) {
        bypassFab.current = false;
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      setCreateMenuOpen(true);
    };
    document.addEventListener('click', interceptFab, true);
    return () => document.removeEventListener('click', interceptFab, true);
  }, [active, manager, mobile]);

  const cards = useMemo(() => shifts.flatMap(cardsForShift).sort((a, b) => new Date(a.shift.starts_at).getTime() - new Date(b.shift.starts_at).getTime()), [shifts]);

  const refreshSchedule = () => {
    const mobileRefresh = document.querySelector<HTMLButtonElement>('.wiw-search-row button');
    if (mobileRefresh) mobileRefresh.click();
    const desktopRefresh = document.querySelector<HTMLButtonElement>('.sv2-search button');
    if (desktopRefresh) desktopRefresh.click();
  };

  const loadShifts = async () => {
    setBusy(true);
    try {
      const data = await api('shifts/?ordering=starts_at');
      setShifts(unpack(data));
    } catch (error: any) {
      setMessage(error.message || 'Schichten konnten nicht geladen werden.');
    } finally {
      setBusy(false);
    }
  };

  const openManage = () => {
    setCreateMenuOpen(false);
    setManageOpen(true);
    void loadShifts();
  };

  const openManual = () => {
    setCreateMenuOpen(false);
    const button = document.querySelector<HTMLButtonElement>('.wiw-create-fab');
    if (button) {
      bypassFab.current = true;
      button.click();
      window.setTimeout(() => { bypassFab.current = false; }, 250);
      return;
    }
    document.querySelector<HTMLButtonElement>('[data-testid="schedule-create-manual"]')?.click();
  };

  const openAi = () => {
    setCreateMenuOpen(false);
    setParsed(undefined);
    setOrderText('');
    setMessage('');
    setAiOpen(true);
  };

  async function parseOrder() {
    if (!orderText.trim()) {
      setMessage('Bitte zuerst den Auftragstext einfügen.');
      return;
    }
    setBusy(true);
    try {
      const result: any = await api('automation/orders/parse/', { method: 'POST', body: JSON.stringify({ text: orderText }) });
      setParsed(result);
      setMessage(`${result.shifts?.length || 0} Schicht(en) erkannt. Bitte kurz prüfen.`);
    } catch (error: any) {
      setMessage(error.message || 'AI-Analyse fehlgeschlagen.');
    } finally {
      setBusy(false);
    }
  }

  async function approveOrder() {
    if (!parsed) return void parseOrder();
    setBusy(true);
    try {
      const result: any = await api('automation/orders/approve/', { method: 'POST', body: JSON.stringify({ parsed, raw_text: orderText }) });
      setMessage(`${result.created_count || 0} Personalplatz/-plätze als OpenShift erstellt.`);
      setAiOpen(false);
      setParsed(undefined);
      setOrderText('');
      refreshSchedule();
    } catch (error: any) {
      setMessage(error.message || 'OpenShifts konnten nicht erstellt werden.');
    } finally {
      setBusy(false);
    }
  }

  async function removeCard(card: Card) {
    const who = card.worker?.name || (card.open ? 'OpenShift' : 'Schicht');
    if (!window.confirm(`${who} · ${formatWindow(card.shift)} wirklich löschen?`)) return;
    setBusy(true);
    try {
      if (card.slot?.id) {
        await api(`shifts/${card.shift.id}/cards/${card.slot.id}/delete/`, { method: 'DELETE' });
      } else {
        await api(`shifts/${card.shift.id}/`, { method: 'DELETE' });
      }
      setMessage('Schichtkarte wurde gelöscht.');
      await loadShifts();
      refreshSchedule();
    } catch (error: any) {
      setMessage(error.message || 'Schichtkarte konnte nicht gelöscht werden.');
    } finally {
      setBusy(false);
    }
  }

  if (!active || !manager || !host) return null;

  return createPortal(
    <>
      {!mobile ? <div className="admin-schedule-actions desktop"><button type="button" onClick={openManage}>Schichten verwalten</button></div> : null}

      {mobile && createMenuOpen ? createPortal(
        <div className="admin-create-menu-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setCreateMenuOpen(false); }}>
          <section className="admin-create-menu" role="dialog" aria-modal="true" aria-label="Schicht erstellen">
            <header><strong>Schicht erstellen</strong><button type="button" onClick={() => setCreateMenuOpen(false)}>Abbrechen</button></header>
            <button type="button" className="primary" onClick={openManual}><span className="menu-icon">+</span><span><b>Manuell</b><small>WIW-Formular öffnen</small></span><em>›</em></button>
            <button type="button" onClick={openAi}><span className="menu-icon">AI</span><span><b>Mit AI</b><small>Auftrag analysieren und Schichten erstellen</small></span><em>›</em></button>
            <button type="button" onClick={openManage}><span className="menu-icon">⋯</span><span><b>Schichten verwalten</b><small>Einzelne Schichtkarten verwalten oder löschen</small></span><em>›</em></button>
          </section>
        </div>, document.body,
      ) : null}

      {aiOpen ? createPortal(<div className="admin-schedule-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setAiOpen(false); }}>
        <section className="admin-schedule-sheet ai" role="dialog" aria-modal="true" aria-label="Schichten mit AI erstellen">
          <header><div><small>AI · PERSONALPLANUNG</small><h2>Schichten mit AI erstellen</h2></div><button type="button" onClick={() => setAiOpen(false)}>Fertig</button></header>
          <label>Auftragstext<textarea autoFocus value={orderText} onChange={(event) => { setOrderText(event.target.value); setParsed(undefined); }} placeholder="Kundenanfrage hier einfügen …" /></label>
          {parsed ? <div className="admin-ai-preview"><b>{parsed.shifts?.length || 0} Schicht(en) erkannt</b>{parsed.shifts?.map((item: any, index: number) => <span key={index}>{item.date} · {item.start_time}–{item.end_time} · {item.count}× {item.role} · {item.site_text}</span>)}</div> : null}
          <div className="admin-schedule-sheet-actions"><button type="button" onClick={() => setAiOpen(false)}>Abbrechen</button><button type="button" className="primary" disabled={busy} onClick={() => void (parsed ? approveOrder() : parseOrder())}>{busy ? '…' : parsed ? 'OpenShifts erstellen' : 'Mit AI analysieren'}</button></div>
          {message ? <button type="button" className="admin-schedule-message" onClick={() => setMessage('')}>{message}</button> : null}
        </section>
      </div>, document.body) : null}

      {manageOpen ? createPortal(<div className="admin-schedule-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setManageOpen(false); }}>
        <section className="admin-schedule-sheet manage" role="dialog" aria-modal="true" aria-label="Schichten verwalten">
          <header><div><small>ADMIN · DIENSTPLAN</small><h2>Schichten verwalten</h2><p>Jede Person und jeder OpenShift-Platz ist eine eigene Karte. Änderungen machst du direkt durch Antippen der Karte im Dienstplan; hier kannst du einzelne Karten löschen.</p></div><button type="button" onClick={() => setManageOpen(false)}>Fertig</button></header>
          <div className="admin-manage-toolbar"><button type="button" className="primary" onClick={() => { setManageOpen(false); openManual(); }}>+ Schicht hinzufügen</button><button type="button" disabled={busy} onClick={() => void loadShifts()}>{busy ? '…' : 'Aktualisieren'}</button></div>
          <div className="admin-shift-card-list">
            {cards.slice(0, 160).map((card) => <article key={card.key}>
              <div><b>{card.shift.position_name || 'Schicht'}</b><span>{formatWindow(card.shift)}</span><small>{card.worker?.name || (card.open ? 'OpenShift' : 'Unbesetzt')} · {card.shift.client_name || ''}{card.shift.location_name ? ` · ${card.shift.location_name}` : ''}</small></div>
              <button type="button" className="danger" disabled={busy} onClick={() => void removeCard(card)}>Löschen</button>
            </article>)}
            {!cards.length && !busy ? <div className="admin-shift-empty">Keine Schichten vorhanden.</div> : null}
          </div>
          {message ? <button type="button" className="admin-schedule-message" onClick={() => setMessage('')}>{message}</button> : null}
        </section>
      </div>, document.body) : null}
    </>,
    host,
  );
}
