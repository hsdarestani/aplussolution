import React, { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { api } from './api';
import './payroll-workspace.css';

type PayrollRow = {
  id: string;
  worker_id: string;
  employee_name: string;
  year_month: string;
  ist_hours: string;
  soll_hours: string;
  difference_hours: string;
  carryover_previous: string;
  paid_hours: string;
  manual_adjustment: string;
  saldo_cumulative: string;
  hourly_rate: string;
  gross_amount: string;
  source: string;
};

type Draft = { paid_hours: string; manual_adjustment: string };

const number = (value: unknown) => {
  const parsed = Number(String(value ?? '0').replace(',', '.'));
  return Number.isFinite(parsed) ? parsed : 0;
};

const decimal = (value: unknown) => number(value).toLocaleString('de-DE', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const money = (value: unknown) => number(value).toLocaleString('de-DE', {
  style: 'currency',
  currency: 'EUR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const monthLabel = (value: string) => {
  const [year, month] = value.split('-').map(Number);
  if (!year || !month) return value;
  return new Intl.DateTimeFormat('de-DE', { month: 'short', year: 'numeric' })
    .format(new Date(year, month - 1, 1));
};

export default function PayrollWorkspaceEnhancer() {
  const [target, setTarget] = useState<Element | null>(null);
  const [rows, setRows] = useState<PayrollRow[]>([]);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [month, setMonth] = useState('all');
  const [busyId, setBusyId] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    const locate = () => setTarget(document.querySelector('[data-testid="working-time-panel"]'));
    locate();
    const observer = new MutationObserver(locate);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  async function loadRows() {
    setLoading(true);
    setMessage('');
    try {
      const response: any = await api('working-time/records/');
      const nextRows = (response?.results || response || []) as PayrollRow[];
      setRows(nextRows);
      setDrafts(Object.fromEntries(nextRows.map((row) => [row.id, {
        paid_hours: row.paid_hours,
        manual_adjustment: row.manual_adjustment,
      }])));
    } catch (error: any) {
      setMessage(error?.message || 'Arbeitszeitkonto konnte nicht geladen werden.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (target) void loadRows();
  }, [target]);

  const months = useMemo(
    () => Array.from(new Set(rows.map((row) => row.year_month))).sort().reverse(),
    [rows],
  );

  const visibleRows = useMemo(
    () => rows.filter((row) => month === 'all' || row.year_month === month),
    [rows, month],
  );

  const latestMonth = months[0];
  const latestRows = rows.filter((row) => row.year_month === latestMonth);
  const summary = {
    ist: latestRows.reduce((sum, row) => sum + number(row.ist_hours), 0),
    soll: latestRows.reduce((sum, row) => sum + number(row.soll_hours), 0),
    saldo: latestRows.reduce((sum, row) => sum + number(row.saldo_cumulative), 0),
    gross: latestRows.reduce((sum, row) => sum + number(row.gross_amount), 0),
  };

  async function saveRow(row: PayrollRow) {
    const draft = drafts[row.id] || { paid_hours: row.paid_hours, manual_adjustment: row.manual_adjustment };
    setBusyId(row.id);
    setMessage('');
    try {
      await api(`working-time/records/${row.id}/`, {
        method: 'PATCH',
        body: JSON.stringify({
          paid_hours: draft.paid_hours,
          manual_adjustment: draft.manual_adjustment,
        }),
      });
      await loadRows();
      setMessage('Auszahlung/Korrektur gespeichert. Folgemonate wurden neu berechnet.');
    } catch (error: any) {
      setMessage(error?.message || 'Änderung konnte nicht gespeichert werden.');
    } finally {
      setBusyId('');
    }
  }

  if (!target) return null;

  return createPortal(
    <div className="payroll-workspace" data-testid="payroll-workspace">
      <div className="payroll-workspace-head">
        <div>
          <small>LOHNVORBEREITUNG</small>
          <h4>Monatskonten & Brutto</h4>
          <p>Nur freigegebene Zeiteinträge fließen in IST und Brutto ein. Der Stundensatz enthält die hinterlegte übertarifliche Zulage.</p>
        </div>
        <div className="payroll-workspace-controls">
          <label>
            Monat
            <select aria-label="Arbeitszeitkonto Monat" value={month} onChange={(event) => setMonth(event.target.value)}>
              <option value="all">Alle Monate</option>
              {months.map((item) => <option key={item} value={item}>{monthLabel(item)}</option>)}
            </select>
          </label>
          <button type="button" onClick={() => void loadRows()} disabled={loading}>
            {loading ? 'Lädt …' : 'Aktualisieren'}
          </button>
        </div>
      </div>

      {!!latestMonth && (
        <div className="payroll-summary" aria-label={`Lohnübersicht ${monthLabel(latestMonth)}`}>
          <div><span>IST</span><strong>{decimal(summary.ist)} Std.</strong></div>
          <div><span>SOLL</span><strong>{decimal(summary.soll)} Std.</strong></div>
          <div><span>Saldo</span><strong className={summary.saldo < 0 ? 'negative' : 'positive'}>{decimal(summary.saldo)} Std.</strong></div>
          <div><span>Brutto vorbereitet</span><strong>{money(summary.gross)}</strong></div>
        </div>
      )}

      {message && <div className="payroll-message" role="status">{message}</div>}

      <div className="payroll-table-wrap">
        <table className="payroll-table">
          <thead>
            <tr>
              <th>Mitarbeiter</th>
              <th>Monat</th>
              <th>IST</th>
              <th>SOLL</th>
              <th>Δ</th>
              <th>Übertrag</th>
              <th>Auszahlung</th>
              <th>Korrektur</th>
              <th>Saldo</th>
              <th>Stundensatz inkl. Zulage</th>
              <th>Brutto</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row) => {
              const draft = drafts[row.id] || { paid_hours: row.paid_hours, manual_adjustment: row.manual_adjustment };
              return (
                <tr key={row.id}>
                  <td><b>{row.employee_name}</b></td>
                  <td>{monthLabel(row.year_month)}</td>
                  <td>{decimal(row.ist_hours)}</td>
                  <td>{decimal(row.soll_hours)}</td>
                  <td className={number(row.difference_hours) < 0 ? 'negative' : 'positive'}>{decimal(row.difference_hours)}</td>
                  <td>{decimal(row.carryover_previous)}</td>
                  <td>
                    <input
                      aria-label={`Auszahlung ${row.employee_name} ${row.year_month}`}
                      type="number"
                      min="0"
                      step="0.25"
                      value={draft.paid_hours}
                      onChange={(event) => setDrafts({ ...drafts, [row.id]: { ...draft, paid_hours: event.target.value } })}
                    />
                  </td>
                  <td>
                    <input
                      aria-label={`Korrektur ${row.employee_name} ${row.year_month}`}
                      type="number"
                      step="0.25"
                      value={draft.manual_adjustment}
                      onChange={(event) => setDrafts({ ...drafts, [row.id]: { ...draft, manual_adjustment: event.target.value } })}
                    />
                  </td>
                  <td className={number(row.saldo_cumulative) < 0 ? 'negative' : 'positive'}><b>{decimal(row.saldo_cumulative)}</b></td>
                  <td>{money(row.hourly_rate)}</td>
                  <td><b>{money(row.gross_amount)}</b></td>
                  <td>
                    <button type="button" onClick={() => void saveRow(row)} disabled={busyId === row.id}>
                      {busyId === row.id ? 'Speichert …' : 'Speichern'}
                    </button>
                  </td>
                </tr>
              );
            })}
            {!visibleRows.length && !loading && (
              <tr><td colSpan={12} className="payroll-empty">Noch keine Monatsdaten. Zuerst Arbeitszeit synchronisieren.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="payroll-footnote">Lohnvorbereitung, nicht Steuer-/Sozialversicherungsabrechnung. Netto wird aus der hochgeladenen Lohnabrechnung übernommen.</p>
    </div>,
    target,
  );
}
