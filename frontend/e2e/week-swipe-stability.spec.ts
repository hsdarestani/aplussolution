import { expect, test, type Page } from '@playwright/test';

async function setup(page: Page) {
  await page.setViewportSize({ width: 390, height: 700 });
  await page.clock.setFixedTime(new Date('2026-09-14T10:00:00Z'));
  await page.addInitScript(() => localStorage.setItem('access', 'swipe-stability'));

  await page.route('**/api/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace('/api/', '');
    let json: any = [];

    if (path === 'auth/me/') json = { id: 'admin', role: 'admin', first_name: 'Admin', name: 'Admin', email: 'qa@example.test' };
    else if (path === 'admin/mobile-schedule/') {
      const start = url.searchParams.get('date_from') || '2026-09-14';
      const base = new Date(`${start}T12:00:00Z`);
      const shifts = Array.from({ length: 7 }, (_, index) => {
        const date = new Date(base);
        date.setUTCDate(base.getUTCDate() + index);
        const key = date.toISOString().slice(0, 10);
        return {
          id: `${start}-${index}`,
          client: 'client',
          client_name: 'Evangelische Akademie',
          location: 'location',
          location_name: 'Evangelische Akademie',
          position: 'position',
          position_name: 'Servicekraft',
          schedule_groups: ['service'],
          starts_at: `${key}T08:30:00+02:00`,
          ends_at: `${key}T16:30:00+02:00`,
          status: 'published',
          required_count: 2,
          open_count: 0,
          filled_count: 2,
          slot_cards: [0, 1].map(worker => ({
            id: `${start}-${index}-${worker}`,
            status: 'claimed',
            is_open: false,
            worker: { id: `worker-${worker}`, name: worker ? 'Musa Jamali' : 'Tooba Amjad' },
          })),
        };
      });
      json = { date_from: start, date_to: url.searchParams.get('date_to'), shifts };
    } else if (path === 'admin/mobile-dashboard/') json = { open_shift_rows: [] };
    else if (path === 'clients/') json = [{ id: 'client', name: 'Evangelische Akademie', active: true }];
    else if (path === 'locations/') json = [{ id: 'location', client: 'client', name: 'Evangelische Akademie', active: true }];
    else if (path === 'positions/') json = [{ id: 'position', name: 'Servicekraft', active: true }];
    else if (path === 'workers/') json = [
      { id: 'worker-0', active: true, schedule_groups: ['service'], user_detail: { name: 'Tooba Amjad' } },
      { id: 'worker-1', active: true, schedule_groups: ['service'], user_detail: { name: 'Musa Jamali' } },
    ];
    else if (path === 'shifts/') json = [];

    return route.fulfill({ json });
  });
}

async function ionicScrollTop(page: Page) {
  return page.locator('ion-content.app-content').evaluate(async element => {
    const scroll = await (element as any).getScrollElement();
    return scroll.scrollTop;
  });
}

test('horizontal week swipe does not change the vertical viewport', async ({ page }) => {
  await setup(page);
  await page.goto('/?view=schedule');
  const schedule = page.getByTestId('wiw-native-schedule');
  await expect(schedule).toBeVisible();
  await expect(schedule.locator('.wiw-week-pane')).toHaveCount(3);

  await page.locator('ion-content.app-content').evaluate(async element => {
    const scroll = await (element as any).getScrollElement();
    scroll.scrollTop = 220;
    scroll.dispatchEvent(new Event('scroll'));
  });
  await page.waitForTimeout(80);
  const before = await ionicScrollTop(page);
  expect(before).toBeGreaterThan(150);

  await schedule.locator('.wiw-week-swipe-track').evaluate(element => {
    const fire = (type: string, x: number, y: number, active: boolean) => {
      const event = new Event(type, { bubbles: true, cancelable: true }) as any;
      const point = { clientX: x, clientY: y };
      Object.defineProperty(event, 'touches', { value: active ? [point] : [] });
      Object.defineProperty(event, 'changedTouches', { value: [point] });
      element.dispatchEvent(event);
    };
    fire('touchstart', 330, 260, true);
    fire('touchmove', 210, 262, true);
    fire('touchmove', 100, 263, true);
    fire('touchend', 80, 263, false);
  });

  await page.waitForTimeout(520);
  const after = await ionicScrollTop(page);
  expect(Math.abs(after - before)).toBeLessThanOrEqual(2);
  await expect(schedule.locator('.wiw-week-strip button.active b')).toHaveText('21');
});
