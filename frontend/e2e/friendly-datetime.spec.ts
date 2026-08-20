import { expect, Page, Route, test } from '@playwright/test';

async function fulfill(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function mockAdmin(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('access', 'friendly-datetime-access');
    localStorage.setItem('refresh', 'friendly-datetime-refresh');
  });

  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api\//, '');
    if (path === 'auth/me/') return fulfill(route, {
      id: 'admin-1', email: 'admin@example.test', name: 'A+ Admin', first_name: 'A+', last_name: 'Admin', role: 'admin', phone: '',
    });
    if (path.startsWith('shifts/')) return fulfill(route, []);
    if (path.startsWith('clients/')) return fulfill(route, [{ id: 'client-1', name: 'A+', active: true }]);
    if (path.startsWith('locations/')) return fulfill(route, [{ id: 'location-1', client: 'client-1', name: 'QA Frankfurt Testsite', active: true }]);
    if (path.startsWith('positions/')) return fulfill(route, [{ id: 'position-1', name: 'QA Servicekraft', active: true }]);
    if (path.startsWith('orders/')) return fulfill(route, []);
    if (path.startsWith('workers/')) return fulfill(route, []);
    return fulfill(route, []);
  });
}

test('shift form uses separate friendly date and time controls', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockAdmin(page);
  await page.goto('/?view=schedule');

  await expect(page.getByRole('heading', { name: 'Personalbedarf & Schichten' })).toBeVisible();
  await page.getByRole('button', { name: 'Personalbedarf' }).click();

  const start = page.getByTestId('datetime-beginn');
  const end = page.getByTestId('datetime-ende');
  await expect(start).toBeVisible();
  await expect(end).toBeVisible();
  await expect(start.getByRole('button', { name: 'Heute' })).toBeVisible();
  await expect(start.getByRole('button', { name: 'Morgen' })).toBeVisible();
  await expect(start.getByLabel('Beginn Datum')).toBeVisible();
  await expect(start.getByLabel('Beginn Uhrzeit')).toBeVisible();
  await expect(end.getByLabel('Ende Datum')).toBeVisible();
  await expect(end.getByLabel('Ende Uhrzeit')).toBeVisible();
  await expect(page.locator('ion-input[type="datetime-local"]')).toHaveCount(0);

  await start.getByRole('button', { name: 'Morgen' }).click();
  await expect(start.getByLabel('Beginn Datum')).not.toHaveValue('');
  await expect(end.getByLabel('Ende Datum')).not.toHaveValue('');

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
