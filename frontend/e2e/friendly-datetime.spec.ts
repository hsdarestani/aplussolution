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

test('shift form replaces browser date/time interaction with the global friendly picker', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockAdmin(page);
  await page.goto('/?view=schedule');

  await expect(page.getByRole('heading', { name: 'Personalbedarf & Schichten' })).toBeVisible();
  await page.getByTestId('schedule-create-manual').click();

  const start = page.getByTestId('datetime-beginn');
  const end = page.getByTestId('datetime-ende');
  const startDate = start.locator('ion-input[aria-label="Beginn Datum"]');
  const startTime = start.locator('ion-input[aria-label="Beginn Uhrzeit"]');
  const endDate = end.locator('ion-input[aria-label="Ende Datum"]');
  const endTime = end.locator('ion-input[aria-label="Ende Uhrzeit"]');

  await expect(start).toBeVisible();
  await expect(end).toBeVisible();
  await expect(start.getByRole('button', { name: 'Heute' })).toBeVisible();
  await expect(start.getByRole('button', { name: 'Morgen' })).toBeVisible();

  await expect(startDate).toHaveAttribute('data-aplus-picker-kind', 'date');
  await expect(startDate).toHaveAttribute('type', 'date');
  await expect(startDate).toHaveAttribute('readonly', '');
  await expect(startTime).toHaveAttribute('data-aplus-picker-kind', 'time');
  await expect(startTime).toHaveAttribute('type', 'time');
  await expect(startTime).toHaveAttribute('readonly', '');
  await expect(endDate).toHaveAttribute('data-aplus-picker-kind', 'date');
  await expect(endTime).toHaveAttribute('data-aplus-picker-kind', 'time');

  await startDate.click();
  const picker = page.locator('ion-modal.friendly-picker-modal');
  await expect(picker).toBeVisible();
  await expect(picker.getByRole('heading', { name: 'Beginn Datum' })).toBeVisible();
  await expect(picker.getByRole('button', { name: 'Heute' })).toBeVisible();
  await expect(picker.getByRole('button', { name: 'Morgen' })).toBeVisible();

  await picker.getByRole('button', { name: 'Morgen' }).click();
  await picker.getByRole('button', { name: 'Übernehmen' }).click();
  await expect(picker).not.toBeVisible();
  await expect.poll(async () => startDate.evaluate((element: any) => String(element.value || ''))).not.toBe('');
  await expect.poll(async () => endDate.evaluate((element: any) => String(element.value || ''))).not.toBe('');

  await startTime.click();
  await expect(picker).toBeVisible();
  await expect(picker.getByRole('heading', { name: 'Beginn Uhrzeit' })).toBeVisible();
  await expect(picker.getByRole('button', { name: 'Jetzt' })).toBeVisible();
  await expect(picker.locator('ion-datetime[presentation="time"]')).toBeVisible();
  await picker.getByRole('button', { name: 'Abbrechen' }).click();
  await expect(picker).not.toBeVisible();

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
