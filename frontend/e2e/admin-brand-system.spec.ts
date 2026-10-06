import { expect, test } from '@playwright/test';

const admin = {
  id: 'admin-priority-user',
  email: 'admin@example.test',
  name: 'Alex Admin',
  first_name: 'Alex',
  last_name: 'Admin',
  role: 'admin',
  phone: '',
};

async function openAdminHome(page: any, width: number, height: number) {
  await page.setViewportSize({ width, height });
  await page.addInitScript(() => {
    localStorage.setItem('access', 'priority-e2e-access');
    localStorage.setItem('refresh', 'priority-e2e-refresh');
  });
  await page.route('**/api/**', async (route: any) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api\//, '');
    const body = path === 'auth/me/'
      ? admin
      : path.startsWith('admin/exceptions/')
        ? { summary: { critical: 0, warning: 0, by_category: {} }, results: [] }
        : [];
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
  await page.goto('/');
}

for (const width of [1440, 1024, 390]) {
  test(`admin brand navigation ${width}`, async ({ page }) => {
    await openAdminHome(page, width, 1000);
    await expect(page.locator('.ap-workspace-header')).toBeVisible();
    await expect(page.getByText('Alles im Blick. Jeder Einsatz zählt.')).toBeVisible();
    const priorities = page.getByTestId('admin-priority-actions');
    await expect(priorities).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
    await page.screenshot({ path: `test-results/admin-brand-${width}.png`, fullPage: true });
    await priorities.getByRole('button', { name: 'Personal & Kunden', exact: true }).click();
    await expect(page.locator('.ap-workspace-header h1')).toHaveText(/Personal|Mitarbeiter/);
  });
}

test('desktop modules share the brand frame and preserve navigation', async ({ page }) => {
  await openAdminHome(page, 1440, 1000);
  for (const label of ['Dienstplan', 'Zeiterfassung', 'Lohn & Dokumente', 'Mitteilungen', 'Anfragen, Berichte & Verwaltung', 'Personal & Kunden', 'Einstellungen', 'Verträge & ANÜ']) {
    await page.locator('.app > aside ion-item').filter({ hasText: label }).click();
    await expect(page.locator('.ap-workspace-header h1')).toHaveText(label);
    await expect(page.locator('.app-main')).toBeVisible();
    await page.screenshot({ path: `test-results/module-${label.replace(/[^a-zA-Z]/g, '')}.png`, fullPage: true });
  }
});
