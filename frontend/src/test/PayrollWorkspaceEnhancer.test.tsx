import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiMock = vi.fn();
const apiBlobMock = vi.fn();
vi.mock('../api', () => ({
  api: (...args: any[]) => apiMock(...args),
  apiBlob: (...args: any[]) => apiBlobMock(...args),
}));

import PayrollWorkspaceEnhancer from '../PayrollWorkspaceEnhancer';

const row = {
  id: 'rec-1',
  worker_id: 'worker-1',
  employee_name: 'Anna Becker',
  employment_type: 'minijob',
  year_month: '2026-08',
  ist_hours: '50.00',
  soll_hours: '38.00',
  difference_hours: '12.00',
  carryover_previous: '0.00',
  paid_hours: '0.00',
  paid_total_hours: '38.00',
  monthly_balance_hours: '12.00',
  manual_adjustment: '0.00',
  saldo_cumulative: '12.00',
  hourly_rate: '17.50',
  gross_amount: '875.00',
  gross_with_surcharges: '900.00',
  night_hours: '4.00',
  saturday_hours: '10.00',
  sunday_hours: '0.00',
  surcharge_amount: '25.00',
  entry_count: 1,
  payroll_statement: {
    id: 'statement-1',
    transferred_amount: '500.00',
    payment_date: '2026-09-05',
    source: 'lexware_bank_export',
  },
  source: 'aplus_time_entries',
};

const detail = {
  ...row,
  entries: [{
    id: 'entry-1',
    client_name: 'Kunde GmbH',
    location_name: 'Messe Frankfurt',
    planned_start: '2026-08-03T08:00:00+02:00',
    planned_end: '2026-08-03T16:00:00+02:00',
    local_clock_in: '2026-08-03T08:00:00+02:00',
    local_clock_out: '2026-08-03T18:00:00+02:00',
    break_minutes: 0,
    worked_minutes: 600,
    night_minutes: 0,
    saturday_minutes: 0,
    sunday_minutes: 0,
  }],
};

describe('PayrollWorkspaceEnhancer', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="root"></div><section data-testid="working-time-panel"></section>';
    apiMock.mockReset();
    apiBlobMock.mockReset();
    apiBlobMock.mockResolvedValue({ blob: new Blob(['pdf']), filename: 'Arbeitszeitkonto.pdf' });
    apiMock.mockImplementation((path: string, options?: RequestInit) => {
      if (path === 'working-time/records/' && !options) return Promise.resolve({ results: [row] });
      if (path === 'working-time/settings/' && !options) return Promise.resolve({
        employees: [
          { worker_id: 'worker-1', employee_name: 'Anna Becker' },
          { worker_id: 'worker-2', employee_name: 'Berta Klein' },
        ],
      });
      if (path === 'working-time/records/rec-1/details/') return Promise.resolve(detail);
      if (path === 'working-time/records/rec-1/' && options?.method === 'PATCH') {
        return Promise.resolve({ ...row, paid_total_hours: '45.00', saldo_cumulative: '5.00' });
      }
      return Promise.resolve({ results: [row] });
    });
  });

  it('hides inactive empty duplicates and WIW technical users but keeps an explicit historical picker', async () => {
    const employees = [
      { worker_id: 'real-musa', employee_name: 'Musa Jamali', employee_number: '53560424', worker_active: true },
      { worker_id: 'stub-musa', employee_name: 'Musa Jamali', employee_number: 'LOCAL-MUSA-JAMALI', worker_active: false },
      { worker_id: 'real-antor', employee_name: 'Antor Shaha', employee_number: 'MA-0061', worker_active: true },
      { worker_id: 'stub-antor', employee_name: 'Antor Shaha', employee_number: 'MA-0063', worker_active: false },
      { worker_id: 'wiw-synthetic', employee_name: 'wiw-48430856@sync.invalid', employee_number: 'WIW-48430856', worker_active: true, is_synthetic: true },
      { worker_id: 'review-user', employee_name: 'Store Reviewer', employee_number: 'TEST-REVIEW', worker_active: true },
    ];
    apiMock.mockImplementation((path: string) => {
      if (path.startsWith('working-time/records/?')) {
        return Promise.resolve({ results: [
          { ...row, id: 'rec-real-musa', worker_id: 'real-musa', employee_name: 'Musa Jamali', employee_number: '53560424', worker_active: true },
          { ...row, id: 'rec-synthetic', worker_id: 'wiw-synthetic', employee_name: 'wiw-48430856@sync.invalid', is_synthetic: true },
        ] });
      }
      if (path === 'working-time/settings/') return Promise.resolve({ employees });
      if (path.startsWith('working-time/lexware-history/')) return Promise.resolve({ results: [] });
      return Promise.resolve({ results: [] });
    });
    render(<PayrollWorkspaceEnhancer />);
    const workspace = await screen.findByTestId('payroll-workspace');
    const select = within(workspace).getByLabelText('Mitarbeiter auswählen');
    await waitFor(() => expect(within(select).getByRole('option', { name: 'Antor Shaha' })).toBeInTheDocument());
    expect(within(select).getAllByRole('option', { name: 'Musa Jamali' })).toHaveLength(1);
    expect(within(select).queryByText(/sync.invalid/)).not.toBeInTheDocument();
    expect(within(select).queryByText(/Store Reviewer/)).not.toBeInTheDocument();

    fireEvent.click(within(workspace).getByRole('checkbox', { name: 'Historische und technische Profile anzeigen' }));
    await waitFor(() => {
      expect(within(select).getAllByRole('option', { name: /Musa Jamali.*Personalnr/ })).toHaveLength(2);
      expect(within(select).getAllByRole('option', { name: /Antor Shaha.*Personalnr/ })).toHaveLength(2);
    });
    expect(within(select).getByRole('option', { name: /wiw-48430856@sync.invalid/ })).toBeInTheDocument();
    expect(within(select).getByRole('option', { name: /Store Reviewer/ })).toBeInTheDocument();

    fireEvent.change(select, { target: { value: 'stub-musa' } });
    fireEvent.click(within(workspace).getByRole('checkbox', { name: 'Historische und technische Profile anzeigen' }));
    expect((select as HTMLSelectElement).value).toBe('');
  });

  it('reviews unmatched employees from archived PDFs without another import', async () => {
    const existingHandler = apiMock.getMockImplementation();
    apiMock.mockImplementation((path: string, options?: RequestInit) => {
      if (path === 'working-time/lexware-unmatched/?period=2025-12') {
        return Promise.resolve({
          period: '2025-12',
          evidence_files: 2,
          scanned_rows: 31,
          matched_rows: 0,
          unmatched_rows: 31,
          unmatched_unique_count: 1,
          errors: [],
          unmatched: [{ employee_name: 'Missing Employee', rows: 3, sources: ['Lohnabrechnungen_2025-12.pdf'] }],
        });
      }
      return existingHandler?.(path, options);
    });
    render(<PayrollWorkspaceEnhancer />);
    const workspace = await screen.findByTestId('payroll-workspace');
    fireEvent.click(within(workspace).getByRole('button', { name: /Datenpflege & Import/ }));
    fireEvent.change(within(workspace).getByLabelText('Lexware Abrechnungsmonat'), {
      target: { value: '2025-12' },
    });
    fireEvent.click(within(workspace).getByRole('button', { name: 'Nicht zugeordnete prüfen' }));
    expect(await within(workspace).findByText('Missing Employee')).toBeInTheDocument();
    expect(apiMock).toHaveBeenCalledWith('working-time/lexware-unmatched/?period=2025-12');
    expect(apiMock.mock.calls.some(([path]) => path === 'working-time/lexware-import/')).toBe(false);
  });

  it('downloads a separate monthly Arbeitszeitnachweis next to existing PDF', async () => {
    Object.defineProperty(URL, 'createObjectURL', { value: vi.fn(() => 'blob:demo'), configurable: true });
    Object.defineProperty(URL, 'revokeObjectURL', { value: vi.fn(), configurable: true });
    render(<PayrollWorkspaceEnhancer />);
    const workspace = await screen.findByTestId('payroll-workspace');
    fireEvent.click(within(workspace).getByRole('button', { name: 'Arbeitszeitnachweis PDF' }));
    await waitFor(() => expect(apiBlobMock).toHaveBeenCalledWith(
      'working-time/attendance-pdf/worker-1/?month=2026-08',
    ));
  });

  it('switches to earlier years without automatically rebuilding historical balances', async () => {
    render(<PayrollWorkspaceEnhancer />);
    const workspace = await screen.findByTestId('payroll-workspace');
    const year = within(workspace).getByLabelText('Arbeitszeitkonto Jahr') as HTMLSelectElement;
    expect(year.value).toBe('2026');
    fireEvent.change(year, { target: { value: '2025' } });
    await waitFor(() => {
      expect(apiMock).toHaveBeenCalledWith('working-time/records/?from=2025-01&to=2025-12');
      expect(apiMock).toHaveBeenCalledWith('working-time/lexware-readiness/?year=2025');
    });
    expect(year.value).toBe('2025');
    expect(apiMock.mock.calls.some(([path]) => path === 'working-time/rebuild-all/')).toBe(false);
  });

  it('renders audited monthly payroll and saves total paid hours', async () => {
    render(<PayrollWorkspaceEnhancer />);

    const workspace = await screen.findByTestId('payroll-workspace');
    expect(within(workspace).getAllByText('Anna Becker').length).toBeGreaterThanOrEqual(1);
    const employeeSelect = within(workspace).getByLabelText('Mitarbeiter auswählen');
    expect(employeeSelect.tagName).toBe('SELECT');
    expect(within(employeeSelect).getByRole('option', { name: 'Alle Mitarbeiter' })).toBeInTheDocument();
    expect(within(employeeSelect).getByRole('option', { name: 'Berta Klein' })).toBeInTheDocument();
    expect(within(workspace).getAllByText(/900,00/).length).toBeGreaterThanOrEqual(1);
    expect(within(workspace).getAllByText(/500,00/).length).toBeGreaterThanOrEqual(1);
    expect(within(workspace).getByText(/17,50/)).toBeInTheDocument();
    expect(within(workspace).getAllByText('+12,00 Std.').length).toBeGreaterThanOrEqual(2);
    expect(within(workspace).getByRole('button', { name: 'Arbeitszeitnachweis PDF' })).toBeInTheDocument();

    fireEvent.click(within(workspace).getByRole('button', { name: 'Tagesnachweis öffnen' }));
    expect(await within(workspace).findByText('Kunde GmbH')).toBeInTheDocument();
    const dailyTable = within(workspace).getByRole('table', { name: 'Tagesnachweis Anna Becker 2026-08' });
    expect(within(dailyTable).getByText('10,00 Std.')).toBeInTheDocument();

    const paid = within(workspace).getByLabelText('Bezahlte Stunden Anna Becker 2026-08');
    const correction = within(workspace).getByLabelText('Korrektur Anna Becker 2026-08');
    fireEvent.change(paid, { target: { value: '45.00' } });
    fireEvent.change(correction, { target: { value: '0.00' } });
    fireEvent.click(within(workspace).getByRole('button', { name: 'Speichern' }));

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      'working-time/records/rec-1/',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ paid_total_hours: '45.00', manual_adjustment: '0.00' }),
      }),
    ));
  });
});
