import { expect, test } from '@playwright/test';
for (const width of [1440, 390]) {
  test(`weekly export in admin browser ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.addInitScript(() => { localStorage.setItem('access', 'test'); localStorage.setItem('refresh', 'test'); });
    await page.route('**/api/**', async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith('/reports/stundenzettel.pdf')) {
        expect(new URL(route.request().url()).searchParams.get('week')).toBe('2026-W45');
        return route.fulfill({ status: 200, contentType: 'application/pdf', headers: { 'Content-Disposition': 'attachment; filename="Stundenzettel - HK - KW45.pdf"' }, body: '%PDF-1.4\ntest' });
      }
      const body = path.endsWith('/auth/me/') ? { id: 'test-admin', email: 'admin@example.test', name: 'Admin', role: 'admin' } : path.includes('exceptions') ? { summary: {}, results: [] } : [];
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    });
    await page.goto('/');
    const panel = page.getByRole('region', { name: 'Stundenzettel exportieren' });
    await expect(panel).toBeVisible();
    await panel.scrollIntoViewIfNeeded();
    await panel.getByLabel('Kalenderwoche').fill('2026-W45');
    const download = page.waitForEvent('download');
    await panel.getByRole('button', { name: 'Housekeeping · PDF' }).click();
    expect((await download).suggestedFilename()).toBe('Stundenzettel - HK - KW45.pdf');
    expect(await panel.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
    await panel.screenshot({ path: `test-results/stundenzettel-${width}.png` });
  });
}
