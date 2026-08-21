import { expect, Page, Route, test } from '@playwright/test';

async function fulfill(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

const shift = {
  id: 'shift-berlin-1',
  client_name: 'A+',
  position_name: 'QA Servicekraft',
  location_name: 'QA Frankfurt Testsite',
  starts_at: '2026-08-21T10:00:00+02:00',
  ends_at: '2026-08-21T14:00:00+02:00',
  break_minutes: 15,
  status: 'published',
  required_count: 2,
  filled_count: 1,
  open_count: 1,
  assigned_workers: [{ id: 'worker-1', name: 'QA Mina Berger' }],
};

async function mockAdmin(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('access', 'berlin-schedule-access');
    localStorage.setItem('refresh', 'berlin-schedule-refresh');
  });

  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api\//, '');
    if (path === 'auth/me/') return fulfill(route, {
      id: 'admin-1', email: 'admin@example.test', name: 'A+ Admin', first_name: 'A+', last_name: 'Admin', role: 'admin', phone: '',
    });
    if (path.startsWith('shifts/')) return fulfill(route, [shift]);
    if (path.startsWith('clients/')) return fulfill(route, [{ id: 'client-1', name: 'A+', active: true }]);
    if (path.startsWith('locations/')) return fulfill(route, [{ id: 'location-1', client: 'client-1', name: 'QA Frankfurt Testsite', active: true }]);
    if (path.startsWith('positions/')) return fulfill(route, [{ id: 'position-1', name: 'QA Servicekraft', active: true }]);
    if (path.startsWith('orders/')) return fulfill(route, []);
    if (path.startsWith('workers/')) return fulfill(route, []);
    return fulfill(route, []);
  });
}

async function mockWorker(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('access', 'berlin-worker-access');
    localStorage.setItem('refresh', 'berlin-worker-refresh');
  });

  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api\//, '');
    if (path === 'auth/me/') return fulfill(route, {
      id: 'worker-user-1', email: 'qa.leon@example.test', name: 'QA Leon Fischer', first_name: 'QA Leon', last_name: 'Fischer', role: 'worker', phone: '',
    });
    if (path === 'employee/home/') return fulfill(route, {
      worker: { name: 'QA Leon Fischer', employee_number: 'QA-1002', employment_type: 'teilzeit' },
      next_shift: { ...shift, filled_count: 2, open_count: 0 },
      available_count: 1,
      available_shifts: [{ ...shift, id: 'shift-open-2', filled_count: 0, open_count: 2 }],
      month_worked_minutes: 0,
      contract_actions: 0,
      contracts_expiring_30: 0,
      unread_notifications: 1,
    });
    return fulfill(route, []);
  });
}

test.use({ timezoneId: 'Asia/Tehran' });

const fixedNow = new Date('2026-08-21T08:00:00Z');

test('schedule always shows German business time regardless of device timezone', async ({ page }) => {
  await page.clock.setFixedTime(fixedNow);
  await mockAdmin(page);
  await page.goto('/?view=schedule');

  await expect(page.getByRole('heading', { name: 'Personalbedarf & Schichten' })).toBeVisible();
  const shiftCard = page.locator('.sv2-card').filter({ hasText: 'QA Servicekraft' }).first();
  await expect(shiftCard).toContainText('10:00–14:00');
  await expect(shiftCard).toContainText('1/2 besetzt · 1 frei');
  await expect(shiftCard).not.toContainText('11:30–15:30');
  await expect(shiftCard.locator('.sv2-date b')).toHaveText('21');
});

test('worker home always shows German business time regardless of device timezone', async ({ page }) => {
  await page.clock.setFixedTime(fixedNow);
  await mockWorker(page);
  await page.goto('/?view=home');

  await expect(page.getByRole('heading', { name: 'QA Leon Fischer' })).toBeVisible();
  const nextShift = page.locator('.next-shift-card').filter({ hasText: 'QA Servicekraft' }).first();
  await expect(nextShift).toContainText('10:00–14:00');
  await expect(nextShift).not.toContainText('11:30–15:30');

  const openShift = page.locator('.available-mini').filter({ hasText: 'QA Servicekraft' }).first();
  await expect(openShift).toContainText('10:00');
  await expect(openShift).not.toContainText('11:30');
});
