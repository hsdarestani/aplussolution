import { readFileSync } from 'node:fs';
import path from 'node:path';
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
    const pathName = url.pathname.replace(/^\/api\//, '');
    const method = route.request().method();
    if (pathName === 'auth/me/') return json(route, client);
    if (pathName === 'portal/client-dashboard/') return json(route, { role: 'client', active_orders: 1, upcoming_shifts: 1, contracts_to_sign: 0 });
    if (pathName.startsWith('shifts/')) return json(route, scheduleShifts);
    if (pathName.startsWith('orders/')) return json(route, []);
    if (pathName.startsWith('contracts/')) return json(route, []);
    if (pathName.startsWith('documents/')) return json(route, []);
    if (pathName === 'operations/') return json(route, { role: 'client', unread_notifications: 0, open_orders: 0 });
    if (pathName === 'operations/folders/') return json(route, { workers: [], clients: [{ id: 'client-own', name: 'Marthas' }] });
    if (pathName === 'portal/rating-candidates/') return json(route, [{ shift_id: shift.id, worker_id: 'worker-francesco', worker_name: 'Francesco Trulli', position_name: shift.position_name, location_name: shift.location_name, starts_at: shift.starts_at, ends_at: shift.ends_at }]);
    if (pathName.startsWith('ratings/')) {
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

  test('client enhancers are session-keyed so a fresh login does not need a manual refresh', async () => {
    const source = readFileSync(path.join(process.cwd(), 'src/main.tsx'), 'utf8');
    expect(source).toContain('function ClientPortalMount()');
    expect(source).toContain("localStorage.getItem('access')");
    expect(source).toContain('window.setInterval(syncSession, 180)');
    expect(source).toContain('<React.Fragment key={generation}>');
    expect(source).toContain('<ClientPortalMount />');
  });

  test('calendar keeps the complete week strip visible, sticky day labels and admin-style week motion', async ({ page }) => {
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
    const appBar = page.locator('.mobile-appbar');
    await expect(calendar).toBeVisible();
    await expect(calendar).toHaveClass(/wiw-employee-schedule/);
    await expect(calendar).toHaveClass(/wiw-schedule-mobile/);
    await expect(calendar).toHaveClass(/wiw-employee-admin-parity/);
    await expect(calendar.getByRole('tablist')).toHaveCount(0);
    await expect(weekStrip).toHaveClass(/wiw-week-strip/);
    await expect(weekStrip).toHaveCSS('position', 'relative');
    await expect(dayView).toHaveClass(/wiw-week-scroll/);
    await expect(dayView).toHaveAttribute('data-layout', 'list');
    await expect(dayView).toHaveCSS('overflow-y', 'auto');
    await expect(weekTotal).toHaveClass(/wiw-week-total/);
    await expect(weekTotal).toHaveCSS('position', 'relative');

    await expect(calendar.getByText('Francesco T.')).toBeVisible();
    await expect(calendar.getByText('SK').first()).toBeVisible();
    await expect(calendar.getByText('Evangelische Akademie').first()).toBeVisible();
    await expect(calendar.getByText('Gesamtstunden')).toBeVisible();

    const firstVisibleDay = calendar.locator('.wiw-day-section').first();
    const firstVisibleHeader = firstVisibleDay.locator('> header');
    const firstPopulatedDay = calendar.locator('.wiw-day-section:has(.wiw-shift-card)').first();
    const firstPopulatedHeader = firstPopulatedDay.locator('> header');
    const firstCard = firstPopulatedDay.locator('.wiw-shift-card').first();
    await expect(firstVisibleHeader).toBeVisible();
    await expect(firstVisibleHeader).toHaveCSS('position', 'sticky');
    await expect(firstVisibleHeader).toHaveCSS('top', '0px');
    await expect(firstPopulatedHeader).toBeVisible();
    await expect(firstCard).toBeVisible();

    const appBarBox = await appBar.boundingBox();
    const weekBox = await weekStrip.boundingBox();
    const firstVisibleHeaderBox = await firstVisibleHeader.boundingBox();
    const populatedHeaderBox = await firstPopulatedHeader.boundingBox();
    const cardBox = await firstCard.boundingBox();
    expect(appBarBox && weekBox && firstVisibleHeaderBox && populatedHeaderBox && cardBox).toBeTruthy();
    expect(weekBox!.y).toBeGreaterThanOrEqual(appBarBox!.y + appBarBox!.height - 1);
    expect(firstVisibleHeaderBox!.y).toBeGreaterThanOrEqual(weekBox!.y + weekBox!.height - 1);
    expect(cardBox!.y).toBeGreaterThanOrEqual(populatedHeaderBox!.y + populatedHeaderBox!.height - 1);

    const headerTextBefore = await firstVisibleHeader.textContent();
    await dayView.evaluate((element) => { element.scrollTop = Math.min(80, element.scrollHeight - element.clientHeight); element.dispatchEvent(new Event('scroll')); });
    await expect(firstVisibleHeader).toBeVisible();
    await expect(firstVisibleHeader).toHaveText(headerTextBefore || '');
    const scrolledHeaderBox = await firstVisibleHeader.boundingBox();
    const scrollBox = await dayView.boundingBox();
    expect(scrolledHeaderBox && scrollBox).toBeTruthy();
    expect(Math.abs(scrolledHeaderBox!.y - scrollBox!.y)).toBeLessThanOrEqual(2);

    await dayView.dispatchEvent('touchstart', { touches: [{ clientX: 320, clientY: 300 }] });
    await dayView.dispatchEvent('touchmove', { touches: [{ clientX: 180, clientY: 302 }] });
    await expect.poll(() => dayView.evaluate((element: HTMLElement) => element.style.transform)).toContain('translate3d');
    await dayView.dispatchEvent('touchend', { changedTouches: [{ clientX: 120, clientY: 302 }] });
    await expect(calendar.getByTestId('schedule-day-view')).toHaveClass(/wiw-week-turn-next/);

    const totalBox = await weekTotal.boundingBox();
    const navBox = await tabs.boundingBox();
    expect(totalBox && navBox).toBeTruthy();
    expect(Math.abs((totalBox!.y + totalBox!.height) - navBox!.y)).toBeLessThanOrEqual(3);

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
