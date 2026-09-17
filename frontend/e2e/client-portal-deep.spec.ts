import { expect, Page, Route, test } from '@playwright/test';

const client = {
  id: 'client-user-deep-qa',
  email: 'qa.client.deep@example.test',
  name: 'Claudia Fröhling',
  first_name: 'Claudia',
  last_name: 'Fröhling',
  role: 'client',
  phone: '',
};

const access = {
  client_id: 'client-own',
  client_name: 'Marthas',
  account_name: 'Claudia Fröhling',
  first_name: 'Claudia',
  read_only: false,
  location_scope_id: null,
  location_scope_name: '',
  capabilities: {},
};

function currentWeekShift() {
  const start = new Date();
  start.setUTCHours(16, 0, 0, 0);
  const end = new Date(start.getTime() + 6 * 60 * 60 * 1000);
  return {
    id: 'shift-own',
    client: 'client-own',
    client_name: 'Marthas',
    location: 'location-own',
    location_name: 'Evangelische Akademie',
    position: 'position-service',
    position_name: 'Servicekraft',
    starts_at: start.toISOString(),
    ends_at: end.toISOString(),
    status: 'confirmed',
    required_count: 2,
    filled_count: 2,
    notes: 'Terrasse vorbereiten',
    assigned_workers: [
      { id: 'worker-one', name: 'Anna Einsatz' },
      { id: 'worker-two', name: 'Lukas Einsatz' },
    ],
  };
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

type State = { orderPost?: any; shiftRequestPost?: any; ratingPost?: any };

async function mockClientApi(page: Page, state: State = {}) {
  const shift = currentWeekShift();
  await page.addInitScript(() => {
    localStorage.setItem('access', 'client-deep-e2e');
    localStorage.setItem('refresh', 'client-deep-refresh');
  });

  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api\//, '');
    const method = route.request().method();

    if (path === 'auth/me/') return json(route, client);
    if (path === 'portal/client-access/') return json(route, access);
    if (path === 'portal/client-shifts/') return json(route, [shift]);
    if (path === 'portal/client-documents/') return json(route, [
      {
        id: 'doc-own',
        title: 'Einsatzinformation',
        file: '/media/documents/qa.pdf',
        uploaded_by_name: 'Claudia Fröhling',
        created_at: new Date().toISOString(),
      },
    ]);
    if (path === 'portal/client-order-metadata/') return json(route, {
      locations: [{ id: 'location-own', name: 'Evangelische Akademie' }],
      positions: [{ id: 'position-service', name: 'Servicekraft' }],
    });
    if (path === 'portal/shift-change-requests/' && method === 'POST') {
      state.shiftRequestPost = route.request().postDataJSON();
      return json(route, { id: 'change-request', ...state.shiftRequestPost, status: 'pending' }, 201);
    }
    if (path.startsWith('orders/')) {
      if (method === 'POST') {
        state.orderPost = route.request().postDataJSON();
        return json(route, { id: 'order-new', client: 'client-own', client_name: 'Marthas', ...state.orderPost }, 201);
      }
      return json(route, []);
    }
    if (path === 'portal/rating-candidates/') return json(route, [
      { shift_id: 'shift-past', worker_id: 'worker-one', worker_name: 'Anna Einsatz', location_name: 'Evangelische Akademie', starts_at: '2026-09-14T16:00:00Z', ends_at: '2026-09-14T22:00:00Z', notes: 'Terrasse vorbereiten' },
      { shift_id: 'shift-past', worker_id: 'worker-two', worker_name: 'Lukas Einsatz', location_name: 'Evangelische Akademie', starts_at: '2026-09-14T16:00:00Z', ends_at: '2026-09-14T22:00:00Z', notes: 'Terrasse vorbereiten' },
    ]);
    if (path.startsWith('ratings/')) {
      if (method === 'POST') {
        state.ratingPost = route.request().postDataJSON();
        return json(route, { id: 'rating-new', ...state.ratingPost, created_at: new Date().toISOString() }, 201);
      }
      return json(route, []);
    }
    if (path.startsWith('announcements/')) return json(route, []);
    return json(route, []);
  });
}

test.describe('client portal v4 mobile workflows', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('dashboard and Mehr stay intentionally simple', async ({ page }) => {
    await mockClientApi(page);
    await page.goto('/');

    const home = page.getByTestId('client-portal-v2-home');
    await expect(home.getByRole('heading', { name: 'Guten Tag, Claudia' })).toBeVisible();
    await expect(home.getByRole('button', { name: /Personal anfragen/ })).toBeVisible();
    await expect(home.getByText('Einsatzinformation')).toBeVisible();
    await expect(home.getByText('Was möchtest du erledigen?')).toHaveCount(0);
    await expect(home.getByText('AKTIONEN')).toHaveCount(0);

    const tabs = page.getByTestId('client-v2-tabbar');
    await tabs.getByRole('button', { name: 'Weitere Bereiche öffnen' }).click();
    const more = page.getByTestId('client-v2-more');
    await expect(more.getByRole('button', { name: /Personal anfragen/ })).toBeVisible();
    await expect(more.getByRole('button', { name: /Dokumente/ })).toBeVisible();
    await expect(more.getByRole('button', { name: /Mitteilungen/ })).toBeVisible();
    await expect(more.getByRole('button', { name: /Profil & Sicherheit/ })).toBeVisible();
    await expect(more.getByRole('button', { name: /Servicecenter/ })).toHaveCount(0);
    await expect(more.getByRole('button', { name: /Verträge/ })).toHaveCount(0);
  });

  test('client can submit a mobile-safe personnel request and shift change request', async ({ page }) => {
    const state: State = {};
    await mockClientApi(page, state);
    await page.goto('/');

    const tabs = page.getByTestId('client-v2-tabbar');
    await tabs.getByRole('button', { name: 'Weitere Bereiche öffnen' }).click();
    await page.getByTestId('client-v2-more').getByRole('button', { name: /Personal anfragen/ }).click();
    const orders = page.locator('.client-v4-orders');
    await expect(orders.getByRole('heading', { name: 'Personal anfragen' })).toBeVisible();
    await orders.getByRole('button', { name: /Neuer Auftrag/ }).click();

    const orderDialog = page.getByRole('dialog');
    await orderDialog.locator('select').nth(0).selectOption('location-own');
    await orderDialog.locator('select').nth(1).selectOption('position-service');
    await orderDialog.locator('input[type="datetime-local"]').nth(0).fill('2026-10-10T18:00');
    await orderDialog.locator('input[type="datetime-local"]').nth(1).fill('2026-10-10T23:00');
    await orderDialog.locator('input[type="number"]').fill('3');
    await orderDialog.locator('textarea').fill('Bitte erfahrenes Servicepersonal.');
    await orderDialog.getByRole('button', { name: 'Anfrage senden' }).click();
    await expect.poll(() => state.orderPost).toBeTruthy();
    expect(state.orderPost.requested_staff).toBe(3);
    expect(state.orderPost.functions).toEqual(['position-service']);

    await tabs.getByRole('button', { name: 'Kalender' }).click();
    const schedule = page.locator('.client-v4-schedule');
    await expect(schedule).toBeVisible();
    await schedule.getByRole('button', { name: /Evangelische Akademie/ }).click();
    await expect(page.getByText('Terrasse vorbereiten', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: /Zeit \/ Datum ändern/ }).click();
    const changeDialog = page.getByRole('dialog');
    await changeDialog.locator('textarea').fill('Eine Stunde später beginnen.');
    await changeDialog.getByRole('button', { name: 'Änderung senden' }).click();
    await expect.poll(() => state.shiftRequestPost).toBeTruthy();
    expect(state.shiftRequestPost.shift).toBe('shift-own');
    expect(state.shiftRequestPost.request_type).toBe('change');
  });

  test('rating flow chooses the compact shift first, then one worker at a time', async ({ page }) => {
    const state: State = {};
    await mockClientApi(page, state);
    await page.goto('/');

    const tabs = page.getByTestId('client-v2-tabbar');
    await tabs.getByRole('button', { name: 'Bewerten' }).click();
    const ratings = page.locator('.client-v4-ratings');
    await expect(ratings.getByRole('heading', { name: 'Einsatz auswählen' })).toBeVisible();
    const shiftButton = ratings.getByRole('button', { name: /Evangelische Akademie.*Terrasse vorbereiten/ });
    await expect(shiftButton).toBeVisible();
    await shiftButton.click();
    await expect(ratings.getByRole('heading', { name: 'Einzeln bewerten' })).toBeVisible();
    await expect(ratings.getByText('Anna Einsatz')).toBeVisible();
    await expect(ratings.getByText('Lukas Einsatz')).toBeVisible();

    await ratings.getByRole('button', { name: /Anna Einsatz/ }).click();
    const ratingDialog = page.getByRole('dialog');
    await ratingDialog.locator('textarea').fill('Sehr gut.');
    await ratingDialog.getByRole('button', { name: 'Bewertung speichern' }).click();
    await expect.poll(() => state.ratingPost).toBeTruthy();
    expect(state.ratingPost.shift).toBe('shift-past');
    expect(state.ratingPost.worker).toBe('worker-one');
  });
});
