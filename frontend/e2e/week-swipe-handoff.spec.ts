import { expect, test, type Page } from '@playwright/test';

async function setup(page: Page, options: { dense?: boolean; previousGate?: Promise<void> } = {}) {
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
      if (start === '2026-09-07') await options.previousGate;
      const slots = options.dense && start === '2026-09-14' ? 8 : 1;
      const shifts = Array.from({ length: 7 }, (_, index) => {
        const date = new Date(`${start}T12:00:00Z`);
        date.setUTCDate(date.getUTCDate() + index);
        const key = date.toISOString().slice(0, 10);
        return {
          id: `${start}-${index}`,
          client: 'client', client_name: 'Martha’s finest',
          location: 'location', location_name: 'Evangelische Akademie',
          position: 'position', position_name: 'Servicekraft', schedule_groups: ['service'],
          starts_at: `${key}T08:30:00+02:00`, ends_at: `${key}T16:30:00+02:00`,
          status: 'published', required_count: slots, open_count: 0, filled_count: slots,
          slot_cards: Array.from({ length: slots }, (_, slot) => ({
            id: `${start}-${index}-slot-${slot}`, status: 'claimed', is_open: false,
            worker: { id: `worker-${slot}`, name: 'Tooba Amjad' },
          })),
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


test('shorter week keeps the current list visible during the drag and reuses the destination logos', async ({ page }) => {
  await setup(page, { dense: true });
  await page.goto('/?view=schedule');
  const schedule = page.getByTestId('wiw-native-schedule');
  const track = schedule.locator('.wiw-week-swipe-track');
  const previous = track.locator('.wiw-week-pane-prev[data-week-ready="true"]');
  await expect(previous).toBeAttached();
  const logo = previous.locator('.wiw-client-logo img').first();
  await expect(logo).toHaveAttribute('loading', 'eager');
  await logo.evaluate((image) => {
    (window as any).destinationLogo = image;
  });
  await page.locator('ion-content.app-content').evaluate(async (element: HTMLIonContentElement) => {
    (await element.getScrollElement()).scrollTop = 1700;
  });
  const initial = await track.evaluate((element) => {
    const previousPane = element.querySelector('.wiw-week-pane-prev')!;
    const center = element.querySelector('.wiw-week-pane-center')!;
    return {
      previousBottom: previousPane.getBoundingClientRect().bottom,
      centerBottom: center.getBoundingClientRect().bottom,
    };
  });
  expect(initial.previousBottom).toBeLessThan(0);
  expect(initial.centerBottom).toBeGreaterThan(700);

  await track.evaluate(async (element) => {
    for (const [type, x] of [['touchstart', 40], ['touchmove', 360]] as const) {
      const event = new Event(type, { bubbles: true, cancelable: true });
      Object.defineProperty(event, 'touches', { value: [{ clientX: x, clientY: 260 }] });
      element.dispatchEvent(event);
    }
    await new Promise(requestAnimationFrame);
  });
  expect(Math.abs(tx(await track.evaluate(element => getComputedStyle(element).transform)))).toBeLessThan(2);

  await track.evaluate((element) => {
    const event = new Event('touchend', { bubbles: true, cancelable: true });
    Object.defineProperty(event, 'changedTouches', { value: [{ clientX: 360, clientY: 260 }] });
    element.dispatchEvent(event);
  });
  await expect(schedule.locator('.wiw-week-strip button.active b')).toHaveText('7');
  const center = track.locator('.wiw-week-pane-center');
  const retained = await center.locator('.wiw-client-logo img').first().evaluate((image) => image === (window as any).destinationLogo);
  expect(retained).toBe(true);
  await expect(center.locator('.wiw-shift-card').last()).toBeInViewport();
});

test('uncached destination waits on the visible week until its shifts arrive', async ({ page }) => {
  let releasePrevious!: () => void;
  const previousGate = new Promise<void>((resolve) => { releasePrevious = resolve; });
  await setup(page, { previousGate });
  try {
    await page.goto('/?view=schedule');
    const schedule = page.getByTestId('wiw-native-schedule');
    const track = schedule.locator('.wiw-week-swipe-track');
    const active = schedule.locator('.wiw-week-strip button.active b');
    const total = schedule.locator('.wiw-week-total strong');
    await expect(total).toHaveText('56.0');
    await dispatchSwipe(track, 55, 335);
    await expect(track).toHaveAttribute('aria-busy', 'true');
    await expect(active).toHaveText('14');
    await expect(total).toHaveText('56.0');
    await expect(track.locator('.wiw-week-pane-center .wiw-shift-card').first()).toBeInViewport();
    releasePrevious();
    await expect(active).toHaveText('7');
    await expect(track).toHaveAttribute('aria-busy', 'false');
    await expect(track.locator('.wiw-week-pane-center .wiw-shift-card').first()).toBeInViewport();
  } finally {
    releasePrevious();
  }
});
