import { expect, Page, Route, test } from '@playwright/test';

async function fulfill(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function mockApi(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('access', 'masterdata-e2e-access');
    localStorage.setItem('refresh', 'masterdata-e2e-refresh');
  });

  const now = Date.now();
  const locations = Array.from({ length: 7 }, (_, index) => ({
    id: `loc-${index}`,
    name: index === 6 ? 'QA Newest Testsite' : `Standort ${index + 1}`,
    address: `Teststraße ${index + 1}, Frankfurt am Main`,
    client_name: 'QA Kunde',
    active: true,
    created_at: new Date(now - (6 - index) * 60_000).toISOString(),
  }));
  const positions = ['Servicekraft', 'Serviceleitung', 'Front Office', 'Housekeeping', 'Bar-Support'].map((name, index) => ({
    id: `pos-${index}`,
    name,
    color: '#155eef',
    active: true,
    created_at: new Date(now - (4 - index) * 60_000).toISOString(),
  }));

  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api\//, '');
    if (path === 'auth/me/') return fulfill(route, {
      id: 'admin-1', email: 'admin@example.test', name: 'A+ Admin', first_name: 'A+', last_name: 'Admin', role: 'admin', phone: '',
    });
    if (path.startsWith('workers/portal-status/')) return fulfill(route, []);
    if (path.startsWith('workers/')) return fulfill(route, []);
    if (path.startsWith('clients/')) return fulfill(route, [{ id: 'client-1', name: 'QA Kunde', active: true }]);
    if (path.startsWith('locations/')) return fulfill(route, locations);
    if (path.startsWith('positions/')) return fulfill(route, positions);
    return fulfill(route, []);
  });
}

// Phase 1 intentionally moved master-data administration out of Personal & Kunden.
test('settings owns locations and positions after Personal & Kunden cleanup', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  await page.goto('/?view=settings');

  await expect(page.getByRole('heading', { name: 'Einstellungen' })).toBeVisible();
  const masterDataPanels = page.locator('.master-data > .panel');
  const locationsPanel = masterDataPanels.nth(0);
  const positionsPanel = masterDataPanels.nth(1);
  await expect(locationsPanel.getByRole('heading', { name: 'Einsatzorte' })).toBeVisible();
  await expect(positionsPanel.getByRole('heading', { name: 'Positionen' })).toBeVisible();
  await expect(locationsPanel.getByText('QA Newest Testsite', { exact: true })).toBeVisible();
  await expect(locationsPanel.getByText('Standort 1', { exact: true })).toBeVisible();

  await positionsPanel.getByRole('button', { name: 'Position', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Position anlegen' })).toBeVisible();
  await expect(page.locator('ion-input[type="color"]')).toBeVisible();
});