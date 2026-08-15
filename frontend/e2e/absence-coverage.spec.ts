import { expect, Page, Route, test } from '@playwright/test';

const worker = {
  id: 'worker-user-absence', email: 'worker@absence.test', name: 'Mina Berger', first_name: 'Mina', last_name: 'Berger', role: 'worker', phone: '',
};
const admin = {
  id: 'admin-user-absence', email: 'admin@absence.test', name: 'Alex Admin', first_name: 'Alex', last_name: 'Admin', role: 'admin', phone: '',
};
const shift = {
  id: 'shift-absence-1',
  client: 'client-1', client_name: 'Main Suites Frankfurt',
  position: 'position-1', position_name: 'Servicekraft',
  location: 'location-1', location_name: 'Frankfurt Innenstadt',
  starts_at: '2026-08-16T10:00:00+02:00', ends_at: '2026-08-16T16:00:00+02:00',
  break_minutes: 30, status: 'confirmed', required_count: 1, filled_count: 1, open_count: 0,
  assignments: [{ slot: 'slot-absence-1', worker: 'worker-profile-1', worker_name: 'Mina Berger' }],
  required_tags: [],
};

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function baseMock(page: Page, user: any, onCallout?: (body: any) => void) {
  await page.addInitScript(() => {
    localStorage.setItem('access', 'absence-e2e-access');
    localStorage.setItem('refresh', 'absence-e2e-refresh');
  });
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace(/^\/api\//, '');
    if (path === 'auth/me/') return json(route, user);
    if (path === 'dashboard/') return json(route, {});
    if (path === 'employee/home/') return json(route, { worker: { name: worker.name }, unread_notifications: 0, next_shift: shift, month_worked_minutes: 0, available_count: 0, contract_actions: 0, contracts_expiring_30: 0, available_shifts: [] });
    if (path.startsWith('shifts/mine/')) return json(route, [shift]);
    if (path.startsWith('shifts/available/')) return json(route, []);
    if (path === 'operations/callouts/report/' && request.method() === 'POST') {
      const body = request.postDataJSON(); onCallout?.(body);
      return json(route, { id: 'case-1', shift: shift.id, slot: 'slot-absence-1', kind: body.kind, status: 'coverage_pending', short_notice: true }, 201);
    }
    if (path.startsWith('admin/exceptions/')) return json(route, { summary: { critical: 0, warning: 0, by_category: {} }, results: [] });
    if (path.startsWith('absence-cases/')) return json(route, user.role === 'admin' ? [{ id: 'case-dashboard-1', status: 'coverage_pending', short_notice: true, shift_title: 'Servicekraft', shift_starts_at: shift.starts_at, shift_ends_at: shift.ends_at }] : []);
    if (path === 'shifts/' || path.startsWith('shifts/?')) return json(route, [shift]);
    if (path === 'workers/') return json(route, []);
    if (path === 'clients/') return json(route, []);
    if (path === 'locations/') return json(route, []);
    if (path === 'positions/') return json(route, []);
    if (path === 'orders/') return json(route, []);
    if (path === 'skill-tags/') return json(route, []);
    return json(route, []);
  });
}

test('worker reports a callout directly from My Shifts', async ({ page }) => {
  let payload: any;
  await page.setViewportSize({ width: 390, height: 844 });
  await baseMock(page, worker, (body) => { payload = body; });
  await page.goto('/?view=schedule');
  await expect(page.getByRole('heading', { name: 'Schichten' })).toBeVisible();
  await page.locator('ion-segment-button[value="mine"]').click();
  await expect(page.getByRole('button', { name: 'Ausfall melden' })).toBeVisible();
  await page.getByRole('button', { name: 'Ausfall melden' }).click();
  await expect(page.getByRole('heading', { name: 'Ausfall melden' })).toBeVisible();
  await page.locator('ion-textarea textarea').fill('Akut krank');
  await page.getByRole('button', { name: 'Ausfall bestätigen' }).click();
  await expect.poll(() => payload).toMatchObject({ shift: shift.id, slot: 'slot-absence-1', kind: 'sick', note: 'Akut krank' });
});

test('admin dashboard surfaces urgent coverage cases', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await baseMock(page, admin);
  await page.goto('/');
  const card = page.getByTestId('absence-dashboard-card');
  await expect(card).toBeVisible();
  await expect(card.getByText('1 offene Ausfälle')).toBeVisible();
  await expect(card.getByText('1 ≤ 24h')).toBeVisible();
  await expect(card.getByRole('button', { name: 'Bearbeiten' })).toBeVisible();
});
