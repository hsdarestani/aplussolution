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

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

test('admin payroll workspace shows monthly figures and persists adjustments without page overflow', async ({ page }) => {
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
    if (path === 'working-time/records/payroll-row-1/' && request.method() === 'PATCH') {
      const payload = request.postDataJSON();
      payrollRow = {
        ...payrollRow,
        paid_hours: payload.paid_hours,
        manual_adjustment: payload.manual_adjustment,
        saldo_cumulative: '0.50',
      };
      return json(route, payrollRow);
    }
    return json(route, []);
  });

  await page.goto('/?view=operations#arbeitszeitkonto');
  const workspace = page.getByTestId('payroll-workspace');
  await expect(workspace).toBeVisible();
  await expect(page.getByText('Anna Becker')).toBeVisible();
  await expect(page.getByText('1.400,00 €').first()).toBeVisible();

  // Mobile payroll cards are intentionally compact. Expand the employee card before
  // checking the hourly rate and edit controls that live inside the details section.
  await workspace.getByRole('button', { name: 'Details & Bearbeiten', exact: true }).click();
  await expect(page.getByText('17,50 €')).toBeVisible();

  await page.getByLabel('Auszahlung Anna Becker 2026-08').fill('1');
  await page.getByLabel('Korrektur Anna Becker 2026-08').fill('-0.5');
  await workspace.getByRole('button', { name: 'Speichern', exact: true }).click();
  await expect(page.getByText(/Folgemonate wurden neu berechnet/)).toBeVisible();

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
