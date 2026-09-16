import { expect, test } from '@playwright/test';

const shifts = [
  {
    id: 'peer-shift',
    client_name: 'Evangelische Akademie',
    location_name: 'Evangelische Akademie',
    position_name: 'Servicekraft',
    starts_at: '2026-09-16T08:30:00+02:00',
    ends_at: '2026-09-16T15:30:00+02:00',
    break_minutes: 0,
    status: 'confirmed',
    assigned_workers: [{ id: 'peer', name: 'Kollege Peer', is_me: false }],
  },
  {
    id: 'own-shift',
    client_name: 'A+',
    location_name: 'Stadthaus am Markt',
    position_name: 'Servicekraft',
    starts_at: '2026-09-16T16:00:00+02:00',
    ends_at: '2026-09-16T22:00:00+02:00',
    break_minutes: 0,
    status: 'confirmed',
    assigned_workers: [{ id: 'me', name: 'Eigener Mitarbeiter', is_me: true }],
  },
];

test('Meine Schichten filters coworkers while Service Zeitplan still shows them', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 780 });
  await page.clock.setFixedTime(new Date('2026-09-16T10:00:00Z'));
  await page.addInitScript(() => {
    localStorage.setItem('access', 'my-shifts-regression');
    localStorage.setItem('refresh', 'my-shifts-regression-refresh');
  });

  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api\//, '');
    let body: any = [];

    if (path === 'auth/me/') {
      body = {
        id: 'me',
        email: 'me@example.test',
        name: 'Eigener Mitarbeiter',
        role: 'worker',
      };
    } else if (path.startsWith('employee/schedule/')) {
      body = { service_schedule: true, shifts };
    } else if (path.startsWith('shifts/available/')) {
      body = [];
    }

    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });

  await page.goto('/?view=schedule');
  const schedule = page.getByTestId('wiw-employee-schedule');
  await expect(schedule).toBeVisible();

  const currentWeek = schedule.locator('.wiw-employee-week-current');
  await expect(schedule.getByRole('tab', { name: 'Service Zeitplan' })).toHaveAttribute('aria-selected', 'true');
  await expect(currentWeek).toContainText('Kollege P.');
  await expect(currentWeek).toContainText('Eigener M.');

  await schedule.getByRole('tab', { name: 'Meine Schichten' }).click();
  await expect(schedule.getByRole('tab', { name: 'Meine Schichten' })).toHaveAttribute('aria-selected', 'true');
  await expect(currentWeek).toContainText('Eigener M.');
  await expect(currentWeek).not.toContainText('Kollege P.');
  await expect(currentWeek.locator('.wiw-shift-card.is-filled')).toHaveCount(1);

  await schedule.getByRole('tab', { name: 'Service Zeitplan' }).click();
  await expect(schedule.getByRole('tab', { name: 'Service Zeitplan' })).toHaveAttribute('aria-selected', 'true');
  await expect(currentWeek).toContainText('Kollege P.');
  await expect(currentWeek.locator('.wiw-shift-card.is-filled')).toHaveCount(2);
});
