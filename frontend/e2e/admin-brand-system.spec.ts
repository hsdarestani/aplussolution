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

for (const width of [1440, 1024]) {
  test(`admin brand navigation ${width}`, async ({ page }) => {
    await openAdminHome(page, width, 1000);
    await expect(page.locator('.ap-workspace-header')).toBeVisible();
    await expect(page.getByText('Alles im Blick. Jeder Einsatz zählt.')).toBeVisible();
    const priorities = page.getByTestId('admin-priority-actions');
    await expect(priorities).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
    await expect(page.locator('.admin-attention-hero ion-button')).toContainText('Aktualisieren');
    await page.screenshot({ path: `test-results/admin-brand-${width}.png`, fullPage: true });
    if (width === 390) {
      await page.getByTestId('admin-priority-actions').scrollIntoViewIfNeeded();
      await page.screenshot({ path: 'test-results/admin-brand-mobile-actions.png' });
    }
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
    if (label === 'Zeiterfassung') await expect(page.locator('.attendance-head')).toBeVisible();
    if (label === 'Anfragen, Berichte & Verwaltung') await expect(page.locator('.operations-stats')).toBeVisible();
    if (label === 'Einstellungen') await expect(page.getByRole('button', { name: 'Einsatzort anlegen', exact: true })).toBeVisible();
    await page.screenshot({ path: `test-results/module-${label.replace(/[^a-zA-Z]/g, '')}.png`, fullPage: true });
  }
});

test('settings form retains editable fields and cancel action', async ({ page }) => {
  await openAdminHome(page, 1440, 1000);
  await page.locator('.app > aside ion-item').filter({ hasText: 'Einstellungen' }).click();
  await page.getByRole('button', { name: 'Einsatzort anlegen', exact: true }).click();
  const modal = page.locator('ion-modal').filter({ has: page.getByText('Einsatzort anlegen', {exact: true}) });
  await expect(modal).toBeVisible();
  const name = modal.locator('ion-input').filter({ hasText: 'Bezeichnung' }).locator('input');
  await name.fill('Test Einsatzort');
  await expect(name).toHaveValue('Test Einsatzort');
  await page.screenshot({path: 'test-results/settings-location-form.png'});
  await modal.getByRole('button', {name: 'Abbrechen', exact: true}).click();
  await expect(modal).toBeHidden();
});

test('mobile design is preserved and desktop styling is removed on resize', async ({ page }) => {
  await openAdminHome(page, 1440, 1000);
  await expect(page.locator('.ap-workspace-header')).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator('[data-admin-web="true"]')).toHaveCount(0);
  await expect(page.locator('body')).not.toHaveAttribute('data-ap-admin-web', 'true');
  await expect(page.locator('.ap-workspace-header')).toHaveCount(0);
  await expect(page.getByTestId('wiw-mobile-admin-dashboard')).toBeVisible();
  await expect(page.getByTestId('admin-priority-actions')).toBeHidden();
  await expect(page.locator('.admin-attention-hero h1')).toHaveText('Nur das, was heute Aufmerksamkeit braucht.');
  await page.screenshot({ path: 'test-results/restored-mobile.png' });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await expect(page.locator('.ap-workspace-header')).toBeVisible();
  await expect(page.getByTestId('admin-priority-actions')).toBeVisible();
});
