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

test('admin start uses WIW hierarchy on mobile and keeps desktop priority shortcuts', async ({ page }) => {
  await openAdminHome(page, 390, 844);
  const wiw = page.getByTestId('wiw-mobile-admin-dashboard');
  await expect(wiw).toBeVisible();
  for (const label of ['Arbeitszeit-Hinweise', 'Mitarbeiteraktivität', 'Abwesenheitsanträge', 'Schichtanfragen', 'OpenShift-Anfragen', 'Schichten', 'OpenShifts verfügbar']) {
    await expect(wiw.getByRole('button', { name: label, exact: true })).toBeVisible();
  }
  await expect(page.getByTestId('admin-priority-actions')).toBeHidden();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);

  await openAdminHome(page, 1440, 1000);
  const priorities = page.getByTestId('admin-priority-actions');
  await expect(priorities).toBeVisible();
  await expect(priorities.getByRole('button')).toHaveCount(5);
  for (const label of ['Dienstplan', 'Zeiterfassung', 'Lohn & Anfragen', 'Personal & Kunden', 'Mitteilungen']) {
    await expect(priorities.getByRole('button', { name: label, exact: true })).toBeAttached();
  }
});
