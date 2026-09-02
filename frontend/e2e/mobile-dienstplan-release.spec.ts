import { expect, test, type Page } from '@playwright/test';

async function mobileAdmin(page: Page) {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.clock.setFixedTime(new Date('2026-09-02T08:00:00Z'));
  await page.addInitScript(() => {
    localStorage.setItem('access', 'mobile-qa');
    Object.defineProperty(navigator, 'vibrate', { value: () => { (window as any).hapticTicks = ((window as any).hapticTicks || 0) + 1; return true; } });
  });
  const shifts = ['service', 'housekeeping', 'front_office'].map((group, index) => ({
    id: `shift-${index}`, client: 'client', client_name: 'Hotel Spenerhaus', location: 'location', location_name: 'Frankfurt',
    position: `position-${index}`, position_name: ['Servicekraft', 'Housekeeping', 'Front-Office'][index], schedule_groups: [group],
    starts_at: '2026-09-02T10:00:00+02:00', ends_at: '2026-09-02T16:00:00+02:00', status: 'published', required_count: 1,
    open_count: 0, filled_count: 1, slot_cards: [{ id: `slot-${index}`, status: 'claimed', worker: { id: 'tooba', name: 'Tooba Amjad' } }],
  }));
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname.replace('/api/', '');
    let json: any = [];
    if (path === 'auth/me/') json = { id: 'admin', role: 'admin', name: 'Admin', email: 'qa@example.test' };
    if (path === 'admin/mobile-schedule/') json = { shifts };
    if (path === 'admin/mobile-dashboard/') json = { open_shift_rows: [] };
    if (path === 'clients/') json = [{ id: 'client', name: 'Hotel Spenerhaus', active: true }];
    if (path === 'locations/') json = [{ id: 'location', client: 'client', name: 'Frankfurt', active: true }];
    if (path === 'positions/') json = shifts.map(s => ({ id: s.position, name: s.position_name, active: true }));
    if (path === 'workers/') json = ['Tooba Amjad', 'Musa Jamali', 'Akeel Zafar', 'Other Worker'].map((name, index) => ({ id: ['tooba', 'musa', 'akeel', 'other'][index], active: true, user_detail: { name, email: `qa${index}@example.test` } }));
    if (path === 'shifts/' && route.request().method() === 'GET') json = shifts;
    if (route.request().method() === 'PATCH') json = { shift: shifts[0] };
    return route.fulfill({ json });
  });
  await page.goto('/?view=schedule');
  await expect(page.getByTestId('wiw-native-schedule').locator('.wiw-shift-card')).toHaveCount(3);
}

test('mobile filters stay multi-select and worker reassignment replaces the current choice', async ({ page }) => {
  await mobileAdmin(page);
  const schedule = page.getByTestId('wiw-native-schedule');
  const filters = schedule.locator('.wiw-group-filters');
  await filters.getByRole('button', { name: 'Housekeeping', exact: true }).click();
  await expect(schedule.locator('.wiw-shift-card')).toHaveCount(2);
  await filters.getByRole('button', { name: 'Front Office', exact: true }).click();
  await expect(schedule.locator('.wiw-shift-card')).toHaveCount(1);
  await filters.getByRole('button', { name: 'Housekeeping', exact: true }).click();
  await expect(schedule.locator('.wiw-shift-card')).toHaveCount(2);
  await schedule.locator('.wiw-shift-card').filter({ hasText: 'Servicekraft' }).click();
  const form = page.getByTestId('wiw-shift-form');
  await form.locator('.wiw-form-row').filter({ hasText: /^Service$/ }).click();
  let sheet = form.locator('.wiw-choice-sheet');
  await sheet.getByRole('button', { name: 'Housekeeping', exact: true }).click();
  await sheet.getByRole('button', { name: 'Front Office', exact: true }).click();
  await expect(sheet.locator('button.selected')).toHaveCount(3);
  await sheet.getByRole('button', { name: 'Fertig' }).click();
  await expect(form.getByRole('button', { name: /Einsatzort anlegen/ })).toBeEnabled();
  await form.getByRole('button', { name: /Einsatzort anlegen/ }).click();
  await expect(page.locator('.wiw-location-create-sheet .wiw-client-context')).toContainText('Hotel Spenerhaus');
  await page.locator('.wiw-location-create-sheet header').getByRole('button', { name: 'Abbrechen' }).click();
  await form.getByRole('button', { name: /Mitarbeiter ändern/ }).click();
  sheet = form.locator('.wiw-choice-sheet');
  await expect(sheet.getByRole('button', { name: 'Other Worker' })).toHaveCount(0);
  await expect(sheet.locator('div > button')).toHaveText(['Akeel Zafar', 'Musa Jamali', 'Tooba Amjad']);
  await sheet.getByRole('button', { name: 'Musa Jamali' }).click();
  await expect(sheet.locator('button.selected')).toHaveText('Musa Jamali');
  await sheet.getByRole('button', { name: 'Fertig' }).click();
  const assignment = page.waitForRequest(request => request.url().endsWith('/shifts/shift-0/assign/') && request.method() === 'POST');
  await form.getByRole('button', { name: 'Sichern', exact: true }).click();
  expect((await assignment).postDataJSON().workers).toEqual(['musa']);
});

test('dense time wheel emits feedback and notes can reopen without locking the form', async ({ page }) => {
  await mobileAdmin(page);
  await page.getByRole('button', { name: 'Schicht anlegen', exact: true }).click();
  await page.getByRole('button', { name: /Manuell.*WIW-Formular öffnen/ }).click();
  const form = page.getByTestId('wiw-shift-form');
  await form.getByRole('button', { name: /Wähle Zeitrahmen/ }).click();
  const wheel = page.getByTestId('wiw-time-wheel');
  const firstColumn = wheel.locator('.wiw-wheel-column').first();
  const next = firstColumn.locator('button.active + button');
  await expect(next).toHaveCSS('height', '32px');
  const selected = await next.textContent();
  await next.click();
  await expect(firstColumn.locator('button.active')).toHaveText(selected!);
  await expect.poll(() => page.evaluate(() => (window as any).hapticTicks || 0)).toBeGreaterThan(0);
  await form.getByRole('button', { name: 'Füge Notiz hinzu' }).click();
  await form.locator('textarea').fill('Testnotiz');
  await form.getByRole('button', { name: 'Notiz bearbeiten' }).click();
  await expect(form.locator('textarea')).toHaveCount(0);
  await form.getByRole('button', { name: 'Notiz bearbeiten' }).click();
  await expect(form.locator('textarea')).toHaveValue('Testnotiz');
  await form.getByRole('button', { name: 'Abbrechen', exact: true }).click();
  await page.locator('.wiw-pdf-button').click();
  const pdf = page.locator('.wiw-pdf-sheet');
  await pdf.getByRole('button', { name: 'Service', exact: true }).click();
  await pdf.getByRole('button', { name: 'Front Office', exact: true }).click();
  await pdf.getByRole('button', { name: 'Housekeeping', exact: true }).click();
  await expect(pdf.locator('.compact button.active')).toHaveCount(3);
});
