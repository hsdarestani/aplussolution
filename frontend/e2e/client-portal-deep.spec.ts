import { expect, Page, Route, test } from '@playwright/test';

const client = {
  id: 'client-user-deep-qa',
  email: 'qa.client.deep@example.test',
  name: 'QA Claudia Kunde',
  first_name: 'Claudia',
  last_name: 'Kunde',
  role: 'client',
  phone: '',
};

const candidate = {
  shift_id: 'shift-own-past',
  worker_id: 'worker-own-past',
  worker_name: 'Anna Einsatz',
  position_name: 'Servicekraft',
  location_name: 'QA Eigener Standort',
  starts_at: '2026-08-20T16:00:00Z',
  ends_at: '2026-08-20T20:00:00Z',
};

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function mockClientApi(page: Page, state: { ratingPost?: any } = {}) {
  await page.addInitScript(() => {
    localStorage.setItem('access', 'client-deep-e2e');
    localStorage.setItem('refresh', 'client-deep-refresh');
  });

  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api\//, '');
    const method = route.request().method();

    if (path === 'auth/me/') return json(route, client);
    if (path === 'dashboard/') return json(route, { active_orders: 1, upcoming_shifts: 1, contracts_to_sign: 1 });

    if (path === 'operations/') {
      return json(route, {
        role: 'client',
        unread_notifications: 1,
        notifications: [{ id: 'n-own', title: 'Eigener Hinweis', body: 'Nur für diesen Kunden', created_at: '2026-08-22T08:00:00Z', read_at: null }],
        coverage_gaps: [{ order: 'order-own', client: 'client-own', title: 'Eigener Auftrag', client_name: 'QA Client GmbH', requested: 3, assigned: 2, open_shifts: 1, gap: 1, starts_at: '2026-08-25T15:00:00Z', severity: 'warning', message: '1 Position ist noch nicht fest besetzt.' }],
        contracts_due: 1,
        documents: 1,
        open_orders: 1,
      });
    }
    if (path === 'operations/folders/') {
      return json(route, {
        workers: [],
        clients: [{ id: 'client-own', name: 'QA Client GmbH', customer_number: 'KD-QA', documents: 1, contracts: 1, orders: 1 }],
      });
    }
    if (path === 'operations/notifications/read-all/' && method === 'POST') return json(route, { updated: 1 });

    if (path.startsWith('orders/')) {
      if (method === 'POST') {
        const body = route.request().postDataJSON();
        return json(route, { id: 'order-new', client: 'client-own', client_name: 'QA Client GmbH', ...body }, 201);
      }
      return json(route, [{ id: 'order-own', title: 'Eigener Auftrag', client: 'client-own', client_name: 'QA Client GmbH', location: 'location-own', location_name: 'QA Eigener Standort', starts_at: '2026-08-25T15:00:00Z', ends_at: '2026-08-25T20:00:00Z', requested_staff: 3, status: 'planning', description: 'Service' }]);
    }
    if (path === 'locations/') return json(route, [{ id: 'location-own', name: 'QA Eigener Standort', client: 'client-own', client_name: 'QA Client GmbH', address: 'Musterweg 1, Frankfurt', active: true }]);

    if (path.startsWith('shifts/')) return json(route, [{ id: candidate.shift_id, client: 'client-own', client_name: 'QA Client GmbH', location: 'location-own', location_name: candidate.location_name, position: 'position-service', position_name: candidate.position_name, starts_at: candidate.starts_at, ends_at: candidate.ends_at, status: 'completed', required_count: 1 }]);

    if (path.startsWith('contracts/')) return json(route, [{ id: 'contract-own', title: 'ANÜ – QA Client GmbH', client: 'client-own', client_name: 'QA Client GmbH', status: 'sent', pdf: '/media/contracts/qa.pdf', signatures: [], readiness: { generation_allowed: false, send_allowed: false, document_current: true, pending_signature_roles: ['client'], blocking_issues: [] }, updated_at: '2026-08-22T08:00:00Z' }]);

    if (path.startsWith('documents/')) return json(route, [{ id: 'doc-own', title: 'Einsatzinformation', client: 'client-own', client_name: 'QA Client GmbH', folder: 'orders', visibility: 'client', file: '/media/documents/qa.pdf', created_at: '2026-08-22T08:00:00Z' }]);
    if (path.startsWith('payroll/')) return json(route, []);

    if (path === 'portal/rating-candidates/') return json(route, [candidate]);
    if (path.startsWith('ratings/')) {
      if (method === 'POST') {
        state.ratingPost = route.request().postDataJSON();
        return json(route, { id: 'rating-new', client: 'client-own', client_name: 'QA Client GmbH', worker: candidate.worker_id, worker_name: candidate.worker_name, shift: candidate.shift_id, ...state.ratingPost, created_at: '2026-08-22T08:00:00Z' }, 201);
      }
      return json(route, []);
    }

    if (path === 'portal/message-recipients/') return json(route, [{ id: 'dispatcher-1', name: 'A+ Disposition', role: 'manager' }]);
    if (path.startsWith('conversations/')) return json(route, []);

    return json(route, []);
  });
}

async function openDesktopNav(page: Page, label: string) {
  await page.getByText(label, { exact: true }).first().click();
}

test('client portal keeps servicecenter, orders, documents and chat scoped to the client', async ({ page }) => {
  await mockClientApi(page);
  await page.goto('/');

  await expect(page.getByText('QA Claudia Kunde').first()).toBeVisible();

  await openDesktopNav(page, 'Servicecenter');
  await expect(page.getByRole('heading', { name: 'Servicecenter' })).toBeVisible();
  await expect(page.getByText('Eigener Auftrag')).toBeVisible();
  await expect(page.getByText('QA Client GmbH')).toBeVisible();
  await expect(page.getByText('Eigener Hinweis')).toBeVisible();
  await expect(page.getByText(/Fremd|Andere GmbH/i)).toHaveCount(0);

  await openDesktopNav(page, 'Aufträge');
  await expect(page.getByRole('heading', { name: 'Aufträge' })).toBeVisible();
  await expect(page.getByText('Eigener Auftrag')).toBeVisible();
  await page.getByRole('button', { name: 'Neuer Auftrag' }).click();
  const locationSelect = page.locator('ion-select').filter({ hasText: 'Einsatzort' }).last();
  await locationSelect.click();
  await expect(page.getByRole('radio', { name: 'QA Eigener Standort' })).toBeVisible();
  await page.keyboard.press('Escape');

  await openDesktopNav(page, 'Dokumente');
  await expect(page.getByRole('heading', { name: /Dokumente/ })).toBeVisible();
  await expect(page.getByText('Einsatzinformation')).toBeVisible();

  await openDesktopNav(page, 'Nachrichten');
  await expect(page.getByRole('heading', { name: 'Nachrichten' })).toBeVisible();
  await page.getByRole('button', { name: 'Unterhaltung' }).click();
  const participants = page.locator('ion-select').filter({ hasText: 'Teilnehmer' }).last();
  await participants.click();
  await expect(page.getByRole('checkbox', { name: /A\+ Disposition/ })).toBeVisible();
  await expect(page.getByText(/worker@example|client@example/i)).toHaveCount(0);
});

test('client rating uses only completed assigned candidate and submits the bound shift', async ({ page }) => {
  const state: { ratingPost?: any } = {};
  await mockClientApi(page, state);
  await page.goto('/');

  await openDesktopNav(page, 'Mitarbeiter bewerten');
  await expect(page.getByRole('heading', { name: 'Mitarbeiter bewerten' })).toBeVisible();
  await page.getByRole('button', { name: 'Neue Bewertung' }).click();

  const shiftSelect = page.locator('ion-select').filter({ hasText: 'Einsatz *' }).last();
  await shiftSelect.click();
  await page.getByRole('radio', { name: /Servicekraft/ }).click();

  const workerSelect = page.locator('ion-select').filter({ hasText: 'Mitarbeiter *' }).last();
  await workerSelect.click();
  await expect(page.getByRole('radio', { name: 'Anna Einsatz' })).toBeVisible();
  await page.getByRole('radio', { name: 'Anna Einsatz' }).click();

  await page.getByRole('button', { name: 'Speichern' }).click();
  await expect.poll(() => state.ratingPost).toBeTruthy();
  expect(state.ratingPost.shift).toBe(candidate.shift_id);
  expect(state.ratingPost.worker).toBe(candidate.worker_id);
  await expect(page.getByText('Bewertung wurde gespeichert.')).toBeVisible();
});

test.describe('client mobile shell', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('client can reach secondary portal areas from Mehr without horizontal overflow', async ({ page }) => {
    await mockClientApi(page);
    await page.goto('/');

    await page.getByRole('button', { name: 'Weitere Bereiche öffnen' }).click();
    await expect(page.getByRole('heading', { name: 'Weitere Bereiche' })).toBeVisible();
    await expect(page.getByRole('button', { name: /Verträge & Signatur/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Dokumente/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Mitarbeiter bewerten/ })).toBeVisible();

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });
});
