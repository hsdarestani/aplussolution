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
  lexware_sick_hours?: string;
  lexware_sick_continued_pay?: string;
  lexware_u1_reimbursement?: string;
  lexware_absence_evidence?: Array<{
    absence_type?: string;
    date_from?: string;
    date_to?: string;
    absence_hours?: string;
    continued_pay?: string;
    reimbursement_amount?: string;
    reimbursement_percent?: string;
  }>;
};

type ReconciliationItem = {
  label?: string;
  status?: string;
  aplus_hours?: string;
  aplus_amount?: string;
  lexware_hours?: string | null;
  lexware_amount?: string | null;
};

type SurchargeReconciliation = {
  overall?: string;
  night?: ReconciliationItem;
  saturday?: ReconciliationItem;
  sunday?: ReconciliationItem;
  holiday?: ReconciliationItem;
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
  holiday_minutes?: number;
  holiday_details?: Array<{ date: string; name: string; minutes: number }>;
  notes?: string;
  clock_out_rollover_corrected?: boolean;
  source?: string;
};

type PayrollRow = {
  id: string;
  worker_id: string;
  employee_name: string;
  employee_number?: string;
  worker_active?: boolean;
  user_active?: boolean;
  is_synthetic?: boolean;
  employment_type?: string;
  historical_soll_unverified?: boolean;
  employment_classification_unverified?: boolean;
  year_month: string;
  ist_hours: string;
  soll_hours: string;
  difference_hours: string;
  carryover_previous: string;
  paid_hours: string;
  paid_total_hours?: string;
  balance_basis?: 'paid_hours' | 'soll_salary' | 'open_month' | string;
  balance_reference_hours?: string;
  monthly_balance_hours?: string;
  manual_adjustment: string;
  saldo_cumulative: string;
  hourly_rate: string;
  gross_amount: string;
  gross_with_surcharges?: string;
  night_hours?: string;
  saturday_hours?: string;
  sunday_hours?: string;
  holiday_hours?: string;
  holiday_surcharge_amount?: string;
  surcharge_amount?: string;
  entry_count?: number;
  absence_days?: number;
  vacation_days?: number;
  sick_days?: number;
  other_absence_days?: number;
  minijob_limit?: string | null;
  minijob_warning?: boolean;
  contract_issues?: string[];
  reconciliation_status?: string;
  is_open_month?: boolean;
  reconciliation_issues?: string[];
  surcharge_reconciliation?: SurchargeReconciliation;
  payroll_statement?: PayrollStatement | null;
  source: string;
  entries?: PayrollEntry[];
};

type LexwareReadiness = {
  year: number;
  expected_through?: string | null;
  expected_months: number;
  complete_months: number;
  parsed_complete_months?: number;
  core_documents_expected: number;
  core_documents_present: number;
  annual_complete: boolean;
  no_additional_import_required: boolean;
  missing?: Array<{ period: string; kind: string }>;
  optional_documents?: Record<string, number>;
  enrichment_needed?: boolean;
  missing_payslip_person_group?: number;
};

type HistoricLexwareRow = {
  worker_id: string;
  employee_name: string;
  employee_number: string;
  worker_active?: boolean;
  user_active?: boolean;
  is_synthetic?: boolean;
  period: string;
  gross_amount: string | null;
  net_amount: string | null;
  transferred_amount: string | null;
  historical_profile: boolean;
};

type Draft = { paid_total_hours: string; manual_adjustment: string };
type EmployeeOption = {
  worker_id: string;
  employee_name: string;
  employee_number?: string;
  worker_active?: boolean;
  user_active?: boolean;
  is_synthetic?: boolean;
  has_period_data?: boolean;
  has_payroll_history?: boolean;
};

const isTechnicalEmployee = (item: EmployeeOption) =>
  item.is_synthetic === true
  || item.employee_name.toLowerCase().endsWith('@sync.invalid')
  || item.employee_name.trim().toLowerCase() === 'store reviewer';

const isNormalEmployeeOption = (item: EmployeeOption) =>
  !isTechnicalEmployee(item)
  && (item.worker_active !== false || Boolean(item.has_period_data) || Boolean(item.has_payroll_history));

const employeeNameKey = (name: string) => name.normalize('NFKC').trim().toLocaleLowerCase('de').replace(/\\s+/g, ' ');

const mergeEmployeeOptions = (...groups: EmployeeOption[][]): EmployeeOption[] => {
  const options = new Map<string, EmployeeOption>();
  for (const item of groups.flat()) {
    if (!item.worker_id || !item.employee_name.trim()) continue;
    const previous = options.get(item.worker_id);
    options.set(item.worker_id, {
      ...previous,
      ...item,
      has_period_data: Boolean(previous?.has_period_data || item.has_period_data),
      has_payroll_history: Boolean(previous?.has_payroll_history || item.has_payroll_history),
    });
  }
  return Array.from(options.values()).sort((a, b) =>
    a.employee_name.localeCompare(b.employee_name, 'de')
    || String(a.employee_number || '').localeCompare(String(b.employee_number || ''), 'de')
    || a.worker_id.localeCompare(b.worker_id),
  );
};
type SettingRow = EmployeeOption & {
  employment_type?: string;
  monthly_limit: string;
  hourly_rate: string;
  night_surcharge_percent: string;
  saturday_surcharge_percent: string;
  sunday_surcharge_percent: string;
  holiday_surcharge_percent: string;
  active?: boolean;
  excluded?: boolean;
  notes?: string;
};

const number = (value: unknown) => {
  const parsed = Number(String(value ?? '0').replace(',', '.'));
  return Number.isFinite(parsed) ? parsed : 0;
};
const decimal = (value: unknown) => number(value).toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const signedDecimal = (value: unknown) => number(value).toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: 'always' });
const money = (value: unknown) => number(value).toLocaleString('de-DE', { style: 'currency', currency: 'EUR', minimumFractionDigits: 2, maximumFractionDigits: 2 });
const monthLabel = (value: string) => {
  const [year, month] = value.split('-').map(Number);
  if (!year || !month) return value;
  return new Intl.DateTimeFormat('de-DE', { timeZone: BUSINESS_TIME_ZONE, month: 'long', year: 'numeric' }).format(new Date(Date.UTC(year, month - 1, 1, 12)));
};
const employmentLabel = (value?: string) => value === 'historisch' ? 'Historisch (Lohnart unbekannt)' : value === 'ungeklaert' ? 'Ungeklärt' : value === 'minijob' ? 'Minijob' : value === 'teilzeit' ? 'Teilzeit' : value === 'vollzeit' ? 'Vollzeit' : value === 'student' ? 'Studentische Aushilfe' : value === 'geschaeftsfuehrer' ? 'Geschäftsführer' : 'Beschäftigung';
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
  const [historicalPayrollRows, setHistoricalPayrollRows] = useState<HistoricLexwareRow[]>([]);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [details, setDetails] = useState<Record<string, PayrollRow>>({});
  const [settingsRows, setSettingsRows] = useState<SettingRow[]>([]);
  const [month, setMonth] = useState('all');
  const [selectedYear, setSelectedYear] = useState(() => Number(currentMonth().slice(0, 4)) || new Date().getFullYear());
  const [selectedWorkerId, setSelectedWorkerId] = useState('');
  const [employeeOptions, setEmployeeOptions] = useState<EmployeeOption[]>([]);
  const [showHistoricalProfiles, setShowHistoricalProfiles] = useState(false);
  const [expandedId, setExpandedId] = useState('');
  const [busyId, setBusyId] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [emptyReason, setEmptyReason] = useState('');
  const [lexwarePeriod, setLexwarePeriod] = useState(currentMonth());
  const [lexwareFiles, setLexwareFiles] = useState<File[]>([]);
  const [lexwareBusy, setLexwareBusy] = useState(false);
  const [unmatchedBusy, setUnmatchedBusy] = useState(false);
  const [unmatchedReport, setUnmatchedReport] = useState<{ period: string; unmatched_unique_count: number; unmatched_rows: number; evidence_files: number; unmatched: Array<{ employee_name: string; rows: number; sources: string[] }>; errors: Array<{ file: string; reason: string }> } | null>(null);
  const [masterDataFile, setMasterDataFile] = useState<File | null>(null);
  const [masterDataBusy, setMasterDataBusy] = useState(false);
  const [historyBusy, setHistoryBusy] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [dataCareOpen, setDataCareOpen] = useState(false);
  const [settingsBusy, setSettingsBusy] = useState(false);
  const [lexwareReadiness, setLexwareReadiness] = useState<LexwareReadiness | null>(null);
  const autoBuildAttempted = useRef(false);
  const archiveBackfillAttempted = useRef(false);

  useEffect(() => {
    if (standalone) return;
    const locate = () => setTarget(document.querySelector('[data-testid="working-time-panel"]'));
    locate();
    const observer = new MutationObserver(locate);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [standalone]);

  function payrollYearScope() {
    const readinessYear = String(selectedYear);
    const currentYear = Number(currentMonth().slice(0, 4)) || new Date().getFullYear();
    const throughMonth = selectedYear < currentYear ? `${readinessYear}-12` : currentMonth().slice(0, 7);
    return { readinessYear, throughMonth };
  }

  async function fetchRecordsData() {
    const { readinessYear, throughMonth } = payrollYearScope();
    return api(`working-time/records/?from=${encodeURIComponent(`${readinessYear}-01`)}&to=${encodeURIComponent(throughMonth)}`);
  }

  async function fetchWorkspaceMetadata() {
    const { readinessYear } = payrollYearScope();
    const [settingsResponse, readinessResponse]: any[] = await Promise.all([
      api('working-time/settings/'),
      api(`working-time/lexware-readiness/?year=${encodeURIComponent(readinessYear)}`),
    ]);
    return { settingsResponse, readinessResponse };
  }

  async function fetchWorkspaceData() {
    const [response, metadata]: any[] = await Promise.all([
      fetchRecordsData(),
      fetchWorkspaceMetadata(),
    ]);
    return {
      response,
      settingsResponse: metadata.settingsResponse,
      readinessResponse: metadata.readinessResponse,
    };
  }

  function applyWorkspaceData(response: any, settingsResponse?: any, readinessResponse?: LexwareReadiness | null) {
    const nextRows = (response?.results || response || []) as PayrollRow[];
    const configuredSettings = Array.isArray(settingsResponse?.employees)
      ? settingsResponse.employees.map((item: any) => ({
          worker_id: String(item.worker_id || ''),
          employee_name: String(item.employee_name || ''),
          employee_number: String(item.employee_number || ''),
          worker_active: item.worker_active,
          user_active: item.user_active,
          is_synthetic: item.is_synthetic,
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
      : settingsRows;
    const rowEmployees: EmployeeOption[] = nextRows.map(item => ({
      worker_id: item.worker_id,
      employee_name: item.employee_name,
      employee_number: item.employee_number,
      worker_active: item.worker_active,
      user_active: item.user_active,
      is_synthetic: item.is_synthetic,
      has_period_data: true,
    }));
    const uniqueEmployees = mergeEmployeeOptions(configuredSettings, rowEmployees);

    setRows(nextRows);
    setEmployeeOptions(uniqueEmployees);
    if (settingsResponse) setSettingsRows(configuredSettings);
    if (readinessResponse !== undefined) setLexwareReadiness(readinessResponse || null);
    setDrafts(Object.fromEntries(nextRows.map(row => [row.id, {
      paid_total_hours: row.paid_total_hours ?? row.soll_hours,
      manual_adjustment: row.manual_adjustment,
    }])));
  }

  async function loadRows(autoBuild = false) {
    setLoading(true);
    setHistoricalPayrollRows([]);
    setMessage('');
    setEmptyReason('');
    try {
      let response: any = await fetchRecordsData();
      let nextRows = (response?.results || response || []) as PayrollRow[];

      if (standalone && autoBuild && selectedYear === Number(currentMonth().slice(0, 4)) && !nextRows.length && !autoBuildAttempted.current) {
        autoBuildAttempted.current = true;
        setMessage('Arbeitszeitdaten werden aus den vorhandenen Ist Zeiten aufgebaut.');
        const rebuildYear = String(selectedYear);
        const rebuilt: any = await api('working-time/rebuild-all/', { method: 'POST', body: JSON.stringify({ refresh_contract_terms: true, year: rebuildYear }) });
        if (!rebuilt?.records_count) {
          setEmptyReason(rebuilt?.detail || 'Es wurden keine abgeschlossenen oder freigegebenen Ist Zeiten gefunden.');
        }
        response = await fetchRecordsData();
        nextRows = (response?.results || response || []) as PayrollRow[];
      }

      // Paint payroll numbers as soon as the scoped records API returns.
      applyWorkspaceData(response);
      setLoading(false);

      // Settings/readiness are secondary metadata and must not delay the numbers.
      let settingsResponse: any;
      let readinessResponse: LexwareReadiness | null = null;
      try {
        const metadata = await fetchWorkspaceMetadata();
        settingsResponse = metadata.settingsResponse;
        readinessResponse = metadata.readinessResponse;
        applyWorkspaceData(response, settingsResponse, readinessResponse);
      } catch {
        // Keep already rendered payroll data usable if metadata is slow/unavailable.
      }

      // Lexware-only evidence is shown separately; we never manufacture zero IST
      // work-time accounts or Saldo for employees without a true timesheet.
      try {
        const history: any = await api(`working-time/lexware-history/?year=${selectedYear}`);
        const historical = (Array.isArray(history?.results) ? history.results : [])
          .filter((item: any) => /^20\d{2}-(0[1-9]|1[0-2])$/.test(String(item.period || '')) && item.worker_id);
        setHistoricalPayrollRows(historical);
        setEmployeeOptions(previous => {
          return mergeEmployeeOptions(previous, (historical as HistoricLexwareRow[]).map(item => ({
            worker_id: item.worker_id,
            employee_name: item.employee_name,
            employee_number: item.employee_number,
            worker_active: item.worker_active,
            user_active: item.user_active,
            is_synthetic: item.is_synthetic,
            has_payroll_history: true,
          })));
        });
      } catch {
        // Existing IST data remains available if an archive-only listing fails.
      }

      // Historical archive enrichment can be expensive because it reparses PDFs.
      // Run it after the page has rendered instead of blocking payroll numbers.
      if (
        !archiveBackfillAttempted.current
        && selectedYear === Number(currentMonth().slice(0, 4))
        && Boolean(readinessResponse?.enrichment_needed)
      ) {
        archiveBackfillAttempted.current = true;
        const backfillYear = String(readinessResponse?.year || currentMonth().slice(0, 4));
        void api('working-time/lexware-backfill/', {
          method: 'POST',
          body: JSON.stringify({ year: backfillYear }),
        }).then(async (backfill: any) => {
          if (Number(backfill?.attached || 0) > 0 || Number(backfill?.enriched || 0) > 0) {
            const refreshed = await fetchWorkspaceData();
            applyWorkspaceData(
              refreshed.response,
              refreshed.settingsResponse,
              refreshed.readinessResponse,
            );
          }
        }).catch(() => {
          // Best effort only. The visible payroll workspace stays usable.
        });
      }
      if (nextRows.length) setMessage('');
    } catch (error: any) {
      setMessage(error?.message || 'Arbeitszeitkonto konnte nicht geladen werden.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (standalone || target) void loadRows(standalone);
  }, [standalone, target, selectedYear]);

  const workerRows = useMemo(
    () => selectedWorkerId ? rows.filter(row => row.worker_id === selectedWorkerId) : rows,
    [rows, selectedWorkerId],
  );
  const reviewYear = String(selectedYear);
  const reviewThrough = lexwareReadiness?.year === selectedYear ? (lexwareReadiness.expected_through || '') : '';
  const months = useMemo(
    () => Array.from(new Set([
      ...workerRows.map(row => row.year_month),
      ...historicalPayrollRows.filter(row => !selectedWorkerId || row.worker_id === selectedWorkerId).map(row => row.period),
    ])).sort().reverse(),
    [workerRows, historicalPayrollRows, selectedWorkerId],
  );
  const visibleArchiveRows = useMemo(
    () => historicalPayrollRows.filter(row =>
      (!selectedWorkerId || row.worker_id === selectedWorkerId)
      && (month === 'all' || !month || row.period === month)),
    [historicalPayrollRows, selectedWorkerId, month],
  );
  const reviewRows = useMemo(
    () => workerRows.filter(row =>
      row.year_month.startsWith(`${reviewYear}-`)
      && !row.is_open_month
      && (!reviewThrough || row.year_month <= reviewThrough)
    ),
    [workerRows, reviewYear, reviewThrough],
  );
  const visibleRows = useMemo(
    () => month === 'all' || !month
      ? reviewRows
      : workerRows.filter(row => row.year_month === month),
    [workerRows, reviewRows, month],
  );
  const summaryRows = useMemo(
    () => month && month !== 'all'
      ? workerRows.filter(row => row.year_month === month)
      : reviewRows,
    [workerRows, reviewRows, month],
  );

  useEffect(() => {
    if (month === 'all' || !month || months.includes(month)) return;
    setMonth('all');
  }, [selectedWorkerId, months, month]);

  useEffect(() => {
    if (month && month !== 'all') setLexwarePeriod(month);
  }, [month]);

  const visibleEmployeeOptions = useMemo(
    () => employeeOptions.filter(item => showHistoricalProfiles || isNormalEmployeeOption(item)),
    [employeeOptions, showHistoricalProfiles],
  );
  const duplicateNameCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const employee of visibleEmployeeOptions) {
      const key = employeeNameKey(employee.employee_name);
      counts.set(key, (counts.get(key) || 0) + 1);
    }
    return counts;
  }, [visibleEmployeeOptions]);
  const selectedEmployee = employeeOptions.find(item => item.worker_id === selectedWorkerId);
  const selectedSetting = settingsRows.find(item => item.worker_id === selectedWorkerId);
  const closedSummaryRows = summaryRows.filter(row => !row.is_open_month);
  const summary = {
    ist: summaryRows.reduce((sum, row) => sum + number(row.ist_hours), 0),
    paid: summaryRows.reduce((sum, row) => sum + number(row.balance_reference_hours ?? row.paid_total_hours ?? row.soll_hours), 0),
    saldo: summaryRows.reduce((sum, row) => sum + number(row.monthly_balance_hours ?? 0), 0),
    gross: closedSummaryRows.reduce((sum, row) => sum + number(row.gross_with_surcharges ?? row.gross_amount), 0),
    lexwareGross: closedSummaryRows.reduce((sum, row) => sum + number(row.payroll_statement?.gross_amount), 0),
    transferred: closedSummaryRows.reduce((sum, row) => sum + number(row.payroll_statement?.transferred_amount), 0),
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
      const rebuildYear = month && month !== 'all'
        ? month.slice(0, 4)
        : String(selectedYear);
      const result: any = await api('working-time/rebuild-all/', {
        method: 'POST',
        body: JSON.stringify({ year: rebuildYear }),
      });
      setDetails({});
      await loadRows();
      setMessage(result?.records_count
        ? `Historie ${rebuildYear} neu berechnet. ${result.records_count} Monatskonten aktualisiert. Saldo startet für dieses Prüfjahr bei 0.`
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
      const reportYear = month && month !== 'all'
        ? month.slice(0, 4)
        : String(selectedYear);
      const params = new URLSearchParams({ year: reportYear });
      // The Gesamt payroll export always contains all employees.
      // Use worker-specific Word/PDF buttons for an individual account.
      if (month && month !== 'all') params.set('month', month);
      const result = await apiBlob(`working-time/export/${format}/?${params.toString()}`);
      triggerBlobDownload(result.blob, result.filename || `arbeitszeit-lohnkonto.${format}`);
    } catch (error: any) {
      setMessage(error?.message || 'Export konnte nicht erstellt werden.');
    } finally {
      setBusyId('');
    }
  }

  async function downloadArbeitszeitWord() {
    if (!selectedWorkerId) {
      setMessage('Bitte zuerst einen Mitarbeiter auswählen.');
      return;
    }
    setBusyId('export:arbeitszeit-word');
    setMessage('');
    try {
      const reportYear = month && month !== 'all'
        ? month.slice(0, 4)
        : String(selectedYear);
      const result = await apiBlob(`working-time/docx/${selectedWorkerId}/?year=${encodeURIComponent(reportYear)}`);
      triggerBlobDownload(result.blob, result.filename || '01_Arbeitszeitnachweis.docx');
    } catch (error: any) {
      setMessage(error?.message || 'Arbeitszeitnachweis konnte nicht erstellt werden.');
    } finally {
      setBusyId('');
    }
  }

  async function downloadLexwareWord() {
    if (!month || month === 'all') {
      setMessage('Bitte zuerst einen Monat auswählen.');
      return;
    }
    setBusyId('export:lexware-word');
    setMessage('');
    try {
      const result = await apiBlob(`working-time/lexware-docx/?month=${encodeURIComponent(month)}`);
      triggerBlobDownload(result.blob, result.filename || `03_Lexware_Abgleich_${month}.docx`);
    } catch (error: any) {
      setMessage(error?.message || 'Lexware Abgleich konnte nicht erstellt werden.');
    } finally {
      setBusyId('');
    }
  }

  async function downloadSelectedWorkerPdf() {
    if (!selectedWorkerId) {
      setMessage('Bitte zuerst einen Mitarbeiter auswählen.');
      return;
    }
    setBusyId('export:worker-pdf');
    setMessage('');
    try {
      const reportYear = month && month !== 'all'
        ? month.slice(0, 4)
        : String(selectedYear);
      const result = await apiBlob(`working-time/pdf/${selectedWorkerId}/?year=${encodeURIComponent(reportYear)}`);
      triggerBlobDownload(result.blob, result.filename || '04_Pruefnachweis_Mitarbeiter.pdf');
    } catch (error: any) {
      setMessage(error?.message || 'Prüfnachweis konnte nicht erstellt werden.');
    } finally {
      setBusyId('');
    }
  }

  async function downloadAuditWord() {
    const reportYear = month && month !== 'all'
      ? month.slice(0, 4)
      : String(selectedYear);
    setBusyId('export:audit-word');
    setMessage('');
    try {
      const result = await apiBlob(`working-time/audit-docx/?year=${encodeURIComponent(reportYear)}`);
      triggerBlobDownload(result.blob, result.filename || `05_Pruefbericht_Arbeitszeit_Lexware_${reportYear}.docx`);
    } catch (error: any) {
      setMessage(error?.message || 'Prüfbericht konnte nicht erstellt werden.');
    } finally {
      setBusyId('');
    }
  }

  async function downloadPayrollPdf(row: PayrollRow) {
    setBusyId(`pdf:${row.worker_id}`);
    setMessage('');
    try {
      const result = await apiBlob(`working-time/pdf/${row.worker_id}/?year=${encodeURIComponent(row.year_month.slice(0, 4))}`);
      triggerBlobDownload(result.blob, result.filename || `Arbeitszeitkonto_${row.employee_number || row.worker_id}.pdf`);
    } catch (error: any) {
      setMessage(error?.message || 'PDF konnte nicht erstellt werden.');
    } finally {
      setBusyId('');
    }
  }

  async function downloadMonthlyAttendancePdf(row: PayrollRow) {
    setBusyId(`attendance-pdf:${row.id}`);
    setMessage('');
    try {
      const result = await apiBlob(
        `working-time/attendance-pdf/${row.worker_id}/?month=${encodeURIComponent(row.year_month)}`,
      );
      triggerBlobDownload(
        result.blob,
        result.filename || `Arbeitszeitnachweis - ${row.employee_name} - ${monthLabel(row.year_month)}.pdf`,
      );
    } catch (error: any) {
      setMessage(error?.message || 'Monatlicher Arbeitszeitnachweis konnte nicht erstellt werden.');
    } finally {
      setBusyId('');
    }
  }

  async function archiveLargeLexwarePdf(file: File, period: string) {
    // Browser sends 2 MiB chunks. Annual 27 MB+ Lohnkonto uploads no longer
    // require one long-running multipart request on the production server.
    const session: any = await api('working-time/lexware-archive/begin/', {
      method: 'POST',
      body: JSON.stringify({ filename: file.name, size: file.size, period }),
    });
    const size = Number(session.chunk_size);
    const count = Number(session.chunks);
    if (!size || !count) throw new Error('Ungültige Antwort vom Lexware Upload Server.');
    for (let index = 0; index < count; index += 1) {
      const body = new FormData();
      body.append('upload_token', session.upload_token);
      body.append('index', String(index));
      body.append('chunk', file.slice(index * size, Math.min(file.size, (index + 1) * size)), file.name);
      await api('working-time/lexware-archive/chunk/', { method: 'POST', body });
      setMessage(`Jahresnachweis ${file.name}: Teil ${index + 1} von ${count} übertragen.`);
    }
    return api('working-time/lexware-archive/finish/', {
      method: 'POST',
      body: JSON.stringify({ upload_token: session.upload_token }),
    });
  }

  async function importLexware() {
    if (!lexwareFiles.length) {
      setMessage('Bitte mindestens eine Lexware Datei auswählen.');
      return;
    }
    const detectedPeriods = Array.from(new Set(lexwareFiles
      .map(file => file.name.match(/(20[0-9]{2})[-_](0[1-9]|1[0-2])/))
      .filter(Boolean)
      .map(match => `${match?.[1]}-${match?.[2]}`)));
    const containsPackageZip = lexwareFiles.some(file => file.name.toLowerCase().endsWith('.zip'));
    const autoMode = containsPackageZip || detectedPeriods.length > 1;
    if (!autoMode && !lexwarePeriod) {
      setMessage('Bitte Abrechnungsmonat auswählen.');
      return;
    }

    setLexwareBusy(true);
    setMessage('');
    try {
      const form = new FormData();
      form.append('period', autoMode ? 'auto' : lexwarePeriod);
      const years = Array.from(new Set([
        ...detectedPeriods.map(item => item.slice(0, 4)),
        ...lexwareFiles
          .map(file => file.name.match(/(20[0-9]{2})/))
          .filter(Boolean)
          .map(match => String(match?.[1] || '')),
      ].filter(Boolean)));
      if (autoMode && years.length === 1) form.append('year', years[0]);
      const largeAnnual = lexwareFiles.filter(file =>
        file.size > 8 * 1024 * 1024
        && file.name.toLowerCase().endsWith('.pdf')
        && /lohnkonto|lohnjournal|lohnsteuerbescheinigung|meldebescheinigung/i.test(file.name)
      );
      const regularFiles = lexwareFiles.filter(file => !largeAnnual.includes(file));
      if (largeAnnual.length && autoMode) {
        throw new Error('Große Jahresnachweise bitte mit einem konkreten Monat separat hochladen.');
      }
      const annualResults = [];
      for (const file of largeAnnual) {
        annualResults.push(await archiveLargeLexwarePdf(file, lexwarePeriod));
      }
      regularFiles.forEach(file => form.append('files', file));
      const result: any = regularFiles.length
        ? await api('working-time/lexware-import/', { method: 'POST', body: form })
        : { files: largeAnnual.length, employees: [], archived_documents: [], unmatched_count: 0 };
      await loadRows();
      setUnmatchedReport(null);
      const archiveErrors = Array.isArray(result?.archive_errors) ? result.archive_errors : [];
      const archived = (Array.isArray(result?.archived_documents) ? result.archived_documents.length : 0)
        + annualResults.filter(row => row.status === 'archived').length;
      const alreadyArchived = annualResults.filter(row => row.status === 'already_archived').length;
      const periods = Array.isArray(result?.detected_periods) && result.detected_periods.length
        ? result.detected_periods.map((item: string) => monthLabel(item)).join(', ')
        : (lexwarePeriod ? monthLabel(lexwarePeriod) : '');
      const unmatchedRows = Number(result?.unmatched_count || 0);
      const unmatchedUnique = Number(result?.unmatched_unique_count ?? unmatchedRows);
      setMessage(
        `Lexware Import ${archiveErrors.length ? 'teilweise abgeschlossen' : 'abgeschlossen'}${periods ? ` (${periods})` : ''}. ` +
        `${result?.files || lexwareFiles.length} Datei(en), ` +
        `${result?.employees?.length || 0} Mitarbeiter Monatszuordnungen, ` +
        `${archived} Nachweise archiviert. ` +
        (alreadyArchived ? `${alreadyArchived} bereits zuvor archiviert. ` : '') +
        (unmatchedRows
          ? `${unmatchedUnique} eindeutige nicht zugeordnete Fälle (${unmatchedRows} Nachweiszeilen).`
          : 'Alle Nachweise zugeordnet.') +
        (archiveErrors.length ? ` ACHTUNG: ${archiveErrors.length} Datei(en) nicht archiviert: ${archiveErrors.map((row: any) => row.file).join(', ')}. Bitte nur fehlgeschlagene Dateien erneut versuchen.` : '')
      );
      setLexwareFiles([]);
    } catch (error: any) {
      setMessage(error?.message || 'Lexware Import konnte nicht verarbeitet werden.');
    } finally {
      setLexwareBusy(false);
    }
  }

  async function inspectUnmatchedLexware() {
    if (!/^20\d{2}-(0[1-9]|1[0-2])$/.test(lexwarePeriod)) {
      setMessage('Bitte zuerst den Lexware Abrechnungsmonat auswählen.');
      return;
    }
    setUnmatchedBusy(true);
    setUnmatchedReport(null);
    try {
      const report: any = await api(`working-time/lexware-unmatched/?period=${encodeURIComponent(lexwarePeriod)}`);
      setUnmatchedReport(report);
      setMessage(`Lexware ${monthLabel(lexwarePeriod)} geprüft: ${report.unmatched_unique_count} nicht zugeordnete Namen (${report.unmatched_rows} Nachweiszeilen). Keine Lohndaten geändert.`);
    } catch (error: any) {
      setMessage(error?.message || 'Nicht zugeordnete Lexware Fälle konnten nicht gelesen werden.');
    } finally {
      setUnmatchedBusy(false);
    }
  }

  async function importMasterData() {
    if (!masterDataFile) {
      setMessage('Bitte Lexware Stammdaten JSON auswählen.');
      return;
    }
    setMasterDataBusy(true);
    setMessage('');
    try {
      const form = new FormData();
      form.append('file', masterDataFile);
      const result: any = await api('workers/master-data/import/', { method: 'POST', body: form });
      const rebuildYear = month && month !== 'all'
        ? month.slice(0, 4)
        : (months[0]?.slice(0, 4) || String(new Date().getFullYear()));
      const rebuilt: any = await api('working-time/rebuild-all/', {
        method: 'POST',
        body: JSON.stringify({ refresh_contract_terms: true, year: rebuildYear }),
      });
      await loadRows();
      const imported = result?.employees?.length || 0;
      const unmatchedNames = Array.isArray(result?.unmatched) ? result.unmatched : [];
      const unmatched = unmatchedNames.length;
      const rebuiltCount = rebuilt?.records_count || 0;
      const unmatchedText = unmatched ? ` Nicht zugeordnet: ${unmatchedNames.join(', ')}.` : '';
      setMessage(`Lexware Stammdaten gespeichert: ${imported} Mitarbeiter. ${unmatched} nicht zugeordnet. Arbeitszeitkonten mit Vertragsdaten automatisch neu berechnet: ${rebuiltCount}.${unmatchedText}`);
      setMasterDataFile(null);
    } catch (error: any) {
      setMessage(error?.message || 'Lexware Stammdaten konnten nicht importiert werden.');
    } finally {
      setMasterDataBusy(false);
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
          <button type="button" className="payroll-secondary" onClick={() => void downloadArbeitszeitWord()} disabled={!selectedWorkerId || busyId === 'export:arbeitszeit-word'}>01 Word Arbeitszeit</button>
          <button type="button" className="payroll-secondary" onClick={() => void downloadExport('xlsx')} disabled={busyId === 'export:xlsx'}>02 Excel Gesamt</button>
          <button type="button" className="payroll-secondary" onClick={() => void downloadLexwareWord()} disabled={month === 'all' || busyId === 'export:lexware-word'}>03 Word Lexware (alle)</button>
          <button type="button" className="payroll-secondary" onClick={() => void downloadSelectedWorkerPdf()} disabled={!selectedWorkerId || busyId === 'export:worker-pdf'}>04 PDF Prüfnachweis</button>
          <button type="button" className="payroll-secondary" onClick={() => void downloadAuditWord()} disabled={busyId === 'export:audit-word'}>05 Word Prüfbericht (alle)</button>
          <button type="button" onClick={() => setSettingsOpen(value => !value)}>{settingsOpen ? 'Stammdaten schließen' : 'Stammdaten'}</button>
        </div>
      </header>}

      <section className="payroll-filter-deck">
        <div className="payroll-filter-main">
          <label>Jahr
            <select aria-label="Arbeitszeitkonto Jahr" value={selectedYear} onChange={event => {
              const nextYear = Number(event.target.value);
              setSelectedYear(nextYear);
              setMonth('all');
              setExpandedId('');
              setDetails({});
              setLexwareReadiness(null);
              setLexwarePeriod(`${nextYear}-01`);
            }}>
              {Array.from({ length: Math.max(1, (Number(currentMonth().slice(0, 4)) || new Date().getFullYear()) - 1999) }, (_, index) =>
                (Number(currentMonth().slice(0, 4)) || new Date().getFullYear()) - index
              ).map(year => <option key={year} value={year}>{year}</option>)}
            </select>
          </label>
          <label>Mitarbeiter
            <select aria-label="Mitarbeiter auswählen" value={selectedWorkerId} onChange={event => { setSelectedWorkerId(event.target.value); setExpandedId(''); }}>
              <option value="">Alle Mitarbeiter</option>
              {visibleEmployeeOptions.map(item => (
                <option key={item.worker_id} value={item.worker_id}>
                  {item.employee_name}
                  {(duplicateNameCounts.get(employeeNameKey(item.employee_name)) || 0) > 1
                    ? ` · Personalnr. ${item.employee_number || item.worker_id.slice(0, 8)}`
                    : ''}
                  {showHistoricalProfiles && !isNormalEmployeeOption(item) ? ' · Historisch/Technisch' : ''}
                </option>
              ))}
            </select>
            <span className="payroll-employee-filter-advanced">
              <input
                type="checkbox"
                aria-label="Historische und technische Profile anzeigen"
                checked={showHistoricalProfiles}
                onChange={event => {
                  const enabled = event.target.checked;
                  setShowHistoricalProfiles(enabled);
                  if (!enabled && selectedEmployee && !isNormalEmployeeOption(selectedEmployee)) {
                    setSelectedWorkerId('');
                    setExpandedId('');
                  }
                }}
              />
              Historische und technische Profile anzeigen
            </span>
          </label>
          <label>Monat
            <select aria-label="Arbeitszeitkonto Monat" value={month} onChange={event => { setMonth(event.target.value); setExpandedId(''); }}>
              <option value="all">Prüfjahr {reviewYear}</option>
              {months.map(item => <option key={item} value={item}>{monthLabel(item)}</option>)}
            </select>
          </label>
          <button type="button" className="payroll-refresh" onClick={() => void loadRows()} disabled={loading}>{loading ? 'Wird geladen' : 'Aktualisieren'}</button>
        </div>
        <div className="payroll-filter-context">
          <span>{selectedEmployee?.employee_name || 'Gesamte Belegschaft'}</span>
          <b>{visibleRows.length} Monatskonten</b>
          <small>{month === 'all'
            ? `Prüfjahr ${reviewYear}${reviewThrough ? ` · abgeschlossen bis ${monthLabel(reviewThrough)}` : ''}`
            : monthLabel(month)}</small>
        </div>
      </section>

      <section className="payroll-evidence-grid" aria-label="Drei Nachweise">
        <article><span>01</span><div><b>Ist Arbeitszeit</b><small>Beginn, Ende, Pause und Kunde aus der tatsächlichen Zeiterfassung.</small></div></article>
        <article><span>02</span><div><b>Dienstplan</b><small>Der geplante Einsatz bleibt als Vergleich sichtbar und verändert die Ist Stunden nicht.</small></div></article>
        <article><span>03</span><div><b>Zahlung</b><small>Bezahlte Stunden und Lexware Bankbetrag werden separat dokumentiert.</small></div></article>
      </section>

      {lexwareReadiness && <section className={`payroll-readiness ${lexwareReadiness.no_additional_import_required ? 'is-complete' : 'has-gaps'}`}>
        <div>
          <span>LEXWARE DATENSTAND {lexwareReadiness.year}</span>
          <b>{lexwareReadiness.no_additional_import_required
            ? `Vollständig bis ${lexwareReadiness.expected_through ? monthLabel(lexwareReadiness.expected_through) : 'heute'}`
            : `${lexwareReadiness.complete_months} von ${lexwareReadiness.expected_months} Monaten vollständig`}</b>
        </div>
        <small>
          {lexwareReadiness.core_documents_present}/{lexwareReadiness.core_documents_expected} Kernnachweise
          {' · '}
          {Number(lexwareReadiness.parsed_complete_months ?? 0)}/{lexwareReadiness.expected_months} Monate technisch eingelesen
          {' · '}
          {lexwareReadiness.annual_complete ? 'Jahresnachweise vorhanden' : 'Jahresnachweise prüfen'}
          {' · '}
          {lexwareReadiness.no_additional_import_required
            ? 'Kein weiterer Lexware Import für abgeschlossene Monate nötig'
            : `${lexwareReadiness.missing?.length || 0} Nachweise fehlen`}
        </small>
      </section>}

      <section className="payroll-summary" aria-label="Lohnübersicht">
        <div><span>Gearbeitet</span><strong>{decimal(summary.ist)} Std.</strong><small>Ist Zeit</small></div>
        <div><span>Bezahlt oder Soll</span><strong>{decimal(summary.paid)} Std.</strong><small>bei Gehalt gilt die vertragliche Sollzeit</small></div>
        <div><span>Saldo</span><strong className={summary.saldo < 0 ? 'negative' : 'positive'}>{signedDecimal(summary.saldo)} Std.</strong><small>offenes Zeitkonto</small></div>
        <div><span>Lexware Brutto</span><strong>{money(summary.lexwareGross)}</strong><small>Lohnabrechnungen</small></div>
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
          <label>Feiertag Hessen Zuschlag % (laut Vertrag)<input type="number" step="0.01" min="0" value={selectedSetting.holiday_surcharge_percent ?? '0'} onChange={event => updateSelectedSetting('holiday_surcharge_percent', event.target.value)} /></label>
          <button type="button" onClick={() => void saveSelectedSettings()} disabled={settingsBusy}>{settingsBusy ? 'Speichert' : 'Stammdaten speichern'}</button>
        </div>}
      </section>}

      <section className="payroll-data-care">
        <button
          type="button"
          className="payroll-data-care-toggle"
          aria-expanded={dataCareOpen}
          onClick={() => setDataCareOpen(value => !value)}
        >
          <span>⋯</span>
          {dataCareOpen ? 'Datenpflege schließen' : 'Datenpflege & Import'}
        </button>
        {dataCareOpen && <div className="payroll-tool-row payroll-tool-row-collapsed">
          <div className="payroll-tool-card">
            <span className="payroll-tool-index">A</span>
            <div><b>Historie neu berechnen</b><small>Alle vorhandenen echten Arbeitszeiten werden vom ersten Arbeitsmonat bis heute neu aufgebaut.</small></div>
            <button type="button" onClick={() => void rebuildHistory()} disabled={historyBusy}>{historyBusy ? 'Berechnet' : 'Neu berechnen'}</button>
          </div>
          <div className="payroll-tool-card payroll-lexware-card">
            <span className="payroll-tool-index">S</span>
            <div><b>Lexware Stammdaten</b><small>Beschäftigungsart, Eintritt, Wochenstunden, Lohn/Gehalt, Bank, Steuer und Versicherung sicher in der Personalakte speichern.</small></div>
            <div className="payroll-lexware-fields">
              <input aria-label="Lexware Stammdaten Datei" type="file" accept=".json,application/json" onChange={event => setMasterDataFile(event.target.files?.[0] || null)} />
              <button type="button" onClick={() => void importMasterData()} disabled={masterDataBusy || !masterDataFile}>{masterDataBusy ? 'Speichert' : 'Stammdaten übernehmen'}</button>
            </div>
          </div>
          <div className="payroll-tool-card payroll-lexware-card">
            <span className="payroll-tool-index">L</span>
            <div><b>Lexware übernehmen</b><small>Einzelmonat oder komplettes Jahrespaket als ZIP. PDF, SEPA XML und Bankdateien werden automatisch dem richtigen Monat zugeordnet.</small></div>
            <div className="payroll-lexware-fields">
              <input aria-label="Lexware Abrechnungsmonat" type="month" value={lexwarePeriod} onChange={event => { setLexwarePeriod(event.target.value); setUnmatchedReport(null); }} />
              <input
                aria-label="Lexware Dateien"
                type="file"
                multiple
                accept=".pdf,.csv,.zip,.xml,application/pdf,text/csv,application/zip,application/xml,text/xml"
                onChange={event => {
                  const files = Array.from(event.target.files || []);
                  setLexwareFiles(files);
                  const periods = Array.from(new Set(files
                    .map(file => file.name.match(/(20[0-9]{2})[-_](0[1-9]|1[0-2])/))
                    .filter(Boolean)
                    .map(match => `${match?.[1]}-${match?.[2]}`)));
                  if (periods.length === 1 && periods[0]) {
                    setLexwarePeriod(periods[0]);
                    setMessage(`Abrechnungsmonat automatisch erkannt: ${monthLabel(periods[0])}.`);
                  } else if (periods.length > 1) {
                    setMessage(`Jahresimport erkannt: ${periods.length} Abrechnungsmonate werden automatisch getrennt verarbeitet.`);
                  } else if (files.some(file => file.name.toLowerCase().endsWith('.zip'))) {
                    setMessage('Lexware Jahrespaket erkannt. Monate werden beim Import automatisch aus den enthaltenen Dateien erkannt.');
                  }
                }}
              />
              <button type="button" onClick={() => void importLexware()} disabled={lexwareBusy || !lexwareFiles.length}>{lexwareBusy ? 'Importiert' : `Übernehmen${lexwareFiles.length ? ` (${lexwareFiles.length})` : ''}`}</button>
              <button type="button" className="payroll-secondary" onClick={() => void inspectUnmatchedLexware()} disabled={unmatchedBusy}>{unmatchedBusy ? 'Prüfung läuft' : 'Nicht zugeordnete prüfen'}</button>
            </div>
          </div>
        </div>}
      </section>

      {message && <div className="payroll-message" role="status">{message}</div>}
      {unmatchedReport && <div className="payroll-unmatched-report" role="region" aria-label="Nicht zugeordnete Lexware Mitarbeiter">
        <b>{monthLabel(unmatchedReport.period)}: {unmatchedReport.unmatched_unique_count} nicht zugeordnete Namen, {unmatchedReport.unmatched_rows} Nachweiszeilen</b>
        <small>Nur archivierte Dokumente geprüft. Es wurden keine Stunden, Gehälter oder Salden verändert.</small>
        {unmatchedReport.evidence_files === 0 && <p>Keine archivierten Lohnabrechnungen oder Zahlungslisten für diesen Monat gefunden.</p>}
        {unmatchedReport.unmatched.length > 0 && <ul>{unmatchedReport.unmatched.map(item => <li key={item.employee_name}><strong>{item.employee_name}</strong> · {item.rows} Nachweiszeile(n) · {item.sources.join(', ')}</li>)}</ul>}
        {unmatchedReport.errors?.length > 0 && <p>{unmatchedReport.errors.length} Archivdateien konnten nicht gelesen werden.</p>}
      </div>}

      {visibleArchiveRows.length > 0 && <section className="payroll-unmatched-report" aria-label="Lexware Historie ohne Zeiterfassung">
        <b>Lexware Historie ohne Zeiterfassung · {visibleArchiveRows.length} Abrechnungen</b>
        <small>Nur tatsächlich importierte Lexware Beträge. Keine bestätigten Ist Stunden vorhanden; kein künstlicher Soll Wert oder Saldo.</small>
        <div className="payroll-archive-scroll"><table aria-label="Historische Lexware Abrechnungen">
          <thead><tr><th>Mitarbeiter</th><th>Monat</th><th>Brutto</th><th>Netto</th><th>Auszahlungsbetrag</th><th>Nachweis</th></tr></thead>
          <tbody>{visibleArchiveRows.map((item, index) => <tr key={`${item.worker_id}:${item.period}:${index}`}>
            <td>{item.employee_name}</td><td>{monthLabel(item.period)}</td>
            <td>{item.gross_amount == null ? 'Nicht erfasst' : money(item.gross_amount)}</td>
            <td>{item.net_amount == null ? 'Nicht erfasst' : money(item.net_amount)}</td>
            <td>{item.transferred_amount == null ? 'Nicht belegt' : money(item.transferred_amount)}</td>
            <td>{item.historical_profile ? 'Historische Personalakte' : 'Nur Lexware, keine IST Zeiten'}</td>
          </tr>)}</tbody>
        </table></div>
      </section>}

      <div className="payroll-record-list" data-testid="payroll-record-list">
        {visibleRows.map(row => {
          const draft = drafts[row.id] || { paid_total_hours: row.paid_total_hours ?? row.soll_hours, manual_adjustment: row.manual_adjustment };
          const expanded = expandedId === row.id;
          const detail = details[row.id];
          const statement = row.payroll_statement;
          const reconciliationStatus = row.reconciliation_status || 'PRÜFEN';
          const reconciliationClass = reconciliationStatus === 'MATCH'
            ? 'match'
            : reconciliationStatus === 'ABWEICHUNG'
              ? 'abweichung'
              : reconciliationStatus === 'LAUFEND'
                ? 'laufend'
                : 'pruefen';
          return <article className={`payroll-record-card ${expanded ? 'is-expanded' : ''}`} key={row.id}>
            <header>
              <div className="payroll-record-month"><span>{monthLabel(row.year_month)}</span><small>{employmentLabel(row.employment_type)}</small></div>
              <div className="payroll-record-person">
                <strong>{row.employee_name}</strong>
                <span>{row.employee_number || 'Ohne Personalnummer'}</span>
              </div>
              <div className="payroll-record-gross">
                <small>{
                  statement?.source === 'lexware_bank_export'
                    ? 'Bankzahlung'
                    : statement?.source === 'lexware_sepa_xml' || statement?.source === 'lexware_sepa_bundle'
                      ? 'Lexware SEPA'
                      : 'Lexware Zahlungsliste'
                }</small>
                <b>{statement?.transferred_amount ? money(statement.transferred_amount) : 'Noch nicht importiert'}</b>
              </div>
            </header>

            {!!row.contract_issues?.length && row.contract_issues.map((issue, index) =>
              <div className="payroll-warning" key={`${row.id}:contract:${index}`}>{issue}</div>
            )}

            <div className={`payroll-reconciliation payroll-reconciliation-${reconciliationClass}`}>
              <div className="payroll-reconciliation-overall">
                <span>LEXWARE ABGLEICH</span>
                <b>{reconciliationStatus}</b>
                <small>{reconciliationStatus === 'LAUFEND' ? 'Laufender Monat wird noch nicht in den Saldo eingerechnet' : row.reconciliation_issues?.length ? `${row.reconciliation_issues.length} Prüfhinweis(e)` : 'Nachweise stimmen überein'}</small>
              </div>
              {(['night', 'saturday', 'sunday', 'holiday'] as const).map(key => {
                const item = row.surcharge_reconciliation?.[key];
                if (!item) return null;
                const itemClass = item.status === 'MATCH' ? 'match' : item.status === 'ABWEICHUNG' ? 'abweichung' : 'pruefen';
                return <div className={`payroll-reconciliation-item payroll-reconciliation-${itemClass}`} key={key}>
                  <span>{item.label}</span>
                  <b>{item.status}</b>
                  <small>
                    A+ {decimal(item.aplus_hours)} Std. / {money(item.aplus_amount)}
                    {' · '}
                    Lexware {item.lexware_hours == null
                      ? 'kein Zuschlag'
                      : `${decimal(item.lexware_hours)} Std. / ${money(item.lexware_amount)}`}
                  </small>
                </div>;
              })}
            </div>

            <div className="payroll-metrics">
              <div><span>IST</span><b>{decimal(row.ist_hours)} Std.</b></div>
              <div><span>{row.balance_basis === 'open_month' ? 'Saldo Basis' : row.balance_basis === 'soll_salary' ? 'Sollbasis' : 'Bezahlt'}</span><b>{row.balance_basis === 'open_month' ? 'offen' : `${decimal(row.balance_reference_hours ?? row.paid_total_hours ?? row.soll_hours)} Std.`}</b></div>
              <div><span>Monatssaldo</span><b className={number(row.monthly_balance_hours) < 0 ? 'negative' : 'positive'}>{signedDecimal(row.monthly_balance_hours)} Std.</b></div>
              <div><span>Saldo gesamt</span><b className={number(row.saldo_cumulative) < 0 ? 'negative' : 'positive'}>{signedDecimal(row.saldo_cumulative)} Std.</b></div>
              <div>
                <span>{row.balance_basis === 'soll_salary' ? 'Gehalt' : 'Stundensatz'}</span>
                <b>{row.balance_basis === 'soll_salary'
                  ? money(statement?.lexware_monthly_salary ?? row.gross_amount)
                  : money(row.hourly_rate)}</b>
              </div>
              <div><span>A+ Brutto</span><b>{money(row.gross_with_surcharges ?? row.gross_amount)}</b></div>
              {statement?.gross_amount != null && <div><span>Lexware Brutto</span><b>{money(statement.gross_amount)}</b></div>}
              <div><span>Nacht</span><b>{decimal(row.night_hours)} Std.</b></div>
              <div><span>Samstag</span><b>{decimal(row.saturday_hours)} Std.</b></div>
              <div><span>Sonntag</span><b>{decimal(row.sunday_hours)} Std.</b></div>
              <div><span>Feiertag Hessen</span><b>{decimal(row.holiday_hours)} Std.</b></div>
              <div><span>Feiertag Zuschlag</span><b>{money(row.holiday_surcharge_amount)}</b></div>
              <div><span>Zuschläge</span><b>{money(row.surcharge_amount)}</b></div>
              <div><span>Abwesenheit</span><b>{row.absence_days || 0} Tg.</b></div>
              <div><span>Urlaub</span><b>{row.vacation_days || 0} Tg.</b></div>
              <div><span>Krank</span><b>{row.sick_days || 0} Tg.</b></div>
              {number(statement?.lexware_sick_hours) > 0 && <div><span>Lexware Krank</span><b>{decimal(statement?.lexware_sick_hours)} Std.</b></div>}
              <div><span>Soll</span><b>{row.historical_soll_unverified ? 'Historisch nicht belegt' : `${decimal(row.soll_hours)} Std.`}</b></div>
              <div><span>Einträge</span><b>{row.entry_count || 0}</b></div>
            </div>

            <div className="payroll-record-actions">
              <button type="button" onClick={() => void toggleRow(row)}>{expanded ? 'Details schließen' : 'Tagesnachweis öffnen'}</button>
              <button type="button" className="payroll-secondary" onClick={() => void downloadPayrollPdf(row)} disabled={busyId === `pdf:${row.worker_id}`}>{busyId === `pdf:${row.worker_id}` ? 'PDF wird erstellt' : 'PDF'}</button>
              <button type="button" className="payroll-secondary" onClick={() => void downloadMonthlyAttendancePdf(row)} disabled={busyId === `attendance-pdf:${row.id}`}>{busyId === `attendance-pdf:${row.id}` ? 'Arbeitszeitnachweis wird erstellt' : 'Arbeitszeitnachweis PDF'}</button>
            </div>

            {expanded && <div className="payroll-card-details">
              <div className="payroll-edit-row">
                {row.balance_basis === 'soll_salary'
                  ? <label>Saldo Basis
                      <input type="text" value={`Gehalt: Soll ${decimal(row.balance_reference_hours ?? row.soll_hours)} Std.`} disabled />
                    </label>
                  : <label>Bezahlte Stunden gesamt
                      <input aria-label={`Bezahlte Stunden ${row.employee_name} ${row.year_month}`} type="number" min="0" step="0.25" value={draft.paid_total_hours} onChange={event => setDrafts({ ...drafts, [row.id]: { ...draft, paid_total_hours: event.target.value } })} />
                    </label>}
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
                {number(statement?.lexware_sick_hours) > 0 && <div><span>Krankheit Lexware</span><b>{decimal(statement?.lexware_sick_hours)} Std. · U1 {money(statement?.lexware_u1_reimbursement)}</b></div>}
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
                <div className="payroll-daily-head"><div><span>TAGESNACHWEIS</span><b>Soll und Ist nebeneinander</b></div><small>{detail?.entries?.length ?? row.entry_count ?? 0} Einträge</small></div>
                {!detail && <div className="payroll-detail-loading">Tagesdetails werden geladen.</div>}
                {!!detail?.entries?.length && <div className="payroll-daily-table" role="table" aria-label={`Tagesnachweis ${row.employee_name} ${row.year_month}`}>
                  <div className="payroll-daily-row payroll-daily-header" role="row">
                    <span>Datum</span><span>Kunde</span><span>Soll</span><span>Ist</span><span>Pause</span><span>Netto</span><span>Nacht</span><span>Sa</span><span>So</span><span>Feiertag</span><span>Notiz</span>
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
                    <span title={(entry.holiday_details || []).map(item => `${item.date}: ${item.name}`).join(', ')}>{hoursFromMinutes(entry.holiday_minutes)}</span>
                    <span>{entry.notes || '–'}</span>
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

      <footer className="payroll-footnote">Der Saldo basiert auf tatsächlichen Ist Stunden und manuellen Korrekturen. Bei Stundenlohn werden die tatsächlich bezahlten Stunden verwendet, bei Gehalt die vertragliche Sollzeit. Ein Lexware Bankbetrag wird nicht automatisch in Stunden umgerechnet.</footer>
    </div>
  );

  if (standalone) return workspace;
  if (!target) return null;
  return createPortal(workspace, target);
}
