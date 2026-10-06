import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { api, apiBlob } from './api';
import { BUSINESS_TIME_ZONE } from './berlinLocale';
import './payroll-workspace.css';

type LexwareSupplement = {
  label?: string;
  hours?: string;
  hourly_rate?: string;
  percent?: string;
  amount?: string;
};

type PayrollStatement = {
  id: string;
  gross_amount?: string | null;
  net_amount?: string | null;
  transferred_amount?: string | null;
  payment_date?: string | null;
  source?: string;
  source_reference?: string;
  document_url?: string;
  lexware_compensation_type?: string;
  lexware_paid_hours?: string | null;
  lexware_hourly_rate?: string | null;
  lexware_monthly_salary?: string | null;
  lexware_payout_amount?: string | null;
  lexware_personal_number?: string;
  lexware_supplements?: LexwareSupplement[];
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
  clock_out_rollover_corrected?: boolean;
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
type EmployeeOption = { worker_id: string; employee_name: string };
type SettingRow = EmployeeOption & {
  employment_type?: string;
  monthly_limit: string;
  hourly_rate: string;
  night_surcharge_percent: string;
  saturday_surcharge_percent: string;
  sunday_surcharge_percent: string;
  active?: boolean;
  excluded?: boolean;
  notes?: string;
};

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

function triggerBlobDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export default function PayrollWorkspaceEnhancer({ standalone = false }: { standalone?: boolean }) {
  const [target, setTarget] = useState<Element | null>(null);
  const [rows, setRows] = useState<PayrollRow[]>([]);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [details, setDetails] = useState<Record<string, PayrollRow>>({});
  const [settingsRows, setSettingsRows] = useState<SettingRow[]>([]);
  const [month, setMonth] = useState('all');
  const [selectedWorkerId, setSelectedWorkerId] = useState('');
  const [employeeOptions, setEmployeeOptions] = useState<EmployeeOption[]>([]);
  const [expandedId, setExpandedId] = useState('');
  const [busyId, setBusyId] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [emptyReason, setEmptyReason] = useState('');
  const [lexwarePeriod, setLexwarePeriod] = useState(currentMonth());
  const [lexwareFiles, setLexwareFiles] = useState<File[]>([]);
  const [lexwareBusy, setLexwareBusy] = useState(false);
  const [historyBusy, setHistoryBusy] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsBusy, setSettingsBusy] = useState(false);
  const autoBuildAttempted = useRef(false);

  useEffect(() => {
    if (standalone) return;
    const locate = () => setTarget(document.querySelector('[data-testid="working-time-panel"]'));
    locate();
    const observer = new MutationObserver(locate);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [standalone]);

  async function fetchWorkspaceData() {
    const [response, settingsResponse]: any[] = await Promise.all([
      api('working-time/records/'),
      api('working-time/settings/'),
    ]);
    return { response, settingsResponse };
  }

  function applyWorkspaceData(response: any, settingsResponse: any) {
    const nextRows = (response?.results || response || []) as PayrollRow[];
    const configuredSettings = Array.isArray(settingsResponse?.employees)
      ? settingsResponse.employees.map((item: any) => ({
          worker_id: String(item.worker_id || ''),
          employee_name: String(item.employee_name || ''),
          employment_type: item.employment_type,
          monthly_limit: String(item.monthly_limit ?? '0'),
          hourly_rate: String(item.hourly_rate ?? '0'),
          night_surcharge_percent: String(item.night_surcharge_percent ?? '0'),
          saturday_surcharge_percent: String(item.saturday_surcharge_percent ?? '0'),
          sunday_surcharge_percent: String(item.sunday_surcharge_percent ?? '0'),
          active: item.active,
          excluded: item.excluded,
          notes: item.notes,
        })).filter((item: SettingRow) => item.worker_id && item.employee_name)
      : [];
    const rowEmployees = nextRows.map(item => ({ worker_id: item.worker_id, employee_name: item.employee_name }));
    const uniqueEmployees = Array.from(
      new Map([...configuredSettings, ...rowEmployees].map(item => [item.worker_id, { worker_id: item.worker_id, employee_name: item.employee_name }])).values(),
    ).sort((a, b) => a.employee_name.localeCompare(b.employee_name, 'de'));

    setRows(nextRows);
    setEmployeeOptions(uniqueEmployees);
    setSettingsRows(configuredSettings);
    setDrafts(Object.fromEntries(nextRows.map(row => [row.id, {
      paid_total_hours: row.paid_total_hours ?? row.soll_hours,
      manual_adjustment: row.manual_adjustment,
    }])));
  }

  async function loadRows(autoBuild = false) {
    setLoading(true);
    setMessage('');
    setEmptyReason('');
    try {
      let { response, settingsResponse } = await fetchWorkspaceData();
      let nextRows = (response?.results || response || []) as PayrollRow[];

      if (standalone && autoBuild && !nextRows.length && !autoBuildAttempted.current) {
        autoBuildAttempted.current = true;
        setMessage('Arbeitszeitdaten werden aus den vorhandenen Ist Zeiten aufgebaut.');
        const rebuilt: any = await api('working-time/rebuild-all/', { method: 'POST', body: '{}' });
        if (!rebuilt?.records_count) {
          setEmptyReason(rebuilt?.detail || 'Es wurden keine abgeschlossenen oder freigegebenen Ist Zeiten gefunden.');
        }
        ({ response, settingsResponse } = await fetchWorkspaceData());
        nextRows = (response?.results || response || []) as PayrollRow[];
      }

      applyWorkspaceData(response, settingsResponse);
      if (nextRows.length) setMessage('');
    } catch (error: any) {
      setMessage(error?.message || 'Arbeitszeitkonto konnte nicht geladen werden.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (standalone || target) void loadRows(standalone);
  }, [standalone, target]);

  const workerRows = useMemo(
    () => selectedWorkerId ? rows.filter(row => row.worker_id === selectedWorkerId) : rows,
    [rows, selectedWorkerId],
  );
  const months = useMemo(() => Array.from(new Set(workerRows.map(row => row.year_month))).sort().reverse(), [workerRows]);
  const visibleRows = useMemo(() => workerRows.filter(row => month === 'all' || !month || row.year_month === month), [workerRows, month]);
  const summaryRows = useMemo(() => {
    if (month && month !== 'all') return workerRows.filter(row => row.year_month === month);
    if (selectedWorkerId) return workerRows;
    const newest = months[0];
    return newest ? rows.filter(row => row.year_month === newest) : [];
  }, [rows, workerRows, selectedWorkerId, month, months]);

  useEffect(() => {
    if (month === 'all' || !month || months.includes(month)) return;
    setMonth('all');
  }, [selectedWorkerId, months, month]);

  useEffect(() => {
    if (month && month !== 'all') setLexwarePeriod(month);
  }, [month]);

  const selectedEmployee = employeeOptions.find(item => item.worker_id === selectedWorkerId);
  const selectedSetting = settingsRows.find(item => item.worker_id === selectedWorkerId);
  const summary = {
    ist: summaryRows.reduce((sum, row) => sum + number(row.ist_hours), 0),
    paid: summaryRows.reduce((sum, row) => sum + number(row.paid_total_hours ?? row.soll_hours), 0),
    saldo: selectedWorkerId && month === 'all'
      ? number(workerRows[0]?.saldo_cumulative)
      : summaryRows.reduce((sum, row) => sum + number(row.monthly_balance_hours ?? row.saldo_cumulative), 0),
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
      setMessage('Auszahlung und Korrektur gespeichert. Die Folgemonate wurden neu berechnet.');
    } catch (error: any) {
      setMessage(error?.message || 'Änderung konnte nicht gespeichert werden.');
    } finally {
      setBusyId('');
    }
  }

  async function rebuildHistory() {
    setHistoryBusy(true);
    setMessage('');
    setEmptyReason('');
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

  async function saveSelectedSettings() {
    if (!selectedSetting) {
      setMessage('Bitte zuerst einen Mitarbeiter auswählen.');
      return;
    }
    setSettingsBusy(true);
    setMessage('');
    try {
      await api('working-time/settings/', {
        method: 'POST',
        body: JSON.stringify({ employees: [selectedSetting] }),
      });
      await loadRows();
      setMessage('Stundensatz, Sollstunden und Zuschläge wurden gespeichert.');
    } catch (error: any) {
      setMessage(error?.message || 'Einstellungen konnten nicht gespeichert werden.');
    } finally {
      setSettingsBusy(false);
    }
  }

  function updateSelectedSetting(key: keyof SettingRow, value: string) {
    if (!selectedWorkerId) return;
    setSettingsRows(current => current.map(item => item.worker_id === selectedWorkerId ? { ...item, [key]: value } : item));
  }

  async function downloadExport(format: 'xlsx' | 'csv') {
    setBusyId(`export:${format}`);
    setMessage('');
    try {
      const query = selectedWorkerId ? `?worker=${encodeURIComponent(selectedWorkerId)}` : '';
      const result = await apiBlob(`working-time/export/${format}/${query}`);
      triggerBlobDownload(result.blob, result.filename || `arbeitszeit-lohnkonto.${format}`);
    } catch (error: any) {
      setMessage(error?.message || 'Export konnte nicht erstellt werden.');
    } finally {
      setBusyId('');
    }
  }

  async function downloadPayrollPdf(row: PayrollRow) {
    setBusyId(`pdf:${row.worker_id}`);
    setMessage('');
    try {
      const result = await apiBlob(`working-time/pdf/${row.worker_id}/`);
      triggerBlobDownload(result.blob, result.filename || `Arbeitszeitkonto_${row.employee_number || row.worker_id}.pdf`);
    } catch (error: any) {
      setMessage(error?.message || 'PDF konnte nicht erstellt werden.');
    } finally {
      setBusyId('');
    }
  }

  async function importLexware() {
    if (!lexwareFiles.length || !lexwarePeriod) {
      setMessage('Bitte Abrechnungsmonat und mindestens eine Lexware Datei auswählen.');
      return;
    }
    setLexwareBusy(true);
    setMessage('');
    try {
      const form = new FormData();
      form.append('period', lexwarePeriod);
      lexwareFiles.forEach(file => form.append('files', file));
      const result: any = await api('working-time/lexware-import/', { method: 'POST', body: form });
      await loadRows();
      setMessage(`Lexware Import abgeschlossen. ${result?.files || lexwareFiles.length} Datei(en), ${result?.employees?.length || 0} Mitarbeiter zugeordnet, ${result?.unmatched_count || 0} nicht zugeordnet.`);
      setLexwareFiles([]);
    } catch (error: any) {
      setMessage(error?.message || 'Lexware Import konnte nicht verarbeitet werden.');
    } finally {
      setLexwareBusy(false);
    }
  }

  const workspace = (
    <div className={`payroll-workspace ${standalone ? 'payroll-standalone' : ''}`} data-testid="payroll-workspace">
      {standalone && <header className="payroll-page-hero">
        <div>
          <span className="payroll-kicker">A+ SOLUTION · ABRECHNUNG</span>
          <h2>Arbeitszeit &amp; Lohnkonto</h2>
          <p>Ein Mitarbeiter. Eine nachvollziehbare Monatsakte. Ist Zeiten, Dienstplan und tatsächliche Zahlung bleiben getrennt und trotzdem direkt vergleichbar.</p>
        </div>
        <div className="payroll-hero-actions">
          <button type="button" className="payroll-secondary" onClick={() => void downloadExport('xlsx')} disabled={busyId === 'export:xlsx'}>Excel</button>
          <button type="button" className="payroll-secondary" onClick={() => void downloadExport('csv')} disabled={busyId === 'export:csv'}>CSV</button>
          <button type="button" onClick={() => setSettingsOpen(value => !value)}>{settingsOpen ? 'Stammdaten schließen' : 'Stammdaten'}</button>
        </div>
      </header>}

      <section className="payroll-filter-deck">
        <div className="payroll-filter-main">
          <label>Mitarbeiter
            <select aria-label="Mitarbeiter auswählen" value={selectedWorkerId} onChange={event => { setSelectedWorkerId(event.target.value); setExpandedId(''); }}>
              <option value="">Alle Mitarbeiter</option>
              {employeeOptions.map(item => <option key={item.worker_id} value={item.worker_id}>{item.employee_name}</option>)}
            </select>
          </label>
          <label>Monat
            <select aria-label="Arbeitszeitkonto Monat" value={month} onChange={event => { setMonth(event.target.value); setExpandedId(''); }}>
              <option value="all">Alle Monate</option>
              {months.map(item => <option key={item} value={item}>{monthLabel(item)}</option>)}
            </select>
          </label>
          <button type="button" className="payroll-refresh" onClick={() => void loadRows()} disabled={loading}>{loading ? 'Wird geladen' : 'Aktualisieren'}</button>
        </div>
        <div className="payroll-filter-context">
          <span>{selectedEmployee?.employee_name || 'Gesamte Belegschaft'}</span>
          <b>{visibleRows.length} Monatskonten</b>
          <small>{month === 'all' ? 'Gesamter verfügbarer Zeitraum' : monthLabel(month)}</small>
        </div>
      </section>

      <section className="payroll-evidence-grid" aria-label="Drei Nachweise">
        <article><span>01</span><div><b>Ist Arbeitszeit</b><small>Beginn, Ende, Pause und Kunde aus der tatsächlichen Zeiterfassung.</small></div></article>
        <article><span>02</span><div><b>Dienstplan</b><small>Der geplante Einsatz bleibt als Vergleich sichtbar und verändert die Ist Stunden nicht.</small></div></article>
        <article><span>03</span><div><b>Zahlung</b><small>Bezahlte Stunden und Lexware Bankbetrag werden separat dokumentiert.</small></div></article>
      </section>

      <section className="payroll-summary" aria-label="Lohnübersicht">
        <div><span>Gearbeitet</span><strong>{decimal(summary.ist)} Std.</strong><small>Ist Zeit</small></div>
        <div><span>Bezahlt</span><strong>{decimal(summary.paid)} Std.</strong><small>bestätigte Stunden</small></div>
        <div><span>Saldo</span><strong className={summary.saldo < 0 ? 'negative' : 'positive'}>{decimal(summary.saldo)} Std.</strong><small>offenes Zeitkonto</small></div>
        <div><span>Brutto vorbereitet</span><strong>{money(summary.gross)}</strong><small>inklusive Zuschläge</small></div>
        <div><span>Lexware Auszahlung</span><strong>{money(summary.transferred)}</strong><small>Zahlungsliste oder Bankexport</small></div>
      </section>

      {settingsOpen && <section className="payroll-settings-panel">
        <div className="payroll-section-title">
          <div><span>STAMMDATEN</span><h3>Vertrag und Zuschläge</h3></div>
          <p>{selectedSetting ? selectedSetting.employee_name : 'Für die Bearbeitung bitte einen Mitarbeiter auswählen.'}</p>
        </div>
        {selectedSetting && <div className="payroll-settings-grid">
          <label>Sollstunden pro Monat<input type="number" step="0.25" value={selectedSetting.monthly_limit} onChange={event => updateSelectedSetting('monthly_limit', event.target.value)} /></label>
          <label>Stundensatz<input type="number" step="0.01" value={selectedSetting.hourly_rate} onChange={event => updateSelectedSetting('hourly_rate', event.target.value)} /></label>
          <label>Nacht Zuschlag %<input type="number" step="0.01" value={selectedSetting.night_surcharge_percent} onChange={event => updateSelectedSetting('night_surcharge_percent', event.target.value)} /></label>
          <label>Samstag Zuschlag %<input type="number" step="0.01" value={selectedSetting.saturday_surcharge_percent} onChange={event => updateSelectedSetting('saturday_surcharge_percent', event.target.value)} /></label>
          <label>Sonntag Zuschlag %<input type="number" step="0.01" value={selectedSetting.sunday_surcharge_percent} onChange={event => updateSelectedSetting('sunday_surcharge_percent', event.target.value)} /></label>
          <button type="button" onClick={() => void saveSelectedSettings()} disabled={settingsBusy}>{settingsBusy ? 'Speichert' : 'Stammdaten speichern'}</button>
        </div>}
      </section>}

      <section className="payroll-tool-row">
        <div className="payroll-tool-card">
          <span className="payroll-tool-index">A</span>
          <div><b>Historie neu berechnen</b><small>Alle vorhandenen echten Arbeitszeiten werden vom ersten Arbeitsmonat bis heute neu aufgebaut.</small></div>
          <button type="button" onClick={() => void rebuildHistory()} disabled={historyBusy}>{historyBusy ? 'Berechnet' : 'Neu berechnen'}</button>
        </div>
        <div className="payroll-tool-card payroll-lexware-card">
          <span className="payroll-tool-index">L</span>
          <div><b>Lexware übernehmen</b><small>Lohnabrechnungen PDF, Zahlungsliste PDF oder CSV/ZIP gemeinsam importieren.</small></div>
          <div className="payroll-lexware-fields">
            <input aria-label="Lexware Abrechnungsmonat" type="month" value={lexwarePeriod} onChange={event => setLexwarePeriod(event.target.value)} />
            <input aria-label="Lexware Dateien" type="file" multiple accept=".pdf,.csv,.zip,application/pdf,text/csv,application/zip" onChange={event => setLexwareFiles(Array.from(event.target.files || []))} />
            <button type="button" onClick={() => void importLexware()} disabled={lexwareBusy || !lexwareFiles.length}>{lexwareBusy ? 'Importiert' : `Übernehmen${lexwareFiles.length ? ` (${lexwareFiles.length})` : ''}`}</button>
          </div>
        </div>
      </section>

      {message && <div className="payroll-message" role="status">{message}</div>}

      <div className="payroll-record-list" data-testid="payroll-record-list">
        {visibleRows.map(row => {
          const draft = drafts[row.id] || { paid_total_hours: row.paid_total_hours ?? row.soll_hours, manual_adjustment: row.manual_adjustment };
          const expanded = expandedId === row.id;
          const detail = details[row.id];
          const statement = row.payroll_statement;
          return <article className={`payroll-record-card ${expanded ? 'is-expanded' : ''}`} key={row.id}>
            <header>
              <div className="payroll-record-month"><span>{monthLabel(row.year_month)}</span><small>{employmentLabel(row.employment_type)}</small></div>
              <div className="payroll-record-person">
                <strong>{row.employee_name}</strong>
                <span>{row.employee_number || 'Ohne Personalnummer'}</span>
              </div>
              <div className="payroll-record-gross">
                <small>{statement?.source === 'lexware_bank_export' ? 'Lexware überwiesen' : 'Lexware Zahlungsliste'}</small>
                <b>{statement?.transferred_amount ? money(statement.transferred_amount) : 'Noch nicht importiert'}</b>
              </div>
            </header>

            {row.minijob_warning && <div className="payroll-warning">Prüfung nötig: Grundbrutto liegt über {money(row.minijob_limit)}. Die Minijob Einstufung wird nicht automatisch geändert.</div>}

            <div className="payroll-metrics">
              <div><span>IST</span><b>{decimal(row.ist_hours)} Std.</b></div>
              <div><span>Bezahlt</span><b>{decimal(row.paid_total_hours ?? row.soll_hours)} Std.</b></div>
              <div><span>Monatssaldo</span><b className={number(row.monthly_balance_hours) < 0 ? 'negative' : 'positive'}>{decimal(row.monthly_balance_hours)} Std.</b></div>
              <div><span>Saldo gesamt</span><b className={number(row.saldo_cumulative) < 0 ? 'negative' : 'positive'}>{decimal(row.saldo_cumulative)} Std.</b></div>
              <div><span>Stundensatz</span><b>{money(row.hourly_rate)}</b></div>
              <div><span>Brutto</span><b>{money(row.gross_with_surcharges ?? row.gross_amount)}</b></div>
              <div><span>Nacht</span><b>{decimal(row.night_hours)} Std.</b></div>
              <div><span>Samstag</span><b>{decimal(row.saturday_hours)} Std.</b></div>
              <div><span>Sonntag</span><b>{decimal(row.sunday_hours)} Std.</b></div>
              <div><span>Zuschläge</span><b>{money(row.surcharge_amount)}</b></div>
              <div><span>Soll</span><b>{decimal(row.soll_hours)} Std.</b></div>
              <div><span>Einträge</span><b>{row.entry_count || 0}</b></div>
            </div>

            <div className="payroll-record-actions">
              <button type="button" onClick={() => void toggleRow(row)}>{expanded ? 'Details schließen' : 'Tagesnachweis öffnen'}</button>
              <button type="button" className="payroll-secondary" onClick={() => void downloadPayrollPdf(row)} disabled={busyId === `pdf:${row.worker_id}`}>{busyId === `pdf:${row.worker_id}` ? 'PDF wird erstellt' : 'PDF'}</button>
            </div>

            {expanded && <div className="payroll-card-details">
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
                <div><span>Zahlungsliste</span><b>{statement?.transferred_amount ? money(statement.transferred_amount) : 'Keine Daten'}</b></div>
                <div><span>Lexware Brutto</span><b>{statement?.gross_amount ? money(statement.gross_amount) : 'Keine Daten'}</b></div>
                <div><span>Lexware Netto</span><b>{statement?.net_amount ? money(statement.net_amount) : 'Keine Daten'}</b></div>
                <div><span>Auszahlungsbetrag</span><b>{statement?.lexware_payout_amount ? money(statement.lexware_payout_amount) : 'Keine Daten'}</b></div>
                <div><span>Abrechnungsart</span><b>{
                  statement?.lexware_compensation_type === 'hourly'
                    ? `${decimal(statement.lexware_paid_hours)} Std. × ${money(statement.lexware_hourly_rate)}`
                    : statement?.lexware_compensation_type === 'salary'
                      ? `Gehalt ${money(statement.lexware_monthly_salary)}`
                      : 'Keine Daten'
                }</b></div>
                <div><span>Quelle</span><b>{
                  statement?.source === 'lexware_pdf_bundle' ? 'Lexware PDFs'
                  : statement?.source === 'lexware_payslip_pdf' ? 'Lohnabrechnung PDF'
                  : statement?.source === 'lexware_zahlungsliste_pdf' ? 'Zahlungsliste PDF'
                  : statement?.source === 'lexware_bank_export' ? 'Lexware Bankexport'
                  : statement?.source || 'Keine Daten'
                }</b></div>
              </div>
              {statement?.lexware_compensation_type === 'salary' && <div className="payroll-lexware-note">
                Lexware weist hier ein festes Gehalt aus, keine bezahlten Stunden. Stunden werden deshalb nicht aus dem Geldbetrag geschätzt.
              </div>}
              {!!statement?.lexware_supplements?.length && <div className="payroll-lexware-supplements">
                {statement.lexware_supplements.map((item, index) => <span key={index}>{item.label}: {decimal(item.hours)} Std. · {decimal(item.percent)}% · {money(item.amount)}</span>)}
              </div>}

              <div className="payroll-daily">
                <div className="payroll-daily-head"><div><span>TAGESNACHWEIS</span><b>Plan und Ist nebeneinander</b></div><small>{detail?.entries?.length ?? row.entry_count ?? 0} Einträge</small></div>
                {!detail && <div className="payroll-detail-loading">Tagesdetails werden geladen.</div>}
                {!!detail?.entries?.length && <div className="payroll-daily-table" role="table" aria-label={`Tagesnachweis ${row.employee_name} ${row.year_month}`}>
                  <div className="payroll-daily-row payroll-daily-header" role="row">
                    <span>Datum</span><span>Kunde</span><span>Plan</span><span>Ist</span><span>Pause</span><span>Netto</span><span>Nacht</span><span>Sa</span><span>So</span>
                  </div>
                  {detail.entries.map(entry => <div className="payroll-daily-row" role="row" key={entry.id}>
                    <span>{dateLabel(entry.local_clock_in)}</span>
                    <span>{entry.client_name || 'Ohne Zuordnung'}<small>{entry.location_name || entry.position_name || ''}</small></span>
                    <span>{timeLabel(entry.planned_start)} bis {timeLabel(entry.planned_end)}</span>
                    <span>{timeLabel(entry.local_clock_in)} bis {timeLabel(entry.local_clock_out)}{entry.clock_out_rollover_corrected ? <small>Datumswechsel korrigiert</small> : null}</span>
                    <span>{entry.break_minutes || 0} Min.</span>
                    <span>{hoursFromMinutes(entry.worked_minutes)} Std.</span>
                    <span>{hoursFromMinutes(entry.night_minutes)}</span>
                    <span>{hoursFromMinutes(entry.saturday_minutes)}</span>
                    <span>{hoursFromMinutes(entry.sunday_minutes)}</span>
                  </div>)}
                </div>}
                {detail && !detail.entries?.length && <div className="payroll-empty compact">Keine Tageszeiten in diesem Monat.</div>}
              </div>
            </div>}
          </article>;
        })}

        {!visibleRows.length && !loading && <section className="payroll-empty-state">
          <span className="payroll-empty-mark">A+</span>
          <div>
            <small>NOCH KEIN MONATSKONTO</small>
            <h3>{selectedEmployee ? `Für ${selectedEmployee.employee_name} sind noch keine Monatsdaten vorhanden.` : 'Es sind noch keine Monatsdaten vorhanden.'}</h3>
            <p>{emptyReason || 'Die Seite hat den automatischen Aufbau bereits geprüft. Falls neue Ist Zeiten freigegeben wurden, kannst du die Historie erneut berechnen.'}</p>
          </div>
          <button type="button" onClick={() => void rebuildHistory()} disabled={historyBusy}>{historyBusy ? 'Wird geprüft' : 'Historie prüfen'}</button>
        </section>}
      </div>

      <footer className="payroll-footnote">Der Saldo basiert auf tatsächlichen Ist Stunden, bestätigten bezahlten Stunden und manuellen Korrekturen. Sollstunden bleiben ein Vertragsvergleich. Ein Lexware Bankbetrag wird nicht automatisch in Stunden umgerechnet.</footer>
    </div>
  );

  if (standalone) return workspace;
  if (!target) return null;
  return createPortal(workspace, target);
}
