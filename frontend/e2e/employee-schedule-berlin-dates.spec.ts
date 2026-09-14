import { expect, test } from '@playwright/test';

const shifts = [
  {
    id: 'peer-sep16',
    client_name: 'Evangelische Akademie',
    location_name: 'Evangelische Akademie',
    position_name: 'Servicekraft',
    starts_at: '2026-09-16T08:30:00+02:00',
    ends_at: '2026-09-16T19:00:00+02:00',
    break_minutes: 0,
    status: 'confirmed',
    assigned_workers: [{ id: 'tooba', name: 'Tooba Ahmadi', is_me: false }],
  },
  {
    id: 'own-sep16',
    client_name: 'A+',
    location_name: 'A+',
    position_name: 'Servicekraft',
    starts_at: '2026-09-16T15:30:00+02:00',
    ends_at: '2026-09-16T21:00:00+02:00',
    break_minutes: 0,
    status: 'confirmed',
    assigned_workers: [{ id: 'arina', name: 'Arina Martynko', is_me: true }],
  },
  {
    id: 'historical-2024',
    client_name: 'Evangelische Akademie',
    location_name: 'Evangelische Akademie',
    position_name: 'Servicekraft',
    starts_at: '2024-09-17T11:00:00+02:00',
    ends_at: '2024-09-17T21:00:00+02:00',
    break_minutes: 0,
    status: 'confirmed',
    assigned_workers: [{ id: 'tooba', name: 'Tooba Ahmadi', is_me: false }],
  },
];

test('employee Dienstplan keeps the weekly calendar and shows Service Zeitplan peer cards', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 780 });
  await page.clock.setFixedTime(new Date('2026-09-14T12:00:00Z'));
  await page.addInitScript(() => {
    localStorage.setItem('access', 'employee-date-regression');
    localStorage.setItem('refresh', 'employee-date-regression-refresh');
  });

  await page.route('**/api/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace(/^\/api\//, '');
    let body: any = [];

    if (path === 'auth/me/') {
      body = {
        id: 'worker-date-regression',
        email: 'arina@example.test',
        name: 'Arina Martynko',
        first_name: 'Arina',
        last_name: 'Martynko',
        role: 'worker',
      };
    } else if (path.startsWith('employee/schedule/')) {
      body = { service_schedule: true, shifts };
    } else if (path.startsWith('shifts/available/')) {
      body = [];
    } else if (path === 'employee/home/') {
      body = { worker: { name: 'Arina Martynko' }, unread_notifications: 0, available_shifts: [] };
    } else if (path === 'operations/') {
      body = { notifications: [], unread_notifications: 0 };
    }

    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });

  await page.goto('/?view=schedule');
  const schedule = page.getByTestId('wiw-employee-schedule');
  await expect(schedule).toBeVisible();
  await expect(schedule.getByText('Service Zeitplan')).toBeVisible();
  await expect(page.getByTestId('phase8-week-strip')).toBeVisible();

  const days = schedule.locator('.wiw-employee-day');
  await expect(days).toHaveCount(7);
  await expect(days.nth(0).locator('header')).toContainText('Mo');
  await expect(days.nth(0).locator('header')).toContainText('14.09.');
  await expect(days.nth(2).locator('header')).toContainText('Mi');
  await expect(days.nth(2).locator('header')).toContainText('16.09.');

  const wednesdayCards = days.nth(2).locator('.wiw-employee-shift-card');
  await expect(wednesdayCards).toHaveCount(2);
  await expect(wednesdayCards.nth(0)).toContainText('Tooba A.');
  await expect(wednesdayCards.nth(0)).toContainText('08:30–19:00');
  await expect(wednesdayCards.nth(1)).toContainText('Arina M.');
  await expect(wednesdayCards.nth(1)).toContainText('15:30–21:00');

  // Historical WIW rows may still be returned by the API, but they must never
  // replace the selected/current week in the worker calendar.
  await expect(schedule).not.toContainText('11:00–21:00');

  // Service peer hours are visible but must not inflate the logged-in worker's total.
  const total = page.getByTestId('phase8-week-total');
  await expect(total).toContainText('Eigene Gesamtstunden');
  await expect(total).toContainText('5.5');

  await wednesdayCards.nth(0).click();
  const detail = page.getByTestId('wiw-employee-shift-detail');
  await expect(detail).toContainText('Tooba A.');
  await expect(detail.getByRole('button', { name: 'Nur sichtbar · Service Zeitplan' })).toBeDisabled();
});
