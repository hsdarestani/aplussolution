import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiMock = vi.fn();
vi.mock('../api', () => ({ api: (...args: any[]) => apiMock(...args) }));

import PayrollWorkspaceEnhancer from '../PayrollWorkspaceEnhancer';

const row = {
  id: 'rec-1',
  worker_id: 'worker-1',
  employee_name: 'Anna Becker',
  year_month: '2026-08',
  ist_hours: '80.00',
  soll_hours: '80.00',
  difference_hours: '0.00',
  carryover_previous: '2.00',
  paid_hours: '0.00',
  manual_adjustment: '0.00',
  saldo_cumulative: '2.00',
  hourly_rate: '17.50',
  gross_amount: '1400.00',
  source: 'aplus_time_entries',
};

describe('PayrollWorkspaceEnhancer', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="root"></div><section data-testid="working-time-panel"></section>';
    apiMock.mockReset();
    apiMock.mockImplementation((path: string, options?: RequestInit) => {
      if (path === 'working-time/records/' && !options) return Promise.resolve({ results: [row] });
      if (path === 'working-time/records/rec-1/' && options?.method === 'PATCH') {
        return Promise.resolve({ ...row, paid_hours: '1.00', manual_adjustment: '-0.50', saldo_cumulative: '0.50' });
      }
      return Promise.resolve({ results: [row] });
    });
  });

  it('renders monthly payroll values and saves payout/correction', async () => {
    render(<PayrollWorkspaceEnhancer />);

    const workspace = await screen.findByTestId('payroll-workspace');
    expect(within(workspace).getByText('Anna Becker')).toBeInTheDocument();
    expect(within(workspace).getAllByText(/1\.400,00/).length).toBeGreaterThanOrEqual(1);
    expect(within(workspace).getByText(/17,50/)).toBeInTheDocument();

    const payout = within(workspace).getByLabelText('Auszahlung Anna Becker 2026-08');
    const correction = within(workspace).getByLabelText('Korrektur Anna Becker 2026-08');
    fireEvent.change(payout, { target: { value: '1.00' } });
    fireEvent.change(correction, { target: { value: '-0.50' } });
    fireEvent.click(within(workspace).getByRole('button', { name: 'Speichern' }));

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      'working-time/records/rec-1/',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ paid_hours: '1.00', manual_adjustment: '-0.50' }),
      }),
    ));
  });
});
