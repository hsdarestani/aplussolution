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
