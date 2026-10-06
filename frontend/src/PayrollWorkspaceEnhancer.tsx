import React, { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { api, apiBlob } from './api';
import { BUSINESS_TIME_ZONE } from './berlinLocale';
import './payroll-workspace.css';

type PayrollStatement = {
  id: string;
  gross_amount?: string | null;
  net_amount?: string | null;
  transferred_amount?: string | null;
  payment_date?: string | null;
  source?: string;
  source_reference?: string;
  document_url?: string;
};

type PayrollEntry = {
  id: string;
  client_name?: string;
  location_name?: string;
  position_name?: string;
  planned_start?: string | null;
  planned_end?: string | null;
  planned_break_minutes?: number;
  local_clock_in?: string;
  local_clock_out?: string;
  break_minutes?: number;
  worked_minutes?: number;
  night_minutes?: number;
  saturday_minutes?: number;
  sunday_minutes?: number;
  source?: string;
};

type PayrollRow = {
  id: string;
  worker_id: string;
  employee_name: string;
  employee_number?: string;
  employment_type?: string;
  year_month: string;
  ist_hours: string;
  soll_hours: string;
  difference_hours: string;
  carryover_previous: string;
  paid_hours: string;
  paid_base_hours?: string;
  paid_total_hours?: string;
  monthly_balance_hours?: string;
  manual_adjustment: string;
  saldo_cumulative: string;
  hourly_rate: string;
  gross_amount: string;
  gross_with_surcharges?: string;
  night_hours?: string;
  saturday_hours?: string;
  sunday_hours?: string;
  surcharge_amount?: string;
  entry_count?: number;
  minijob_limit?: string | null;
  minijob_warning?: boolean;
  payroll_statement?: PayrollStatement | null;
  source: string;
  entries?: PayrollEntry[];
};

type Draft = { paid_total_hours: string; manual_adjustment: string };

const number = (value: unknown) => {
  const parsed = Number(String(value ?? '0').replace(',', '.'));
  return Number.isFinite(parsed) ? parsed : 0;
};
const decimal = (value: unknown) => number(value).toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const money = (value: unknown) => number(value).toLocaleString('de-DE', { style: 'currency', currency: 'EUR', minimumFractionDigits: 2, maximumFractionDigits: 2 });
const monthLabel = (value: string) => {
  const [year, month] = value.split('-').map(Number);
  if (!year || !month) return value;
  return new Intl.DateTimeFormat('de-DE', { timeZone: BUSINESS_TIME_ZONE, month: 'long', year: 'numeric' }).format(new Date(Date.UTC(year, month - 1, 1, 12)));
};
const employmentLabel = (value?: string) => value === 'minijob' ? 'Minijob' : value === 'teilzeit' ? 'Teilzeit' : value === 'vollzeit' ? 'Vollzeit' : value === 'student' ? 'Studentische Aushilfe' : 'Beschäftigung';
const dateLabel = (value?: string | null) => value ? new Date(value).toLocaleDateString('de-DE', { timeZone: BUSINESS_TIME_ZONE }) : 'Keine Angabe';
const timeLabel = (value?: string | null) => value ? new Date(value).toLocaleTimeString('de-DE', { timeZone: BUSINESS_TIME_ZONE, hour: '2-digit', minute: '2-digit' }) : 'Keine Angabe';
const hoursFromMinutes = (value?: number) => decimal(number(value) / 60);
const currentMonth = () => {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: BUSINESS_TIME_ZONE, year: 'numeric', month: '2-digit' }).formatToParts(new Date());
  const year = parts.find(part => part.type === 'year')?.value || '';
  const month = parts.find(part => part.type === 'month')?.value || '';
  return year && month ? `${year}-${month}` : '';
};

export default function PayrollWorkspaceEnhancer() {
  const [target, setTarget] = useState<Element | null>(null);
  const [rows, setRows] = useState<PayrollRow[]>([]);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [details, setDetails] = useState<Record<string, PayrollRow>>({});
  const [month, setMonth] = useState('');
  const [employeeQuery, setEmployeeQuery] = useState('');
  const [expandedId, setExpandedId] = useState('');
  const [busyId, setBusyId] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [lexwarePeriod, setLexwarePeriod] = useState(currentMonth());
  const [lexwareFile, setLexwareFile] = useState<File | null>(null);
  const [lexwareBusy, setLexwareBusy] = useState(false);
  const [historyBusy, setHistoryBusy] = useState(false);

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
      setDrafts(Object.fromEntries(nextRows.map(row => [row.id, { paid_total_hours: row.paid_total_hours ?? row.soll_hours, manual_adjustment: row.manual_adjustment }])));
      const newestMonth = Array.from(new Set(nextRows.map(row => row.year_month))).sort().reverse()[0];
      setMonth(current => current || newestMonth || 'all');
    } catch (error: any) {
      setMessage(error?.message || 'Arbeitszeitkonto konnte nicht geladen werden.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (target) void loadRows();
  }, [target]);

  const months = useMemo(() => Array.from(new Set(rows.map(row => row.year_month))).sort().reverse(), [rows]);
  const visibleRows = useMemo(() => {
    const query = employeeQuery.trim().toLocaleLowerCase('de-DE');
    return rows.filter(row =>
      (month === 'all' || !month || row.year_month === month)
      && (!query || row.employee_name.toLocaleLowerCase('de-DE').includes(query))
    );
  }, [rows, month, employeeQuery]);

  const summaryRows = useMemo(() => {
    if (month && month !== 'all') return rows.filter(row => row.year_month === month);
    const newest = months[0];
    return newest ? rows.filter(row => row.year_month === newest) : [];
  }, [rows, month, months]);

  const summary = {
    ist: summaryRows.reduce((sum, row) => sum + number(row.ist_hours), 0),
    paid: summaryRows.reduce((sum, row) => sum + number(row.paid_total_hours ?? row.soll_hours), 0),
    saldo: summaryRows.reduce((sum, row) => sum + number(row.saldo_cumulative), 0),
    gross: summaryRows.reduce((sum, row) => sum + number(row.gross_with_surcharges ?? row.gross_amount), 0),
    transferred: summaryRows.reduce((sum, row) => sum + number(row.payroll_statement?.transferred_amount), 0),
  };

  async function loadDetail(row: PayrollRow) {
    if (details[row.id]) return;
    try {
      const result: any = await api(`working-time/records/${row.id}/details/`);
      setDetails(current => ({ ...current, [row.id]: result as PayrollRow }));
    } catch (error: any) {
      setMessage(error?.message || 'Tagesdetails konnten nicht geladen werden.');
    }
  }

  async function toggleRow(row: PayrollRow) {
    const expanded = expandedId === row.id;
    setExpandedId(expanded ? '' : row.id);
    if (!expanded) await loadDetail(row);
  }

  async function saveRow(row: PayrollRow) {
    const draft = drafts[row.id] || { paid_total_hours: row.paid_total_hours ?? row.soll_hours, manual_adjustment: row.manual_adjustment };
    setBusyId(row.id);
    setMessage('');
    try {
      await api(`working-time/records/${row.id}/`, {
        method: 'PATCH',
        body: JSON.stringify({ paid_total_hours: draft.paid_total_hours, manual_adjustment: draft.manual_adjustment }),
      });
      setDetails(current => {
        const next = { ...current };
        delete next[row.id];
        return next;
      });
      await loadRows();
      setMessage('Auszahlung und Korrektur gespeichert. Alle Folgemonate wurden neu berechnet.');
    } catch (error: any) {
      setMessage(error?.message || 'Änderung konnte nicht gespeichert werden.');
    } finally {
      setBusyId('');
    }
  }

  async function rebuildHistory() {
    setHistoryBusy(true);
    setMessage('');
    try {
      const result: any = await api('working-time/rebuild-all/', { method: 'POST', body: '{}' });
      setDetails({});
      await loadRows();
      setMessage(result?.records_count
        ? `Gesamthistorie ab ${dateLabel(result.start)} neu berechnet. ${result.records_count} Monatskonten aktualisiert.`
        : result?.detail || 'Keine Arbeitszeiten zum Neuaufbau gefunden.');
    } catch (error: any) {
      setMessage(error?.message || 'Gesamthistorie konnte nicht neu berechnet werden.');
    } finally {
      setHistoryBusy(false);
    }
  }

  async function downloadPayrollPdf(row: PayrollRow) {
    setBusyId(`pdf:${row.worker_id}`);
    setMessage('');
    try {
      const result = await apiBlob(`working-time/pdf/${row.worker_id}/`);
      const url = URL.createObjectURL(result.blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = result.filename || `Arbeitszeitkonto_${row.employee_number || row.worker_id}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error: any) {
      setMessage(error?.message || 'PDF konnte nicht erstellt werden.');
    } finally {
      setBusyId('');
    }
  }

  async function importLexware() {
    if (!lexwareFile || !lexwarePeriod) {
      setMessage('Bitte Abrechnungsmonat und Lexware Datei auswählen.');
      return;
    }
    setLexwareBusy(true);
    setMessage('');
    try {
      const form = new FormData();
      form.append('period', lexwarePeriod);
      form.append('file', lexwareFile);
      const result: any = await api('working-time/lexware-import/', { method: 'POST', body: form });
      await loadRows();
      setMessage(`Lexware Import abgeschlossen. ${result?.employees?.length || 0} Mitarbeiter zugeordnet. ${result?.unmatched_count || 0} Zeilen nicht zugeordnet.`);
      setLexwareFile(null);
    } catch (error: any) {
      setMessage(error?.message || 'Lexware Import konnte nicht verarbeitet werden.');
    } finally {
      setLexwareBusy(false);
    }
  }

  if (!target) return null;

  return createPortal(
    <div className="payroll-workspace" data-testid="payroll-workspace">
      <div className="payroll-workspace-head">
        <div>
          <small>ARBEITSZEIT UND LOHNKONTO</small>
          <h4>Monatskonto mit Tagesnachweis</h4>
          <p>IST kommt ausschließlich aus tatsächlichen Arbeitszeiten. Dienstplanzeiten werden nur zum Vergleich gezeigt. Auszahlung, Lexware Zahlung und Zeitkonto bleiben getrennte Nachweise.</p>
        </div>
        <div className="payroll-workspace-controls">
          <label>Monat
            <select aria-label="Arbeitszeitkonto Monat" value={month} onChange={event => { setMonth(event.target.value); setExpandedId(''); }}>
              <option value="all">Alle Monate</option>
              {months.map(item => <option key={item} value={item}>{monthLabel(item)}</option>)}
            </select>
          </label>
          <label className="payroll-employee-filter">Mitarbeiter
            <input aria-label="Mitarbeiter suchen" type="search" placeholder="Name suchen" value={employeeQuery} onChange={event => { setEmployeeQuery(event.target.value); setExpandedId(''); }} />
          </label>
          <button type="button" onClick={() => void loadRows()} disabled={loading}>{loading ? 'Lädt' : 'Aktualisieren'}</button>
        </div>
      </div>

      <div className="payroll-summary" aria-label="Lohnübersicht">
        <div><span>Gearbeitet</span><strong>{decimal(summary.ist)} Std.</strong></div>
        <div><span>Bezahlt</span><strong>{decimal(summary.paid)} Std.</strong></div>
        <div><span>Saldo</span><strong className={summary.saldo < 0 ? 'negative' : 'positive'}>{decimal(summary.saldo)} Std.</strong></div>
        <div><span>Brutto vorbereitet</span><strong>{money(summary.gross)}</strong></div>
        <div><span>Lexware überwiesen</span><strong>{money(summary.transferred)}</strong></div>
      </div>

      <div className="payroll-audit-tools">
        <div>
          <b>Gesamthistorie</b>
          <span>Vom ersten echten Arbeitsmonat bis heute neu berechnen.</span>
          <button type="button" onClick={() => void rebuildHistory()} disabled={historyBusy}>{historyBusy ? 'Berechnet' : 'Gesamthistorie neu berechnen'}</button>
        </div>
        <div>
          <b>Lexware Import einmalig</b>
          <span>Bankexport als CSV oder ZIP. Der gewählte Monat ist der Abrechnungsmonat.</span>
          <div className="payroll-lexware-fields">
            <input aria-label="Lexware Abrechnungsmonat" type="month" value={lexwarePeriod} onChange={event => setLexwarePeriod(event.target.value)} />
            <input aria-label="Lexware Datei" type="file" accept=".csv,.zip,text/csv,application/zip" onChange={event => setLexwareFile(event.target.files?.[0] || null)} />
            <button type="button" onClick={() => void importLexware()} disabled={lexwareBusy || !lexwareFile}>{lexwareBusy ? 'Importiert' : 'Lexware übernehmen'}</button>
          </div>
        </div>
      </div>

      {message && <div className="payroll-message" role="status">{message}</div>}

      <div className="payroll-list-meta">
        <span>{visibleRows.length} Monatskonten</span>
        {month !== 'all' && month && <b>{monthLabel(month)}</b>}
      </div>

      <div className="payroll-record-list" data-testid="payroll-record-list">
        {visibleRows.map(row => {
          const draft = drafts[row.id] || { paid_total_hours: row.paid_total_hours ?? row.soll_hours, manual_adjustment: row.manual_adjustment };
          const expanded = expandedId === row.id;
          const detail = details[row.id];
          const statement = row.payroll_statement;
          return <article className={`payroll-record-card ${expanded ? 'is-expanded' : ''}`} key={row.id}>
            <header>
              <div className="payroll-record-person">
                <strong>{row.employee_name}</strong>
                <span>{employmentLabel(row.employment_type)} · {monthLabel(row.year_month)}</span>
              </div>
              <div className="payroll-record-gross">
                <small>Lexware überwiesen</small>
                <b>{statement?.transferred_amount ? money(statement.transferred_amount) : 'Noch nicht importiert'}</b>
              </div>
            </header>

            {row.minijob_warning && <div className="payroll-warning">Prüfung nötig: Grundbrutto liegt über {money(row.minijob_limit)}. Die Minijob Einstufung wird nicht automatisch geändert.</div>}

            <div className="payroll-mobile-summary" aria-label={`Kurzinfo ${row.employee_name}`}>
              <div><span>IST</span><b>{decimal(row.ist_hours)}</b></div>
              <div><span>Bezahlt</span><b>{decimal(row.paid_total_hours ?? row.soll_hours)}</b></div>
              <div><span>Saldo</span><b className={number(row.saldo_cumulative) < 0 ? 'negative' : 'positive'}>{decimal(row.saldo_cumulative)}</b></div>
            </div>

            <button className="payroll-card-toggle" type="button" aria-expanded={expanded} onClick={() => void toggleRow(row)}>{expanded ? 'Weniger anzeigen' : 'Tagesdetails und Bearbeitung'}</button>

            <div className="payroll-card-details">
              <div className="payroll-metrics">
                <div><span>Gearbeitet</span><b>{decimal(row.ist_hours)} Std.</b></div>
                <div><span>Bezahlt gesamt</span><b>{decimal(row.paid_total_hours ?? row.soll_hours)} Std.</b></div>
                <div><span>Monatssaldo</span><b className={number(row.monthly_balance_hours) < 0 ? 'negative' : 'positive'}>{decimal(row.monthly_balance_hours)} Std.</b></div>
                <div><span>Saldo kumuliert</span><b className={number(row.saldo_cumulative) < 0 ? 'negative' : 'positive'}>{decimal(row.saldo_cumulative)} Std.</b></div>
                <div><span>Stundensatz</span><b>{money(row.hourly_rate)}</b></div>
                <div><span>Brutto mit Zuschlägen</span><b>{money(row.gross_with_surcharges ?? row.gross_amount)}</b></div>
                <div><span>Nacht</span><b>{decimal(row.night_hours)} Std.</b></div>
                <div><span>Samstag</span><b>{decimal(row.saturday_hours)} Std.</b></div>
                <div><span>Sonntag</span><b>{decimal(row.sunday_hours)} Std.</b></div>
                <div><span>Zuschläge</span><b>{money(row.surcharge_amount)}</b></div>
                <div><span>Soll</span><b>{decimal(row.soll_hours)} Std.</b></div>
                <div><span>Offene Stunden im Monat</span><b className={number(row.monthly_balance_hours) < 0 ? 'negative' : 'positive'}>{decimal(row.monthly_balance_hours)} Std.</b></div>
              </div>

              <div className="payroll-edit-row">
                <label>Bezahlte Stunden gesamt
                  <input aria-label={`Bezahlte Stunden ${row.employee_name} ${row.year_month}`} type="number" min="0" step="0.25" value={draft.paid_total_hours} onChange={event => setDrafts({ ...drafts, [row.id]: { ...draft, paid_total_hours: event.target.value } })} />
                </label>
                <label>Korrektur Stunden
                  <input aria-label={`Korrektur ${row.employee_name} ${row.year_month}`} type="number" step="0.25" value={draft.manual_adjustment} onChange={event => setDrafts({ ...drafts, [row.id]: { ...draft, manual_adjustment: event.target.value } })} />
                </label>
                <button type="button" onClick={() => void saveRow(row)} disabled={busyId === row.id}>{busyId === row.id ? 'Speichert' : 'Speichern'}</button>
              </div>

              <div className="payroll-payment-strip">
                <div><span>Lexware Betrag</span><b>{statement?.transferred_amount ? money(statement.transferred_amount) : 'Keine Daten'}</b></div>
                <div><span>Zahlungsdatum</span><b>{statement?.payment_date ? dateLabel(statement.payment_date) : 'Keine Daten'}</b></div>
                <div><span>Quelle</span><b>{statement?.source === 'lexware_bank_export' ? 'Lexware Bankexport' : statement?.source || 'Keine Daten'}</b></div>
              </div>

              <div className="payroll-document-actions">
                <button type="button" onClick={() => void downloadPayrollPdf(row)} disabled={busyId === `pdf:${row.worker_id}`}>
                  {busyId === `pdf:${row.worker_id}` ? 'PDF wird erstellt' : 'PDF Arbeitszeitkonto'}
                </button>
                <span>Enthält Monatsübersicht und Tagesnachweis mit Kunde, Plan, Ist, Pause, Nacht, Samstag und Sonntag.</span>
              </div>

              <div className="payroll-daily">
                <div className="payroll-daily-head"><b>Tagesnachweis</b><span>{detail?.entries?.length ?? row.entry_count ?? 0} Einträge</span></div>
                {!detail && <div className="payroll-detail-loading">Tagesdetails werden geladen.</div>}
                {!!detail?.entries?.length && <div className="payroll-daily-table" role="table" aria-label={`Tagesnachweis ${row.employee_name} ${row.year_month}`}>
                  <div className="payroll-daily-row payroll-daily-header" role="row">
                    <span>Datum</span><span>Kunde</span><span>Plan</span><span>Ist</span><span>Pause</span><span>Netto</span><span>Nacht</span><span>Sa</span><span>So</span>
                  </div>
                  {detail.entries.map(entry => <div className="payroll-daily-row" role="row" key={entry.id}>
                    <span>{dateLabel(entry.local_clock_in)}</span>
                    <span>{entry.client_name || 'Ohne Zuordnung'}<small>{entry.location_name || entry.position_name || ''}</small></span>
                    <span>{timeLabel(entry.planned_start)} bis {timeLabel(entry.planned_end)}</span>
                    <span>{timeLabel(entry.local_clock_in)} bis {timeLabel(entry.local_clock_out)}</span>
                    <span>{entry.break_minutes || 0} Min.</span>
                    <span>{hoursFromMinutes(entry.worked_minutes)} Std.</span>
                    <span>{hoursFromMinutes(entry.night_minutes)}</span>
                    <span>{hoursFromMinutes(entry.saturday_minutes)}</span>
                    <span>{hoursFromMinutes(entry.sunday_minutes)}</span>
                  </div>)}
                </div>}
                {detail && !detail.entries?.length && <div className="payroll-empty">Keine Tageszeiten in diesem Monat.</div>}
              </div>
            </div>
          </article>;
        })}
        {!visibleRows.length && !loading && <div className="payroll-empty">Keine passenden Monatsdaten gefunden.</div>}
      </div>

      <p className="payroll-footnote">Saldo wird aus tatsächlich gearbeiteten Stunden minus tatsächlich bezahlten Stunden berechnet. SOLL bleibt ein separater Vertragsvergleich. Der Lexware Betrag ist der importierte Bankabfluss und wird nicht automatisch in Stunden umgerechnet.</p>
    </div>,
    target,
  );
}
