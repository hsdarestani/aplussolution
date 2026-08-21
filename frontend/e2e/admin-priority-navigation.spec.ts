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

test('admin start exposes Ashkan priorities 1-5 directly on mobile and desktop', async ({ page }) => {
  for (const viewport of [{ width: 390, height: 844 }, { width: 1440, height: 1000 }]) {
    await openAdminHome(page, viewport.width, viewport.height);
    const priorities = page.getByTestId('admin-priority-actions');
    await expect(priorities).toBeVisible();
    await expect(priorities.getByRole('button')).toHaveCount(5);
    for (const label of ['Auftrag & AI', 'Dienstplanung', 'Zeiterfassung', 'Arbeitszeit & Lohn', 'Personal & Kunden']) {
      await expect(priorities.getByRole('button', { name: label, exact: true })).toBeAttached();
    }
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  }
});
