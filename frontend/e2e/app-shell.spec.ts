import { expect, Page, Route, test } from '@playwright/test';

type Role = 'admin' | 'manager' | 'worker' | 'client';

const worker = {
  id: 'worker-user-1',
  email: 'worker@example.test',
  name: 'Mina Berger',
  first_name: 'Mina',
  last_name: 'Berger',
  role: 'worker' as Role,
  phone: '',
};

const admin = {
  id: 'admin-user-1',
  email: 'admin@example.test',
  name: 'Alex Admin',
  first_name: 'Alex',
  last_name: 'Admin',
  role: 'admin' as Role,
  phone: '',
};

const client = {
  id: 'client-user-1',
  email: 'lara@main-suites.example.test',
  name: 'Lara Becker',
  first_name: 'Lara',
  last_name: 'Becker',
  role: 'client' as Role,
  phone: '',
};

const hoursFromNow = (hours: number) => new Date(Date.now() + hours * 60 * 60 * 1000).toISOString();

const availableShift = {
  id: 'shift-1',
  client_name: 'Main Suites Frankfurt',
  position_name: 'Servicekraft',
  location_name: 'Frankfurt Innenstadt',
  starts_at: hoursFromNow(4),
  ends_at: hoursFromNow(11),
  break_minutes: 30,
  status: 'published',
  required_count: 4,
  filled_count: 2,
  open_count: 2,
};

const mineShift = {
  ...availableShift,
  id: 'shift-mine-1',
  filled_count: 4,
  open_count: 0,
};

async function fulfill(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

async function mockApi(page: Page, user: typeof worker | typeof admin | typeof client, seenPaths?: string[]) {
  await page.addInitScript(() => {
    localStorage.setItem('access', 'phase6-e2e-access');
    localStorage.setItem('refresh', 'phase6-e2e-refresh');
  });

  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api\//, '');
    seenPaths?.push(path);

    if (path === 'auth/me/') return fulfill(route, user);

    if (path === 'dashboard/') {
      return fulfill(route, user.role === 'client' ? {
        active_orders: 2,
        upcoming_shifts: 1,
        contracts_to_sign: 1,
      } : {});
    }

    if (path === 'employee/home/') {
      return fulfill(route, {
        worker: { name: worker.name, employee_number: 'MA-2048', employment_type: 'Teilzeit' },
        unread_notifications: 2,
        next_shift: availableShift,
        month_worked_minutes: 2325,
        available_count: 2,
        contract_actions: 1,
        contracts_expiring_30: 0,
        available_shifts: [availableShift],
      });
    }

    if (path.startsWith('shifts/available/')) return fulfill(route, [availableShift]);
    if (path.startsWith('shifts/mine/')) return fulfill(route, [mineShift]);

    if (path === 'attendance/home/') {
      return fulfill(route, {
        active_entry: null,
        eligible_shift: availableShift,
        month_worked_minutes: 2325,
        pending_corrections: 0,
        history: [],
        corrections: [],
      });
    }
    if (path === 'attendance/exceptions/') {
      return fulfill(route, {
        counts: {
          pending_corrections: 0,
          unapproved_entries: 0,
          long_running_entries: 1,
          total: 1,
        },
        pending_corrections: [],
        unapproved_entries: [],
        long_running_entries: [
          {
            id: 'entry-long-1',
            worker_name: 'Mina Berger',
            clock_in: hoursFromNow(-13),
          },
        ],
      });
    }
    if (path === 'time-off/') return fulfill(route, []);

    if (path.startsWith('admin/exceptions/')) {
      return fulfill(route, {
        summary: {
          critical: 1,
          warning: 2,
          by_category: { staffing: 1, attendance: 1, contracts: 1, documents: 0, integrations: 0, requests: 0 },
        },
        results: [
          {
            category: 'staffing',
            severity: 'critical',
            title: 'Schicht noch nicht vollständig besetzt',
            message: 'Main Suites Frankfurt · 2 von 4 Positionen besetzt',
            view: 'schedule',
            object_id: 'shift-1',
            meta: { open_count: 2, filled_count: 2, required_count: 4 },
          },
        ],
      });
    }

    if (path === 'shifts/' || path.startsWith('shifts/?')) return fulfill(route, [availableShift]);
    if (path === 'clients/') return fulfill(route, []);
    if (path === 'locations/') return fulfill(route, []);
    if (path === 'positions/') return fulfill(route, []);
    if (path === 'orders/') return fulfill(route, []);

    return fulfill(route, []);
  });
}

async function expectNoHorizontalPageOverflow(page: Page) {
  await expect.poll(() => page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }))).toEqual(expect.objectContaining({ scrollWidth: expect.any(Number), clientWidth: expect.any(Number) }));

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, 'page must not create horizontal viewport overflow').toBeLessThanOrEqual(1);
}

test.describe('Phase 6 mobile QA', () => {
  test('worker can move through primary flows and gets an app-native release confirmation', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockApi(page, worker);
    await page.goto('/');

    await expect(page.getByRole('heading', { name: 'Mina Berger' })).toBeVisible();
    await expect(page.locator('.mobile-tabbar')).toBeVisible();
    await expect(page.locator('.mobile-tabbar button')).toHaveCount(4);
    await expect(page.locator('aside')).toBeHidden();
    await expectNoHorizontalPageOverflow(page);

    await page.locator('.mobile-tabbar button').filter({ hasText: 'Dienstplan' }).click();
    await expect(page.getByTestId('phase8-week-strip')).toBeVisible();
    await expect(page.getByText('Servicekraft', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('Main Suites Frankfurt', { exact: true }).first()).toBeVisible();
    await expectNoHorizontalPageOverflow(page);

    await page.locator('ion-segment-button[value="mine"]').click();
    await expect(page.getByRole('button', { name: 'Freigeben' })).toBeVisible();
    await page.getByRole('button', { name: 'Freigeben' }).click();
    await expect(page.getByText('Schicht freigeben?', { exact: true })).toBeVisible();
    await expect(page.getByText('wird wieder für andere Mitarbeiter verfügbar.', { exact: false })).toBeVisible();
    await page.getByRole('button', { name: 'Abbrechen' }).click();
    await expect(page.getByText('Schicht freigeben?', { exact: true })).toBeHidden();

    await page.locator('.mobile-tabbar button').filter({ hasText: 'Zeiterfassung' }).click();
    await expect(page.getByTestId('phase8-pay-periods')).toBeVisible();
    await expect(page.getByText('Abrechnungszeiträume', { exact: true })).toBeVisible();
    await expectNoHorizontalPageOverflow(page);

    await page.getByRole('button', { name: 'Weitere Bereiche öffnen' }).click();
    await expect(page.getByRole('heading', { name: 'Weitere Bereiche' })).toBeVisible();
    const moreMenu = page.locator('.mobile-menu-grid');
    await expect(moreMenu.getByRole('button', { name: 'Meine Verträge', exact: true })).toBeVisible();
    await expect(moreMenu.getByRole('button', { name: 'Dokumente', exact: true })).toBeVisible();
    await expect(moreMenu.getByRole('button', { name: 'Ranking', exact: true })).toBeVisible();
    await expect(moreMenu.getByRole('button', { name: 'Mitteilungen', exact: true })).toBeVisible();
  });

  test('worker deep links survive refresh and browser history while role guards stay enforced', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockApi(page, worker);
    await page.goto('/?view=schedule');

    await expect(page.getByTestId('phase8-week-strip')).toBeVisible();
    await expect.poll(() => new URL(page.url()).searchParams.get('view')).toBe('schedule');

    await page.reload();
    await expect(page.getByTestId('phase8-week-strip')).toBeVisible();
    await expect.poll(() => new URL(page.url()).searchParams.get('view')).toBe('schedule');

    await page.locator('.mobile-tabbar button').filter({ hasText: 'Zeiterfassung' }).click();
    await expect(page.getByTestId('phase8-pay-periods')).toBeVisible();
    await expect.poll(() => new URL(page.url()).searchParams.get('view')).toBe('time');

    await page.goBack();
    await expect(page.getByTestId('phase8-week-strip')).toBeVisible();
    await expect.poll(() => new URL(page.url()).searchParams.get('view')).toBe('schedule');

    await page.goForward();
    await expect(page.getByTestId('phase8-pay-periods')).toBeVisible();
    await expect.poll(() => new URL(page.url()).searchParams.get('view')).toBe('time');

    await page.goto('/?view=people');
    await expect(page.getByRole('heading', { name: 'Mina Berger' })).toBeVisible();
    await expect.poll(() => new URL(page.url()).searchParams.get('view')).toBeNull();
  });

  test('admin exception center and timer-close reason dialog stay usable on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockApi(page, admin);
    await page.goto('/');

    await expect(page.getByTestId('admin-exception-center')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Nur das, was heute Aufmerksamkeit braucht.' })).toBeVisible();
    await expect(page.getByText('Schicht noch nicht vollständig besetzt')).toBeVisible();
    await expect(page.locator('.mobile-tabbar button')).toHaveCount(4);
    await expectNoHorizontalPageOverflow(page);

    await page.locator('.mobile-tabbar button').filter({ hasText: 'Zeiterfassung' }).click();
    await expect(page.getByRole('heading', { name: /Ungewöhnlich lange (laufende Timer|offene Zeiterfassungen)/ })).toBeVisible();
    await page.getByRole('button', { name: /Timer beenden|Prüfen & schließen/ }).click();
    const closeAlert = page.locator('ion-alert');
    await expect(closeAlert).toBeVisible();
    await expect(closeAlert.locator('textarea')).toBeVisible();
    await closeAlert.locator('textarea').fill('E2E Prüfung');
    await page.getByRole('button', { name: 'Abbrechen' }).click();
    await expect(closeAlert).toBeHidden();

    await page.getByRole('button', { name: 'Weitere Bereiche öffnen' }).click();
    const moreMenu = page.locator('.mobile-menu-grid');
    await expect(moreMenu.getByRole('button', { name: 'Verträge & ANÜ', exact: true })).toBeVisible();
    await expect(moreMenu.getByRole('button', { name: 'Lohn & Dokumente', exact: true })).toBeVisible();
    await expect(moreMenu.getByRole('button', { name: 'Anfragen, Berichte & Verwaltung', exact: true })).toBeVisible();
  });

  test('client sees a client-scoped schedule without manager controls or manager API fan-out', async ({ page }) => {
    const seenPaths: string[] = [];
    await page.setViewportSize({ width: 390, height: 844 });
    await mockApi(page, client, seenPaths);
    await page.goto('/');

    await expect(page.getByRole('heading', { name: 'Guten Tag, Lara' })).toBeVisible();
    await expect(page.getByText('Personal genau dann, wenn du es brauchst.')).toBeVisible();
    await expect(page.getByText('Aktive Aufträge')).toBeVisible();
    await expect(page.getByText('Zu unterzeichnen')).toBeVisible();
    await expect(page.locator('.mobile-tabbar button')).toHaveCount(4);
    await expectNoHorizontalPageOverflow(page);

    await page.locator('.mobile-tabbar button').filter({ hasText: 'Dienstplan' }).click();
    await expect(page.getByRole('heading', { name: 'Einsätze', exact: true })).toBeVisible();
    await expect(page.getByText('Geplante Einsätze und aktueller Besetzungsstatus für Ihre Aufträge.')).toBeVisible();
    await expect(page.getByText('Servicekraft', { exact: true }).first()).toBeVisible();
    await expect(page.locator('ion-segment')).toHaveCount(0);
    await expect(page.getByRole('button', { name: /Personalbedarf/i })).toHaveCount(0);
    await expectNoHorizontalPageOverflow(page);

    expect(seenPaths).not.toContain('clients/');
    expect(seenPaths).not.toContain('locations/');
    expect(seenPaths).not.toContain('positions/');
    expect(seenPaths).not.toContain('orders/');

    await page.getByRole('button', { name: 'Weitere Bereiche öffnen' }).click();
    const moreMenu = page.locator('.mobile-menu-grid');
    await expect(moreMenu.getByRole('button', { name: 'Servicecenter', exact: true })).toBeVisible();
    await expect(moreMenu.getByRole('button', { name: 'Aufträge', exact: true })).toBeVisible();
    await expect(moreMenu.getByRole('button', { name: 'Verträge & Signatur', exact: true })).toBeVisible();
    await expect(moreMenu.getByRole('button', { name: 'Mitarbeiter bewerten', exact: true })).toBeVisible();
  });
});

test.describe('Phase 6 desktop smoke', () => {
  test('admin shell keeps full navigation and opens staffing from the exception center', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await mockApi(page, admin);
    await page.goto('/');

    await expect(page.locator('aside')).toBeVisible();
    await expect(page.locator('.mobile-tabbar')).toBeHidden();
    await expect(page.getByTestId('admin-exception-center')).toBeVisible();

    const adminNav = page.locator('aside ion-list ion-item ion-label');
    await expect(adminNav).toHaveText([
      'Übersicht',
      'Dienstplan',
      'Zeiterfassung',
      'Lohn & Dokumente',
      'Mitteilungen',
      'Anfragen, Berichte & Verwaltung',
      'Personal & Kunden',
      'Einstellungen',
      'Verträge & ANÜ',
      'Profil',
    ]);

    await page.getByRole('button', { name: 'Öffnen' }).first().click();
    await expect(page.getByRole('heading', { name: 'Personalbedarf & Schichten' })).toBeVisible();
    await expect(page.getByText('Servicekraft', { exact: true }).first()).toBeVisible();
    await expectNoHorizontalPageOverflow(page);
  });

  test('worker desktop keeps the familiar schedule-attendance-mitteilungen-requests structure', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await mockApi(page, worker);
    await page.goto('/');

    const workerNav = page.locator('aside ion-list ion-item ion-label');
    await expect(workerNav).toHaveText([
      'Start',
      'Mein Dienstplan',
      'Zeiterfassung',
      'Mitteilungen',
      'Anfragen',
      'Dokumente',
      'Meine Verträge',
      'Ranking',
      'Profil',
    ]);
  });
});