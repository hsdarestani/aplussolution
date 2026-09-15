import { expect, test } from '@playwright/test';

const shifts = [
  {
    id: 'previous-week',
    client_name: 'Evangelische Akademie',
    location_name: 'Evangelische Akademie',
    position_name: 'Servicekraft',
    starts_at: '2026-09-10T09:00:00+02:00',
    ends_at: '2026-09-10T15:00:00+02:00',
    break_minutes: 0,
    status: 'confirmed',
    assigned_workers: [{ id: 'prev', name: 'Previous Worker', is_me: false }],
  },
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
    id: 'next-week',
    client_name: 'Evangelische Akademie',
    location_name: 'Evangelische Akademie',
    position_name: 'Servicekraft',
    starts_at: '2026-09-23T10:00:00+02:00',
    ends_at: '2026-09-23T16:00:00+02:00',
    break_minutes: 0,
    status: 'confirmed',
    assigned_workers: [{ id: 'next', name: 'Next Worker', is_me: false }],
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

const openShifts = [
  {
    id: 'open-sep19',
    client_name: 'A+',
    location_name: 'A+',
    position_name: 'Servicekraft',
    starts_at: '2026-09-19T11:00:00+02:00',
    ends_at: '2026-09-19T22:00:00+02:00',
    break_minutes: 0,
    status: 'published',
    assigned_workers: [],
  },
  {
    id: 'open-sep30',
    client_name: 'Evangelische Akademie',
    location_name: 'Evangelische Akademie',
    position_name: 'Servicekraft',
    starts_at: '2026-09-30T15:00:00+02:00',
    ends_at: '2026-09-30T19:30:00+02:00',
    break_minutes: 0,
    status: 'published',
    assigned_workers: [],
  },
];

test('employee Dienstplan keeps worker logic while matching admin week navigation and OpenShift layout', async ({ page }) => {
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
      body = openShifts;
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
  await expect(schedule.getByRole('tab', { name: 'Service Zeitplan' })).toBeVisible();
  const weekStrip = schedule.getByTestId('phase8-week-strip');
  await expect(weekStrip).toBeVisible();

  const previews = schedule.locator('.wiw-employee-week-preview');
  await expect(previews).toHaveCount(2);
  await expect(previews.nth(0)).toContainText('Previous W.');
  await expect(previews.nth(0)).toContainText('09:00–15:00');
  await expect(previews.nth(1)).toContainText('Next W.');
  await expect(previews.nth(1)).toContainText('10:00–16:00');

  const currentWeek = schedule.locator('.wiw-employee-week-current');
  const days = currentWeek.locator('.wiw-day-section');
  await expect(days).toHaveCount(7);
  await expect(days.nth(0).locator('header')).toContainText('Mo');
  await expect(days.nth(0).locator('header')).toContainText('14.09.2026');
  await expect(days.nth(2).locator('header')).toContainText('Mi');
  await expect(days.nth(2).locator('header')).toContainText('16.09.2026');

  const wednesday = page.locator('#wiw-employee-day-2026-09-16');
  const beforeTop = await wednesday.evaluate((node) => node.getBoundingClientRect().top);
  await weekStrip.locator('button').nth(3).click();
  await page.waitForTimeout(450);
  const afterTop = await wednesday.evaluate((node) => node.getBoundingClientRect().top);
  expect(afterTop).toBeLessThan(beforeTop);
  expect(afterTop).toBeLessThan(220);

  const wednesdayCards = wednesday.locator('.wiw-shift-card.is-filled');
  await expect(wednesdayCards).toHaveCount(2);
  await expect(wednesdayCards.filter({ hasText: 'Tooba A.' })).toContainText('08:30–19:00');
  await expect(wednesdayCards.filter({ hasText: 'Arina M.' })).toContainText('15:30–21:00');
  await expect(wednesdayCards.first()).toHaveAttribute('style', /--wiw-card-accent/);

  await expect(schedule).not.toContainText('11:00–21:00');

  const total = schedule.getByTestId('phase8-week-total');
  await expect(total).toContainText('Eigene Gesamtstunden');
  await expect(total).toContainText('5.5');

  await wednesdayCards.filter({ hasText: 'Tooba A.' }).click();
  const detail = page.getByTestId('wiw-employee-shift-detail');
  await expect(detail).toContainText('Tooba A.');
  await expect(detail.getByRole('button', { name: 'Nur sichtbar · Service Zeitplan' })).toBeDisabled();

  await detail.getByRole('button', { name: 'Zurück' }).click();
  await schedule.getByRole('tab', { name: 'OpenShifts' }).click();

  await expect(schedule.getByTestId('phase8-week-strip')).toHaveCount(0);
  await expect(schedule.getByTestId('phase8-week-total')).toHaveCount(0);
  const openDays = schedule.locator('.wiw-day-section');
  await expect(openDays).toHaveCount(2);
  await expect(openDays.nth(0).locator('header')).toContainText('19.09.2026');
  await expect(openDays.nth(1).locator('header')).toContainText('30.09.2026');
  await expect(schedule.locator('.wiw-shift-card.is-open')).toHaveCount(2);
  await expect(schedule.locator('.wiw-shift-card.is-open').first()).toContainText('OpenShift');
  await expect(schedule.locator('.wiw-shift-card.is-open').first()).toContainText('SK');
});
