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

async function dispatchSwipe(track: ReturnType<Page['locator']>, fromX: number, toX: number) {
  await track.evaluate((element, { fromX, toX }) => {
    const fire = (type: string, x: number, y: number, active: boolean) => {
      const event = new Event(type, { bubbles: true, cancelable: true }) as any;
      const point = { clientX: x, clientY: y };
      Object.defineProperty(event, 'touches', { value: active ? [point] : [] });
      Object.defineProperty(event, 'changedTouches', { value: [point] });
      element.dispatchEvent(event);
    };
    fire('touchstart', fromX, 260, true);
    fire('touchmove', (fromX + toX) / 2, 262, true);
    fire('touchmove', toX, 263, true);
    fire('touchend', toX, 263, false);
  }, { fromX, toX });
}

test('completed swipe never flashes the old center week during async handoff', async ({ page }) => {
  await setup(page);
  await page.goto('/?view=schedule');
  const schedule = page.getByTestId('wiw-native-schedule');
  await expect(schedule).toBeVisible();

  await page.locator('ion-content.app-content').evaluate((element: any) => {
    const original = element.getScrollElement.bind(element);
    element.getScrollElement = async () => {
      await new Promise(resolve => setTimeout(resolve, 90));
      return original();
    };
  });

  const track = schedule.locator('.wiw-week-swipe-track');
  await dispatchSwipe(track, 335, 60);

  await page.waitForTimeout(215);
  const mid = await track.evaluate(element => ({
    transform: getComputedStyle(element).transform,
    active: document.querySelector('.wiw-week-strip button.active b')?.textContent,
  }));
  expect(!(Math.abs(tx(mid.transform)) < 5 && mid.active === '14')).toBeTruthy();

  await page.waitForTimeout(220);
  await expect(schedule.locator('.wiw-week-strip button.active b')).toHaveText('21');
  const endTransform = await track.evaluate(element => getComputedStyle(element).transform);
  expect(Math.abs(tx(endTransform))).toBeLessThan(2);
});

test('adjacent week uses the same geometry and card styling before and after handoff', async ({ page }) => {
  await setup(page);
  await page.goto('/?view=schedule');
  const schedule = page.getByTestId('wiw-native-schedule');
  await expect(schedule).toBeVisible();

  const panes = schedule.locator('.wiw-week-pane');
  await expect(panes).toHaveCount(3);
  const left = panes.nth(0);
  await expect(left.locator('.wiw-shift-card').first()).toBeVisible();

  const preview = await left.evaluate(element => {
    const pane = element.getBoundingClientRect();
    const header = element.querySelector('.wiw-day-visual > header') as HTMLElement;
    const card = element.querySelector('.wiw-shift-card') as HTMLElement;
    const heading = element.querySelector('.wiw-day-heading') as HTMLElement;
    const h = getComputedStyle(header);
    const c = getComputedStyle(card);
    const r = card.getBoundingClientRect();
    return {
      headerHeight: header.getBoundingClientRect().height,
      headerDisplay: h.display,
      headingOffsetX: heading.getBoundingClientRect().x - pane.x,
      cardHeight: r.height,
      cardBackground: c.backgroundImage,
      cardBorder: c.borderLeftColor,
    };
  });

  const track = schedule.locator('.wiw-week-swipe-track');
  await dispatchSwipe(track, 55, 335);
  await page.waitForTimeout(520);
  await expect(schedule.locator('.wiw-week-strip button.active b')).toHaveText('7');

  const center = schedule.locator('.wiw-week-pane').nth(1);
  const active = await center.evaluate(element => {
    const pane = element.getBoundingClientRect();
    const header = element.querySelector('.wiw-day-visual > header') as HTMLElement;
    const card = element.querySelector('.wiw-shift-card') as HTMLElement;
    const heading = element.querySelector('.wiw-day-heading') as HTMLElement;
    const h = getComputedStyle(header);
    const c = getComputedStyle(card);
    const r = card.getBoundingClientRect();
    return {
      headerHeight: header.getBoundingClientRect().height,
      headerDisplay: h.display,
      headingOffsetX: heading.getBoundingClientRect().x - pane.x,
      cardHeight: r.height,
      cardBackground: c.backgroundImage,
      cardBorder: c.borderLeftColor,
    };
  });

  expect(active.headerHeight).toBe(preview.headerHeight);
  expect(active.headerDisplay).toBe(preview.headerDisplay);
  expect(Math.abs(active.headingOffsetX - preview.headingOffsetX)).toBeLessThanOrEqual(1);
  expect(active.cardHeight).toBe(preview.cardHeight);
  expect(active.cardBackground).toBe(preview.cardBackground);
  expect(active.cardBorder).toBe(preview.cardBorder);
});
