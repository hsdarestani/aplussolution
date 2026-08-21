import { expect, Page, Route, test } from '@playwright/test';

const admin = {
  id: 'admin-timezone-qa',
  email: 'admin@example.test',
  name: 'A+ Admin',
  first_name: 'A+',
  last_name: 'Admin',
  role: 'admin',
  phone: '',
};

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function mockAdminApi(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('access', 'orders-timezone-e2e');
    localStorage.setItem('refresh', 'orders-timezone-refresh');
  });

  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api\//, '');

    if (path === 'auth/me/') return json(route, admin);
    if (path === 'dashboard/') {
      return json(route, {
        workers: 1,
        clients: 1,
        open_shifts: 0,
        pending_time_off: 0,
        contracts_due: 0,
        upcoming_shifts: [],
      });
    }
    if (path.startsWith('orders/')) {
      return json(route, [
        {
          id: 'order-timezone-qa',
          title: 'QA Client Order',
          client: 'client-own',
          client_name: 'QA Client Portal GmbH',
          location: 'location-own',
          location_name: 'QA Client Portal Standort',
          starts_at: '2026-08-22T16:59:00Z',
          ends_at: '2026-08-22T21:00:00Z',
          requested_staff: 2,
          functions: [],
          status: 'planning',
        },
      ]);
    }
    if (path.startsWith('clients/')) return json(route, []);
    if (path === 'locations/') return json(route, []);
    if (path === 'positions/') return json(route, []);
    return json(route, []);
  });
}

test.use({ timezoneId: 'Asia/Tehran' });

test('orders render Europe/Berlin business time even on a Tehran device', async ({ page }) => {
  await mockAdminApi(page);
  await page.goto('/');
  await page.getByText('Auftragseingang & AI', { exact: true }).first().click();

  const order = page.getByText('QA Client Order').locator('..');
  await expect(page.getByText('QA Client Order')).toBeVisible();
  await expect(page.getByText(/18:59/)).toBeVisible();
  await expect(page.getByText(/20:29/)).toHaveCount(0);
  await expect(order).toBeVisible();
});
