import { expect, Page, Route, test } from '@playwright/test';

const client = {
  id: 'client-visual-qa',
  email: 'visual.client@example.test',
  name: 'Marthas',
  first_name: 'Marthas',
  last_name: '',
  role: 'client',
  phone: '',
};

function todayShift() {
  const start = new Date();
  start.setUTCHours(8, 30, 0, 0);
  const end = new Date(start.getTime() + 8.5 * 60 * 60 * 1000);
  return {
    id: 'shift-client-visual',
    client: 'client-own',
    client_name: 'Marthas',
    position: 'position-service',
    position_name: 'Servicekraft',
    location: 'location-own',
    location_name: 'Evangelische Akademie',
    starts_at: start.toISOString(),
    ends_at: end.toISOString(),
    break_minutes: 30,
    status: 'confirmed',
    open_count: 0,
    assigned_workers: [{ id: 'worker-francesco', slot_id: 'slot-francesco', name: 'Francesco Trulli', is_me: false }],
  };
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function mockClient(page: Page, state: { ratingPost?: any }) {
  const shift = todayShift();
  const scheduleShifts = [shift, ...Array.from({ length: 11 }, (_, index) => ({
    ...shift,
    id: `shift-client-scroll-${index}`,
    assigned_workers: [{
      id: `worker-scroll-${index}`,
      slot_id: `slot-scroll-${index}`,
      name: `Mitarbeiter ${index + 1}`,
      is_me: false,
    }],
  }))];
  await page.addInitScript(() => {
    localStorage.setItem('access', 'client-visual-token');
    localStorage.setItem('refresh', 'client-visual-refresh');
  });
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api\//, '');
    const method = route.request().method();
    if (path === 'auth/me/') return json(route, client);
    if (path === 'portal/client-dashboard/') return json(route, { role: 'client', active_orders: 1, upcoming_shifts: 1, contracts_to_sign: 0 });
    if (path.startsWith('shifts/')) return json(route, scheduleShifts);
    if (path.startsWith('orders/')) return json(route, []);
    if (path.startsWith('contracts/')) return json(route, []);
    if (path.startsWith('documents/')) return json(route, []);
    if (path === 'operations/') return json(route, { role: 'client', unread_notifications: 0, open_orders: 0 });
    if (path === 'operations/folders/') return json(route, { workers: [], clients: [{ id: 'client-own', name: 'Marthas' }] });
    if (path === 'portal/rating-candidates/') return json(route, [{ shift_id: shift.id, worker_id: 'worker-francesco', worker_name: 'Francesco Trulli', position_name: shift.position_name, location_name: shift.location_name, starts_at: shift.starts_at, ends_at: shift.ends_at }]);
    if (path.startsWith('ratings/')) {
      if (method === 'POST') {
        state.ratingPost = route.request().postDataJSON();
        return json(route, { id: 'rating-new', worker_name: 'Francesco Trulli', created_at: new Date().toISOString(), ...state.ratingPost }, 201);
      }
      return json(route, []);
    }
    return json(route, []);
  });
}

test.describe('client portal visual parity', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('calendar matches workforce rows and keeps chrome stable while only the list scrolls', async ({ page }) => {
    const state: { ratingPost?: any } = {};
    await mockClient(page, state);
    await page.goto('/');

    const tabs = page.getByTestId('client-v2-tabbar');
    await expect(tabs.getByRole('button')).toHaveCount(4);
    await tabs.getByRole('button', { name: 'Kalender' }).click();

    const calendar = page.getByTestId('client-v3-schedule');
    const weekStrip = calendar.getByTestId('phase8-week-strip');
    const dayView = calendar.getByTestId('schedule-day-view');
    const weekTotal = calendar.getByTestId('phase8-week-total');
    await expect(calendar).toBeVisible();
    await expect(calendar.getByRole('tablist', { name: 'Einsatzfilter' })).toBeHidden();
    await expect(weekStrip).toBeVisible();
    await expect(dayView).toHaveAttribute('data-layout', 'list');
    await expect(calendar.getByText('Francesco T.')).toBeVisible();
    await expect(calendar.getByText('Servicekraft').first()).toBeVisible();
    await expect(calendar.getByText('Evangelische Akademie').first()).toBeVisible();
    await expect(calendar.getByText('Gesamtstunden')).toBeVisible();

    const card = calendar.locator('.client-v3-shift-card').first();
    await expect(card).toHaveClass(/wiw-shift-card/);
    await expect(card).toHaveCSS('background-color', 'rgb(255, 255, 255)');
    await expect(card).toHaveCSS('border-left-style', 'none');
    const accent = await card.evaluate((element) => getComputedStyle(element, '::before').backgroundColor);
    expect(accent).not.toBe('rgba(0, 0, 0, 0)');

    await expect(calendar).toHaveCSS('display', 'flex');
    await expect(calendar).toHaveCSS('overflow-y', 'hidden');
    await expect(weekStrip).toHaveCSS('position', 'relative');
    await expect(dayView).toHaveCSS('overflow-y', 'auto');
    await expect(weekTotal).toHaveCSS('position', 'relative');

    const header = page.locator('.mobile-appbar');
    const headerBox = await header.boundingBox();
    const weekBefore = await weekStrip.boundingBox();
    const totalBefore = await weekTotal.boundingBox();
    expect(headerBox).toBeTruthy();
    expect(weekBefore).toBeTruthy();
    expect(totalBefore).toBeTruthy();
    expect(weekBefore!.y).toBeGreaterThanOrEqual(headerBox!.y + headerBox!.height - 1);

    await dayView.evaluate((element) => { element.scrollTop = element.scrollHeight; });
    await expect.poll(() => dayView.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
    const weekAfter = await weekStrip.boundingBox();
    const totalAfter = await weekTotal.boundingBox();
    expect(Math.abs(weekAfter!.y - weekBefore!.y)).toBeLessThanOrEqual(1);
    expect(Math.abs(totalAfter!.y - totalBefore!.y)).toBeLessThanOrEqual(1);

    await dayView.evaluate((element) => { element.scrollTop = 0; });
    await card.click();
    await expect(page.getByTestId('client-v3-shift-detail')).toBeVisible();
    await expect(page.getByText('Einsatzdetails')).toBeVisible();

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });

  test('rating screen is custom, compact and submits the selected client candidate', async ({ page }) => {
    const state: { ratingPost?: any } = {};
    await mockClient(page, state);
    await page.goto('/');

    const tabs = page.getByTestId('client-v2-tabbar');
    await tabs.getByRole('button', { name: 'Mitarbeiter bewerten' }).click();
    const ratings = page.getByTestId('client-v3-ratings');
    await expect(ratings).toBeVisible();
    await expect(ratings.getByText('Noch keine Bewertungen')).toBeVisible();
    await ratings.getByRole('button', { name: /Neue Bewertung/ }).click();

    const dialog = page.getByRole('dialog', { name: 'Einsatz bewerten' });
    await dialog.getByLabel('Einsatz', { exact: true }).selectOption('shift-client-visual');
    await dialog.getByLabel('Mitarbeiter', { exact: true }).selectOption('worker-francesco');
    await dialog.getByRole('radio', { name: '4 Sterne' }).first().click();
    await dialog.getByRole('button', { name: 'Bewertung speichern' }).click();

    await expect.poll(() => state.ratingPost).toBeTruthy();
    expect(state.ratingPost.shift).toBe('shift-client-visual');
    expect(state.ratingPost.worker).toBe('worker-francesco');
    await expect(ratings.getByText('Bewertung wurde gespeichert.')).toBeVisible();
  });
});
