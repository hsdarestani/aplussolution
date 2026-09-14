import { expect, test, type Page } from '@playwright/test';

async function mockAdmin(page: Page) {
  await page.setViewportSize({ width: 390, height: 500 });
  await page.clock.setFixedTime(new Date('2026-09-14T10:00:00Z'));
  await page.addInitScript(() => localStorage.setItem('access', 'sep14-regression'));

  const avatar = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="32" height="32"%3E%3Crect width="32" height="32" fill="%23999"/%3E%3C/svg%3E';
  const shifts = [
    ['service', 'Servicekraft', 'Tooba Amjad', avatar, '08:30:00', '15:30:00'],
    ['front_office', 'Front-Office', 'Musa Jamali', '', '09:00:00', '16:00:00'],
    ['housekeeping', 'Housekeeping', 'Shaha Ahmad', '', '10:00:00', '17:00:00'],
  ].map(([group, position, name, workerAvatar, start, end], index) => ({
    id: `shift-${index}`,
    client: 'client',
    client_name: 'Evangelische Akademie',
    location: 'location',
    location_name: 'Evangelische Akademie',
    position: `position-${index}`,
    position_name: position,
    schedule_groups: [group],
    starts_at: `2026-09-14T${start}+02:00`,
    ends_at: `2026-09-14T${end}+02:00`,
    status: 'published',
    required_count: 1,
    open_count: 0,
    filled_count: 1,
    slot_cards: [{
      id: `slot-${index}`,
      status: 'claimed',
      is_open: false,
      worker: { id: `worker-${index}`, name, avatar: workerAvatar },
    }],
  }));

  await page.route('**/api/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace('/api/', '');
    let json: any = [];
    if (path === 'auth/me/') json = { id: 'admin', role: 'admin', first_name: 'Admin', name: 'Admin', email: 'qa@example.test' };
    else if (path === 'admin/mobile-schedule/') json = { shifts };
    else if (path === 'admin/mobile-dashboard/') json = { open_shift_rows: [] };
    else if (path === 'clients/') json = [{ id: 'client', name: 'Evangelische Akademie', active: true }];
    else if (path === 'locations/') json = [{ id: 'location', client: 'client', name: 'Evangelische Akademie', active: true }];
    else if (path === 'positions/') json = shifts.map(shift => ({ id: shift.position, name: shift.position_name, active: true }));
    else if (path === 'workers/') json = shifts.map((shift, index) => ({ id: `worker-${index}`, active: true, schedule_groups: shift.schedule_groups, user_detail: { name: shift.slot_cards[0].worker.name } }));
    else if (path === 'shifts/') json = shifts;
    else if (path === 'attendance/exceptions/') json = { history: [], counts: {}, pending_corrections: [], unapproved_entries: [], long_running_entries: [] };
    else if (path === 'attendance/history/') json = { history: [], count: 0 };
    else if (path === 'time-off/') json = [];
    return route.fulfill({ json });
  });
}

test('current week stays centered, day header sticks, avatar fallback is stable, and time view has no global search', async ({ page }) => {
  await mockAdmin(page);
  await page.goto('/?view=schedule');

  const schedule = page.getByTestId('wiw-native-schedule');
  await expect(schedule).toBeVisible();
  const panes = schedule.locator('.wiw-week-pane');
  await expect(panes).toHaveCount(3);

  const rects = await panes.evaluateAll(elements => elements.map(element => {
    const rect = element.getBoundingClientRect();
    return { left: rect.left, right: rect.right, width: rect.width };
  }));
  expect(rects[0].right).toBeLessThanOrEqual(1);
  expect(Math.abs(rects[1].left)).toBeLessThanOrEqual(1);
  expect(rects[1].width).toBeGreaterThan(380);
  expect(rects[2].left).toBeGreaterThanOrEqual(389);

  const firstDay = panes.nth(1).locator('.wiw-day-section').first();
  expect(await firstDay.evaluate(element => element.firstElementChild?.tagName)).toBe('HEADER');
  const header = firstDay.locator(':scope > header');
  await expect(header).toHaveCSS('position', 'sticky');

  const cards = firstDay.locator('.wiw-shift-card');
  await expect(cards).toHaveCount(3);
  await expect(cards.filter({ hasText: 'Tooba A.' }).locator('.wiw-worker-avatar-image')).toBeVisible();
  const fallback = cards.filter({ hasText: 'Musa J.' }).locator('.wiw-worker-avatar-fallback');
  await expect(fallback).toBeVisible();
  await expect(fallback).toHaveCSS('width', '32px');
  await expect(fallback).toHaveCSS('height', '32px');

  const personAndTime = await cards.filter({ hasText: 'Musa J.' }).locator('.wiw-card-line.primary').evaluate(element => {
    const person = element.querySelector('.wiw-card-person')!.getBoundingClientRect();
    const time = element.children[element.children.length - 1].getBoundingClientRect();
    return { personLeft: person.left, personRight: person.right, timeLeft: time.left };
  });
  expect(personAndTime.personLeft).toBeLessThan(personAndTime.timeLeft);
  expect(personAndTime.personRight).toBeLessThanOrEqual(personAndTime.timeLeft);

  await page.locator('ion-content.app-content').evaluate(async element => {
    const scroll = await (element as any).getScrollElement();
    scroll.scrollTop = 110;
    scroll.dispatchEvent(new Event('scroll'));
  });
  await page.waitForTimeout(80);
  const stickyBox = await header.boundingBox();
  const weekBox = await schedule.locator('.wiw-week-strip').boundingBox();
  expect(stickyBox).not.toBeNull();
  expect(weekBox).not.toBeNull();
  expect(Math.abs(stickyBox!.y - (weekBox!.y + weekBox!.height))).toBeLessThanOrEqual(2);

  await page.goto('/?view=time');
  await expect(page.getByText('Abrechnungszeiträume')).toBeVisible();
  await expect(page.locator('.app-main > .global-search')).toHaveCount(0);
});
