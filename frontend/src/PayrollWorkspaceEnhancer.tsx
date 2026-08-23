import React, { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { api } from './api';
import { BUSINESS_TIME_ZONE } from './berlinLocale';
import './payroll-workspace.css';

type PayrollRow = {
  id: string; worker_id: string; employee_name: string; year_month: string; ist_hours: string; soll_hours: string;
  difference_hours: string; carryover_previous: string; paid_hours: string; manual_adjustment: string; saldo_cumulative: string;
  hourly_rate: string; gross_amount: string; source: string;
};
type Draft = { paid_hours: string; manual_adjustment: string };
const number = (value: unknown) => { const parsed = Number(String(value ?? '0').replace(',', '.')); return Number.isFinite(parsed) ? parsed : 0; };
const decimal = (value: unknown) => number(value).toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const money = (value: unknown) => number(value).toLocaleString('de-DE', { style: 'currency', currency: 'EUR', minimumFractionDigits: 2, maximumFractionDigits: 2 });
const monthLabel = (value: string) => {
  const [year, month] = value.split('-').map(Number); if (!year || !month) return value;
  return new Intl.DateTimeFormat('de-DE', { timeZone: BUSINESS_TIME_ZONE, month: 'short', year: 'numeric' }).format(new Date(Date.UTC(year, month - 1, 1, 12)));
};

export default function PayrollWorkspaceEnhancer() {
  const [target, setTarget] = useState<Element | null>(null);
  const [rows, setRows] = useState<PayrollRow[]>([]);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [month, setMonth] = useState('');
  const [employeeQuery, setEmployeeQuery] = useState('');
  const [expandedId, setExpandedId] = useState('');
  const [busyId, setBusyId] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => { const locate = () => setTarget(document.querySelector('[data-testid="working-time-panel"]')); locate(); const observer = new MutationObserver(locate); observer.observe(document.body, { childList: true, subtree: true }); return () => observer.disconnect(); }, []);

  async function loadRows() {
    setLoading(true); setMessage('');
    try {
      const response: any = await api('working-time/records/');
      const nextRows = (response?.results || response || []) as PayrollRow[];
      setRows(nextRows);
      setDrafts(Object.fromEntries(nextRows.map(row => [row.id, { paid_hours: row.paid_hours, manual_adjustment: row.manual_adjustment }])));
      const newestMonth = Array.from(new Set(nextRows.map(row => row.year_month))).sort().reverse()[0];
      setMonth(current => current || newestMonth || 'all');
    } catch (error: any) { setMessage(error?.message || 'Arbeitszeitkonto konnte nicht geladen werden.'); }
    finally { setLoading(false); }
  }
  useEffect(() => { if (target) void loadRows(); }, [target]);

  const months = useMemo(() => Array.from(new Set(rows.map(row => row.year_month))).sort().reverse(), [rows]);
  const visibleRows = useMemo(() => {
    const query = employeeQuery.trim().toLocaleLowerCase('de-DE');
    return rows.filter(row => (month === 'all' || !month || row.year_month === month) && (!query || row.employee_name.toLocaleLowerCase('de-DE').includes(query)));
  }, [rows, month, employeeQuery]);
  const latestMonth = months[0]; const latestRows = rows.filter(row => row.year_month === latestMonth);
  const summary = { ist: latestRows.reduce((s,r)=>s+number(r.ist_hours),0), soll: latestRows.reduce((s,r)=>s+number(r.soll_hours),0), saldo: latestRows.reduce((s,r)=>s+number(r.saldo_cumulative),0), gross: latestRows.reduce((s,r)=>s+number(r.gross_amount),0) };

  async function saveRow(row: PayrollRow) {
    const draft = drafts[row.id] || { paid_hours: row.paid_hours, manual_adjustment: row.manual_adjustment };
    setBusyId(row.id); setMessage('');
    try {
      await api(`working-time/records/${row.id}/`, { method: 'PATCH', body: JSON.stringify({ paid_hours: draft.paid_hours, manual_adjustment: draft.manual_adjustment }) });
      await loadRows(); setMessage('Auszahlung/Korrektur gespeichert. Folgemonate wurden neu berechnet.');
    } catch (error: any) { setMessage(error?.message || 'Änderung konnte nicht gespeichert werden.'); }
    finally { setBusyId(''); }
  }

  if (!target) return null;
  return createPortal(<div className="payroll-workspace" data-testid="payroll-workspace">
    <div className="payroll-workspace-head"><div><small>LOHNVORBEREITUNG</small><h4>Monatskonten & Brutto</h4><p>Nur freigegebene Zeiteinträge fließen in IST und Brutto ein. Der Stundensatz enthält die hinterlegte übertarifliche Zulage.</p></div><div className="payroll-workspace-controls"><label>Monat<select aria-label="Arbeitszeitkonto Monat" value={month} onChange={e=>{setMonth(e.target.value);setExpandedId('');}}><option value="all">Alle Monate</option>{months.map(item=><option key={item} value={item}>{monthLabel(item)}</option>)}</select></label><label className="payroll-employee-filter">Mitarbeiter<input aria-label="Mitarbeiter suchen" type="search" placeholder="Name suchen" value={employeeQuery} onChange={e=>{setEmployeeQuery(e.target.value);setExpandedId('');}} /></label><button type="button" onClick={()=>void loadRows()} disabled={loading}>{loading?'Lädt …':'Aktualisieren'}</button></div></div>
    {!!latestMonth&&<div className="payroll-summary" aria-label={`Lohnübersicht ${monthLabel(latestMonth)}`}><div><span>IST</span><strong>{decimal(summary.ist)} Std.</strong></div><div><span>SOLL</span><strong>{decimal(summary.soll)} Std.</strong></div><div><span>Saldo</span><strong className={summary.saldo<0?'negative':'positive'}>{decimal(summary.saldo)} Std.</strong></div><div><span>Brutto vorbereitet</span><strong>{money(summary.gross)}</strong></div></div>}
    {message&&<div className="payroll-message" role="status">{message}</div>}
    <div className="payroll-list-meta"><span>{visibleRows.length} Datensätze</span>{month!=='all'&&month&&<b>{monthLabel(month)}</b>}</div>
    <div className="payroll-record-list" data-testid="payroll-record-list">
      {visibleRows.map(row=>{const draft=drafts[row.id]||{paid_hours:row.paid_hours,manual_adjustment:row.manual_adjustment};const expanded=expandedId===row.id;return <article className={`payroll-record-card ${expanded?'is-expanded':''}`} key={row.id}>
        <header><div className="payroll-record-person"><strong>{row.employee_name}</strong><span>{monthLabel(row.year_month)}</span></div><div className="payroll-record-gross"><small>Brutto vorbereitet</small><b>{money(row.gross_amount)}</b></div></header>
        <div className="payroll-mobile-summary" aria-label={`Kurzinfo ${row.employee_name}`}><div><span>IST</span><b>{decimal(row.ist_hours)}</b></div><div><span>SOLL</span><b>{decimal(row.soll_hours)}</b></div><div><span>Saldo</span><b className={number(row.saldo_cumulative)<0?'negative':'positive'}>{decimal(row.saldo_cumulative)}</b></div></div>
        <button className="payroll-card-toggle" type="button" aria-expanded={expanded} onClick={()=>setExpandedId(expanded?'':row.id)}>{expanded?'Weniger anzeigen':'Details & Bearbeiten'}</button>
        <div className="payroll-card-details">
          <div className="payroll-metrics">
            <div><span>IST</span><b>{decimal(row.ist_hours)} Std.</b></div><div><span>SOLL</span><b>{decimal(row.soll_hours)} Std.</b></div><div><span>Δ</span><b className={number(row.difference_hours)<0?'negative':'positive'}>{decimal(row.difference_hours)} Std.</b></div><div><span>Übertrag</span><b>{decimal(row.carryover_previous)} Std.</b></div><div><span>Saldo</span><b className={number(row.saldo_cumulative)<0?'negative':'positive'}>{decimal(row.saldo_cumulative)} Std.</b></div><div><span>Stundensatz inkl. Zulage</span><b>{money(row.hourly_rate)}</b></div>
          </div>
          <div className="payroll-edit-row"><label>Auszahlung (Std.)<input aria-label={`Auszahlung ${row.employee_name} ${row.year_month}`} type="number" min="0" step="0.25" value={draft.paid_hours} onChange={e=>setDrafts({...drafts,[row.id]:{...draft,paid_hours:e.target.value}})}/></label><label>Korrektur (Std.)<input aria-label={`Korrektur ${row.employee_name} ${row.year_month}`} type="number" step="0.25" value={draft.manual_adjustment} onChange={e=>setDrafts({...drafts,[row.id]:{...draft,manual_adjustment:e.target.value}})}/></label><button type="button" onClick={()=>void saveRow(row)} disabled={busyId===row.id}>{busyId===row.id?'Speichert …':'Speichern'}</button></div>
        </div>
      </article>;})}
      {!visibleRows.length&&!loading&&<div className="payroll-empty">Keine passenden Monatsdaten gefunden.</div>}
    </div>
    <p className="payroll-footnote">Auszahlung/Korrektur werden in Stunden geführt. Lohnvorbereitung, nicht Steuer-/Sozialversicherungsabrechnung. Netto wird aus der hochgeladenen Lohnabrechnung übernommen.</p>
  </div>, target);
}
