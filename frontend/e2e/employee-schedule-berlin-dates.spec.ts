import { expect, test } from '@playwright/test';

const shifts = [
  {
    id: 'sep17',
    client_name: 'Evangelische Akademie',
    location_name: 'Evangelische Akademie',
    position_name: 'Servicekraft',
    starts_at: '2026-09-17T16:00:00+02:00',
    ends_at: '2026-09-17T21:00:00+02:00',
    break_minutes: 0,
    status: 'confirmed',
  },
  {
    id: 'sep20',
    client_name: 'A+',
    location_name: 'A+',
    position_name: 'Servicekraft',
    starts_at: '2026-09-20T12:00:00+02:00',
    ends_at: '2026-09-20T18:00:00+02:00',
    break_minutes: 0,
    status: 'confirmed',
  },
];

test('employee Dienstplan keeps Berlin weekday, date and time aligned', async ({ page }) => {
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
    } else if (path.startsWith('shifts/mine/')) {
      body = shifts;
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

  const days = schedule.locator('.wiw-employee-day');
  await expect(days).toHaveCount(2);

  await expect(days.nth(0).locator('header')).toContainText('Do');
  await expect(days.nth(0).locator('header')).toContainText('17.09.');
  await expect(days.nth(0).locator('.wiw-employee-shift-card').first()).toContainText('16:00–21:00');

  await expect(days.nth(1).locator('header')).toContainText('So');
  await expect(days.nth(1).locator('header')).toContainText('20.09.');
  await expect(days.nth(1).locator('.wiw-employee-shift-card').first()).toContainText('12:00–18:00');
});
