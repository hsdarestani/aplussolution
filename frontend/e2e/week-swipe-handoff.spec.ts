import { expect, test, type Page } from '@playwright/test';

async function setup(page: Page) {
  await page.setViewportSize({ width: 390, height: 700 });
  await page.clock.setFixedTime(new Date('2026-09-14T10:00:00Z'));
  await page.addInitScript(() => localStorage.setItem('access', 'swipe-handoff'));

  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace('/api/', '');
    let json: any = [];
    if (path === 'auth/me/') json = { id: 'admin', role: 'admin', first_name: 'Admin', name: 'Admin', email: 'qa@example.test' };
    else if (path === 'admin/mobile-schedule/') {
      const start = url.searchParams.get('date_from') || '2026-09-14';
      const shifts = Array.from({ length: 7 }, (_, index) => {
        const date = new Date(`${start}T12:00:00Z`);
        date.setUTCDate(date.getUTCDate() + index);
        const key = date.toISOString().slice(0, 10);
        return {
          id: `${start}-${index}`,
          client: 'client', client_name: 'Evangelische Akademie',
          location: 'location', location_name: 'Evangelische Akademie',
          position: 'position', position_name: 'Servicekraft', schedule_groups: ['service'],
          starts_at: `${key}T08:30:00+02:00`, ends_at: `${key}T16:30:00+02:00`,
          status: 'published', required_count: 1, open_count: 0, filled_count: 1,
          slot_cards: [{ id: `${start}-${index}-slot`, status: 'claimed', is_open: false, worker: { id: 'worker', name: 'Tooba Amjad' } }],
        };
      });
      json = { shifts };
    } else if (path === 'admin/mobile-dashboard/') json = { open_shift_rows: [] };
    else if (path === 'clients/') json = [{ id: 'client', name: 'Evangelische Akademie', active: true }];
    else if (path === 'locations/') json = [{ id: 'location', client: 'client', name: 'Evangelische Akademie', active: true }];
    else if (path === 'positions/') json = [{ id: 'position', name: 'Servicekraft', active: true }];
    else if (path === 'workers/') json = [{ id: 'worker', active: true, schedule_groups: ['service'], user_detail: { name: 'Tooba Amjad' } }];
    else if (path === 'shifts/') json = [];
    return route.fulfill({ json });
  });
}

function tx(transform: string) {
  if (transform === 'none') return 0;
  const m = /matrix\([^,]+,[^,]+,[^,]+,[^,]+,\s*([-\d.]+)/.exec(transform);
  return m ? Number(m[1]) : 0;
}

test('completed swipe never flashes the old center week during async handoff', async ({ page }) => {
  await setup(page);
  await page.goto('/?view=schedule');
  const schedule = page.getByTestId('wiw-native-schedule');
  await expect(schedule).toBeVisible();

  // Deliberately slow Ionic scroll lookup. The old implementation reset the
  // track immediately while changeWeek awaited this promise, exposing the old
  // center week for a visible frame. The fixed implementation keeps the incoming
  // week at the endpoint until state + transform can be committed atomically.
  await page.locator('ion-content.app-content').evaluate((element: any) => {
    const original = element.getScrollElement.bind(element);
    element.getScrollElement = async () => {
      await new Promise(resolve => setTimeout(resolve, 90));
      return original();
    };
  });

  const track = schedule.locator('.wiw-week-swipe-track');
  await track.evaluate(element => {
    const fire = (type: string, x: number, y: number, active: boolean) => {
      const event = new Event(type, { bubbles: true, cancelable: true }) as any;
      const point = { clientX: x, clientY: y };
      Object.defineProperty(event, 'touches', { value: active ? [point] : [] });
      Object.defineProperty(event, 'changedTouches', { value: [point] });
      element.dispatchEvent(event);
    };
    fire('touchstart', 335, 260, true);
    fire('touchmove', 170, 262, true);
    fire('touchmove', 80, 263, true);
    fire('touchend', 60, 263, false);
  });

  await page.waitForTimeout(215);
  const mid = await track.evaluate(element => ({
    transform: getComputedStyle(element).transform,
    active: document.querySelector('.wiw-week-strip button.active b')?.textContent,
  }));
  // While getScrollElement is still pending we must either still be holding the
  // incoming pane at about -1 viewport, or already have the new active week. We
  // must never be back at transform 0 with the old 14th active.
  expect(!(Math.abs(tx(mid.transform)) < 5 && mid.active === '14')).toBeTruthy();

  await page.waitForTimeout(220);
  await expect(schedule.locator('.wiw-week-strip button.active b')).toHaveText('21');
  const endTransform = await track.evaluate(element => getComputedStyle(element).transform);
  expect(Math.abs(tx(endTransform))).toBeLessThan(2);
});
