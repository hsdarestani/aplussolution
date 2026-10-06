import { expect, Route, test } from '@playwright/test';

const admin = {
  id: 'admin-payroll',
  email: 'payroll@example.test',
  name: 'Payroll Admin',
  first_name: 'Payroll',
  last_name: 'Admin',
  role: 'admin',
  phone: '',
};

let payrollRow = {
  id: 'payroll-row-1',
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

const payrollDetail = {
  ...payrollRow,
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

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

test('admin payroll workspace reconciles daily actual time and paid hours without page overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => {
    localStorage.setItem('access', 'payroll-e2e-access');
    localStorage.setItem('refresh', 'payroll-e2e-refresh');
  });

  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace(/^\/api\//, '');

    if (path === 'auth/me/') return json(route, admin);
    if (path === 'dashboard/') return json(route, {});
    if (path === 'operations/') return json(route, {
      notifications: [], readiness: {}, conflicts: [], unavailable_assignments: [], coverage_gaps: [], overtime_risks: [], swaps: [],
    });
    if (path === 'operations/folders/') return json(route, { workers: [], clients: [] });
    if (path.startsWith('shifts/')) return json(route, []);
    if (path === 'integrations/wiw/status/') return json(route, { configured: false });
    if (path === 'document-catalog/') return json(route, { documents: [], complete: false });
    if (path === 'automation/orders/packages/') return json(route, { results: [] });
    if (path === 'working-time/settings/') return json(route, { employees: [] });
    if (path === 'working-time/records/' && request.method() === 'GET') return json(route, { results: [payrollRow] });
    if (path === 'working-time/records/payroll-row-1/details/') return json(route, payrollDetail);
    if (path === 'working-time/records/payroll-row-1/' && request.method() === 'PATCH') {
      const payload = request.postDataJSON();
      payrollRow = {
        ...payrollRow,
        paid_total_hours: payload.paid_total_hours,
        manual_adjustment: payload.manual_adjustment,
        monthly_balance_hours: '5.00',
        saldo_cumulative: '5.00',
      };
      return json(route, payrollRow);
    }
    return json(route, []);
  });

  await page.goto('/?view=operations#arbeitszeitkonto');
  const workspace = page.getByTestId('payroll-workspace');
  await expect(workspace).toBeVisible();
  await expect(page.getByText('Anna Becker')).toBeVisible();
  await expect(page.getByText('900,00 €').first()).toBeVisible();
  await expect(page.getByText('500,00 €').first()).toBeVisible();

  await workspace.getByRole('button', { name: 'Tagesdetails und Bearbeitung', exact: true }).click();
  await expect(page.getByText('17,50 €')).toBeVisible();
  await expect(page.getByText('Kunde GmbH')).toBeVisible();
  const dailyTable = workspace.getByRole('table', { name: 'Tagesnachweis Anna Becker 2026-08' });
  await expect(dailyTable.getByText('10,00 Std.')).toBeVisible();

  await page.getByLabel('Bezahlte Stunden Anna Becker 2026-08').fill('45');
  await page.getByLabel('Korrektur Anna Becker 2026-08').fill('0');
  await workspace.getByRole('button', { name: 'Speichern', exact: true }).click();
  await expect(page.getByText(/Folgemonate wurden neu berechnet/)).toBeVisible();

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
