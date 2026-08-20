import { expect, Page, Route, test } from '@playwright/test';

async function fulfill(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function mockAdmin(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('access', 'berlin-schedule-access');
    localStorage.setItem('refresh', 'berlin-schedule-refresh');
  });

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

test.use({ timezoneId: 'Asia/Tehran' });

test('schedule always shows German business time regardless of device timezone', async ({ page }) => {
  await mockAdmin(page);
  await page.goto('/?view=schedule');

  await expect(page.getByRole('heading', { name: 'Personalbedarf & Schichten' })).toBeVisible();
  const shiftCard = page.locator('.sv2-card').filter({ hasText: 'QA Servicekraft' }).first();
  await expect(shiftCard).toContainText('10:00–14:00');
  await expect(shiftCard).toContainText('1/2 besetzt · 1 frei');
  await expect(shiftCard).not.toContainText('11:30–15:30');
  await expect(shiftCard.locator('.sv2-date b')).toHaveText('21');
});
